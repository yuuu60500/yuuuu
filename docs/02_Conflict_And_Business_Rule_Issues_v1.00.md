# Conflict Analysis & Business Rule Issues — v1.00

**对应 Rule 64（写代码前主动找逻辑冲突）与 Rule 65（不得自行修改业务规则）。**

本文件分三部分：

1. **Part A** — Rule 64 十项检查清单的逐条回答
2. **Part B** — 规则之间的冲突 / 歧义（CONF-01 … CONF-16）
3. **Part C** — BUSINESS RULE ISSUE（BRI-01 … BRI-04，需用户裁决）
4. **Part D** — 需要用户签字的决策点汇总

> **重要：** Part C 中的任何"Suggested Alternative"**均未实施**。
> v1.00 规格一律按**现有规则字面**实现（Rule 65）。

---

## Part A — Rule 64 检查清单

| # | 检查项 | 结论 | 封堵条款 |
|---|--------|------|---------|
| 1 | 是否存在 Future Leak？ | **规格层面 NO**（代码层面待实现后审计） | Spec §19 全表；AX-1 / AX-2 |
| 2 | 是否存在 Historical Repaint？ | **规格层面 NO** | Spec §18 全表；AX-4 |
| 3 | ARMED 和 Identification 是否可能时序倒置？ | **曾经会，已封堵** | Rule 18 → Spec §9.5（`n > A`）+ §17.2 Phase 4/5 |
| 4 | MSS Reference 是否可能来自未来？ | **曾经会（最危险的一条），已封堵** | Spec §11.1 **C1**：`swing.confirm_time <= close_time(A)` |
| 5 | CISD Reference 是否会移动？ | **NO** | Spec §10.1 冻结；Reference 是 Cycle 结构成员 |
| 6 | BPR 是否可能读取 ARMED 前结构？ | **部分可能，已参数化并需裁决** | CONF-04 / `InpBPRRequireBothLegsAfterArmed` |
| 7 | 旧 Cycle Reference 是否会进入新 Cycle？ | **NO（结构上根除）** | Spec §9.4：不存在任何模块级 Reference 全局变量 |
| 8 | PA 是否使用无限历史窗口？ | **NO** | Spec §13 P5 + `InpSetupWindowBars` + `InpPABreakRetestMaxBars` |
| 9 | H4 与 M5 是否可能时间错位？ | **曾经会，已封堵** | Spec §15.2 严格判据 `h4_open + 4h <= m5_open` |
| 10 | Object 是否可能多实例冲突？ | **曾经会（ChartID 相同），已封堵** | Spec §14.2 Instance Claim 协议 |

---

## Part B — 规则冲突 / 歧义

### CONF-01 — Rule 18 与 Rule 39/40 的时序张力 【真实冲突】

**涉及规则：** Rule 18（确认从 ARMED 后下一根已关闭 K 线开始）、Rule 39（Engulfing 的
Trigger Candle 必须 touch/interact 当前 Active M5 Block）、Rule 40（Rejection 同理）。

**冲突描述：**
典型的 PA REJECTION（长下影刺入 OB 后收回）与 PA ENGULFING，
**最经典的形态恰恰发生在"触碰 Block 的那一根 K 线"上**。
而 Rule 18 规定 ARMED 当根不参与确认 → 这类形态在 v1.00 中**系统性地无法被标记**，
除非价格在下一根继续与 Block 交互。

**为什么仍然遵守 Rule 18：**
Rule 18 自带例外条款——"除非能够严格证明事件顺序在实时数据中当时已经可知"。
历史 K 线只有 OHLC，**无法**证明"触碰发生在 Rejection 形态成立之前"。
若允许同根确认，Historical Build 与 Live 会在这一点上产生不可调和的差异，
直接违反 Rule 51 / 52。

**v1.00 最终处置（D-4，2026-09-22）：**
对 **PA ENGULFING / PA REJECTION** 开放 ARMED 当根确认，因为这两者的确认事件就是
bar A 自身的收盘，而触碰是该 K 线数据的子集 —— 顺序由定义保证，落入 Rule 18 的例外条款。
**CISD / MSS / BPR / PA BREAK-RETEST 仍严格 `n > A`。**
**交易逻辑改变：YES（已获用户批准）。**

