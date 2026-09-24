# H4 Context → M5 Identification Indicator
# Architecture & Logic Specification — v1.00

**Status:** Specification only. No MQL5 written. **NOT COMPILE VERIFIED.**
**Baseline:** v1.00 = Frozen Baseline (Rule 74)
**Scope:** Trend-Following only (Rule 2). MARK ONLY (Rule 1).

> 阅读顺序建议：先读 `docs/02_Conflict_And_Business_Rule_Issues_v1.00.md`
> 的 CONF-01 / CONF-02 / CONF-05，再回到本文件第 8、9 章。

---

## 目录

| # | 章节 |
|---|------|
| 1 | Indicator Objective |
| 2 | H4 Context State Machine |
| 3 | H4 Structure |
| 4 | H4 POI |
| 5 | M5 OB |
| 6 | M5 Breaker |
| 7 | M5 Block State Machine |
| 8 | ARMED |
| 9 | Identification Cycle |
| 10 | CISD |
| 11 | MSS |
| 12 | BPR |
| 13 | PA (Engulfing / Rejection / Break-Retest) |
| 14 | Object Architecture |
| 15 | MTF Time Mapping |
| 16 | Historical Build |
| 17 | Live Update |
| 18 | Repaint Analysis |
| 19 | Future Leak Analysis |
| 20 | Performance Architecture |
| A | Input Parameter Table (Rule 60) |
| B | 全局定义 (Pip / Margin / Tolerance / Direction) |

---

## 0. 全局公理 (Axioms)

这 6 条是整份规格的地基，后续每一章都必须可以回溯到这里。

**AX-1 — Closed Bar Commit (Rule 49)**
任何"状态迁移"与"模型确认"只在**已关闭 K 线**上提交。
bar 0 只能用于 preview / current price interaction / drawing update，
绝不参与 Historical Confirmation。

**AX-2 — Unified Forward Clock (Rule 50 / 51)**
系统只有一个时钟：**M5 已关闭 K 线的收盘时刻**。
H4 只能在其 K 线**收盘时刻 ≤ 当前 M5 收盘时刻**时被读入。
不存在 `h4_index == m5_index` 的映射，只存在 `datetime` 映射。

**AX-3 — Reference ≠ Confirmation (解决 Rule 17 与 Rule 19/25 的表面冲突)**

| 概念 | 是否允许取自 ARMED 之前 |
|------|------------------------|
| **Reference**（CISD Level / MSS Break Level / PA 参考结构） | **允许**，且必须在 ARMED 当时已经可知 |
| **Confirmation**（真正把一个模型标出来的那根 K 线） | **禁止**，必须严格晚于 ARMED bar |

Rule 17 禁止的是"把 ARMED 之前已经发生的结构事件回头算成本 Cycle 的**信号**"，
不是禁止使用 ARMED 之前**已经确认**的价格水平作为**参考**。
Rule 19（向前回看 12 根找 CISD Reference）与 Rule 25（使用 ARMED 之前已确认的 Swing）
正是 Reference，不是 Confirmation。二者不冲突。

**AX-4 — Immutable Event Record (Rule 47)**
所有已确认对象是**不可变记录**：
`{id, direction, confirm_time, confirm_bar_time, level/zone, reference_time, cycle_id}`
之后只允许追加 `state` 变化（例如 `ACTIVE → INVALIDATED`），
**不允许**修改 time / level / reference / candle，**不允许**删除。
失效 = 改变显示样式，不是"历史上从未发生"。

**AX-5 — Deterministic Ordering (Rule 16 / 45)**
同一根已关闭 K 线内如果同时满足多个条件，必须由**固定相位顺序**决定，
且该顺序在 Historical Build 与 Live 中完全一致（见第 17 章 Phase 0–7）。

**AX-6 — State ≠ Drawing (Rule 53)**
Chart Object 永远是状态的**投影**，绝不是状态本身。
任何逻辑判断都不允许调用 `ObjectFind()` / `ObjectGetDouble()`。

---

## 1. Indicator Objective

### 1.1 目标

在 M5 图表上，为交易员标记出一条**完整、可追溯、不重绘、无未来函数**的顺势识别链：

```
H4 在哪里 (Context)
→ H4 哪个位置值得关注 (POI)
→ 价格到了没有 (Touch)
→ M5 在这个位置给出了什么精细结构 (M5 Block)
→ 价格确认了这个结构没有 (ARMED)
→ ARMED 之后市场说了什么 (CISD / MSS / BPR / PA)
```

### 1.2 明确不做

- 不产生 Entry / Exit / SL / TP / Lot
- 不做多模型组合门槛（Rule 46：禁止"两个模型同时出现才显示"）
- 不做胜率统计、不做信号评分排序
- 不做逆势模式
- 不因为"历史图更好看"而改变任何 Signal Timing（Rule 69）

### 1.3 输出物

| 类别 | 输出 |
|------|------|
| Context | H4 Context 文字面板 + H4 Trading Range + Liquidity 标记 |
| POI | H4 OB 完整区域 Rectangle（含状态色） |
| M5 Block | M5 OB / M5 BREAKER Rectangle + `M5 OB ARMED` / `M5 BREAKER ARMED` 标签 |
| Identification | `▲/▼ CISD`、`▲/▼ MSS`、`▲/▼ BPR`、`▲/▼ PA ENGULFING`、`▲/▼ PA REJECTION`、`▲/▼ PA BREAK-RETEST` |
| Level | `CISD Level` 水平线、`MSS Break Level` 水平线、`BPR Zone` Rectangle |

**禁止缩写为 `C` / `M` / `B`（Rule 24 / 28 / 37 / 61）。**

### 1.4 方向约束 (Rule 2 的强制推论)

在 v1.00 中，**方向是全链路一致的单向过滤**：

| H4 Context | 允许的 H4 POI | 允许的 M5 Block | 允许的 Identification 方向 |
|-----------|--------------|-----------------|---------------------------|
| BULLISH | Bullish OB (Demand) | Bullish OB / Bullish Breaker | 仅 `▲` |
| BEARISH | Bearish OB (Supply) | Bearish OB / Bearish Breaker | 仅 `▼` |
| RANGE | 不新建 Setup | — | — |
| TRANSITION | 不新建 Setup | — | — |

> 这意味着：`▼ CISD` 只可能出现在 BEARISH Context 的 Cycle 里。
> 同一个 Cycle 内**不会**出现方向相反的两个模型。
> 详见 CONF-03（TRANSITION / RANGE 期间既有 Cycle 的处理）。

---

## 2. H4 Context State Machine

### 2.1 States

```
CTX_RANGE        // 无有效方向 / 双向失败
CTX_BULLISH      // 确认上升趋势
CTX_BEARISH      // 确认下降趋势
CTX_TRANSITION   // CHOCH 之后、新趋势确认之前
```

TRANSITION 额外带一个 `pending_direction`（CHOCH 指向的方向），
它**不是**趋势方向，只是"待确认方向"。

### 2.2 输入事件

Context 只被以下**已关闭 H4 K 线**产生的事件驱动：

| 事件 | 定义 |
|------|------|
| `EV_BOS_UP` | H4 Close > 最近一个已确认 Swing High + BreakMargin |
| `EV_BOS_DOWN` | H4 Close < 最近一个已确认 Swing Low − BreakMargin |
| `EV_CHOCH_UP` | 在 BEARISH 中，Close > 最近一个已确认 Lower High + BreakMargin |
| `EV_CHOCH_DOWN` | 在 BULLISH 中，Close < 最近一个已确认 Higher Low − BreakMargin |
| `EV_TIMEOUT` | TRANSITION 持续超过 `InpH4TransitionMaxBars` 根 H4 |

BOS 与 CHOCH 的区分只看**当前 Context**：
顺着当前 Context 方向破坏结构 = BOS；逆着当前 Context 方向破坏结构 = CHOCH。
初始 `CTX_RANGE` 状态下没有"顺逆"，第一次结构突破一律视为 BOS。

### 2.3 State Transition Table (Frozen)

| From | Event | To | 说明 |
|------|-------|----|------|
| RANGE | EV_BOS_UP | BULLISH | 建立新趋势 |
| RANGE | EV_BOS_DOWN | BEARISH | 建立新趋势 |
| BULLISH | EV_BOS_UP | BULLISH | 趋势延续，更新 TR（见 3.4） |
| BULLISH | EV_CHOCH_DOWN | TRANSITION(pending=DOWN) | **不直接翻转**（Rule 3） |
| BEARISH | EV_BOS_DOWN | BEARISH | 趋势延续 |
| BEARISH | EV_CHOCH_UP | TRANSITION(pending=UP) | **不直接翻转** |
| TRANSITION(pending=DOWN) | EV_BOS_DOWN | BEARISH | 同方向结构确认 → 新趋势成立 |
| TRANSITION(pending=DOWN) | EV_BOS_UP | BULLISH | Transition 失败，原趋势恢复 |
| TRANSITION(pending=UP) | EV_BOS_UP | BULLISH | 新趋势成立 |
| TRANSITION(pending=UP) | EV_BOS_DOWN | BEARISH | Transition 失败，原趋势恢复 |
| TRANSITION | EV_TIMEOUT | RANGE | 久拖不决 = 区间 |
| RANGE | EV_TIMEOUT | RANGE | 保持 |

**TRANSITION 中的"同方向 Structure Confirmation"精确定义（Rule 3）：**

```
BULLISH
→ EV_CHOCH_DOWN 发生在 H4 bar c，被跌破的 Higher Low = HL_c
→ 进入 TRANSITION(pending=DOWN)，记录 anchor_swing_low = HL_c
→ 之后必须出现「一个在 bar c 之后新确认的 Swing Low」并被 H4 Close 跌破
   （即 EV_BOS_DOWN，且被破的 Swing Low 的 confirm_time > c）
→ BEARISH
```

即：**CHOCH 之后必须再有一次"新的、独立的"同方向结构破坏**，
不允许用同一个 HL_c 既当 CHOCH 又当 BOS（否则一根 K 线就翻转趋势，违反 Rule 3）。

### 2.4 Context Strength / Quality（显示用，不参与过滤）

