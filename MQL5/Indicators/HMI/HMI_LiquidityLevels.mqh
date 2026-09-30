//+------------------------------------------------------------------+
//| HMI_LiquidityLevels.mqh — PD / PW / PM levels + sweep (BRI-09)   |
//|                                                                  |
//| MARK ONLY (BRI-09 S-1, Rule 1 / 69). Nothing in Phase 0-7 reads  |
//| any state kept here: no POI, session, block, cycle or model can  |
//| be gated, filtered or moved by a level or a sweep.               |
//|                                                                  |
//| One sweep definition for every level (S-5), judged on CLOSED M5  |
//| bars (S-3):                                                      |
//|   beyond   the wick goes past the level by more than the break   |
//|            margin (D-6, same per-bar margin as everywhere else)  |
//|   SWEEP    a close back on the original side within N bars of   |
//|            the first bar that went beyond (N = 0: same bar)      |
//|   BROKEN   N bars later and still no close back                  |
//| Each level resolves once (S-4) and is committed at the close of  |
//| the bar that resolved it (AX-1).                                 |
//+------------------------------------------------------------------+
#ifndef HMI_LIQLEVELS_MQH
#define HMI_LIQLEVELS_MQH
#include "HMI_H4RangeEngine.mqh"

#define LQ_INTACT   0
#define LQ_PENDING  1
#define LQ_SWEPT    2
#define LQ_BROKEN   3
#define LQ_UNKNOWN  4          // history does not reach the level's start: state cannot be known - never fires

#define PL_COUNT    6          // PDH PDL PWH PWL PMH PML, in that order

struct PeriodLevel
  {
   bool              valid;
   int               side;           // +1 high (buy-side), -1 low (sell-side)
   double            price;
   datetime          from;           // start of the period this level applies to
   int               lq_state;
   int               pierce_index;   // M5 bar that first went beyond, -1 if none
   datetime          event_time;     // close of the resolving bar, 0 while open
  };

struct LiqEvent
  {
   string            name;           // PDH ... PML / BSL / SSL
   int               side;
   double            price;
   int               kind;           // LQ_SWEPT / LQ_BROKEN
   datetime          bar_time;       // OPEN time of the resolving M5 bar (label anchor)
   long              uid;            // drawing owner
   int               vis;
  };

PeriodLevel g_pl[PL_COUNT];
datetime    g_pl_key[3];             // day / week / month start the levels belong to
LiqEvent    g_liqev[MAX_LIQEV];  int g_liqev_n = 0;
long        g_liqev_uid = 0;
// drawing bookkeeping (read and written by HMI_ObjectManager only)
long        g_pl_drawn[PL_COUNT];    // owner of the line each slot last drew, 0 = none
long        g_lqe_del_from = 1;      // labels of events below this uid are already gone
// v2.47 replay bars: the M5 bars BEFORE the window, for this module only
MqlRates    g_lr[];  int g_lr_n = 0;  double g_lr_atr[];
int         g_lr_unknown = 0;        // items the loaded history could not reach

string PLName(const int i)
  {
   switch(i)
     {
      case 0: return("PDH");
      case 1: return("PDL");
      case 2: return("PWH");
      case 3: return("PWL");
      case 4: return("PMH");
     }
   return("PML");
  }

void LiqLevelsReset()
  {
   for(int i = 0; i < PL_COUNT; i++) { g_pl[i].valid = false; g_pl[i].lq_state = LQ_INTACT; }
   for(int k = 0; k < 3; k++) g_pl_key[k] = 0;
   g_liqev_n   = 0;
   g_liqev_uid = 0;
   for(int d = 0; d < PL_COUNT; d++) g_pl_drawn[d] = 0;
   g_lqe_del_from = 1;
   g_lr_n = 0;  g_lr_unknown = 0;
  }

//--- period boundaries in broker server time (S-2) ------------------
datetime DayStartOf(const datetime t) { return(t - (t % 86400)); }

datetime WeekStartOf(const datetime t)            // MT5 W1 bars open on Sunday
  {
   MqlDateTime s; TimeToStruct(t, s);
   return(DayStartOf(t) - (datetime)(s.day_of_week * 86400));
  }

datetime MonthStartOf(const datetime t)
  {
   MqlDateTime s; TimeToStruct(t, s);
   s.day = 1; s.hour = 0; s.min = 0; s.sec = 0;
   return(StructToTime(s));
  }

datetime PrevMonthStartOf(const datetime t)
  {
   MqlDateTime s; TimeToStruct(MonthStartOf(t), s);
   if(s.mon == 1) { s.mon = 12; s.year--; } else s.mon--;
   return(StructToTime(s));
  }

