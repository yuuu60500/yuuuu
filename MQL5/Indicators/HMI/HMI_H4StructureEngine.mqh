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

// A-33 (v2.53): one closed H4 bar = at most one structure event.
// H4DetectBreak still decides WHETHER bar h breaks structure and which swing
// is the primary reference: the latest confirmed, unprocessed swing of the
// direction (Spec 2.2) - that is unchanged. What changes is what the break
// leaves behind. Every OTHER confirmed, unprocessed swing of the same
// direction that this same close effectively breaks (same margin, same
// visibility as the primary) is processed with it. Before, they stayed
// unprocessed, and each later bar that merely stayed beyond them "broke"
// the next one: one BOS per bar out of a single push, while price was
// already turning back (A-33). Swings this close does NOT break are left
// alone, and so are swings of the other direction.
// Returns how many extra swings were processed; `list` names them for the
// log (time@price, oldest first).
int H4ConsumeSameDirBroken(const int h, const int dir, const int primary, const datetime t, string &list)
  {
   list = "";
   if(!SafeIdx(h, g_h4_n) || dir == DIR_NONE) return(0);
   datetime vis = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int      mp  = MarginH4Pts(h);
   int      n   = 0;
   for(int i = 0; i < g_h4sw_n; i++)
     {
      if(i == primary || g_h4sw[i].dir != dir || g_h4sw[i].swept) continue;
      if(g_h4sw[i].confirm_time > vis) continue;            // only swings confirmed by then
      bool brk = (dir == DIR_BULL) ? BreakUp  (g_h4[h].close, g_h4sw[i].price, mp)
                                   : BreakDown(g_h4[h].close, g_h4sw[i].price, mp);
      if(!brk) continue;
      H4ConsumeSwing(i, t);
      n++;
      if(InpLogSignals)
         list += (list == "" ? "" : "|") + TimeToString(g_h4sw[i].bar_time, TIME_DATE|TIME_MINUTES) +
                 "@" + DoubleToString(g_h4sw[i].price, _Digits);
     }
   return(n);
  }

//====================== BRI-12 (v2.54) ==============================
// Effective close break of a level by H4 bar h in direction dir: the same
// strict integer-point margin as every other H4 break (global semantics
// unchanged).
bool H4CloseBreaks(const int h, const int dir, const double level)
  {
   if(!SafeIdx(h, g_h4_n)) return(false);
   int mp = MarginH4Pts(h);
   return(dir == DIR_BULL ? BreakUp(g_h4[h].close, level, mp)
                          : BreakDown(g_h4[h].close, level, mp));
  }

// The latest confirmed, unprocessed swing of one direction, when bar h's
// close breaks it; -1 otherwise. One direction of H4DetectBreak: a trend
// judges failure, continuation and internal swings separately (P-7).
int H4DetectBreakDir(const int h, const int dir)
  {
   if(!SafeIdx(h, g_h4_n)) return(-1);
   datetime vis = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int i = SwingLastUnswept(g_h4sw, g_h4sw_n, dir, vis);
   if(i >= 0 && H4CloseBreaks(h, dir, g_h4sw[i].price)) return(i);
   return(-1);
  }

// Has any H4 close after the swing's confirmation, up to and including bar
// h, effectively broken it (each bar with its own margin)? "Not processed"
// is not the same thing: a swing is processed only when the state machine
// looks at it, and a close can break a swing it does not look at.
bool H4SwingBrokenSince(const int idx, const int h)
  {
   if(!SafeIdx(idx, g_h4sw_n)) return(true);
   int from = MathMax(g_h4sw[idx].bar_index + 1, 0);
   for(int k = from; k <= h && k < g_h4_n; k++)
     {
      if(CloseTimeOf(g_h4[k].time, PERIOD_H4) <= g_h4sw[idx].confirm_time) continue;
      if(H4CloseBreaks(k, g_h4sw[idx].dir, g_h4sw[idx].price)) return(true);
     }
   return(false);
  }

// P-1: the candidate a BOS of direction dir on bar h leaves behind. Bounded
// by the swing this BOS broke (primary): an opposite swing FORMED after it,
// already confirmed at this close, not processed and not effectively broken
// by any close since its confirmation - this close included (v2.54r2, P1).
// Of those, the latest formed. A swing formed before the primary belongs to
// an earlier move and is never a candidate; one that confirms after this
// close is not known yet; a broken one is not a legal level, ever.
int H4ProtCandidate(const int dir, const int primary, const int h, const datetime vis)
  {
   if(!SafeIdx(primary, g_h4sw_n)) return(-1);
   datetime after = g_h4sw[primary].bar_time;
   int best = -1;
   for(int i = 0; i < g_h4sw_n; i++)
     {
      if(g_h4sw[i].dir != -dir || g_h4sw[i].swept) continue;
      if(g_h4sw[i].confirm_time > vis || g_h4sw[i].bar_time <= after) continue;
      if(best >= 0 && g_h4sw[i].bar_time <= g_h4sw[best].bar_time) continue;
      if(H4SwingBrokenSince(i, h)) continue;
      best = i;
     }
   return(best);
  }

// P-4: every confirmed, unprocessed swing of direction dir that bar h's
// close effectively breaks is processed - not only the latest one, which a
// newer, unbroken swing can shadow. Returns the latest of them (the
// diagnostic row's primary) or -1; `also` / `list` name the others.
int H4ConsumeAllBroken(const int h, const int dir, const datetime t, string &list, int &also)
  {
   list = "";
   also = 0;
   if(!SafeIdx(h, g_h4_n)) return(-1);
   datetime vis = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   int last = -1;
   for(int i = 0; i < g_h4sw_n; i++)
     {
      if(g_h4sw[i].dir != dir || g_h4sw[i].swept || g_h4sw[i].confirm_time > vis) continue;
      if(H4CloseBreaks(h, dir, g_h4sw[i].price)) last = i;
     }
   if(last < 0) return(-1);
   H4ConsumeSwing(last, t);
   also = H4ConsumeSameDirBroken(h, dir, last, t, list);
   return(last);
  }

// P-5: structure that can resolve a TRANSITION. t_choch is the close time
// of the CHOCH bar. The first bar after it OPENS at t_choch, so formation is
// bar_time >= t_choch (the CHOCH bar itself opened earlier and is old), and
// the swing must also be confirmed after the CHOCH close.
bool H4FreshAfter(const int idx, const datetime t_choch)
  {
   if(!SafeIdx(idx, g_h4sw_n)) return(false);
   return(g_h4sw[idx].bar_time >= t_choch && g_h4sw[idx].confirm_time > t_choch);
  }

// The stored swing a level was taken from; -1 once it left the window.
int H4SwingById(const long id)
  {
   for(int i = g_h4sw_n - 1; i >= 0; i--)
      if(g_h4sw[i].id == id) return(i);
   return(-1);
  }

#endif // HMI_H4STRUCT_MQH
