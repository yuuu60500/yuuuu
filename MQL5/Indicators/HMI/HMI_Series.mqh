//+------------------------------------------------------------------+
//| HMI_Series.mqh — explicit M5 / H4 series (chart timeframe free)  |
//| Only CLOSED bars are ever stored. Index 0 = oldest, append-only, |
//| so runtime bar indices stay stable for the whole session.        |
//+------------------------------------------------------------------+
#ifndef HMI_SERIES_MQH
#define HMI_SERIES_MQH
#include "HMI_Util.mqh"

MqlRates g_m5[];  int g_m5_n = 0;   double g_m5_atr[];
MqlRates g_h4[];  int g_h4_n = 0;   double g_h4_atr[];

//--- Wilder-free simple ATR(14) over closed bars, computed forward  |
//--- (uses bars <= i only, so it can never leak the future)         |
void SeriesComputeATR(const MqlRates &r[], const int n, double &atr[], const int from)
  {
   ArrayResize(atr, n);
   for(int i = MathMax(from, 0); i < n; i++)
     {
      if(i < 14) { atr[i] = 0.0; continue; }
      double sum = 0.0;
      for(int k = i - 13; k <= i; k++)
        {
         double pc = r[k-1].close;
         double tr = MathMax(r[k].high - r[k].low,
                     MathMax(MathAbs(r[k].high - pc), MathAbs(r[k].low - pc)));
         sum += tr;
        }
      atr[i] = sum / 14.0;
     }
  }

//--- full (re)load --------------------------------------------------
bool SeriesLoad(const ENUM_TIMEFRAMES tf, MqlRates &r[], int &cnt, double &atr[], const int want)
  {
   MqlRates tmp[];
   int got = CopyRates(_Symbol, tf, 1, want, tmp);   // start at shift 1 = last CLOSED bar
   if(got <= 0) { cnt = 0; return(false); }
   ArrayResize(r, got);
   for(int i = 0; i < got; i++) r[i] = tmp[i];
   cnt = got;
   SeriesComputeATR(r, cnt, atr, 0);
   return(true);
  }

//--- append bars that closed since the last stored one --------------
//--- returns number appended, or -1 when a full reload is required   |
// Return codes. "Not ready" used to be indistinguishable from "nothing new",
// which is what let a lagging H4 feed leave M5 advancing on a stale context
// with no catch-up (A-30). Callers must treat them differently.
#define SA_RELOAD     (-1)   // history changed underneath us: rebuild
#define SA_NOT_READY  (-2)   // the terminal has not delivered the bars yet
#define SA_NONE         0    // genuinely nothing new has closed

int SeriesAppend(const ENUM_TIMEFRAMES tf, MqlRates &r[], int &cnt, double &atr[])
  {
   if(cnt <= 0) return(SA_RELOAD);
   datetime last = r[cnt-1].time;

   int sh = iBarShift(_Symbol, tf, last, true);
   if(sh < 0)  return(SA_RELOAD);   // bar vanished (history refresh) -> reload

   // A-32: a broker may revise a bar in place without removing any bar, so
   // iBarShift still finds it and nothing below would notice. Re-read that
   // same bar and compare: if the terminal now reports values other than the
   // ones this build was made from, the build is stale.
   // Copied BY POSITION on purpose - the start_time overload's direction is
   // easy to misread, and a check that silently reads the wrong bar is worse
   // than no check.
   // Exact comparison is correct here: any revision at all invalidates the
   // build, so this is change detection, not a price-level test.
   MqlRates chk[];
   if(CopyRates(_Symbol, tf, sh, 1, chk) == 1)
     {
      if(chk[0].time  != r[cnt-1].time  ||
         chk[0].open  != r[cnt-1].open  || chk[0].high  != r[cnt-1].high ||
         chk[0].low   != r[cnt-1].low   || chk[0].close != r[cnt-1].close)
         return(SA_RELOAD);
     }
   if(sh <= 1) return(SA_NONE);     // nothing new closed
   int want = sh - 1;
   MqlRates tmp[];
   int got = CopyRates(_Symbol, tf, 1, want, tmp);
   // A partial batch is a sync hiccup, not a short history: iBarShift just
   // found bar `sh`, so bars 1..sh-1 all exist. Appending half of them would
   // leave the engine mid-update, so take nothing and retry next tick.
   if(got < want) return(SA_NOT_READY);
   int old = cnt;
   ArrayResize(r, old + got);
   for(int i = 0; i < got; i++) r[old + i] = tmp[i];
   cnt = old + got;
   SeriesComputeATR(r, cnt, atr, old);
   return(got);
  }

bool SeriesInit()
  {
   bool a = SeriesLoad(PERIOD_M5, g_m5, g_m5_n, g_m5_atr, InpMaxHistoryBarsM5);
   bool b = SeriesLoad(PERIOD_H4, g_h4, g_h4_n, g_h4_atr, InpMaxHistoryBarsH4);
   return(a && b && g_m5_n > 50 && g_h4_n > 10);
  }

//====================== break margin (D-6) ==========================
int MarginPtsFrom(const double atr_value)
  {
   switch(InpBreakMarginMode)
     {
      case MARGIN_POINTS:
         return(InpBreakMarginPoints);
      case MARGIN_ATR_FRAC:
        {
         if(atr_value <= 0.0) return(PipsToPts(InpBreakMarginPips));   // warmup fallback
         return((int)MathRound(InpBreakMarginATRFrac * atr_value / _Point));
        }
     }
   return(PipsToPts(InpBreakMarginPips));                              // MARGIN_PIPS
  }

int MarginM5Pts(const int n)
  {
   double a = (SafeIdx(n, g_m5_n) ? g_m5_atr[n] : 0.0);
   return(MarginPtsFrom(a));
  }

int MarginH4Pts(const int h)
  {
   double a = (SafeIdx(h, g_h4_n) ? g_h4_atr[h] : 0.0);
   return(MarginPtsFrom(a));
  }

//--- helpers used everywhere: strict break with margin --------------
bool BreakUp  (const double price, const double level, const int mpts) { return(Pts(price, level) >  mpts); }
bool BreakDown(const double price, const double level, const int mpts) { return(Pts(price, level) < -mpts); }

#endif // HMI_SERIES_MQH