// High / low of [from, to) from H4 bars Phase 0 has ALREADY consumed.
// H4 bars nest exactly inside server days, weeks and months, so this is
// the D1 / W1 / MN1 bar's own high and low - taken from the one H4 feed the
// engine already keeps in step with M5 (H4VisibleTo), instead of three more
// series that would each need their own sync and reload handling.
// Refuses a period the loaded window does not fully cover.
bool H4PeriodHiLo(const datetime from, const datetime to, double &hi, double &lo)
  {
   if(g_h4_n <= 0 || g_h4[0].time > from) return(false);
   bool any = false;
   for(int h = 0; h < g_h4_cursor && h < g_h4_n; h++)
     {
      if(g_h4[h].time < from) continue;
      if(g_h4[h].time >= to)  break;
      if(!any) { hi = g_h4[h].high; lo = g_h4[h].low; any = true; }
      else     { hi = MathMax(hi, g_h4[h].high); lo = MathMin(lo, g_h4[h].low); }
     }
   return(any);
  }

void PLSet(const int i, const int side, const double px, const datetime from)
  {
   g_pl[i].valid        = true;
   g_pl[i].side         = side;
   g_pl[i].price        = px;
   g_pl[i].from         = from;
   g_pl[i].lq_state     = LQ_INTACT;
   g_pl[i].pierce_index = -1;
   g_pl[i].event_time   = 0;
  }

void PLPair(const int i, const bool ok, const double hi, const double lo, const datetime from)
  {
   if(!ok) { g_pl[i].valid = false; g_pl[i+1].valid = false; return; }
   PLSet(i,     +1, hi, from);
   PLSet(i + 1, -1, lo, from);
  }

// Previous TRADING day: the newest consumed H4 day before today, skipping a
// short Sunday session when asked to (S-2 appendix).
datetime PrevTradingDay(const datetime today)
  {
   for(int h = MathMin(g_h4_cursor, g_h4_n) - 1; h >= 0; h--)
     {
      datetime d = DayStartOf(g_h4[h].time);
      if(d >= today) continue;
      if(InpPDSkipSunday)
        {
         MqlDateTime s; TimeToStruct(d, s);
         if(s.day_of_week == 0) continue;
        }
      return(d);
     }
   return(0);
  }

void LiqLevelsRoll(const int n)
  {
   datetime t = g_m5[n].time;
   double hi = 0.0, lo = 0.0;

   // `ok` is computed on its own line: argument evaluation order is not
   // guaranteed, so hi / lo must not be filled inside the same call's
   // argument list that also passes them by value.
   datetime d0 = DayStartOf(t);
   if(d0 != g_pl_key[0])
     {
      g_pl_key[0] = d0;
      datetime pd = PrevTradingDay(d0);
      bool ok = (pd > 0 && H4PeriodHiLo(pd, pd + 86400, hi, lo));
      PLPair(0, ok, hi, lo, d0);
     }
   datetime w0 = WeekStartOf(t);
   if(w0 != g_pl_key[1])
     {
      g_pl_key[1] = w0;
      datetime pw = w0 - 7 * 86400;
      bool ok = H4PeriodHiLo(pw, w0, hi, lo);
      PLPair(2, ok, hi, lo, w0);
     }
   datetime m0 = MonthStartOf(t);
   if(m0 != g_pl_key[2])
     {
      g_pl_key[2] = m0;
      bool ok = H4PeriodHiLo(PrevMonthStartOf(t), m0, hi, lo);
      PLPair(4, ok, hi, lo, m0);
     }
  }

//=== v2.47: one judgement for every M5 bar, replayed or live ==========
// Bars before the first M5 bar of the window live in g_lr (loaded only for
// this module); index k < 0 means g_lr[g_lr_n + k], k >= 0 means g_m5[k].
// The shared g_m5 series is never touched for liquidity's sake.

bool LiqBarAt(const int k, MqlRates &r)
  {
   if(k >= 0) { if(!SafeIdx(k, g_m5_n)) return(false); r = g_m5[k]; return(true); }
   int j = g_lr_n + k;
   if(j < 0) return(false);
   r = g_lr[j];
   return(true);
  }

// ATR(14) exactly as SeriesComputeATR defines it, at M5 index n. For the
// first 14 window bars g_m5_atr is 0 (its own warm-up); here the replay bars
// supply the missing history, so the threshold at the seam is the one a run
// started earlier would have used - the historical threshold, restored.
double LiqAtrAt(const int n)
  {
   if(n >= 14 || g_lr_n <= 0) return(SafeIdx(n, g_m5_n) ? g_m5_atr[n] : 0.0);
   double sum = 0.0;
   for(int k = n - 13; k <= n; k++)
     {
      MqlRates cur, prv;
      if(!LiqBarAt(k, cur) || !LiqBarAt(k - 1, prv)) return(0.0);
      sum += MathMax(cur.high - cur.low,
             MathMax(MathAbs(cur.high - prv.close), MathAbs(cur.low - prv.close)));
     }
   return(sum / 14.0);
  }

