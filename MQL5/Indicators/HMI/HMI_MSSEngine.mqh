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

   // BRI-08 (v2.55): the FIRST close beyond the level by this bar's margin
   // confirms; where the previous close was is not looked at. A close between
   // the level and the threshold is not a break and consumes nothing.
   if(!B8Beyond(cy.dir, g_m5[n].close, cy.mss_level, MarginM5Pts(n))) return(false);
   B8LogBreak(cy, "MSS", n, cy.mss_level, cy.mss_ref_time);
   ModelConfirm(cy, MDL_MSS, n);
   return(true);
  }

#endif // HMI_MSS_MQH
