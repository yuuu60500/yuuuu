//+------------------------------------------------------------------+
//| HMI_H4RangeEngine.mqh — versioned trading range + liquidity      |
//| A range is never edited in place: every change closes the live    |
//| version and appends a new one (Rule 4).                           |
//+------------------------------------------------------------------+
#ifndef HMI_H4RANGE_MQH
#define HMI_H4RANGE_MQH
#include "HMI_H4ContextEngine.mqh"

int TRLive() { return(g_tr_n > 0 ? g_tr_n - 1 : -1); }

void TRPush(const TRange &v)
  {
   if(g_tr_n >= MAX_TRANGE)
     {
      for(int i = 1; i < MAX_TRANGE; i++) g_tr[i-1] = g_tr[i];
      g_tr_n = MAX_TRANGE - 1;
     }
   g_tr[g_tr_n] = v;
   g_tr_n++;
  }

void TRCloseLive(const datetime t)
  {
   int i = TRLive();
   if(i >= 0 && g_tr[i].valid_to == 0) g_tr[i].valid_to = t;
  }

// newest confirmed swing of a direction, swept or not
int SwingLastAny(const HSwing &arr[], const int cnt, const int dir, const datetime visible_at)
  {
   for(int i = cnt - 1; i >= 0; i--)
      if(arr[i].dir == dir && arr[i].confirm_time <= visible_at) return(i);
   return(-1);
  }

void TRNewVersion(const int h, const CtxEventType ev)
  {
   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int hi_i = SwingLastAny(g_h4sw, g_h4sw_n, DIR_BULL, t);
   int lo_i = SwingLastAny(g_h4sw, g_h4sw_n, DIR_BEAR, t);

   TRange v;
   v.version_id = g_next_id++;
   v.valid_from = t;
   v.valid_to   = 0;
   v.created_by = ev;

   if(ev == EV_BOS_UP)
     {
      v.a_lo      = (lo_i >= 0 ? g_h4sw[lo_i].price : g_h4[h].low);
      v.a_lo_time = (lo_i >= 0 ? g_h4sw[lo_i].bar_time : g_h4[h].time);
      v.a_hi      = g_h4[h].high;
      v.a_hi_time = g_h4[h].time;
     }
   else if(ev == EV_BOS_DOWN)
     {
      v.a_hi      = (hi_i >= 0 ? g_h4sw[hi_i].price : g_h4[h].high);
      v.a_hi_time = (hi_i >= 0 ? g_h4sw[hi_i].bar_time : g_h4[h].time);
      v.a_lo      = g_h4[h].low;
      v.a_lo_time = g_h4[h].time;
     }
   else                                        // CHOCH: freeze both sides
     {
      v.a_hi      = (hi_i >= 0 ? g_h4sw[hi_i].price : g_h4[h].high);
      v.a_hi_time = (hi_i >= 0 ? g_h4sw[hi_i].bar_time : g_h4[h].time);
      v.a_lo      = (lo_i >= 0 ? g_h4sw[lo_i].price : g_h4[h].low);
      v.a_lo_time = (lo_i >= 0 ? g_h4sw[lo_i].bar_time : g_h4[h].time);
     }

   TRCloseLive(t);
   TRPush(v);
  }

// Forward-only extension: a new confirmed swing beyond the live anchor
// opens a NEW version, it never rewrites the old one (Rule 4).
void TRExtendOnSwing(const int h)
  {
   int i = TRLive();
   if(i < 0) return;
   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);

   if(g_ctx == CTX_BULLISH)
     {
      int s = SwingLastAny(g_h4sw, g_h4sw_n, DIR_BULL, t);
      if(s < 0 || g_h4sw[s].confirm_time != t) return;      // only just-confirmed swings
      if(Pts(g_h4sw[s].price, g_tr[i].a_hi) <= 0) return;
      TRange v = g_tr[i];
      v.version_id = g_next_id++;
      v.valid_from = t;
      v.valid_to   = 0;
      v.a_hi       = g_h4sw[s].price;
      v.a_hi_time  = g_h4sw[s].bar_time;
      TRCloseLive(t);
      TRPush(v);
     }
   else if(g_ctx == CTX_BEARISH)
     {
      int s = SwingLastAny(g_h4sw, g_h4sw_n, DIR_BEAR, t);
      if(s < 0 || g_h4sw[s].confirm_time != t) return;
      if(Pts(g_h4sw[s].price, g_tr[i].a_lo) >= 0) return;
      TRange v = g_tr[i];
      v.version_id = g_next_id++;
      v.valid_from = t;
      v.valid_to   = 0;
      v.a_lo       = g_h4sw[s].price;
      v.a_lo_time  = g_h4sw[s].bar_time;
      TRCloseLive(t);
      TRPush(v);
     }
  }

//--- liquidity: mark only (Rule 69: never used as a filter) --------
void LiqPush(const HSwing &s)
  {
   if(g_liq_n >= MAX_LIQ)
     {
      for(int i = 1; i < MAX_LIQ; i++) g_liq[i-1] = g_liq[i];
      g_liq_n = MAX_LIQ - 1;
     }
   LiqPool p;
   p.id          = g_next_id++;
   p.type        = s.dir;
   p.price       = s.price;
   p.origin_time = s.bar_time;
   p.confirm_time = s.confirm_time;
   p.swept       = false;
   p.swept_time  = 0;
   p.lq_state    = 0;                 // LQ_INTACT (HMI_LiquidityLevels.mqh)
   p.pierce_index = -1;
   p.vis         = -1;
   g_liq[g_liq_n] = p;
   g_liq_n++;
  }

void LiqOnBar(const int h)
  {
   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   // register pools for swings confirmed by this very bar
   for(int i = g_h4sw_n - 1; i >= 0 && i >= g_h4sw_n - 4; i--)
      if(g_h4sw[i].confirm_time == t) LiqPush(g_h4sw[i]);
   // v2.42 (BRI-09 S-5): sweeps are no longer judged here. The old test -
   // any H4 wick through the level - could not tell a sweep from a break.
   // Both pools and PD/PW/PM levels are now judged on closed M5 bars by
   // LiqM5OnBar (HMI_LiquidityLevels.mqh) with one definition.
   //
   // v2.45: EXCEPT before M5 coverage begins. An H4 bar that closed before
   // the first M5 bar can never be judged on M5, and leaving the pool INTACT
   // would let a rebuild fire it again later, although a run that started
   // earlier had already resolved it. If such a bar went beyond the pool,
   // the pool was resolved before coverage - how, M5 would have to say, and
   // there is none - so it is UNKNOWN: resolved, kind unknown, no event.
   // The window starts on an H4 boundary (SeriesAlignM5ToH4), so this bar is
   // complete; the pool's own confirming bar is never tested against it.
   if(g_m5_n > 0 && t <= g_m5[0].time)
     {
      int mp = MarginM5Pts(0);
      for(int k = 0; k < g_liq_n; k++)
        {
         if(g_liq[k].swept || g_liq[k].lq_state != 0) continue;
         if(g_liq[k].confirm_time > g_h4[h].time) continue;       // confirmed at this bar's close
         bool beyond = (g_liq[k].type == DIR_BULL) ? BreakUp(g_h4[h].high, g_liq[k].price, mp)
                                                   : BreakDown(g_h4[h].low, g_liq[k].price, mp);
         if(!beyond) continue;
         g_liq[k].lq_state   = 4;                                  // LQ_UNKNOWN
         g_liq[k].swept      = true;
         g_liq[k].swept_time = t;
        }
     }
  }

#endif // HMI_H4RANGE_MQH