---

### CONF-02 — Rule 17 与 Rule 19/25 的表面冲突 【非冲突，已定义解决】

**涉及规则：** Rule 17（ARMED 之前的历史结构不能回头被算成本 Cycle 信号）、
Rule 19（CISD 向前回看 12 根）、Rule 25（MSS 使用 ARMED 之前已确认的 Swing）。

**分析：** 两者操作的是不同概念。引入 **AX-3 Reference ≠ Confirmation** 后冲突消失：

```
Reference    = 价格水平，可取自 ARMED 之前，但必须在 ARMED 当时已经可知
Confirmation = 标记事件，必须严格晚于 ARMED bar
```

**v1.00 处置：** 按 AX-3 实施。**交易逻辑改变：NO。**

---

### CONF-03 — Context 翻转时，既有 ARMED Cycle 的归属 【规则缺口】

**涉及规则：** Rule 2（只做顺势）、Rule 15（只有新 ARMED 才结束旧 Cycle）、
Rule 3（CHOCH → TRANSITION）。

**缺口描述：**
Cycle #21 在 BULLISH Context 下 ARMED；两小时后 H4 出现 CHOCH → Context 变为 TRANSITION。
此时 Cycle #21 是否继续识别？规则集未定义。

**可选解释：**
- (a) 继续 —— Rule 15 字面：只有新 ARMED 能结束 Cycle
- (b) 立即结束 —— Rule 2 字面：顺势前提已消失

**v1.00 处置（默认，按 Rule 15 字面）：**
```
Cycle 继续运行直到被新的 ARMED 结束。
但：Refinement Session 因 Context 方向翻转而结束（Spec §5.1），
    所以不会再产生新的 Block → 实际上 Cycle 会自然走到尽头。
    注意：TRANSITION 不等于方向翻转，只有 BULLISH↔BEARISH 才算翻转。
```
**交易逻辑改变：NO（这是对现有规则的字面实现）。**
**已裁决：** D-1 —— 继续（维持 Rule 15 字面）。

---

### CONF-04 — Rule 32 的"ARMED 之后形成的 BPR"存在两种读法 【歧义】

**涉及规则：** Rule 31 / 32 / 33。

**歧义描述：**
BPR 由一条 Bullish FVG + 一条 Bearish FVG 重叠构成。若较早的一条 FVG 形成于 ARMED 之前、
较晚的一条形成于 ARMED 之后：

- **读法 A（宽松，v1.00 默认）：** BPR 这个"重叠区域"直到较晚那条 FVG 出现才存在，
  所以它是"ARMED 之后形成的"，合法。
  依据 Rule 32 原文"ARMED **前已经存在**的历史 BPR 不能回头当成本 Cycle 的 BPR"
  —— 该 BPR 在 ARMED 前并不存在。
- **读法 B（严格）：** 两条腿都必须形成于 ARMED 之后。

**v1.00 处置：** 默认读法 A，并提供 `InpBPRRequireBothLegsAfterArmed`（default false）
可切换到读法 B。两条腿都必须落在 `InpSetupWindowBars` 窗口内（bounded）。
**交易逻辑改变：** 取决于用户选择；默认值按字面最贴近的读法 A。
**已裁决：** D-2 —— 允许早腿早于 ARMED，但须 ≥ Session 起点。

---

### CONF-05 — ARMED Block 失效后 Cycle 是否继续 【规则缺口】

**涉及规则：** Rule 12（Block 有 INVALIDATED 状态）、Rule 15（只有新 ARMED 结束 Cycle）、
Rule 44（模型不互相 Consume）、Rule 39/40（PA 需与 **Active** M5 Block 交互）。

**缺口描述：**
Bullish Block 被 M5 收盘跌破 → `BLOCK_INVALIDATED`。
此时 Rule 39/40 要求的"Active M5 Block"已不存在，但 Rule 15 说 Cycle 未结束。

