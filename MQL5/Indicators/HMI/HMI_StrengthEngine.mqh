//+------------------------------------------------------------------+
//| HMI_StrengthEngine.mqh — H4 trend strength score (v2.56, BRI-13)  |
//| DISPLAY ONLY (Rule 69): no rule, mark or state reads it back.     |
//| docs/02 "BRI-13 修订稿 2"; offline model tools/strength_sim.py.    |
//+------------------------------------------------------------------+
#ifndef HMI_STRENGTHENGINE_MQH
#define HMI_STRENGTHENGINE_MQH
#include "HMI_H4ContextEngine.mqh"

// Requirement §5 / §10 first-version constants. They are not inputs, so the
// trading params digest stays as it was; every HMI-STR row carries STR_DEF
// instead, and a change of any constant must change STR_DEF.
#define STR_N        12      // main window (closes)
#define STR_K        3       // recent momentum window
#define STR_ATR_N    14      // ATR14 = SeriesComputeATR's simple mean TR
#define STR_W_MOVE   45      // weights, percent
#define STR_W_EFF    35
#define STR_W_MOM    20
#define STR_MOVE_ATR 3       // net move: full marks at 3 ATR
#define STR_MOM_ATR  1       // recent momentum: full marks at 1 ATR
#define STR_T_MED    35      // tiers on the UNROUNDED score
#define STR_T_STRONG 65
#define STR_DEF      "STR1-N12K3-M3R1-W45.35.20-T35.65"

#define STR_OK       0
#define STR_NODIR    1
#define STR_NODATA   2

#define SR_NONE      0
#define SR_HISTORY   1       // fewer than 15 closed H4 bars up to h
#define SR_ATR       2       // ATR = 0 over the 14 bars

#define ST_NA        0
#define ST_WEAK      1
#define ST_MED       2
#define ST_STRONG    3

struct StrRec
  {
   int      state;
   int      reason;
   int      ctx;              // CtxState after processing the bar
   int      dir;              // +1 / -1 / 0
   int      leg;              // g_leg_seq after the bar (kept for the v2.58 arrow; not logged)
   long     chg12, chg3, path, trsum;   // points; up-positive closes changes
   long     net, recent;      // dir x chg12, dir x chg3
   long     num, den;         // raw = num / den exactly
   double   s_move, s_eff, s_mom;
   int      score;            // round half up of raw; -1 when not OK
   int      tier;
  };

StrRec   g_str[];                // one record per PROCESSED H4 bar, index = H4 index
int      g_str_n      = 0;
bool     g_str_wait   = false;   // a series did not deliver: the panel says "waiting"

long StrL(const double a, const double b) { return((long)MathRound((a - b) / _Point)); }
long StrAbs(const long v) { return(v < 0 ? -v : v); }
long StrMax(const long a, const long b) { return(a > b ? a : b); }
long StrMin(const long a, const long b) { return(a < b ? a : b); }

long StrTR(const int k)
  {
   double pc = g_h4[k-1].close;
   return(StrMax(StrL(g_h4[k].high, g_h4[k].low),
                 StrMax(StrAbs(StrL(g_h4[k].high, pc)), StrAbs(StrL(g_h4[k].low, pc)))));
  }

void StrReset()
  {
   g_str_n = 0;
   ArrayResize(g_str, 0, 512);
  }

void StrLog(const int h);

