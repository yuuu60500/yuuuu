//+------------------------------------------------------------------+
//| HMI_ObjectManager.mqh — the ONLY module allowed to call Object*  |
//| State is never read back from the chart (Rule 53).               |
//+------------------------------------------------------------------+
#ifndef HMI_OM_MQH
#define HMI_OM_MQH
#include "HMI_BPREngine.mqh"
#include "HMI_Style.mqh"
#include "HMI_PriceActionEngine.mqh"

#define TT_MARK  "MK"
#define TT_CTX   "CX"
#define TT_TR    "TR"
#define TT_LIQ   "LQ"
#define TT_POI   "P4"
#define TT_BLK   "MB"
#define TT_ARM   "MA"
#define TT_MDL   "ML"
#define TT_LVL   "LV"
#define TT_BPR   "BZ"
#define TT_PRV   "DB"

string OM_Prefix() { return(HMI_PREFIX + "_" + g_inst + "_"); }

string OM_Name(const string tt, const long owner, const int sub)
  {
   return(OM_Prefix() + tt + "_" + IntegerToString(owner) + "_" + IntegerToString(sub));
  }

void OM_Register(const string name)
  {
   if(g_obj_n >= MAX_OBJREG) return;
   g_obj[g_obj_n] = name;
   g_obj_n++;
  }

//--- multi-instance safety (Rule 55) --------------------------------
bool OM_ClaimInstance()
  {
   long h = ChartID();
   for(int i = 0; i < StringLen(_Symbol); i++)
      h = h * 31 + StringGetCharacter(_Symbol, i);

   for(int k = 0; k < 64; k++)
     {
      int  v   = (int)((h + (long)k * 40503) & 0xFFFF);
      string tag = StringFormat("%04X", v);
      string mk  = HMI_PREFIX + "_" + tag + "_" + TT_MARK + "_0_0";
      if(ObjectFind(0, mk) >= 0) continue;                 // taken by another instance
      if(!ObjectCreate(0, mk, OBJ_LABEL, 0, 0, 0)) continue;
      ObjectSetInteger(0, mk, OBJPROP_TIMEFRAMES, OBJ_NO_PERIODS);
      ObjectSetInteger(0, mk, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, mk, OBJPROP_SELECTABLE, false);
      g_inst = tag;
      OM_Register(mk);
      return(true);
     }
   return(false);
  }

void OM_DeleteOwnAll()
  {
   string pfx = OM_Prefix();
   for(int i = ObjectsTotal(0, -1, -1) - 1; i >= 0; i--)
     {
      string nm = ObjectName(0, i, -1, -1);
      if(StringFind(nm, pfx) == 0) ObjectDelete(0, nm);     // own instance only
     }
   g_obj_n = 0;
  }

void OM_RecreateMarker()
  {
   string mk = HMI_PREFIX + "_" + g_inst + "_" + TT_MARK + "_0_0";
   if(ObjectCreate(0, mk, OBJ_LABEL, 0, 0, 0))
     {
      ObjectSetInteger(0, mk, OBJPROP_TIMEFRAMES, OBJ_NO_PERIODS);
      ObjectSetInteger(0, mk, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, mk, OBJPROP_SELECTABLE, false);
     }
   OM_Register(mk);
  }

void OM_Unregister(const string name)
  {
   for(int i = 0; i < g_obj_n; i++)
      if(g_obj[i] == name)
        {
         for(int k = i + 1; k < g_obj_n; k++) g_obj[k-1] = g_obj[k];
         g_obj_n--;
         return;
        }
  }

// Drop the graphics of one owner while its record stays in memory
// (Spec 14.7: graphics are trimmed, records are not).
void OM_DeleteOwner(const string tt, const long owner, const int subs)
  {
   for(int s2 = 0; s2 < subs; s2++)
     {
      string nm = OM_Name(tt, owner, s2);
      ObjectDelete(0, nm);
      OM_Unregister(nm);
     }
  }

bool OM_Protected(const string name)
  {
   // the instance marker owns the tag and the panel is rebuilt every bar:
   // trimming either one would break multi-instance safety or flicker
   return(StringFind(name, "_" + TT_MARK + "_") >= 0 ||
          StringFind(name, "_" + TT_CTX  + "_") >= 0);
  }

void OM_Trim()
  {
   int lim = MathMax(50, InpObjectHistoryLimit);
   int i = 0;
   while(g_obj_n > lim && i < g_obj_n)
     {
      if(OM_Protected(g_obj[i])) { i++; continue; }
      ObjectDelete(0, g_obj[i]);
      for(int k = i + 1; k < g_obj_n; k++) g_obj[k-1] = g_obj[k];
      g_obj_n--;
     }
  }

