//+------------------------------------------------------------------+
//| HMI_Defs.mqh                                                     |
//| H4 Context -> M5 Identification Indicator  v1.00                 |
//| Enums / structs / global state. MARK ONLY. Trend-following only. |
//+------------------------------------------------------------------+
#ifndef HMI_DEFS_MQH
#define HMI_DEFS_MQH

#define HMI_VERSION      "2.14"
#define HMI_PREFIX       "HMI"

//--- direction ------------------------------------------------------
#define DIR_NONE   0
#define DIR_BULL   1
#define DIR_BEAR  (-1)

//--- display glyphs (escaped so the file survives any code page) ----
#define SYM_UP     "\x25B2"
#define SYM_DOWN   "\x25BC"

//--- capacities (all fixed: no dynamic growth, Rule 59) -------------
#define MAX_H4_SWINGS   128
#define MAX_M5_SWINGS   128
#define MAX_H4_FVG      128
#define MAX_M5_FVG      256
#define MAX_POIS         64   // physical record store; the LOGICAL window is InpH4MaxPOIs
#define MAX_BLOCKS       64
#define MAX_BRKCAND      16
#define MAX_CYCLES       32
#define MAX_BPR          32
#define MAX_TRANGE       64
#define MAX_LIQ         128
#define MAX_OBJREG     1024
#define MAX_ALERTQ       32

//--- enums ----------------------------------------------------------
enum BlockState
  {
   BLOCK_NONE, BLOCK_CANDIDATE, BLOCK_CONFIRMED, BLOCK_ACTIVE,
   BLOCK_TOUCHED, BLOCK_ARMED, BLOCK_INVALID, BLOCK_EXPIRED
  };

enum BlockType { BT_M5_OB, BT_M5_BREAKER };

enum POIState
  {
   POI_NONE, POI_CANDIDATE, POI_CONFIRMED, POI_ACTIVE,
   POI_TOUCHED, POI_INVALID, POI_EXPIRED
  };

enum ZoneState
  {
   ZS_NONE, ZS_CANDIDATE, ZS_CONFIRMED, ZS_ACTIVE,
   ZS_TOUCHED, ZS_INVALID, ZS_EXPIRED
  };

enum CtxState { CTX_RANGE, CTX_BULLISH, CTX_BEARISH, CTX_TRANSITION };

enum CtxEventType
  {
   EV_NONE, EV_BOS_UP, EV_BOS_DOWN, EV_CHOCH_UP, EV_CHOCH_DOWN, EV_TIMEOUT
  };

enum CycleState { CY_NONE, CY_ACTIVE, CY_CLOSED };

enum ModelType
  {
   MDL_CISD = 0, MDL_MSS = 1, MDL_BPR = 2,
   MDL_PA_ENGULF = 3, MDL_PA_REJECT = 4, MDL_PA_BREAKRETEST = 5
  };
#define MDL_COUNT 6

enum ModelResult { MR_PENDING, MR_CONFIRMED, MR_PASS, MR_NA };

enum SessionEnd
  {
   SE_NONE, SE_POI_INVALID, SE_CONTEXT_FLIP, SE_TIMEOUT, SE_NEW_SESSION
  };

enum MarginMode { MARGIN_PIPS, MARGIN_POINTS, MARGIN_ATR_FRAC };   // D-6

// Which chart periods the M5 detail layer is visible on. Uses MT5's own
// OBJPROP_TIMEFRAMES, so one instance stays readable on an H4 chart without
// touching a single display switch.
enum M5LayerVis
  {
   M5LAYER_OFF,       // never drawn
   M5LAYER_M5_ONLY,   // only on an M5 chart
   M5LAYER_UPTO_M15,  // M1 / M5 / M15
   M5LAYER_ALWAYS     // every period (pre-v2.10 behaviour)
  };

enum PanelMode
  {
   PANEL_OFF,        // no panel at all
   PANEL_COMPACT,    // 2 lines (+ ADR / ATR if enabled)
   PANEL_FULL        // every diagnostic line
  };

//--- structs --------------------------------------------------------
struct HSwing
  {
   long              id;
   int               dir;            // DIR_BULL = swing high, DIR_BEAR = swing low
   int               bar_index;      // runtime index only, never persisted
   datetime          bar_time;
   datetime          confirm_time;   // anti future-leak key field
   double            price;
   bool              swept;
   datetime          swept_time;
  };

struct HFvg
  {
   long              id;
   int               dir;
   int               bar_index;      // third bar of the triple
   datetime          bar_time;
   datetime          confirm_time;
   double            hi;
   double            lo;
  };

struct H4POI
  {
   long              id;
   int               dir;
   datetime          origin_time;    // OB candle
   datetime          confirm_time;   // FVG completion
   double            hi;             // full OB range (Rule 5)
   double            lo;
   long              fvg_id;         // validation only
   POIState          state;
   datetime          touched_time;
   datetime          invalid_time;
   bool              out_of_window;  // pushed out of the logical window: record kept, graphics dropped
   int               session_count;  // refinement sessions started from this POI
   bool              awaiting_leave;  // timed out; price must fully leave before it re-arms
   int               vis;            // last drawn visual state (-2 = graphics removed)
  };

