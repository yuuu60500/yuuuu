//+------------------------------------------------------------------+
//| HMI_CISDEngine.mqh — close-confirmed break of a FROZEN level     |
//| Does not know that MSS/BPR/PA exist (Rule 30 / 44).              |
//+------------------------------------------------------------------+
#ifndef HMI_CISD_MQH
#define HMI_CISD_MQH
#include "HMI_CycleManager.mqh"

bool CISD_Check(IdentificationCycle &cy, const int n)
  {
   if(cy.result[MDL_CISD] != MR_PENDING) return(false);   // Rule 43: max 1
   if(cy.cisd_ref_time == 0) return(false);               // no reference -> N/A
   if(n < 1 || !SafeIdx(n, g_m5_n)) return(false);

   int    mp   = MarginM5Pts(n);
   double prev = g_m5[n-1].close;
   double cur  = g_m5[n].close;

   bool ok;
   if(cy.dir == DIR_BULL)
      ok = (Pts(prev, cy.cisd_level) <= 0) && BreakUp(cur, cy.cisd_level, mp);
   else
      ok = (Pts(prev, cy.cisd_level) >= 0) && BreakDown(cur, cy.cisd_level, mp);

   if(!ok) return(false);
   ModelConfirm(cy, MDL_CISD, n);
   return(true);
  }

#endif // HMI_CISD_MQH