```
strength = 同方向连续 BOS 次数（进入该 Context 后累计，遇 CHOCH 归零）
quality  = { CLEAN, MESSY }
           CLEAN : 自 Context 建立以来无 CHOCH
           MESSY : 出现过至少一次失败的 TRANSITION
```

按 Rule 69，strength / quality **不作为任何过滤条件**，仅用于面板显示。

### 2.5 Context 的时间戳与不可变性

每次 Context 变化产生一条不可变记录：

```
ContextEvent { seq, time(H4 close time), from_state, to_state, trigger_event, ref_swing_time, ref_price }
```

Context **当前值**是可变的，但**历史 ContextEvent 列表不可变**。
这保证第 18 章 Repaint Analysis 里 Context 面板与历史标记永远自洽。

---

## 3. H4 Structure

### 3.1 Swing 定义 (Fractal)

```
Swing High at bar i  ⇔  high[i] = max(high[i-L .. i+R])  且 high[i] > high[i-1], high[i] > high[i+1]
Swing Low  at bar i  ⇔  low[i]  = min(low[i-L .. i+R])   且 low[i]  < low[i-1],  low[i]  < low[i+1]

L = InpH4SwingLeft  (default 2)
R = InpH4SwingRight (default 2)
```

**Confirmation Time（关键反未来函数条款）：**

```
swing.bar_time     = time[i]          // 摆动点本身所在 K 线
swing.confirm_time = close_time(i+R)  // 右侧第 R 根 K 线收盘时刻
```

系统在任何时刻 `T` 只允许看到 `confirm_time <= T` 的 Swing。
一个 Swing 的 `bar_time` 早于 ARMED、但 `confirm_time` 晚于 ARMED —— **不可用**（Rule 25 / 48）。

平局处理（`high[i] == high[j]`，i<j，同在窗口内）：
以**更早**的 bar 为准（`i`），后者不再登记为独立 Swing，改登记为 `equal_high`（Liquidity 用）。
这保证 Historical Build 与 Live 得到同一集合（AX-5）。

### 3.2 BOS / CHOCH

统一使用 **H4 Close 确认 + BreakMargin**，禁止 Wick-only：

```
Break Up   ⇔  close[h] > level + BreakMargin
Break Down ⇔  close[h] < level − BreakMargin
```

`level` 只能来自 `confirm_time <= close_time(h)` 的已确认 Swing。
每个 Swing 只能被"消费"一次：被突破后标记 `swept = true`，不再作为后续 BOS/CHOCH 的 level。

### 3.3 Trading Range — Versioned Anchor (Rule 4)

Trading Range 不是一个会被随意移动的变量，而是**版本化不可变记录**：

```
TradingRange {
   version_id,
   valid_from (datetime),   // 建立时刻
   valid_to   (datetime),   // 0 = 仍然有效
   anchor_low, anchor_low_time,
   anchor_high, anchor_high_time,
   created_by  { BOS_UP, BOS_DOWN, CHOCH_UP, CHOCH_DOWN }
}
```

**建立 / 更新规则（Frozen）：**

| 触发 | 动作 |
|------|------|
| `EV_BOS_UP` | 关闭旧版本（`valid_to = 事件时刻`），新建版本：`anchor_low` = 本次 BOS 之前最后一个已确认 Swing Low；`anchor_high` = 突破后的当前极值高 |
| `EV_BOS_DOWN` | 镜像 |
| `EV_CHOCH_*` | 关闭旧版本，新建版本，`created_by = CHOCH_*`，两端 anchor 冻结为 CHOCH 当时的已确认 Swing |
| 新确认 Swing High（BULLISH 中） | **Forward-Only Extension**：若 `swing.price > anchor_high`，关闭旧版本并新建版本（anchor_low 继承，anchor_high 更新） |
| 其它任何情况 | **不动** |

**关键点：** "更新 Trading Range"永远表现为 *关闭旧版本 + 新建版本*，
**绝不是**就地修改历史版本的字段。这样既满足 Rule 4（不回头改历史 Anchor），
又允许 Range 随行情向前扩展。每根 H4 K 线最多产生 1 个新版本。

### 3.4 Liquidity

```
LiquidityPool {
   id, type { BSL, SSL }, price, origin_time,
   kind { SWING, EQUAL_HL },
   state { INTACT, SWEPT }, swept_time
}
```

- `BSL` = 已确认 Swing High（及其 equal highs）
- `SSL` = 已确认 Swing Low（及其 equal lows）
- `SWEPT` 判定：H4 **Wick** 越过即可（流动性是被"扫"的，不需要收盘确认），
  但 `swept_time` 只在该 H4 K 线**收盘后**提交（AX-1：提交时刻 = 收盘时刻）。
- 相对 Trading Range：`EXTERNAL`（在 TR 之外）/ `INTERNAL`（在 TR 之内）

Liquidity 在 v1.00 **只标记、不过滤**（Rule 69）。

---

## 4. H4 POI

### 4.1 POI 定义

```
POI Zone = 完整 H4 Order Block 的 [low, high]      (Rule 5)
FVG      = 仅用于「验证 OB」，不参与 POI Zone 几何  (Rule 5)
```

### 4.2 OB Candidate

| 方向 | OB Candidate |
|------|-------------|
| Bullish POI | 一根 **Bearish** H4 K 线（`close < open`） |
| Bearish POI | 一根 **Bullish** H4 K 线（`close > open`） |

Doji（`close == open`）**不作为** OB Candidate（无方向 → 无法定义"反方向"）。

### 4.3 FVG 定义（三根 K 线）

```
Bullish FVG @ bar i :  low[i] > high[i-2]
                       zone = [ high[i-2], low[i] ]
                       confirm_time = close_time(i)

Bearish FVG @ bar i :  high[i] < low[i-2]
                       zone = [ high[i], low[i-2] ]
                       confirm_time = close_time(i)
```

### 4.4 OB ↔ FVG Connection Rule (Rule 6 — FROZEN)

对候选 OB（bar `o`），在 `o+1 .. o+InpH4OBtoFVGMaxBars`（default 3）范围内
寻找**同 POI 方向**的 FVG：

```
Bullish:
   gap_points = round( (fvg_low  - ob_high) / _Point )
   VALID   ⇔  gap_points <= tol_points          // 含 Touch(=0) 与 Overlap(<0)
   INVALID ⇔  gap_points >  tol_points          // 真实正价格空隙

Bearish:
   gap_points = round( (ob_low - fvg_high) / _Point )
   VALID   ⇔  gap_points <= tol_points
   INVALID ⇔  gap_points >  tol_points
```

`tol_points = round(InpH4ConnectTolerancePips * PipSize / _Point)`，**default 0**。

> 一律使用**整数 point 比较**，禁止 `double ==`（浮点等值在 MQL5 不可靠）。
> `Touch = VALID / Overlap = VALID / Positive Gap = INVALID`（Rule 6，冻结）。

若在窗口内找到多个合法 FVG：取**最早**的那个（`o` 之后第一个），
保证 Historical 与 Live 一致（AX-5）。

### 4.5 POI Lifecycle

```
POI_CANDIDATE   // OB K 线被识别（尚无 FVG）
POI_CONFIRMED   // FVG 出现且 Connection 合法 → 冻结 confirm_time
POI_ACTIVE      // 已确认且未被触碰，等待价格
POI_TOUCHED     // 被 M5 已关闭 K 线触碰 → 启动 M5 Refinement
POI_INVALIDATED // 被击穿
POI_EXPIRED     // 超出保留窗口 / 超过 InpH4MaxPOIs
```

| 迁移 | 条件 | 提交时刻 |
|------|------|---------|
| CANDIDATE → CONFIRMED | 4.4 Connection 通过，且 Context 方向匹配（1.4） | FVG 的 H4 K 线收盘 |
| CONFIRMED → ACTIVE | 立即 | 同上 |
| ACTIVE → TOUCHED | 存在 M5 已关闭 K 线：Bullish `low_m5 <= poi.high` 且 `high_m5 >= poi.low`；Bearish 镜像。且该 M5 K 线 `open_time >= poi.confirm_time` | 该 M5 K 线收盘 |
| 任意 → INVALIDATED | Bullish：H4 `close < poi.low − BreakMargin`；Bearish：H4 `close > poi.high + BreakMargin` | 该 H4 K 线收盘 |
| 任意 → EXPIRED | `now − confirm_time > InpH4POIMaxAgeBars × H4` 或被 `InpH4MaxPOIs` 挤出 | 检查时 |

**注意 `open_time >= poi.confirm_time` 这一条（反未来函数关键）：**
一根 M5 K 线不能去"触碰"一个在它收盘那一刻才刚被确认的 H4 POI。

### 4.6 POI 排序与上限

同时保留最多 `InpH4MaxPOIs`（default 12）个 `ACTIVE/TOUCHED` POI，
按 `confirm_time` 降序保留最新的。被挤出者 → `POI_EXPIRED`（记录保留，不删除历史标记）。

---

## 5. M5 Order Block

### 5.1 触发前提 (Rule 7 — FROZEN)

```
H4 POI 未 TOUCHED  →  不启动 M5 Refinement  →  不产生任何 M5 Block
```

M5 Refinement Session 定义：

```
RefinementSession {
   session_id,
   poi_id,
   start_bar_time,   // = 触发 POI_TOUCHED 的那根 M5 K 线的 time
   end_bar_time,     // 0 = 进行中
   direction,        // 继承 POI 方向
   end_reason { POI_INVALIDATED, CONTEXT_FLIP, TIMEOUT, NEW_SESSION }
}
```

**Session 结束条件（任一满足）：**

| 条件 | 说明 |
|------|------|
| 对应 H4 POI 变为 `INVALIDATED` | 位置已被证伪 |
| H4 Context 方向翻转（BULLISH↔BEARISH） | 顺势前提消失 |
| 超过 `InpM5RefinementMaxBars`（default 288 = 1 天 M5） | 防止无限窗口 |
| 另一个 H4 POI 被触碰并开启新 Session | 见下 |

