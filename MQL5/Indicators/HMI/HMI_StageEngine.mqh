//+------------------------------------------------------------------+
//| HMI_StageEngine.mqh — trend stage, reasons, strength arrow and    |
//| the six-row trend panel (v2.58, BRI-15).                          |
//| DISPLAY ONLY (Rule 69): no rule, mark or state reads it back. It  |
//| reads the strength / quality records and the context as they     |
//| stand after the bar and computes no score of its own.            |
//| docs/02 "BRI-15"; offline model tools/stage_sim.py.               |
//+------------------------------------------------------------------+
#ifndef HMI_STAGEENGINE_MQH
#define HMI_STAGEENGINE_MQH
#include "HMI_QualityEngine.mqh"

// Requirement §7 / §8 / §5.4 / §10 constants. Not inputs: the trading params
// digest stays as it was; every HMI-STG row carries STG_DEF.
#define STG_NEAR_K    56     // 56 dist <= T  <=>  dist <= 0.25 ATR14 (ATR14 = T / 14)
#define STG_EFF_LOW   35     // S_eff below this: price goes back and forth
#define STG_POS_STR   65     // a strength item counts as high from its top tier boundary ...
#define STG_POS_QLT   70     // ... a quality item from its
#define STG_ARR_BARS  3      // arrow: the score 3 H4 bars earlier, same leg
#define STG_ARR_DELTA 5      //        displayed scores 5 apart
#define STG_DEF       "STG1-NEAR25-DEEP2.3-EFF35-POS65.70-ARR3.5"

#define SG_NODATA     0      // stages, in the priority order of requirement §7
#define SG_NOATR      1
#define SG_TRANS      2
#define SG_RANGE      3
#define SG_BUILD      4
#define SG_DEEP       5
#define SG_PUSH       6
#define SG_CONSOL     7
#define SG_PULLBACK   8
#define SG_COUNT      9

#define RS_PROT_BROKEN  0    // reasons (HMI-STG-HIST counts them in this order)
#define RS_SWING_BROKEN 1
#define RS_TIMEOUT      2
#define RS_NO_PROT      3
#define RS_LEG          4
#define RS_DEEP         5
#define RS_BRK_FAIL     6
#define RS_COUNTER      7
#define RS_CHOP         8
#define RS_MOVE         9
#define RS_RET          10
#define RS_BRK          11
#define RS_EFF          12
#define RS_MOM          13
#define RS_OVL          14
#define RS_COUNT        15

#define AR_NA         0      // strength arrow
#define AR_UP         1
#define AR_DOWN       2
#define AR_FLAT       3
#define AR_NEW        4

#define CK_NONE       0      // how a TRANSITION opened / a RANGE began
#define CK_BREAK      1
#define CK_FALLBACK   2
#define CK_TIMEOUT    3
#define CK_INIT       4

struct StgRec
  {
   int      stage;
   int      rs[2];            // reasons, rn of them
   int      rn;
   int      dir;              // +1 / -1 / 0
   int      pend;             // TRANSITION's pending direction, else 0
   int      chk;              // CK_*
   int      prot;             // trend: 1 / 0 = protected level valid; -1 outside a trend
   bool     has_x;            // trend with the quality record's retrace items
   bool     has_prev;         // a bar between the anchor and h
   double   prev_px;          // the leg's extreme over bars a+1 .. h-1
   double   bar_px;           // bar h's high (bull) / low (bear)
   long     dist;             // D x (ext - close), points, not clamped
   int      refresh;          // 1 / 0; -1 = NA
   int      near_;            // 1 / 0; -1 = NA
   int      arrow;
   int      ref_score;        // the strength score of h - 3; -1 = NA
  };

StgRec   g_stg[];                // one record per PROCESSED H4 bar, index = H4 index
int      g_stg_n          = 0;
int      g_stg_trans_kind = CK_NONE;  // how the current TRANSITION opened (kept while it lasts)
bool     g_stg_prot_prev  = false;    // g_prot.valid after the previous bar (the level the CHOCH was judged against)

void StgReset()
  {
   g_stg_n          = 0;
   g_stg_trans_kind = CK_NONE;
   g_stg_prot_prev  = false;
   ArrayResize(g_stg, 0, 512);
  }

//--- the strength items as integers (HMI_StrengthEngine.mqh): m / 3T, e / path, q / T
void StgStrItems(const StrRec &s, long &m, long &e, long &q)
  {
   m = StrMin(StrMax(STR_ATR_N * s.net, 0), STR_MOVE_ATR * s.trsum);
   e = StrMin(StrMax(s.net, 0), s.path);
   q = StrMin(StrMax(STR_ATR_N * s.recent, 0), STR_MOM_ATR * s.trsum);
  }

void StgAdd(StgRec &r, const int code)
  {
   if(r.rn < 2) { r.rs[r.rn] = code;  r.rn++; }
  }

void StgLog(const int h);

