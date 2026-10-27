//+------------------------------------------------------------------+
//| HMI_QualityEngine.mqh — H4 trend quality score (v2.57, BRI-14)    |
//| DISPLAY ONLY (Rule 69): no rule, mark or state reads it back.     |
//| docs/02 "BRI-14"; offline model tools/quality_sim.py.             |
//+------------------------------------------------------------------+
#ifndef HMI_QUALITYENGINE_MQH
#define HMI_QUALITYENGINE_MQH
#include "HMI_StrengthEngine.mqh"

// Requirement §6 / §10 constants with the §6.1 ruling (C-1 .. C-9 confirmed
// 2026-10-27). Not inputs: the trading params digest stays as it was; every
// HMI-QLT row carries QLT_DEF, and a change of any constant must change it.
#define QLT_EV_WIN   60      // events: the latest 60 processed H4 bars ...
#define QLT_EV_MAX   5       // ... the latest 5 mature ones of the current leg
#define QLT_EV_OBS   3       // closes observed after the break
#define QLT_EV_MIN   3       // fewer mature events: no Q_break, no total
#define QLT_OV_BARS  12      // 11 adjacent pairs
#define QLT_FP       1000000 // overlap fixed point (floor per pair)
#define QLT_W_BRK    40      // weights, percent
#define QLT_W_RET    35
#define QLT_W_OVL    25
#define QLT_T_FAIR   40      // tiers on the UNROUNDED score
#define QLT_T_GOOD   70
#define QLT_DEF      "QLT1-B60.5.3.3S1-RA-O12F6-W40.35.25-T40.70"
// raw = num / den, den = LCD x leg (LCD = lcm(60, 20, 440000)):
//   num = W_BRK s (LCD / n) leg + C_RET num_r + C_OVL (11 FP - so) leg
#define QLT_LCD      1320000
#define QLT_C_RET    462000  // = W_RET x LCD / 100 (0.35 num_r / leg)
#define QLT_C_OVL    3       // = W_OVL x LCD / (11 x FP), exact (0.25 x 100 (11 FP - so) / 11 FP)
#define QLT_LEG_MAX  ((long)100000 * (long)100000)   // 1e10 points: 2 num + den stays inside a long

#define QLT_OK       0
#define QLT_PARTIAL  1
#define QLT_NODIR    2
#define QLT_NODATA   3

#define QR_FEW       1       // reasons of PARTIAL, joined by + in this order
#define QR_ANCHOR    2
#define QR_LEG       4
#define QR_SCALE     8

#define QT_NA        0
#define QT_POOR      1
#define QT_FAIR      2
#define QT_GOOD      3

#define QS_NONE      0       // "-"
#define QS_FEW       1
#define QS_LOW       2       // 3 or 4 mature events
#define QS_FIVE      3

struct QltEvent
  {
   int      k;                // H4 index of the break
   bool     start;            // the leg's opening break (RANGE BOS / TRANS_OK / TRANS_FAIL)
   double   level;            // frozen: the primary swing's price
  };

struct QltRec
  {
   int      state;
   int      reason;           // QR_* bits (PARTIAL)
   int      ctx;
   int      dir;
   int      n, s, fail, pend; // mature events used, of them OK / FAIL; pending events
   int      sample;
   long     so;               // sum of the 11 fixed-point overlaps
   bool     has_anchor;
   double   anchor_px;
   int      anchor_bar;       // H4 index of the leg_anchor swing bar
   double   ext_px;
   long     leg, x, num_r;    // points; Q_retrace = num_r / leg when has_x
   bool     has_x;
   long     num, den;         // raw = num / den exactly (OK)
   int      score;            // round half up of raw; -1 when not OK
   int      tier;
  };

QltEvent g_qev[];                // the current leg's breaks within the window, oldest first
int      g_qev_n      = 0;
int      g_qlt_leg    = -1;      // the g_leg_seq those events belong to; -1 = no trend
QltRec   g_qlt[];                // one record per PROCESSED H4 bar, index = H4 index
int      g_qlt_n      = 0;

void QltReset()
  {
   g_qev_n   = 0;
   g_qlt_leg = -1;
   g_qlt_n   = 0;
   ArrayResize(g_qev, 0, 64);
   ArrayResize(g_qlt, 0, 512);
  }

