//+------------------------------------------------------------------+
//|                                        H4M5_Identification.mq5   |
//|        H4 Context -> M5 Identification Indicator  v1.00          |
//|                                                                  |
//|  MARK ONLY.  NO ENTRY DECISION.  NO AUTO TRADE.                  |
//|  Trend-following only.  No historical repaint.  No future leak.  |
//|                                                                  |
//|  Specification: docs/01_Architecture_Spec_v1.00.md               |
//|  Decisions D-1..D-7: docs/02_Conflict_And_Business_Rule_Issues.. |
//+------------------------------------------------------------------+
#property copyright "H4M5 Identification"
#property version   "2.00"
#property description "H4 Context -> H4 POI -> M5 Block -> ARMED -> CISD / MSS / BPR / PA"
#property description "MARK ONLY - the indicator never decides an entry."
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

#include <HMI/HMI_AlertManager.mqh>

//+------------------------------------------------------------------+
//| Phase 0 helper: consume one CLOSED H4 bar                        |
//+------------------------------------------------------------------+
void H4ProcessBar(const int h)
  {
   SwingDetect(g_h4, h, PERIOD_H4, InpH4SwingLeft, InpH4SwingRight,
               g_h4sw, g_h4sw_n, MAX_H4_SWINGS);
   LiqOnBar(h);

   CtxState before = g_ctx;
   CtxEventType ev = H4ContextOnBar(h);

   if(ev == EV_BOS_UP || ev == EV_BOS_DOWN || ev == EV_CHOCH_UP || ev == EV_CHOCH_DOWN)
      TRNewVersion(h, ev);
   else
      TRExtendOnSwing(h);

   int fi = FvgDetect(g_h4, h, PERIOD_H4, g_h4fvg, g_h4fvg_n, MAX_H4_FVG);
   POIOnBar(h, fi);
   POIInvalidateOnBar(h);

   if(before != g_ctx && SafeIdx(g_active_cyc, g_cyc_n))
      g_cyc[g_active_cyc].ctx_changed = true;          // diagnostic only (D-1)
  }

//+------------------------------------------------------------------+
//| Phase 7 logging half (CSV, for build-vs-live diffing)            |
//+------------------------------------------------------------------+
void LogPhase7()
  {
   if(!InpLogSignals) return;
   string tag = (g_live ? "HMI-LIVE" : "HMI-BUILD");
   for(int ci = 0; ci < g_cyc_n; ci++)
     {
      for(int m = 0; m < MDL_COUNT; m++)
        {
         if(g_cyc[ci].result[m] != MR_CONFIRMED) continue;
         if((g_cyc[ci].logged_mask & (1 << m)) != 0) continue;
         g_cyc[ci].logged_mask |= (1 << m);
         double lvl = (m == MDL_CISD ? g_cyc[ci].cisd_level
                      : (m == MDL_MSS ? g_cyc[ci].mss_level : 0.0));
         datetime rt = (m == MDL_CISD ? g_cyc[ci].cisd_ref_time
                       : (m == MDL_MSS ? g_cyc[ci].mss_ref_time : 0));
         PrintFormat("%s,%s,MODEL,%d,%I64d,%I64d,%s,%s,%s,%s,%s,%s",
                     tag, _Symbol, g_cyc[ci].dir, g_cyc[ci].cycle_id, g_cyc[ci].block_id,
                     (g_cyc[ci].anchor_type == BT_M5_OB ? "OB" : "BREAKER"),
                     ModelName(m),
                     TimeToString(CloseTimeOf(g_cyc[ci].cfm_time[m], PERIOD_M5), TIME_DATE|TIME_SECONDS),
                     DoubleToString(g_cyc[ci].cfm_price[m], _Digits),
                     TimeToString(rt, TIME_DATE|TIME_SECONDS),
                     DoubleToString(lvl, _Digits));
        }
     }
  }