//--- the stage of H4 bar h (called right after QltOnH4Bar: same point in build and live, Rule 51) ---
void StgOnH4Bar(const int h)
  {
   if(h < 0 || h >= g_h4_n) return;
   if(ArraySize(g_stg) < h + 1) ArrayResize(g_stg, h + 1, 512);
   StrRec s = g_str[h];
   QltRec q = g_qlt[h];
   datetime t = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   // a TRANSITION entered on this bar: P-4 when the leg had a protected level, else P-6b
   if(g_ctx == CTX_TRANSITION && g_ctx_time == t)
      g_stg_trans_kind = (g_stg_prot_prev ? CK_BREAK : CK_FALLBACK);

   StgRec r;
   ZeroMemory(r);
   r.prot = -1;  r.refresh = -1;  r.near_ = -1;  r.arrow = AR_NA;  r.ref_score = -1;
   int d = (g_ctx == CTX_BULLISH ? 1 : (g_ctx == CTX_BEARISH ? -1 : 0));
   r.dir  = d;
   r.pend = (g_ctx == CTX_TRANSITION ? g_ctx_pending : 0);
   r.chk  = (g_ctx == CTX_TRANSITION ? g_stg_trans_kind
                                     : (g_ctx == CTX_RANGE ? (g_ctx_time != 0 ? CK_TIMEOUT : CK_INIT) : CK_NONE));
   if(d != 0) r.prot = (g_prot.valid ? 1 : 0);

   //--- arrow (§5.4): displayed scores 3 bars apart, the same leg, both scored
   if(s.state == STR_OK)
     {
      bool ref_ok = (h >= STG_ARR_BARS && g_str[h - STG_ARR_BARS].state == STR_OK);
      if(ref_ok) r.ref_score = g_str[h - STG_ARR_BARS].score;
      if(!ref_ok || g_str[h - STG_ARR_BARS].leg != s.leg)
         r.arrow = AR_NEW;
      else
        {
         int dl = s.score - r.ref_score;
         r.arrow = (dl >= STG_ARR_DELTA ? AR_UP : (dl <= -STG_ARR_DELTA ? AR_DOWN : AR_FLAT));
        }
     }

   //--- the extreme this bar is judged against (the quality record's leg from leg_anchor)
   if(d != 0 && q.has_x)
     {
      int a = q.anchor_bar;
      r.has_x    = true;
      r.bar_px   = (d == 1 ? g_h4[h].high : g_h4[h].low);
      r.has_prev = (a + 1 <= h - 1);
      if(r.has_prev)
        {
         double e = (d == 1 ? g_h4[a+1].high : g_h4[a+1].low);
         for(int i = a + 2; i <= h - 1; i++)
            e = (d == 1 ? MathMax(e, g_h4[i].high) : MathMin(e, g_h4[i].low));
         r.prev_px = e;
        }
      r.dist    = d * StrL(q.ext_px, g_h4[h].close);
      r.refresh = (r.has_prev && d * StrL(r.bar_px, r.prev_px) > 0 ? 1 : 0);
      if(s.trsum > 0) r.near_ = (STG_NEAR_K * r.dist <= s.trsum ? 1 : 0);
     }

   //--- the stage (§7), the first that holds
   if(s.state == STR_NODATA)
      r.stage = (s.reason == SR_HISTORY ? SG_NODATA : SG_NOATR);
   else if(g_ctx == CTX_TRANSITION)
     {
      r.stage = SG_TRANS;
      if(r.chk == CK_BREAK)    StgAdd(r, RS_PROT_BROKEN);
      if(r.chk == CK_FALLBACK) StgAdd(r, RS_SWING_BROKEN);
     }
   else if(g_ctx == CTX_RANGE)
     {
      r.stage = SG_RANGE;
      if(r.chk == CK_TIMEOUT) StgAdd(r, RS_TIMEOUT);
     }
   else
     {
      if(r.prot != 1)       { r.stage = SG_BUILD;  StgAdd(r, RS_NO_PROT); }
      else if(!q.has_x)     { r.stage = SG_BUILD;  StgAdd(r, RS_LEG); }
      else if(3 * q.x > 2 * q.leg)            r.stage = SG_DEEP;
      else if(r.refresh == 1 && r.near_ == 1) r.stage = SG_PUSH;
      else if(r.near_ == 1)                   r.stage = SG_CONSOL;
      else                                    r.stage = SG_PULLBACK;
      //--- reasons (§8): risks in order, strengths only when nothing else applies
      long m = 0, e = 0, qm = 0;
      StgStrItems(s, m, e, qm);
      int  before = r.rn;
      bool risk = false;
      if(q.has_x && 3 * q.x > 2 * q.leg)                    { StgAdd(r, RS_DEEP);     risk = true; }
      if(q.fail > 0)                                        { StgAdd(r, RS_BRK_FAIL); risk = true; }
      if(qm == 0 && s.recent < 0)                           { StgAdd(r, RS_COUNTER);  risk = true; }
      if(s.path > 0 && 100 * e < STG_EFF_LOW * s.path)      { StgAdd(r, RS_CHOP);     risk = true; }
      if(before == 0 && !risk)
        {
         if(100 * m >= STG_POS_STR * STR_MOVE_ATR * s.trsum)                StgAdd(r, RS_MOVE);
         if(q.has_x && q.num_r >= STG_POS_QLT * q.leg)                      StgAdd(r, RS_RET);
         if(q.n >= QLT_EV_MIN && q.s == q.n)                                StgAdd(r, RS_BRK);
         if(s.path > 0 && 100 * e >= STG_POS_STR * s.path)                  StgAdd(r, RS_EFF);
         if(100 * qm >= STG_POS_STR * STR_MOM_ATR * s.trsum)                StgAdd(r, RS_MOM);
         if(100 * (11 * (long)QLT_FP - q.so) >= STG_POS_QLT * 11 * (long)QLT_FP) StgAdd(r, RS_OVL);
        }
     }
   g_stg[h] = r;
   g_stg_n  = h + 1;
   g_stg_prot_prev = g_prot.valid;
   StgLog(h);
  }

string StgStageName(const int s)
  {
   switch(s)
     {
      case SG_NODATA:   return("NODATA");
      case SG_NOATR:    return("NOATR");
      case SG_TRANS:    return("TRANS");
      case SG_RANGE:    return("RANGE");
      case SG_BUILD:    return("BUILD");
      case SG_DEEP:     return("DEEP");
      case SG_PUSH:     return("PUSH");
      case SG_CONSOL:   return("CONSOL");
     }
   return("PULLBACK");
  }

