//+------------------------------------------------------------------+
//| HMI_SwingEngine.mqh — fractal swings shared by H4 and M5         |
//| A swing is only visible from its confirm_time (Rule 25 / 48).    |
//+------------------------------------------------------------------+
#ifndef HMI_SWING_MQH
#define HMI_SWING_MQH
#include "HMI_Series.mqh"

void SwingPush(HSwing &arr[], int &cnt, const int cap, const HSwing &s)
  {
   if(cnt >= cap)
     {
      for(int i = 1; i < cap; i++) arr[i-1] = arr[i];
      cnt = cap - 1;
     }
   arr[cnt] = s;
   cnt++;
  }

// Ties resolve to the EARLIER bar: strict '>' on the left, '>=' on the
// right (Spec 3.1) so historical build and live replay agree.
void SwingDetect(const MqlRates &r[], const int n, const ENUM_TIMEFRAMES tf,
                 const int L, const int R, HSwing &arr[], int &cnt, const int cap)
  {
   // A-28: L and R come straight from inputs and MQL5 enforces no range.
   // R < 1 makes c = n - R land at or past n: the right-side loop then never
   // runs, so the fractal is "confirmed" with no confirmation at all, and at
   // the newest bar c indexes past the end of the array. A fractal needs at
   // least one bar on each side by definition.
   if(L < 1 || R < 1) return;
   int c = n - R;
   if(c - L < 0 || c <= 0 || c >= n) return;

   bool hi_ok = true, lo_ok = true;
   for(int j = c - L; j < c && (hi_ok || lo_ok); j++)
     {
      if(r[c].high <= r[j].high) hi_ok = false;
      if(r[c].low  >= r[j].low ) lo_ok = false;
     }
   for(int j = c + 1; j <= c + R && (hi_ok || lo_ok); j++)
     {
      if(r[c].high < r[j].high) hi_ok = false;
      if(r[c].low  > r[j].low ) lo_ok = false;
     }

   if(hi_ok)
     {
      HSwing s;
      s.id           = g_next_id++;
      s.dir          = DIR_BULL;
      s.bar_index    = c;
      s.bar_time     = r[c].time;
      s.confirm_time = CloseTimeOf(r[n].time, tf);
      s.price        = r[c].high;
      s.swept        = false;
      s.swept_time   = 0;
      SwingPush(arr, cnt, cap, s);
     }
   if(lo_ok)
     {
      HSwing s;
      s.id           = g_next_id++;
      s.dir          = DIR_BEAR;
      s.bar_index    = c;
      s.bar_time     = r[c].time;
      s.confirm_time = CloseTimeOf(r[n].time, tf);
      s.price        = r[c].low;
      s.swept        = false;
      s.swept_time   = 0;
      SwingPush(arr, cnt, cap, s);
     }
  }

//--- most recent unswept confirmed swing of a direction -------------
int SwingLastUnswept(const HSwing &arr[], const int cnt, const int dir, const datetime visible_at)
  {
   for(int i = cnt - 1; i >= 0; i--)
      if(arr[i].dir == dir && !arr[i].swept && arr[i].confirm_time <= visible_at)
         return(i);
   return(-1);
  }

#endif // HMI_SWING_MQH