//--- the score of H4 bar h, from bars h-14 .. h and the context AFTER h -----
//--- (called last in H4ProcessBar: same point in build and live, Rule 51) ---
void StrOnH4Bar(const int h)
  {
   if(h < 0 || h >= g_h4_n) return;
   if(ArraySize(g_str) < h + 1) ArrayResize(g_str, h + 1, 512);
   StrRec r;
   ZeroMemory(r);
   r.state = STR_NODATA;  r.reason = SR_HISTORY;  r.ctx = (int)g_ctx;  r.leg = g_leg_seq;
   r.score = -1;  r.tier = ST_NA;  r.den = 1;
   if(h >= STR_ATR_N)
     {
      long T = 0;
      for(int k = h - STR_ATR_N + 1; k <= h; k++) T += StrTR(k);
      long path = 0;
      for(int i = h - STR_N + 1; i <= h; i++) path += StrAbs(StrL(g_h4[i].close, g_h4[i-1].close));
      r.trsum = T;  r.path = path;
      r.chg12 = StrL(g_h4[h].close, g_h4[h - STR_N].close);
      r.chg3  = StrL(g_h4[h].close, g_h4[h - STR_K].close);
      r.reason = SR_NONE;
      if(T <= 0)
         r.reason = SR_ATR;
      else if(g_ctx != CTX_BULLISH && g_ctx != CTX_BEARISH)
         r.state = STR_NODIR;
      else
        {
         r.state  = STR_OK;
         r.dir    = (g_ctx == CTX_BULLISH ? 1 : -1);
         r.net    = r.dir * r.chg12;
         r.recent = r.dir * r.chg3;
         // A = T / 14:  net / (3A) = 14 net / 3T,  recent / A = 14 recent / T
         long m = StrMin(StrMax(STR_ATR_N * r.net, 0), STR_MOVE_ATR * T);
         long e = StrMin(StrMax(r.net, 0), path);
         long q = StrMin(StrMax(STR_ATR_N * r.recent, 0), STR_MOM_ATR * T);
         // raw = W_MOVE m / (MOVE_ATR T) + W_EFF e / path + W_MOM q / (MOM_ATR T), exactly
         if(path > 0)
           {
            r.num = (STR_W_MOVE * m * STR_MOM_ATR + STR_W_MOM * q * STR_MOVE_ATR) * path
                    + STR_W_EFF * e * T * STR_MOVE_ATR * STR_MOM_ATR;
            r.den = T * path * STR_MOVE_ATR * STR_MOM_ATR;
           }
         else
           {
            r.num = STR_W_MOVE * m * STR_MOM_ATR + STR_W_MOM * q * STR_MOVE_ATR;   // path 0 -> e 0
            r.den = T * STR_MOVE_ATR * STR_MOM_ATR;
           }
         r.s_move = 100.0 * (double)m / (double)(STR_MOVE_ATR * T);
         r.s_eff  = (path > 0 ? 100.0 * (double)e / (double)path : 0.0);
         r.s_mom  = 100.0 * (double)q / (double)(STR_MOM_ATR * T);
         r.score  = (int)((2 * r.num + r.den) / (2 * r.den));
         r.tier   = (r.num < STR_T_MED * r.den ? ST_WEAK : (r.num < STR_T_STRONG * r.den ? ST_MED : ST_STRONG));
        }
     }
   g_str[h] = r;
   g_str_n  = h + 1;
   StrLog(h);
  }

string StrStateName(const int s)  { return(s == STR_OK ? "OK" : (s == STR_NODIR ? "NODIR" : "NODATA")); }
string StrReasonName(const int s) { return(s == SR_HISTORY ? "HISTORY" : (s == SR_ATR ? "ATR" : "-")); }
string StrTierName(const int t)   { return(t == ST_WEAK ? "WEAK" : (t == ST_MED ? "MED" : (t == ST_STRONG ? "STRONG" : "NA"))); }
string StrD6(const double v)      { return(DoubleToString(v, 6)); }

//--- one row per H4 bar: live, or in a build the bars that close inside the M5 window ---
void StrLog(const int h)
  {
   if(!InpLogSignals) return;
   datetime bar = CloseTimeOf(g_h4[h].time, PERIOD_H4);
   if(!g_live && (g_m5_n <= 0 || bar <= g_m5[0].time)) return;
   StrRec r = g_str[h];
   bool raw = (r.reason != SR_HISTORY);      // closes, path and TR exist from h = 14
   bool ok  = (r.state == STR_OK);
   PrintFormat("HMI-STR,%s,live=%d,bar=%s,ctx=%s,state=%s,reason=%s,def=%s,dir=%d,chg12=%s,chg3=%s,path=%s,tr_sum=%s," +
               "net=%s,recent=%s,s_move=%s,s_eff=%s,s_mom=%s,raw=%s,score=%s,tier=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, (g_live ? 1 : 0), TimeToString(bar, TIME_DATE|TIME_MINUTES), CtxName((CtxState)r.ctx),
               StrStateName(r.state), StrReasonName(r.reason), STR_DEF, r.dir,
               (raw ? IntegerToString(r.chg12) : "NA"), (raw ? IntegerToString(r.chg3) : "NA"),
               (raw ? IntegerToString(r.path) : "NA"), (raw ? IntegerToString(r.trsum) : "NA"),
               (ok ? IntegerToString(r.net) : "NA"), (ok ? IntegerToString(r.recent) : "NA"),
               (ok ? StrD6(r.s_move) : "NA"), (ok ? StrD6(r.s_eff) : "NA"), (ok ? StrD6(r.s_mom) : "NA"),
               (ok ? StrD6((double)r.num / (double)r.den) : "NA"), (ok ? IntegerToString(r.score) : "NA"),
               StrTierName(r.tier), g_inst, g_run_id, g_init_seq);
  }

