//+------------------------------------------------------------------+
//| HMI_H4ContextEngine.mqh — 4-state context machine (Rule 3)       |
//| CHOCH never flips the trend by itself: it only opens TRANSITION. |
//+------------------------------------------------------------------+
#ifndef HMI_H4CTX_MQH
#define HMI_H4CTX_MQH
#include "HMI_H4StructureEngine.mqh"

int CtxDirection()
  {
   if(g_ctx == CTX_BULLISH) return(DIR_BULL);
   if(g_ctx == CTX_BEARISH) return(DIR_BEAR);
   return(DIR_NONE);                   // RANGE / TRANSITION: no new setups
  }

void CtxEnter(const CtxState st, const int pending, const datetime t)
  {
   g_ctx         = st;
   g_ctx_pending = pending;
   g_ctx_time    = t;
   g_ctx_bars    = 0;
  }

// Classify the raw break for bar h and drive the state machine.
// Returns the classified event (for the trading-range engine).
CtxEventType H4ContextOnBar(const int h)
  {
   g_ctx_bars++;

   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);

   //--- timeout: a transition that never resolves becomes a range ---
   if(g_ctx == CTX_TRANSITION && g_ctx_bars > InpH4TransitionMaxBars)
     {
      CtxEnter(CTX_RANGE, DIR_NONE, t);
      return(EV_TIMEOUT);
     }

   int broken = -1;
   int brk = H4DetectBreak(h, broken);
   if(brk == DIR_NONE) return(EV_NONE);

   datetime brk_confirm = (SafeIdx(broken, g_h4sw_n) ? g_h4sw[broken].confirm_time : 0);
   H4ConsumeSwing(broken, t);

   CtxEventType ev = EV_NONE;

   switch(g_ctx)
     {
      case CTX_RANGE:
         // no prevailing direction: the first break is a BOS
         if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
         else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
         g_ctx_strength = 1;
         break;

      case CTX_BULLISH:
         if(brk == DIR_BULL) { ev = EV_BOS_UP; g_ctx_strength++; }
         else
           {
            ev = EV_CHOCH_DOWN;                       // Rule 3: no direct flip
            g_ctx_messy = true;
            CtxEnter(CTX_TRANSITION, DIR_BEAR, t);
            g_ctx_strength = 0;
           }
         break;

      case CTX_BEARISH:
         if(brk == DIR_BEAR) { ev = EV_BOS_DOWN; g_ctx_strength++; }
         else
           {
            ev = EV_CHOCH_UP;
            g_ctx_messy = true;
            CtxEnter(CTX_TRANSITION, DIR_BULL, t);
            g_ctx_strength = 0;
           }
         break;

      case CTX_TRANSITION:
        {
         // Confirmation must break a swing that was confirmed AFTER the
         // CHOCH, otherwise one single move would flip the trend (Rule 3).
         bool fresh = (brk_confirm > g_ctx_time);
         if(brk == g_ctx_pending)
           {
            if(!fresh) { ev = EV_NONE; break; }       // same leg, not a new event
            if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
            else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
            g_ctx_strength = 1;
           }
         else
           {
            // transition failed: the original trend resumes
            if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
            else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
            g_ctx_strength = 1;
           }
         break;
        }
     }
   return(ev);
  }

#endif // HMI_H4CTX_MQH
