//+------------------------------------------------------------------+
//| HMI_PriceActionEngine.mqh — PA is a peer of CISD/MSS/BPR         |
//| (Rule 38), never a filter on them (Rule 42 / 44).                |
//+------------------------------------------------------------------+
#ifndef HMI_PA_MQH
#define HMI_PA_MQH
#include "HMI_CycleManager.mqh"

bool PAInteracts(const IdentificationCycle &cy, const int n)
  {
   return(RangesIntersect(g_m5[n].low, g_m5[n].high, cy.anchor_lo, cy.anchor_hi));
  }

//--- PA ENGULFING (Rule 39) -----------------------------------------
bool PA_Engulf(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_PA_ENGULF] != MR_PENDING) return(false);
   if(n < 1 || !SafeIdx(n, g_m5_n)) return(false);
   if(CandleDir(g_m5[n])   !=  cy.dir) return(false);
   if(CandleDir(g_m5[n-1]) != -cy.dir) return(false);

   if(cy.dir == DIR_BULL)
     {
      if(Pts(g_m5[n].open,  g_m5[n-1].close) > 0) return(false);
      if(Pts(g_m5[n].close, g_m5[n-1].open)  < 0) return(false);
     }
   else
     {
      if(Pts(g_m5[n].open,  g_m5[n-1].close) < 0) return(false);
      if(Pts(g_m5[n].close, g_m5[n-1].open)  > 0) return(false);
     }

   double b0 = Body(g_m5[n]), b1 = Body(g_m5[n-1]);
   if(b1 > 0.0 && b0 < InpPAEngulfMinBodyRatio * b1) return(false);
   if(!PAInteracts(cy, n)) return(false);

   ModelConfirm(cy, MDL_PA_ENGULF, n);
   return(true);
  }

//--- PA REJECTION (Rule 40) -----------------------------------------
bool PA_Reject(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_PA_REJECT] != MR_PENDING) return(false);
   if(!SafeIdx(n, g_m5_n)) return(false);

   double rng = g_m5[n].high - g_m5[n].low;
   if(Pts(g_m5[n].high, g_m5[n].low) <= 0) return(false);

   double body  = Body(g_m5[n]);
   double upper = g_m5[n].high - MathMax(g_m5[n].open, g_m5[n].close);
   double lower = MathMin(g_m5[n].open, g_m5[n].close) - g_m5[n].low;
   double wick  = (cy.dir == DIR_BULL ? lower : upper);
   double other = (cy.dir == DIR_BULL ? upper : lower);

   if(body > 0.0 && wick < InpPARejWickToBody * body) return(false);
   if(wick < InpPARejWickToRange * rng) return(false);
   if(wick <= other) return(false);
   if(!PAInteracts(cy, n)) return(false);

   // the wick must be rejected: the close has to hold on the right side
   if(cy.dir == DIR_BULL && Pts(g_m5[n].close, cy.anchor_lo) <= 0) return(false);
   if(cy.dir == DIR_BEAR && Pts(g_m5[n].close, cy.anchor_hi) >= 0) return(false);

   ModelConfirm(cy, MDL_PA_REJECT, n);
   return(true);
  }

//--- PA BREAK-RETEST (Rule 41) --------------------------------------
bool PA_CheckBreakRetest(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_PA_BREAKRETEST] != MR_PENDING) return(false);
   if(n < 1 || !SafeIdx(n, g_m5_n)) return(false);

   int mp  = MarginM5Pts(n);
   int tol = PipsToPts(InpPARetestTolerancePips);

   //--- 1) an armed break is waiting for its retest+hold ------------
   if(cy.br_active)
     {
      if(n - cy.br_break_index > InpPABreakRetestMaxBars)
         cy.br_active = false;                        // break expires, R unfreezes
      else
        {
         bool hold;
         if(cy.dir == DIR_BULL)
            hold = (Pts(g_m5[n].low,  cy.br_ref) <=  tol) && BreakUp  (g_m5[n].close, cy.br_ref, mp);
         else
            hold = (Pts(g_m5[n].high, cy.br_ref) >= -tol) && BreakDown(g_m5[n].close, cy.br_ref, mp);
         if(hold)
           {
            cy.br_active = false;
            ModelConfirm(cy, MDL_PA_BREAKRETEST, n);
            return(true);
           }
         return(false);
        }
     }

   //--- 2) refresh the local reference (post-ARMED structure only) --
   datetime t = CloseTimeOf(g_m5[n].time, PERIOD_M5);
   for(int i = g_m5sw_n - 1; i >= 0; i--)
     {
      if(g_m5sw[i].confirm_time != t) break;
      if(g_m5sw[i].dir != cy.dir) continue;
      if(g_m5sw[i].bar_index < cy.armed_index) continue;   // Rule 41: after ARMED
      cy.br_ref      = g_m5sw[i].price;
      cy.br_ref_time = g_m5sw[i].bar_time;
      break;
     }
   if(cy.br_ref_time == 0) return(false);

   //--- 3) break freezes the reference ------------------------------
   bool brk = (cy.dir == DIR_BULL) ? BreakUp  (g_m5[n].close, cy.br_ref, mp)
                                   : BreakDown(g_m5[n].close, cy.br_ref, mp);
   if(brk)
     {
      cy.br_active      = true;
      cy.br_break_index = n;
     }
   return(false);
  }

//--- Phase 4 entry points (n > A) -----------------------------------
bool PA_CheckEngulfing(IdentificationCycle &cy, const int n) { return(PA_Engulf(cy, n)); }
bool PA_CheckRejection(IdentificationCycle &cy, const int n) { return(PA_Reject(cy, n)); }

//--- Phase 5b entry points (n == A, D-4) ----------------------------
// Legal because the confirmation event IS bar A's own close and the touch
// is a subset of that same closed-bar data (Spec 9.5.1).
bool PA_CheckEngulfingArmedBar(IdentificationCycle &cy, const int n)
  {
   if(!InpPAAllowArmedBarConfirm) return(false);
   if(n != cy.armed_index) return(false);
   return(PA_Engulf(cy, n));
  }

bool PA_CheckRejectionArmedBar(IdentificationCycle &cy, const int n)
  {
   if(!InpPAAllowArmedBarConfirm) return(false);
   if(n != cy.armed_index) return(false);
   return(PA_Reject(cy, n));
  }

#endif // HMI_PA_MQH
