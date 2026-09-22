# Replay & Repaint Test Plan — v1.00

**对应 Rule 71 / 72 / 73。本计划在 Phase 3（实现）完成后执行。**
**当前全部项目状态：NOT VERIFIED（无 MT5 环境）。**

---

## 1. 测试环境要求

| 项目 | 要求 |
|------|------|
| 平台 | MT5 Strategy Tester — Visual Mode，Every tick based on real ticks |
| 图表周期 | M5（指标逻辑与周期无关，但显示以 M5 为准） |
| 品种 | 至少 2 个：1 个 5-digit 外汇（EURUSD）+ 1 个非外汇（XAUUSD，用于验证 BRI-03 的 margin 退化） |
| 区间 | 至少覆盖 1 个完整的 BULLISH → CHOCH → TRANSITION → BEARISH 循环 |
| 日志 | 开启 Experts 日志，指标在每次模型确认时输出一行结构化日志（见 §5） |

---

## 2. 逐模块 Replay Test (Rule 71)

### 2.1 H4 POI

| 用例 | 步骤 | 期望 |
|------|------|------|
| POI-01 Formation | 定位一个 H4 Bullish OB + Bullish FVG | 矩形在 **FVG 第三根 K 线收盘**时出现，不早于此 |
| POI-02 Gap Reject | 定位一个 OB 与 FVG 之间有正空隙的形态 | **不**产生 POI（Rule 6） |
| POI-03 Touch | 价格回落触碰 POI | 触碰 K 线收盘时 POI → TOUCHED，同时 Refinement Session 建立 |
| POI-04 Invalidation | H4 收盘跌破 POI 下沿 − margin | POI → INVALIDATED，样式改变，**矩形不消失** |
| POI-05 Reload | 在 POI-03 之后 Refresh / 切周期 / 重启 MT5 | POI 的 confirm_time / zone / state 完全一致 |
| POI-06 窗口挤出（A-11） | 连续创建超过 `InpH4MaxPOIs` 个 POI | 最旧的 POI **图形消失**（不是停留在存活样式）；其内部记录仍在且为 `POI_EXPIRED` |
| POI-07 v1.00 等价性（A-11） | 同一区间跑 v1.00 与 v1.01，导出 CSV | 两份信号日志**逐行完全相同** |
| POI-08 复触默认关闭（A-06） | `InpPOIMaxSessions = 1`，Session 超时后价格回到同一 POI | **不**开启新 Session（与 v1.00 相同） |
| POI-09 复触开启（A-06） | `InpPOIMaxSessions = 2` | 必须先有一根已关闭 M5 完全脱离 POI 区间，之后再次触碰才开新 Session；价格一直压在区内则**永不**重启 |

### 2.2 M5 Order Block

| 用例 | 期望 |
|------|------|
| MOB-01 Formation | 仅在 Session 开始后（POI TOUCHED 之后）才可能出现 |
| MOB-02 FVG Connection | Touch / Overlap → 有效；正空隙 → **无效**（Rule 10） |
| MOB-03 Lookback 边界（D-3） | OB 起源 K 线可早于 Session 起点最多 2 根；第 3 根及更早**必须**被拒绝 |
| MOB-03b Confirm 硬约束 | 任何 Block 的 `confirm_time` **必须** ≥ `session.start_bar_time`，无一例外 |
| MOB-04 Touch → ARMED | 触碰 K 线收盘时出现 `M5 OB ARMED` 标签 |
| MOB-05 Invalidation | 收盘击穿 → INVALIDATED 样式；历史标记保留 |

### 2.3 Breaker

| 用例 | 期望 |
|------|------|
| BRK-01 原 OB | 逆势方向 M5 OB 被登记但**不 ARMED**（CONF-06） |
| BRK-02 Break | 收盘突破 + margin → 原 OB INVALIDATED + Breaker Candidate |
| BRK-03 FVG Connection | 翻转方向 FVG 与 Breaker zone Touch/Overlap → 有效；正空隙 → 无效 |
| BRK-04 Touch → ARMED | 出现 `M5 BREAKER ARMED` 标签（文字与 OB 不同） |

### 2.4 CISD

| 用例 | 期望 |
|------|------|
| CISD-01 Reference Freeze | ARMED 瞬间确定 `CISD Level`；此后 12 根内出现新的反方向 run **不移动**该 Level |
| CISD-02 Close Break | 仅当 `close[n-1]` 在未突破侧、`close[n]` 越过 + margin 时确认 |
| CISD-03 Margin | 越过量 < 0.3 pip → **不确认** |
| CISD-04 No Wick-only | 上影刺穿但收盘未过 → **不确认**（Rule 23） |
| CISD-05 Lookback 边界 | 窗口内无反方向 K 线 → 本 Cycle CISD 显示 `N/A`，无报错 |
| CISD-06 Reload | 重载后 `▲ CISD` 的时间 / 价格 / Level 完全一致 |
| CISD-07 显示 | 文字为 `▲ CISD`，**不是** `C`；Level 线带 `CISD Level` 文字 |

