//+------------------------------------------------------------------+
//| HMI_CycleManager.mqh — ARMED arbitration and cycle isolation     |
//| Every reference lives INSIDE the cycle struct, so an old cycle    |
//| cannot leak into a new one (Rule 15).                             |
//+------------------------------------------------------------------+
#ifndef HMI_CYCLE_MQH
#define HMI_CYCLE_MQH
#include "HMI_M5BlockEngine.mqh"

//--- BRI-08 diagnostics (v2.55, log only; docs/02 "BRI-08 修订稿 2" B8-5) ----
// Times: armed = ARMED bar CLOSE; every other time = M5 bar OPEN. Each margin is
// MarginM5Pts() of the bar it is printed next to - never the confirming or the
// ARMED bar's margin standing in for another bar's.
string B8Px(const double v) { return(DoubleToString(v, _Digits)); }

bool B8Beyond(const int dir, const double close, const double level, const int mp)
  {
   return(dir == DIR_BULL ? BreakUp(close, level, mp) : BreakDown(close, level, mp));
  }

void B8LogRefCISD(const IdentificationCycle &cy, const int A, const string state,
                  const int k, const int j, const int b)
  {
   if(!InpLogSignals) return;
   bool   has  = (k >= 0);
   double cand = (has ? g_m5[k].open : 0.0);
   bool   ok   = (state == "OK");
   PrintFormat("HMI-REF,%s,CISD,cycle=%I64d,dir=%d,live=%d,armed=%s,armed_mp=%d,state=%s,level=%s,ref=%s," +
               "cand_level=%s,run_from=%s,run_to=%s,brk_bar=%s,brk_close=%s,brk_mp=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, cy.cycle_id, cy.dir, (g_live ? 1 : 0), DiagT(cy.armed_time), MarginM5Pts(A), state,
               (ok ? B8Px(cand) : "NA"), (ok ? DiagT(g_m5[k].time) : "-"),
               (has ? B8Px(cand) : "NA"), (has ? DiagT(g_m5[k].time) : "-"), (has ? DiagT(g_m5[j].time) : "-"),
               (b >= 0 ? DiagT(g_m5[b].time) : "-"), (b >= 0 ? B8Px(g_m5[b].close) : "NA"),
               (b >= 0 ? IntegerToString(MarginM5Pts(b)) : "NA"),
               g_inst, g_run_id, g_init_seq);
  }

// One HMI-BRK row per CISD / MSS confirmation: the confirming bar and the bar
// before it, each with its own margin (B8-SLOW is read from prev_close / prev_mp).
void B8LogBreak(const IdentificationCycle &cy, const string model, const int n,
                const double level, const datetime ref)
  {
   if(!InpLogSignals || n < 1) return;
   PrintFormat("HMI-BRK,%s,%s,cycle=%I64d,dir=%d,live=%d,bar=%s,close=%s,mp=%d,prev_bar=%s,prev_close=%s,prev_mp=%d," +
               "level=%s,ref=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, model, cy.cycle_id, cy.dir, (g_live ? 1 : 0),
               DiagT(g_m5[n].time), B8Px(g_m5[n].close), MarginM5Pts(n),
               DiagT(g_m5[n-1].time), B8Px(g_m5[n-1].close), MarginM5Pts(n-1),
               B8Px(level), DiagT(ref), g_inst, g_run_id, g_init_seq);
  }

