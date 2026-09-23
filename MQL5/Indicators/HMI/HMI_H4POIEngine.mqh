//+------------------------------------------------------------------+
//| HMI_H4POIEngine.mqh — POI = the FULL H4 order block (Rule 5)     |
//| The FVG only validates the OB; it never becomes the POI itself.  |
//+------------------------------------------------------------------+
#ifndef HMI_H4POI_MQH
#define HMI_H4POI_MQH
#include "HMI_H4RangeEngine.mqh"
#include "HMI_FVGEngine.mqh"

int POIFindById(const long id)
  {
   for(int i = 0; i < g_poi_n; i++) if(g_poi[i].id == id) return(i);
   return(-1);
  }

// The logical window stays exactly InpH4MaxPOIs wide, so which POIs are
// touchable is unchanged. What changes is that the record falling out of
// the window is DEMOTED to POI_EXPIRED instead of being deleted (Spec 4.6 /
// 14.7 / AX-4): a deleted record left its rectangle frozen in live style on
// the chart and left an active session holding a dangling poi_id.
void POIPush(const H4POI &p)
  {
   int cap = MathMin(MAX_POIS, MathMax(1, InpH4MaxPOIs));

   //--- 1) demote whatever leaves the logical window ---------------
   if(g_poi_n >= cap)
     {
      int drop = g_poi_n - cap;                 // oldest still inside the window
      if(SafeIdx(drop, g_poi_n))
        {
         if(g_poi[drop].state != POI_INVALID) g_poi[drop].state = POI_EXPIRED;
         g_poi[drop].out_of_window = true;      // drawing layer will drop its graphics
        }
     }

   //--- 2) physical store: only ever drop records that are already
   //---    out of the window, and never the one the session uses ---
   if(g_poi_n >= MAX_POIS)
     {
      int kill = 0;
      while(kill < g_poi_n - 1 &&
            (!g_poi[kill].out_of_window ||
             (g_sess.active && g_poi[kill].id == g_sess.poi_id)))
         kill++;
      if(!g_poi[kill].out_of_window) kill = 0;   // pathological: fall back to v1.00 behaviour
      for(int i = kill + 1; i < g_poi_n; i++) g_poi[i-1] = g_poi[i];
      g_poi_n--;
     }

   g_poi[g_poi_n] = p;
   g_poi_n++;
  }

// A-06 (opt-in): a session that ended on TIMEOUT may re-arm its POI, but
// only after price has fully left the zone on a closed bar - otherwise the
// session would restart on the very next bar, forever.
// InpPOIMaxSessions = 1 (default) never reaches this path.
void POIReArmCheck(const int n)
  {
   for(int i = 0; i < g_poi_n; i++)
     {
      if(!g_poi[i].awaiting_leave) continue;
      if(g_poi[i].state != POI_TOUCHED || g_poi[i].out_of_window)
        { g_poi[i].awaiting_leave = false; continue; }
      if(RangesIntersect(g_m5[n].low, g_m5[n].high, g_poi[i].lo, g_poi[i].hi)) continue;
      g_poi[i].awaiting_leave = false;
      g_poi[i].state          = POI_ACTIVE;
      g_poi[i].vis            = -1;
     }
  }