**同时只允许 1 个 Active Refinement Session。**
若新 POI 被触碰时旧 Session 仍活跃：旧 Session 以 `NEW_SESSION` 结束，
其 `CANDIDATE/CONFIRMED/ACTIVE` 状态的 Block 全部 → `BLOCK_EXPIRED`；
**已经 ARMED 的 Cycle 不受影响**，只能由"新的 ARMED"结束（Rule 15）。

### 5.2 M5 Block 搜索窗口 (Rule 7 的强制推论)

```
候选 OB 的 origin bar index  >=  session.start_bar_index − InpM5BlockLookbackFromTouch
InpM5BlockLookbackFromTouch  default = 2   (D-3 裁决，2026-09-22)

硬约束（不受该参数影响）：
   block.confirm_time >= session.start_bar_time
```

这条直接禁止了"扫描整个 M5 历史，把任意 M5 Block 关联到未来才触碰的 H4 POI"。

**D-3 裁决说明（default 0 → 2）：**
`lookback = 0` 会系统性漏掉下面这个常见形态：

```
bar N-1 : 阴线，收在 POI 上沿之上（尚未触碰）
bar N   : 下影刺入 POI（触碰，Session 起点），强阳收高（位移）
bar N+2 : Bullish FVG 完成
```

按定义，这里的 Bullish OB 是 **bar N-1**（位移前最后一根反方向 K 线），
而它早于 Session 起点 1 根 → 被 `lookback = 0` 排除，整个 M5 OB 消失。

回溯 2 根**不引入未来函数**：Block 的 `confirm_time` 仍然必须 ≥ Session 起点
（FVG 只能在触碰之后完成），只是几何来源的 K 线可以早 1–2 根。
Rule 7 禁止的是"扫描整个 M5 历史关联未来才触碰的 POI"，与有界 2 根回溯无关。

### 5.3 M5 OB 定义 (Rule 9 — FROZEN)

```
Bullish M5 OB:
   OB Candle = 上涨位移前的一根 Bearish M5 K 线 (close < open)
   +  同方向 Bullish FVG
   +  OB/FVG Connection 合法 (第 5.4 节)

Bearish M5 OB:
   OB Candle = 下跌位移前的一根 Bullish M5 K 线 (close > open)
   +  同方向 Bearish FVG
   +  OB/FVG Connection 合法
```

Zone = **完整 OB K 线的 [low, high]**（与 H4 POI 同规则，Rule 5）。

### 5.4 M5 OB ↔ FVG Connection (Rule 10 — FROZEN，不得删除)

与 4.4 完全同构，参数换为 `InpM5OBtoFVGMaxBars`(default 3) / `InpM5ConnectTolerancePips`(default 0)：

```
Touch      (gap == 0)  = VALID
Overlap    (gap  < 0)  = VALID
Price Gap  (gap  > 0)  = INVALID
```

### 5.5 确认时刻

```
m5_ob.origin_time  = OB K 线的 time
m5_ob.confirm_time = FVG 第三根 K 线的收盘时刻
```

**Block 从 `confirm_time` 起才存在**，绝不允许在 `origin_time` 那一刻就被视为已存在（Rule 48）。
Rectangle 的左边界画在 `origin_time`（视觉需要），但对象**创建于** `confirm_time`（见 14.5）。

---

## 6. M5 Breaker Block

### 6.1 定义链 (Rule 11 — FROZEN)

```
Previously Valid OB              // 必须是本 Session 内已登记的 M5 OB
   ↓
OB 被价格有效突破                 // Closed M5 Candle + BreakMargin
   ↓
原 OB 角色发生转换                // Zone 几何不变，direction 翻转
   ↓
Breaker Candidate
   ↓
新方向 FVG 出现
   ↓
Breaker 与该 FVG Touch / Overlap  // 与 5.4 同规则
   ↓
Valid Breaker Block
```

### 6.2 "Previously Valid OB" 的范围界定

```
原 OB 必须满足：
  - 属于当前 Active RefinementSession
  - 曾经达到过 BLOCK_CONFIRMED 或更高状态
  - 其 direction 与当前 Session 方向 **相反**
```

> 这里存在一个重要取舍：Session 方向是顺势方向（例如 BULLISH），
> 而能翻转成 **Bullish Breaker** 的原 OB 必须是 **Bearish OB**（逆势方向）。
> 因此系统必须在 Session 内**同时追踪双方向的 M5 OB**，
> 但只有**顺势方向**的 Block 可以进入 `ARMED`（Rule 2 / 1.4）。
> 逆势方向的 OB 只作为 Breaker 的原料，**永不 ARMED、永不建立 Cycle**。
> 见 CONF-06。

### 6.3 "有效突破" 定义

```
Bearish OB 被向上突破 ⇔ 存在已关闭 M5 K 线 b :
      close[b] > ob.high + BreakMargin
      且 b 在 ob.confirm_time 之后

Bullish OB 被向下突破 ⇔ close[b] < ob.low − BreakMargin
```

突破发生时：原 OB → `BLOCK_INVALIDATED`（记录保留），同时产生一个
`BreakerCandidate { zone = 原 OB zone, direction = 翻转后方向, break_time = close_time(b) }`。

### 6.4 Breaker 的 FVG 连接

在 `b+1 .. b+InpM5OBtoFVGMaxBars` 内寻找**翻转后方向**的 FVG，
用 5.4 同一套整数 point 判定：

```
Bullish Breaker（zone 来自原 Bearish OB）:
   gap_points = round( (fvg_low - breaker.high) / _Point )
   VALID ⇔ gap_points <= tol_points
```

> **注意：** Breaker 的 zone 是原 OB 的完整 [low, high]，
> 而 Bullish Breaker 要求 Bullish FVG 与之 Touch/Overlap。
> 由于突破已经发生，价格通常已在 zone 上方，
> 因此该 FVG 多半出现在 zone 上沿附近 —— 这正是 Rule 11 的意图。
> 若 FVG 完全脱离 zone 之上并留下正空隙 → `INVALID`（Rule 11 明确要求）。

### 6.5 Breaker 确认时刻

```
breaker.origin_time  = 原 OB K 线 time      (zone 几何来源)
breaker.break_time   = 突破 K 线收盘时刻
breaker.confirm_time = FVG 第三根 K 线收盘时刻   // Block 从此刻起存在
```

### 6.6 与普通 OB 的并列关系 (Rule 8)

```
M5 Block = { M5_OB, M5_BREAKER }
```

两者：
- 共用同一个 `M5Block` 结构与同一套生命周期（第 7 章）
- 都可以被触碰 → `ARMED` → 建立独立 Identification Cycle
- 显示文字不同：`M5 OB ARMED` vs `M5 BREAKER ARMED`（Rule 13 / 61）
- 在"同一根 K 线多个 Block"的仲裁中地位平等（第 8.4 节）

---

## 7. M5 Block State Machine (Rule 12 / 56)

### 7.1 States

```
BLOCK_NONE
BLOCK_CANDIDATE     // OB K 线 / Breaker Candidate 已识别，FVG 尚未验证
BLOCK_CONFIRMED     // FVG Connection 通过，Block 正式存在
BLOCK_ACTIVE        // 已确认、方向顺势、未被触碰，等待价格
BLOCK_TOUCHED       // 被触碰，但**未**成为 Cycle Anchor（见 8.4 仲裁落选）
BLOCK_ARMED         // 被触碰且被选为 Cycle Anchor → 建立 Identification Cycle
BLOCK_INVALIDATED   // 被击穿 / 被用作 Breaker 原料
BLOCK_EXPIRED       // Session 结束、超龄、超出数量上限
```

> `TOUCHED` 与 `ARMED` 的区别（Rule 12 要求两者并存的唯一合理解释）：
> **TOUCHED = 发生了合法触碰但未获得 Cycle**；**ARMED = 获得 Cycle**。
> 逆势方向的 Block（Breaker 原料）被触碰时也只能到 `TOUCHED`，永不 `ARMED`。

### 7.2 Transition Table

| From | To | 条件 | 提交时刻 |
|------|----|------|---------|
| NONE | CANDIDATE | OB K 线识别 / Breaker Candidate 生成 | 该 K 线收盘 |
| CANDIDATE | CONFIRMED | FVG Connection VALID（5.4 / 6.4） | FVG 第三根收盘 |
| CANDIDATE | EXPIRED | 窗口内未找到合法 FVG | 窗口末根收盘 |
| CONFIRMED | ACTIVE | 方向 == Session 方向 | 同 CONFIRMED |
| CONFIRMED | TOUCHED | 方向 != Session 方向（逆势原料）且被触碰 | 触碰 K 线收盘 |
| ACTIVE | ARMED | 触碰 + 通过 8.4 仲裁 | 触碰 K 线收盘 |
| ACTIVE | TOUCHED | 触碰但 8.4 仲裁落选 | 触碰 K 线收盘 |
| TOUCHED | ARMED | 后续 K 线再次触碰且仲裁胜出 | 该 K 线收盘 |
| ACTIVE/TOUCHED/ARMED | INVALIDATED | Bullish：`close < block.low − BreakMargin`；Bearish 镜像 | 该 K 线收盘 |
| CONFIRMED/ACTIVE | INVALIDATED | 被突破并转为 Breaker 原料（6.3） | 突破 K 线收盘 |
| 任意 | EXPIRED | Session 结束 / 超出 `InpM5MaxBlocks` | 检查时 |

### 7.3 ARMED Block 被 INVALIDATED 时的行为

```
默认（InpStopIdentificationOnBlockInvalidation = false）：
   Block → BLOCK_INVALIDATED（显示更新）
   其 Identification Cycle **继续运行**
   只有「新的 ARMED」才能结束该 Cycle（Rule 15 / 44 字面要求）
```

这是对 Rule 15 与 Rule 44 的字面遵守。见 **BRI-02**（我认为这条值得讨论，但未经批准不擅自更改）。

---

## 8. ARMED

### 8.1 Touch 定义

```
Bullish Block:  已关闭 M5 K 线 n 满足  low[n]  <= block.high  且 high[n] >= block.low
Bearish Block:  已关闭 M5 K 线 n 满足  high[n] >= block.low   且 low[n]  <= block.high
```