//--- Rule 19: freeze the CISD reference once, at ARMED --------------
// BRI-08 (v2.55): the run is chosen exactly as before; if any bar i in
// [k+1, A] - the ARMED bar included - already closed beyond open[k] by its own
// margin, the reference was broken before the cycle existed: CISD is N/A for
// this cycle (no other run is searched). A close between the level and the
// threshold is not a break (guard 3).
void Cycle_FreezeCISDReference(IdentificationCycle &cy, const int A)
  {
   cy.cisd_level    = 0.0;
   cy.cisd_ref_time = 0;
   cy.cisd_run_from = 0;
   cy.cisd_run_to   = 0;

   int lookback = MathMax(1, InpCISDLookbackBars);
   int lo  = MathMax(0, A - lookback + 1);
   int opp = -cy.dir;

   int j = -1;
   for(int k = A; k >= lo; k--)
      if(CandleDir(g_m5[k]) == opp) { j = k; break; }
   if(j < 0) { cy.result[MDL_CISD] = MR_NA; B8LogRefCISD(cy, A, "NA_NONE", -1, -1, -1); return; }

   int k2 = j;
   while(k2 - 1 >= lo && CandleDir(g_m5[k2-1]) == opp) k2--;

   double cand = g_m5[k2].open;          // OPEN of the OLDEST bar of the run
   int b = -1;
   for(int i = k2 + 1; i <= A && b < 0; i++)
      if(B8Beyond(cy.dir, g_m5[i].close, cand, MarginM5Pts(i))) b = i;
   if(b >= 0) { cy.result[MDL_CISD] = MR_NA; B8LogRefCISD(cy, A, "NA_BROKEN", k2, j, b); return; }

   cy.cisd_level    = cand;
   cy.cisd_ref_time = g_m5[k2].time;
   cy.cisd_run_from = g_m5[k2].time;
   cy.cisd_run_to   = g_m5[j].time;
   B8LogRefCISD(cy, A, "OK", k2, j, -1);
  }

// C5: first bar m in (swing, A] whose close is beyond the swing, each bar with its
// own margin (BRI-08) or, for the v2.54 diagnostic, with the ARMED bar's margin.
int MSS_C5Break(const int dir, const int si, const int A, const bool per_bar, const int mpA)
  {
   for(int m = g_m5sw[si].bar_index + 1; m <= A; m++)
      if(B8Beyond(dir, g_m5[m].close, g_m5sw[si].price, (per_bar ? MarginM5Pts(m) : mpA)))
         return(m);
   return(-1);
  }

//--- Rule 25 / 26 / 29: freeze the MSS reference once, at ARMED -----
// BRI-08 (v2.55): C5 judges each bar with its own margin. The v2.54 choice (C5
// with the ARMED bar's margin) is worked out alongside for the log only - it is
// never written into the cycle and decides nothing.
void Cycle_FreezeMSSReference(IdentificationCycle &cy, const int A)
  {
   cy.mss_level    = 0.0;
   cy.mss_ref_time = 0;

   int W  = MathMax(5, InpSetupWindowBars);
   int lo = MathMax(0, A - W + 1);
   datetime armed_close = CloseTimeOf(g_m5[A].time, PERIOD_M5);
   int mpA  = MarginM5Pts(A);
   int want = cy.dir;                      // bull cycle -> swing HIGH

   int pick = -1, pick_old = -1;
   string c5diff = "";
   for(int i = g_m5sw_n - 1; i >= 0 && (pick < 0 || pick_old < 0); i--)
     {
      if(g_m5sw[i].bar_index < lo) break;                     // C2 window
      if(g_m5sw[i].dir != want) continue;                     // C3
      if(g_m5sw[i].confirm_time > armed_close) continue;      // C1 no future swing
      if(cy.dir == DIR_BULL && Pts(g_m5sw[i].price, g_m5[A].high) <= 0) continue;  // C4
      if(cy.dir == DIR_BEAR && Pts(g_m5sw[i].price, g_m5[A].low)  >= 0) continue;

      int bn = MSS_C5Break(cy.dir, i, A, true,  mpA);         // C5, BRI-08
      int bo = MSS_C5Break(cy.dir, i, A, false, mpA);         // C5, v2.54 (diagnostic)
      if((bn >= 0) != (bo >= 0))
        {
         int m = (bo >= 0 ? bo : bn);                         // the decisive bar of the side that took it
         if(c5diff != "") c5diff += ";";
         c5diff += StringFormat("%s@%s/%s/%s/%d/o%dn%d", DiagT(g_m5sw[i].bar_time), B8Px(g_m5sw[i].price),
                                DiagT(g_m5[m].time), B8Px(g_m5[m].close), MarginM5Pts(m),
                                (bo >= 0 ? 1 : 0), (bn >= 0 ? 1 : 0));
        }
      if(pick < 0 && bn < 0)     pick = i;
      if(pick_old < 0 && bo < 0) pick_old = i;
     }

   if(pick >= 0)
     {
      cy.mss_level    = g_m5sw[pick].price;
      cy.mss_ref_time = g_m5sw[pick].bar_time;
     }
   else
      cy.result[MDL_MSS] = MR_NA;          // bounded search failed: no MSS this cycle

   if(InpLogSignals)
      PrintFormat("HMI-REF,%s,MSS,cycle=%I64d,dir=%d,live=%d,armed=%s,armed_mp=%d,state=%s,level=%s,ref=%s," +
                  "old_state=%s,old_level=%s,old_ref=%s,c5diff=%s,inst=%s,run=%I64d,init=%d",
                  _Symbol, cy.cycle_id, cy.dir, (g_live ? 1 : 0), DiagT(cy.armed_time), mpA,
                  (pick >= 0 ? "OK" : "NA_NONE"),
                  (pick >= 0 ? B8Px(g_m5sw[pick].price) : "NA"), (pick >= 0 ? DiagT(g_m5sw[pick].bar_time) : "-"),
                  (pick_old >= 0 ? "OK" : "NA_NONE"),
                  (pick_old >= 0 ? B8Px(g_m5sw[pick_old].price) : "NA"),
                  (pick_old >= 0 ? DiagT(g_m5sw[pick_old].bar_time) : "-"),
                  (c5diff == "" ? "-" : c5diff), g_inst, g_run_id, g_init_seq);
  }