int LiqMarginAt(const int n) { return(MarginPtsFrom(LiqAtrAt(n))); }

//--- S-3 on one closed M5 bar. Returns LQ_SWEPT / LQ_BROKEN when the level
//--- resolves on this bar, LQ_INTACT otherwise. idx is the bar's index in
//--- the combined numbering above, so a pierce during the replay carries
//--- over into the window with the right bar count. -----------------------
int LiqJudgeBar(const int side, const double level, const MqlRates &b, const int mp,
                const int idx, int &state, int &pierce)
  {
   if(state == LQ_SWEPT || state == LQ_BROKEN || state == LQ_UNKNOWN) return(LQ_INTACT);
   if(state == LQ_INTACT)
     {
      bool beyond = (side > 0) ? BreakUp(b.high, level, mp) : BreakDown(b.low, level, mp);
      if(!beyond) return(LQ_INTACT);
      state  = LQ_PENDING;
      pierce = idx;
     }
   bool back = (side > 0) ? (Pts(b.close, level) <= 0) : (Pts(b.close, level) >= 0);
   if(back) { state = LQ_SWEPT; return(LQ_SWEPT); }
   if(idx - pierce >= MathMax(0, InpLiqSweepReclaimBars)) { state = LQ_BROKEN; return(LQ_BROKEN); }
   return(LQ_INTACT);
  }

int LiqJudge(const int side, const double level, int &state, int &pierce, const int n)
  {
   return(LiqJudgeBar(side, level, g_m5[n], LiqMarginAt(n), n, state, pierce));
  }

// Replay one level / pool from its own start over the M5 bars before the
// window, with each bar's own ATR threshold. No event is emitted - those
// bars are outside the window - but the STATE is what a run that started
// earlier would hold now. History that does not reach the start leaves the
// state unknowable: UNKNOWN, never fires, and counted in the build log.
void LiqReplayItem(const int side, const double price, const datetime start, const datetime avail,
                   int &state, int &pierce, datetime &ev_time)
  {
   if(start < avail) { state = LQ_UNKNOWN; g_lr_unknown++; return; }
   for(int r = 0; r < g_lr_n; r++)
     {
      if(g_lr[r].time < start) continue;
      int k = LiqJudgeBar(side, price, g_lr[r], MarginPtsFrom(g_lr_atr[r]), r - g_lr_n, state, pierce);
      if(k != LQ_INTACT) { ev_time = CloseTimeOf(g_lr[r].time, PERIOD_M5); return; }
     }
  }

void LiqReplay()
  {
   g_lr_n = 0;  g_lr_unknown = 0;
   if(g_m5_n <= 0) return;
   datetime first = g_m5[0].time;
   datetime need  = first;
   for(int i = 0; i < PL_COUNT; i++)
      if(g_pl[i].valid && g_pl[i].from < need) need = g_pl[i].from;
   for(int j = 0; j < g_liq_n; j++)
      if(!g_liq[j].swept && g_liq[j].confirm_time < need) need = g_liq[j].confirm_time;
   if(need >= first) return;                             // everything starts inside the window

   // three extra days so ATR(14) is already valid at `need`, weekend or not
   MqlRates tmp[];
   int got = CopyRates(_Symbol, PERIOD_M5, need - 3 * 86400, first - 1, tmp);
   if(got > 0)
     {
      ArrayResize(g_lr, got);
      for(int i = 0; i < got; i++) g_lr[i] = tmp[i];
      g_lr_n = got;
      SeriesComputeATR(g_lr, g_lr_n, g_lr_atr, 0);
     }
   datetime avail = first;                               // nothing loaded: nothing is known
   if(g_lr_n > 0)
      avail = g_lr[(InpBreakMarginMode == MARGIN_ATR_FRAC ? MathMin(14, g_lr_n - 1) : 0)].time;

   for(int i = 0; i < PL_COUNT; i++)
     {
      if(!g_pl[i].valid || g_pl[i].from >= first) continue;
      int st = g_pl[i].lq_state, pi = g_pl[i].pierce_index;  datetime et = g_pl[i].event_time;
      LiqReplayItem(g_pl[i].side, g_pl[i].price, g_pl[i].from, avail, st, pi, et);
      g_pl[i].lq_state = st;  g_pl[i].pierce_index = pi;  g_pl[i].event_time = et;
     }
   for(int j = 0; j < g_liq_n; j++)
     {
      if(g_liq[j].swept || g_liq[j].confirm_time >= first) continue;
      int side = (g_liq[j].type == DIR_BULL ? +1 : -1);
      int st = g_liq[j].lq_state, pi = g_liq[j].pierce_index;  datetime et = g_liq[j].swept_time;
      LiqReplayItem(side, g_liq[j].price, g_liq[j].confirm_time, avail, st, pi, et);
      g_liq[j].lq_state = st;  g_liq[j].pierce_index = pi;
      if(st == LQ_SWEPT || st == LQ_BROKEN || st == LQ_UNKNOWN) { g_liq[j].swept = true; g_liq[j].swept_time = et; }
     }
   if(InpLogSignals)
      PrintFormat("HMI-LIQ-REPLAY,%s,need_from=%s,have_from=%s,bars=%d,unknown=%d,inst=%s",
                  _Symbol, TimeToString(need, TIME_DATE|TIME_MINUTES),
                  (g_lr_n > 0 ? TimeToString(avail, TIME_DATE|TIME_MINUTES) : "none"),
                  g_lr_n, g_lr_unknown, g_inst);
  }

