//+------------------------------------------------------------------+
//| HMI_H4StructureEngine.mqh — BOS / CHOCH on closed H4 candles     |
//| Close confirmation + margin only. Wick breaks never count.       |
//+------------------------------------------------------------------+
#ifndef HMI_H4STRUCT_MQH
#define HMI_H4STRUCT_MQH
#include "HMI_SwingEngine.mqh"

// Returns the raw break direction of H4 bar h (DIR_NONE when none) and
// the index of the swing it consumed. The caller classifies it as BOS or
// CHOCH from the current context (Spec 2.2).
int H4DetectBreak(const int h, int &broken_idx)
  {
   broken_idx = -1;
   if(!SafeIdx(h, g_h4_n)) return(DIR_NONE);

   datetime vis = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int mp = MarginH4Pts(h);

   int ih = SwingLastUnswept(g_h4sw, g_h4sw_n, DIR_BULL, vis);
   if(ih >= 0 && BreakUp(g_h4[h].close, g_h4sw[ih].price, mp))
     { broken_idx = ih; return(DIR_BULL); }

   int il = SwingLastUnswept(g_h4sw, g_h4sw_n, DIR_BEAR, vis);
   if(il >= 0 && BreakDown(g_h4[h].close, g_h4sw[il].price, mp))
     { broken_idx = il; return(DIR_BEAR); }

   return(DIR_NONE);
  }

// A swing may only be consumed once (Spec 3.2).
void H4ConsumeSwing(const int idx, const datetime t)
  {
   if(!SafeIdx(idx, g_h4sw_n)) return;
   g_h4sw[idx].swept      = true;
   g_h4sw[idx].swept_time = t;
  }

#endif // HMI_H4STRUCT_MQH