### 2.5 MSS

| 用例 | 期望 |
|------|------|
| MSS-01 Swing Freeze | ARMED 瞬间确定 `MSS Break Level`，之后新 Swing 出现**不改变**它 |
| MSS-02 Correct Swing | 选中的是"ARMED 前已确认、窗口内、方向正确、位于上方、未被吃掉"的最近一个 |
| MSS-03 No Future Swing | 构造一个 `bar_time < ARMED` 但 `confirm_time > ARMED` 的 Swing → **不得**被选用（最关键用例） |
| MSS-04 Close Break | Wick break 不确认 |
| MSS-05 无 Reference | 显示 `N/A`，不标记 |
| MSS-06 Reload | 完全一致 |
| MSS-07 显示 | `▲ MSS` + `MSS Break Level`，不是 `M` |

### 2.6 BPR

| 用例 | 期望 |
|------|------|
| BPR-01 First Only | 一个 Cycle 内只出现一个 `▲ BPR`，后续重叠不再标记（Rule 33） |
| BPR-02 Real Overlap | 两条方向相反的 FVG 必须**真实重叠**；相切（0 point）不算 |
| BPR-03 时序 | ARMED 之前已完整存在的 BPR **不被采用**（Rule 32） |
| BPR-03b 早腿边界（D-2） | 早腿 `confirm_time` 早于 Session 起点 → **不采用**；晚于 Session 起点但早于 ARMED → 采用 |
| BPR-04 Touch | 价格进入 BPR zone → 状态 TOUCHED，样式改变 |
| BPR-05 Invalidation | 收盘穿透 → INVALIDATED，**Rectangle 必须立即改样式**（Rule 36） |
| BPR-06 No Second | First BPR 失效后**不**寻找第二个（CONF-10） |

### 2.7 Price Action

| 用例 | 期望 |
|------|------|
| PA-01 Engulfing | 仅 ARMED 之后、与 Block 有交集、方向顺势、已关闭 K 线 |
| PA-02 Rejection | 影线比例满足且与 Block 有交互；bar 0 不作最终确认 |
| PA-03 Break-Retest | Reference 来自 ARMED 之后确认的局部结构；超时未 Hold → 作废 |
| PA-04 Setup Window | 所有 PA 参考不得超出 `InpSetupWindowBars` |
| PA-05 ARMED 当根（D-4） | `InpPAAllowArmedBarConfirm = true` 时，ARMED 当根的 REJECTION / ENGULFING **必须**被标记；CISD / MSS / BPR / BREAK-RETEST 在当根**必须不**被标记 |
| PA-06 ARMED 当根开关 | 设为 false 后重跑同一区间 → 仅 PA-05 的两类标记消失，其余逐行完全相同 |
| PA-07 ARMED 当根可重放 | PA-05 产生的标记在 Reload 后时间 / 价格 / Cycle 归属完全一致（D-4 论证的实测证据） |

### 2.8 Cycle 管理

| 用例 | 期望 |
|------|------|
| CYC-01 切换 | 新 Block ARMED → 旧 Cycle CLOSED，未形成模型记为 `PASS` |
| CYC-02 无泄漏 | 新 Cycle 的 CISD/MSS Level 与旧 Cycle **不同且独立重算** |
| CYC-03 同根冲突 | 旧 Cycle 在 bar n 确认模型 + 新 Block 在 bar n ARMED → **两者都记录**（Phase 4 先于 Phase 5） |
| CYC-04 同根多模型 | CISD + MSS + PA ENGULFING 同根 → **三个标记全部可见**，垂直堆叠（Rule 45） |
| CYC-05 无组合门槛 | 只出现 CISD、其它都没有 → `▲ CISD` 仍然正常显示（Rule 46） |

---

## 3. Repaint Test (Rule 72)

### 3.1 执行流程

```
1. Visual Mode 逐根 Replay 选定区间
2. 每出现一个标记，记录五元组：
      (model, direction, confirm_bar_time, confirm_price, reference_time/level)
   → 存为 RUN-A 清单（指标同时写 CSV 日志，见 §5）
3. 继续播放到区间末尾
4. Refresh（Ctrl+R） / 切换周期往返 / 重新加载指标 / 重启 MT5
5. 在同一区间、同一参数下重新运行 → RUN-B
6. 逐行 diff RUN-A 与 RUN-B
```