string StgReasonName(const int c)
  {
   switch(c)
     {
      case RS_PROT_BROKEN:  return("PROT_BROKEN");
      case RS_SWING_BROKEN: return("SWING_BROKEN");
      case RS_TIMEOUT:      return("TIMEOUT");
      case RS_NO_PROT:      return("NO_PROT");
      case RS_LEG:          return("LEG");
      case RS_DEEP:         return("DEEP");
      case RS_BRK_FAIL:     return("BRK_FAIL");
      case RS_COUNTER:      return("COUNTER");
      case RS_CHOP:         return("CHOP");
      case RS_MOVE:         return("MOVE");
      case RS_RET:          return("RET");
      case RS_BRK:          return("BRK");
      case RS_EFF:          return("EFF");
      case RS_MOM:          return("MOM");
     }
   return("OVL");
  }

string StgArrowName(const int a)
  {
   return(a == AR_UP ? "UP" : (a == AR_DOWN ? "DOWN" : (a == AR_FLAT ? "FLAT" : (a == AR_NEW ? "NEW" : "NA"))));
  }

string StgChkName(const int c)
  {
   return(c == CK_BREAK ? "BREAK" : (c == CK_FALLBACK ? "FALLBACK" : (c == CK_TIMEOUT ? "TIMEOUT" : (c == CK_INIT ? "INIT" : "-"))));
  }

string StgReasons(const StgRec &r)
  {
   string out = "";
   for(int i = 0; i < r.rn; i++) out += (i > 0 ? "+" : "") + StgReasonName(r.rs[i]);
   return(out == "" ? "-" : out);
  }

string StgFlag(const int v) { return(v < 0 ? "NA" : IntegerToString(v)); }

//--- one row per H4 bar: live, or in a build the bars that close inside the M5 window (as HMI-STR / HMI-QLT) ---
void StgLog(const int h)
  {
   if(!InpLogSignals) return;
   datetime bar = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   if(!g_live && (g_m5_n <= 0 || bar <= g_m5[0].time)) return;
   StgRec r = g_stg[h];
   StrRec s = g_str[h];
   QltRec q = g_qlt[h];
   bool arr = (r.arrow != AR_NA);
   PrintFormat("HMI-STG,%s,live=%d,bar=%s,ctx=%s,stage=%s,reasons=%s,def=%s,dir=%d,pend=%s,chk=%s,prot=%s," +
               "anchor_bar=%s,prev_ext=%s,bar_ext=%s,ext=%s,close=%s,dist_pts=%s,tr_sum=%s,refresh=%s,near=%s," +
               "arrow=%s,ref_bar=%s,ref_score=%s,score=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, (g_live ? 1 : 0), TimeToString(bar, TIME_DATE|TIME_MINUTES), CtxName(g_ctx),
               StgStageName(r.stage), StgReasons(r), STG_DEF, r.dir,
               (r.pend == 1 ? "UP" : (r.pend == -1 ? "DOWN" : "-")), StgChkName(r.chk), StgFlag(r.prot),
               (r.has_x ? TimeToString(g_h4[q.anchor_bar].time, TIME_DATE|TIME_MINUTES) : "-"),
               (r.has_x && r.has_prev ? QltPx(r.prev_px) : "NA"), (r.has_x ? QltPx(r.bar_px) : "NA"),
               (r.has_x ? QltPx(q.ext_px) : "NA"), QltPx(g_h4[h].close),
               (r.has_x ? IntegerToString(r.dist) : "NA"),
               (s.reason != SR_HISTORY ? IntegerToString(s.trsum) : "NA"),
               StgFlag(r.refresh), StgFlag(r.near_), StgArrowName(r.arrow),
               (arr && h >= STG_ARR_BARS ? StrBarTime(h - STG_ARR_BARS) : "-"), StgFlag(r.ref_score),
               (s.state == STR_OK ? IntegerToString(s.score) : "NA"), g_inst, g_run_id, g_init_seq);
  }

//--- build end: the whole processed H4 window (as HMI-STR-HIST / HMI-QLT-HIST) ---
void StgLogHist()
  {
   if(!InpLogSignals) return;
   int sg[SG_COUNT], rc[RS_COUNT], ac[5];
   ArrayInitialize(sg, 0);
   ArrayInitialize(rc, 0);
   ArrayInitialize(ac, 0);
   for(int h = 0; h < g_stg_n; h++)
     {
      sg[g_stg[h].stage]++;
      for(int i = 0; i < g_stg[h].rn; i++) rc[g_stg[h].rs[i]]++;
      ac[g_stg[h].arrow]++;
     }
   string rs = "";
   for(int i = 0; i < RS_COUNT; i++) rs += (i > 0 ? ";" : "") + IntegerToString(rc[i]);
   PrintFormat("HMI-STG-HIST,%s,live=0,def=%s,from=%s,to=%s,bars=%d,nodata=%d,noatr=%d,trans=%d,range=%d,build=%d,deep=%d," +
               "push=%d,consol=%d,pullback=%d,rs=%s,up=%d,down=%d,flat=%d,new=%d,inst=%s,run=%I64d,init=%d",
               _Symbol, STG_DEF,
               (g_stg_n > 0 ? StrBarTime(0) : "-"), (g_stg_n > 0 ? StrBarTime(g_stg_n - 1) : "-"), g_stg_n,
               sg[SG_NODATA], sg[SG_NOATR], sg[SG_TRANS], sg[SG_RANGE], sg[SG_BUILD], sg[SG_DEEP], sg[SG_PUSH],
               sg[SG_CONSOL], sg[SG_PULLBACK], rs, ac[AR_UP], ac[AR_DOWN], ac[AR_FLAT], ac[AR_NEW],
               g_inst, g_run_id, g_init_seq);
  }

