//+------------------------------------------------------------------+
//| HMI_BPREngine.mqh — first real overlap of two opposite FVGs      |
//| First valid BPR per cycle only; an invalidated one is never      |
//| replaced (Rule 33 / CONF-10).                                     |
//+------------------------------------------------------------------+
#ifndef HMI_BPR_MQH
#define HMI_BPR_MQH
#include "HMI_CycleManager.mqh"

int BPRPush(const BPRZone &z)
  {
   if(g_bpr_n >= MAX_BPR)
     {
      for(int i = 1; i < MAX_BPR; i++) g_bpr[i-1] = g_bpr[i];
      g_bpr_n = MAX_BPR - 1;
     }
   g_bpr[g_bpr_n] = z;
   g_bpr_n++;
   return(g_bpr_n - 1);
  }

bool BPR_Check(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_BPR] != MR_PENDING) return(false);

   //--- the later leg must be an FVG completed by THIS bar ----------
   int late = -1;
   for(int i = g_m5fvg_n - 1; i >= 0; i--)
     {
      if(g_m5fvg[i].bar_index == n) { late = i; break; }
      if(g_m5fvg[i].bar_index <  n) break;
     }
   if(late < 0) return(false);
   if(g_m5fvg[late].confirm_time <= cy.armed_time) return(false);   // Rule 32

   int W  = MathMax(5, InpSetupWindowBars);
   int lo = MathMax(0, cy.armed_index - W + 1);

   int    best = -1;
   double b_lo = 0.0, b_hi = 0.0;

   for(int i = g_m5fvg_n - 1; i >= 0; i--)
     {
      if(i == late) continue;
      if(g_m5fvg[i].bar_index < lo) break;                          // bounded window
      if(g_m5fvg[i].dir == g_m5fvg[late].dir) continue;             // must be opposite
      if(InpBPRRequireBothLegsAfterArmed &&
         g_m5fvg[i].confirm_time <= cy.armed_time) continue;        // strict reading
      if(InpBPREarlyLegFromSessionStart &&
         g_m5fvg[i].confirm_time < cy.session_start_time) continue; // D-2

      double ov_lo = MathMax(g_m5fvg[i].lo, g_m5fvg[late].lo);
      double ov_hi = MathMin(g_m5fvg[i].hi, g_m5fvg[late].hi);
      if(Pts(ov_hi, ov_lo) <= 0) continue;                          // real overlap only

      if(best < 0)
        { best = i; b_lo = ov_lo; b_hi = ov_hi; continue; }

      // iteration is newest-first, so only exact ties need arbitration
      if(g_m5fvg[i].confirm_time == g_m5fvg[best].confirm_time)
        {
         int d = Pts(ov_hi - ov_lo, b_hi - b_lo);
         bool take = (d > 0) || (d == 0 && Pts(ov_lo, b_lo) < 0) ||
                     (d == 0 && Pts(ov_lo, b_lo) == 0 && g_m5fvg[i].id > g_m5fvg[best].id);
         if(take) { best = i; b_lo = ov_lo; b_hi = ov_hi; }
        }
     }
   if(best < 0) return(false);

   BPRZone z;
   z.id              = g_next_id++;
   z.cycle_id        = cy.cycle_id;
   z.dir             = cy.dir;                       // direction follows the cycle
   z.hi              = b_hi;
   z.lo              = b_lo;
   z.formation_time  = g_m5fvg[late].confirm_time;
   z.leg_bull_fvg_id = (g_m5fvg[late].dir == DIR_BULL ? g_m5fvg[late].id : g_m5fvg[best].id);
   z.leg_bear_fvg_id = (g_m5fvg[late].dir == DIR_BEAR ? g_m5fvg[late].id : g_m5fvg[best].id);
   z.state           = ZS_ACTIVE;
   z.touched_time    = 0;
   z.invalid_time    = 0;
   z.vis             = -1;
   BPRPush(z);

   cy.bpr_id = z.id;
   ModelConfirm(cy, MDL_BPR, n);
   return(true);
  }

//--- lifecycle on every closed bar (Rule 36) ------------------------
void BPRLifecycle(const int n)
  {
   datetime t  = CloseTimeOf(g_m5[n].time, PERIOD_M5);
   int      mp = MarginM5Pts(n);
   for(int i = 0; i < g_bpr_n; i++)
     {
      if(g_bpr[i].state != ZS_ACTIVE && g_bpr[i].state != ZS_TOUCHED) continue;
      if(g_bpr[i].formation_time > g_m5[n].time) continue;

      bool dead = (g_bpr[i].dir == DIR_BULL)
                  ? BreakDown(g_m5[n].close, g_bpr[i].lo, mp)
                  : BreakUp  (g_m5[n].close, g_bpr[i].hi, mp);
      if(dead)
        {
         g_bpr[i].state        = ZS_INVALID;
         g_bpr[i].invalid_time = t;
         g_bpr[i].vis          = -1;
         continue;
        }
      if(g_bpr[i].state == ZS_ACTIVE &&
         RangesIntersect(g_m5[n].low, g_m5[n].high, g_bpr[i].lo, g_bpr[i].hi))
        {
         g_bpr[i].state        = ZS_TOUCHED;
         g_bpr[i].touched_time = t;
         g_bpr[i].vis          = -1;
        }
     }
  }

#endif // HMI_BPR_MQH
