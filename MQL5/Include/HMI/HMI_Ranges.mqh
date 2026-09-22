//+------------------------------------------------------------------+
//| HMI_Ranges.mqh — ATR and ADR panel metrics                       |
//|                                                                  |
//| PANEL ONLY. Nothing here is read by Phase 0-7, so neither ATR    |
//| nor ADR can filter, gate or move a mark (Rule 46 / 69).          |
//|                                                                  |
//| ATR comes from the engine's own forward-computed series          |
//| (g_h4_atr / g_m5_atr), so the panel shows exactly the value the  |
//| MARGIN_ATR_FRAC mode would use - no second, divergent ATR.       |
//|                                                                  |
//| ADR uses the broker's own D1 bars, and averages CLOSED days      |
//| only: folding today's partial range in would understate it.      |
//+------------------------------------------------------------------+
#ifndef HMI_RANGES_MQH
#define HMI_RANGES_MQH
#include "HMI_Series.mqh"

input group "=== Panel: ATR / ADR ==="
input bool InpShowATR    = false;  // ambient info; off by default to keep the panel short
input bool InpShowADR    = true;
input int  InpADRDays    = 20;    // closed days averaged for ADR

double   g_adr          = 0.0;    // average daily range, price units
int      g_adr_samples  = 0;
double   g_today_range  = 0.0;
double   g_today_hi     = 0.0;
double   g_today_lo     = 0.0;
bool     g_adr_ok       = false;

//--- refreshed once per new closed bar from the drawing layer -------
void RangesUpdate()
  {
   g_adr_ok = false;
   int want = MathMax(2, InpADRDays) + 1;        // +1 = today's unclosed bar
   MqlRates d[];
   int got = CopyRates(_Symbol, PERIOD_D1, 0, want, d);
   if(got < 2) return;                           // history not ready: panel shows n/a

   int today = got - 1;                          // last element = current day
   double sum = 0.0;
   int    cnt = 0;
   for(int i = today - 1; i >= 0 && cnt < InpADRDays; i--)
     {
      double r = d[i].high - d[i].low;
      if(r <= 0.0) continue;                     // holiday / empty bar
      sum += r;
      cnt++;
     }
   if(cnt <= 0) return;

   g_adr         = sum / cnt;
   g_adr_samples = cnt;
   g_today_hi    = d[today].high;
   g_today_lo    = d[today].low;
   g_today_range = g_today_hi - g_today_lo;
   g_adr_ok      = true;
  }

string RangesPips(const double price_value)
  {
   double ps = PipSize();
   if(ps <= 0.0) return("?");
   return(DoubleToString(price_value / ps, 1));
  }

string RangesATRText()
  {
   double a_h4 = (g_h4_n > 0 ? g_h4_atr[g_h4_n - 1] : 0.0);
   double a_m5 = (g_m5_n > 0 ? g_m5_atr[g_m5_n - 1] : 0.0);
   string s = "ATR(14): H4 ";
   s += (a_h4 > 0.0 ? RangesPips(a_h4) + " pip" : "n/a");
   s += "  |  M5 ";
   s += (a_m5 > 0.0 ? RangesPips(a_m5) + " pip" : "n/a");
   return(s);
  }

string RangesADRText()
  {
   if(!g_adr_ok || g_adr <= 0.0)
      return("ADR(" + IntegerToString(InpADRDays) + "): n/a");

   double used_pct = 100.0 * g_today_range / g_adr;
   double left     = g_adr - g_today_range;
   if(left < 0.0) left = 0.0;

   string s = "ADR(" + IntegerToString(g_adr_samples) + "): " + RangesPips(g_adr) + " pip";
   s += "  |  today " + RangesPips(g_today_range) + " pip (";
   s += DoubleToString(used_pct, 0) + "%)";
   s += "  |  left " + RangesPips(left) + " pip";
   if(used_pct >= 100.0) s += "  [EXHAUSTED]";
   return(s);
  }

#endif // HMI_RANGES_MQH