//--- cycle storage --------------------------------------------------
int CycPush(const IdentificationCycle &cy)
  {
   int cap = MathMin(MAX_CYCLES, MathMax(2, InpMaxCyclesKept));
   if(g_cyc_n >= cap)
     {
      for(int i = 1; i < g_cyc_n; i++) g_cyc[i-1] = g_cyc[i];
      g_cyc_n--;
      if(g_active_cyc > 0) g_active_cyc--; else g_active_cyc = -1;
     }
   g_cyc[g_cyc_n] = cy;
   g_cyc_n++;
   return(g_cyc_n - 1);
  }

void CycCloseActive(const datetime t)
  {
   if(!SafeIdx(g_active_cyc, g_cyc_n)) { g_active_cyc = -1; return; }
   for(int m = 0; m < MDL_COUNT; m++)
      if(g_cyc[g_active_cyc].result[m] == MR_PENDING)
         g_cyc[g_active_cyc].result[m] = MR_PASS;     // Rule 15 / 34
   g_cyc[g_active_cyc].state       = CY_CLOSED;
   g_cyc[g_active_cyc].closed_time = t;
   g_active_cyc = -1;
  }

int CycCreate(const int blk_idx, const int A)
  {
   IdentificationCycle cy;
   cy.cycle_id           = g_blk[blk_idx].id;     // cycle id == block id (Spec 9.1)
   cy.block_id           = g_blk[blk_idx].id;
   cy.dir                = g_blk[blk_idx].dir;
   cy.anchor_type        = g_blk[blk_idx].block_type;
   cy.anchor_hi          = g_blk[blk_idx].hi;
   cy.anchor_lo          = g_blk[blk_idx].lo;
   cy.armed_time         = CloseTimeOf(g_m5[A].time, PERIOD_M5);
   cy.armed_index        = A;
   cy.state              = CY_ACTIVE;
   cy.closed_time        = 0;
   cy.session_start_time = g_sess.start_time;
   cy.drawn_mask         = 0;
   cy.logged_mask        = 0;
   cy.cisd_level         = 0.0;  cy.cisd_ref_time = 0;
   cy.cisd_run_from      = 0;    cy.cisd_run_to   = 0;
   cy.mss_level          = 0.0;  cy.mss_ref_time  = 0;
   cy.br_ref             = 0.0;  cy.br_ref_time   = 0;
   cy.br_break_index     = -1;   cy.br_active     = false;
   cy.bpr_id             = -1;
   cy.ctx_changed        = false;
   cy.anchor_invalidated = false;
   for(int m = 0; m < MDL_COUNT; m++)
     { cy.result[m] = MR_PENDING; cy.cfm_time[m] = 0; cy.cfm_price[m] = 0.0; }

   Cycle_FreezeCISDReference(cy, A);
   Cycle_FreezeMSSReference(cy, A);

   g_blk[blk_idx].state      = BLOCK_ARMED;
   g_blk[blk_idx].armed_time = cy.armed_time;
   g_blk[blk_idx].vis        = -1;
   if(InpLogSignals)                     // A-37 diagnostic, log only
      PrintFormat("HMI-ARM,%s,block=%I64d,sess=%I64d,dir=%d,bar=%s,inst=%s,run=%I64d,init=%d",
                  _Symbol, g_blk[blk_idx].id, g_blk[blk_idx].session_id,
                  g_blk[blk_idx].dir, DiagT(cy.armed_time), g_inst, g_run_id, g_init_seq);

   return(CycPush(cy));
  }