//--- build end: the whole processed H4 window (not bars still waiting for M5) ---
void StrLogHist()
  {
   if(!InpLogSignals) return;
   int cnt[101];
   ArrayInitialize(cnt, 0);
   int ok = 0, nodir = 0, nodata = 0, tw = 0, tm = 0, ts = 0;
   for(int h = 0; h < g_str_n; h++)
     {
      if(g_str[h].state == STR_NODIR)  { nodir++;  continue; }
      if(g_str[h].state == STR_NODATA) { nodata++; continue; }
      ok++;
      int sc = g_str[h].score;
      if(sc < 0) sc = 0;
      if(sc > 100) sc = 100;
      cnt[sc]++;
      if(g_str[h].tier == ST_WEAK) tw++; else if(g_str[h].tier == ST_MED) tm++; else ts++;
     }
   string hs = "";
   for(int i = 0; i <= 100; i++) hs += (i > 0 ? ";" : "") + IntegerToString(cnt[i]);
   PrintFormat("HMI-STR-HIST,%s,live=0,def=%s,from=%s,to=%s,bars=%d,ok=%d,nodir=%d,nodata=%d,weak=%d,med=%d,strong=%d,h=%s,inst=%s,run=%I64d,init=%d",
               _Symbol, STR_DEF,
               (g_str_n > 0 ? TimeToString(CloseTimeOf(g_h4[0].time, PERIOD_H4), TIME_DATE|TIME_MINUTES) : "-"),
               (g_str_n > 0 ? TimeToString(CloseTimeOf(g_h4[g_str_n-1].time, PERIOD_H4), TIME_DATE|TIME_MINUTES) : "-"),
               g_str_n, ok, nodir, nodata, tw, tm, ts, hs, g_inst, g_run_id, g_init_seq);
  }

//--- waiting: a series did not deliver (or no build yet). Logged once per episode ---
void StrSetWait(const string src)
  {
   if(g_str_wait) return;
   g_str_wait = true;
   if(InpLogSignals)
      PrintFormat("HMI-STR-WAIT,%s,live=1,state=NODATA,reason=WAIT,src=%s,last=%s,inst=%s,run=%I64d,init=%d",
                  _Symbol, src,
                  (g_str_n > 0 ? TimeToString(CloseTimeOf(g_h4[g_str_n-1].time, PERIOD_H4), TIME_DATE|TIME_MINUTES) : "-"),
                  g_inst, g_run_id, g_init_seq);
  }

//====================== panel text (display) =========================
// The source stays ASCII: Chinese words are written as \uXXXX and decoded
// here, so the compiled strings do not depend on how the file is encoded.
#define ZH_STRENGTH  "\\u8D8B\\u52BF\\u5F3A\\u5EA6"                 // 趋势强度
#define ZH_STR_SHORT "\\u5F3A\\u5EA6"                               // 强度
#define ZH_WEAK      "\\u5F31"                                      // 弱
#define ZH_MED       "\\u4E2D\\u7B49"                               // 中等
#define ZH_STRONG    "\\u5F3A"                                      // 强
#define ZH_DOT       "\\u00B7"                                      // ·
#define ZH_ASOF      "\\u6570\\u636E\\u622A\\u81F3"                 // 数据截至
#define ZH_CLOSE     "\\u6536\\u76D8"                               // 收盘
#define ZH_WAIT      "\\u7B49\\u5F85\\u6570\\u636E"                 // 等待数据
#define ZH_LASTOK    "\\u4E0A\\u6B21\\u6709\\u6548\\u7ED3\\u679C"   // 上次有效结果
#define ZH_FEW       "\\u6837\\u672C\\u4E0D\\u8DB3"                 // 样本不足
#define ZH_FEW15     "H4 \\u4E0D\\u8DB3 15 \\u6839"                 // H4 不足 15 根
#define ZH_NA        "\\u4E0D\\u53EF\\u7528"                        // 不可用
#define ZH_ATRBAD    "ATR \\u65E0\\u6548"                           // ATR 无效
#define ZH_NORATE    "\\u6682\\u4E0D\\u8BC4\\u7EA7"                 // 暂不评级
#define ZH_RANGE     "\\u533A\\u95F4\\u9707\\u8361"                 // 区间震荡
#define ZH_TRANS     "\\u53CD\\u8F6C\\u5F85\\u786E\\u8BA4"          // 反转待确认
#define ZH_LP        "\\uFF08"                                      // （
#define ZH_RP        "\\uFF09"                                      // ）
#define ZH_COMMA     "\\uFF0C"                                      // ，
#define ZH_COUNT     "\\u8BA1\\u6570"                               // 计数
#define ZH_STRUCT    "\\u7ED3\\u6784\\u8BCA\\u65AD"                 // 结构诊断