//--- the event at bar k seen from bar h: 0 pending, 1 OK, 2 FAIL ---------
int QltOutcome(const QltEvent &e, const int d, const int h)
  {
   if(h - e.k < QLT_EV_OBS) return(0);
   for(int j = e.k + 1; j <= e.k + QLT_EV_OBS; j++)
      if(d * StrL(g_h4[j].close, e.level) < 0) return(2);   // beyond the level against D; equal is not a failure
   return(1);
  }

long QltRetraceNum(const long x, const long leg)
  {
   if(3 * x <= leg)     return(100 * leg);
   if(3 * x <= 2 * leg) return(160 * leg - 180 * x);
   return(120 * (leg - x));
  }

void QltLog(const int h);

//--- the quality of H4 bar h (called right after StrOnH4Bar: same point in build and live, Rule 51) ---
void QltOnH4Bar(const int h)
  {
   if(h < 0 || h >= g_h4_n) return;
   if(ArraySize(g_qlt) < h + 1) ArrayResize(g_qlt, h + 1, 512);
   int d = (g_ctx == CTX_BULLISH ? 1 : (g_ctx == CTX_BEARISH ? -1 : 0));

   //--- the tracker: the current leg's breaks (kept on every bar, early ones too)
   if(d == 0)
     { g_qlt_leg = -1;  g_qev_n = 0; }
   else
     {
      bool started = (g_leg_seq != g_qlt_leg);
      if(started) { g_qlt_leg = g_leg_seq;  g_qev_n = 0; }
      if(g_ctx_brk_h == h && g_ctx_brk_dir == d)
        {
         if(ArraySize(g_qev) < g_qev_n + 1) ArrayResize(g_qev, g_qev_n + 1, 64);
         g_qev[g_qev_n].k     = h;
         g_qev[g_qev_n].start = started;
         g_qev[g_qev_n].level = g_ctx_brk_px;
         g_qev_n++;
        }
      int w = 0;                                   // drop what left the 60-bar window
      for(int i = 0; i < g_qev_n; i++)
         if(h - g_qev[i].k <= QLT_EV_WIN - 1) g_qev[w++] = g_qev[i];
      g_qev_n = w;
     }

   QltRec r;
   ZeroMemory(r);
   r.state = QLT_NODATA;  r.ctx = (int)g_ctx;  r.score = -1;  r.tier = QT_NA;  r.den = 1;
   r.anchor_bar = -1;  r.sample = QS_NONE;
   if(h >= QLT_OV_BARS - 1)
     {
      //--- Q_overlap: the latest 12 bars, whatever the leg
      long so = 0;
      for(int i = h - QLT_OV_BARS + 2; i <= h; i++)
        {
         long inter = StrMax(0, StrL(MathMin(g_h4[i].high, g_h4[i-1].high), MathMax(g_h4[i].low, g_h4[i-1].low)));
         long uni   = StrL(MathMax(g_h4[i].high, g_h4[i-1].high), MathMin(g_h4[i].low, g_h4[i-1].low));
         so += (uni == 0 ? QLT_FP : (QLT_FP * inter) / uni);
        }
      r.so = so;
      if(d == 0)
         r.state = QLT_NODIR;
      else
        {
         r.dir = d;
         //--- Q_break: the latest 5 mature events (oldest first in g_qev)
         int mature = 0;
         for(int i = 0; i < g_qev_n; i++) if(h - g_qev[i].k >= QLT_EV_OBS) mature++;
         int m = 0;
         for(int i = 0; i < g_qev_n; i++)
           {
            int res = QltOutcome(g_qev[i], d, h);
            if(res == 0) { r.pend++; continue; }
            m++;
            if(m <= mature - QLT_EV_MAX) continue;  // older than the latest five
            r.n++;
            if(res == 1) r.s++; else r.fail++;
           }
         if(r.n >= QLT_EV_MIN) r.sample = (r.n == QLT_EV_MAX ? QS_FIVE : QS_LOW);
         else                { r.sample = QS_FEW;  r.reason |= QR_FEW; }
         //--- Q_retrace: from leg_anchor (BRI-12 P-3), never protected_level
         if(!g_anchor.valid)
            r.reason |= QR_ANCHOR;
         else
           {
            int a = g_anchor.bar_index;
            r.has_anchor = true;  r.anchor_px = g_anchor.price;  r.anchor_bar = a;
            if(a < 0 || a >= h)
               r.reason |= QR_LEG;                // no bar after the anchor (cannot happen: the anchor confirms before its BOS)
            else
              {
               double ext = (d == 1 ? g_h4[a+1].high : g_h4[a+1].low);
               for(int i = a + 2; i <= h; i++)
                  ext = (d == 1 ? MathMax(ext, g_h4[i].high) : MathMin(ext, g_h4[i].low));
               r.ext_px = ext;
               r.leg = d * StrL(ext, g_anchor.price);
               if(r.leg <= 0)               r.reason |= QR_LEG;
               else if(r.leg > QLT_LEG_MAX) r.reason |= QR_SCALE;
               else
                 {
                  r.x = StrMin(StrMax(d * StrL(ext, g_h4[h].close), 0), r.leg);
                  r.num_r = QltRetraceNum(r.x, r.leg);
                  r.has_x = true;
                 }
              }
           }
         if(r.reason != 0)
            r.state = QLT_PARTIAL;
         else
           {
            r.state = QLT_OK;
            r.den   = (long)QLT_LCD * r.leg;
            r.num   = (long)QLT_W_BRK * r.s * (QLT_LCD / r.n) * r.leg + (long)QLT_C_RET * r.num_r +
                      (long)QLT_C_OVL * (11 * (long)QLT_FP - r.so) * r.leg;
            r.score = (int)((2 * r.num + r.den) / (2 * r.den));
            r.tier  = (r.num < QLT_T_FAIR * r.den ? QT_POOR : (r.num < QLT_T_GOOD * r.den ? QT_FAIR : QT_GOOD));
           }
        }
     }
   g_qlt[h] = r;
   g_qlt_n  = h + 1;
   QltLog(h);
  }

