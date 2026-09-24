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
   g_ctx_messy   = false;   // BRI-06: quality is per context leg, like strength.
                            // The failed-transition branch sets it AFTER calling
                            // this, so the new leg is born carrying the mark.
  }

// Diagnostic only - never read by an engine, and emitted under a prefix of
// its own so the reload/repaint parser, which splits on HMI-BUILD, does not
// pick these up as mark rows. It makes the Context chain auditable the way
// HMI-REJECT made Rule 6's refusal side auditable: every state change comes
// out with the swing it broke and the state it left behind, so `str N` on the
// panel can be counted back from the log instead of taken on trust.
void CtxLog(const string kind, const string dir, const int h, const int broken)
  {
   if(!InpLogSignals) return;
   string sw_t = "", sw_p = "";
   if(SafeIdx(broken, g_h4sw_n))
     {
      sw_t = TimeToString(g_h4sw[broken].bar_time, TIME_DATE|TIME_MINUTES);
      sw_p = DoubleToString(g_h4sw[broken].price, _Digits);
     }
   PrintFormat("HMI-CTX,%s,%s,dir=%s,live=%d,ctx=%s,str=%d,messy=%d,bar=%s,swing=%s,swing_px=%s,close=%s",
               _Symbol, kind, dir, (g_live ? 1 : 0),
               CtxName(g_ctx), g_ctx_strength, (g_ctx_messy ? 1 : 0),
               TimeToString(CloseTimeOf(g_h4[h].time, PERIOD_H4), TIME_DATE|TIME_MINUTES),
               sw_t, sw_p, DoubleToString(g_h4[h].close, _Digits));
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
      CtxLog("TIMEOUT", "-", h, -1);
      return(EV_TIMEOUT);
     }

   int broken = -1;
   int brk = H4DetectBreak(h, broken);
   if(brk == DIR_NONE) return(EV_NONE);

   datetime brk_confirm = (SafeIdx(broken, g_h4sw_n) ? g_h4sw[broken].confirm_time : 0);
   H4ConsumeSwing(broken, t);

   CtxEventType ev   = EV_NONE;
   string       kind = "";                       // diagnostic label only
   string       vdir = (brk == DIR_BULL ? "UP" : "DOWN");

   switch(g_ctx)
     {
      case CTX_RANGE:
         // no prevailing direction: the first break is a BOS
         if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
         else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
         g_ctx_strength = 1;
         kind = "BOS";
         break;

      case CTX_BULLISH:
         if(brk == DIR_BULL) { ev = EV_BOS_UP; g_ctx_strength++; kind = "BOS"; }
         else
           {
            ev = EV_CHOCH_DOWN;                       // Rule 3: no direct flip
            CtxEnter(CTX_TRANSITION, DIR_BEAR, t);
            g_ctx_strength = 0;
            kind = "CHOCH";
           }
         break;

      case CTX_BEARISH:
         if(brk == DIR_BEAR) { ev = EV_BOS_DOWN; g_ctx_strength++; kind = "BOS"; }
         else
           {
            ev = EV_CHOCH_UP;
            CtxEnter(CTX_TRANSITION, DIR_BULL, t);
            g_ctx_strength = 0;
            kind = "CHOCH";
           }
         break;

      case CTX_TRANSITION:
        {
         // Confirmation must break a swing that was confirmed AFTER the
         // CHOCH, otherwise one single move would flip the trend (Rule 3).
         bool fresh = (brk_confirm > g_ctx_time);
         if(brk == g_ctx_pending)
           {
            // Rule 3 freshness: a break of a swing confirmed before the CHOCH
            // is the same leg, so it resolves nothing. Logged because "why did
            // nothing happen here" is the hardest thing to reconstruct later.
            if(!fresh) { ev = EV_NONE; kind = "TRANS_SAMELEG"; break; }
            if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
            else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
            g_ctx_strength = 1;
            kind = "TRANS_OK";
           }
         else
           {
            // Transition failed: the original trend resumes. THIS is the
            // "failed TRANSITION" the spec means by MESSY (docs/01 202-204) -
            // not the CHOCH that opened the transition, because a CHOCH whose
            // transition then succeeds is an ordinary reversal (A-25).
            if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
            else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
            g_ctx_strength = 1;
            g_ctx_messy    = true;
            kind = "TRANS_FAIL";
           }
         break;
        }
     }

   if(kind != "") CtxLog(kind, vdir, h, broken);
   return(ev);
  }

#endif // HMI_H4CTX_MQH