//====================== panel text (display) =========================
// Same wording as stage_sim.panel_rows / items_rows. Chinese as \uXXXX (HMI_U).
#define ZH_LAB_DIR       "H4 \\u8D8B\\u52BF"                                 // H4 趋势
#define ZH_LAB_STAGE     "\\u5F53\\u524D\\u9636\\u6BB5"                      // 当前阶段
#define ZH_LAB_WHY       "\\u4E3B\\u8981\\u539F\\u56E0"                      // 主要原因
#define ZH_UP_TRI        "\\u25B2"                                           // ▲
#define ZH_DN_TRI        "\\u25BC"                                           // ▼
#define ZH_BULL          "\\u591A\\u5934"                                    // 多头
#define ZH_BEAR          "\\u7A7A\\u5934"                                    // 空头
#define ZH_TRANS_HEAD    "\\u8FC7\\u6E21"                                    // 过渡
#define ZH_PEND_UP       "\\u504F\\u591A\\u5F85\\u786E\\u8BA4"               // 偏多待确认
#define ZH_PEND_DN       "\\u504F\\u7A7A\\u5F85\\u786E\\u8BA4"               // 偏空待确认
#define ZH_SERVER        "\\uFF08\\u670D\\u52A1\\u5668\\u65F6\\u95F4\\uFF09" // （服务器时间）
#define ZH_ARR_UP        "\\u2191"                                           // ↑
#define ZH_ARR_DN        "\\u2193"                                           // ↓
#define ZH_ARR_FLAT      "\\u2192"                                           // →
#define ZH_ARR_NEW       "\\u65B0\\u8D8B\\u52BF"                             // 新趋势
#define ZH_DASH          "\\u2014"                                           // —
#define ZH_SG_BUILD      "\\u7ED3\\u6784\\u5F85\\u5B8C\\u5584"               // 结构待完善
#define ZH_SG_DEEP       "\\u6DF1\\u5EA6\\u56DE\\u64A4"                      // 深度回撤
#define ZH_SG_PUSH       "\\u5EF6\\u7EED\\u63A8\\u8FDB"                      // 延续推进
#define ZH_SG_HIGH       "\\u9AD8\\u4F4D\\u6574\\u7406"                      // 高位整理
#define ZH_SG_LOW        "\\u4F4E\\u4F4D\\u6574\\u7406"                      // 低位整理
#define ZH_SG_PULL       "\\u6B63\\u5E38\\u56DE\\u64A4"                      // 正常回撤
#define ZH_R_BULLPROT    "\\u591A\\u5934\\u4FDD\\u62A4\\u4F4E\\u70B9\\u5DF2\\u7834" // 多头保护低点已破
#define ZH_R_BEARPROT    "\\u7A7A\\u5934\\u4FDD\\u62A4\\u9AD8\\u70B9\\u5DF2\\u7834" // 空头保护高点已破
#define ZH_R_BULLSW      "\\u591A\\u5934\\u4F4E\\u70B9\\u5DF2\\u7834"        // 多头低点已破
#define ZH_R_BEARSW      "\\u7A7A\\u5934\\u9AD8\\u70B9\\u5DF2\\u7834"        // 空头高点已破
#define ZH_R_NOPROT_SFX  "\\uFF08\\u65E0\\u4FDD\\u62A4\\u70B9\\uFF09"        // （无保护点）
#define ZH_R_TIMEOUT_A   "\\u8FC7\\u6E21\\u8D85"                             // 过渡超
#define ZH_R_TIMEOUT_B   "\\u6839\\u672A\\u786E\\u8BA4"                      // 根未确认
#define ZH_R_NOPROT      "\\u7F3A\\u5C11\\u4FDD\\u62A4\\u70B9"               // 缺少保护点
#define ZH_R_DEEP        "\\u56DE\\u64A4\\u504F\\u6DF1"                      // 回撤偏深
#define ZH_R_BRKFAIL     "\\u8FD1\\u671F\\u7A81\\u7834\\u5931\\u8D25"        // 近期突破失败
#define ZH_R_COUNTER     "\\u8FD1\\u671F\\u9006\\u5411\\u8FD0\\u884C"        // 近期逆向运行
#define ZH_R_CHOP        "\\u4EF7\\u683C\\u5F80\\u8FD4\\u660E\\u663E"        // 价格往返明显
#define ZH_R_MOVE        "\\u540C\\u5411\\u63A8\\u8FDB\\u660E\\u663E"        // 同向推进明显
#define ZH_R_RET         "\\u56DE\\u64A4\\u8F83\\u6D45"                      // 回撤较浅
#define ZH_R_BRK         "\\u7A81\\u7834\\u5168\\u90E8\\u5B88\\u4F4F"        // 突破全部守住
#define ZH_R_EFF         "\\u63A8\\u8FDB\\u6548\\u7387\\u9AD8"               // 推进效率高
#define ZH_R_MOM         "\\u8FD1\\u671F\\u63A8\\u8FDB\\u6709\\u529B"        // 近期推进有力
#define ZH_R_OVL         "K \\u7EBF\\u91CD\\u53E0\\u5C11"                    // K 线重叠少
#define ZH_R_NONE        "\\u65E0\\u7A81\\u51FA\\u5206\\u9879"               // 无突出分项
#define ZH_STR_ITEMS     "\\u5F3A\\u5EA6\\u5206\\u9879"                      // 强度分项
#define ZH_QLT_ITEMS     "\\u8D28\\u91CF\\u5206\\u9879"                      // 质量分项
#define ZH_I_MOVE        "\\u51C0\\u63A8\\u8FDB"                             // 净推进
#define ZH_I_EFF         "\\u6548\\u7387"                                    // 效率
#define ZH_I_MOM         "\\u52A8\\u91CF"                                    // 动量
// v2.58r4: the compact panels
#define ZH_BAR           "\\uFF5C"                                           // ｜
#define ZH_WHY_SHORT     "\\u539F\\u56E0"                                    // 原因
#define ZH_LEAN_UP       "\\u504F\\u591A"                                    // 偏多
#define ZH_LEAN_DN       "\\u504F\\u7A7A"                                    // 偏空
#define ZH_M5_TRACK      "\\u8DDF\\u8E2A\\u4E2D"                             // 跟踪中
#define ZH_M5_IDLE       "\\u672A\\u8DDF\\u8E2A"                             // 未跟踪
#define ZH_M5_FROM       "\\u8D77"                                           // 起
#define ZH_M5_DONE       "\\u5DF2\\u786E\\u8BA4"                             // 已确认
#define ZH_M5_ITEM       "\\u9879"                                           // 项
#define ZH_M5_ANCHOR     "\\u951A\\u70B9\\u5931\\u6548"                      // 锚点失效
#define ZH_M5_CTX        "H4 \\u8D8B\\u52BF\\u5DF2\\u53D8"                   // H4 趋势已变
#define ZH_M5_POI        "H4 POI \\u5DF2\\u89E6\\u53CA"                      // H4 POI 已触及
#define ZH_M5_WAITBLK    "\\u7B49\\u5F85 M5 \\u533A\\u5757"                  // 等待 M5 区块
#define ZH_M5_WAITPOI    "\\u7B49\\u5F85\\u4EF7\\u683C\\u89E6\\u53CA H4 POI" // 等待价格触及 H4 POI
#define ZH_M5_PAUSE      "H4 \\u975E\\u8D8B\\u52BF\\uFF0C\\u6682\\u505C\\u65B0\\u8DDF\\u8E2A" // H4 非趋势，暂停新跟踪
#define ZH_COLON         "\\uFF1A"                                           // ：
#define ZH_ADR_TODAY     "\\u4ECA\\u65E5\\u6CE2\\u5E45\\u5360 ADR"           // 今日波幅占 ADR
#define ZH_ADR_LEFT      "\\u5269\\u4F59"                                    // 剩余
#define ZH_ADR_EXH       "\\u5DF2\\u7528\\u5C3D"                             // 已用尽
#define ZH_LIQ_WAIT      "\\u6D41\\u52A8\\u6027\\u5386\\u53F2\\u7B49\\u5F85\\u4E2D\\uFF0C\\u6D41\\u52A8\\u6027\\u7EBF\\u6682\\u5B9A" // 流动性历史等待中，流动性线暂定