string QltStateName(const int s) { return(s == QLT_OK ? "OK" : (s == QLT_PARTIAL ? "PARTIAL" : (s == QLT_NODIR ? "NODIR" : "NODATA"))); }
string QltTierName(const int t)  { return(t == QT_POOR ? "POOR" : (t == QT_FAIR ? "FAIR" : (t == QT_GOOD ? "GOOD" : "NA"))); }
string QltSampleName(const int s) { return(s == QS_FEW ? "FEW" : (s == QS_LOW ? "LOW" : (s == QS_FIVE ? "FIVE" : "-"))); }

string QltReasonName(const QltRec &r)
  {
   if(r.state == QLT_NODATA) return("HISTORY");
   if(r.state != QLT_PARTIAL) return("-");
   string s = "";
   if((r.reason & QR_FEW) != 0)    s += (s == "" ? "" : "+") + "FEW";
   if((r.reason & QR_ANCHOR) != 0) s += (s == "" ? "" : "+") + "ANCHOR";
   if((r.reason & QR_LEG) != 0)    s += (s == "" ? "" : "+") + "LEG";
   if((r.reason & QR_SCALE) != 0)  s += (s == "" ? "" : "+") + "SCALE";
   return(s);
  }

double QltBreak(const QltRec &r)   { return(100.0 * (double)r.s / (double)r.n); }
double QltRetrace(const QltRec &r) { return((double)r.num_r / (double)r.leg); }
double QltOverlap(const QltRec &r) { return(100.0 * (double)(11 * (long)QLT_FP - r.so) / (double)(11 * (long)QLT_FP)); }
string QltPx(const double v)       { return(DoubleToString(v, _Digits)); }

//--- the events of bar h as logged: pending ones and the mature ones used ---
string QltEventList(const int h, const int d)
  {
   int mature = 0;
   for(int i = 0; i < g_qev_n; i++) if(h - g_qev[i].k >= QLT_EV_OBS) mature++;
   string out = "";
   int m = 0;
   for(int i = 0; i < g_qev_n; i++)
     {
      int res = QltOutcome(g_qev[i], d, h);
      if(res != 0) { m++;  if(m <= mature - QLT_EV_MAX) continue; }
      string obs = "";
      for(int j = g_qev[i].k + 1; j <= MathMin(g_qev[i].k + QLT_EV_OBS, h); j++)
         obs += (obs == "" ? "" : "|") + QltPx(g_h4[j].close);
      out += (out == "" ? "" : ";") + StrBarTime(g_qev[i].k) + "@" + QltPx(g_qev[i].level) + "/" +
             (g_qev[i].start ? "START" : "BOS") + "/" + (res == 0 ? "PEND" : (res == 1 ? "OK" : "FAIL")) + "/" +
             (obs == "" ? "-" : obs);
     }
   return(out == "" ? "-" : out);
  }

