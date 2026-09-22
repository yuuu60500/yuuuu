//+------------------------------------------------------------------+
//| HMI_Style.mqh — every visual property, one place                 |
//|                                                                  |
//| Pure presentation: nothing here is read by the detection engines |
//| (Phase 0-7), so no style change can move a mark.                 |
//|                                                                  |
//| NOTE (MT5 behaviour): a line style other than SOLID is only      |
//| rendered when width == 1. Set width 1 if you want DASH / DOT.    |
//+------------------------------------------------------------------+
#ifndef HMI_STYLE_MQH
#define HMI_STYLE_MQH
#include "HMI_Defs.mqh"

//================== fonts / panel ==================================
input group "=== Display layers ==="
input M5LayerVis InpM5Layer = M5LAYER_UPTO_M15;   // M5 blocks / ARMED / CISD / MSS / BPR / PA
                                                  // H4 POI, trading range, liquidity and kill
                                                  // zones are never hidden by this

input group "=== Style: font & panel ==="
input string InpFontName          = "Arial";       // font for every text object
input PanelMode       InpPanelMode   = PANEL_COMPACT;      // OFF / COMPACT / FULL
input ENUM_BASE_CORNER InpPanelCorner = CORNER_LEFT_UPPER;
input int    InpPanelX            = 10;
input int    InpPanelY            = 18;
input color  InpPanelColor        = clrWhite;      // default row colour
input int    InpPanelFontSize     = 8;
input bool   InpPanelColorByContext = true;       // colour the context row by direction
input color  InpPanelCtxBullColor   = clrLimeGreen;
input color  InpPanelCtxBearColor   = clrTomato;
input color  InpPanelCtxRangeColor  = clrSilver;  // RANGE and TRANSITION

//================== H4 POI =========================================
input group "=== Style: H4 POI zone ==="
input color           InpPOIBullColor   = clrTeal;
input ENUM_LINE_STYLE InpPOIBullStyle   = STYLE_SOLID;
input int             InpPOIBullWidth   = 1;
input color           InpPOIBearColor   = clrMaroon;
input ENUM_LINE_STYLE InpPOIBearStyle   = STYLE_SOLID;
input int             InpPOIBearWidth   = 1;
input color           InpPOITouchColor  = clrDarkTurquoise;   // touched: session started
input ENUM_LINE_STYLE InpPOITouchStyle  = STYLE_DASH;
input int             InpPOITouchWidth  = 1;
input color           InpPOIDeadColor   = clrDimGray;
input ENUM_LINE_STYLE InpPOIDeadStyle   = STYLE_DOT;
input int             InpPOIDeadWidth   = 1;
input bool            InpPOIFill        = false;
input color           InpPOITextColor   = clrTeal;
input int             InpPOITextSize    = 8;

//================== H4 trading range / liquidity ===================
input group "=== Style: H4 trading range & liquidity ==="
input color           InpTRangeColor    = clrSlateGray;
input ENUM_LINE_STYLE InpTRangeStyle    = STYLE_DOT;
input int             InpTRangeWidth    = 1;
input color           InpBSLColor       = clrSlateGray;      // buy-side liquidity
input ENUM_LINE_STYLE InpBSLStyle       = STYLE_DOT;
input int             InpBSLWidth       = 1;
input color           InpSSLColor       = clrSlateGray;      // sell-side liquidity
input ENUM_LINE_STYLE InpSSLStyle       = STYLE_DOT;
input int             InpSSLWidth       = 1;

//================== M5 blocks ======================================
input group "=== Style: M5 order block ==="
input color           InpOBBullColor    = clrDodgerBlue;
input ENUM_LINE_STYLE InpOBBullStyle    = STYLE_SOLID;
input int             InpOBBullWidth    = 1;
input color           InpOBBearColor    = clrOrangeRed;
input ENUM_LINE_STYLE InpOBBearStyle    = STYLE_SOLID;
input int             InpOBBearWidth    = 1;

