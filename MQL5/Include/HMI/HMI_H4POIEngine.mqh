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

void POIPush(const H4POI &p)
  {
   int cap = MathMin(MAX_POIS, MathMax(1, InpH4MaxPOIs));
   if(g_poi_n >= cap)
     {
      for(int i = 1; i < g_poi_n; i++) g_poi[i-1] = g_poi[i];
      g_poi_n--;
     }
   g_poi[g_poi_n] = p;
   g_poi_n++;
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

   for(int o = h - 1; o >= oldest; o--)         // nearest to the FVG first (CONF-14)
     {
      if(CandleDir(g_h4[o]) != -dir) continue;  // OB is the opposite candle
      saw_candidate = true;
      if(!ConnectionValid(dir, g_h4[o].high, g_h4[o].low,
                          g_h4fvg[fvg_idx].hi, g_h4fvg[fvg_idx].lo, tol))
         continue;                              // real positive gap -> keep looking

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
      p.state        = POI_ACTIVE;
      p.touched_time = 0;
      p.invalid_time = 0;
      p.vis          = -1;
      POIPush(p);
      return;
     }

   if(saw_candidate) g_diag_poi_rejected_gap++;  // BRI-04 / D-7 diagnostic
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
