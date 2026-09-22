//+------------------------------------------------------------------+
//| HMI_Params.mqh — every threshold lives here (Rule 60 / Rule 22)  |
//+------------------------------------------------------------------+
#ifndef HMI_PARAMS_MQH
#define HMI_PARAMS_MQH
#include "HMI_Defs.mqh"

input group "=== General ==="
input int    InpMaxHistoryBarsM5   = 5000;   // M5 history window
input int    InpMaxHistoryBarsH4   = 500;    // H4 history window
input int    InpWarmupSuppressBars = 100;    // suppress marks on the oldest N M5 bars
input bool   InpLogSignals         = false;  // CSV signal log (build vs live diff)

input group "=== Break margin (Rule 22 / D-6) ==="
input MarginMode InpBreakMarginMode   = MARGIN_PIPS; // margin mode (default = spec behaviour)
input double InpBreakMarginPips       = 0.3;  // MARGIN_PIPS
input int    InpBreakMarginPoints     = 3;    // MARGIN_POINTS
input double InpBreakMarginATRFrac    = 0.05; // MARGIN_ATR_FRAC (ATR 14)

input group "=== OB / FVG connection (Rule 6 / Rule 10) ==="
input int    InpH4OBtoFVGMaxBars      = 3;
input double InpH4ConnectTolerancePips= 0.0;
input int    InpM5OBtoFVGMaxBars      = 3;
input double InpM5ConnectTolerancePips= 0.0;

input group "=== H4 structure / context ==="
input int    InpH4SwingLeft           = 2;
input int    InpH4SwingRight          = 2;
input int    InpH4MaxPOIs             = 12;
input int    InpH4POIMaxAgeBars       = 120;  // H4 bars
input int    InpH4TransitionMaxBars   = 18;   // H4 bars before TRANSITION -> RANGE
input int    InpPOIMaxSessions        = 1;    // refinement sessions per H4 POI (1 = v1.00 behaviour)

input group "=== M5 refinement ==="
input int    InpM5SwingLeft           = 2;
input int    InpM5SwingRight          = 2;
input int    InpM5RefinementMaxBars   = 288;
input int    InpM5BlockLookbackFromTouch = 2; // D-3 (was 0)
input int    InpM5MaxBlocks           = 64;
input bool   InpEnableBreaker         = false;  // D-10: OFF by default.
                                                // ON restores Rule 8 / Rule 11 and also
                                                // re-enables counter-direction OB tracking

input group "=== Identification ==="
input int    InpCISDLookbackBars      = 12;   // Rule 19
input int    InpSetupWindowBars       = 60;   // Rule 29 / 41
input bool   InpBPRRequireBothLegsAfterArmed = false; // CONF-04
input bool   InpBPREarlyLegFromSessionStart  = true;  // D-2
input bool   InpPAAllowArmedBarConfirm       = true;  // D-4 (PA ENGULFING / REJECTION only)
input bool   InpStopIdentificationOnBlockInvalidation = false; // D-5
input double InpPAEngulfMinBodyRatio  = 1.0;
input double InpPARejWickToBody       = 2.0;
input double InpPARejWickToRange      = 0.5;
input int    InpPABreakRetestMaxBars  = 12;
input double InpPARetestTolerancePips = 0.5;

input group "=== Display ==="
input bool   InpShowH4POI             = true;
input bool   InpShowTradingRange      = true;
input bool   InpShowLiquidity         = true;
input int    InpLiqMaxLines            = 10;   // per side; keeps the chart readable
input bool   InpShowM5Blocks          = true;
input bool   InpShowCounterDirBlocks  = false;  // CONF-06 breaker material
input bool   InpShowRejectedOB        = false;  // BRI-04 diagnostic
input bool   InpShowArmedLabel        = true;
input bool   InpShowCISD              = true;
input bool   InpShowMSS               = true;
input bool   InpShowBPR               = true;
input bool   InpShowPA                = true;
input bool   InpShowLevelLines        = true;
input double InpLabelStackOffsetPips  = 1.5;
input int    InpMaxCyclesKept         = 20;
input int    InpObjectHistoryLimit    = 500;
input int    InpLevelLineExtendBars   = 12;
input int    InpPreviewUpdateMs       = 250;   // bar-0 preview throttle


input group "=== Alerts ==="
input bool   InpAlertsEnabled         = false;
input bool   InpAlertPopup            = true;
input bool   InpAlertPush             = false;
input bool   InpAlertOnArmed          = true;
input bool   InpAlertOnCISD           = true;
input bool   InpAlertOnMSS            = true;
input bool   InpAlertOnBPR            = true;
input bool   InpAlertOnPA             = true;

#endif // HMI_PARAMS_MQH