**v1.00 处置（按 Rule 15 字面）：**
```
Cycle 继续；PA 的交互判定继续使用该 Block 的**几何区间**（zone 不变）；
提供 InpStopIdentificationOnBlockInvalidation（default false）。
```
**→ 见 BRI-02。**

---

### CONF-06 — Rule 2（顺势）与 Rule 11（Breaker 需要反方向 OB） 【结构性推论】

**涉及规则：** Rule 2、Rule 8、Rule 11。

**描述：**
Bullish Breaker 的原料是一个**被向上突破的 Bearish OB**。
在 BULLISH Context 的 Session 中，Bearish OB 属于逆势方向。
若严格执行"只识别顺势 Block"，则 **Breaker 永远无法产生**，Rule 11 形同虚设。

**v1.00 处置（唯一自洽解）：**
```
Session 内**同时追踪双方向 M5 OB**；
但逆势方向 OB 只能作为 Breaker 原料，
  - 永不进入 BLOCK_ARMED
  - 永不建立 Identification Cycle
  - 默认不绘制（InpShowCounterDirBlocks = false）
只有顺势方向的 M5 OB 与 Breaker 可以 ARMED。
```
**交易逻辑改变：NO**（这是让 Rule 11 可执行的必要条件，不改变任何标记规则）。

---

### CONF-07 — Rule 7（不得向触碰点之前回溯）与 Rule 11（Previously Valid OB） 【张力】

**描述：**
Breaker 要求"先有一个有效 OB，再被突破"。
若 M5 Block 搜索窗口严格从 H4 POI 触碰点开始（`InpM5BlockLookbackFromTouch = 0`），
则原 OB 也必须在触碰点之后形成 → Breaker 至少需要
`OB 形成(3根) + 突破(1根) + 新 FVG(3根) ≈ 7 根 M5` 才可能出现。

**v1.00 处置：** 保持严格（default 0），因为这是 Rule 7 的字面要求。
参数 `InpM5BlockLookbackFromTouch` 保留（可设 >0），但**默认 0**。
**交易逻辑改变：NO。**
**已裁决：** D-3 —— `InpM5BlockLookbackFromTouch = 2`（见 docs/01 §5.2 漏标场景）。

---

### CONF-08 — Rule 13（价格触碰即 ARMED）与 Rule 49（必须已关闭 K 线） 【表面冲突，已证明等价】

**描述：** 触碰可能发生在 bar 0 的 tick 流中；Rule 49 要求确认用已关闭 K 线。

**证明（Spec §8.2）：**
K 线的 `high/low` 在其生命周期内单调扩张，
bar 0 期间发生的任何触碰，必然体现在该 K 线收盘后的 `[low, high]` 中。
因此"收盘时提交 ARMED"与"tick 时刻发现触碰"指向**同一根 K 线、同一个事件**，
只是提交时刻统一到收盘。Historical Reload 必然重现同一事件。

**v1.00 处置：** ARMED 在触碰 K 线**收盘**提交；bar 0 显示 `PENDING TOUCH` 预览（不入状态）。
**交易逻辑改变：NO。**

---

### CONF-09 — Rule 16（同根多 Block）需要"最新"的精确定义 【歧义，已消除】

**描述：** "最新有效 Block"在同一根 K 线上可能仍然并列（两个 Block 同根确认）。

**v1.00 处置：** 四级仲裁（Spec §8.4），最后一级用单调递增的 `block.id` 兜底，
保证**绝无未定义行为**。**交易逻辑改变：NO。**

---

### CONF-10 — Rule 33（First BPR Only）与 Rule 36（BPR 失效） 【需明示】

**描述：** 若 First BPR 被判定 INVALIDATED，是否可以标记第二个 BPR？

**v1.00 处置：** **不可以**。Rule 33 优先：每 Cycle 只记录 First Valid BPR。
失效的 BPR 保留记录并以失效样式显示（Rule 36 / 47）。
**交易逻辑改变：NO。**

---

### CONF-11 — Rule 22（0.3 pip）在非外汇品种上的退化 【数值风险】

**→ 见 BRI-03。**

---

### CONF-12 — Rule 25 + Rule 29 可能导致 MSS Reference 经常为空 【副作用，可接受】

