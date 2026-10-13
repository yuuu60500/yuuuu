//+------------------------------------------------------------------+
//| HMI_H4ContextEngine.mqh — 4-state context machine (Rule 3)       |
//| CHOCH never flips the trend by itself: it only opens TRANSITION. |
//+------------------------------------------------------------------+
#ifndef HMI_H4CTX_MQH
#define HMI_H4CTX_MQH
#include "HMI_H4StructureEngine.mqh"

int CtxDirection()
  {
   if(g_ctx == CTX_BULLISH) return(DIR_BULL);
   if(g_ctx == CTX_BEARISH) return(DIR_BEAR);
   return(DIR_NONE);                   // RANGE / TRANSITION: no new setups
  }

void CtxEnter(const CtxState st, const int pending, const datetime t)
  {
   g_ctx         = st;
   g_ctx_pending = pending;
   g_ctx_time    = t;
   g_ctx_bars    = 0;
   g_ctx_messy   = false;   // BRI-06: quality is per context leg, like strength.
                            // The failed-transition branch sets it AFTER calling
                            // this, so the new leg is born carrying the mark.
  }

// Diagnostic only - never read by an engine, and emitted under a prefix of
// its own so the reload/repaint parser, which splits on HMI-BUILD, does not
// pick these up as mark rows. It makes the Context chain auditable the way
// HMI-REJECT made Rule 6's refusal side auditable: every state change comes
// out with the swing it broke and the state it left behind, so `str N` on the
// panel can be counted back from the log instead of taken on trust.
void CtxLogAt(const string kind, const string dir, const int h, const string sw_t, const string sw_p, const int also)
  {
   if(!InpLogSignals) return;
   PrintFormat("HMI-CTX,%s,%s,dir=%s,live=%d,ctx=%s,str=%d,messy=%d,bar=%s,swing=%s,swing_px=%s,close=%s,also=%d,inst=%s,run=%I64d,init=%d",
               _Symbol, kind, dir, (g_live ? 1 : 0),
               CtxName(g_ctx), g_ctx_strength, (g_ctx_messy ? 1 : 0),
               TimeToString(CloseTimeOf(g_h4[h].time, PERIOD_H4), TIME_DATE|TIME_MINUTES),
               sw_t, sw_p, DoubleToString(g_h4[h].close, _Digits), also, g_inst, g_run_id, g_init_seq);
  }

string SwT(const int i) { return(SafeIdx(i, g_h4sw_n) ? TimeToString(g_h4sw[i].bar_time, TIME_DATE|TIME_MINUTES) : ""); }
string SwP(const int i) { return(SafeIdx(i, g_h4sw_n) ? DoubleToString(g_h4sw[i].price, _Digits) : ""); }

void CtxLog(const string kind, const string dir, const int h, const int broken, const int also = 0)
  {
   CtxLogAt(kind, dir, h, SwT(broken), SwP(broken), also);
  }

// One row per de-duplicated bar: which swings were processed together with
// the primary. ReloadTest -Versus reads it to tell a BOS that v2.52 would
// have counted on a later bar (a suppressed duplicate) from any other
// difference (A-56).
void CtxDedupLog(const string kind, const string dir, const datetime t, const string prim_t, const string prim_p,
                 const int also, const string also_list)
  {
   if(also <= 0 || !InpLogSignals) return;
   PrintFormat("HMI-CTX-DEDUP,%s,%s,dir=%s,bar=%s,primary=%s@%s,also=%d,swings=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, kind, dir, TimeToString(t, TIME_DATE|TIME_MINUTES),
               (prim_t == "" ? "-" : prim_t), (prim_p == "" ? "-" : prim_p),
               also, also_list, g_inst, g_run_id, g_init_seq);
  }

//====================== BRI-12 (v2.54) ==============================
// protected_level decides when a trend's structure has failed (CHOCH);
// leg_anchor is the same candidate without the monotonic rule, logged for
// the scoring version and read by nothing here. Independent fields,
// independent rows, neither ever overwrites the other.
void ProtClear(HProtLevel &p)
  {
   p.valid        = false;
   p.price        = 0.0;
   p.swing_id     = 0;
   p.bar_index    = -1;
   p.swing_time   = 0;
   p.confirm_time = 0;
   p.bos_time     = 0;
  }