即：**K 线区间与 Block 区间存在交集**（wick 触碰即算触碰，这是"触碰"的定义，
与"突破确认需要收盘"是两件事）。

约束（反未来函数）：`time[n] >= block.confirm_time`。
一根 K 线不能触碰一个在它收盘瞬间才被确认的 Block。

### 8.2 ARMED 提交时刻 (AX-1 的直接应用)

```
即使真实触碰发生在 bar 0 的 tick 流中间，
ARMED 也只在**该 K 线收盘**时正式提交。
```

**为什么这不会造成 Live 与 Historical 不一致：**
K 线的 `high/low` 在其生命周期内单调扩张，
因此 bar 0 期间发生的任何触碰，都必然保留在该 K 线收盘后的 `[low, high]` 里。
Historical 重建读到同一根已关闭 K 线 → 得到同一个 ARMED 事件与同一个时间戳。

bar 0 期间可显示 `PENDING TOUCH` 预览样式（虚线 / 半透明），
但**不写入任何 State**（AX-6）。

### 8.3 ARMED 前置条件（全部必须满足）

1. Block 状态为 `ACTIVE`
2. `block.direction == session.direction == context.direction`
3. 所属 RefinementSession 仍然 Active
4. `time[n] >= block.confirm_time`
5. Block 在本根 K 线尚未被判定 `INVALIDATED`（Phase 顺序保证，见 17.2）

### 8.4 同一根 K 线多个 Block 的 Deterministic Selection (Rule 16 — FROZEN)

同一根已关闭 M5 K 线 `n` 上可能有多个 Block 同时满足触碰条件。仲裁顺序：

```
1. 取 confirm_time 最大者           // 「最新有效 Block」
2. 若并列，取 origin_time 最大者     // 更靠近现在的 K 线
3. 若仍并列，取 zone 中点更靠近 block 方向反侧者
      Bullish → 取 (high+low)/2 更小者（更深的 Demand）
      Bearish → 取 (high+low)/2 更大者
4. 若仍并列，取 block.id 更大者      // id 单调递增，绝对可判定
```

胜者 → `BLOCK_ARMED`；其余触碰者 → `BLOCK_TOUCHED`。
第 4 条保证**永远不存在未定义行为**，Historical Build 与 Live Replay 必然一致（AX-5）。

### 8.5 ARMED 的显示 (Rule 13 / 61)

```
M5 OB ARMED          // block_type == M5_OB
M5 BREAKER ARMED     // block_type == M5_BREAKER
```

标签锚定在 ARMED K 线的时间 + Block zone 外沿，**不随后续行情移动**。

---

## 9. Identification Cycle

### 9.1 定义 (Rule 14)

```
一个 ARMED M5 Block  ≡  一个独立 Identification Cycle
M5 OB #21 ARMED  →  Cycle #21
```

`cycle_id` 与 `block_id` 一一对应（实现上 `cycle_id = block_id`，避免两套编号错配）。

### 9.2 Cycle 内观察的 6 个模型（完全并列，Rule 38 / 42 / 44）

```
CISD
MSS
BPR
PA ENGULFING
PA REJECTION
PA BREAK-RETEST
```

**三条冻结的独立性条款：**

| 条款 | 内容 |
|------|------|
| Rule 30 / 42 | 任一模型成立**不得**终止其它模型的检测 |
| Rule 44 | 任一模型**不得** Consume 其它模型 |
| Rule 43 | 每个模型在每个 Cycle 内**只标第一次**，`max 1` |
| Rule 45 | 同一根 K 线同时成立多个模型 → **全部**记录、**全部**显示 |
| Rule 46 | **禁止**"多个模型同时出现才显示"的组合门槛 |

### 9.3 Cycle 生命周期

```
CYCLE_ACTIVE   // 从 armed_time 起
CYCLE_CLOSED   // 被新的 ARMED 结束（Rule 15）
```

**唯一的结束条件是：另一个 Block 进入 ARMED。**（Rule 15 字面）
结束时，尚未形成的模型标记为 `PASS`（Rule 15 / 34），并写入 Cycle 记录（可在面板显示）。

### 9.4 Cycle 隔离 (Rule 15 — 防泄漏)

新 Cycle 建立时，以下内容**全部重新计算，禁止继承**：

```
cisd_level / cisd_reference_time
mss_level  / mss_reference_time
pa_break_retest_reference
bpr_first_valid
所有 *_done 标志
```

实现约束：所有 Reference 都是 `IdentificationCycle` 结构的**成员**，
**不存在**任何模块级 / 全局的 `g_lastCISDLevel` 之类变量。
这是从代码结构上根除 Rule 15 泄漏的手段（见 `docs/03`）。

### 9.5 确认起始时刻 (Rule 18 — FROZEN)

```
ARMED bar = A
Identification Confirmation 只在 已关闭 K 线 n > A 上进行
```

**理由：** 在 bar A 上，"首次触碰"与"事后确认"的先后顺序在实时 tick 流中不可判定，
在历史 K 线上更不可判定（只有 OHLC，没有 tick 顺序）。
因此 bar A 一律不参与确认。

### 9.5.1 ARMED-Bar PA 例外 (D-4 裁决，2026-09-22)

Rule 18 自带例外条款："除非能够严格证明事件顺序在实时数据中当时已经可知"。
对**单根/双根 PA 形态**，该证明是成立的：

```
PA REJECTION 的确认事件 = bar A 自身的收盘。
而"下影刺入 Block"本身就是那次触碰 ⇒ 触碰必然发生在收盘之前或当时。
顺序由定义保证，不需要 tick 数据。
Historical 重建读同一根已关闭 K 线 ⇒ 结果完全相同，无 Live/Historical 分歧。
```

因此 v1.00 采用**窄范围例外**（`InpPAAllowArmedBarConfirm`，default **true**）：

| 模型 | ARMED 当根 (n == A) | 理由 |
|------|--------------------|------|
| PA REJECTION | **允许** | 确认数据 = bar A 自身，触碰是其子集 |
| PA ENGULFING | **允许** | 确认数据 = {A−1, A}；A−1 属 Reference（AX-3） |
| CISD | **禁止** | 需要 `close[A−1]` 作为**确认输入**；该突破可能整段发生在触碰之前，且 Reference run 可能包含 bar A → 语义循环 |
| MSS | **禁止** | 同上 |
| BPR | **禁止** | 定义上要求 ARMED 之后形成 |
| PA BREAK-RETEST | **禁止** | 定义上要求 ARMED 之后的新局部结构 |

实现落点：新增 **Phase 5b**（§17.2），在 Cycle 建立之后、仅用 bar A / A−1 评估这两个 PA 模型。
`InpPAAllowArmedBarConfirm = false` 时退回 Rule 18 的字面行为（全部 `n > A`）。

> 其余模型仍严格遵守 Rule 18。见 CONF-01 / BRI-01。

### 9.6 Cycle 切换与同根冲突的相位顺序 (AX-5)

若在同一根已关闭 K 线 `n` 上，既满足"旧 Cycle 的某模型确认"又满足"新 Block ARMED"：

```
Phase 4 : 先用 bar n 对 **旧 Cycle** 做 Identification 确认   → 该模型正常标记
Phase 5 : 再处理 bar n 的 Touch / ARMED                      → 新 Cycle 建立
Phase 5 之后：旧 Cycle → CLOSED，未形成模型 = PASS
新 Cycle 的确认从 bar n+1 开始（Rule 18）
```

**依据：** 在 bar n 收盘那一刻，两个事实都已完全可知，不存在未来函数；
固定相位顺序保证可重放。

---

## 10. CISD

### 10.1 Reference 冻结 (Rule 19 — FROZEN)

在 `ARMED` 提交的那一刻（bar A 收盘）立即执行一次，之后**永久冻结**：

```
方向 = Cycle 方向
opposite(bar) :  Bullish Cycle → bearish K 线 (close < open)
                 Bearish Cycle → bullish K 线 (close > open)
Doji (close == open) → 中性，既不是 run 成员，也会终止 run

窗口 = [ A − InpCISDLookbackBars + 1 , A ]   // default 12 根 M5，含 bar A

step 1: 从 A 向前找最大的 j，使 opposite(j) 为真
        若窗口内不存在 → cisd_reference = NONE，本 Cycle CISD = N/A（不标记，不报错）
step 2: k = j; while (k-1 在窗口内 && opposite(k-1)) k--;
step 3: cisd_level          = open[k]          // 连续反方向 Delivery Run **最老**一根的 Open
        cisd_reference_time = time[k]
        cisd_run_from = k, cisd_run_to = j
```

**冻结含义：** `cisd_level` 在本 Cycle 生命周期内永不改变，
不因新的 Delivery Run 出现而移动（Rule 19 明确要求）。

### 10.2 Confirmation (Rule 20 / 21 / 23 — FROZEN)

只在已关闭 K 线 `n > A` 上检查：

```
Bullish:
   close[n-1] <= cisd_level                          // Previous Close 在未突破侧
   close[n]   >  cisd_level + BreakMargin            // Current Close 正式上穿

Bearish:
   close[n-1] >= cisd_level
   close[n]   <  cisd_level − BreakMargin
```

- **必须 Close 确认**，High/Low 刺穿一律无效（Rule 23）
- `n-1` 可以等于 `A`（bar A 的 close 作为"前一根收盘"是完全已知的，不是未来函数）
- 每 Cycle 最多 1 次（Rule 43）；`cisd_done = true` 之后不再检测

### 10.3 显示 (Rule 24 — FROZEN)

确认瞬间立即标记，**不等 Entry / 不等 MSS / 不等 BPR**：

```
▲ CISD        (Bullish)
▼ CISD        (Bearish)
+ 水平线 "CISD Level" 画在 cisd_level
  时间范围 [ cisd_reference_time , 确认 K 线 time + N 根 ]
```

禁止显示为 `C`。

---

## 11. MSS

### 11.1 Reference 选择与冻结 (Rule 25 / 26 / 29 — FROZEN)

在 `ARMED` 提交那一刻执行一次，之后永久冻结。