**描述：**
MSS Reference 必须同时满足：ARMED 之前已确认（C1）、在 60 根窗口内（C2）、
方向正确（C3）、位于 ARMED K 线上方/下方（C4）、尚未被吃掉（C5）。
在急速位移行情中，这些条件可能同时不满足 → 本 Cycle **无 MSS**。

**v1.00 处置：** `mss_reference = NONE` → 本 Cycle MSS 显示为 `N/A`（面板），不标记、不报错。
这是正确行为：宁可漏标，不可用未来 Swing 补齐（Rule 26 / 48）。
**交易逻辑改变：NO。**

---

### CONF-13 — Rule 25 未规定"哪一个 Swing High" 【歧义，已消除】

**v1.00 处置：** Spec §11.1 的 C1–C5 + "取 bar_time 最大者"，三级并列消解。
**交易逻辑改变：NO（原规则未定义，此处补全为可判定规则）。**

---

### CONF-14 — Rule 9"位移前的反方向 Candle"需要可判定定义 【歧义，已消除】

**描述：** "位移（displacement）"本身是主观概念，若引入位移强度阈值会构成新增过滤条件（违反 Rule 69）。

**v1.00 处置：**
```
不引入位移强度阈值。
"位移"由 **FVG 的存在** 客观代表（有 FVG ⇔ 有位移）。
候选 OB = FVG 之前、窗口 InpM5OBtoFVGMaxBars 内、方向相反、且满足 Connection 规则的 K 线。
若窗口内有多根反方向 K 线满足连接：取**离 FVG 最近**的那根（最后一根反方向 K 线），
这与 ICT 的「last opposite candle before displacement」一致。
```
**交易逻辑改变：NO（补全为可判定规则，未增加过滤）。**

---

### CONF-15 — Rule 54/55：ChartID 无法区分同图表两实例 【真实技术缺陷，已封堵】

**v1.00 处置：** Instance Claim 协议（Spec §14.2）：
用隐藏 marker 对象抢占 4 hex tag，`OnDeinit` 只删自己 tag 前缀的对象。
**交易逻辑改变：NO。**

---

### CONF-16 — Rule 51（Historical Build）与 Rule 7 的窗口边界 【边界效应，已声明】

**描述：**
若某个 H4 POI 的触碰发生在 M5 历史窗口起点**之前**，
重建时该 Session 无法完整复现（缺少触碰时刻的 M5 数据）。

**v1.00 处置：**
```
POI Touch 只承认发生在 M5 处理窗口内的触碰；
窗口最左端 InpWarmupSuppressBars 根 M5 不产生任何标记；
Context 面板在 warmup 期间显示 (WARMUP)。
```
这属于**数据窗口效应**，在 Spec §16.3 已公开声明，不属于重绘（Rule 52 的前提是同一配置）。
**交易逻辑改变：NO。**

---

## Part C — BUSINESS RULE ISSUE (Rule 65 格式)

### BRI-01

```
BUSINESS RULE ISSUE

Current Rule:
Rule 18 — Identification confirmation 从 ARMED 后「下一根已关闭 M5 Candle」开始。
Rule 39 / 40 — PA ENGULFING / PA REJECTION 的 Trigger Candle 必须与 Active M5 Block
               有触碰 / 交互关系。

Problem:
最经典的 PA REJECTION（长下影刺入 M5 Block 后收回）与部分 PA ENGULFING，
在形态上就发生在「首次触碰 Block 的那一根 K 线」。
Rule 18 把该根排除在确认范围之外，导致这类形态系统性漏标。

Possible Consequence:
- PA REJECTION 的标记数量显著少于交易员肉眼所见
- 交易员可能误以为指标「漏掉了」明显的拒绝形态
- 在快速反转行情中，M5 Block 的第一根反应 K 线往往就是唯一的 PA 信号

Suggested Alternative:
新增参数 InpPAAllowArmedBarConfirm（default = false）。
当且仅当设为 true 时，允许 PA ENGULFING / PA REJECTION 在 ARMED 当根确认，
且必须附加约束：
   - 该根 K 线的收盘价必须已经脱离 Block 的被突破侧（证明「先触碰、后反应」的顺序）
   - CISD / MSS / BPR 仍然严格遵守 Rule 18（不放宽）
   - 面板明确标注「ARMED-BAR PA: ENABLED」，提示该模式下
     Historical 与 Live 的 tick 级顺序无法严格证明

Would Trading Logic Change:
YES
```