//--- primitives -----------------------------------------------------
void OM_Rect(const string name, const datetime t1, const double p1,
             const datetime t2, const double p2, const StyleZone &st)
  {
   if(!ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2))
     {
      ObjectMove(0, name, 0, t1, p1);
      ObjectMove(0, name, 1, t2, p2);
     }
   else OM_Register(name);
   ObjectSetInteger(0, name, OBJPROP_COLOR, st.clr);
   ObjectSetInteger(0, name, OBJPROP_FILL, st.fill);
   ObjectSetInteger(0, name, OBJPROP_STYLE, st.style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, st.width);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void OM_Text(const string name, const datetime t, const double p,
             const string text, const StyleText &st, const ENUM_ANCHOR_POINT anchor)
  {
   if(!ObjectCreate(0, name, OBJ_TEXT, 0, t, p))
      ObjectMove(0, name, 0, t, p);
   else OM_Register(name);
   ObjectSetString(0, name, OBJPROP_TEXT, text);            // text never goes in the name
   ObjectSetString(0, name, OBJPROP_FONT, InpFontName);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, st.size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, st.clr);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void OM_Level(const string name, const datetime t1, const datetime t2,
              const double price, const StyleZone &st)
  {
   if(!ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price))
     {
      ObjectMove(0, name, 0, t1, price);
      ObjectMove(0, name, 1, t2, price);
     }
   else OM_Register(name);
   ObjectSetInteger(0, name, OBJPROP_COLOR, st.clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, st.style);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, st.width);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void OM_Panel(const int line, const string text)
  {
   string name = OM_Name(TT_CTX, 0, line);
   if(!ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0)) { }
   else OM_Register(name);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, InpPanelX);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, InpPanelY + line * (TS_PANEL.size + 6));
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, InpFontName);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, TS_PANEL.size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, TS_PANEL.clr);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

//--- helpers --------------------------------------------------------
datetime OM_RightEdge()
  {
   datetime last = (g_m5_n > 0 ? g_m5[g_m5_n-1].time : TimeCurrent());
   return(last + (datetime)((long)InpLevelLineExtendBars * PeriodSeconds(PERIOD_M5)));
  }

int POIVis(const H4POI &p)
  {
   if(p.state == POI_INVALID || p.state == POI_EXPIRED) return(2);
   return(p.state == POI_TOUCHED ? 1 : 0);
  }

int BlkVis(const M5Block &b)
  {
   switch(b.state)
     {
      case BLOCK_ARMED:   return(3);
      case BLOCK_TOUCHED: return(2);
      case BLOCK_INVALID:
      case BLOCK_EXPIRED: return(4);
     }
   return(1);
  }

