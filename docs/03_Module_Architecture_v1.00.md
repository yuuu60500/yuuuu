# Code Architecture — v1.00

**对应 Rule 56 / 57 / 58 / 59。仍属设计阶段：以下为结构声明与职责划分，非实现代码。**

---

## 1. 文件结构

```
MQL5/Indicators/HMI/
   H4M5_Identification.mq5          // 入口：inputs / OnInit / OnCalculate / OnDeinit
MQL5/Include/HMI/
   HMI_Defs.mqh                     // enum / struct / 常量 / 方向 / 类型码
   HMI_Params.mqh                   // 所有 input 的集中持有与派生值（PipSize / MarginPoints）
   HMI_Util.mqh                     // Pts() / SafeIdx() / CloseTime() / H4VisibleTo() / Hash
   HMI_Series.mqh                   // M5 / H4 增量取数与游标（CopyRates 封装）
   HMI_SwingEngine.mqh              // 通用 Swing（H4 与 M5 共用，参数化 L/R）
   HMI_FVGEngine.mqh                // 通用 FVG（H4 与 M5 共用）
   HMI_H4StructureEngine.mqh        // BOS / CHOCH / Swing 消费
   HMI_H4ContextEngine.mqh          // Context 状态机 + ContextEvent 日志
   HMI_H4RangeEngine.mqh            // Versioned TradingRange + Liquidity
   HMI_H4POIEngine.mqh              // OB 候选 + FVG 连接 + POI 生命周期
   HMI_M5BlockEngine.mqh            // RefinementSession + M5 OB + Breaker + Block 生命周期
   HMI_CycleManager.mqh             // ARMED 仲裁 + Cycle 建立 / 关闭 + Reference 冻结
   HMI_CISDEngine.mqh
   HMI_MSSEngine.mqh
   HMI_BPREngine.mqh
   HMI_PriceActionEngine.mqh
   HMI_ObjectManager.mqh            // 唯一允许调用 Object* API 的模块
   HMI_AlertManager.mqh
```

**依赖方向（严格单向，禁止回边）：**

```
Defs / Params / Util / Series
      ↓
Swing / FVG
      ↓
H4Structure → H4Context → H4Range → H4POI
      ↓
M5Block → CycleManager
      ↓
CISD / MSS / BPR / PriceAction     (四者互不依赖 —— Rule 30 / 42 / 44 的结构保证)
      ↓
ObjectManager / AlertManager        (只读 State，不被任何上游引用)
```

> `CISDEngine` **不得** `#include` `MSSEngine`，反之亦然。
> 这是把 Rule 30 / 44「模型不互相 Consume」写进**编译期**的手段。

---

## 2. Enum 定义 (Rule 56)

```mql5
enum BlockState {
   BLOCK_NONE, BLOCK_CANDIDATE, BLOCK_CONFIRMED, BLOCK_ACTIVE,
   BLOCK_TOUCHED, BLOCK_ARMED, BLOCK_INVALID, BLOCK_EXPIRED
};

enum BlockType    { BT_M5_OB, BT_M5_BREAKER };

enum POIState     { POI_NONE, POI_CANDIDATE, POI_CONFIRMED, POI_ACTIVE,
                    POI_TOUCHED, POI_INVALID, POI_EXPIRED };

enum ZoneState    { ZS_NONE, ZS_CANDIDATE, ZS_CONFIRMED, ZS_ACTIVE,
                    ZS_TOUCHED, ZS_INVALID, ZS_EXPIRED };          // BPR 用

enum CtxState     { CTX_RANGE, CTX_BULLISH, CTX_BEARISH, CTX_TRANSITION };

enum CtxEventType { EV_NONE, EV_BOS_UP, EV_BOS_DOWN, EV_CHOCH_UP,
                    EV_CHOCH_DOWN, EV_TIMEOUT };

enum CycleState   { CY_NONE, CY_ACTIVE, CY_CLOSED };

enum ModelType    { MDL_CISD, MDL_MSS, MDL_BPR,
                    MDL_PA_ENGULF, MDL_PA_REJECT, MDL_PA_BREAKRETEST,
                    MDL_COUNT };                                    // = 6

enum ModelResult  { MR_PENDING, MR_CONFIRMED, MR_PASS, MR_NA };     // NA = 无 Reference

enum SessionEnd   { SE_NONE, SE_POI_INVALID, SE_CONTEXT_FLIP, SE_TIMEOUT, SE_NEW_SESSION };

enum MarginMode   { MARGIN_PIPS, MARGIN_POINTS, MARGIN_ATR_FRAC };   // D-6
```

---

## 3. Struct 定义 (Rule 56 / 57)

