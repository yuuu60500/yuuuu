//+------------------------------------------------------------------+
//| HMI_CycleManager.mqh — ARMED arbitration and cycle isolation     |
//| Every reference lives INSIDE the cycle struct, so an old cycle    |
//| cannot leak into a new one (Rule 15).                             |
//+------------------------------------------------------------------+
#ifndef HMI_CYCLE_MQH
#define HMI_CYCLE_MQH
#include "HMI_M5BlockEngine.mqh"

//--- Rule 19: freeze the CISD reference once, at ARMED --------------
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
   if(j < 0) { cy.result[MDL_CISD] = MR_NA; return; }

   int k2 = j;
   while(k2 - 1 >= lo && CandleDir(g_m5[k2-1]) == opp) k2--;

   cy.cisd_level    = g_m5[k2].open;      // OPEN of the OLDEST bar of the run
   cy.cisd_ref_time = g_m5[k2].time;
   cy.cisd_run_from = g_m5[k2].time;
   cy.cisd_run_to   = g_m5[j].time;
  }

//--- Rule 25 / 26 / 29: freeze the MSS reference once, at ARMED -----
void Cycle_FreezeMSSReference(IdentificationCycle &cy, const int A)
  {
   cy.mss_level    = 0.0;
   cy.mss_ref_time = 0;

   int W  = MathMax(5, InpSetupWindowBars);
   int lo = MathMax(0, A - W + 1);
   datetime armed_close = CloseTimeOf(g_m5[A].time, PERIOD_M5);
   int mp = MarginM5Pts(A);
   int want = cy.dir;                      // bull cycle -> swing HIGH

   for(int i = g_m5sw_n - 1; i >= 0; i--)
     {
      if(g_m5sw[i].bar_index < lo) break;                     // C2 window
      if(g_m5sw[i].dir != want) continue;                     // C3
      if(g_m5sw[i].confirm_time > armed_close) continue;      // C1 no future swing
      if(cy.dir == DIR_BULL && Pts(g_m5sw[i].price, g_m5[A].high) <= 0) continue;  // C4
      if(cy.dir == DIR_BEAR && Pts(g_m5sw[i].price, g_m5[A].low)  >= 0) continue;

      bool taken = false;                                     // C5 already consumed?
      for(int m = g_m5sw[i].bar_index + 1; m <= A && !taken; m++)
        {
         if(cy.dir == DIR_BULL && BreakUp  (g_m5[m].close, g_m5sw[i].price, mp)) taken = true;
         if(cy.dir == DIR_BEAR && BreakDown(g_m5[m].close, g_m5sw[i].price, mp)) taken = true;
        }
      if(taken) continue;

      cy.mss_level    = g_m5sw[i].price;
      cy.mss_ref_time = g_m5sw[i].bar_time;
      return;
     }
   cy.result[MDL_MSS] = MR_NA;             // bounded search failed: no MSS this cycle
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
            PrintFormat("HMI-GUARD,%s,ARMED_BLOCKED,block=%I64d,blk_sess=%I64d,sess=%I64d,sess_dir=%d,ctx_dir=%d,bar=%s",
                        _Symbol, g_blk[i].id, g_blk[i].session_id, g_sess.id,
                        g_sess.dir, CtxDirection(),
                        TimeToString(CloseTimeOf(g_m5[n].time, PERIOD_M5), TIME_DATE|TIME_MINUTES));
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