input group "=== Style: M5 breaker block ==="
input color           InpBRKBullColor   = clrRoyalBlue;
input ENUM_LINE_STYLE InpBRKBullStyle   = STYLE_DASH;
input int             InpBRKBullWidth   = 1;
input color           InpBRKBearColor   = clrCrimson;
input ENUM_LINE_STYLE InpBRKBearStyle   = STYLE_DASH;
input int             InpBRKBearWidth   = 1;

input group "=== Style: M5 block states ==="
input color           InpBlkTouchColor  = clrSilver;         // touched but NOT armed
input ENUM_LINE_STYLE InpBlkTouchStyle  = STYLE_DASHDOT;
input int             InpBlkTouchWidth  = 1;
input color           InpBlkArmedColor  = clrGold;
input ENUM_LINE_STYLE InpBlkArmedStyle  = STYLE_SOLID;
input int             InpBlkArmedWidth  = 2;
input color           InpBlkDeadColor   = clrDimGray;
input ENUM_LINE_STYLE InpBlkDeadStyle   = STYLE_DOT;
input int             InpBlkDeadWidth   = 1;
input bool            InpBlkFill        = false;
input color           InpArmedTextColor = clrGold;
input int             InpArmedTextSize  = 9;

//================== BPR ============================================
input group "=== Style: BPR zone ==="
input color           InpBPRColor       = clrMediumPurple;
input ENUM_LINE_STYLE InpBPRStyle       = STYLE_SOLID;
input int             InpBPRWidth       = 1;
input color           InpBPRTouchColor  = clrPlum;
input ENUM_LINE_STYLE InpBPRTouchStyle  = STYLE_DASH;
input int             InpBPRTouchWidth  = 1;
input color           InpBPRDeadColor   = clrDimGray;
input ENUM_LINE_STYLE InpBPRDeadStyle   = STYLE_DOT;
input int             InpBPRDeadWidth   = 1;
input bool            InpBPRFill        = false;

//================== level lines ====================================
input group "=== Style: CISD Level / MSS Break Level ==="
input color           InpCISDLineColor  = clrWhite;
input ENUM_LINE_STYLE InpCISDLineStyle  = STYLE_DASH;
input int             InpCISDLineWidth  = 1;
input color           InpMSSLineColor   = clrWhite;
input ENUM_LINE_STYLE InpMSSLineStyle   = STYLE_DASHDOT;
input int             InpMSSLineWidth   = 1;
input color           InpLevelTextColor = clrWhite;
input int             InpLevelTextSize  = 7;

//================== model labels ===================================
input group "=== Style: CISD label ==="
input color  InpCISDBullColor   = clrLime;
input color  InpCISDBearColor   = clrRed;
input int    InpCISDTextSize    = 9;

input group "=== Style: MSS label ==="
input color  InpMSSBullColor    = clrAqua;
input color  InpMSSBearColor    = clrMagenta;
input int    InpMSSTextSize     = 9;

input group "=== Style: BPR label ==="
input color  InpBPRBullColor    = clrMediumPurple;
input color  InpBPRBearColor    = clrMediumPurple;
input int    InpBPRTextSize     = 9;

input group "=== Style: PA ENGULFING label ==="
input color  InpPAEngBullColor  = clrChartreuse;
input color  InpPAEngBearColor  = clrTomato;
input int    InpPAEngTextSize   = 8;

input group "=== Style: PA REJECTION label ==="
input color  InpPARejBullColor  = clrSpringGreen;
input color  InpPARejBearColor  = clrOrangeRed;
input int    InpPARejTextSize   = 8;

input group "=== Style: PA BREAK-RETEST label ==="
input color  InpPABRBullColor   = clrPaleGreen;
input color  InpPABRBearColor   = clrLightCoral;
input int    InpPABRTextSize    = 8;

input group "=== Style: bar-0 preview ==="
input color  InpPreviewColor    = clrGold;
input int    InpPreviewTextSize = 7;

//===================================================================
//                    resolved style records
//===================================================================
struct StyleZone
  {
   color            clr;
   ENUM_LINE_STYLE  style;
   int              width;
   bool             fill;
  };