struct M5Block
  {
   long              id;
   int               dir;
   BlockType         block_type;
   datetime          origin_time;
   datetime          confirm_time;
   datetime          armed_time;
   datetime          touched_time;
   datetime          invalid_time;
   double            hi;
   double            lo;
   BlockState        state;
   long              session_id;
   long              src_block_id;   // breaker: source OB id, else -1
   long              fvg_id;
   bool              counter_dir;    // breaker material only, never ARMED (CONF-06)
   int               vis;
  };

struct BreakerCand
  {
   long              src_block_id;
   int               dir;            // flipped direction
   double            hi;
   double            lo;
   datetime          origin_time;
   int               break_index;
   datetime          break_time;
   bool              used;
  };

struct RefSession
  {
   long              id;
   long              poi_id;
   int               dir;
   int               start_index;
   datetime          start_time;
   datetime          end_time;
   SessionEnd        end_reason;
   bool              active;
  };

struct BPRZone
  {
   long              id;
   long              cycle_id;
   int               dir;
   double            hi;
   double            lo;
   datetime          formation_time;
   long              leg_bull_fvg_id;
   long              leg_bear_fvg_id;
   ZoneState         state;
   datetime          touched_time;
   datetime          invalid_time;
   int               vis;
  };

struct IdentificationCycle
  {
   long              cycle_id;
   long              block_id;
   int               dir;
   BlockType         anchor_type;
   double            anchor_hi;
   double            anchor_lo;
   datetime          armed_time;
   int               armed_index;    // runtime only
   CycleState        state;
   datetime          closed_time;
   datetime          session_start_time;   // D-2 early-leg bound

   ModelResult       result[MDL_COUNT];
   datetime          cfm_time[MDL_COUNT];
   double            cfm_price[MDL_COUNT];
   int               drawn_mask;
   int               logged_mask;

   //--- frozen references (Rule 19 / 26) ---
   double            cisd_level;
   datetime          cisd_ref_time;
   datetime          cisd_run_from;
   datetime          cisd_run_to;
   double            mss_level;
   datetime          mss_ref_time;

   //--- PA BREAK-RETEST local state ---
   double            br_ref;
   datetime          br_ref_time;
   int               br_break_index;
   bool              br_active;

   long              bpr_id;
   bool              ctx_changed;          // diagnostic (D-1)
   bool              anchor_invalidated;   // diagnostic (D-5)
  };

struct TRange
  {
   long              version_id;
   datetime          valid_from;
   datetime          valid_to;       // 0 = still live
   double            a_lo;
   double            a_hi;
   datetime          a_lo_time;
   datetime          a_hi_time;
   CtxEventType      created_by;
  };

struct LiqPool
  {
   long              id;
   int               type;           // DIR_BULL = BSL, DIR_BEAR = SSL
   double            price;
   datetime          origin_time;
   bool              swept;
   datetime          swept_time;
   int               vis;            // last drawn state (-2 = graphics removed)
  };

//====================== GLOBAL STATE ================================
string   g_inst          = "0000";     // instance tag (Rule 55)
long     g_next_id       = 1;
bool     g_live          = false;      // false during historical build (no alerts)
bool     g_ready         = false;

//--- H4 ---
HSwing   g_h4sw[MAX_H4_SWINGS];  int g_h4sw_n = 0;
HFvg     g_h4fvg[MAX_H4_FVG];    int g_h4fvg_n = 0;
H4POI    g_poi[MAX_POIS];        int g_poi_n = 0;
TRange   g_tr[MAX_TRANGE];       int g_tr_n = 0;
LiqPool  g_liq[MAX_LIQ];         int g_liq_n = 0;

CtxState g_ctx           = CTX_RANGE;
int      g_ctx_pending   = DIR_NONE;
int      g_ctx_strength  = 0;
bool     g_ctx_messy     = false;
datetime g_ctx_time      = 0;          // when current state was entered
int      g_ctx_bars      = 0;          // H4 bars spent in current state
int      g_h4_cursor     = 0;          // next H4 bar index to consume

//--- M5 ---
HSwing   g_m5sw[MAX_M5_SWINGS];  int g_m5sw_n = 0;
HFvg     g_m5fvg[MAX_M5_FVG];    int g_m5fvg_n = 0;
M5Block  g_blk[MAX_BLOCKS];      int g_blk_n = 0;
BreakerCand g_brk[MAX_BRKCAND];  int g_brk_n = 0;
RefSession  g_sess;

//--- cycles / bpr ---
IdentificationCycle g_cyc[MAX_CYCLES];  int g_cyc_n = 0;
int      g_active_cyc = -1;
BPRZone  g_bpr[MAX_BPR];         int g_bpr_n = 0;

//--- diagnostics (D-7) ---
int      g_diag_poi_rejected_gap = 0;
int      g_diag_blk_rejected_gap = 0;

//--- object registry (drawing layer asset only, Rule 53) ---
string   g_obj[MAX_OBJREG];      int g_obj_n = 0;

//--- alert queue ---
string   g_alertq[MAX_ALERTQ];   int g_alertq_n = 0;

#endif // HMI_DEFS_MQH