void ProtFromSwing(const int i, const datetime bos_t, HProtLevel &p)
  {
   ProtClear(p);
   if(!SafeIdx(i, g_h4sw_n)) return;
   p.valid        = true;
   p.price        = g_h4sw[i].price;
   p.swing_id     = g_h4sw[i].id;
   p.bar_index    = g_h4sw[i].bar_index;
   p.swing_time   = g_h4sw[i].bar_time;
   p.confirm_time = g_h4sw[i].confirm_time;
   p.bos_time     = bos_t;
  }

string ProtPx(const HProtLevel &p) { return(p.valid ? DoubleToString(p.price, _Digits) : "NA"); }

// HMI-PROT / HMI-ANCHOR: dir = the trend direction of the leg (UP: the
// level is a swing low). age = H4 bars from the swing bar to this bar.
void ProtLog(const string tag, const string ev, const int d, const int h,
             const HProtLevel &lv, const HProtLevel &prev, const HProtLevel &cand)
  {
   if(!InpLogSignals) return;
   PrintFormat("%s,%s,%s,dir=%s,live=%d,leg=%d,bar=%s,level=%s,swing=%s,confirm=%s,bos=%s,age=%d,prev=%s,cand=%s,inst=%s,run=%I64d,init=%d",
               tag, _Symbol, ev, (d == DIR_BULL ? "UP" : "DOWN"), (g_live ? 1 : 0), g_leg_seq,
               DiagT(CloseTimeOf(g_h4[h].time, PERIOD_H4)),
               ProtPx(lv), (lv.valid ? DiagT(lv.swing_time) : "-"),
               (lv.valid ? DiagT(lv.confirm_time) : "-"), (lv.valid ? DiagT(lv.bos_time) : "-"),
               (lv.valid && lv.bar_index >= 0 ? h - lv.bar_index : -1),
               ProtPx(prev), ProtPx(cand), g_inst, g_run_id, g_init_seq);
  }

// P-1 / P-2 / P-3: a BOS of direction d broke swing `primary` on bar h.
// leg_start: RANGE -> BOS, TRANS_OK, TRANS_FAIL - a new leg, nothing is
// inherited (the monotonic rule holds within one leg only).
void ProtOnBos(const int d, const int primary, const int h, const datetime t, const bool leg_start)
  {
   HProtLevel cand, nolv, prev;
   ProtClear(nolv);
   ProtFromSwing(H4ProtCandidate(d, primary, t), t, cand);
   if(leg_start)
     {
      g_leg_seq++;
      g_prot   = cand;
      g_anchor = cand;
      // no legal candidate and no older level: INVALID, structure sample insufficient
      ProtLog("HMI-PROT",   (cand.valid ? "SET" : "INVALID"), d, h, g_prot,   nolv, cand);
      ProtLog("HMI-ANCHOR", (cand.valid ? "SET" : "INVALID"), d, h, g_anchor, nolv, cand);
      return;
     }
   //--- protected_level: bull only moves up, bear only down; worse or no candidate keeps it
   prev = g_prot;
   if(!cand.valid)
      ProtLog("HMI-PROT", "KEEP_NONE", d, h, g_prot, nolv, cand);
   else if(!prev.valid)
     {
      g_prot = cand;
      ProtLog("HMI-PROT", "SET", d, h, g_prot, nolv, cand);
     }
   else if((d == DIR_BULL && Pts(cand.price, prev.price) > 0) ||
           (d == DIR_BEAR && Pts(cand.price, prev.price) < 0))
     {
      g_prot = cand;
      ProtLog("HMI-PROT", "ADVANCE", d, h, g_prot, prev, cand);
     }
   else
      ProtLog("HMI-PROT", "KEEP_WORSE", d, h, g_prot, nolv, cand);
   //--- leg_anchor: the same candidate, no monotonic rule
   prev = g_anchor;
   if(!cand.valid)
      ProtLog("HMI-ANCHOR", "KEEP_NONE", d, h, g_anchor, nolv, cand);
   else
     {
      g_anchor = cand;
      ProtLog("HMI-ANCHOR", (prev.valid ? "MOVE" : "SET"), d, h, g_anchor, prev, cand);
     }
  }