**当前状态：D-4 裁决（2026-09-22）—— 窄范围启用。**
`InpPAAllowArmedBarConfirm = true`，仅适用 PA ENGULFING / PA REJECTION；
CISD / MSS / BPR / PA BREAK-RETEST 仍严格 `n > A`。设为 false 可退回 Rule 18 字面行为。

---

### BRI-02

```
BUSINESS RULE ISSUE

Current Rule:
Rule 15 — 只有「新的有效 M5 Block 被触碰并进入 ARMED」才结束旧 Identification Cycle。
Rule 12 — M5 Block 具有 INVALIDATED 状态。

Problem:
当 ARMED Block 已被价格明确击穿（例如 Bullish Block 被 M5 收盘跌破下沿）后，
按 Rule 15 字面，该 Cycle 仍然继续识别 CISD / MSS / BPR / PA。
此时：
  - Rule 39 / 40 所要求的「Active M5 Block」在业务意义上已不存在
  - CISD / MSS 的冻结 Reference 已经失去其原始位置含义
  - 在没有新 Block 出现的情况下，这个 Cycle 可能持续数小时继续产出标记

Possible Consequence:
在已经失效的位置上继续产出 ▲/▼ 标记，交易员可能误读为「该位置仍然有效」。

Suggested Alternative:
新增参数 InpStopIdentificationOnBlockInvalidation（default = false，保持现有规则）。
设为 true 时：ARMED Block 进入 INVALIDATED → 该 Cycle 立即 CLOSED，
未形成模型记为 PASS（与 Rule 15 的 PASS 语义一致），等待下一个 ARMED。

Would Trading Logic Change:
YES
```

**当前状态：D-5 裁决（2026-09-22）—— 不启用。**
`InpStopIdentificationOnBlockInvalidation = false`，完全遵守 Rule 15 字面。
附加诊断显示 `ANCHOR INVALIDATED`（不改逻辑）。

---

### BRI-03

```
BUSINESS RULE ISSUE

Current Rule:
Rule 22 — CISD Break Margin 默认 0.3 pip，作为 Input Parameter。

Problem:
「pip」在不同品种上的换算并不统一：
  - 5 digits / 3 digits 外汇：PipSize = 10 × Point  → 0.3 pip 有意义
  - XAUUSD（_Digits == 2，Point = 0.01）：PipSize = 0.01 → 0.3 pip = 0.003
    小于最小报价单位 → Break Margin 实际退化为 0，
    「收盘穿越 + Margin」退化为「收盘穿越」
  - 指数 / 加密（_Digits == 1 或 0）：同样退化
  - 反之，若把 Gold 的 1 pip 定义为 0.1 或 1.0，0.3 pip 又可能过大

Possible Consequence:
同一个 0.3 的默认值，在外汇上是合理噪音过滤，在黄金/指数上等于没有过滤，
造成 CISD / MSS 在不同品种上的严格程度不一致（用户不易察觉）。

Suggested Alternative:
新增 InpBreakMarginMode 枚举（default = PIPS，保持现状）：
   PIPS          : 现行定义（不变）
   POINTS        : 直接以 _Point 计
   ATR_FRACTION  : margin = InpBreakMarginATRFrac × ATR(M5, 14)，自适应品种
并在启动时于 Experts 日志打印实际生效的 margin（价格单位 + points），
让用户一眼看出是否退化为 0。

Would Trading Logic Change:
YES（仅当用户主动切换模式时）
```

**当前状态：D-6 裁决（2026-09-22）—— 实施三模式，默认 `MARGIN_PIPS`（行为不变）+ 强制启动日志。**

---

### BRI-04