```
Bullish Cycle → 找 Swing High；Bearish Cycle → 找 Swing Low
窗口 W = [ A − InpSetupWindowBars + 1 , A ]     // default 60 根 M5（bounded，Rule 29）

候选 Swing 必须全部满足：
  C1 swing.confirm_time <= close_time(A)        // ARMED 之前已经确认（Rule 25 / 48）
  C2 swing.bar_time     >= time[A − W + 1]      // 在 bounded setup window 内（Rule 29）
  C3 方向正确（Bullish 取 Swing High）
  C4 Bullish: swing.price > high[A]             // 必须在上方，才可能被「向上突破」
     Bearish: swing.price < low[A]
  C5 未被提前吃掉：不存在 bar m ∈ (swing.bar_index, A] 使
     Bullish: close[m] > swing.price + BreakMargin
     Bearish: close[m] < swing.price − BreakMargin
  C6 swing 不属于任何已结束 Cycle 的 reference 缓存（结构上由 9.4 保证）

选择：满足 C1..C5 的候选中，取 **bar_time 最大** 者（最近的）
      若并列，取 price 更靠近当前价者；再并列取 bar_index 更大者
若无候选 → mss_reference = NONE，本 Cycle MSS = N/A
```

**C5 是 Rule 29「Swing 是否已经失去作为当前参考的意义」的精确化。**
**禁止**在窗口之外无限向历史搜索（Rule 29 明确禁止）。

### 11.2 Confirmation (Rule 27 — FROZEN)

只在已关闭 K 线 `n > A` 上检查：

```
Bullish:
   close[n-1] <= mss_level
   close[n]   >  mss_level + BreakMargin

Bearish:
   close[n-1] >= mss_level
   close[n]   <  mss_level − BreakMargin
```

Wick Break 无效。每 Cycle 最多 1 次。

### 11.3 显示 (Rule 28)

```
▲ MSS  /  ▼ MSS
+ 水平线 "MSS Break Level" 画在 mss_level
  时间范围 [ mss_reference_time , 确认 K 线 time + N 根 ]
```

禁止显示为 `M`。

### 11.4 与 CISD 的独立性 (Rule 30)

```
CISD 确认  ⇏  停止 MSS 检测
MSS  确认  ⇏  停止 CISD 检测
```

实现上两者是 `CycleManager` 里两个**互不引用**的检测函数，
共享的只有只读的 `bar` 数据与 `cycle.armed_bar_index`。

---

## 12. BPR

### 12.1 定义 (Rule 31 — FROZEN)

```
BPR = 一个 Bullish FVG 与一个 Bearish FVG 的**真实价格重叠区域**

ov_low  = max(bull_fvg.low , bear_fvg.low)
ov_high = min(bull_fvg.high, bear_fvg.high)
VALID ⇔ round((ov_high − ov_low)/_Point) > 0      // 必须有真实重叠，相切不算
```

不得把两个无重叠的 FVG 强行称为 BPR。

### 12.2 时序 (Rule 32 — 需要用户确认的精确化，见 CONF-04)

```
BPR 的「形成时刻」 = 两条 FVG 中**较晚**那条的 confirm_time
要求： bpr.formation_time > close_time(A)        // ARMED 之后形成
```

- ARMED 之前**已经完整存在**的 BPR，不得回头算作本 Cycle 的 BPR（Rule 32 字面）
- 默认允许"较早那条 FVG"形成于 ARMED 之前（因为此时 BPR 本身尚不存在）
- 参数 `InpBPRRequireBothLegsAfterArmed`（default **false**）可切换为更严格解释
- 两条 FVG 的 `confirm_time` 都必须落在 `[A − InpSetupWindowBars, now]` 内（bounded）
- **D-2 裁决（2026-09-22）附加约束：** 较早那条腿必须满足
  `early_leg.confirm_time >= session.start_bar_time`
  （即形成于当前 H4 POI 被触碰之后），参数 `InpBPREarlyLegFromSessionStart`（default **true**）。
  理由：BPR 的业务含义是"进入 Block 路上的反方向 FVG 被反噬"，
  该腿必然属于本次 Setup；60 根窗口对早腿过宽，收紧到 Session 起点更贴合 Rule 7 的链路语义。

### 12.3 First Valid Only (Rule 33 / 43)

```
每个 Cycle 只记录 First Valid BPR
之后再出现 BPR → 不标记、不替换、不更新
```

同一根 K 线上若新 FVG 同时与多条反向 FVG 重叠，仲裁：

```
1. 取「较早腿」confirm_time 最大者
2. 并列 → 取 overlap 高度（point）更大者
3. 并列 → 取 ov_low 更小者
4. 并列 → 取 fvg.id 更大者
```

### 12.4 Direction (Rule 2 / 37)

v1.00 只标记与 Cycle 方向一致的 BPR：
Bullish Cycle → `▲ BPR`；Bearish Cycle → `▼ BPR`。
（BPR 本身由一多一空两条 FVG 构成，方向归属由 Cycle 决定，而非由 FVG 决定。）

### 12.5 BPR 记录与生命周期 (Rule 35 / 36)

```
BPRZone {
   id, cycle_id, direction,
   high, low,
   formation_time,          // 较晚腿的 confirm_time
   leg_bull_fvg_id, leg_bear_fvg_id,
   state { CANDIDATE, CONFIRMED, ACTIVE, TOUCHED, INVALIDATED, EXPIRED },
   touched_time, invalidated_time
}
```

| 迁移 | 条件 |
|------|------|
| CANDIDATE → CONFIRMED | 12.1 重叠成立 + 12.2 时序成立 |
| CONFIRMED → ACTIVE | 立即 |
| ACTIVE → TOUCHED | 已关闭 M5 K 线区间与 BPR zone 有交集 |
| 任意 → INVALIDATED | Bullish：`close < bpr.low − BreakMargin`；Bearish：`close > bpr.high + BreakMargin` |
| 任意 → EXPIRED | Cycle CLOSED 后超过 `InpObjectHistoryLimit` 保留窗口 |

**Rule 36 强制条款：** 内部 `INVALIDATED` 必须**立即**反映到 Rectangle 样式
（改颜色 / 改边框 / 打叉标注），
绝不允许"内部已失效但图上仍是 Active 样式"。
即使 First BPR 失效，也**不会**去找第二个 BPR（Rule 33 优先）。

### 12.6 显示 (Rule 37 / 62)

```
▲ BPR  /  ▼ BPR
+ Rectangle Zone  [ov_low, ov_high]，时间从 formation_time 起
```

禁止显示为 `B`。

---

## 13. Price Action 模块

PA 与 CISD / MSS / BPR **完全并列**（Rule 38），不是任何 SMC 模型的附属条件。
三个 PA 模型互相独立，各自每 Cycle `max 1`。

**共同前提（全部必须满足）：**

```
P1  Cycle 处于 CYCLE_ACTIVE
P2  确认 K 线 n > A （Rule 18）
    例外：PA ENGULFING / PA REJECTION 在 InpPAAllowArmedBarConfirm = true 时
          允许 n == A（§9.5.1，D-4 裁决）
P3  方向 == Cycle 方向（Rule 2）
P4  使用已关闭 K 线（Rule 40 / 49），bar 0 不做最终确认
P5  参考窗口 bounded：所有参考结构取自 [A, n] ⊂ setup window（Rule 41）
```

`anchor` = 本 Cycle 的 ARMED Block zone `[blk_low, blk_high]`（即使 Block 后来 INVALIDATED，
几何仍用于 PA 交互判定；见 7.3 / BRI-02）。

### 13.1 PA ENGULFING (Rule 39)

```
Bullish（在 Bullish Cycle 中）:
  E1 bar n-1 为 bearish (close < open)
  E2 bar n   为 bullish (close > open)
  E3 body(n) 完全吞没 body(n-1):
        open[n]  <= close[n-1]
        close[n] >= open[n-1]
  E4 body(n) >= InpPAEngulfMinBodyRatio × body(n-1)      // default 1.0
  E5 与 anchor 有空间关系：[low[n], high[n]] ∩ [blk_low, blk_high] ≠ ∅
     （Rule 39「Trigger Candle touch / interact with Active M5 Block」）

Bearish：完全镜像
```

`body(x) = |close[x] − open[x]|`。若 `body(n-1) == 0`（doji）→ E4 自动通过，E3 仍需成立。

### 13.2 PA REJECTION (Rule 40)

```
Bullish:
  R1 range = high[n] − low[n] > 0
  R2 lower_wick = min(open[n],close[n]) − low[n]
     upper_wick = high[n] − max(open[n],close[n])
     body       = |close[n] − open[n]|
  R3 lower_wick >= InpPARejWickToBody × body          // default 2.0（body==0 时自动通过）
  R4 lower_wick >= InpPARejWickToRange × range        // default 0.5
  R5 lower_wick >  upper_wick
  R6 有效 Interaction：low[n] <= blk_high  且  high[n] >= blk_low
  R7 收盘拒绝成立：close[n] > blk_low      // 下影刺入但收回

Bearish：完全镜像（upper_wick 主导，close[n] < blk_high）
```

Pin Bar 属于本模型的一个特例，不单独建模。

### 13.3 PA BREAK-RETEST (Rule 41)

```
Reference R：
  - 必须是 **ARMED 之后**新确认的 M5 局部结构（Rule 41「ARMED ↓ 确认当前 Setup 内有效
    Local Structure Reference」）
  - Bullish → Swing High；Bearish → Swing Low
  - swing.confirm_time > close_time(A) 且 swing.bar_time ∈ [A, n]
  - 取满足条件中 bar_time 最大者；R 随新的局部结构确认而**向前更新**
    （注意：R 在 Break 事件发生的瞬间冻结，见下）

Break（bar b, b > R.confirm_bar）:
  Bullish: close[b] > R.price + BreakMargin
  → 冻结 br_ref_price = R.price, br_break_time = close_time(b)

Retest + Hold（bar h, b < h <= b + InpPABreakRetestMaxBars，default 12）:
  Bullish: low[h]  <= R.price + retest_tol        // 回踩触及
           close[h] >  R.price + BreakMargin       // 收盘守住
  Bearish 镜像
  retest_tol = InpPARetestTolerancePips（default 0.5 pip）

满足 → PA BREAK-RETEST 确认于 bar h
若超过 InpPABreakRetestMaxBars 未完成 Hold → 本次 Break 作废，
   R 解冻，可由后续新的局部结构重新触发（但模型仍然每 Cycle max 1 次标记）
```

