//+------------------------------------------------------------------+
//| HMI_MSSEngine.mqh — close-confirmed break of a FROZEN M5 swing   |
//| Does not know that CISD/BPR/PA exist (Rule 30 / 44).             |
//+------------------------------------------------------------------+
#ifndef HMI_MSS_MQH
#define HMI_MSS_MQH
#include "HMI_CycleManager.mqh"

bool MSS_Check(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_MSS] != MR_PENDING) return(false);
   if(cy.mss_ref_time == 0) return(false);
   if(n < 1 || !SafeIdx(n, g_m5_n)) return(false);

   int    mp   = MarginM5Pts(n);
   double prev = g_m5[n-1].close;
   double cur  = g_m5[n].close;

   bool ok;
   if(cy.dir == DIR_BULL)
      ok = (Pts(prev, cy.mss_level) <= 0) && BreakUp(cur, cy.mss_level, mp);
   else
      ok = (Pts(prev, cy.mss_level) >= 0) && BreakDown(cur, cy.mss_level, mp);

   if(!ok) return(false);
   ModelConfirm(cy, MDL_MSS, n);
   return(true);
  }

#endif // HMI_MSS_MQH