datetime LiqPierceTime(const int k) { MqlRates r; if(LiqBarAt(k, r)) return(r.time); return(0); }

// Record + log one resolution. The row uses the MODEL row's column layout
// (ids in columns 3-4, event time in 7) so the repaint and LIVE-vs-BUILD
// checks take sweeps exactly like marks (S-6): a sweep that appears live
// and not in the rebuild is the same failure as a vanished model.
void LiqEmit(const string name, const int side, const double px, const int pierce,
             const int n, const int kind)
  {
   if(g_liqev_n >= MAX_LIQEV)
     {
      for(int i = 1; i < g_liqev_n; i++) g_liqev[i-1] = g_liqev[i];
      g_liqev_n--;
     }
   LiqEvent e;
   e.name     = name;
   e.side     = side;
   e.price    = px;
   e.kind     = kind;
   e.bar_time = g_m5[n].time;
   e.uid      = ++g_liqev_uid;
   e.vis      = -1;
   g_liqev[g_liqev_n] = e;
   g_liqev_n++;

   if(InpLogSignals)
      PrintFormat("%s,%s,LIQ,%d,0,0,%s,%s,%s,%s,%s,0,inst=%s",
                  (g_live ? "HMI-LIVE" : "HMI-BUILD"), _Symbol, side, name,
                  (kind == LQ_SWEPT ? "SWEEP" : "BROKEN"),
                  TimeToString(CloseTimeOf(g_m5[n].time, PERIOD_M5), TIME_DATE|TIME_SECONDS),
                  DoubleToString(px, _Digits),
                  TimeToString(LiqPierceTime(pierce), TIME_DATE|TIME_SECONDS), g_inst);
  }

//--- Phase 1b: runs on every closed M5 bar, warm-up included, so the
//--- level state is the same whichever bar a build starts from; only
//--- the EVENTS are held back during warm-up, like every other mark. -
void LiqM5OnBar(const int n)
  {
   if(!SafeIdx(n, g_m5_n)) return;
   bool emit = (n >= InpWarmupSuppressBars);
   datetime tc = CloseTimeOf(g_m5[n].time, PERIOD_M5);

   LiqLevelsRoll(n);
   if(n == 0) LiqReplay();                    // levels and pools that began before the window
   for(int i = 0; i < PL_COUNT; i++)
     {
      if(!g_pl[i].valid) continue;
      int st = g_pl[i].lq_state, pi = g_pl[i].pierce_index;
      int k  = LiqJudge(g_pl[i].side, g_pl[i].price, st, pi, n);
      g_pl[i].lq_state = st;  g_pl[i].pierce_index = pi;
      if(k == LQ_INTACT) continue;
      g_pl[i].event_time = tc;
      if(emit) LiqEmit(PLName(i), g_pl[i].side, g_pl[i].price, g_pl[i].pierce_index, n, k);
     }
   for(int j = 0; j < g_liq_n; j++)
     {
      if(g_liq[j].swept) continue;
      int side = (g_liq[j].type == DIR_BULL ? +1 : -1);
      int st = g_liq[j].lq_state, pi = g_liq[j].pierce_index;
      int k  = LiqJudge(side, g_liq[j].price, st, pi, n);
      g_liq[j].lq_state = st;  g_liq[j].pierce_index = pi;
      if(k == LQ_INTACT) continue;
      g_liq[j].swept      = true;        // resolved: the line goes (unchanged display rule)
      g_liq[j].swept_time = tc;
      if(emit) LiqEmit(side > 0 ? "BSL" : "SSL", side, g_liq[j].price, g_liq[j].pierce_index, n, k);
     }
  }

#endif // HMI_LIQLEVELS_MQH