int StrHex(const ushort c)
  {
   if(c >= '0' && c <= '9') return(c - '0');
   if(c >= 'A' && c <= 'F') return(c - 'A' + 10);
   if(c >= 'a' && c <= 'f') return(c - 'a' + 10);
   return(-1);
  }

string HMI_U(const string s)
  {
   string out = "";
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(s, i);
      if(c == '\\' && i + 5 < n && StringGetCharacter(s, i + 1) == 'u')
        {
         int v = 0;
         bool good = true;
         for(int k = 2; k <= 5; k++)
           {
            int d = StrHex(StringGetCharacter(s, i + k));
            if(d < 0) { good = false; break; }
            v = v * 16 + d;
           }
         if(good) { out += ShortToString((ushort)v); i += 5; continue; }
        }
      out += ShortToString(c);
     }
   return(out);
  }

string StrTierZh(const int t) { return(HMI_U(t == ST_WEAK ? ZH_WEAK : (t == ST_MED ? ZH_MED : ZH_STRONG))); }

string StrBarTime(const int h) { return(TimeToString(CloseTimeOf(g_h4[h].time, PERIOD_H4), TIME_DATE|TIME_MINUTES)); }

//--- the strength line; the same wording as strength_sim.panel_text -----
string StrPanelText()
  {
   string head = HMI_U(ZH_STRENGTH) + "  ";
   int h = g_str_n - 1;
   if(!g_ready || h < 0 || h >= g_h4_n)
      return(head + HMI_U(ZH_WAIT));
   StrRec r = g_str[h];
   if(g_str_wait)
     {
      if(r.state != STR_OK) return(head + HMI_U(ZH_WAIT));
      return(head + HMI_U(ZH_WAIT) + HMI_U(ZH_LP) + HMI_U(ZH_LASTOK) + " " + StrTierZh(r.tier) + " " + HMI_U(ZH_DOT) + " " +
             IntegerToString(r.score) + "/100" + HMI_U(ZH_COMMA) + StrBarTime(h) + " H4 " + HMI_U(ZH_CLOSE) + HMI_U(ZH_RP));
     }
   if(r.state == STR_NODATA)
      return(head + (r.reason == SR_HISTORY ? HMI_U(ZH_FEW) + HMI_U(ZH_LP) + HMI_U(ZH_FEW15) + HMI_U(ZH_RP)
                                            : HMI_U(ZH_NA) + HMI_U(ZH_LP) + HMI_U(ZH_ATRBAD) + HMI_U(ZH_RP)));
   if(r.state == STR_NODIR)
      return(head + HMI_U(ZH_NORATE) + HMI_U(ZH_LP) + HMI_U(r.ctx == CTX_RANGE ? ZH_RANGE : ZH_TRANS) + HMI_U(ZH_RP));
   return(head + StrTierZh(r.tier) + " " + HMI_U(ZH_DOT) + " " + IntegerToString(r.score) + "/100   " +
          HMI_U(ZH_ASOF) + " " + StrBarTime(h) + " H4 " + HMI_U(ZH_CLOSE));
  }

//--- the short form for PANEL_COMPACT -----------------------------------
string StrPanelShort()
  {
   string head = HMI_U(ZH_STR_SHORT) + " ";
   int h = g_str_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n) return(head + HMI_U(ZH_WAIT));
   StrRec r = g_str[h];
   if(r.state == STR_NODATA) return(head + HMI_U(r.reason == SR_HISTORY ? ZH_FEW : ZH_NA));
   if(r.state == STR_NODIR)  return(head + HMI_U(ZH_NORATE));
   return(head + StrTierZh(r.tier) + " " + IntegerToString(r.score) + "/100");
  }

//--- PANEL_COMPACT's time row: the H4 close the strength line belongs to (the same
//--- cursor); none while waiting - an older bar's time is not current then ---------
string StrPanelAsOf()
  {
   int h = g_str_n - 1;
   if(!g_ready || g_str_wait || h < 0 || h >= g_h4_n) return("");
   return(HMI_U(ZH_ASOF) + " " + StrBarTime(h) + " H4 " + HMI_U(ZH_CLOSE));
  }

#endif // HMI_STRENGTHENGINE_MQH