struct StyleText
  {
   color  clr;
   int    size;
  };

StyleZone ZS_POI_BULL,  ZS_POI_BEAR,  ZS_POI_TOUCH, ZS_POI_DEAD;
StyleZone ZS_TRANGE,    ZS_BSL,       ZS_SSL;
StyleZone ZS_OB_BULL,   ZS_OB_BEAR,   ZS_BRK_BULL,  ZS_BRK_BEAR;
StyleZone ZS_BLK_TOUCH, ZS_BLK_ARMED, ZS_BLK_DEAD;
StyleZone ZS_BPR,       ZS_BPR_TOUCH, ZS_BPR_DEAD;
StyleZone ZS_CISD_LINE, ZS_MSS_LINE;

StyleText TS_POI, TS_ARMED, TS_LEVEL, TS_PANEL, TS_PREVIEW;

void SetZ(StyleZone &z, const color c, const ENUM_LINE_STYLE s, const int w, const bool f)
  { z.clr = c; z.style = s; z.width = MathMax(1, w); z.fill = f; }

void SetT(StyleText &t, const color c, const int s)
  { t.clr = c; t.size = MathMax(5, s); }

void StylesInit()
  {
   SetZ(ZS_POI_BULL,  InpPOIBullColor,  InpPOIBullStyle,  InpPOIBullWidth,  InpPOIFill);
   SetZ(ZS_POI_BEAR,  InpPOIBearColor,  InpPOIBearStyle,  InpPOIBearWidth,  InpPOIFill);
   SetZ(ZS_POI_TOUCH, InpPOITouchColor, InpPOITouchStyle, InpPOITouchWidth, InpPOIFill);
   SetZ(ZS_POI_DEAD,  InpPOIDeadColor,  InpPOIDeadStyle,  InpPOIDeadWidth,  false);

   SetZ(ZS_TRANGE,    InpTRangeColor,   InpTRangeStyle,   InpTRangeWidth,   false);
   SetZ(ZS_BSL,       InpBSLColor,      InpBSLStyle,      InpBSLWidth,      false);
   SetZ(ZS_SSL,       InpSSLColor,      InpSSLStyle,      InpSSLWidth,      false);

   SetZ(ZS_OB_BULL,   InpOBBullColor,   InpOBBullStyle,   InpOBBullWidth,   InpBlkFill);
   SetZ(ZS_OB_BEAR,   InpOBBearColor,   InpOBBearStyle,   InpOBBearWidth,   InpBlkFill);
   SetZ(ZS_BRK_BULL,  InpBRKBullColor,  InpBRKBullStyle,  InpBRKBullWidth,  InpBlkFill);
   SetZ(ZS_BRK_BEAR,  InpBRKBearColor,  InpBRKBearStyle,  InpBRKBearWidth,  InpBlkFill);
   SetZ(ZS_BLK_TOUCH, InpBlkTouchColor, InpBlkTouchStyle, InpBlkTouchWidth, InpBlkFill);
   SetZ(ZS_BLK_ARMED, InpBlkArmedColor, InpBlkArmedStyle, InpBlkArmedWidth, InpBlkFill);
   SetZ(ZS_BLK_DEAD,  InpBlkDeadColor,  InpBlkDeadStyle,  InpBlkDeadWidth,  false);

   SetZ(ZS_BPR,       InpBPRColor,      InpBPRStyle,      InpBPRWidth,      InpBPRFill);
   SetZ(ZS_BPR_TOUCH, InpBPRTouchColor, InpBPRTouchStyle, InpBPRTouchWidth, InpBPRFill);
   SetZ(ZS_BPR_DEAD,  InpBPRDeadColor,  InpBPRDeadStyle,  InpBPRDeadWidth,  false);

   SetZ(ZS_CISD_LINE, InpCISDLineColor, InpCISDLineStyle, InpCISDLineWidth, false);
   SetZ(ZS_MSS_LINE,  InpMSSLineColor,  InpMSSLineStyle,  InpMSSLineWidth,  false);

   SetT(TS_POI,     InpPOITextColor,   InpPOITextSize);
   SetT(TS_ARMED,   InpArmedTextColor, InpArmedTextSize);
   SetT(TS_LEVEL,   InpLevelTextColor, InpLevelTextSize);
   SetT(TS_PANEL,   InpPanelColor,     InpPanelFontSize);
   SetT(TS_PREVIEW, InpPreviewColor,   InpPreviewTextSize);
  }