#define PC_BASE   0              // the trend panel's row colours (resolved in HMI_ObjectManager)
#define PC_BULL   1
#define PC_BEAR   2
#define PC_TRANS  3
#define PC_RANGE  4
#define PC_HIGH   5              // v2.58r3: strength / quality rows by tier (强 / 良好, 中等 / 一般, 弱 / 较差)
#define PC_MID    6
#define PC_LOW    7
#define PC_LAB    8              // v2.58r4: a compact row's label words (强度 / 质量 / 原因 / ｜) in the label colour

string StgStageZh(const StgRec &r)
  {
   switch(r.stage)
     {
      case SG_NODATA: return(HMI_U(ZH_FEW));
      case SG_NOATR:  return(HMI_U(ZH_NA));
      case SG_TRANS:  return(HMI_U(ZH_TRANS));
      case SG_RANGE:  return(HMI_U(ZH_RANGE));
      case SG_BUILD:  return(HMI_U(ZH_SG_BUILD));
      case SG_DEEP:   return(HMI_U(ZH_SG_DEEP));
      case SG_PUSH:   return(HMI_U(ZH_SG_PUSH));
      case SG_CONSOL: return(HMI_U(r.dir == 1 ? ZH_SG_HIGH : ZH_SG_LOW));
     }
   return(HMI_U(ZH_SG_PULL));
  }

string StgReasonZh(const int c, const StgRec &r)
  {
   switch(c)
     {
      case RS_PROT_BROKEN:  return(HMI_U(r.pend == -1 ? ZH_R_BULLPROT : ZH_R_BEARPROT));
      case RS_SWING_BROKEN: return(HMI_U(r.pend == -1 ? ZH_R_BULLSW : ZH_R_BEARSW) + HMI_U(ZH_R_NOPROT_SFX));
      case RS_TIMEOUT:      return(HMI_U(ZH_R_TIMEOUT_A) + " " + IntegerToString(InpH4TransitionMaxBars) + " " + HMI_U(ZH_R_TIMEOUT_B));
      case RS_NO_PROT:      return(HMI_U(ZH_R_NOPROT));
      case RS_LEG:          return(HMI_U(ZH_LEGBAD));
      case RS_DEEP:         return(HMI_U(ZH_R_DEEP));
      case RS_BRK_FAIL:     return(HMI_U(ZH_R_BRKFAIL));
      case RS_COUNTER:      return(HMI_U(ZH_R_COUNTER));
      case RS_CHOP:         return(HMI_U(ZH_R_CHOP));
      case RS_MOVE:         return(HMI_U(ZH_R_MOVE));
      case RS_RET:          return(HMI_U(ZH_R_RET));
      case RS_BRK:          return(HMI_U(ZH_R_BRK));
      case RS_EFF:          return(HMI_U(ZH_R_EFF));
      case RS_MOM:          return(HMI_U(ZH_R_MOM));
     }
   return(HMI_U(ZH_R_OVL));
  }