string QltPairs(const int h)
  {
   string out = "";
   for(int i = h - QLT_OV_BARS + 2; i <= h; i++)
     {
      long inter = StrMax(0, StrL(MathMin(g_h4[i].high, g_h4[i-1].high), MathMax(g_h4[i].low, g_h4[i-1].low)));
      long uni   = StrL(MathMax(g_h4[i].high, g_h4[i-1].high), MathMin(g_h4[i].low, g_h4[i-1].low));
      out += (out == "" ? "" : ";") + IntegerToString(inter) + "/" + IntegerToString(uni);
     }
   return(out);
  }

//--- one row per H4 bar: live, or in a build the bars that close inside the M5 window (as HMI-STR) ---
void QltLog(const int h)
  {
   if(!InpLogSignals) return;
   datetime bar = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   if(!g_live && (g_m5_n <= 0 || bar <= g_m5[0].time)) return;
   QltRec r = g_qlt[h];
   bool trend = (r.state == QLT_OK || r.state == QLT_PARTIAL);
   bool data  = (r.state != QLT_NODATA);
   bool brk   = (trend && r.n >= QLT_EV_MIN);
   bool ok    = (r.state == QLT_OK);
   bool legv  = (trend && r.has_anchor && r.anchor_bar >= 0 && r.anchor_bar < h);
   PrintFormat("HMI-QLT,%s,live=%d,bar=%s,ctx=%s,state=%s,reason=%s,def=%s,dir=%d,ev=%s,b_n=%d,b_ok=%d,b_fail=%d,b_pend=%d,q_break=%s," +
               "anchor=%s,anchor_bar=%s,ext=%s,close=%s,leg_pts=%s,retr_pts=%s,q_retrace=%s,ov=%s,ov_sum=%s,q_overlap=%s," +
               "raw=%s,score=%s,tier=%s,sample=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, (g_live ? 1 : 0), TimeToString(bar, TIME_DATE|TIME_MINUTES), CtxName((CtxState)r.ctx),
               QltStateName(r.state), QltReasonName(r), QLT_DEF, r.dir,
               (trend ? QltEventList(h, r.dir) : "-"), r.n, r.s, r.fail, r.pend,
               (brk ? StrD6(QltBreak(r)) : "NA"),
               (trend && r.has_anchor ? QltPx(r.anchor_px) : "NA"),
               (trend && r.has_anchor ? TimeToString(g_h4[r.anchor_bar].time, TIME_DATE|TIME_MINUTES) : "-"),
               (legv ? QltPx(r.ext_px) : "NA"), QltPx(g_h4[h].close),
               (legv ? IntegerToString(r.leg) : "NA"), (r.has_x ? IntegerToString(r.x) : "NA"),
               (r.has_x ? StrD6(QltRetrace(r)) : "NA"),
               (data ? QltPairs(h) : "NA"), (data ? IntegerToString(r.so) : "NA"), (data ? StrD6(QltOverlap(r)) : "NA"),
               (ok ? StrD6((double)r.num / (double)r.den) : "NA"), (ok ? IntegerToString(r.score) : "NA"),
               QltTierName(r.tier), QltSampleName(r.sample), g_inst, g_run_id, g_init_seq);
  }

