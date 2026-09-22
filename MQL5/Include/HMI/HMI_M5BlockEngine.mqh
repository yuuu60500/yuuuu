//+------------------------------------------------------------------+
//| HMI_M5BlockEngine.mqh — refinement session, M5 OB, breaker       |
//| Nothing here may run before an H4 POI has actually been touched  |
//| (Rule 7).                                                        |
//+------------------------------------------------------------------+
#ifndef HMI_M5BLOCK_MQH
#define HMI_M5BLOCK_MQH
#include "HMI_H4POIEngine.mqh"

int BlockFindById(const long id)
  {
   for(int i = 0; i < g_blk_n; i++) if(g_blk[i].id == id) return(i);
   return(-1);
  }

int BlkPush(const M5Block &b)
  {
   int cap = MathMin(MAX_BLOCKS, MathMax(4, InpM5MaxBlocks));
   if(g_blk_n >= cap)
     {
      for(int i = 1; i < g_blk_n; i++) g_blk[i-1] = g_blk[i];
      g_blk_n--;
     }
   g_blk[g_blk_n] = b;
   g_blk_n++;
   return(g_blk_n - 1);
  }

//=================== refinement session =============================
void SessionExpireOpenBlocks()
  {
   for(int i = 0; i < g_blk_n; i++)
      if(g_blk[i].state == BLOCK_CANDIDATE || g_blk[i].state == BLOCK_CONFIRMED ||
         g_blk[i].state == BLOCK_ACTIVE    || g_blk[i].state == BLOCK_TOUCHED)
         g_blk[i].state = BLOCK_EXPIRED;
   g_brk_n = 0;
  }

void SessionEndNow(const SessionEnd reason, const datetime t)
  {
   if(!g_sess.active) return;
   g_sess.active     = false;
   g_sess.end_time   = t;
   g_sess.end_reason = reason;
   SessionExpireOpenBlocks();     // ARMED blocks / cycles are NOT touched (Rule 15)

   // A-06 (opt-in, default off): only a TIMEOUT may hand the POI back.
   // POI_INVALID / CONTEXT_FLIP / NEW_SESSION never re-arm.
   if(reason != SE_TIMEOUT || InpPOIMaxSessions <= 1) return;
   int pi = POIFindById(g_sess.poi_id);
   if(pi < 0) return;
   if(g_poi[pi].state != POI_TOUCHED || g_poi[pi].out_of_window) return;
   if(g_poi[pi].session_count >= InpPOIMaxSessions) return;
   g_poi[pi].awaiting_leave = true;
  }

void SessionStart(const int poi_idx, const int n)
  {
   if(!SafeIdx(poi_idx, g_poi_n)) return;
   if(g_sess.active) SessionEndNow(SE_NEW_SESSION, g_m5[n].time);
   g_sess.id          = g_next_id++;
   g_sess.poi_id      = g_poi[poi_idx].id;
   g_sess.dir         = g_poi[poi_idx].dir;
   g_sess.start_index = n;
   g_sess.start_time  = g_m5[n].time;
   g_sess.end_time    = 0;
   g_sess.end_reason  = SE_NONE;
   g_sess.active      = true;
   g_poi[poi_idx].session_count++;
  }

void SessionMaintain(const int n)
  {
   if(!g_sess.active) return;
   datetime t = CloseTimeOf(g_m5[n].time, PERIOD_M5);

   int pi = POIFindById(g_sess.poi_id);
   if(pi >= 0 && g_poi[pi].state == POI_INVALID)     // Spec 5.1: INVALIDATED only
     { SessionEndNow(SE_POI_INVALID, t); return; }

   if(CtxDirection() != DIR_NONE && CtxDirection() != g_sess.dir)
     { SessionEndNow(SE_CONTEXT_FLIP, t); return; }

   if(n - g_sess.start_index > InpM5RefinementMaxBars)
     { SessionEndNow(SE_TIMEOUT, t); return; }
  }

//=================== block creation =================================
bool BlockExists(const datetime origin_time, const int dir, const BlockType bt)
  {
   for(int i = 0; i < g_blk_n; i++)
      if(g_blk[i].origin_time == origin_time && g_blk[i].dir == dir && g_blk[i].block_type == bt)
         return(true);
   return(false);
  }

void BrkCandPush(const BreakerCand &c)
  {
   if(g_brk_n >= MAX_BRKCAND)
     {
      for(int i = 1; i < MAX_BRKCAND; i++) g_brk[i-1] = g_brk[i];
      g_brk_n = MAX_BRKCAND - 1;
     }
   g_brk[g_brk_n] = c;
   g_brk_n++;
  }