### 3.2 判定标准

| 检查项 | PASS 条件 |
|--------|----------|
| Signal 是否移动 | `confirm_bar_time` / `confirm_price` 逐行完全相同 |
| Signal 是否消失 | 行数与集合完全相同 |
| Reference 是否改变 | `cisd_level` / `mss_level` / `br_ref_price` 逐行相同 |
| 形成时间是否改变 | 同上 |
| Cycle 是否改变 | `cycle_id` 的分组结构相同（id 数值本身允许不同，分组边界必须相同） |

> **注意：** `cycle_id` 的绝对数值依赖 `next_id` 计数起点，重载后可能整体平移。
> 判定只看**分组边界**（哪些标记属于同一个 Cycle），不看绝对数值。
> 若需要绝对可比，把 `cycle_id` 改为 `armed_time` 的派生值 —— 实现阶段确认。

### 3.3 额外的压力场景

| 场景 | 目的 |
|------|------|
| 参数不变，只改 `InpMaxHistoryBarsM5`（5000 → 3000） | 验证"窗口最左端以外"结果一致（Spec §16.3 的边界声明） |
| 同一图表加载两个实例（不同参数） | 验证 Rule 55：互不删除对象；移除其中一个，另一个完好 |
| 周末 / 节假日跳空区间 | 验证 H4/M5 时间映射（Rule 50）与缺口 FVG 处理 |
| 换品种（EURUSD → XAUUSD） | 验证 pip / margin 退化（BRI-03）与对象命名冲突 |
| 三种 margin 模式切换（D-6） | `MARGIN_PIPS` 在 EURUSD 上与原结果逐行一致；XAUUSD 上 `MARGIN_PIPS` 应打印 0-point WARNING，`MARGIN_ATR_FRAC` 应给出非零 margin |

---

## 4. Audit 计划 (Rule 66 / 67)

实现完成后，按 P0 → P3 顺序重新逐行审计，每个问题按 Rule 67 格式输出：

```
ID / Severity / Module / Function / Location / Trigger /
Expected Behavior / Actual Behavior / Impact /
Historical Repaint: YES|NO / Future Leak: YES|NO /
Business Logic Impact: YES|NO / Recommended Fix / Confidence: HIGH|MEDIUM|LOW
```

**证据规则（Rule 67）：** 没有 Replay 证据的一律写 `Potential Risk`，
**不得**写 `Confirmed Bug`。

**修复节奏（Rule 68）：** `Audit → Issue #1 → Fix → Review → Compile → Replay Test → Issue #2`，
一次只修一个，禁止顺带重构 / 顺带加过滤 / 顺带改信号时序（Rule 69）。

---

## 5. 结构化日志（供 diff 使用）

指标在每次模型确认 / 状态迁移时向 Experts 日志输出一行 CSV：

```
HMI,<utc_iso>,<event>,<dir>,<cycle_id>,<block_id>,<model>,<confirm_time>,<price>,<ref_time>,<ref_level>,<state>
```

`Phase7` 之外不产生日志。Historical Build 期间日志前缀为 `HMI-BUILD`，
Live 期间为 `HMI-LIVE`，便于验证两者一致（Rule 51 的直接证据）。

---

## 6. 最终验收表模板 (Rule 73)

> 以下为**模板**。当前无任何实测证据，全部填 `NOT VERIFIED`。
> 只有在真实 MT5 上跑完 §2 / §3 之后才允许改写。

```
Architecture:          PASS        (规格层面，见 docs/01)
Business Logic:        PENDING     (等待 D-1..D-7 裁决)
Future Leak:           NOT VERIFIED (规格分析 PASS，代码未实现)
Historical Repaint:    NOT VERIFIED (规格分析 PASS，代码未实现)
H4/M5 Alignment:       NOT VERIFIED
H4 POI:                NOT VERIFIED
M5 OB:                 NOT VERIFIED
M5 Breaker:            NOT VERIFIED
ARMED:                 NOT VERIFIED
Cycle Management:      NOT VERIFIED
CISD:                  NOT VERIFIED
MSS:                   NOT VERIFIED
BPR:                   NOT VERIFIED
PA:                    NOT VERIFIED
Object Management:     NOT VERIFIED
Multi-instance:        NOT VERIFIED
Historical vs Live:    NOT VERIFIED
MetaEditor:            NOT COMPILE VERIFIED
Replay:                NOT VERIFIED
```