// Called for H4 bar h with the FVG (if any) that this bar completed.
void POIOnBar(const int h, const int fvg_idx)
  {
   if(fvg_idx < 0 || !SafeIdx(fvg_idx, g_h4fvg_n)) return;

   int dir = g_h4fvg[fvg_idx].dir;
   if(dir != CtxDirection()) return;            // trend-following only (Rule 2)

   int tol = PipsToPts(InpH4ConnectTolerancePips);
   int oldest = MathMax(0, h - InpH4OBtoFVGMaxBars);
   bool saw_candidate = false;

   string rejected = "";                       // filled only when nothing is created

   for(int o = h - 1; o >= oldest; o--)         // nearest to the FVG first (CONF-14)
     {
      if(CandleDir(g_h4[o]) != -dir) continue;  // OB is the opposite candle
      saw_candidate = true;
      int gap = ConnectionGapPts(dir, g_h4[o].high, g_h4[o].low,
                                 g_h4fvg[fvg_idx].hi, g_h4fvg[fvg_idx].lo);
      if(gap > tol)                             // real positive gap -> keep looking
        {
         if(InpLogSignals)
            rejected += StringFormat("|ob=%s,ob_hi=%s,ob_lo=%s,gap_pts=%d",
                                     TimeToString(g_h4[o].time, TIME_DATE|TIME_MINUTES),
                                     DoubleToString(g_h4[o].high, _Digits),
                                     DoubleToString(g_h4[o].low, _Digits), gap);
         continue;
        }

      for(int i = 0; i < g_poi_n; i++)          // de-duplicate
         if(g_poi[i].origin_time == g_h4[o].time && g_poi[i].dir == dir) return;

      H4POI p;
      p.id           = g_next_id++;
      p.dir          = dir;
      p.origin_time  = g_h4[o].time;
      p.confirm_time = g_h4fvg[fvg_idx].confirm_time;
      p.hi           = g_h4[o].high;            // FULL order block (Rule 5)
      p.lo           = g_h4[o].low;
      p.fvg_id       = g_h4fvg[fvg_idx].id;
      p.state          = POI_ACTIVE;
      p.touched_time   = 0;
      p.invalid_time   = 0;
      p.out_of_window  = false;
      p.session_count  = 0;
      p.awaiting_leave = false;
      p.vis            = -1;
      POIPush(p);
      return;
     }

   if(saw_candidate) g_diag_poi_rejected_gap++;  // BRI-04 / D-7 diagnostic

   // Reaching here means this FVG produced NO POI. Printing every rejected
   // candidate with its measured gap makes the refusal side of Rule 6
   // checkable against the data window, instead of just a counter.
   if(InpLogSignals && rejected != "")
      PrintFormat("HMI-REJECT,%s,H4POI,%s,fvg=%s,fvg_lo=%s,fvg_hi=%s%s",
                  _Symbol, (dir == DIR_BULL ? "BULL" : "BEAR"),
                  TimeToString(g_h4fvg[fvg_idx].bar_time, TIME_DATE|TIME_MINUTES),
                  DoubleToString(g_h4fvg[fvg_idx].lo, _Digits),
                  DoubleToString(g_h4fvg[fvg_idx].hi, _Digits), rejected);
  }

//--- invalidation on a closed H4 candle -----------------------------
void POIInvalidateOnBar(const int h)
  {
   datetime t  = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int      mp = MarginH4Pts(h);
   for(int i = 0; i < g_poi_n; i++)
     {
      if(g_poi[i].state != POI_ACTIVE && g_poi[i].state != POI_TOUCHED) continue;
      if(g_poi[i].confirm_time > g_h4[h].time) continue;
      bool dead = (g_poi[i].dir == DIR_BULL)
                  ? BreakDown(g_h4[h].close, g_poi[i].lo, mp)
                  : BreakUp  (g_h4[h].close, g_poi[i].hi, mp);
      if(dead)
        {
         g_poi[i].state        = POI_INVALID;
         g_poi[i].invalid_time = t;
        }
     }
   // age out
   for(int i = 0; i < g_poi_n; i++)
     {
      if(g_poi[i].state != POI_ACTIVE) continue;
      if((long)(t - g_poi[i].confirm_time) > (long)InpH4POIMaxAgeBars * PeriodSeconds(PERIOD_H4))
         g_poi[i].state = POI_EXPIRED;
     }
  }

//--- touch detection runs on CLOSED M5 bars (Spec 4.5) --------------
// A bar may only touch a POI that was already confirmed when it opened.
int POITouchedBy(const int n)
  {
   int best = -1;
   for(int i = 0; i < g_poi_n; i++)
     {
      if(g_poi[i].state != POI_ACTIVE) continue;
      if(g_poi[i].confirm_time > g_m5[n].time) continue;     // anti future-leak
      if(!RangesIntersect(g_m5[n].low, g_m5[n].high, g_poi[i].lo, g_poi[i].hi)) continue;
      if(best < 0 || g_poi[i].confirm_time > g_poi[best].confirm_time) best = i;
     }
   return(best);
  }

#endif // HMI_H4POI_MQH