// Called on bar n with the M5 FVG (if any) completed by that bar.
void M5BlocksOnFVG(const int n, const int fvg_idx)
  {
   if(!g_sess.active || fvg_idx < 0 || !SafeIdx(fvg_idx, g_m5fvg_n)) return;

   int dir = g_m5fvg[fvg_idx].dir;
   int tol = PipsToPts(InpM5ConnectTolerancePips);

   //--- 1) plain M5 order block ------------------------------------
   int oldest = MathMax(0, n - InpM5OBtoFVGMaxBars);
   oldest = MathMax(oldest, g_sess.start_index - InpM5BlockLookbackFromTouch);  // D-3
   bool saw = false, made = false;

   for(int o = n - 1; o >= oldest; o--)
     {
      if(CandleDir(g_m5[o]) != -dir) continue;
      saw = true;
      if(!ConnectionValid(dir, g_m5[o].high, g_m5[o].low,
                          g_m5fvg[fvg_idx].hi, g_m5fvg[fvg_idx].lo, tol)) continue;
      if(BlockExists(g_m5[o].time, dir, BT_M5_OB)) { made = true; break; }

      M5Block b;
      b.id           = g_next_id++;
      b.dir          = dir;
      b.block_type   = BT_M5_OB;
      b.origin_time  = g_m5[o].time;
      b.confirm_time = g_m5fvg[fvg_idx].confirm_time;   // block exists only from here
      b.armed_time   = 0;
      b.touched_time = 0;
      b.invalid_time = 0;
      b.hi           = g_m5[o].high;                    // FULL OB (Rule 5)
      b.lo           = g_m5[o].low;
      // counter-direction blocks exist only as breaker material (CONF-06)
      b.state        = (dir == g_sess.dir ? BLOCK_ACTIVE : BLOCK_CONFIRMED);
      b.counter_dir  = (dir != g_sess.dir);
      b.session_id   = g_sess.id;
      b.src_block_id = -1;
      b.fvg_id       = g_m5fvg[fvg_idx].id;
      b.vis          = -1;
      BlkPush(b);
      made = true;
      break;
     }
   if(saw && !made) g_diag_blk_rejected_gap++;

   //--- 2) breaker block -------------------------------------------
   for(int c = 0; c < g_brk_n; c++)
     {
      if(g_brk[c].used || g_brk[c].dir != dir) continue;
      if(n - g_brk[c].break_index > InpM5OBtoFVGMaxBars) continue;
      if(!ConnectionValid(dir, g_brk[c].hi, g_brk[c].lo,
                          g_m5fvg[fvg_idx].hi, g_m5fvg[fvg_idx].lo, tol)) continue;
      if(BlockExists(g_brk[c].origin_time, dir, BT_M5_BREAKER)) { g_brk[c].used = true; continue; }

      M5Block b;
      b.id           = g_next_id++;
      b.dir          = dir;
      b.block_type   = BT_M5_BREAKER;
      b.origin_time  = g_brk[c].origin_time;
      b.confirm_time = g_m5fvg[fvg_idx].confirm_time;
      b.armed_time   = 0;
      b.touched_time = 0;
      b.invalid_time = 0;
      b.hi           = g_brk[c].hi;
      b.lo           = g_brk[c].lo;
      b.state        = (dir == g_sess.dir ? BLOCK_ACTIVE : BLOCK_CONFIRMED);
      b.counter_dir  = (dir != g_sess.dir);
      b.session_id   = g_sess.id;
      b.src_block_id = g_brk[c].src_block_id;
      b.fvg_id       = g_m5fvg[fvg_idx].id;
      b.vis          = -1;
      BlkPush(b);
      g_brk[c].used = true;
     }
  }

//=================== invalidation / breaker material ================
void M5BlockInvalidate(const int n)
  {
   datetime t  = CloseTimeOf(g_m5[n].time, PERIOD_M5);
   int      mp = MarginM5Pts(n);

   for(int i = 0; i < g_blk_n; i++)
     {
      BlockState st = g_blk[i].state;
      if(st != BLOCK_CONFIRMED && st != BLOCK_ACTIVE &&
         st != BLOCK_TOUCHED   && st != BLOCK_ARMED) continue;
      if(g_blk[i].confirm_time > g_m5[n].time) continue;

      bool dead = (g_blk[i].dir == DIR_BULL)
                  ? BreakDown(g_m5[n].close, g_blk[i].lo, mp)
                  : BreakUp  (g_m5[n].close, g_blk[i].hi, mp);
      if(!dead) continue;

      g_blk[i].state        = BLOCK_INVALID;
      g_blk[i].invalid_time = t;

      if(g_sess.active && g_blk[i].session_id == g_sess.id)
        {
         BreakerCand c;
         c.src_block_id = g_blk[i].id;
         c.dir          = -g_blk[i].dir;          // role reversal (Rule 11)
         c.hi           = g_blk[i].hi;
         c.lo           = g_blk[i].lo;
         c.origin_time  = g_blk[i].origin_time;
         c.break_index  = n;
         c.break_time   = t;
         c.used         = false;
         BrkCandPush(c);
        }
     }
  }

#endif // HMI_M5BLOCK_MQH