```mql5
struct Swing {
   long      id;
   int       dir;            // DIR_BULL = swing high, DIR_BEAR = swing low
   datetime  bar_time;
   datetime  confirm_time;   // ★ 反未来函数核心字段
   double    price;
   bool      swept;
   datetime  swept_time;
};

struct FVG {
   long      id;
   int       dir;
   datetime  bar_time;       // 三根中的第三根
   datetime  confirm_time;
   double    high, low;
   bool      used_in_bpr;
};

struct TradingRange {
   long      version_id;
   datetime  valid_from, valid_to;      // valid_to == 0 → 仍然有效
   double    anchor_low,  anchor_high;
   datetime  anchor_low_time, anchor_high_time;
   CtxEventType created_by;
};

struct LiquidityPool {
   long      id;
   int       type;           // DIR_BULL = BSL(Swing High) / DIR_BEAR = SSL(Swing Low)
   double    price;
   datetime  origin_time;
   bool      is_equal_hl;
   bool      swept;  datetime swept_time;
   bool      external;       // 相对当前 TradingRange
};

struct ContextEvent {
   long         seq;
   datetime     time;        // 触发事件的 H4 K 线收盘时刻
   CtxState     from_state, to_state;
   CtxEventType trigger;
   datetime     ref_swing_time;
   double       ref_price;
};

struct H4POI {
   long      id;
   int       dir;
   datetime  origin_time;    // OB K 线
   datetime  confirm_time;   // FVG 完成时刻
   double    high, low;      // ★ 完整 OB 区域（Rule 5）
   long      fvg_id;         // 仅验证用
   POIState  state;
   datetime  touched_time, invalid_time;
};

struct M5Block {
   long      id;
   datetime  origin_time;
   datetime  confirm_time;
   datetime  armed_time;
   double    high, low;
   int       direction;
   BlockType block_type;
   BlockState state;
   long      session_id;
   long      src_block_id;   // Breaker: 原 OB 的 id；OB: -1
   long      fvg_id;
   datetime  touched_time, invalid_time;
};

struct RefinementSession {
   long        id;
   long        poi_id;
   int         direction;
   datetime    start_bar_time, end_bar_time;
   SessionEnd  end_reason;
};

struct BPRZone {
   long      id, cycle_id;
   int       direction;
   double    high, low;
   datetime  formation_time;
   long      leg_bull_fvg_id, leg_bear_fvg_id;
   ZoneState state;
   datetime  touched_time, invalid_time;
};

struct IdentificationCycle {
   long      cycle_id;          // == block_id
   long      block_id;
   int       direction;
   BlockType anchor_type;
   double    anchor_high, anchor_low;
   datetime  armed_time;
   int       armed_bar_index;   // 运行期索引，随 shift 重算，不用于持久比较
   CycleState state;
   datetime  closed_time;

   // ---- 结果（每模型 max 1，Rule 43）----
   ModelResult result[MDL_COUNT];
   datetime    confirm_time[MDL_COUNT];
   double      confirm_price[MDL_COUNT];

   // ---- 冻结 Reference（Rule 19 / 26）----
   double    cisd_level;        datetime cisd_reference_time;
   datetime  cisd_run_from_time, cisd_run_to_time;
   double    mss_level;         datetime mss_reference_time;

   // ---- PA BREAK-RETEST 局部状态 ----
   double    br_ref_price;      datetime br_ref_time;
   datetime  br_break_time;     bool     br_break_active;

   // ---- BPR ----
   long      bpr_id;            // -1 = 尚未形成
};
```

> **Rule 15 泄漏的结构性根除：**
> `cisd_level` / `mss_level` / `br_ref_price` / `bpr_id` **全部**是 Cycle 的成员。
> 代码中**不存在**任何 `g_cisd_level` 之类的模块级变量。
> 新 Cycle = 新结构体（清零），旧 Reference 在语法上无法被访问。

---

## 4. 全局状态容器

```mql5
struct EngineState {
   // series cursors
   datetime  last_m5_processed;
   datetime  last_h4_processed;
   bool      warmup_done;
   bool      live_mode;                 // Historical Build 期间为 false（抑制 Alert）

   // H4
   CtxState  ctx;  int ctx_pending_dir; int ctx_strength; bool ctx_messy;
   Swing     h4_swings[64];   int h4_swing_count;
   TradingRange tr_versions[32]; int tr_count;
   LiquidityPool liq[64];     int liq_count;
   H4POI     pois[12];        int poi_count;

   // M5
   Swing     m5_swings[64];   int m5_swing_count;
   FVG       m5_fvgs[128];    int m5_fvg_count;
   M5Block   blocks[64];      int block_count;
   RefinementSession session;            // 同时只有 1 个 Active

   // Cycles
   IdentificationCycle cycles[20];  int cycle_count; int active_cycle_idx;

   // BPR
   BPRZone   bprs[20];        int bpr_count;

   // ids
   long      next_id;                    // 全局单调递增，仲裁兜底用（Spec §8.4）
};
```