> "Break 之前 R 可以向前更新，Break 之后 R 冻结" —— 这不是重绘：
> 未冻结前**尚未产生任何标记**；产生标记时 `br_ref_price` 已冻结（AX-4）。

### 13.4 PA 独立性 (Rule 42)

```
PA ENGULFING 出现 ⇏ 禁止 CISD / MSS / BPR / 其它 PA
```

三个 PA 模型可以在同一根 K 线上同时成立（例如 Engulfing + Rejection），
此时**两个都必须标记**（Rule 45）。

### 13.5 显示

```
▲ PA ENGULFING     / ▼ PA ENGULFING
▲ PA REJECTION     / ▼ PA REJECTION
▲ PA BREAK-RETEST  / ▼ PA BREAK-RETEST
```

同根多模型采用**垂直堆叠**（见 14.6），禁止隐藏任何模型（Rule 45）。

---

## 14. Object Architecture (Rule 53 / 54 / 55)

### 14.1 分层铁律

```
Detection  →  State  →  Drawing
```

```
允许:  if (cycle.cisd_done) { draw(...) }
禁止:  if (ObjectFind(0, name) >= 0) { mss_exists = true }   // Rule 53 明确禁止
```

`ObjectManager` 是**单向下游**：只读 State，只写 Chart。
任何上游模块不得调用 `Object*` API。

### 14.2 Instance ID 与多实例安全 (Rule 55)

`ChartID()` 在同一图表上的两个实例中**相同**，因此不能单独用作实例标识。

**Instance Claim 协议（OnInit）：**

```
for (n = 0; n < 64; n++) {
    tag = Hex4( Hash(ChartID(), _Symbol, n) )          // 4 个十六进制字符
    marker = "HMI_" + tag + "_MK_000000"
    if (ObjectFind(0, marker) >= 0) continue;          // 该 tag 已被占用
    ObjectCreate(marker as OBJ_LABEL, 隐藏/不可见);
    g_inst = tag;  break;
}
若 64 次全部失败 → OnInit 返回 INIT_FAILED 并提示
```

**OnDeinit：** 只遍历删除前缀为 `"HMI_" + g_inst + "_"` 的对象（含 marker）。
**绝不**执行 `ObjectsDeleteAll(0, "HMI_")`（会删掉别的实例的对象，违反 Rule 55）。

### 14.3 Object Name 规范 (Rule 54)

```
格式:  HMI_{INST}_{TT}_{SEQ}
       └3┘ └─4─┘ └2┘ └─6─┘      总长 = 3+1+4+1+2+1+6 = 18 字符   (上限 63，安全)

INST : 4 hex，实例唯一
TT   : 2 字符类型码
SEQ  : 6 位十进制全局单调递增序号（本实例内唯一）
```

| TT | 对象 | TT | 对象 |
|----|------|----|------|
| `MK` | Instance Marker | `MB` | M5 Block Rectangle |
| `CX` | Context Panel Label | `MA` | M5 Block ARMED Label |
| `TR` | Trading Range Rectangle | `CD` | `▲/▼ CISD` Label |
| `LQ` | Liquidity Line | `CL` | CISD Level Line |
| `P4` | H4 POI Rectangle | `MS` | `▲/▼ MSS` Label |
| `PL` | H4 POI Label | `ML` | MSS Break Level Line |
| `BZ` | BPR Zone Rectangle | `BL` | `▲/▼ BPR` Label |
| `PE` | PA ENGULFING Label | `PR` | PA REJECTION Label |
| `PB` | PA BREAK-RETEST Label | `DB` | Debug/预览对象 |

**显示文字与 Object Name 严格分离（Rule 54）：**
`▲ CISD`、`M5 BREAKER ARMED`、`MSS Break Level` 等全部写入 `OBJPROP_TEXT`，
**绝不**写入 Object Name。
Name → Symbol / Timeframe / Cycle 冲突全部由 `{INST}+{SEQ}` 的唯一性解决。

### 14.4 Object Registry

```
struct DrawnObject { long owner_id; int owner_kind; int tt; string name; datetime t; };
```

内部维护 `DrawnObject[]` 注册表。
- 更新对象属性 → 通过注册表查名字（O(1) 哈希或线性小表）
- 删除对象 → 只删注册表里属于自己的条目
- **状态判断永远不查注册表**（注册表是绘图层资产，不是业务状态）

### 14.5 绘图时间锚定规则（反视觉重绘）

| 对象 | 左边界时间 | 创建时刻 |
|------|-----------|---------|
| H4 POI Rectangle | OB K 线 `origin_time` | POI `confirm_time` |
| M5 Block Rectangle | OB/Breaker `origin_time` | Block `confirm_time` |
| CISD Level Line | `cisd_reference_time` | CISD 确认时刻 |
| MSS Break Level Line | `mss_reference_time` | MSS 确认时刻 |
| BPR Zone | 较晚腿 FVG 的 K 线时间 | BPR `formation_time` |
| 所有 `▲/▼` Label | 确认 K 线时间 | 确认时刻 |

> 矩形左边界画在历史 K 线上属于"向左延伸显示"，不是重绘：
> 对象**出现的时刻**始终是 `confirm_time`，且此后其几何**永不改变**（AX-4）。
> 右边界允许随时间向右延伸（纯显示行为，不改变任何已记录字段）。

### 14.6 同根多标记的堆叠 (Rule 45)

同一根 K 线上多个模型确认时，按固定顺序自下而上（Bullish）/ 自上而下（Bearish）堆叠：

```
顺序: CISD → MSS → BPR → PA ENGULFING → PA REJECTION → PA BREAK-RETEST
偏移: k × InpLabelStackOffsetPips（default 1.5 pip）
```

**禁止合并为单一缩写、禁止隐藏任何一个模型。**
可以另外提供一个"组合摘要"文本对象，但不得替代独立标记（Rule 45 / 46）。

### 14.7 对象数量控制

```
InpObjectHistoryLimit (default 500)  // 总对象上限
InpMaxCyclesKept      (default 20)   // 保留最近 N 个 Cycle 的图形
```

超限时按 `confirm_time` 从最旧开始删除**图形**；
**内部记录不删除**（AX-4：历史事件不可消失，只是不再绘制）。

---

## 15. MTF Time Mapping (Rule 50)

### 15.1 禁止事项

```
禁止:  h4_rates[i]  与  m5_rates[i]  直接对应
禁止:  任何形式的 bar index 跨周期相等假设
```

### 15.2 唯一允许的映射方式

```mql5
// M5 已关闭 K 线 n 的收盘时刻
datetime m5_close_time = m5_time[n] + PeriodSeconds(PERIOD_M5);

// 该时刻「已经收盘」的最新 H4 K 线 shift（相对 H4 序列）
int h4_shift_containing = iBarShift(_Symbol, PERIOD_H4, m5_time[n], false);
int h4_shift_closed     = h4_shift_containing + 1;   // 包含 m5_time[n] 的 H4 K 线尚未收盘
```

严格判据（实现中统一用此函数）：

```
H4 bar h 对 M5 bar n 可见  ⇔  h4_time[h] + PeriodSeconds(PERIOD_H4) <= m5_time[n]
```

即：H4 K 线必须在 M5 K 线**开盘之前**已经收盘。
这一条同时消灭了"同一秒钟收盘的 H4 事件被同根 M5 提前使用"的边界漏洞。

### 15.3 数据可用性防御

```
CopyRates(_Symbol, PERIOD_H4, ...) 返回 < 0 或 少于需求根数
→ 本次 OnCalculate 直接 return prev_calculated（不做任何状态推进）
→ 下一 tick 重试
```

**绝不允许**用不完整的 H4 数据建立 Context（会造成 Reload 后结果不同，违反 Rule 52）。

### 15.4 图表周期独立性

指标通过显式 `CopyRates(PERIOD_M5)` / `CopyRates(PERIOD_H4)` 取数，
**不依赖** `OnCalculate` 传入的 `rates` 数组所属周期。
`OnCalculate` 仅作为"tick / 新 K 线"触发器。
推荐挂载在 M5 图表（否则标记密度与可读性下降），但逻辑结果与图表周期无关。

### 15.5 夏令时 / 缺口 / 周末

- 所有比较基于 broker server time 的 `datetime`，不做时区换算
- H4 K 线缺失（节假日）不做插值；`iBarShift(..., false)` 返回最近的既有 K 线
- 周末跳空造成的 FVG 按正常 FVG 处理（不特殊过滤，Rule 69）

---

## 16. Historical Build (Rule 51)

### 16.1 目标

```
Historical Build  ≈  Live Replay
```

实现手段：**同一套函数**。历史重建不是"另一条代码路径"，
而是把 Live 的单根处理函数 `ProcessClosedM5Bar(n)` 从最老的 bar 循环调用到最新。

```
OnInit / 首次 OnCalculate:
   for (n = oldest_required; n <= last_closed; n++)
        ProcessClosedM5Bar(n);          // 与 Live 完全相同的函数
```

**禁止**：先整体扫描出所有 Swing / FVG / OB 再"回填"信号（那必然引入未来函数）。

### 16.2 Warmup 与窗口

```
InpMaxHistoryBarsM5 (default 5000)   // ≈ 17 个交易日
InpMaxHistoryBarsH4 (default 500)    // ≈ 3 个月
```

```
t0 = m5_time[oldest_required]
step 1  H4 Warmup: 对所有 h4_time[h] + 4h <= t0 的 H4 K 线，按时间正序执行
        H4 结构 / Context / TradingRange / Liquidity / POI 处理
        （此阶段不产生 M5 Refinement，因为没有 M5 触碰数据）
step 2  M5 正序主循环：每根 M5 已关闭 K 线内先补齐"此刻新收盘的 H4 K 线"，再处理 M5
```