//--- the strength / quality values of the trend panel -------------------
string StgStrengthValue(const StrRec &s, const int arrow, const bool wait)
  {
   if(wait)
     {
      if(s.state != STR_OK) return(HMI_U(ZH_WAIT));
      return(HMI_U(ZH_WAIT) + HMI_U(ZH_LP) + HMI_U(ZH_LASTOK) + " " + StrTierZh(s.tier) + " " + HMI_U(ZH_DOT) + " " +
             IntegerToString(s.score) + "/100" + HMI_U(ZH_RP));
     }
   if(s.state == STR_NODATA)
      return(s.reason == SR_HISTORY ? HMI_U(ZH_FEW) + HMI_U(ZH_LP) + HMI_U(ZH_FEW15) + HMI_U(ZH_RP)
                                    : HMI_U(ZH_NA) + HMI_U(ZH_LP) + HMI_U(ZH_ATRBAD) + HMI_U(ZH_RP));
   if(s.state == STR_NODIR) return(HMI_U(ZH_NORATE));
   string a = (arrow == AR_UP ? ZH_ARR_UP : (arrow == AR_DOWN ? ZH_ARR_DN : (arrow == AR_FLAT ? ZH_ARR_FLAT : ZH_ARR_NEW)));
   return(StrTierZh(s.tier) + " " + HMI_U(ZH_DOT) + " " + IntegerToString(s.score) + "/100 " + HMI_U(a));
  }

string StgQualityValue(const QltRec &q, const bool wait)
  {
   if(wait)
     {
      if(q.state != QLT_OK) return(HMI_U(ZH_WAIT));
      return(HMI_U(ZH_WAIT) + HMI_U(ZH_LP) + HMI_U(ZH_LASTOK) + " " + QltTierZh(q.tier) + " " + HMI_U(ZH_DOT) + " " +
             IntegerToString(q.score) + "/100" + HMI_U(ZH_RP));
     }
   if(q.state == QLT_NODATA) return(HMI_U(ZH_FEW) + HMI_U(ZH_LP) + HMI_U(ZH_FEW12) + HMI_U(ZH_RP));
   if(q.state == QLT_NODIR)  return(HMI_U(ZH_NORATE));
   if(q.state == QLT_PARTIAL)
      return(HMI_U((q.reason & QR_FEW) != 0 ? ZH_FEW : ZH_NA) + HMI_U(ZH_LP) + QltWhy(q) + HMI_U(ZH_RP) +
             "  " + HMI_U(ZH_LOCAL) + " " + QltLocal(q, " " + HMI_U(ZH_DOT) + " "));
   return(QltTierZh(q.tier) + " " + HMI_U(ZH_DOT) + " " + IntegerToString(q.score) + "/100" + HMI_U(ZH_LP) +
          (q.sample == QS_FIVE ? "5 " + HMI_U(ZH_TIMES_EV)
                               : HMI_U(ZH_LOWSMP) + " " + IntegerToString(q.n) + " " + HMI_U(ZH_TIMES_BRK)) + HMI_U(ZH_RP));
  }

// the reasons row: at most two, 无突出分项 in a trend without one, — outside a trend
string StgWhyText(const StgRec &r)
  {
   string why = "";
   for(int i = 0; i < r.rn; i++) why += (i > 0 ? HMI_U(ZH_COMMA) : "") + StgReasonZh(r.rs[i], r);
   if(why == "") why = HMI_U(r.dir != 0 ? ZH_R_NONE : ZH_DASH);
   return(why);
  }

//--- PANEL_FULL's trend panel (requirement §2): labels, values, colour keys. v2.58r4: five rows -
// the 数据截至 row is gone from both modes (the bar time stays in every HMI-STR / QLT / STG row)
#define STG_FULL_ROWS 5

void StgPanelRows(string &lab[], string &val[], int &ck[])
  {
   ArrayResize(lab, STG_FULL_ROWS);  ArrayResize(val, STG_FULL_ROWS);  ArrayResize(ck, STG_FULL_ROWS);
   lab[0] = HMI_U(ZH_LAB_DIR);   lab[1] = HMI_U(ZH_STRENGTH);  lab[2] = HMI_U(ZH_QUALITY);
   lab[3] = HMI_U(ZH_LAB_STAGE); lab[4] = HMI_U(ZH_LAB_WHY);
   for(int i = 0; i < STG_FULL_ROWS; i++) ck[i] = PC_BASE;
   int h = g_stg_n - 1;
   if(!g_ready || h < 0 || h >= g_h4_n || h >= g_str_n || h >= g_qlt_n)
     {
      for(int i = 0; i < 4; i++) val[i] = HMI_U(ZH_WAIT);
      val[4] = HMI_U(ZH_DASH);
      return;
     }
   StgRec r = g_stg[h];
   StrRec s = g_str[h];
   QltRec q = g_qlt[h];
   if(g_str_wait)
     {
      val[0] = HMI_U(ZH_WAIT);
      val[1] = StgStrengthValue(s, r.arrow, true);
      val[2] = StgQualityValue(q, true);
      val[3] = HMI_U(ZH_WAIT);
      val[4] = HMI_U(ZH_DASH);
      return;
     }
   if(g_ctx == CTX_BULLISH)      { val[0] = HMI_U(ZH_UP_TRI) + " " + HMI_U(ZH_BULL);  ck[0] = PC_BULL; }
   else if(g_ctx == CTX_BEARISH) { val[0] = HMI_U(ZH_DN_TRI) + " " + HMI_U(ZH_BEAR);  ck[0] = PC_BEAR; }
   else if(g_ctx == CTX_TRANSITION)
     {
      val[0] = HMI_U(ZH_TRANS_HEAD) + " " + HMI_U(ZH_DOT) + " " + HMI_U(r.pend == 1 ? ZH_PEND_UP : ZH_PEND_DN);
      ck[0]  = PC_TRANS;
     }
   else                          { val[0] = HMI_U(ZH_RANGE);  ck[0] = PC_RANGE; }
   val[1] = StgStrengthValue(s, r.arrow, false);
   val[2] = StgQualityValue(q, false);
   if(s.state == STR_OK) ck[1] = (s.tier == ST_STRONG ? PC_HIGH : (s.tier == ST_MED ? PC_MID : PC_LOW));
   if(q.state == QLT_OK) ck[2] = (q.tier == QT_GOOD ? PC_HIGH : (q.tier == QT_FAIR ? PC_MID : PC_LOW));
   val[3] = StgStageZh(r);
   val[4] = StgWhyText(r);
  }