```
BUSINESS RULE ISSUE

Current Rule:
Rule 5 / Rule 6 — H4 POI = 完整 OB 区域；FVG 只负责验证；
                  OB 与 FVG 必须 Touch 或 Overlap，存在正价格空隙 = INVALID。

Problem:
在 H4 这种较大周期上，「OB 与其位移 FVG 之间存在正空隙」是相当常见的形态
（尤其新闻驱动的跳空位移）。严格执行该规则会使 H4 POI 数量明显减少，
从而使整条链路（POI → Touch → M5 Refinement → ARMED → Identification）
的触发频率下降。

Possible Consequence:
指标在某些品种 / 某些时段可能长时间没有任何 Setup。
这不是 Bug，而是规则的直接结果，但用户需要事先知道。

Suggested Alternative:
不修改规则。仅建议：
  - 在 Context 面板显示「H4 POI: n ACTIVE / m REJECTED-BY-GAP」计数
  - 把被 Gap 否决的 OB 以极淡的虚线框可选显示（InpShowRejectedOB，default false）
  这样用户能看到「规则否决了什么」，而不是以为指标失灵。

Would Trading Logic Change:
NO（纯诊断显示，不改变任何标记逻辑）
```

**当前状态：D-7 裁决（2026-09-22）—— 实施诊断计数。** `InpShowRejectedOB` 仍 default false。

---

## Part D — 需要用户签字的决策点

**裁决日期：2026-09-22 — 用户已签字批准以下全部决定。**

| ID | 决策点 | 初始默认 | **最终裁决** | 交易逻辑改变 |
|----|--------|---------|-------------|-------------|
| **D-1** | Context 变 TRANSITION / RANGE 时，既有 ARMED Cycle 是否继续？ | 继续 | **继续**（维持 Rule 15 字面） | NO |
| **D-2** | BPR 较早那条 FVG 是否允许形成于 ARMED 之前？ | 允许 | **允许**，且新增约束：早腿须 ≥ Session 起点（`InpBPREarlyLegFromSessionStart = true`） | YES（小幅收紧） |
| **D-3** | M5 Block 搜索是否允许向 POI 触碰点之前回溯？ | 0 | **`InpM5BlockLookbackFromTouch = 2`** | YES |
| **D-4** | 是否启用 BRI-01（PA 在 ARMED 当根确认）？ | 否 | **是，但窄范围**：仅 PA ENGULFING / PA REJECTION（`InpPAAllowArmedBarConfirm = true`）；CISD / MSS / BPR / BREAK-RETEST 仍 `n > A` | YES |
| **D-5** | 是否启用 BRI-02（Block 失效即结束 Cycle）？ | 否 | **否**（维持 Rule 15 字面） | NO |
| **D-6** | 是否启用 BRI-03（Break Margin 模式）？ | 否 | **是**：实施三模式，**默认仍 PIPS**（行为不变）+ 强制启动日志 | NO（默认下） |
| **D-7** | 是否实施 BRI-04 诊断计数？ | 建议是 | **是** | NO |

### 裁决理由摘要

**D-1 —— 继续。** TRANSITION ≠ 方向翻转。实务上 H4 CHOCH 往往**就是**把价格打进 H4 POI 的那一段下跌；
此时杀掉 Cycle 等于系统性杀掉深回撤型顺势 Setup。且全方向翻转已经会结束 Refinement Session，
Cycle 会自然走到尽头。附加诊断：Cycle 面板标注 `CTX CHANGED DURING CYCLE`（不改逻辑）。

**D-2 —— 允许，但收紧。** BPR 的经典形态是"下跌进 Block 时留下的 Bearish FVG 被反转上涨的
Bullish FVG 反噬重叠"，该 Bearish FVG 几乎总是形成于 ARMED 之前。要求两腿都在 ARMED 之后
等于废掉模型。但 60 根窗口对早腿过宽 → 收紧到 Session 起点（POI 触碰之后）。

**D-3 —— 0 改为 2。** 见 `docs/01` §5.2 的漏标场景（OB 是触碰前一根阴线）。
`confirm_time >= session.start_bar_time` 的硬约束保证无未来函数。