### 16.3 Warmup 边界的诚实声明

```
最早的 InpMaxHistoryBarsH4 根 H4 之前的结构不可知，
因此窗口最左端的 Context 可能与"拥有更长历史时"不同。
```

这属于**数据窗口效应**，不是重绘。处理方式：

- `InpWarmupSuppressBars`（default 100 根 M5）：窗口最左端 N 根 M5 **不产生任何标记**
- Context 面板在 warmup 完成前显示 `CTX_RANGE (WARMUP)`
- 只要 `InpMaxHistoryBarsM5 / H4` 不变，同一份数据的重建结果必然一致（Rule 52）

> **诚实声明：** 若用户在重载时修改了历史窗口参数，最左端结果可能变化。
> 这不违反 Rule 52（Rule 52 的前提是"同一份历史数据 + 同一配置"）。

### 16.4 完整重建链（与 Rule 51 要求一一对应）

```
Oldest Required Bar
  → Forward Processing
  → Context Update            (第 2 章)
  → POI Creation              (第 4 章)
  → POI Touch                 (4.5)
  → M5 Block Creation         (第 5/6 章)
  → ARMED                     (第 8 章)
  → Identification            (第 10–13 章)
```

---

## 17. Live Update

### 17.1 触发分类

| 事件 | 动作 |
|------|------|
| 新 tick，bar 0 未收盘 | 只更新 preview（PENDING TOUCH 样式、矩形右边界延伸）。**不推进任何 State** |
| 新 M5 K 线出现（即 bar 1 刚收盘） | 执行一次 `ProcessClosedM5Bar(last_closed)` |
| 新 H4 K 线收盘 | 由 `ProcessClosedM5Bar` 内部的 H4 同步阶段自动处理（15.2） |
| 换周期 / 重载 / 重启 | 重新执行 Historical Build（16.1），结果必须一致（Rule 52） |

### 17.2 单根已关闭 M5 K 线的固定相位顺序 (AX-5 — FROZEN)

```
ProcessClosedM5Bar(n):

  Phase 0  H4 Sync
           处理所有满足 h4_time[h] + 4h <= m5_time[n] 且尚未处理的 H4 K 线：
           Swing 确认 → BOS/CHOCH → Context → TradingRange → Liquidity → POI 生命周期

  Phase 0b 已有 Session 生命周期与资格检查（2026-09-24 用户签字新增，v2.38）
           按 Phase 0 刚产出的 H4 context 检查已有 Session，任一成立即结束：
             · 关联 POI 已失效                    → SE_POI_INVALID
             · H4 为 RANGE / TRANSITION           → SE_CONTEXT_NEUTRAL
             · H4 方向与 Session 不一致           → SE_CONTEXT_FLIP
             · Session 超时                       → SE_TIMEOUT
           结束时：过期该 Session 尚未 ARMED 的 block，清除 breaker 候选；
                   已 ARMED cycle 保持原生命周期（Rule 15）
           必须位于 Phase 1 之前：M5BlocksOnFVG 只检查 g_sess.active，
           Session 若在此存活，会在已不允许的 context 下产出 block

  Phase 1  M5 Structure Update
           bar n 的 M5 Swing 确认（滞后 R 根）、FVG 确认、OB/Breaker Candidate 登记

  Phase 2  Invalidation Pass (POI / Block)
           用 bar n 的 close 判定 H4 POI（用 H4 close，见 4.5）/ M5 Block 失效
           → 失效的 Block 在本根不可能 ARMED

  Phase 3  Refinement Session —— 仅新建
           POI Touch 检测 → 新建 Session；Block 候选窗口推进
           （已有 Session 的结束判定已移至 Phase 0b）

  Phase 4  Identification（针对**旧/当前** Cycle，要求 n > cycle.armed_bar_index）
           固定检测顺序：CISD → MSS → BPR → PA ENGULFING → PA REJECTION → PA BREAK-RETEST
           各自独立，互不短路（Rule 30 / 42 / 44）

  Phase 5  Touch / ARMED 仲裁（8.4）
           若产生新 ARMED：旧 Cycle → CLOSED（未形成模型 = PASS），新 Cycle 建立
           新 Cycle 的 Reference 在此刻冻结（10.1 / 11.1）
           新 Cycle 的确认从 n+1 开始（Rule 18）

  Phase 5b ARMED-Bar PA（仅当 InpPAAllowArmedBarConfirm = true，且本根刚建立新 Cycle）
           仅用 bar A / A−1 评估 PA ENGULFING 与 PA REJECTION
           CISD / MSS / BPR / PA BREAK-RETEST **不**在此阶段评估

  Phase 6  Post Lifecycle
           BPR 状态更新（TOUCHED / INVALIDATED）、对象数量裁剪、Cycle 归档

  Phase 7  Drawing + Alert
           读取 State → 绘制 / 更新对象；新确认模型触发一次去重 Alert
```

**Phase 5b 必须在 Phase 5 之后**：Cycle 必须先存在，PA 结果才有归属。
**Phase 4 先于 Phase 5** 是 9.6 的实现落点，也是 Rule 15 与 Rule 45 能同时成立的唯一顺序。

### 17.3 Alert 去重 (Rule 66 P2)

```
alert_key = (cycle_id, model_type)
已发送集合内存留存，Cycle 归档时一并保留
Historical Build 阶段 **不发送** Alert（只在 g_live == true 之后发送）
```

---

## 18. Repaint Analysis (Rule 47 / 52)

### 18.1 逐对象论证

| 对象 | 确认依赖 | 确认后是否可变 | 结论 |
|------|---------|--------------|------|
| H4 Swing | 右侧 R 根已关闭 H4 | 否（`bar_time`/`price`/`confirm_time` 冻结） | NO REPAINT |
| H4 BOS/CHOCH | 已关闭 H4 close + margin | 否 | NO REPAINT |
| H4 Context | ContextEvent 追加式 | 历史事件不可变，只有"当前值"前进 | NO REPAINT |
| Trading Range | 版本化记录 | 旧版本 `valid_to` 封口后不可变 | NO REPAINT |
| H4 POI | OB + FVG，`confirm_time` 冻结 | 只有 `state` 可变 | NO REPAINT（状态变化是设计内的 Invalidation 显示） |
| M5 Block | 同上 | 同上 | NO REPAINT |
| ARMED | 触碰 K 线收盘提交 | 否 | NO REPAINT |
| CISD | `cisd_level` 在 ARMED 冻结；确认用 close | 否 | NO REPAINT |
| MSS | `mss_level` 在 ARMED 冻结 | 否 | NO REPAINT |
| BPR | 两腿 FVG 几何固定；First Only | 只有 `state` 可变 | NO REPAINT |
| PA ENGULFING / REJECTION | 单根/双根已关闭 K 线 | 否 | NO REPAINT |
| PA BREAK-RETEST | Break 时冻结 `br_ref_price` | 否 | NO REPAINT |

### 18.2 三个"看起来像重绘但不是"的情形（需向用户说明）

| 现象 | 解释 |
|------|------|
| 矩形左边界在历史 K 线上 | 对象**创建于** confirm 时刻，左边界只是几何来源（14.5） |
| 矩形右边界随时间延伸 | 纯显示行为，不改变任何记录字段 |
| 失效对象变色 | Rule 47 允许："即使失效，也不能假装历史上从未形成过" → 改样式，不删除 |

### 18.3 唯一允许的"非重绘型差异"

```
历史窗口参数（InpMaxHistoryBarsM5 / H4 / InpWarmupSuppressBars）被修改
→ 窗口最左端结果可能不同
```

这属于输入变更，不是重绘（16.3）。

### 18.4 bar 0 预览与最终标记的关系

bar 0 的 `PENDING TOUCH` 预览对象使用独立类型码 `DB`，
在该 K 线收盘时**无条件删除并重建为正式对象或消失**。
预览对象**永不**写入 State，也**永不**被计入历史记录。

---

## 19. Future Leak Analysis (Rule 48)

逐项论证"标记第一次出现的那一刻，所需数据是否全部已知"：

| 项目 | 所需数据 | 最早可知时刻 | 标记时刻 | 泄漏 |
|------|---------|------------|---------|------|
| H4 Swing | bar i 的左 L 右 R 根 | `close_time(i+R)` | 同左 | NO |
| H4 FVG | bar i-2..i | `close_time(i)` | 同左 | NO |
| H4 OB | OB K 线 + FVG 连接 | FVG `close_time` | 同左 | NO |
| H4 POI Touch | M5 K 线 `[low,high]` | 该 M5 收盘 | 同左 | NO |
| M5 Swing | 右 R 根 | `close_time(i+R)` | 同左 | NO |
| M5 OB | OB + FVG | FVG 收盘 | 同左 | NO |
| Breaker | 原 OB + 突破 close + 新 FVG | 新 FVG 收盘 | 同左 | NO |
| ARMED | 触碰 K 线 `[low,high]` | 该 K 线收盘 | 同左 | NO |
| CISD Reference | `[A-11..A]` 的 open/close | `close_time(A)` | 冻结于 A | NO |
| CISD Confirm | `close[n-1], close[n]` | `close_time(n)` | 同左 | NO |
| MSS Reference | `confirm_time <= close_time(A)` 的 Swing（C1） | `close_time(A)` | 冻结于 A | NO |
| MSS Confirm | `close[n-1], close[n]` | `close_time(n)` | 同左 | NO |
| BPR | 两腿 FVG，较晚者 confirm | 较晚腿收盘 | 同左 | NO |
| PA ENGULFING | bar n-1, n | `close_time(n)` | 同左 | NO |
| PA REJECTION | bar n | `close_time(n)` | 同左 | NO |
| PA BREAK-RETEST | R(post-ARMED 确认) + b + h | `close_time(h)` | 同左 | NO |
| H4 Context | 已关闭 H4 事件流 | H4 收盘 | 同左 | NO |
| HTF POI 可见性 | `poi.confirm_time <= m5_time[n]` | — | — | NO |

### 19.1 三个曾经最容易出泄漏的点（已被规格显式封堵）