//====================== full sync ===================================
void OM_SyncAll()
  {
   datetime redge = OM_RightEdge();

   //--- context panel ----------------------------------------------
   if(InpShowH4Context)
     {
      string s1 = "H4 CONTEXT: " + CtxName(g_ctx) +
                  (g_ctx == CTX_TRANSITION ? " (pending " + (g_ctx_pending == DIR_BULL ? "UP" : "DOWN") + ")" : "") +
                  "   strength " + IntegerToString(g_ctx_strength) +
                  (g_ctx_messy ? "   quality MESSY" : "   quality CLEAN");
      int act = 0;
      for(int i = 0; i < g_poi_n; i++) if(g_poi[i].state == POI_ACTIVE) act++;
      string s2 = "H4 POI: " + IntegerToString(act) + " ACTIVE / " +
                  IntegerToString(g_diag_poi_rejected_gap) + " REJECTED-BY-GAP" +
                  "   |   M5 BLOCK GAP-REJECTED: " + IntegerToString(g_diag_blk_rejected_gap);
      string s3 = "SESSION: " + (g_sess.active ? "ACTIVE since " +
                  TimeToString(g_sess.start_time, TIME_DATE|TIME_MINUTES) : "none");
      string s4 = "CYCLE: none";
      if(SafeIdx(g_active_cyc, g_cyc_n))
        {
         IdentificationCycle cy = g_cyc[g_active_cyc];
         string st = "";
         for(int m = 0; m < MDL_COUNT; m++)
           {
            string tagm = ModelName(m) + "=";
            if(cy.result[m] == MR_CONFIRMED) tagm += "OK";
            else if(cy.result[m] == MR_NA)   tagm += "N/A";
            else if(cy.result[m] == MR_PASS) tagm += "PASS";
            else                             tagm += "-";
            st += tagm + " ";
           }
         s4 = "CYCLE #" + IntegerToString(cy.cycle_id) + " " +
              (cy.dir == DIR_BULL ? "BULL" : "BEAR") + "  " + st +
              (cy.anchor_invalidated ? " [ANCHOR INVALIDATED]" : "") +
              (cy.ctx_changed ? " [CTX CHANGED DURING CYCLE]" : "");
        }
      OM_Panel(0, "HMI v" + HMI_VERSION + "  MARK ONLY - NO ENTRY DECISION");
      OM_Panel(1, s1);
      OM_Panel(2, s2);
      OM_Panel(3, s3);
      OM_Panel(4, s4);
     }

   //--- trading range ----------------------------------------------
   if(InpShowTradingRange && g_tr_n > 0)
     {
      int i = g_tr_n - 1;
      OM_Rect(OM_Name(TT_TR, g_tr[i].version_id, 0), g_tr[i].valid_from, g_tr[i].a_hi,
              redge, g_tr[i].a_lo, ZS_TRANGE);
     }

   //--- liquidity ---------------------------------------------------
   if(InpShowLiquidity)
      for(int i = 0; i < g_liq_n; i++)
        {
         if(g_liq[i].swept) continue;
         OM_Level(OM_Name(TT_LIQ, g_liq[i].id, 0), g_liq[i].origin_time, redge,
                  g_liq[i].price, g_liq[i].type == DIR_BULL ? ZS_BSL : ZS_SSL);
        }

   //--- H4 POI ------------------------------------------------------
   if(InpShowH4POI)
      for(int i = 0; i < g_poi_n; i++)
        {
         if(g_poi[i].out_of_window)          // left the display window: drop graphics once
           {
            if(g_poi[i].vis >= 0) { OM_DeleteOwner(TT_POI, g_poi[i].id, 2); g_poi[i].vis = -2; }
            continue;
           }
         int vis = POIVis(g_poi[i]);
         bool dead = (vis == 2);
         if(dead && g_poi[i].vis == vis) continue;
         StyleZone zst = POIStyleOf(g_poi[i]);
         datetime t2 = dead ? (g_poi[i].invalid_time > 0 ? g_poi[i].invalid_time : redge) : redge;
         OM_Rect(OM_Name(TT_POI, g_poi[i].id, 0), g_poi[i].origin_time, g_poi[i].hi,
                 t2, g_poi[i].lo, zst);
         OM_Text(OM_Name(TT_POI, g_poi[i].id, 1), g_poi[i].origin_time, g_poi[i].hi,
                 "H4 POI", TS_POI, ANCHOR_LEFT_LOWER);
         g_poi[i].vis = vis;
        }

   //--- M5 blocks ---------------------------------------------------
   if(InpShowM5Blocks)
      for(int i = 0; i < g_blk_n; i++)
        {
         if(!InpShowCounterDirBlocks && g_blk[i].counter_dir) continue;
         int vis = BlkVis(g_blk[i]);
         bool dead = (vis == 4);
         if(dead && g_blk[i].vis == vis) continue;
         StyleZone bst = BlockStyleOf(g_blk[i]);
         datetime t2 = dead ? (g_blk[i].invalid_time > 0 ? g_blk[i].invalid_time : redge) : redge;
         OM_Rect(OM_Name(TT_BLK, g_blk[i].id, 0), g_blk[i].origin_time, g_blk[i].hi,
                 t2, g_blk[i].lo, bst);
         g_blk[i].vis = vis;
        }

   //--- cycles: ARMED label, models, levels -------------------------
   for(int ci = 0; ci < g_cyc_n; ci++)
     {
      IdentificationCycle cy = g_cyc[ci];
      double off = InpLabelStackOffsetPips * PipSize();

      if(InpShowArmedLabel && (cy.drawn_mask & (1 << 6)) == 0)
        {
         string txt = (cy.anchor_type == BT_M5_OB ? "M5 OB ARMED" : "M5 BREAKER ARMED");
         double p   = (cy.dir == DIR_BULL ? cy.anchor_lo - off : cy.anchor_hi + off);
         OM_Text(OM_Name(TT_ARM, cy.cycle_id, 0), cy.armed_time, p, txt, TS_ARMED,
                 cy.dir == DIR_BULL ? ANCHOR_UPPER : ANCHOR_LOWER);
         cy.drawn_mask |= (1 << 6);
        }

      for(int m = 0; m < MDL_COUNT; m++)
        {
         if(cy.result[m] != MR_CONFIRMED) continue;
         if((cy.drawn_mask & (1 << m)) != 0) continue;
         if(m == MDL_CISD && !InpShowCISD) continue;
         if(m == MDL_MSS  && !InpShowMSS)  continue;
         if(m == MDL_BPR  && !InpShowBPR)  continue;
         if(m >= MDL_PA_ENGULF && !InpShowPA) continue;

         int k = 0;                                   // vertical stacking (Rule 45)
         for(int q = 0; q < m; q++)
            if(cy.result[q] == MR_CONFIRMED && cy.cfm_time[q] == cy.cfm_time[m]) k++;

         double p = (cy.dir == DIR_BULL ? cy.cfm_price[m] - (k + 1) * off
                                        : cy.cfm_price[m] + (k + 1) * off);
         OM_Text(OM_Name(TT_MDL, cy.cycle_id, m), cy.cfm_time[m], p,
                 DirGlyph(cy.dir) + " " + ModelName(m),
                 ModelStyleOf(m, cy.dir),
                 cy.dir == DIR_BULL ? ANCHOR_UPPER : ANCHOR_LOWER);
         cy.drawn_mask |= (1 << m);
        }

      if(InpShowLevelLines && InpShowCISD && cy.result[MDL_CISD] == MR_CONFIRMED &&
         (cy.drawn_mask & (1 << 7)) == 0)
        {
         datetime t2 = cy.cfm_time[MDL_CISD] + (datetime)((long)InpLevelLineExtendBars * PeriodSeconds(PERIOD_M5));
         OM_Level(OM_Name(TT_LVL, cy.cycle_id, 0), cy.cisd_ref_time, t2, cy.cisd_level,
                  ZS_CISD_LINE);
         OM_Text(OM_Name(TT_LVL, cy.cycle_id, 1), t2, cy.cisd_level, "CISD Level",
                 TS_LEVEL, ANCHOR_LEFT);
         cy.drawn_mask |= (1 << 7);
        }
      if(InpShowLevelLines && InpShowMSS && cy.result[MDL_MSS] == MR_CONFIRMED &&
         (cy.drawn_mask & (1 << 8)) == 0)
        {
         datetime t2 = cy.cfm_time[MDL_MSS] + (datetime)((long)InpLevelLineExtendBars * PeriodSeconds(PERIOD_M5));
         OM_Level(OM_Name(TT_LVL, cy.cycle_id, 2), cy.mss_ref_time, t2, cy.mss_level,
                  ZS_MSS_LINE);
         OM_Text(OM_Name(TT_LVL, cy.cycle_id, 3), t2, cy.mss_level, "MSS Break Level",
                 TS_LEVEL, ANCHOR_LEFT);
         cy.drawn_mask |= (1 << 8);
        }
      g_cyc[ci] = cy;
     }

   //--- BPR zones ---------------------------------------------------
   if(InpShowBPR)
      for(int i = 0; i < g_bpr_n; i++)
        {
         int vis = (g_bpr[i].state == ZS_INVALID ? 2 : (g_bpr[i].state == ZS_TOUCHED ? 1 : 0));
         if(vis == 2 && g_bpr[i].vis == vis) continue;
         StyleZone pst = BPRStyleOf(g_bpr[i]);
         datetime t2 = (vis == 2 && g_bpr[i].invalid_time > 0 ? g_bpr[i].invalid_time : redge);
         OM_Rect(OM_Name(TT_BPR, g_bpr[i].id, 0), g_bpr[i].formation_time, g_bpr[i].hi,
                 t2, g_bpr[i].lo, pst);
         g_bpr[i].vis = vis;
        }
  }

//--- bar-0 preview: drawing only, never state (Spec 8.2 / 18.4) -----
void OM_Preview()
  {
   string nm = OM_Name(TT_PRV, 0, 0);
   ObjectDelete(0, nm);
   if(!g_sess.active) return;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid <= 0.0) return;
   for(int i = 0; i < g_blk_n; i++)
     {
      if(g_blk[i].state != BLOCK_ACTIVE || g_blk[i].dir != g_sess.dir) continue;
      if(bid > g_blk[i].hi || bid < g_blk[i].lo) continue;
      double off = InpLabelStackOffsetPips * PipSize();
      datetime t0 = iTime(_Symbol, PERIOD_M5, 0);
      OM_Text(nm, t0, (g_blk[i].dir == DIR_BULL ? g_blk[i].lo - off : g_blk[i].hi + off),
              "PENDING TOUCH", TS_PREVIEW,
              g_blk[i].dir == DIR_BULL ? ANCHOR_UPPER : ANCHOR_LOWER);
      return;
     }
  }

#endif // HMI_OM_MQH