// The leg ends (CHOCH): ev = BREAK (protected broken) or FALLBACK (P-6b).
void ProtLeave(const string ev, const int d, const int h)
  {
   HProtLevel nolv;
   ProtClear(nolv);
   ProtLog("HMI-PROT",   ev,      d, h, g_prot,   nolv, nolv);
   ProtLog("HMI-ANCHOR", "RESET", d, h, g_anchor, nolv, nolv);
   ProtClear(g_prot);
   ProtClear(g_anchor);
  }

// P-4: a swing inside the leg broken by a close that did not break the
// protected level. Processed (it can never be "broken again" later), no
// state change, no strength change - one diagnostic row.
void InternalLog(const string dir, const int h, const int idx, const int also, const string also_list)
  {
   if(!InpLogSignals || !SafeIdx(idx, g_h4sw_n)) return;
   PrintFormat("HMI-CTX-INTERNAL,%s,dir=%s,live=%d,ctx=%s,bar=%s,swing=%s,swing_px=%s,close=%s,also=%d,swings=%s,prot=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, dir, (g_live ? 1 : 0), CtxName(g_ctx),
               DiagT(CloseTimeOf(g_h4[h].time, PERIOD_H4)),
               SwT(idx), SwP(idx), DoubleToString(g_h4[h].close, _Digits),
               also, also_list, ProtPx(g_prot), g_inst, g_run_id, g_init_seq);
  }

// One closed H4 bar while BULLISH / BEARISH (P-7): failure first, judged
// against the protected level as it stood BEFORE this bar; then the
// continuation BOS (which may move the level for the NEXT bar); then the
// internal swings.
CtxEventType H4TrendOnBar(const int h, const datetime t)
  {
   int    d  = CtxDirection();
   string vd = (d == DIR_BULL ? "UP" : "DOWN");
   string od = (d == DIR_BULL ? "DOWN" : "UP");
   string also_list = "";
   int    also = 0;

   //--- P-4: only an effective close beyond the protected level is a CHOCH,
   // and it switches to TRANSITION on this very bar
   if(g_prot.valid && H4CloseBreaks(h, -d, g_prot.price))
     {
      string pt = DiagT(g_prot.swing_time);
      string pp = DoubleToString(g_prot.price, _Digits);
      int pidx = H4SwingById(g_prot.swing_id);           // -1 once it left the swing window
      H4ConsumeSwing(pidx, t);
      also = H4ConsumeSameDirBroken(h, -d, pidx, t, also_list);
      CtxEnter(CTX_TRANSITION, -d, t);
      g_ctx_strength = 0;
      CtxLogAt("CHOCH", od, h, pt, pp, also);
      CtxDedupLog("CHOCH", od, t, pt, pp, also, also_list);
      ProtLeave("BREAK", d, h);
      return(d == DIR_BULL ? EV_CHOCH_DOWN : EV_CHOCH_UP);
     }

   //--- P-6b (boundary rule): this leg never had a legal protected level
   // (INVALID - structure sample insufficient). Its failure is judged by the
   // v2.53 rule: the latest confirmed, unprocessed opposite swing.
   if(!g_prot.valid)
     {
      int fi = H4DetectBreakDir(h, -d);
      if(fi >= 0)
        {
         H4ConsumeSwing(fi, t);
         also = H4ConsumeSameDirBroken(h, -d, fi, t, also_list);
         CtxEnter(CTX_TRANSITION, -d, t);
         g_ctx_strength = 0;
         CtxLog("CHOCH", od, h, fi, also);
         CtxDedupLog("CHOCH", od, t, SwT(fi), SwP(fi), also, also_list);
         ProtLeave("FALLBACK", d, h);
         return(d == DIR_BULL ? EV_CHOCH_DOWN : EV_CHOCH_UP);
        }
     }

   //--- continuation: BOS in the trend direction
   int bi = H4DetectBreakDir(h, d);
   if(bi >= 0)
     {
      H4ConsumeSwing(bi, t);
      also = H4ConsumeSameDirBroken(h, d, bi, t, also_list);
      g_ctx_strength++;
      CtxLog("BOS", vd, h, bi, also);
      CtxDedupLog("BOS", vd, t, SwT(bi), SwP(bi), also, also_list);
      ProtOnBos(d, bi, h, t, false);
      return(d == DIR_BULL ? EV_BOS_UP : EV_BOS_DOWN);
     }

   //--- P-4: an internal swing - processed, the trend stands
   int ii = H4DetectBreakDir(h, -d);
   if(ii >= 0)
     {
      H4ConsumeSwing(ii, t);
      also = H4ConsumeSameDirBroken(h, -d, ii, t, also_list);
      InternalLog(od, h, ii, also, also_list);
     }
   return(EV_NONE);
  }