| 风险 | 封堵条款 |
|------|---------|
| Swing 的 `bar_time` 早于 ARMED 但 `confirm_time` 晚于 ARMED 被当作 MSS Reference | 11.1 **C1** |
| H4 K 线与 M5 K 线在同一秒收盘，H4 结论被同根 M5 使用 | 15.2 严格判据 `h4_time + 4h <= m5_time[n]` |
| 在 ARMED 那根 K 线上同时完成 Touch 与模型确认 | 9.5 / Rule 18（`n > A`） |

---

## 20. Performance Architecture (Rule 59)

### 20.1 禁止事项

```
禁止每 tick：扫描全部历史 / 删除全部 Objects / 重建 Context / 重建 Block / 重建 Identification
```

### 20.2 计算模型

```
Initial Historical Build        O(N)   一次性
+ New M5 Bar Processing         O(1)   摊销（窗口都是常数：12 / 60 / 288）
+ New H4 Bar Processing         O(1)
+ Current Price Interaction     O(k)   k = 当前可见对象数（仅绘图）
```

### 20.3 数据结构

| 数据 | 结构 | 容量 |
|------|------|------|
| M5/H4 rates | `MqlRates[]`（显式 CopyRates，增量拷贝末端 N 根） | 固定 |
| Swings | 环形缓冲 | `InpSwingBufferSize` = 64 |
| FVGs | 环形缓冲 | 128 |
| Blocks | 定长数组 + 自由链表 | `InpM5MaxBlocks` = 64 |
| POIs | 定长数组 | `InpH4MaxPOIs` = 12 |
| Cycles | 环形缓冲 | `InpMaxCyclesKept` = 20 |
| Drawn Objects | 注册表数组 | `InpObjectHistoryLimit` = 500 |

**全部定长，零动态增长，杜绝 Array Out of Range（Rule 66 P0）。**
所有数组访问统一经由 `SafeIdx()` 边界检查封装。

### 20.4 增量取数

```
新 K 线时只 CopyRates 末端 (R + 需要的最大回看 + 5) 根，不整段重拷
维护 g_last_processed_m5_time / g_last_processed_h4_time 作为推进游标
```

### 20.5 绘图节流

```
bar 0 预览更新频率上限：InpPreviewUpdateMs（default 250ms）
矩形右边界延伸：每根新 K 线更新一次，不每 tick 更新
ChartRedraw() 每次 OnCalculate 最多调用一次
```

---

## 附录 A — Input Parameter Table (Rule 60)

> 所有阈值集中于此，**禁止在函数内写死**（Rule 60 / 22）。

### A.1 General

| 参数 | 默认 | 说明 |
|------|------|------|
| `InpMaxHistoryBarsM5` | 5000 | M5 历史处理窗口 |
| `InpMaxHistoryBarsH4` | 500 | H4 历史处理窗口 |
| `InpWarmupSuppressBars` | 100 | 窗口最左端抑制标记的 M5 根数 |

### A.2 Break / Tolerance (Rule 22)

| 参数 | 默认 | 说明 |
|------|------|------|
| `InpBreakMarginMode` | **MARGIN_PIPS** | D-6 裁决：`MARGIN_PIPS` / `MARGIN_POINTS` / `MARGIN_ATR_FRAC`。默认模式下行为与原规格完全一致 |
| `InpBreakMarginPips` | **0.3** | 全局 Break Margin（CISD / MSS / BOS / CHOCH / Block 突破 / 失效） |
| `InpBreakMarginPoints` | 3 | 仅 `MARGIN_POINTS` 模式使用 |
| `InpBreakMarginATRFrac` | 0.05 | 仅 `MARGIN_ATR_FRAC` 模式使用，ATR(M5,14) |
| `InpH4ConnectTolerancePips` | 0.0 | H4 OB↔FVG 连接容差 |
| `InpM5ConnectTolerancePips` | 0.0 | M5 OB↔FVG 连接容差 |
| `InpPARetestTolerancePips` | 0.5 | Break-Retest 回踩容差 |

### A.3 H4

| 参数 | 默认 |
|------|------|
| `InpH4SwingLeft` / `InpH4SwingRight` | 2 / 2 |
| `InpH4OBtoFVGMaxBars` | 3 |
| `InpH4MaxPOIs` | 12 |
| `InpH4POIMaxAgeBars` | 120 (H4) |
| `InpH4TransitionMaxBars` | 18 (H4) |

### A.4 M5 Refinement

| 参数 | 默认 |
|------|------|
| `InpM5SwingLeft` / `InpM5SwingRight` | 2 / 2 |
| `InpM5OBtoFVGMaxBars` | 3 |
| `InpM5RefinementMaxBars` | 288 |
| `InpM5BlockLookbackFromTouch` | **2** (D-3) |
| `InpM5MaxBlocks` | 64 |

### A.5 Identification

| 参数 | 默认 | 对应规则 |
|------|------|---------|
| `InpCISDLookbackBars` | **12** | Rule 19 |
| `InpSetupWindowBars` | 60 | Rule 29 / 41 |
| `InpBPRRequireBothLegsAfterArmed` | false | Rule 32（见 CONF-04 / D-2） |
| `InpBPREarlyLegFromSessionStart` | **true** | D-2 裁决：早腿须在 Session 起点之后 |
| `InpPAAllowArmedBarConfirm` | **true** | D-4 裁决：PA ENGULFING / REJECTION 允许 n == A（§9.5.1） |
| `InpStopIdentificationOnBlockInvalidation` | false | Rule 15（见 BRI-02） |
| `InpPAEngulfMinBodyRatio` | 1.0 | Rule 39 |
| `InpPARejWickToBody` | 2.0 | Rule 40 |
| `InpPARejWickToRange` | 0.5 | Rule 40 |
| `InpPABreakRetestMaxBars` | 12 | Rule 41 |

### A.6 Display

| 参数 | 默认 |
|------|------|
| `InpM5Layer` | **M5LAYER_UPTO_M15**（v2.10）：M5 细节层只在 M1/M5/M15 图表显示 |
| `InpPanelMode` / `InpPanelCorner` | **PANEL_COMPACT** / CORNER_LEFT_UPPER（v1.31） |
| `InpShowH4POI` / `InpShowTradingRange` / `InpShowLiquidity` | true / true / **true** |
| `InpShowM5Blocks` / `InpShowArmedLabel` | true / true |
| `InpShowCounterDirBlocks` | false |  <!-- Breaker 原料（逆势 OB），见 CONF-06 -->
| `InpShowRejectedOB` | false |  <!-- 被 Gap 否决的 OB 诊断显示，见 BRI-04 -->
| `InpShowCISD` / `InpShowMSS` / `InpShowBPR` / `InpShowPA` | true |
| `InpShowLevelLines` | true |
| `InpLabelStackOffsetPips` | 1.5 |
| `InpMaxCyclesKept` | 20 |
| `InpObjectHistoryLimit` | 500 |
| `InpPreviewUpdateMs` | 250 |
| 各类颜色 / 线型 / 线宽 / 字号 | 见 `HMI_Style.mqh`（106 个参数，v1.10） |
| Kill Zone 时段与样式 | 见 `HMI_KillZone.mqh`（47 个参数，v1.20，见 D-8） |
| `InpShowLiquidity` | **true**（v1.20 起默认打开） |
| `InpLiqMaxLines` | 10（每侧上限，纯显示） |
| ATR / ADR 面板 | 见 `HMI_Ranges.mqh`（3 个参数，v1.30，见 D-9） |

> **样式参数全部集中在 `MQL5/Include/HMI/HMI_Style.mqh`**，与功能参数（本附录 A.1–A.5）
> 物理分离。样式层不被任何识别引擎读取，因此任何样式改动都不可能移动一个标记。
> MT5 行为注意：线型（DASH / DOT 等）只在 `width == 1` 时才会被渲染，宽度 > 1 一律显示为实线。

### A.7 Alert

| 参数 | 默认 |
|------|------|
| `InpAlertsEnabled` | false |
| `InpAlertPopup` / `InpAlertPush` / `InpAlertMail` | true / false / false |
| `InpAlertOnArmed` / `InpAlertOnCISD` / `InpAlertOnMSS` / `InpAlertOnBPR` / `InpAlertOnPA` | true |

---

## 附录 B — 全局定义

### B.1 Pip 定义

```mql5
double PipSize() {
   return ((_Digits == 3 || _Digits == 5) ? 10.0 * _Point : _Point);
}
double BreakMargin() {                       // D-6 裁决
   switch(InpBreakMarginMode) {
      case MARGIN_POINTS:   return InpBreakMarginPoints * _Point;
      case MARGIN_ATR_FRAC: return InpBreakMarginATRFrac * ATR_M5_14();
      default:              return InpBreakMarginPips * PipSize();   // MARGIN_PIPS
   }
}
```

**D-6 强制诊断（无条件执行，不改变逻辑）：** `OnInit` 在 Experts 日志打印

```
HMI: effective break margin = 0.00300 price / 0 points   <-- 若为 0 points 追加 WARNING
```

这样用户可以一眼看出 margin 是否在本品种上退化为 0。

> **注意（见 BRI-03）：** 对 `_Digits == 2` 的品种（如 XAUUSD 部分经纪商），
> `PipSize = 0.01`，`0.3 pip = 0.003` 小于最小报价单位 → Break Margin 实际退化为 0。
> 规格不擅自更改（Rule 65），但必须让用户知道。

### B.2 价格比较一律整数化

```mql5
int Pts(double a, double b) { return (int)MathRound((a - b) / _Point); }
bool GtMargin(double a, double b) { return Pts(a, b) > MarginPoints(); }
```

**禁止** `double ==` / `double >` 直接用于关键判定（浮点误差会破坏可重放性）。

### B.3 方向常量

```mql5
#define DIR_NONE   0
#define DIR_BULL  +1
#define DIR_BEAR  -1
```

### B.4 时间工具

```mql5
datetime CloseTime(ENUM_TIMEFRAMES tf, datetime open_time);   // open_time + PeriodSeconds(tf)
bool     H4VisibleTo(datetime h4_open, datetime m5_open);     // h4_open + 4h <= m5_open
```
