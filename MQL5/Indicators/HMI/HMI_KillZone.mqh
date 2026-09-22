//+------------------------------------------------------------------+
//| HMI_KillZone.mqh — session (kill zone) HIGH / LOW levels         |
//|                                                                  |
//| Lines only: the HIGH and the LOW of the M5 bars inside each time |
//| window. No zone rectangle is drawn.                              |
//|                                                                  |
//| PURE DISPLAY. Nothing here is read by Phase 0-7, so a kill zone  |
//| can never filter, gate or move a mark (Rule 46 / 69).            |
//|                                                                  |
//| All hours are BROKER SERVER TIME, not your local time and not    |
//| New York time. Check the server clock in MT5 (Market Watch) and  |
//| shift these values yourself; they do not follow DST for you.     |
//+------------------------------------------------------------------+
#ifndef HMI_KILLZONE_MQH
#define HMI_KILLZONE_MQH
#include "HMI_Style.mqh"
#include "HMI_Series.mqh"

#define KZ_COUNT      4
#define MAX_KZ_INST  40      // KZ_COUNT x (InpKZDays + 1)

input group "=== Kill zone: general ==="
input bool   InpShowKillZones   = true;
input int    InpKZDays          = 5;     // how many days back to draw
input int    InpKZExtendBars    = 24;    // extend the levels N M5 bars to the right
input bool   InpKZShowLabel     = true;
input color  InpKZTextColor     = clrGainsboro;
input int    InpKZTextSize      = 7;

input group "=== Kill zone 1 ==="
input bool            InpKZ1On     = true;
input string          InpKZ1Name   = "ASIA";
input int             InpKZ1StartH = 2;      // server time
input int             InpKZ1StartM = 0;
input int             InpKZ1EndH   = 8;
input int             InpKZ1EndM   = 0;
input color           InpKZ1Color  = clrKhaki;
input ENUM_LINE_STYLE InpKZ1Style  = STYLE_DOT;
input int             InpKZ1Width  = 1;

input group "=== Kill zone 2 ==="
input bool            InpKZ2On     = true;
input string          InpKZ2Name   = "LONDON";
input int             InpKZ2StartH = 9;
input int             InpKZ2StartM = 0;
input int             InpKZ2EndH   = 12;
input int             InpKZ2EndM   = 0;
input color           InpKZ2Color  = clrSkyBlue;
input ENUM_LINE_STYLE InpKZ2Style  = STYLE_DOT;
input int             InpKZ2Width  = 1;

input group "=== Kill zone 3 ==="
input bool            InpKZ3On     = true;
input string          InpKZ3Name   = "NY AM";
input int             InpKZ3StartH = 14;
input int             InpKZ3StartM = 30;
input int             InpKZ3EndH   = 17;
input int             InpKZ3EndM   = 0;
input color           InpKZ3Color  = clrLightSalmon;
input ENUM_LINE_STYLE InpKZ3Style  = STYLE_DOT;
input int             InpKZ3Width  = 1;

input group "=== Kill zone 4 ==="
input bool            InpKZ4On     = false;
input string          InpKZ4Name   = "NY PM";
input int             InpKZ4StartH = 18;
input int             InpKZ4StartM = 0;
input int             InpKZ4EndH   = 20;
input int             InpKZ4EndM   = 0;
input color           InpKZ4Color  = clrThistle;
input ENUM_LINE_STYLE InpKZ4Style  = STYLE_DOT;
input int             InpKZ4Width  = 1;

//--- resolved config (parallel arrays: no strings inside structs) ---
bool      g_kz_on[KZ_COUNT];
string    g_kz_name[KZ_COUNT];
int       g_kz_start[KZ_COUNT];        // minutes from midnight
int       g_kz_end[KZ_COUNT];
StyleZone g_kz_style[KZ_COUNT];
StyleText TS_KZ;

struct KZInst
  {
   int       zone;
   datetime  anchor;      // midnight of the session day the window belongs to
   datetime  t_from;
   datetime  t_to;
   double    hi;
   double    lo;
   bool      complete;    // window fully elapsed -> levels are frozen
  };