// Classify the raw break for bar h and drive the state machine.
// Returns the classified event (for the trading-range engine).
CtxEventType H4ContextOnBar(const int h)
  {
   g_ctx_bars++;

   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);

   //--- timeout: a transition that never resolves becomes a range ---
   // (BRI-10 companion note: a break on the timeout bar itself is not judged
   // here; v2.49 tried that and v2.50 withdrew it pending its own version)
   if(g_ctx == CTX_TRANSITION && g_ctx_bars > InpH4TransitionMaxBars)
     {
      CtxEnter(CTX_RANGE, DIR_NONE, t);
      CtxLog("TIMEOUT", "-", h, -1);
      return(EV_TIMEOUT);
     }

   //--- BRI-12: a trend is judged against its own protected level ---
   if(g_ctx == CTX_BULLISH || g_ctx == CTX_BEARISH)
      return(H4TrendOnBar(h, t));

   //--- RANGE / TRANSITION: the latest confirmed, unprocessed swing ---
   int broken = -1;
   int brk = H4DetectBreak(h, broken);
   if(brk == DIR_NONE) return(EV_NONE);

   // P-5 (v2.54): a TRANSITION resolves - either way - only on structure
   // formed AND confirmed after the CHOCH. v2.53 checked the confirmation
   // of TRANS_OK only, so a swing formed on the CHOCH bar (confirmed later)
   // counted as new, and TRANS_FAIL accepted any pre-CHOCH swing.
   bool fresh = H4FreshAfter(broken, g_ctx_time);
   H4ConsumeSwing(broken, t);
   // A-33: the same close processes every other same-direction swing it
   // breaks - whatever the classification below, TRANS_SAMELEG included, so
   // none of them can be broken "again" by a later bar without a new push.
   string also_list = "";
   int    also      = H4ConsumeSameDirBroken(h, brk, broken, t, also_list);

   CtxEventType ev   = EV_NONE;
   string       kind = "";                       // diagnostic label only
   string       vdir = (brk == DIR_BULL ? "UP" : "DOWN");

   if(g_ctx == CTX_RANGE)
     {
      // no prevailing direction: the first break is a BOS
      if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
      else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
      g_ctx_strength = 1;
      kind = "BOS";
     }
   else if(!fresh)
     {
      // Rule 3 / P-5: old structure, whichever direction, resolves nothing.
      // Logged because "why did nothing happen here" is the hardest thing
      // to reconstruct later.
      ev = EV_NONE;
      kind = "TRANS_SAMELEG";
     }
   else if(brk == g_ctx_pending)
     {
      if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
      else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
      g_ctx_strength = 1;
      kind = "TRANS_OK";
     }
   else
     {
      // Transition failed: the original trend resumes - on NEW structure.
      // THIS is the "failed TRANSITION" the spec means by MESSY (docs/01
      // 202-204) - not the CHOCH that opened the transition, because a CHOCH
      // whose transition then succeeds is an ordinary reversal (A-25).
      if(brk == DIR_BULL) { ev = EV_BOS_UP;   CtxEnter(CTX_BULLISH, DIR_NONE, t); }
      else                { ev = EV_BOS_DOWN; CtxEnter(CTX_BEARISH, DIR_NONE, t); }
      g_ctx_strength = 1;
      g_ctx_messy    = true;
      kind = "TRANS_FAIL";
     }

   CtxLog(kind, vdir, h, broken, also);
   CtxDedupLog(kind, vdir, t, SwT(broken), SwP(broken), also, also_list);
   if(kind == "BOS" || kind == "TRANS_OK" || kind == "TRANS_FAIL")
      ProtOnBos(brk, broken, h, t, true);         // a new leg begins on this bar
   return(ev);
  }

#endif // HMI_H4CTX_MQH