全部**定长**（Rule 59 / P0 Array Out of Range 防御），
所有访问经 `SafeIdx(i, size)` 封装，越界返回 `-1` 并记录一次日志（不崩溃、不静默）。

---

## 5. 主流程函数签名

```mql5
// 入口
int  OnInit();
int  OnCalculate(...);      // 仅作触发器，不依赖传入 rates 的周期
void OnDeinit(const int reason);

// 历史与实时共用的唯一处理函数（Rule 51 的核心保证）
void ProcessClosedM5Bar(const int n);

// Phase 0 .. 7（Spec §17.2）
void Phase0_SyncH4(datetime m5_open_time);
void Phase1_UpdateM5Structure(const int n);
void Phase2_InvalidationPass(const int n);
void Phase3_MaintainSession(const int n);
void Phase4_Identification(const int n);      // 只处理 active cycle，要求 n > armed_bar_index
void Phase5_TouchAndArm(const int n);         // 仲裁 + Cycle 切换
void Phase5b_ArmedBarPA(const int n);         // D-4：仅 PA ENGULFING / REJECTION，仅 n == A
void Phase6_PostLifecycle(const int n);
void Phase7_DrawAndAlert(const int n);

// Identification（四个引擎互不引用）
bool CISD_Check (IdentificationCycle &cy, const int n);
bool MSS_Check  (IdentificationCycle &cy, const int n);
bool BPR_Check  (IdentificationCycle &cy, const int n);
bool PA_CheckEngulfing   (IdentificationCycle &cy, const int n);
bool PA_CheckRejection   (IdentificationCycle &cy, const int n);
bool PA_CheckBreakRetest (IdentificationCycle &cy, const int n);
// D-4：ARMED 当根专用入口，内部只允许读 bar n(=A) 与 n-1
bool PA_CheckEngulfingArmedBar(IdentificationCycle &cy, const int n);
bool PA_CheckRejectionArmedBar(IdentificationCycle &cy, const int n);

// Reference 冻结（仅在 ARMED 瞬间调用一次）
void Cycle_FreezeCISDReference(IdentificationCycle &cy, const int armed_idx);
void Cycle_FreezeMSSReference (IdentificationCycle &cy, const int armed_idx);
```

**Phase4 的固定写法（Rule 30 / 42 / 44 / 45 的落点）：**

```mql5
void Phase4_Identification(const int n) {
   if (g.active_cycle_idx < 0) return;
   IdentificationCycle cy = g.cycles[g.active_cycle_idx];
   if (cy.state != CY_ACTIVE) return;
   if (n <= cy.armed_bar_index) return;            // Rule 18

   // 六个独立调用，无短路、无 else if、无互相 consume
   CISD_Check(cy, n);
   MSS_Check(cy, n);
   BPR_Check(cy, n);
   PA_CheckEngulfing(cy, n);
   PA_CheckRejection(cy, n);
   PA_CheckBreakRetest(cy, n);

   g.cycles[g.active_cycle_idx] = cy;
}
```

> 禁止写成 `if (CISD_Check(...)) return;` 或 `else if`。
> 代码审计时（Rule 66 P1）这是一条硬性检查项。

---

## 6. ObjectManager 接口

```mql5
string OM_NewName(const int tt);                      // HMI_{INST}_{TT}_{SEQ}
bool   OM_Rect (const int tt, long owner, datetime t1, double p1, datetime t2, double p2, color c, ...);
bool   OM_Label(const int tt, long owner, datetime t, double price, const string text, color c, ...);
bool   OM_HLine(const int tt, long owner, datetime t1, datetime t2, double price, const string text, ...);
void   OM_SetState(long owner, int tt, int visual_state);   // ACTIVE / TOUCHED / INVALID 样式
void   OM_DropOldest(int keep_limit);
void   OM_DeleteOwnAll();                              // OnDeinit：只删自己 INST 前缀
```

**铁律：**
- 只有本模块出现 `Object*` API（Rule 53）
- 所有显示文字经 `OBJPROP_TEXT`，**绝不进 Object Name**（Rule 54）
- `OM_*` 只被 `Phase7_DrawAndAlert` 调用

---

## 7. 编译与质量目标 (Rule 70)

```
目标: 0 Errors / 0 Warnings  (#property strict 语义 + MQL5 默认告警)
当前: NOT COMPILE VERIFIED   — 本环境无 MetaEditor / MT5，无法执行编译
```

实现阶段必须由用户在 MetaEditor 中编译并回报，
**本项目在任何阶段都不会仅凭静态阅读声称 `0 Errors / 0 Warnings`。**