void KZInit()
  {
   g_kz_on[0] = InpKZ1On; g_kz_name[0] = InpKZ1Name;
   g_kz_start[0] = InpKZ1StartH * 60 + InpKZ1StartM;
   g_kz_end[0]   = InpKZ1EndH   * 60 + InpKZ1EndM;
   SetZ(g_kz_style[0], InpKZ1Color, InpKZ1Style, InpKZ1Width, false);

   g_kz_on[1] = InpKZ2On; g_kz_name[1] = InpKZ2Name;
   g_kz_start[1] = InpKZ2StartH * 60 + InpKZ2StartM;
   g_kz_end[1]   = InpKZ2EndH   * 60 + InpKZ2EndM;
   SetZ(g_kz_style[1], InpKZ2Color, InpKZ2Style, InpKZ2Width, false);

   g_kz_on[2] = InpKZ3On; g_kz_name[2] = InpKZ3Name;
   g_kz_start[2] = InpKZ3StartH * 60 + InpKZ3StartM;
   g_kz_end[2]   = InpKZ3EndH   * 60 + InpKZ3EndM;
   SetZ(g_kz_style[2], InpKZ3Color, InpKZ3Style, InpKZ3Width, false);

   g_kz_on[3] = InpKZ4On; g_kz_name[3] = InpKZ4Name;
   g_kz_start[3] = InpKZ4StartH * 60 + InpKZ4StartM;
   g_kz_end[3]   = InpKZ4EndH   * 60 + InpKZ4EndM;
   SetZ(g_kz_style[3], InpKZ4Color, InpKZ4Style, InpKZ4Width, false);

   SetT(TS_KZ, InpKZTextColor, InpKZTextSize);
  }

datetime KZDayAnchor(const datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   d.hour = 0; d.min = 0; d.sec = 0;
   return(StructToTime(d));
  }

// Is bar time t inside window z? Windows may wrap midnight, in which case
// the session belongs to the day the window STARTED on.
bool KZContains(const int z, const datetime t, datetime &anchor)
  {
   int s = g_kz_start[z], e = g_kz_end[z];
   if(s == e) return(false);

   MqlDateTime d;
   TimeToStruct(t, d);
   int m = d.hour * 60 + d.min;
   datetime day = KZDayAnchor(t);

   if(s < e)
     {
      if(m < s || m >= e) return(false);
      anchor = day;
      return(true);
     }
   if(m >= s) { anchor = day;                       return(true); }   // before midnight
   if(m <  e) { anchor = day - (datetime)86400;     return(true); }   // after midnight
   return(false);
  }

datetime KZWindowEnd(const int z, const datetime anchor)
  {
   datetime e = anchor + (datetime)((long)g_kz_end[z] * 60);
   if(g_kz_end[z] <= g_kz_start[z]) e += (datetime)86400;             // wrapped
   return(e);
  }

// Pure function over the CLOSED M5 series: no state is touched.
int KZCollect(KZInst &out[])
  {
   int n = 0;
   ArrayResize(out, 0);
   if(g_m5_n <= 0) return(0);

   datetime newest = g_m5[g_m5_n - 1].time;
   datetime oldest = newest - (datetime)((long)(InpKZDays + 1) * 86400);

   for(int i = g_m5_n - 1; i >= 0; i--)
     {
      if(g_m5[i].time < oldest) break;
      for(int z = 0; z < KZ_COUNT; z++)
        {
         if(!g_kz_on[z]) continue;
         datetime anc = 0;
         if(!KZContains(z, g_m5[i].time, anc)) continue;

         int k = -1;
         for(int j = 0; j < n; j++)
            if(out[j].zone == z && out[j].anchor == anc) { k = j; break; }

         if(k < 0)
           {
            if(n >= MAX_KZ_INST) continue;
            ArrayResize(out, n + 1);
            out[n].zone     = z;
            out[n].anchor   = anc;
            out[n].hi       = g_m5[i].high;
            out[n].lo       = g_m5[i].low;
            out[n].t_from   = g_m5[i].time;
            out[n].t_to     = g_m5[i].time;
            out[n].complete = (CloseTimeOf(newest, PERIOD_M5) >= KZWindowEnd(z, anc));
            n++;
           }
         else
           {
            if(g_m5[i].high > out[k].hi)     out[k].hi     = g_m5[i].high;
            if(g_m5[i].low  < out[k].lo)     out[k].lo     = g_m5[i].low;
            if(g_m5[i].time < out[k].t_from) out[k].t_from = g_m5[i].time;
            if(g_m5[i].time > out[k].t_to)   out[k].t_to   = g_m5[i].time;
           }
        }
     }
   return(n);
  }

#endif // HMI_KILLZONE_MQH