//--- v2.58r4 PANEL_COMPACT's trend panel: three rows of coloured segments ----------------------
//   H4 空头｜正常回撤
//   强度 弱25/100↓｜质量 良好74/100
//   原因 回撤偏深，近期逆向运行
// No old score and no 0 stands in for a state: 等待数据 / 样本不足 / 不可用 / 暂不评级 are shown as such.
string StgStrengthShort(const StrRec &s, const int arrow, int &c)
  {
   c = PC_BASE;
   if(s.state == STR_NODATA) return(HMI_U(s.reason == SR_HISTORY ? ZH_FEW : ZH_NA));
   if(s.state == STR_NODIR)  return(HMI_U(ZH_NORATE));
   c = (s.tier == ST_STRONG ? PC_HIGH : (s.tier == ST_MED ? PC_MID : PC_LOW));
   string a = (arrow == AR_UP ? HMI_U(ZH_ARR_UP) : (arrow == AR_DOWN ? HMI_U(ZH_ARR_DN)
              : (arrow == AR_FLAT ? HMI_U(ZH_ARR_FLAT) : " " + HMI_U(ZH_ARR_NEW))));
   return(StrTierZh(s.tier) + IntegerToString(s.score) + "/100" + a);
  }

// 5 mature events: no sample note; 3 or 4: 低样本; fewer: 样本不足 n/3
string StgQualityShort(const QltRec &q, int &c)
  {
   c = PC_BASE;
   if(q.state == QLT_NODATA) return(HMI_U(ZH_FEW));
   if(q.state == QLT_NODIR)  return(HMI_U(ZH_NORATE));
   if(q.state == QLT_PARTIAL)
      return((q.reason & QR_FEW) != 0 ? HMI_U(ZH_FEW) + " " + IntegerToString(q.n) + "/" + IntegerToString(QLT_EV_MIN)
                                      : HMI_U(ZH_NA));
   c = (q.tier == QT_GOOD ? PC_HIGH : (q.tier == QT_FAIR ? PC_MID : PC_LOW));
   return(QltTierZh(q.tier) + IntegerToString(q.score) + "/100" + (q.sample == QS_LOW ? " " + HMI_U(ZH_LOWSMP) : ""));
  }

void StgSeg(string &seg[], int &ck[], int &rw[], int &n, const int row, const string text, const int c)
  {
   ArrayResize(seg, n + 1);  ArrayResize(ck, n + 1);  ArrayResize(rw, n + 1);
   seg[n] = text;  ck[n] = c;  rw[n] = row;
   n++;
  }

int StgCompactRows(string &seg[], int &ck[], int &rw[])
  {
   ArrayResize(seg, 0);  ArrayResize(ck, 0);  ArrayResize(rw, 0);
   int n = 0;
   int h = g_stg_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n || h >= g_str_n || h >= g_qlt_n)
     {
      StgSeg(seg, ck, rw, n, 0, "H4 ", PC_LAB);
      StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_WAIT), PC_BASE);
      StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_STR_SHORT) + " ", PC_LAB);
      StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_WAIT), PC_BASE);
      StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_BAR), PC_LAB);
      StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_QLT_SHORT) + " ", PC_LAB);
      StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_WAIT), PC_BASE);
      StgSeg(seg, ck, rw, n, 2, HMI_U(ZH_WHY_SHORT) + " ", PC_LAB);
      StgSeg(seg, ck, rw, n, 2, HMI_U(ZH_DASH), PC_BASE);
      return(n);
     }
   StgRec r = g_stg[h];
   StrRec s = g_str[h];
   QltRec q = g_qlt[h];
   StgSeg(seg, ck, rw, n, 0, "H4 ", PC_LAB);
   if(g_ctx == CTX_BULLISH)      StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_BULL), PC_BULL);
   else if(g_ctx == CTX_BEARISH) StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_BEAR), PC_BEAR);
   else if(g_ctx == CTX_TRANSITION)
      StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_TRANS_HEAD) + HMI_U(ZH_DOT) + HMI_U(r.pend == 1 ? ZH_LEAN_UP : ZH_LEAN_DN), PC_TRANS);
   else                          StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_RANGE), PC_RANGE);
   if(!(g_ctx == CTX_RANGE && r.stage == SG_RANGE))        // 区间震荡 is said once
     {
      StgSeg(seg, ck, rw, n, 0, HMI_U(ZH_BAR), PC_LAB);
      StgSeg(seg, ck, rw, n, 0, StgStageZh(r), PC_BASE);
     }
   int c = PC_BASE;
   StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_STR_SHORT) + " ", PC_LAB);
   string sv = StgStrengthShort(s, r.arrow, c);
   StgSeg(seg, ck, rw, n, 1, sv, c);
   StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_BAR), PC_LAB);
   StgSeg(seg, ck, rw, n, 1, HMI_U(ZH_QLT_SHORT) + " ", PC_LAB);
   string qv = StgQualityShort(q, c);
   StgSeg(seg, ck, rw, n, 1, qv, c);
   StgSeg(seg, ck, rw, n, 2, HMI_U(ZH_WHY_SHORT) + " ", PC_LAB);
   StgSeg(seg, ck, rw, n, 2, StgWhyText(r), PC_BASE);
   return(n);
  }

//--- v2.58r4 the diagnostic panel's compact rows (texts only; HMI_ObjectManager gathers the state) ---
// "2026.10.28 13:05" -> "10.28 13:05" (server time, as on the chart's time axis)
string StgShortTime(const datetime t) { return(StringSubstr(TimeToString(t, TIME_DATE|TIME_MINUTES), 5)); }