//+------------------------------------------------------------------+
//| The ONE function used by both historical build and live update   |
//| (Rule 51). Phase order is frozen (Spec 17.2).                    |
//+------------------------------------------------------------------+
void ProcessClosedM5Bar(const int n)
  {
   if(!SafeIdx(n, g_m5_n)) return;
   datetime t = CloseTimeOf(g_m5[n].time, PERIOD_M5);

   //--- Phase 0: H4 sync (only bars that closed BEFORE this bar opened)
   while(g_h4_cursor < g_h4_n && H4VisibleTo(g_h4[g_h4_cursor].time, g_m5[n].time))
     {
      H4ProcessBar(g_h4_cursor);
      g_h4_cursor++;
     }

   //--- Phase 1: M5 structure ---------------------------------------
   SwingDetect(g_m5, n, PERIOD_M5, InpM5SwingLeft, InpM5SwingRight,
               g_m5sw, g_m5sw_n, MAX_M5_SWINGS);
   int fi = FvgDetect(g_m5, n, PERIOD_M5, g_m5fvg, g_m5fvg_n, MAX_M5_FVG);

   //--- warmup: build structure, but never mark anything ------------
   if(n < InpWarmupSuppressBars) return;

   M5BlocksOnFVG(n, fi);

   //--- Phase 2: invalidation pass ----------------------------------
   M5BlockInvalidate(n);
   if(SafeIdx(g_active_cyc, g_cyc_n))
     {
      int bi = BlockFindById(g_cyc[g_active_cyc].block_id);
      if(bi >= 0 && g_blk[bi].state == BLOCK_INVALID)
        {
         g_cyc[g_active_cyc].anchor_invalidated = true;
         if(InpStopIdentificationOnBlockInvalidation) CycCloseActive(t);   // D-5 (default off)
        }
     }

   //--- Phase 3: refinement session ---------------------------------
   SessionMaintain(n);
   POIReArmCheck(n);                          // A-06, no-op while InpPOIMaxSessions == 1
   int pi = POITouchedBy(n);
   if(pi >= 0)
     {
      g_poi[pi].state        = POI_TOUCHED;
      g_poi[pi].touched_time = t;
      g_poi[pi].vis          = -1;
      SessionStart(pi, n);
     }

   //--- Phase 4: identification for the CURRENT cycle (n > A) -------
   if(SafeIdx(g_active_cyc, g_cyc_n) &&
      g_cyc[g_active_cyc].state == CY_ACTIVE &&
      n > g_cyc[g_active_cyc].armed_index)
     {
      IdentificationCycle cy = g_cyc[g_active_cyc];
      // six independent calls: no short-circuit, no model consumes another
      CISD_Check(cy, n);
      MSS_Check(cy, n);
      BPR_Check(cy, n);
      PA_CheckEngulfing(cy, n);
      PA_CheckRejection(cy, n);
      PA_CheckBreakRetest(cy, n);
      g_cyc[g_active_cyc] = cy;
     }

   //--- Phase 5: touch / ARMED arbitration --------------------------
   bool armed_now = false;
   int w = M5TouchArbitrate(n);
   if(w >= 0)
     {
      CycCloseActive(t);                       // old cycle ends here (Rule 15)
      g_active_cyc = CycCreate(w, n);
      armed_now    = true;
      if(InpAlertOnArmed)
         AlertPush((g_blk[w].block_type == BT_M5_OB ? "M5 OB ARMED" : "M5 BREAKER ARMED") +
                   "  cycle #" + IntegerToString(g_cyc[g_active_cyc].cycle_id));
     }

   //--- Phase 5b: ARMED-bar PA (D-4) --------------------------------
   if(armed_now && InpPAAllowArmedBarConfirm && SafeIdx(g_active_cyc, g_cyc_n))
     {
      IdentificationCycle cy = g_cyc[g_active_cyc];
      PA_CheckEngulfingArmedBar(cy, n);
      PA_CheckRejectionArmedBar(cy, n);
      g_cyc[g_active_cyc] = cy;
     }

   //--- Phase 6: post lifecycle -------------------------------------
   BPRLifecycle(n);

   //--- Phase 7 (logging half; drawing happens once per batch) ------
   LogPhase7();
  }