//--- shared confirmation sink: records the mark, never consumes any
//--- other model (Rule 44). Used by all four identification engines.
void ModelConfirm(IdentificationCycle &cy, const int m, const int n)
  {
   cy.result[m]    = MR_CONFIRMED;
   cy.cfm_time[m]  = g_m5[n].time;                       // bar the mark belongs to
   cy.cfm_price[m] = (cy.dir == DIR_BULL ? g_m5[n].low : g_m5[n].high);
   if(AlertEnabledFor(m))
      AlertPush(DirGlyph(cy.dir) + " " + ModelName(m) + "  cycle #" +
                IntegerToString(cy.cycle_id) + "  " +
                TimeToString(CloseTimeOf(g_m5[n].time, PERIOD_M5), TIME_DATE|TIME_MINUTES));
  }

//--- Rule 16: fully deterministic selection -------------------------
bool BlockBetter(const M5Block &a, const M5Block &b)
  {
   if(a.confirm_time != b.confirm_time) return(a.confirm_time > b.confirm_time);
   if(a.origin_time  != b.origin_time)  return(a.origin_time  > b.origin_time);
   double ma = (a.hi + a.lo) / 2.0, mb = (b.hi + b.lo) / 2.0;
   int d = Pts(ma, mb);
   if(d != 0) return(a.dir == DIR_BULL ? d < 0 : d > 0);
   return(a.id > b.id);                    // ids are monotonic: never undefined
  }

// Marks every legitimate touch on bar n and returns the block to ARM.
int M5TouchArbitrate(const int n)
  {
   datetime t = CloseTimeOf(g_m5[n].time, PERIOD_M5);
   int winner = -1;

   for(int i = 0; i < g_blk_n; i++)
     {
      BlockState st = g_blk[i].state;
      if(st != BLOCK_ACTIVE && st != BLOCK_CONFIRMED && st != BLOCK_TOUCHED) continue;
      if(g_blk[i].confirm_time > g_m5[n].time) continue;       // anti future-leak
      if(!RangesIntersect(g_m5[n].low, g_m5[n].high, g_blk[i].lo, g_blk[i].hi)) continue;

      if(g_blk[i].touched_time == 0) g_blk[i].touched_time = t;

      bool armable = (g_sess.active && g_blk[i].dir == g_sess.dir && st != BLOCK_CONFIRMED);

      // Phase 5 re-check (signed boundary 1, 2026-09-24): the block must
      // belong to THIS session and the session must still agree with the
      // CURRENT H4 direction. Phase 0b should already have ended any session
      // that fails this, and SessionExpireOpenBlocks any block that outlived
      // its session - so if this test is ever the one that says no, some
      // path around those two has been missed. It says so in the log rather
      // than quietly doing the right thing and hiding the hole.
      if(armable && (g_blk[i].session_id != g_sess.id || CtxDirection() != g_sess.dir))
        {
         armable = false;
         if(InpLogSignals)
            PrintFormat("HMI-GUARD,%s,ARMED_BLOCKED,block=%I64d,blk_sess=%I64d,sess=%I64d,sess_dir=%d,ctx_dir=%d,bar=%s,inst=%s,run=%I64d,init=%d",
                        _Symbol, g_blk[i].id, g_blk[i].session_id, g_sess.id,
                        g_sess.dir, CtxDirection(),
                        TimeToString(CloseTimeOf(g_m5[n].time, PERIOD_M5), TIME_DATE|TIME_MINUTES), g_inst, g_run_id, g_init_seq);
        }

      if(!armable)
        {
         if(st != BLOCK_TOUCHED) { g_blk[i].state = BLOCK_TOUCHED; g_blk[i].vis = -1; }
         continue;
        }
      if(winner < 0 || BlockBetter(g_blk[i], g_blk[winner]))
        {
         if(winner >= 0) { g_blk[winner].state = BLOCK_TOUCHED; g_blk[winner].vis = -1; }
         winner = i;
        }
      else
        { g_blk[i].state = BLOCK_TOUCHED; g_blk[i].vis = -1; }
     }
   return(winner);
  }

#endif // HMI_CYCLE_MQH