bool M5LayerOn() { return(InpM5Layer != M5LAYER_OFF); }

int M5LayerMask()
  {
   switch(InpM5Layer)
     {
      case M5LAYER_M5_ONLY:  return(OBJ_PERIOD_M5);
      case M5LAYER_UPTO_M15: return(OBJ_PERIOD_M1 | OBJ_PERIOD_M5 | OBJ_PERIOD_M15);
      case M5LAYER_ALWAYS:   return(OBJ_ALL_PERIODS);
     }
   return(OBJ_NO_PERIODS);
  }

// the context row reads as a direction at a glance, without parsing text
color CtxPanelColor(const color fallback)
  {
   if(!InpPanelColorByContext) return(fallback);
   if(g_ctx == CTX_BULLISH) return(InpPanelCtxBullColor);
   if(g_ctx == CTX_BEARISH) return(InpPanelCtxBearColor);
   return(InpPanelCtxRangeColor);              // RANGE / TRANSITION
  }

//--- state -> style resolvers (keeps OM_SyncAll free of ternaries) --
StyleZone POIStyleOf(const H4POI &p)
  {
   if(p.state == POI_INVALID || p.state == POI_EXPIRED) return(ZS_POI_DEAD);
   if(p.state == POI_TOUCHED)                           return(ZS_POI_TOUCH);
   return(p.dir == DIR_BULL ? ZS_POI_BULL : ZS_POI_BEAR);
  }

StyleZone BlockStyleOf(const M5Block &b)
  {
   if(b.state == BLOCK_INVALID || b.state == BLOCK_EXPIRED) return(ZS_BLK_DEAD);
   if(b.state == BLOCK_ARMED)                               return(ZS_BLK_ARMED);
   if(b.state == BLOCK_TOUCHED)                             return(ZS_BLK_TOUCH);
   if(b.block_type == BT_M5_BREAKER)
      return(b.dir == DIR_BULL ? ZS_BRK_BULL : ZS_BRK_BEAR);
   return(b.dir == DIR_BULL ? ZS_OB_BULL : ZS_OB_BEAR);
  }

StyleZone BPRStyleOf(const BPRZone &z)
  {
   if(z.state == ZS_INVALID) return(ZS_BPR_DEAD);
   if(z.state == ZS_TOUCHED) return(ZS_BPR_TOUCH);
   return(ZS_BPR);
  }

// one label style per model, per direction (Rule 45: all six stay visible)
StyleText ModelStyleOf(const int m, const int dir)
  {
   StyleText t;
   switch(m)
     {
      case MDL_CISD:
         SetT(t, dir == DIR_BULL ? InpCISDBullColor : InpCISDBearColor, InpCISDTextSize);   break;
      case MDL_MSS:
         SetT(t, dir == DIR_BULL ? InpMSSBullColor : InpMSSBearColor, InpMSSTextSize);      break;
      case MDL_BPR:
         SetT(t, dir == DIR_BULL ? InpBPRBullColor : InpBPRBearColor, InpBPRTextSize);      break;
      case MDL_PA_ENGULF:
         SetT(t, dir == DIR_BULL ? InpPAEngBullColor : InpPAEngBearColor, InpPAEngTextSize); break;
      case MDL_PA_REJECT:
         SetT(t, dir == DIR_BULL ? InpPARejBullColor : InpPARejBearColor, InpPARejTextSize); break;
      default:
         SetT(t, dir == DIR_BULL ? InpPABRBullColor : InpPABRBearColor, InpPABRTextSize);   break;
     }
   return(t);
  }

#endif // HMI_STYLE_MQH
