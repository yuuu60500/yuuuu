//+------------------------------------------------------------------+
//| HMI_Util.mqh — integer-point math, pip size, time helpers        |
//+------------------------------------------------------------------+
#ifndef HMI_UTIL_MQH
#define HMI_UTIL_MQH
#include "HMI_Params.mqh"

//--- pip size (Appendix B.1) ---------------------------------------
double PipSize()
  {
   return((_Digits == 3 || _Digits == 5) ? 10.0 * _Point : _Point);
  }

//--- all price comparisons go through integer points (Appendix B.2)-
int Pts(const double a, const double b)
  {
   return((int)MathRound((a - b) / _Point));
  }

int PipsToPts(const double pips)
  {
   return((int)MathRound(pips * PipSize() / _Point));
  }

//--- array bound guard (Rule 66 P0) --------------------------------
bool SafeIdx(const int i, const int n)
  {
   return(i >= 0 && i < n);
  }

//--- time helpers ---------------------------------------------------
datetime CloseTimeOf(const datetime open_time, const ENUM_TIMEFRAMES tf)
  {
   return(open_time + PeriodSeconds(tf));
  }

// An H4 bar may only be consumed by an M5 bar that opened at or after
// the H4 bar had already closed (Spec 15.2 — kills the same-second leak).
bool H4VisibleTo(const datetime h4_open, const datetime m5_open)
  {
   return(h4_open + PeriodSeconds(PERIOD_H4) <= m5_open);
  }

//--- candle direction ----------------------------------------------
int CandleDir(const MqlRates &r)
  {
   if(r.close > r.open) return(DIR_BULL);
   if(r.close < r.open) return(DIR_BEAR);
   return(DIR_NONE);                        // doji: neutral (Spec 10.1)
  }

double Body(const MqlRates &r) { return(MathAbs(r.close - r.open)); }

//--- zone intersection ---------------------------------------------
bool RangesIntersect(const double a_lo, const double a_hi,
                     const double b_lo, const double b_hi)
  {
   return(a_lo <= b_hi && a_hi >= b_lo);
  }

//--- model names (Rule 24 / 28 / 37 / 61: never abbreviate) --------
string ModelName(const int m)
  {
   switch(m)
     {
      case MDL_CISD:            return("CISD");
      case MDL_MSS:             return("MSS");
      case MDL_BPR:             return("BPR");
      case MDL_PA_ENGULF:       return("PA ENGULFING");
      case MDL_PA_REJECT:       return("PA REJECTION");
      case MDL_PA_BREAKRETEST:  return("PA BREAK-RETEST");
     }
   return("?");
  }

string DirGlyph(const int dir) { return(dir == DIR_BULL ? SYM_UP : SYM_DOWN); }

string CtxName(const CtxState c)
  {
   switch(c)
     {
      case CTX_BULLISH:    return("BULLISH");
      case CTX_BEARISH:    return("BEARISH");
      case CTX_TRANSITION: return("TRANSITION");
     }
   return("RANGE");
  }

bool AlertEnabledFor(const int m)
  {
   switch(m)
     {
      case MDL_CISD: return(InpAlertOnCISD);
      case MDL_MSS:  return(InpAlertOnMSS);
      case MDL_BPR:  return(InpAlertOnBPR);
     }
   return(InpAlertOnPA);
  }

//--- alert queue (flushed in Phase 7 only) -------------------------
void AlertPush(const string text)
  {
   if(g_alertq_n >= MAX_ALERTQ) return;
   g_alertq[g_alertq_n] = text;
   g_alertq_n++;
  }

#endif // HMI_UTIL_MQH