**D-4 —— 窄范围启用（修正）。** 原先"OHLC 无法证明事件顺序"的理由对**单根 PA 形态不成立**：
PA REJECTION 的确认事件就是 bar A 自身的收盘，而刺入 Block 的下影本身就是那次触碰，
顺序由定义保证。CISD / MSS 则确实需要 `close[A−1]` 作为**确认输入**（突破可能整段发生在触碰之前，
且 CISD Reference run 可能包含 bar A → 语义循环），故仍禁止。

**D-5 —— 不启用。** "Block 被击穿 → 随后 CISD 反夺回"本身是高质量形态（扫 OB 下方流动性后反手），
杀掉 Cycle 会把 sweep-and-reclaim 全部过滤掉。且每模型每 Cycle 上限 1 次，
"僵尸 Cycle"最多产出 6 个标记，影响面有界。附加诊断：面板标注 `ANCHOR INVALIDATED`。

**D-6 —— 实施选项 + 强制日志。** 默认 PIPS 模式下行为与原规格**逐条相同**，零风险；
非外汇品种（如 `_Digits == 2` 的 XAUUSD，0.3 pip = 0.003 → 0 points）可切 ATR 模式。
不采用"最小 1 point 下限"，因为那会在用户不知情下改变黄金上的判定。

**D-7 —— 实施。** 纯诊断，区分"规则否决了它"与"指标坏了"。

---

## Part E — 后续新增决策

### D-8 —— Kill Zone 时段标识（2026-09-22，用户要求）

原始 75 条规则中**完全没有**"时间 / 时段"这个维度，核心链路是
`H4 Context → H4 POI → 触碰 → M5 Block → ARMED → 识别`，不含时段。
因此 Kill Zone 是**新增功能**，不是漏实现。

**必须守住的边界：**

```
画出时段 HIGH / LOW                       = 显示层  ← v1.20 实现的就是这个
用时段去过滤 / 门控信号                    = 过滤条件 ← Rule 46 / 69 禁止，未实现
```

| 项目 | 裁决 |
|------|------|
| 实现形式 | **只画 HIGH / LOW 两条线**，不画时段矩形（用户明确要求） |
| 数据来源 | 落在时段窗口内的 **已关闭 M5** K 线的最高价 / 最低价 |
| 是否参与判定 | **否。** `HMI_KillZone.mqh` 不被 Phase 0-7 的任何代码引用；它是一个纯函数 + 绘图 |
| 时区 | 全部是 **broker server time**，不自动跟随夏令时，由用户自行校准 |
| 跨午夜窗口 | 支持（`end <= start` 视为跨日），归属于**开始那一天** |
| 时段数量 | 4 个，各自可独立开关 / 命名 / 设定起止时分 / 颜色 / 线型 / 线宽 |

**Trading Logic Changed：NO。**

> 若将来想用时段做过滤，必须先按 Rule 65 出 BUSINESS RULE ISSUE。
> 建议的正确顺序是：先用 `InpLogSignals` 的 CSV 按时段切分统计，
> 用数据证明某个时段确实没有 edge，再谈过滤。凭感觉加时间过滤是过拟合的经典入口。

### D-9 —— 面板 ATR / ADR（2026-09-22，用户要求）

| 项目 | 裁决 |
|------|------|
| 显示位置 | **只上面板**，不画任何线（用户明确要求） |
| ATR 数据源 | 复用引擎自己前向递推的 `g_h4_atr` / `g_m5_atr`，**不另建一套 ATR** —— 面板显示的就是 `MARGIN_ATR_FRAC` 模式实际会用的那个值 |
| ADR 数据源 | 经纪商自己的 D1 K 线；**只平均已收盘的交易日**（把今天的半截波幅算进去会低估 ADR） |
| 是否参与判定 | **否。** `HMI_Ranges.mqh` 不被 Phase 0-7 任何代码引用 |

**Trading Logic Changed：NO。**

> ADR 的用途是回答"今天还剩多少空间"。日波幅消耗接近 100% 时再去追一个远离当日中枢的
> Setup，赔率通常已经很差 —— 但这个判断**由交易员做**，指标只把数字摆出来（Rule 1）。
> 若将来想用 ADR 消耗度去过滤信号，必须先按 Rule 65 出 BUSINESS RULE ISSUE。
