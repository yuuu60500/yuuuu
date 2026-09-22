//+------------------------------------------------------------------+
//| HMI_FVGEngine.mqh — three-candle fair value gaps (H4 and M5)     |
//+------------------------------------------------------------------+
#ifndef HMI_FVG_MQH
#define HMI_FVG_MQH
#include "HMI_Series.mqh"

void FvgPush(HFvg &arr[], int &cnt, const int cap, const HFvg &f)
  {
   if(cnt >= cap)
     {
      for(int i = 1; i < cap; i++) arr[i-1] = arr[i];
      cnt = cap - 1;
     }
   arr[cnt] = f;
   cnt++;
  }

// Returns the index of the FVG confirmed on bar n, or -1.
int FvgDetect(const MqlRates &r[], const int n, const ENUM_TIMEFRAMES tf,
              HFvg &arr[], int &cnt, const int cap)
  {
   if(n < 2) return(-1);
   HFvg f;
   f.dir = DIR_NONE;

   if(r[n].low > r[n-2].high)                 // bullish gap
     {
      f.dir = DIR_BULL;
      f.lo  = r[n-2].high;
      f.hi  = r[n].low;
     }
   else if(r[n].high < r[n-2].low)            // bearish gap
     {
      f.dir = DIR_BEAR;
      f.lo  = r[n].high;
      f.hi  = r[n-2].low;
     }
   if(f.dir == DIR_NONE) return(-1);
   if(Pts(f.hi, f.lo) <= 0) return(-1);       // must be a real gap

   f.id           = g_next_id++;
   f.bar_index    = n;
   f.bar_time     = r[n].time;
   f.confirm_time = CloseTimeOf(r[n].time, tf);
   FvgPush(arr, cnt, cap, f);
   return(cnt - 1);
  }

//--- OB <-> FVG connection (Rule 6 / Rule 10 — FROZEN) --------------
//  Touch (gap == 0) VALID | Overlap (gap < 0) VALID | Gap > 0 INVALID
bool ConnectionValid(const int dir, const double ob_hi, const double ob_lo,
                     const double fvg_hi, const double fvg_lo, const int tol_pts)
  {
   int gap;
   if(dir == DIR_BULL) gap = Pts(fvg_lo, ob_hi);
   else                gap = Pts(ob_lo,  fvg_hi);
   return(gap <= tol_pts);
  }

#endif // HMI_FVG_MQH