// Row 1, the M5 tracking state. A cycle is being tracked while Phase 4 still
// checks it and something can still be marked: CY_ACTIVE with a model PENDING.
// Only that cycle's flags are shown (锚点失效 = D-5's anchor_invalidated,
// H4 趋势已变 = D-1's ctx_changed); a cycle with every model resolved, or a
// closed one, is history and appears in PANEL_FULL's LAST CYCLE row only.
string StgM5Row(const bool ready, const bool cyc_on, const string armed, const int done, const int pend,
                const bool anchor_bad, const bool ctx_chg, const bool sess_on, const string sess_t, const bool trend)
  {
   if(!ready) return("M5 " + HMI_U(ZH_WAIT));
   if(cyc_on && pend > 0)
     {
      string s = "M5 " + HMI_U(ZH_M5_TRACK) + HMI_U(ZH_LP) + armed + " " + HMI_U(ZH_M5_FROM) + HMI_U(ZH_RP) +
                 HMI_U(ZH_M5_DONE) + " " + IntegerToString(done) + " " + HMI_U(ZH_M5_ITEM) + " " + HMI_U(ZH_DOT) + " " +
                 HMI_U(ZH_PENDING) + " " + IntegerToString(pend) + " " + HMI_U(ZH_M5_ITEM);
      if(anchor_bad) s += " " + HMI_U(ZH_DOT) + " " + HMI_U(ZH_M5_ANCHOR);
      if(ctx_chg)    s += " " + HMI_U(ZH_DOT) + " " + HMI_U(ZH_M5_CTX);
      return(s);
     }
   string head = "M5 " + HMI_U(ZH_M5_IDLE) + " " + HMI_U(ZH_DOT) + " ";
   if(sess_on)
      return(head + HMI_U(ZH_M5_POI) + HMI_U(ZH_LP) + sess_t + HMI_U(ZH_RP) + HMI_U(ZH_COMMA) + HMI_U(ZH_M5_WAITBLK));
   return(head + HMI_U(trend ? ZH_M5_WAITPOI : ZH_M5_PAUSE));
  }

// Row 2, today's range against ADR (pct and left formatted by HMI_Ranges)
string StgADRRow(const bool ok, const string pct, const string left, const bool exhausted)
  {
   if(!ok) return(HMI_U(ZH_ADR_TODAY) + HMI_U(ZH_COLON) + HMI_U(ZH_WAIT));
   return(HMI_U(ZH_ADR_TODAY) + " " + pct + "% " + HMI_U(ZH_DOT) + " " + HMI_U(ZH_ADR_LEFT) + " " + left + " pip" +
          (exhausted ? HMI_U(ZH_LP) + HMI_U(ZH_ADR_EXH) + HMI_U(ZH_RP) : ""));
  }

//--- PANEL_FULL's item rows (diagnostic panel): the strength and quality items of the same bar ---
string StgStrItemsText()
  {
   int h = g_str_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n || g_str[h].state != STR_OK) return("");
   StrRec s = g_str[h];
   long m = 0, e = 0, q = 0;
   StgStrItems(s, m, e, q);
   long eff = (s.path > 0 ? QltRnd(100 * e, s.path) : 0);
   return(HMI_U(ZH_STR_ITEMS) + "  " + HMI_U(ZH_I_MOVE) + " " + IntegerToString(QltRnd(100 * m, STR_MOVE_ATR * s.trsum)) +
          " " + HMI_U(ZH_DOT) + " " + HMI_U(ZH_I_EFF) + " " + IntegerToString(eff) +
          " " + HMI_U(ZH_DOT) + " " + HMI_U(ZH_I_MOM) + " " + IntegerToString(QltRnd(100 * q, STR_MOM_ATR * s.trsum)));
  }

string StgQltItemsText()
  {
   int h = g_qlt_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n) return("");
   QltRec q = g_qlt[h];
   if(q.state != QLT_OK && q.state != QLT_PARTIAL) return("");
   return(HMI_U(ZH_QLT_ITEMS) + "  " + QltLocal(q, " " + HMI_U(ZH_DOT) + " "));
  }

//--- the diagnostic panel's long rows: an OBJ_LABEL shows 63 characters (stage_sim.wrap) ---
#define STG_LABEL_MAX 63

// the last k with sub at k and k + len(sub) <= lim + 1 (Python: s.rfind(sub, 0, lim + 1)); -1 = none
int StgRFind(const string s, const string sub, const int lim)
  {
   int best = -1;
   int ls = StringLen(sub);
   int from = 0;
   while(true)
     {
      int k = StringFind(s, sub, from);
      if(k < 0 || k + ls > lim + 1) break;
      best = k;
      from = k + 1;
     }
   return(best);
  }

int StgWrap(const string text, string &out[])
  {
   ArrayResize(out, 0);
   string cur = text;
   string ind = "    ";
   int lim = STG_LABEL_MAX;
   while(StringLen(cur) > lim)
     {
      int cut = -1, skip = 0;
      int k = StgRFind(cur, "|", lim);
      if(k >= lim / 2) { cut = k;  skip = 1; }
      else
        {
         k = StgRFind(cur, "  ", lim);
         if(k >= lim / 2) { cut = k;  skip = 2; }
        }
      if(cut < 0)
        {
         k = StgRFind(cur, " ", lim);
         if(k > StringLen(ind)) { cut = k;  skip = 1; }
        }
      int n = ArraySize(out);
      ArrayResize(out, n + 1);
      if(cut < 0)
        {
         out[n] = StringSubstr(cur, 0, lim);
         cur = ind + StringSubstr(cur, lim);
         continue;
        }
      string head = StringSubstr(cur, 0, cut);
      StringTrimRight(head);
      string rest = StringSubstr(cur, cut + skip);
      StringTrimLeft(rest);
      out[n] = head;
      cur = ind + rest;
     }
   int n = ArraySize(out);
   ArrayResize(out, n + 1);
   out[n] = cur;
   return(n + 1);
  }

#endif // HMI_STAGEENGINE_MQH