//+------------------------------------------------------------------+
//| State reset + historical build                                   |
//+------------------------------------------------------------------+
void ResetEngine()
  {
   g_next_id = 1;
   g_h4sw_n = 0;  g_h4fvg_n = 0;  g_poi_n = 0;  g_tr_n = 0;  g_liq_n = 0;
   g_m5sw_n = 0;  g_m5fvg_n = 0;  g_blk_n = 0;  g_brk_n = 0;
   g_cyc_n  = 0;  g_bpr_n  = 0;   g_active_cyc = -1;
   g_h4_cursor = 0;
   g_ctx = CTX_RANGE;  g_ctx_pending = DIR_NONE;
   g_ctx_strength = 0; g_ctx_messy = false; g_ctx_time = 0; g_ctx_bars = 0;
   g_diag_poi_rejected_gap = 0;  g_diag_blk_rejected_gap = 0;
   g_alertq_n = 0;
   g_sess.active = false;  g_sess.id = 0;  g_sess.poi_id = 0;
   g_sess.dir = DIR_NONE;  g_sess.start_index = 0;  g_sess.start_time = 0;
   g_sess.end_time = 0;    g_sess.end_reason = SE_NONE;

   OM_DeleteOwnAll();
   OM_RecreateMarker();
  }

void BuildHistory()
  {
   g_live = false;
   for(int n = 0; n < g_m5_n; n++) ProcessClosedM5Bar(n);
   g_live = true;
   g_alertq_n = 0;                     // historical build never alerts
   OM_SyncAll();
   OM_Trim();
   ChartRedraw();
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   StylesInit();                 // resolve all style inputs before anything draws
   KZInit();                     // resolve kill zone windows (display only)

   if(!OM_ClaimInstance())
     {
      Print("HMI: could not claim an instance tag - too many instances on this chart");
      return(INIT_FAILED);
     }
   IndicatorSetString(INDICATOR_SHORTNAME, "HMI v" + HMI_VERSION + " [" + g_inst + "]");

   double m = 0.0;
   switch(InpBreakMarginMode)
     {
      case MARGIN_POINTS:   m = InpBreakMarginPoints * _Point; break;
      case MARGIN_ATR_FRAC: m = 0.0;                           break;   // per-bar, see log below
      default:              m = InpBreakMarginPips * PipSize();
     }
   if(InpBreakMarginMode == MARGIN_ATR_FRAC)
      PrintFormat("HMI: break margin mode = ATR_FRAC (%.4f x ATR14, evaluated per bar)",
                  InpBreakMarginATRFrac);
   else
     {
      int mp = (int)MathRound(m / _Point);
      PrintFormat("HMI: effective break margin = %s price / %d points",
                  DoubleToString(m, _Digits), mp);
      if(mp <= 0)
         Print("HMI: WARNING - break margin degenerates to 0 on this symbol. "
               "See BRI-03 / D-6: consider MARGIN_POINTS or MARGIN_ATR_FRAC.");
     }

   g_ready = false;
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   //--- first run / rebuild ----------------------------------------
   if(!g_ready)
     {
      if(!SeriesInit()) return(rates_total);      // data not ready: retry next tick
      ResetEngine();
      BuildHistory();
      g_ready = true;
      return(rates_total);
     }

   //--- H4 first, so Phase 0 can consume it -------------------------
   int ah = SeriesAppend(PERIOD_H4, g_h4, g_h4_n, g_h4_atr);
   int am = SeriesAppend(PERIOD_M5, g_m5, g_m5_n, g_m5_atr);
   if(ah < 0 || am < 0) { g_ready = false; return(rates_total); }

   if(am > 0)
     {
      for(int n = g_m5_n - am; n < g_m5_n; n++) ProcessClosedM5Bar(n);
      OM_SyncAll();
      OM_Trim();
      AlertFlush();
      ChartRedraw();
      return(rates_total);
     }

   //--- bar 0: preview only, never state (Spec 8.2 / 18.4) ----------
   static ulong last_preview = 0;
   ulong now = GetTickCount64();
   if(now - last_preview >= (ulong)MathMax(50, InpPreviewUpdateMs))
     {
      last_preview = now;
      OM_Preview();
      ChartRedraw();
     }
   return(rates_total);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   OM_DeleteOwnAll();          // own instance only (Rule 55)
   ChartRedraw();
  }
//+------------------------------------------------------------------+