//--- build end: the whole processed H4 window (as HMI-STR-HIST) ---
void QltLogHist()
  {
   if(!InpLogSignals) return;
   int cnt[101];
   ArrayInitialize(cnt, 0);
   int nd[6];                                   // n = 0 .. QLT_EV_MAX (5)
   ArrayInitialize(nd, 0);
   int ok = 0, part = 0, nodir = 0, nodata = 0, tp = 0, tf = 0, tg = 0, few = 0, anc = 0, legbad = 0;
   for(int h = 0; h < g_qlt_n; h++)
     {
      QltRec r = g_qlt[h];
      if(r.state == QLT_NODIR)  { nodir++;  continue; }
      if(r.state == QLT_NODATA) { nodata++; continue; }
      nd[MathMin(r.n, QLT_EV_MAX)]++;
      if(r.state == QLT_PARTIAL)
        {
         part++;
         if((r.reason & QR_FEW) != 0)    few++;
         if((r.reason & QR_ANCHOR) != 0) anc++;
         if((r.reason & QR_LEG) != 0)    legbad++;
         if((r.reason & QR_SCALE) != 0)  legbad++;
         continue;
        }
      ok++;
      cnt[MathMax(0, MathMin(100, r.score))]++;
      if(r.tier == QT_POOR) tp++; else if(r.tier == QT_FAIR) tf++; else tg++;
     }
   string hs = "", ns = "";
   for(int i = 0; i <= 100; i++) hs += (i > 0 ? ";" : "") + IntegerToString(cnt[i]);
   for(int i = 0; i <= QLT_EV_MAX; i++) ns += (i > 0 ? ";" : "") + IntegerToString(nd[i]);
   PrintFormat("HMI-QLT-HIST,%s,live=0,def=%s,from=%s,to=%s,bars=%d,ok=%d,partial=%d,nodir=%d,nodata=%d,poor=%d,fair=%d,good=%d," +
               "few=%d,anchor=%d,legbad=%d,n=%s,h=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, QLT_DEF,
               (g_qlt_n > 0 ? StrBarTime(0) : "-"), (g_qlt_n > 0 ? StrBarTime(g_qlt_n - 1) : "-"),
               g_qlt_n, ok, part, nodir, nodata, tp, tf, tg, few, anc, legbad, ns, hs, g_inst, g_run_id, g_init_seq);
  }

//====================== panel text (display) =========================
// Same wording as quality_sim.panel_text / compact_text. Chinese as \uXXXX (HMI_U).
#define ZH_QUALITY    "\\u8D8B\\u52BF\\u8D28\\u91CF"                      // 趋势质量
#define ZH_QLT_SHORT  "\\u8D28\\u91CF"                                    // 质量
#define ZH_GOOD       "\\u826F\\u597D"                                    // 良好
#define ZH_FAIR       "\\u4E00\\u822C"                                    // 一般
#define ZH_POOR       "\\u8F83\\u5DEE"                                    // 较差
#define ZH_LOWSMP     "\\u4F4E\\u6837\\u672C"                             // 低样本
#define ZH_TIMES_BRK  "\\u6B21\\u7A81\\u7834"                             // 次突破
#define ZH_TIMES_EV   "\\u6B21\\u4E8B\\u4EF6"                             // 次事件
#define ZH_MATURE     "\\u6210\\u719F\\u7A81\\u7834"                      // 成熟突破
#define ZH_PENDING    "\\u5F85\\u786E\\u8BA4"                             // 待确认
#define ZH_NOANCHOR   "\\u65E0\\u6CE2\\u6BB5\\u951A\\u70B9"               // 无波段锚点
#define ZH_LEGBAD     "\\u6CE2\\u6BB5\\u957F\\u5EA6\\u65E0\\u6548"        // 波段长度无效
#define ZH_LOCAL      "\\u5C40\\u90E8\\u8868\\u73B0"                      // 局部表现
#define ZH_LOCAL_S    "\\u5C40\\u90E8"                                    // 局部
#define ZH_BRK        "\\u7A81\\u7834"                                    // 突破
#define ZH_RET        "\\u56DE\\u64A4"                                    // 回撤
#define ZH_OVL        "\\u91CD\\u53E0"                                    // 重叠
#define ZH_FEW12      "H4 \\u4E0D\\u8DB3 12 \\u6839"                      // H4 不足 12 根
#define ZH_SEMI       "\\uFF1B"                                           // ；

string QltTierZh(const int t) { return(HMI_U(t == QT_POOR ? ZH_POOR : (t == QT_FAIR ? ZH_FAIR : ZH_GOOD))); }

// half-up rounding of the items shown as 局部表现 (non-negative)
long QltRnd(const long num, const long den) { return((2 * num + den) / (2 * den)); }

string QltLocal(const QltRec &r, const string sep)
  {
   string out = "";
   if(r.n >= QLT_EV_MIN)
      out += HMI_U(ZH_BRK) + " " + IntegerToString(QltRnd(100 * (long)r.s, (long)r.n));
   if(r.has_x)
      out += (out == "" ? "" : sep) + HMI_U(ZH_RET) + " " + IntegerToString(QltRnd(r.num_r, r.leg));
   out += (out == "" ? "" : sep) + HMI_U(ZH_OVL) + " " +
          IntegerToString(QltRnd(100 * (11 * (long)QLT_FP - r.so), 11 * (long)QLT_FP));
   return(out);
  }

