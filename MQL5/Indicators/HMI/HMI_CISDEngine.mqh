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

   // BRI-08 (v2.55): the FIRST close beyond the level by this bar's margin
   // confirms; where the previous close was is not looked at. A close between
   // the level and the threshold is not a break and consumes nothing.
   if(!B8Beyond(cy.dir, g_m5[n].close, cy.cisd_level, MarginM5Pts(n))) return(false);
   B8LogBreak(cy, "CISD", n, cy.cisd_level, cy.cisd_ref_time);
   ModelConfirm(cy, MDL_CISD, n);
   return(true);
  }

#endif // HMI_CISD_MQH