string QltWhy(const QltRec &r)
  {
   string out = "";
   if((r.reason & QR_FEW) != 0)
     {
      out = HMI_U(ZH_MATURE) + " " + IntegerToString(r.n) + "/" + IntegerToString(QLT_EV_MIN);
      if(r.pend > 0) out += HMI_U(ZH_COMMA) + HMI_U(ZH_PENDING) + " " + IntegerToString(r.pend);
     }
   if((r.reason & QR_ANCHOR) != 0) out += (out == "" ? "" : HMI_U(ZH_SEMI)) + HMI_U(ZH_NOANCHOR);
   if((r.reason & (QR_LEG | QR_SCALE)) != 0) out += (out == "" ? "" : HMI_U(ZH_SEMI)) + HMI_U(ZH_LEGBAD);
   return(out);
  }

//--- the FULL panel line -------------------------------------------------
string QltPanelText()
  {
   string head = HMI_U(ZH_QUALITY) + "  ";
   int h = g_qlt_n - 1;
   if(!g_ready || h < 0 || h >= g_h4_n)
      return(head + HMI_U(ZH_WAIT));
   QltRec r = g_qlt[h];
   if(g_str_wait)                                   // the same waiting state as the strength line
     {
      if(r.state != QLT_OK) return(head + HMI_U(ZH_WAIT));
      return(head + HMI_U(ZH_WAIT) + HMI_U(ZH_LP) + HMI_U(ZH_LASTOK) + " " + QltTierZh(r.tier) + " " + HMI_U(ZH_DOT) + " " +
             IntegerToString(r.score) + "/100" + HMI_U(ZH_COMMA) + StrBarTime(h) + " H4 " + HMI_U(ZH_CLOSE) + HMI_U(ZH_RP));
     }
   if(r.state == QLT_NODATA)
      return(head + HMI_U(ZH_FEW) + HMI_U(ZH_LP) + HMI_U(ZH_FEW12) + HMI_U(ZH_RP));
   if(r.state == QLT_NODIR)
      return(head + HMI_U(ZH_NORATE) + HMI_U(ZH_LP) + HMI_U(r.ctx == CTX_RANGE ? ZH_RANGE : ZH_TRANS) + HMI_U(ZH_RP));
   if(r.state == QLT_PARTIAL)
      return(head + HMI_U((r.reason & QR_FEW) != 0 ? ZH_FEW : ZH_NA) + HMI_U(ZH_LP) + QltWhy(r) + HMI_U(ZH_RP) +
             "  " + HMI_U(ZH_LOCAL) + " " + QltLocal(r, " " + HMI_U(ZH_DOT) + " "));
   return(head + QltTierZh(r.tier) + " " + HMI_U(ZH_DOT) + " " + IntegerToString(r.score) + "/100" + HMI_U(ZH_LP) +
          (r.sample == QS_FIVE ? "5 " + HMI_U(ZH_TIMES_EV)
                               : HMI_U(ZH_LOWSMP) + " " + IntegerToString(r.n) + " " + HMI_U(ZH_TIMES_BRK)) + HMI_U(ZH_RP));
  }

//--- PANEL_COMPACT's quality row (after the strength row) ---------------
string QltPanelShort()
  {
   string head = HMI_U(ZH_QLT_SHORT) + " ";
   int h = g_qlt_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n) return(head + HMI_U(ZH_WAIT));
   QltRec r = g_qlt[h];
   if(r.state == QLT_NODATA) return(head + HMI_U(ZH_FEW));
   if(r.state == QLT_NODIR)  return(head + HMI_U(ZH_NORATE));
   if(r.state == QLT_PARTIAL)
      return(head + ((r.reason & QR_FEW) != 0 ? HMI_U(ZH_FEW) + " " + IntegerToString(r.n) + "/" + IntegerToString(QLT_EV_MIN)
                                              : HMI_U(ZH_NA)) +
             "   " + HMI_U(ZH_LOCAL_S) + " " + QltLocal(r, " "));
   return(head + QltTierZh(r.tier) + " " + IntegerToString(r.score) + "/100   " +
          (r.sample == QS_FIVE ? "5 " + HMI_U(ZH_TIMES_EV) : HMI_U(ZH_LOWSMP)));
  }

#endif // HMI_QUALITYENGINE_MQH
