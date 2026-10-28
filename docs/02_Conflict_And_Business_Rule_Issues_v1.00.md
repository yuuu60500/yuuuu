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

### BRI-05

```
BUSINESS RULE ISSUE

Current Rule:
Rule 8  — M5 Block 至少识别 A. M5 Order Block  B. M5 Breaker Block，两者并列。
Rule 11 — Breaker Block 必须独立于普通 OB 类型识别，并给出完整的
          「原 OB 被突破 → 角色转换 → 新方向 FVG Touch/Overlap」链条。

Problem:
用户要求把 Breaker 做成开关并**默认关闭**。
默认关闭意味着：指标的出厂行为**不再满足 Rule 8 / Rule 11**。
代码仍然完整保留 Breaker 实现，把 InpEnableBreaker 设为 true 即可恢复，
但「默认状态」已经与冻结规则不一致。

Possible Consequence:
- 默认状态下不会出现任何 M5 BREAKER ARMED，Breaker 相关的 Cycle 全部消失
- 「失败的 OB 变成反向支撑」这类形态（止损被扫后反转的位置）不再被标记
- 若日后有人只读 Rule 8 / Rule 11 而不读本条记录，会误以为指标漏实现

Suggested Alternative:
InpEnableBreaker 默认 true（仅把它做成可关的开关）。
这样规则不破，想清理图面或简化审计时手动关掉即可。

Would Trading Logic Change:
YES —— 默认关闭会直接减少信号。

Decision:
用户于 2026-09-22 明确选择 **默认关闭**，并已被告知上述后果。
按 Rule 65，规则本身不改写（Rule 8 / Rule 11 原文保留），
仅记录「默认值偏离规则」这一事实。
```

### D-10 —— Breaker 开关（2026-09-22，用户裁决）

| 项目 | 裁决 |
|------|------|
| 形式 | `InpEnableBreaker`，**默认 false** |
| 关闭时的行为 | 不生成 Breaker；**连逆势 M5 OB 也不再创建**（它们存在的唯一目的就是喂 Breaker，见 CONF-06），所以关闭路径是真的更省，不是「算了但不显示」 |
| 代码是否保留 | **保留完整实现**。三个 guard 控制，设为 true 即恢复 Rule 8 / Rule 11 |
| 版本 | **v2.00**（Rule 74：Business Logic Change）。若默认是 true，这就只是 v1.40 Minor Feature |
| 新增统计字段 | CSV 日志加 `anchor_type`（OB / BREAKER），供日后评估开关是否值得打开 |

**Trading Logic Changed：YES（默认行为改变，已获用户明确批准）。**

> **对回归测试的影响（重要）：** `docs/04` 的 POI-07 等价性测试（v1.x 与新版 CSV 逐行相同）
> 从 v2.00 起**必须先把 `InpEnableBreaker` 设为 true** 才能与 v1.x 对比，
> 否则差异来自这次刻意的默认值变更，不是 bug。

---

## 裁决记录 —— 工程师规则决策补充（2026-09-24）

> 来源：《HMI v2.36 规则决策补充（工程师版）》。用户转交并认可。
> 以下为落地要点，冲突时以补充件为准。

### BRI-07 —— RESOLVED

| 事件 | 新 session | 已有未结束 session | 已 ARMED cycle |
|---|---|---|---|
| H4 同向趋势 | 允许合格 POI 触发 | 可继续 | 沿用周期规则 |
| H4 进入 TRANSITION / RANGE | **禁止** | **结束**，禁止后续新 ARMED | 保留生命周期，标记 context_changed |
| H4 确认反向趋势 | 仅允许新方向 | 结束旧方向 | 保留生命周期，标记 context_changed |

附带约束：

- 禁止触发时**不得**把 POI 标记为已触碰、**不得**消耗 session 配额
- **不得**在 context 不合格时先建 block、再由 SessionMaintain 善后
- 既有 ARMED cycle 本次**不**改为强制取消（如需，另立变更）
- 面板显示当前 H4 状态，不跟随旧 cycle 方向

### BRI-08 —— RESOLVED

采用「首次有效收盘越过阈值」语义，**不要求上一根位于原始参考价另一侧**。

```
多头：close > level + margin        空头：close < level - margin
严格大于 / 小于，沿用整数 point 比较；等于阈值不算
```

例：level=100、margin=3，收盘 99 → 101 → 104。101 不确认，104 确认，
无需先退回 100 以下重新穿越。

**现状差异（已查证）：**

```mql5
// H4DetectBreak —— 已是该语义
if(ih >= 0 && BreakUp(g_h4[h].close, g_h4sw[ih].price, mp))

// CISD_Check / MSS_Check —— 额外要求上一根在原始参考价另一侧
ok = (Pts(prev, cy.cisd_level) <= 0) && BreakUp(cur, cy.cisd_level, mp);
```

故本条**只改 CISD / MSS**；H4 与 POI / block 失效条件不动。

防止迟到伪事件（三条，缺一不可）：

1. 每个参考点保存「是否已发生有效突破」，首次确认后消费，不重复确认
2. ARMED 冻结参考时，检查该参考在「形成 → ARMED」区间内是否已被有效突破；
   已突破则按资格规则排除或置 NA —— **不得把 ARMED 之后持续站在阈值外的
   状态伪装成新突破**
3. 处于参考价与有效阈值之间不算已突破；后续首次达到阈值可以确认

PA 的 ARMED-bar 特例**不**随本条扩展到 CISD / MSS。

margin 沿用逐根计算（动态 ATR），不引入「余量冻结」。日志记录每根实际余量。

### BRI-08 修订稿 2 —— v2.55 定义、成对场景与诊断日志（验收方确认 2026-10-20）

基线：v2.54（MQL 3813868 + 工具 r8，docs/baselines/v2.54.md）。修订稿 1 的核心定义经验收方「HMI v2.55 定义稿审核与工程师
补充要求」（2026-10-20）确认，修订稿 2 补齐其两项验收设计：MSS C5 场景改用合法摆动点；诊断日志给出足以核对历史余量的字段。
不改 H4、不改余量模式与参数（params 摘要仍 461F006E）。离线模型 `python3 tools/bri08_sim.py`：29 个场景 × 多空镜像 ×
v2.54 / v2.55，372/372（含每周期每模型最多一次、确认只在 A 之后、MSS 摆动点由 SwingDetect 规则生成三项不变量）。

**B8-1 范围（已确认）**

| 位置 | v2.54 | v2.55 |
|---|---|---|
| CISD 确认（spec §10.2，`CISD_Check`） | `close[n-1]` 在未突破侧 **且** `close[n]` 有效越过 | 只看 `close[n]`：首次有效越过 |
| MSS 确认（§11.2，`MSS_Check`） | 同上 | 同上 |
| CISD 参考（§10.1，Rule 19） | 不检查 ARMED 前是否已被越过 | 选法不变；`[k+1, A]` 内有一根以当根余量有效越过 `open[k]` → 本周期 CISD = N/A，不另找 run |
| MSS 参考 C5（§11.1） | 用 bar A 的余量判断全部历史根 | 历史第 i 根用 `MarginM5Pts(i)`；排除后按 C1..C5 取下一个。固定余量下与 v2.54 相同 |
| H4 BOS / CHOCH、保护点与锚点、POI、Session、区块、ARMED 仲裁、周期、BPR、PA（含 D-4）、流动性 | — | **不动**；CISD / MSS 仍只在 `n > A` 确认，每周期每模型最多一次，N/A 不影响其他模型 |

**B8-2 定义**（整数 point，`Pts()`；`m(n) = MarginM5Pts(n)`，固定余量模式为常数，ATR_FRAC 为逐根，不冻结阈值）

```
有效越过 L（第 n 根）  多头 Pts(close[n], L) >  m(n)      空头 Pts(close[n], L) < -m(n)      严格；等于不算；影线不算
区间内                 多头 0 < Pts(close[n], L) <= m(n)   不算越过，不消费参考；之后首次有效越过可以确认（防护 3）
确认                   n > A、本周期该模型仍 PENDING、第 n 根有效越过 → 确认于 n；每周期最多 1 次（Rule 43，防护 1）
ARMED 前已越过         CISD：存在 i ∈ [k+1, A] 使第 i 根以 m(i) 有效越过 open[k]  → CISD = N/A（防护 2）
                       MSS ：C5 = 存在 i ∈ (swing, A] 使第 i 根以 m(i) 有效越过     → 该候选排除
```

两个区间都含 ARMED 当根 A。k 本身是反向 K 线，收盘不可能越过自己的开盘，从 k+1 起与从 k 起等价。
余量逐根：S08 中收盘价不变而余量下降，在首次满足阈值的那根确认 —— 这是定义的明确行为，不是价格出现了新位移。

**B8-3 成对场景**（多头形式；L = 100，m = 3，除非注明；空头为价格取反、高低互换的镜像，结果相同。
MSS 场景的摆动点由 `detect_swings()`（SwingDetect，左右各 2 根，左严格、右不严格）从 K 线生成，不手写）

| 场景 | ARMED 及之后的收盘 | v2.54 | v2.55 | 说明 |
|---|---|---|---|---|
| S01 缓慢穿越 | A 99 → 101 → 102 → 104 | 无 | 104 那根 | v2.54 因上一根已在 L 上方永远不确认 |
| S02 穿越后回落再上 | 99 → 101 → 99 → 104 | 104 | 104 | 101 不算越过 |
| S03 一根直接越过 | 99 → 104 | 104 | 104 | 不变 |
| S04 影线 | 99 → 收 102 高 110 → 104 | 无 | 104 | |
| S05 影线（下方收） | 99 → 收 99 高 110 → 104 | 104 | 104 | 不变 |
| S06 恰等于余量 | 99 → 103 → 104 | 无 | 104 | 103 = L + m 不算 |
| S07 A 收在 L | 100 → 104 | 104 | 104 | v2.54 的 `<=` 含等于 |
| S08 ATR 余量下降 | 99 → 104（m=5）→ 104（m=3） | 无 | 第二根 104 | 阈值逐根 |
| S09 ATR 余量上升 | 99 → 104（m=5）→ 106（m=5） | 无 | 106 | |
| S10 恰等于升高后的余量 | 99 → 104（m=5）→ 99 → 105（m=5）→ 106（m=5） | 无 | 106 | |
| S11 A 收在区间内 | 101 → 104 | 无 | 104 | 防护 3 |
| S12 A 收盘已越过 | 104 → 99 → 104 | 第二个 104 | **N/A** | 防护 2 |
| S13 run 与 A 之间已越过 | (105) → A 98 → 104 | 104 | **N/A** | |
| S14 run 与 A 之间只到区间 | (102) → A 98 → 104 | 104 | 104 | |
| S15 ARMED 前按当根余量 | (104，当根 m=5) → A 98 → 104 | 104 | 104 | |
| S16 每周期一次 | 99 → 104 → 98 → 105 | 第一个 104 | 第一个 104 | |
| S17 零余量（XAUUSD 默认） | 99 → 100 → 101（m=0） | 101 | 101 | |
| S18 零余量，A 收在 L+1 | 101 → 99 → 101（m=0） | 第二个 101 | **N/A** | |
| S19 窗口内无反向 K 线 | — | N/A | N/A | |
| S20 B8-SHIFT | 99 → 101 → 104 → 98 → 104 | 第二个 104 | 第一个 104 | 同一周期、同一冻结参考，确认时间错开 |
| M01 MSS 缓慢穿越 | 摆动高点 100（第 2 根，第 4 根确认）；A 97 → 101 → 102 → 104 | 无 | 104 | |
| M02 MSS 一根越过 | 97 → 104 | 104 | 104 | 不变 |
| M03 MSS 影线 + 恰等于 | 97 → 收 99 高 108 → 103 → 104 | 无 | 104 | |
| M04 C5 保留 | 高点 100 确认后第 5 根收 104（当根 m=5），第 6 根高 106 未确认；A=7（m=3）→ 第 8 根收 106 | N/A | 第 8 根 | 验收方夹具；ATR_FRAC 才出现 |
| M05 C5 排除 | 同上，第 5 根 m=3、A 的 m=5 | 第 8 根 | N/A | 验收方夹具 |
| M06 C5 排除后取下一个 | 较新的 100 被收盘 105 吃掉；较老的 108（第 2 根）→ 112 | 112 | 112 | 第 12 根高 107 在 A 时未确认 |
| C01 周期切换 | 周期 1 A=3：101 → 104 → 98；第 7 根收 105 并 ARMED 周期 2（L2 = 104）→ 108 | 周期 1 于第 7 根 | 周期 1 于第 5 根；周期 2 于第 8 根 | 第 7 根先按 Phase 4 检查旧周期，再按 Phase 5 ARMED 新周期 |
| C02 同一 run 的周期切换 | 周期 1 A=3：101；第 5 根收 104 并 ARMED 周期 2（同一 run）→ 99 → 104 | 周期 2 于第 7 根 | 周期 1 于第 5 根；周期 2 N/A | 同一参考不会被两个周期各确认一次 |
| C03 整段只记一次 | 99 → 104 → 98 → 105 → 97 → 106 | 1 次 | 1 次 | 事件列表计数，不只看首次命中 |

规则核的余量是显式输入，不是这些 K 线自己算出的 ATR；原生 MT5 测试以日志里的实际余量核对。

**B8-4 v2.54 → v2.55 差异与归因顺序**（跨版本归因只认具体日志行）

```
1. B8-C5    MSS：v2.55 HMI-REF 的 level/ref 与 old_level/old_ref（旧规则只读对照）不同，且 c5diff 中有对应候选的
            决定性证据（检查根收盘、当根余量 chk_mp、ARMED 余量 armed_mp，o/n 两种判定按算式复核成立）
            —— 冻结参考不同的差异先归这一类
2. B8-SLOW  同一冻结参考：v2.55 在 n 确认，HMI-BRK 的 prev_close 在区间内（越过 L，但按 prev_mp 未有效越过）
            —— v2.54 在 n 不可能确认
3. B8-SHIFT 同一周期、模型、方向、冻结参考（level 与 ref）：v2.54 在之后「回落再穿越」的 n' 确认，v2.55 已在 n 确认（B8-SLOW 的后果）
            —— 只因一前一后各有一个标记不算
4. B8-NA    CISD：v2.55 HMI-REF state=NA_BROKEN，brk_bar ∈ [run_from + 1, A]，brk_close 按 brk_mp 有效越过 cand_level；
            v2.54 同周期的 CISD（level = cand_level）在 n > A 确认，或不确认
其余        H4 结构、CTX / PROT、POI、Session、区块、ARMED、周期、BPR、PA、流动性行 —— 两版必须逐行相同，任何差异都是 UNEXPLAINED；
            MODEL 行在上述四类之外的差异也是 UNEXPLAINED
```

面板上 B8-NA 会显示「CISD N/A」（只显示；Rule 44）。

**B8-5 诊断日志**（InpLogSignals = true；MODEL 行格式不变，两版直接比较；不新增输入）

```
HMI-REF,<sym>,CISD,cycle=<id>,dir=<1|-1>,live=<0|1>,armed=<A 收盘时间>,armed_mp=<A 余量>,state=OK|NA_NONE|NA_BROKEN,
        level=<有效参考价|NA>,ref=<参考 K 线开盘时间|->,cand_level=<Rule 19 候选价|NA>,run_from=<k 开盘时间|->,run_to=<j 开盘时间|->,
        brk_bar=<第一根有效越过的开盘时间|->,brk_close=<其收盘|NA>,brk_mp=<其当根余量|NA>,inst=,run=,init=
HMI-REF,<sym>,MSS,cycle=,dir=,live=,armed=,armed_mp=,state=OK|NA_NONE,level=,ref=<摆动 K 线开盘时间|->,
        old_state=OK|NA_NONE,old_level=,old_ref=,c5diff=<条目;条目|->,inst=,run=,init=
        c5diff 条目 = <候选摆动时间>@<候选价>/<检查根开盘时间>/<检查根收盘>/<检查根余量>/o<0|1>n<0|1>
        —— 新旧 C5 判定不同的每个候选（C1..C4 通过、扫描到两版选中者中较老的一个为止），两个方向都记：
           o1n0 旧排新留（检查根 = 按 ARMED 余量第一根越过的根）；o0n1 旧留新排（检查根 = 按当根余量第一根越过的根）
        old_* 是旧规则（C5 用 armed_mp）选出的参考与状态，只读诊断，不写入周期、不影响任何判定
HMI-BRK,<sym>,CISD|MSS,cycle=,dir=,live=,bar=<确认根开盘时间>,close=,mp=<确认根余量>,prev_bar=<前一根开盘时间>,prev_close=,
        prev_mp=<前一根余量>,level=,ref=,inst=,run=,init=
```

时间口径：`armed` 为 ARMED 根**收盘**时间（与 HMI-ARM 的 bar= 相同）；`bar`、`prev_bar`、`ref`、`run_from`、`run_to`、`brk_bar`
与 c5diff 内的时间为 M5 **开盘**时间（MODEL 行打印的是确认根收盘时间 = 开盘 + 5 分钟）。前一根由 `prev_bar` 明示，
工具不得用「减 5 分钟」推断缺口处的上一根。余量只记判定涉及的根：确认根、前一根、ARMED 根、历史越过证据根 —— 各取那一根
自己的 `MarginM5Pts()`，不用确认根或 ARMED 根的余量替代。HMI-REF 在每个 ARMED 时每模型一行，HMI-BRK 在每次 CISD / MSS 确认时一行；
两者都在 build 与 live 中输出，作为独立判定类别（同窗口重载、实时 vs 重建），`-Versus` 增 BRI-08 模式。

**B8-6 验收方确认（2026-10-20）**

核心规则 1–6 确认（只改 CISD / MSS；首次有效收盘；CISD `[k+1, A]` 越过 → N/A 不另找 run；MSS C5 逐根余量；区间含 A；
余量逐根不冻结）；无需另开业务选项确认。实现版程序版本 2.55，参数摘要保持 461F006E；新日志只用于诊断。
实现顺序：CISD / MSS 确认及参考冻结 → 新诊断行 → ReloadTest 新类别与 BRI-08 归因 → 日志反例 → 场景与原生输出对照 →
编译 → v2.54 / v2.55 同窗口比较。

### §6.1 Q_break —— RESOLVED

- 价格类分项（强度、K 线重叠）仍用最近 **12** 根已收盘 H4
- Q_break 改用：当前趋势段内、最近 **60** 根内发生、最近最多 **5** 个已完成观察的同向 BOS
- 观察期仍 **3** 根；未完成不进分母
- **最少 3 个成熟事件**才计算 Q_break 及包含它的质量总分
- 新趋势段不继承旧段样本；TRANSITION 后重新确立方向视为新段（即使方向相同）
- n=3/4 标「低样本」，n=5 标「5 次事件」，均不宣称统计置信
- 样本不足时**不得**补 50 分 / 满分 / 悄悄归一化权重；改显示「局部表现」

### §4.2 —— 拆成两个独立字段

| 字段 | 用途 | 单调约束 |
|---|---|---|
| `protected_level` | 判定趋势结构失效（决定 CHOCH） | 多头只升不降，空头只降不升；**不跨趋势段** |
| `leg_anchor` | 计算波段推进 / 回撤比例 / 阶段 | 无单调约束；可低于旧保护点 |

- 回撤分母改用 `leg_anchor`，**不再用** `protected_level`
- 影线下探但收盘未构成有效破坏 → `protected_level` 不放宽
- 一旦发生超余量收盘破坏 → **在那一根**切换 TRANSITION，不等后续 BOS
- 两字段必须独立命名、独立时间戳、独立日志、独立测试，禁止互相覆盖
- 记录保护点年龄；点位旧 ≠ 失效，但也不作为近期质量好的证据

### A-33 + §4 —— 立项为新结构规则版本

- 版本号**按现有规范继续递增**，不因「v2.00 级」而从 2.37 倒退编号
- 保留原冻结版、原日志、原行情数据作为可复现旧行为的对照，**不删除旧证据**
- POI-01 / 02a / 02b 与四品种端到端在新规则下**重验并重新批准预期值**
- 「旧基线作废」= 不再用旧输出强制要求新规则完全相等，**不等于**删除
- 分开提交：基础修复 / 结构规则 / 评分面板，各自说明是否预期改变信号

---

## BRI-09 —— RESOLVED：PDH / PDL / PWH / PWL / PMH / PML 与 Liquidity Sweep（v2.42）

**用户 2026-09-30 签字：「BRI-09 六项都同意」—— S-1 至 S-6 全部按 ★ 建议值落地。**

来源：用户 2026-09-30「加入 PWL、PDL、PDH、PWH 这些重要的流动性，并且添加识别 liquidity sweep」；
同日补充「不能只加 PDH/PDL/PWH/PWL，加入月的」→ 增加 PMH / PML（上月高 / 低）。

与现有规则的关系：
- 现有 §3.4 Liquidity 只有 H4 Swing 的 BSL / SSL，`SWEPT` = H4 影线越过即算，
  **不区分「扫了收回」与「直接突破」**。用户要的 sweep 是前者。
- Rule 1 / Rule 69：Liquidity 只标记、不过滤。本草案维持这一点。
- Rule 68：v2.41（A-37 诊断）先单独验收，本功能单独成一个版本。

需要签字的 6 项（每项给出建议值，★ 为建议）：

```
S-1 作用范围
    ★ (a) 只标记 + 日志，不进入 POI / Session / 模型链（Rule 1 / 69 不变）
      (b) 作为标记链的过滤条件 —— 属于业务规则变更，需另行立项

S-2 日 / 周 / 月边界
    ★ (a) 券商服务器时间的 D1 / W1 / MN1 K 线（多数券商 GMT+2/+3 对齐纽约 17:00 收盘）
      (b) 固定纽约 17:00 自行切分
    附：若券商有周日短 K 线，PDH/PDL 是否跳过它取上一个完整交易日  ★ 跳过

S-3 Sweep 判定（M5 收盘 K 线，越过幅度沿用现有 break margin，D-6）
      (a) 同一根 M5：影线越过 + 收盘收回
    ★ (b) 越过后 N 根 M5 内收盘收回即为 SWEEP；N 根内未收回则为 BROKEN（突破）
          N 默认 3（15 分钟），参数可调；(a) 即 N = 0
    提交时刻 = 收回那根 M5 的收盘（AX-1），不回头改历史

S-4 一个水平位只产生一次事件
    ★ 是 —— SWEEP 或 BROKEN 之后该水平位不再判定

S-5 现有 H4 Swing BSL / SSL 是否改用同一判定
    ★ 是 —— 全指标只有一种「sweep」定义；原来的「影线碰到即 SWEPT」
      改为 SWEEP / BROKEN 两类（显示变化，不影响任何标记）
      否 —— 保持原样，只对 PD/PW 水平位做新判定

S-6 显示
    ★ 只画当前的 PDH / PDL / PWH / PWL / PMH / PML 六条线（标签用缩写，不写方向含义）；
      三组可分别开关（InpShowPD / InpShowPW / InpShowPM）；
      SWEEP / BROKEN 在发生的 K 线上标注，保留最近 InpLiqSweepDays 天（默认 5）
    日志：HMI-LIQ,<sym>,SWEEP|BROKEN,level=PDH|PDL|PWH|PWL|PMH|PML|BSL|SSL,px=,bar=
          —— 同样纳入 LIVE vs BUILD 比对（sweep 本身也是标记，必须不重绘）
```

不包含：sweep 的方向含义（「扫高 = 看跌」之类）。这属于交易判断，Rule 1 不做。

附（月线专属）：
- 月初第一天，PMH / PML 取上一个完整月；数据窗口（5000 根 M5 ≈ 26 天）
  不足一个月不影响，月线水平位直接取 MN1 K 线，不从 M5 推算。
- 同一价位可能同时是 PDH 与 PWH（或 PMH）—— 各自独立判定、各记一条事件，
  显示时合并为一条线、标签并列（如「PDH·PWH」）。 ★

---

## BRI-10 —— TOUCHED → ARMED 的「再次触碰」定义（v2.49，D-11）

来源：代码审查（2026-10-01，v2.48 全部源文件静态通读）。

规格两处不一致：
- §7.2 状态表：`TOUCHED → ARMED | 后续 K 线再次触碰且仲裁胜出`
- §8.3 ARMED 前置条件第 1 条：`Block 状态为 ACTIVE`

v2.48 按 §7.2 实现，并把「K 线区间与 Block 相交」（§8.1 的触碰定义）直接当作「再次触碰」。
后果：第 n 根同时触到 B1、B2，B1 按 §8.4 胜出 ARMED，B2 → TOUCHED；第 n+1 根价格仍在
两个区间内，B1 已 ARMED 不参与仲裁，B2 作为 TOUCHED 直接胜出 → ARMED，B1 的 Cycle 在
一根之后被关闭、六个模型全部 PASS。三个重叠 Block 就是三根 K 线三个 Cycle。
重建与实时一致，ReloadTest 查不出。

两种读法：
```
  (a) v2.48 字面：仍在区间内 = 再次触碰 → 落选者下一根即可反手 ARMED
★ (b) 「再次触碰」= 新的触碰事件：上一根已收盘 M5 K 线不与该 Block 相交，本根相交。
      价格离开后再回来的 TOUCHED Block 仍可 ARMED（§7.2 保留）；
      停在区间内不算（§8.3 的 ACTIVE 精神）。ACTIVE Block 的首次触碰天然满足 (b)。
```

**D-11 —— 采用 (b)。** `InpArmRequiresFreshTouch = true`（默认）；`false` = (a)。
进入参数摘要（两种设置的构建不可互比）。交易逻辑改变：YES。
~~工程师裁决，待用户确认；如改回 (a)，只需改默认值，不动代码。~~

**v2.50（用户 2026-10-02 范围决定）：撤回。** 基线恢复为 (a)，不保留开关。(b) 连同
「TRANSITION 超时同根继续判定 BOS」一起保留在 v2.49 提交 30a288b（见 docs/07）和随 v2.50
一并交付的两个补丁文件中，各自独立出版本、独立说明信号变化并回放验收后再定。本条 **OPEN**。

---

## BRI-11 —— BOS 去重的触发条件读法（v2.53，A-33）

来源：用户 2026-10-06 v2.53 需求（只处理 BOS 去重）：
1) 同一根已收盘 H4 有效突破多个同向旧摆动点，只产生一次结构事件；
2) 本次已被有效突破的同向旧点一并标记已处理，后续不能逐根补计；
3) 主参考点选择最近已确认、未处理且被有效突破的同向摆动点；
4) 仅使用当时已确认的摆动点；余量、保护点、评分留在各自版本。

第 3 条有两种读法，事件发生时两者结果相同，分歧只在「最近的未处理点没被突破、更老的被突破」时：

```
★ (甲) 触发条件不变（Spec §2.2「最近一个已确认 Swing」= 最近一个已确认未处理点被突破）；
       触发时其余被这根收盘突破的同向旧点一并处理。主参考点就是那个最近点 ——
       它同时满足「最近、已确认、未处理、被有效突破」。
       与 v2.52 的差异只来自「去掉重复计数」，所有变化可逐条追溯（用户要求）。
  (乙) 任一未处理旧点被突破即触发，在被突破的点中取最近者为主参考点。
       会在 v2.52 没有事件的时刻新增事件（例：较新的更高高点未破、较老的更低高点被破），
       属于触发规则变更，超出「只处理 BOS 去重」。
```

**v2.53 采用 (甲)。** (乙) 若需要，归入保护点 / 结构规则版本（§4.2）另行立项。
验收方 2026-10-06 复核：接受 (甲) 的范围解释（本版未实现「任意旧点被突破就产生事件」）。
(甲) 下不存在陈旧补计：一个点若曾被某根收盘越过，要么当时它就是最近点（当根处理），
要么当时有更新的未处理点 —— 更低的那个也被越过（当根触发并一并处理），更高的那个
日后被突破时这根收盘必然也越过它（一并处理）。它不可能在被越过之后再单独成为主参考点。


---

## BRI-12 —— 保护点 `protected_level` 与波段锚点 `leg_anchor`（v2.54，修订稿 2）

来源：《HMI v2.36 规则决策补充（工程师版）》第三节（结构保护点与波段锚点分开维护，替代两者混用的旧描述）、
原需求第 4.2 节（结构选点与反转时序，继续有效）；验收方 2026-10-09 开发安排、2026-10-13《v2.53r6 验收复核与 v2.54 交接》。
两份原文在验收方交接包中，工程师侧尚未收到；P-1、P-5 采用验收方给出的替换文字，原文如有出入以原文为准。

修订记录：草案（535de9b）→ 修订稿 2：P-1 加上「被突破主参考点之后形成」的起始边界；P-5 由「TRANSITION 内不变」
改为反转与恢复都需 CHOCH 之后形成并确认的新结构；P-6 拆为既定要求（P-6a）与单列的边界规则（P-6b）。

**时间戳定义（全条通用）：** 摆动点的形成时间 = 摆动 K 线的开盘时间（`bar_time`）；确认时间 = 第 R 根右侧 K 线的收盘时间
（`confirm_time`）；H4 事件时间 = 该 K 线收盘时间。CHOCH 时间 `t_choch` = CHOCH 那根 H4 的收盘时间。
CHOCH 之后第一根 K 线的开盘时间等于 `t_choch`，所以「在 CHOCH 之后形成」写作 `bar_time >= t_choch`（含等号）；
CHOCH 那根 K 线本身开盘早于 `t_choch`，属于旧结构。

```
P-1 候选点（每次 BOS 取一次；多头为例，空头对称）
    有效向上 BOS 时，以本次被突破的主高点为起始边界，选择在该高点之后、BOS 之前最近形成，且在 BOS 收盘时已经确认的
    合法回撤低点；不得将主参考点之前形成的旧点充当这次新候选点。
    实现：  主高点.bar_time < 低点.bar_time，低点.confirm_time <= BOS 收盘，低点未被处理，
            且确认之后直到本根（含本根）没有任何收盘以超过当根余量越过它（v2.54r2，A-65）；
            多个符合时取 bar_time 最晚者。本根收盘已越过的反向点先按 P-4 处理，再选点
    无合法候选点：保留仍适用的旧定义（同段已有保护点则保持）；没有任何可用定义 → INVALID（结构样本不足，P-6a）；
    不得用失效的点补齐
    读法（验收方 2026-10-13 确认）：「最近形成」= 形成时间最晚，不以「取最低点」替代；
      「合法」= 当时已经确认、且未被有效收盘破坏 ——「未处理」标志不等于未被破坏

P-2 protected_level（结构失效判定）
    新趋势段的第一次 BOS（RANGE → BOS、TRANS_OK、TRANS_FAIL）：protected = 候选点；无候选 → INVALID
    同一段内后续 BOS：候选点更高 → 上移（ADVANCE）；更低或相等 → 保持（KEEP_WORSE）；无候选 → 保持（KEEP_NONE）；
    此前 INVALID 而出现候选 → SET
    单调约束只在同一趋势段内；TRANSITION 之后重新确立方向是新段（即使方向相同），不继承

P-3 leg_anchor（本版只记录，不参与判定）
    每次 BOS 取同一个候选点，无单调约束（MOVE），可以比保护点更差；无候选 → 保持（KEEP_NONE）
    独立字段、独立时间戳、独立日志行，与保护点互不覆盖；回撤分母日后用 leg_anchor（评分版本）

P-4 结构破坏
    只有收盘越过保护点且超过余量（整数点、严格比较，与所有 H4 突破同一余量语义）才 CHOCH，并在这一根进入 TRANSITION；
    被破坏的保护点及这根收盘同样越过的其它已确认未处理低点一并处理（A-33）
    影线越过、或收盘越过原始价但未超过余量：不破坏，保护点不放宽
    保护点之上的内部低点被有效收盘跌破：不改状态、不改强度；该点标为已处理，记一行 HMI-CTX-INTERNAL。
    本根收盘越过的全部已确认未处理反向点都处理（不只最近一个 —— 较新的未破坏点会遮住较旧的已破坏点）；
    同向 BOS 那一根也处理，且在选保护点之前（v2.54r2）

P-5 反转与恢复（替换草案的「TRANSITION 内不变」）
    反转确认需要 CHOCH 之后形成并确认的新反向结构，再发生有效突破；原方向恢复也需要新结构的有效突破。
    必须同时核对摆动点形成时间和确认时间。CHOCH 之前或发生于 CHOCH 那根 K 线的旧点，即使之后才确认，
    也不能当作新的反转或恢复结构。
    实现：  新结构 ⇔ bar_time >= t_choch 且 confirm_time > t_choch；TRANS_OK 与 TRANS_FAIL 都要求新结构；
            旧结构被突破（任一方向）→ TRANS_SAMELEG：该点被处理，状态不变（v2.53 只对 TRANS_OK 查确认时间，
            TRANS_FAIL 不查）
    TIMEOUT 先于突破判断、全局余量语义：沿用基线

P-6a 保护点 INVALID（既定要求）
    无合法新点且无旧保护点 → 明确标记 INVALID（结构样本不足）：HMI-PROT / HMI-ANCHOR 行 event=INVALID，level=NA

P-6b 边界规则（新增，单列；验收方 2026-10-13 建议保留，定为默认行为）：INVALID 段的结构破坏
    保护点 INVALID 期间，趋势的失效按 v2.53 规则判断：最近一个已确认、未处理的反向摆动点被有效收盘越过 → CHOCH，
    记 HMI-PROT event=FALLBACK。这是新增的降级行为，不是保护点需求本身；FALLBACK 不表示真实保护点已成立，
    INVALID / NA 与 FALLBACK 持续记录
    不设此条的后果（离线模型）：INVALID 段只有在后来某次 BOS 取得候选点后才可能结束 —— 价格反向运行时
    趋势状态长期不变（EURUSD 样本 27% 的趋势 K 线处于 INVALID，空头状态 H4 根数由 263 增到 543）
    对趋势 / Session / MODEL 的影响：P-6b 只作用于 INVALID 段，段内的 CHOCH 与 v2.53 相同；
    Session 资格与 MODEL 仍按 H4 状态（BRI-07）变化，没有另外的规则

P-7 同一根 H4 的处理顺序
    ① 本根收盘确认的新摆动点 → ② TRANSITION 超时 → ③ 趋势中先用「本根之前的」保护点判定破坏（INVALID 时按 P-6b）
    → ④ 未破坏才判定同向 BOS → ⑤ BOS 去重 → ⑥ 本根收盘越过的反向点按 P-4 处理（有无 BOS 都做）
    → ⑦ 有 BOS 时按 P-1 选点、更新保护点 / 锚点（对下一根生效） → 写日志。同一根至多一次状态事件，⑥ 只是诊断记录
    RANGE / TRANSITION 中沿用 v2.53 的检测（先上后下），TRANSITION 中按 P-5 判断新结构；新段第一次 BOS 同样先 ⑥ 再 ⑦。
    继承自 v2.53 的不对称：一根收盘同时越过高点与低点时，RANGE / TRANSITION 取向上那一次（离线场景已写明）

P-8 记录（只记日志，图形留在显示阶段）
    HMI-PROT,<sym>,<event>,dir=<段方向>,live=,leg=<段序号>,bar=<H4 收盘>,level=,swing=<形成>,confirm=,bos=<取点的 BOS>,
             age=<H4 根数>,prev=<上移前>,cand=<本次候选>,inst=,run=,init=
             event: SET / ADVANCE / KEEP_WORSE / KEEP_NONE / INVALID / BREAK / FALLBACK
    HMI-ANCHOR 同格式，event: SET / MOVE / KEEP_NONE / INVALID / RESET
    HMI-CTX-INTERNAL,<sym>,dir=<被越过点的方向>,live=,ctx=,bar=,swing=,swing_px=,close=,also=,swings=,prot=,inst=,run=,init=
    HMI-CTX 行格式不变；Phase 0b 资格检查不变
```

不在本版：BRI-08（CISD / MSS 突破语义）、强度评分、质量评分、趋势面板、图形；全局余量语义不变。

**离线模型（`tools/h4_protect_sim.py`，与 v2.53 模型同一套摆动 / 去重 / POI 规则，只换 BRI-12 部分）：**
v2.54r3 场景 45/45（另含回放判定注入 5 组、「另有合法候选：保护点保持、锚点移动」多空 2 组）；r2 场景 38/38：另含 A-65（ATR 余量收缩，同一收盘越过主高点与更高的回撤低点：多空续段、多头首段、空头首段按 v2.53
先上后下的说明、已安装点不在确认后被越过的不变量）。v2.54 开发版场景 32/32（多空各 16：合法新点上移、更差候选保持且锚点取它、影线越过不破坏、收盘越过原价未超余量不破坏、
有效破坏当根 TRANSITION、内部低点跌破只处理不翻转、无合法点 INVALID 且不取主参考点之前的旧点、
之后才确认的点不作候选、BOS 当根确认的点可作候选、CHOCH 那根的旧低点之后确认仍排除、新低点 → TRANS_OK、
CHOCH 前的旧高点 → 不恢复、新高点 → TRANS_FAIL、CHOCH 后第一根形成的点算新结构、P-6b 有 / 无、新段重置、无重绘）。

EURUSD H4 1292 根（2017-04 .. 2018-02）：

| | v2.53 | v2.54 | v2.54 无 P-6b |
|---|---|---|---|
| BOS | 63 | 74 | 81 |
| CHOCH | 45 | 24 | 14 |
| TRANS_OK / TRANS_FAIL | 25 / 19 | 10 / 8 | 6 / 3 |
| TRANS_SAMELEG | 8 | 13 | 5 |
| TIMEOUT | 1 | 6 | 5 |
| 内部点跌破（INTERNAL；r2 起含 BOS 当根与被遮住的点） | - | 38 | 59 |
| 趋势段 / 起始即 INVALID | - | 25 / 12 | 15 / 7 |
| INVALID 的趋势 K 线 | - | 13% | 27% |
| 段结束：BREAK / FALLBACK | - | 17 / 7 | 14 / 0 |
| 最大强度 | 7 | 17 | - |

A-65 修复前后在这段数据上 H4 状态完全相同（固定余量与 ATR 0.20 两种模式：开发版装入已被越过的点 0 次），差别只在 INTERNAL 行数。
H4 状态与 v2.53 不同的 K 线 407 / 1292；H4 POI 事件只在 v2.53 70 条、只在 v2.54 58 条。逐根截断无重绘。
模型只覆盖 H4；Session、M5 区块与 MODEL 的变化要在 MT5 里比较。

**跨版本归因（v2.54r4 完成，`tools/h4_protect_attr.py` 离线模型 + `ReloadTest -Versus` BRI-12 模式）：**
新版本 ≥ 2.54、旧版本 < 2.54 时启用。每条差异连到日志里的具体行，不以「发生在规则改动之后」解释：
- 日志自洽（否则 UNEXPLAINED）：v2.54 每条 CHOCH 同根有 HMI-PROT BREAK（level = 该 CHOCH 摆动价）或 FALLBACK；
  FALLBACK 只出现在从未有过保护点的段；INTERNAL 的收盘越过自己的摆动点、未越过保护点（按日志余量）；
  TRANS_SAMELEG 的摆动点形成于 CHOCH 之前；str 与 messy 符合规则；收盘与摆动价两版一致
- 进入该根时两版状态相同：差异须由本根的 BRI-12 行解释 —— P-4（v2.54 CHOCH 有 BREAK；或 v2.53 CHOCH 的摆动点在 v2.54
  同根记为 INTERNAL）、P-5（v2.53 TRANS_OK / FAIL ↔ v2.54 TRANS_SAMELEG，同一摆动点、形成于 CHOCH 之前）、
  P-7（INVALID 段的 FALLBACK 与 v2.53 先判向上）、两版的 TRANSITION 由不同且已解释的 CHOCH 打开（超时与新结构各按自己的 CHOCH 计）、
  摆动点已被另一版更早处理（注明时间与来源行）及其后同根改引用的下一个摆动点；否则 PENDING_ATTRIBUTION
- 进入该根时两版状态不同：只在「起点已解释」的分歧区间内解释（状态差异本身来自两版日志的 ctx 字段）
- 段属性（str / messy）：两版各自符合规则，且较早的段起点以来的差异全部已解释
- 链路（POI → Session → Block → ARMED → MODEL）：沿用 A-57 / A-58 规则；凡以 H4 方向不同作理由的，该时刻须处在起点已解释的分歧区间内；
  POI 在另一版已被已解释的 OUT 移出窗口后，其 INVALID / EXPIRED 只在一版出现 → 已解释
- 限制：分歧区间内各行不逐行重推（日志只有事件根的收盘），只核对各版自身规则；M5 链路只能在 MT5 日志上验证
验证：离线模型 EURUSD 302 / 0 / 0、合成序列（种子 37）200 / 0 / 0、篡改防护 9/9；同一运行写成 MT5 日志后
ReloadTest 与模型逐类一致（EURUSD 302、种子 11 171、种子 37 200，均 0 PENDING / 0 UNEXPLAINED）；logtests v01–v08
（种子 37 与 7 种篡改），v2.54r3 脚本 8 组全部失败（docs/evidence/v2.54_attribution_offline.txt）

---

## BRI-13 —— v2.56 强度评分（修订稿 2：按原需求 §5 三项合成，验收方 2026-10-26 口径）

来源：《HMI 趋势面板改造需求（工程师版）》（2026-09-24，基于 v2.33；原文已入库 `docs/requirements/`）§3 / §5 / §10 / §11，
验收方「HMI v2.56 定义稿审核与工程师修订口径」（2026-10-26）。

**定义稿 1 撤回。** 定义稿 1（同日）在没有原文的情况下只用「12 根净推进 / ATR」一项，改变了原需求的强度含义：原需求是
净推进 45% + 方向效率 35% + 近期动量 20%，净推进满分 3 ATR、近期动量满分 1 ATR，分档 35 / 65 按未取整分数。验收方的对照：
同样净推进 1400 point、同样 ATR 500，连续推进与「前段上涨、近期回撤」在定义稿 1 中都是 70；原定义分别是 91 与 56。本稿恢复原定义，
定义稿 1 的 CAP 4 ATR、34 / 64、6 项待确认选择全部作废；它的 53/53 不作为本版验收结果。

### T-1 公式（原需求 §3 / §5）

```
只用已经送入结构引擎的已收盘 H4。h = 刚处理完的一根；D = 处理 h 之后 ctx：BULLISH +1，BEARISH -1；RANGE / TRANSITION 不计算（T-5）
N = 12，K = 3，A = ATR14[h]（SeriesComputeATR 的 14 期简单平均 TR）

net    = D × (C[h] − C[h−12])
path   = Σ |C[i] − C[i−1]|，i = h−11 .. h
recent = D × (C[h] − C[h−3])

S_move = 100 × clamp(net / 3A, 0, 1)
S_eff  = 100 × clamp(max(net, 0) / path, 0, 1)        path = 0 且数据有效时 S_eff = 0
S_mom  = 100 × clamp(recent / A, 0, 1)
raw    = 0.45 S_move + 0.35 S_eff + 0.20 S_mom         0 .. 100，保留小数，分项不先取整
score  = raw 四舍五入（.5 进位）—— 只用于显示
tier   = 按未取整的 raw：[0, 35) 弱 WEAK，[35, 65) 中等 MED，[65, 100] 强 STRONG；0 分属于弱
```

**净推进 ≤ 0 不把总分置零**：此时 S_move、S_eff 为 0，S_mom 仍可有效（验收方对照 3：净推进 0、近 3 根同向 +1 ATR → 20 分，弱）。

**精确运算。** 价格先换成整数 point（`round(差 / _Point)`），T = Σ TR（14 根，= 14A）。设
`m = min(max(14·net, 0), 3T)`，`e = min(max(net, 0), path)`，`q = min(max(14·recent, 0), T)`，则

```
raw = (45·m·1 + 20·q·3)·path + 35·e·T·3·1   /   (T·path·3·1)          path > 0
raw = (45·m·1 + 20·q·3)                       /   (T·3·1)               path = 0（此时 m = q = 0）
score = floor((2·num + den) / (2·den))；tier：num < 35·den 弱，num < 65·den 中等，否则强
```

全部是 64 位整数运算：MQL、离线模型、验收工具三处逐位一致，35 / 65 和 .5 的边界不受浮点影响。分项 S_move / S_eff / S_mom 与 raw
以 6 位小数记入日志（显示与复核用），score / tier 由整数式决定。

### T-2 方向依赖

```
同一组价格，Context 方向相反 → 结果不同（推进、效率、动量都按 D 定向，反向为 0）
镜像对称            价格水平镜像 + BULLISH ↔ BEARISH → 每根 raw 相同（场景全部双向；EURUSD 1292 根 0 差异）
方向来源            处理 h 之后的 Context；TRANSITION 的 pending 方向不用
与趋势段无关        窗口不限当前趋势段、不因新趋势缩短（原需求 §5.4 末段）；不读 BOS 计数、保护点、锚点
```

### T-3 取值范围与显示

```
raw 0 .. 100（小数），score 0 .. 100（整数），tier 弱 / 中等 / 强（按 raw）
面板（FULL）   趋势强度  中等 · 56/100   数据截至 2026.10.26 12:00 H4 收盘
               BOS 计数与 CLEAN / MESSY 仍在 H4 CONTEXT 行，改称「BOS 计数」「结构诊断」，不再叫 strength / quality（原需求 §1.4）
面板（COMPACT）第一行 BULLISH   BOS 3 CLEAN   |   POI 0   |   SESSION 11:55（与 v2.55 相同，str 改称 BOS）
               第二行 强度 中等 56/100   数据截至 2026.10.26 12:00 H4 收盘（等待数据时只有「强度 等待数据」）
               （r2：验收方 P2，分数须能对上它的 H4；r4：MT5 文字标签最多显示 63 个字符，r2 把分数放在第一行后 Session 被截掉，
               改为分数与时间同在第二行；强度相关各行最长 54 个字符，strength_sim P08 检查）
其他状态       样本不足（H4 不足 15 根）/ 不可用（ATR 无效）/ 暂不评级（区间震荡 | 反转待确认）/ 等待数据 —— 都不显示数字
等待数据时     最后处理的一根是有效评分 → 「等待数据（上次有效结果 中等 · 56/100，<时间> H4 收盘）」；否则只写「等待数据」
```

面板文字由源码中的 `\uXXXX` 编码生成（源文件保持 ASCII，不依赖文件编码）。变化箭头属于 v2.58 面板；本版逐根保存
状态、分数、等级与当时的趋势段号（`g_str[]`，段号不写日志），v2.58 直接读取，不另算一套。

### T-4 阈值

3 ATR、1 ATR、45 / 35 / 20、35 / 65 为首版默认定义（原需求 §10），编译常量，不新增输入（交易参数摘要仍为 461F006E）。
每行 HMI-STR 带 `def=STR1-N12K3-M3R1-W45.35.20-T35.65`：任何常量改变都改变 def；两次构建 def 不同时，STR 判为不可比较
（不是重绘），其他类别照常比较。

分布只作记录：`ReloadTest -Str` 合并各图最新构建的 HMI-STR-HIST，给出分位、0 / 100 的个数与三档占比。不为三档均分自动改公式，
不以满分占比作验收硬指标；阈值修订须单独说明对照结果，不在实现里顺手改。离线 EURUSD 记录见 `docs/evidence/v2.56_strength_offline.txt`。

### T-5 数据不足、等待、无方向

```
NODATA / HISTORY   h < 14：从序列起点到 h 不足 15 根已收盘 H4（ATR14 的 TR 需要前一根收盘）  → 样本不足
NODATA / ATR       T = 0（15 根完全无波动）                                                    → 不可用（ATR 无效）
WAIT（面板状态）   序列未同步：本 tick 的 H4 或 M5 SeriesAppend 返回 NOT_READY，或尚无完成的构建；或返回 RELOAD
                   （历史被改动，下一 tick 经 TryBuild 重建 —— v2.56r2，验收方 P2：当下即显示等待，不留旧构建的分数）→ 等待数据
                   日志：进入等待时一行 HMI-STR-WAIT（src=H4 | M5 | BUILD | RELOAD，last=最后处理的 H4 收盘），只在实时出现，不比较
NODIR              数据有效，ctx = RANGE / TRANSITION                                          → 暂不评级（区间 / 过渡）
```

不补 0 或 50，不缩短窗口，不把旧值当当前值：等待时只按「上次有效结果 + 时间」显示，RANGE / TRANSITION 不显示上一方向的分数。

### T-6 时序与边界

```
同根顺序      H4ProcessBar(h)：摆动 → 流动性 → Context（超时 / 保护点 / BOS / TRANS，HMI-CTX / PROT 行）→ 区间 → H4 FVG / POI
              → 计算并记 HMI-STR（最后一步，只读）
CHOCH 当根    处理后 TRANSITION → 当根 NODIR；前一根照常有分
TRANS_OK / FAIL 当根  处理后为新方向 → 当根按新方向计分，窗口照常含过渡期间的根
构建与实时    同一函数（Rule 51）；实时在 H4 根收盘后、第一次处理到它时计算；面板只随已处理的 H4 变化
同一游标      评分、Context、ATR 与「数据截至」都取自同一根已处理 H4（g_str[g_h4_cursor − 1]）
窗口          只读 h−14 .. h：h−14 只用收盘（TR[h−13]）；h−12 是净推进起点与 path 第一步；h−3 是动量起点
```

### T-7 成对场景（`python3 tools/strength_sim.py` → 81/81；每个场景多空各一次，空头 = 价格镜像 + BEARISH）

T = 7000 point（ATR 500）除注明外；括号内为 S_move / S_eff / S_mom。

| 编号 | 场景 | net / path / recent | 期望 |
|---|---|---|---|
| V01 | 验收方对照 1：连续推进 | 1400 / 1400 / +350 | 91 强（93.33 / 100 / 70） |
| V02 | 验收方对照 2：同净推进同 ATR，近期回撤 | 1400 / 3400 / −1000 | 56 中等（93.33 / 41.18 / 0），raw 56.41 |
| V03 | 验收方对照 3：净推进 0，近期恢复 | 0 / 1000 / +500 | 20 弱（0 / 0 / 100） |
| I01 | 只加往返：path 1500 → 2700 | 900 / 1500→2700 / 300 | 60 → 51，只有 S_eff 变（60 → 33.33） |
| I02 | 只减近期：recent 300 → 100 | 900 / 1500 / 300→100 | 60 → 52，只有 S_mom 变（60 → 20） |
| I03 | 只把 ATR 加倍（T 14000） | 900 / 1500 / 300 | 41（raw 40.5，.5 进位），S_move / S_mom 减半，S_eff 不变 |
| C01 | 恰 3 ATR / 超过 3 ATR | 1500 / 1500 / 375；2400 / 2400 / 600 | 95；100（封顶） |
| C02 | 近期恰 1 ATR | 600 / 1000 / 500 | 59（S_mom 100） |
| C03 | 净推进 −300、近期 +500 | −300 / 1300 / +500 | 20 弱（总分不因 net ≤ 0 归零） |
| C04 | 全部逆向 | −900 / 900 / −300 | 0 弱 |
| B01 / B02 | raw 34.5 / 34.96 | 500 / 1000 / 50；500 / 1250 / 149 | 显示 35，等级弱 |
| B03 | raw 恰 35 | 500 / 1250 / 150 | 35 中等 |
| B04 / B05 / B06 | raw 64.46 / 64.5 / 64.96 | 1000 / 2000 / 424；1000 / 2000 / 425；1000 / 1750 / 374 | 64 中等；65 中等；65 中等 |
| B07 | raw 恰 65 | 1000 / 1750 / 375 | 65 强 |
| D01 | h = 13（14 根） | | NODATA / HISTORY |
| D02 | 15 根完全相同（T = 0） | | NODATA / ATR（不是 0 分） |
| D03 | 收盘全相同、K 线有波幅（path = 0，T > 0） | 0 / 0 / 0 | 0 弱（数据有效，S_eff = 0） |
| X01 | 同一组上涨价格在 BEARISH 下 | | 0 弱 |
| X02 | RANGE / TRANSITION | | NODIR，chg12 / chg3 / path / T 照记 |
| W01–W06 | 窗口：h−15 之前不读；h−14 只读收盘；之后的根不改变 h；C[h−3] 只改 recent 与 path；C[h−12] 改 net 与 path | | 见模型输出 |
| E01–E05 | Context 引擎：CHOCH 当根 NODIR；TRANS_OK / FAIL 当根按新方向；趋势中每根有分；与更早历史无关；计分不改变任何状态 | | |
| P01–P08 | 面板文字：有分 / 等待（上一根有分、尚无任何根、上一根为区间）/ 样本不足 / ATR 无效 / 区间、过渡；COMPACT 第二行；各行 ≤ 63 字符 | | 与 MQL 同一措辞 |

真实数据（`--replay`，EURUSD 1292 根）：前缀一致；镜像数据每根 Context 镜像、raw 相同，0 差异；分布只作记录。

### T-8 与现有输出的关系

```
不变        全部现有日志行（MODEL、HMI-CTX / PROT / ANCHOR / INTERNAL / DEDUP / POI / SESS / BLK / ARM / REF / BRK / LIQ …）
            逐字相同；任何标记、POI、Session、周期、MODEL 不读评分（Rule 69）；输入不变（461F006E）
新增        HMI-STR、HMI-STR-HIST、HMI-STR-WAIT 三种日志行；面板一行（FULL）/ 一段（COMPACT）；H4 CONTEXT 行的两个字样
跨版本      v2.55 → v2.56 同窗口：去掉 HMI-STR / HMI-STR-HIST 与身份字段（inst / run / init）后逐行相同；其他任何差异 UNEXPLAINED，
            不因「只加显示」豁免（ReloadTest -Versus 加法模式）
```

### T-9 日志与验收工具

```
HMI-STR,<sym>,live=<0|1>,bar=<H4 收盘时间>,ctx=<BULLISH|BEARISH|RANGE|TRANSITION>,state=OK|NODIR|NODATA,reason=-|HISTORY|ATR,
        def=<定义标识>,dir=<1|-1|0>,chg12=,chg3=,path=,tr_sum=<point|NA>,net=,recent=<point|NA>,
        s_move=,s_eff=,s_mom=,raw=<6 位小数|NA>,score=<0..100|NA>,tier=<WEAK|MED|STRONG|NA>,inst=,run=,init=
        构建：H4 收盘时间晚于 M5 窗口第一根开盘的各根（约 100 根，与标记同一区间）；实时：每根 H4 一行
        chg12 / chg3 为向上为正的原始收盘差；net / recent 为 D 定向后的值
HMI-STR-HIST,<sym>,live=0,def=,from=,to=<已处理 H4 窗口首末根收盘>,bars=,ok=,nodir=,nodata=,weak=,med=,strong=,h=<101 个计数>,inst=,run=,init=
        每次构建一行，在 HMI-BUILD-END 之前；统计整个已处理 H4 窗口（不含尚未送入结构引擎的根）
HMI-STR-WAIT,<sym>,live=1,state=NODATA,reason=WAIT,src=H4|M5|BUILD|RELOAD,last=<最后处理的 H4 收盘|->,inst=,run=,init=
```

`ReloadTest.ps1`：

- **STR 判定类别**：同窗口重载、实时 vs 重建（按 H4 收盘时间，与 HMI-CTX 相同的区间）都要求逐行全字段相同。
- **逐行复算**：按行内 `def=` 解析出的常量，用十进制精确运算，从 chg12 / chg3 / path / tr_sum 复算 net、recent、
  三个分项、raw、score 与 tier。分数或等级不符、分项小数差超过 1e-6，都判为失败。还核对状态与 ctx、reason、NA 字段的一致性，
  以及 path ≥ |chg12|、|chg3|。
- **处理窗口**（v2.56r2，验收方 P2）：构建内每行 HMI-STR 须满足 `From < bar ≤ To`（BEGIN 的 M5 开盘时间，按 H4VisibleTo，
  不另加 5 分钟）；HMI-STR-HIST 的 to 不得晚于 To（from 可以早于 From：直方图统计整个已处理 H4 窗口）。
- **直方图核对**：ok + nodir + nodata = bars；101 个分箱之和 = ok；weak + med + strong = ok；各状态、各等级、各分值的行数
  不超过直方图计数；最后一行 HMI-STR 的 bar = 直方图的 to；同一根 H4 不得有两行。
- **def 不同**：两次构建 def 不同，STR 判为 NOT COMPARABLE（pending）。def 无法解析，判为失败。
- **`-Versus` v2.55 → v2.56 加法模式**：见 T-8。身份字段之外，HMI-LIQ-REPLAY 的 `attempt=`（实例自 OnInit 起的流动性历史探测次数，
  只在 OnInit 清零，A-50）也是实例元数据：只有去掉它后两边相同的行才归此类，单独列出，不算差异（v2.56r3 工具，MT5 2026-10-26）。窗口不同为 NOT JUDGED；新版构建缺 HMI-STR-HIST（未写强度行）判为失败。
- **`-Str`**：分布记录。

`live_coverage.py --ver 2.56` 计 STR 类别，HIST 与 WAIT 行不比较。

工具 r5（MT5 运行 10-26 / 10-27 发现，与 v2.56 规则无关，v2.55 同样受益）：日内 PROT 行只差 `leg=`（重建在 H4 收盘后
窗口起点后移一根，A-59）在 live_coverage.py 中与 ReloadTest 一样记为 PENDING REVIEW，不算差异；ReloadTest -LiveVsBuild
两次构建分处两个日志文件（夜间，可能休眠而进程不变）时整对 pending（A-60），日志按 MT5 的日期文件名排序（复制、解压后写入时间不可靠）。

**不在本版：** 质量评分（v2.57：Q_break、回撤健康度、K 线重叠）、阶段与原因（§7 / §8）、变化箭头与完整趋势面板（v2.58）、图形调整；
H4 结构、保护点、BRI-08、Session、MODEL 规则不动。

---

## BRI-14 —— v2.57 质量评分（定义稿已确认 2026-10-27，C-1 至 C-10 见 Q-11 之后的确认记录；实现见 Q-12）

来源：《HMI 趋势面板改造需求（工程师版）》（docs/requirements/）§6 / §10 / §11；《HMI v2.36 规则决策补充（工程师版）》§6.1、§4.2
（本文件「裁决记录」节）；BRI-12 P-3（leg_anchor）；验收方「HMI v2.56r4 验收结论与下一步」（2026-10-27）。

本稿只定义只读展示与诊断：不调整结构方向、保护点、BRI-08、POI、Session、MODEL 规则；强度公式与 35 / 65 不变（STR def 不变）。
离线模型 `tools/quality_sim.py`（多空镜像场景 127/127，EURUSD 回放 2/2）。MQL 在本稿确认后实现。下文「建议」处是本稿的选择，
标「C-n」的是请验收方确认的点（汇总见 Q-11）。

### Q-1 公式总览

```
只用已经送入结构引擎的已收盘 H4。h = 刚处理完的一根；D = 处理 h 之后 ctx：BULLISH +1，BEARISH -1；RANGE / TRANSITION 不计算
价格全部换成整数 point；整数运算（重叠分项按 10⁻⁶ 定点，Q-4）

Q_break    当前趋势段、最近 60 根内、最近最多 5 个已完成观察的同向突破事件：100 × 成功数 / 事件数（事件数 < 3 → 无此项）
Q_retrace  leg_anchor 起算：leg = D × (ext − anchor)，x = D × (ext − C[h]) 限制在 0 .. leg
           3x ≤ leg：100；3x ≤ 2·leg：(160·leg − 180·x) / leg；否则 120·(leg − x) / leg       （r = x / leg：1/3 → 100，2/3 → 40，1 → 0）
Q_overlap  最近 12 根的 11 对相邻 K 线：o = floor(10⁶ · I / U)，U = 0 时 o = 10⁶；Q_overlap = 100 × (11·10⁶ − Σo) / (11·10⁶)
raw        0.40 Q_break + 0.35 Q_retrace + 0.25 Q_overlap        三项都有效才有总分；分项不先取整
score      raw 四舍五入（.5 进位），只用于显示
tier       按未取整的 raw：[0, 40) 较差 POOR，[40, 70) 一般 FAIR，[70, 100] 良好 GOOD
```

**整数式。** 设成功数 s、事件数 n（3..5）、回撤分子 num_r（上面三段的分子）、Σo = So，则

```
den = 1320000 · leg                                     1320000 = lcm(60, 20, 440000)
num = 40 · s · (1320000 / n) · leg + 7 · num_r · 66000 + 3 · (11·10⁶ − So) · leg
raw = num / den；score = floor((2·num + den) / (2·den))；tier：num < 40·den 较差，num < 70·den 一般，否则良好
```

leg ≤ 10¹⁰ point 时 2·num + den < 2⁶³（MQL long 精确）；超过此值（任何现实品种都达不到）按 PARTIAL / SCALE 处理，不溢出。
模型对每一个有总分的根断言整数式 = 0.40 / 0.35 / 0.25 的有理数合成（场景与 1292 根回放全部成立）。

### Q-2 突破可靠性 Q_break（原需求 §6.1 + 规则决策补充 §6.1）

```
事件         当前趋势段内、与段方向相同的每一次有效突破（结构引擎 HMI-CTX 行）：
             开段那一次（RANGE → BOS、TRANS_OK、TRANS_FAIL）记 START，段内延续 BOS 记 BOS              （建议，C-1：S1）
             TRANS_SAMELEG、CHOCH、INTERNAL 不是事件
冻结参考价   该次突破的主参考摆动点价格（HMI-CTX swing_px）；同根一并处理的旧点（A-33 also）不另算事件           （C-2）
观察         事件 K 线 k 之后的 3 根已收盘 H4：k+1、k+2、k+3
失败         任一根收盘回到参考价另一侧：D × (C − 参考价) < 0（整数 point 严格比较，不加突破余量；等于参考价不算失败）（C-3）
成熟         h ≥ k+3 才有结果（OK / FAIL）；之前为待确认 PEND，不进分母。
             提前看到的失败（k+1 已收回）也要到 k+3 才计入（原需求「为保持样本年龄一致」；回放不提前知道结果）    （C-4）
统计范围     当前趋势段 ∩ 最近 60 根（k ≥ h − 59）；其中最近（k 最大）的至多 5 个成熟事件
最少         n ≥ 3 才有 Q_break 与总分；n = 3 / 4 显示「低样本」，n = 5 显示「5 次事件」，都不宣称统计置信
n = 0 / 1 / 2  「样本不足（成熟突破 n/3，待确认 m）」+ 局部表现（显示见 Q-5）；不补 50、不补满分、不重新归一化权重
```

**BOS 稀疏与窗口解耦。** 价格类分项（强度三项、重叠）仍用最近 12 根；只有事件窗口放宽到 60 根：

- 最大回看：60 根已处理 H4（按 K 线计，周末缺口不占根数；约两周交易日）。模型 EURUSD：有总分的根里，最老被采用事件的年龄中位 41 根、最大 59 根。
- 跨段：不跨。新趋势段不继承旧段任何事件，TRANSITION 之后重新确立方向（TRANS_OK，以及方向相同的 TRANS_FAIL）、RANGE 之后的 BOS
  都是新段；CHOCH 当根即 NODIR，旧段事件全部丢弃（场景 E03–E05）。段的边界与 BRI-12 的 HMI-PROT / HMI-ANCHOR 段号同一来源。
- 不读 BOS 计数（g_ctx_strength）、不读保护点年龄（规则决策补充 §4.2：点位旧不作为近期质量好的证据）。

稀疏程度（EURUSD H4 1292 根，959 根趋势 K 线；只作记录，`--replay`）：

| 事件规则 | Q_break 可用的趋势 K 线 |
|---|---|
| 原文 12 根窗口（不含开段突破） | 29（3.0%） |
| 原文 12 根窗口（含开段突破） | 32（3.3%） |
| 当前段 + 60 根 + 最近 5 个（不含开段突破，S0） | 436（45.5%） |
| **当前段 + 60 根 + 最近 5 个（含开段突破，S1，建议）** | **561（58.5%）** |

S1 理由：开段突破本身就是一次有冻结参考价、方向与该段一致的有效突破（MQL 里同样返回 EV_BOS_UP / DOWN），观察它是否守住与观察段内 BOS
没有区别；不计入它会让每一段在第 4 个 BOS 之前都没有质量分。若验收方选 S0，只改事件筛选，def 标为 S0（模型 `leg_start=False` 已覆盖，E10）。

### Q-3 回撤健康度 Q_retrace（原需求 §6.2 + 规则决策补充 §4.2）

```
起点         leg_anchor（BRI-12 P-3），不是 protected_level；两字段不合并，Q_retrace 不读 protected_level
             （protected_level 只经 CHOCH → TRANSITION → NODIR 间接起作用）
锚点事件     SET / MOVE（每次 BOS 取同一个候选点，无单调约束）→ 换新起点，极值从新锚点重新算
             KEEP_NONE（本次 BOS 无候选）→ 保持旧锚点，极值继续累计
             单调保护点未推进（PROT KEEP_WORSE）而锚点 MOVE → 用移动后的锚点（场景 E06：锚点 1.10330、保护点仍 1.10350，
             分母 2020 而不是 2000）
             INVALID（开段无合法点）→ PARTIAL / ANCHOR，直到某次 BOS 取得候选（SET）
             RESET（CHOCH）→ 段结束，NODIR
             趋势切换（TRANS_OK / TRANS_FAIL）→ 新段自己的 SET 或 INVALID，不沿用旧段锚点
极值 ext     锚点 K 线 a 之后（a+1 .. h，含当前根）多头取最高价 H、空头取最低价 L（含影线）；锚点那根自己的高（低）点不算 ——
             同一根 K 线里高点可能出现在低点之前，无法判断先后                                                    （C-6）
             仅影线创新高、收盘回落：ext 取影线，x > 0（场景 R03）
分母         leg = D × (ext − anchor)；leg ≤ 0 → PARTIAL / LEG（不当作 0 分或满分）
x            D × (ext − C[h])，限制在 0 .. leg：收盘越过锚点但未构成 CHOCH（锚点 ≤ 保护点，多头；余量内）→ x = leg → 0 分（E06 第 19 根）
评分         分段线性（连续，无跳变）：r ≤ 1/3 → 100；1/3 .. 2/3 → 100 → 40；2/3 .. 1 → 40 → 0（R01：r = 101/300 → 99.4）
```

多头 BULLISH 锚点 ≤ 保护点（保护点是段内候选点的最高者，锚点是最近的一个），所以「收盘低于锚点」只有两种结果：越过保护点超过余量 →
当根 CHOCH、NODIR；否则 Q_retrace 0。空头对称。

### Q-4 K 线重叠 Q_overlap（原需求 §6.3）

```
窗口         最近 12 根（h−11 .. h）的 11 对相邻 K 线 (i−1, i)，i = h−10 .. h；不限当前趋势段（价格类分项）
每对         I = max(0, min(H[i], H[i−1]) − max(L[i], L[i−1]))，U = max(H[i], H[i−1]) − min(L[i], L[i−1])（整数 point）
定点         o = floor(10⁶ · I / U)；U = 0（两根同价零波幅）→ o = 10⁶（完全重叠，原文）                        （C-5）
零波幅       零波幅 K 线落在前一根区间之内：I = 0 → o = 0（原公式字面结果：「无重叠」）。EURUSD 1292 根 H4 中零波幅 0 根；
             若验收方认为应视为重叠，属公式修订，另行确认（场景 O05 记录字面结果）                                   （C-5）
缺失行情     序列里只有真实 K 线；周末等缺口两侧的 K 线就是相邻对，不补零波幅 K 线
NODATA       h < 11（不足 12 根已收盘 H4）→ 质量 NODATA / HISTORY（只在序列最开头出现）
```

定点理由：11 个不同分母的平均值在 MQL 的 64 位整数里无法精确通分；规定每对按 10⁻⁶ 向下取整后，MQL、模型、验收工具三处逐位一致，
40 / 70 与 .5 边界不受浮点（含编译器 FMA）影响。误差 ≤ 10⁻⁴ 分（O06：每对 1/3 → 66.666700，而非 66.666667）。

### Q-5 状态与显示

```
OK        趋势中，三项都有效                         趋势质量  良好 · 95/100（低样本 3 次突破）  |  趋势质量  良好 · 95/100（5 次事件）
PARTIAL   趋势中，总分不可用，reason：FEW（成熟事件 < 3）/ ANCHOR（无锚点）/ LEG（leg ≤ 0）/ SCALE，可用 + 连接
          FEW…     趋势质量  样本不足（成熟突破 2/3，待确认 1）  局部表现 回撤 100 · 重叠 78
          FEW+ANCHOR 趋势质量  样本不足（成熟突破 1/3；无波段锚点）  局部表现 重叠 81
          ANCHOR   趋势质量  不可用（无波段锚点）  局部表现 突破 100 · 重叠 81
          局部表现只列有效分项（四舍五入整数），不合成、不评级
NODIR     RANGE / TRANSITION                         趋势质量  暂不评级（区间震荡 | 反转待确认）
NODATA    h < 11                                     趋势质量  样本不足（H4 不足 12 根）
WAIT      与强度同一等待状态（HMI-STR-WAIT）          最后处理的一根为 OK：趋势质量  等待数据（上次有效结果 良好 · 95/100，<时间> H4 收盘）
                                                      否则：趋势质量  等待数据
COMPACT   强度行之后新增一行（第一行 Context / POI / Session、第二行强度与「数据截至」不变，周期行顺延）：
          质量 良好 95/100   低样本 | 质量 良好 95/100   5 次事件 | 质量 样本不足 2/3   局部 回撤 100 重叠 78 |
          质量 不可用   局部 突破 100 重叠 81 | 质量 暂不评级 | 质量 样本不足 | 质量 等待数据
长度      所有质量行 ≤ 54 个字符（OBJ_LABEL 63；P08）
```

「数据截至」只在强度行写一次：质量与强度取自同一根已处理 H4（g_h4_cursor − 1）。等级颜色、阶段、原因、箭头不在本版（v2.58）。

### Q-6 时序与边界

```
同根顺序      H4ProcessBar(h)：摆动 → 流动性 → Context（超时 / 保护点 / BOS / TRANS，HMI-CTX / PROT / ANCHOR 行）→ 区间 → H4 FVG / POI
              → 强度 HMI-STR → 质量 HMI-QLT（最后一步，只读）
BOS 当根      事件加入（PEND）；锚点已按本根更新（ProtOnBos 在 Context 内），回撤用更新后的锚点
CHOCH 当根    NODIR；前一根照常（E03：第 21 根 PARTIAL，第 22 根 NODIR）
TRANS_OK / FAIL 当根  新段：事件只有本根的 START（PEND），锚点为新段 SET / INVALID（E04 / E05）
构建与实时    同一函数；实时在 H4 收盘后第一次处理到它时计算；构建记录与强度同一区间（收盘晚于第一根 M5 开盘）
窗口          读 C[k+1 .. k+3]（各事件）、H / L[a+1 .. h]（锚点之后）、H / L[h−11 .. h]；不读 h 之后（E08：446 根逐根截断一致）
只读          结构、保护点、锚点、POI、Session、MODEL 都不读质量（E09：CTX / PROT / ANCHOR / INTERNAL 行有无质量逐行相同）
```

### Q-7 成对场景（`python3 tools/quality_sim.py` → 127/127；每个场景多空各一次，空头 = 价格镜像 + BEARISH，逐根全字段一致）

| 编号 | 场景 | 期望 |
|---|---|---|
| B01 | 3 个成熟成功 + 1 个 1 根前的事件 | n 3（待确认不计）→ 100，低样本 |
| B02 | 一根收盘低于参考价 1 point（不加余量） | 失败：2/3 = 66.666667 |
| B03 | 收盘恰等于参考价 | 不算失败 |
| B04 | k+1 已失败 | h = k+1、k+2 仍 PEND，k+3 才计 FAIL |
| B05 | 成熟 0 / 1 / 2 个 | PARTIAL / FEW：无 Q_break、无总分（不是 0 / 50 / 100） |
| B06 | 6 个成熟，最老的失败 | 取最近 5 个 → 100、5 次事件；含失败的 5 个 → 80 |
| B07 | 事件在 h−59 / h−60 | 前者计入，后者不计（→ FEW） |
| R01 | leg 300，x = 0 / 100 / 101 / 150 / 200 / 250 / 300 / 330 | 100 / 100 / 99.4 / 70 / 40 / 20 / 0 / 0（限制） |
| R02 / R03 | 锚点根自身高点 500；仅影线新高 350 | 不作极值；ext 取影线 |
| R04 / R05 / R06 | 无锚点；leg = 0；FEW 且无锚点 | ANCHOR（突破、重叠照显示）；LEG；FEW+ANCHOR |
| O01–O04 | 跳空无重叠；完全相同；I/U = 1/2；同价零波幅 | 100；0；50；0（U = 0 → 1，数据有效） |
| O05 | 零波幅 K 线在前一根区间内 | 字面结果 overlap 0 → 100（C-5） |
| O06 / O07 | 每对 1/3；h−12 那根远离 | 66.666700（定点）；不影响 |
| C01 / C02 | 精确 70；精确 69.5 | 70 良好；显示 70、等级一般 |
| C03 / C04 | 精确 40；精确 39.5 | 40 一般；显示 40、等级较差 |
| C05 | 三个事件中一个失败 | 只有 Q_break 变（100 → 66.67），raw 降 40/3 |
| D01 / X01 / X02 | 11 根；RANGE / TRANSITION；同一组上涨价格在 BEARISH 下 | NODATA；NODIR；事件全部失败 |
| E01 | 阶梯上涨（引擎） | START 14 + BOS 23 / 31 / 40 / 49 / 58 / 67；第 34 根第 3 个成熟 → 总分（低样本）；第 52 根 5 次事件；第 61 根最老的移出 |
| E02 | 每次突破 1–10 point 收回（引擎） | 第 30 根 n 3、成功 0 → Q_break 0（有效样本，不是 FEW） |
| E03 / E04 | 保护低点被破 → TRANS_OK（引擎） | CHOCH 当根 NODIR；新段只有自己的 START；连续三根突破 → 待确认 3 |
| E05 | TRANS_FAIL 同方向恢复（引擎） | 新段不继承旧段的成熟成功 |
| E06 | 保护点 KEEP_WORSE、锚点 MOVE（引擎） | 回撤按锚点；余量内越过锚点 → 0 分不 CHOCH |
| E07 | 开段 INVALID（引擎） | FEW+ANCHOR，取得候选后回撤才出现 |
| E08 / E09 | 逐根截断；只读 | 一致；结构行不变 |
| E10 | 同一阶梯按 S0 | 第 3 个成熟事件推迟到第 43 根 |
| **E11** | **强度强但质量差**（E02 的第 40 根） | **强度 75 强；质量 39.24 较差（突破 0/4 守住、重叠 36.0、回撤 86.4）** |
| **E12** | **强度一般但质量好**（E01 的第 36 根，正常回撤第三根） | **强度 45 中等；质量 93.03 良好（3/3 守住、r = 0.295、重叠 72）** |
| P01–P08 | 面板文字 | 见 Q-5；与 MQL 同一措辞；≤ 63 字符 |

### Q-8 与现有输出的关系

```
不变        全部现有日志行（MODEL、HMI-CTX / PROT / ANCHOR / INTERNAL / DEDUP / POI / SESS / BLK / ARM / REF / BRK / LIQ / STR …）逐字相同；
            任何标记、POI、Session、周期、MODEL 不读质量（Rule 69）；输入不变（交易参数摘要仍 461F006E；常量进 def）
新增        HMI-QLT、HMI-QLT-HIST；FULL 一行、COMPACT 第三行
跨版本      v2.56 → v2.57 同窗口：去掉 HMI-QLT / HMI-QLT-HIST 与身份字段后逐行相同（含 HMI-STR）；其他差异 UNEXPLAINED（-Versus 加法模式）
```

### Q-9 日志与验收工具（实现时）

```
HMI-QLT,<sym>,live=<0|1>,bar=<H4 收盘>,ctx=,state=OK|PARTIAL|NODIR|NODATA,reason=-|HISTORY|FEW|ANCHOR|LEG|SCALE（可用 + 连接）,
        def=QLT1-B60.5.3.3S1-RA-O12F6-W40.35.25-T40.70,dir=<1|-1|0>,
        ev=<事件;事件…|->,b_n=,b_ok=,b_fail=,b_pend=,q_break=<6 位小数|NA>,
        anchor=<价格|NA>,anchor_bar=<锚点 K 线开盘时间|->,ext=<价格|NA>,close=<价格>,leg_pts=<整数|NA>,retr_pts=<x|NA>,q_retrace=<6 位|NA>,
        ov=<I/U;… 11 对|NA>,ov_sum=<Σo|NA>,q_overlap=<6 位|NA>,raw=<6 位|NA>,score=<0..100|NA>,tier=POOR|FAIR|GOOD|NA,
        sample=LOW|FIVE|FEW|-,inst=,run=,init=
        事件 = <事件 H4 收盘时间>@<参考价>/<START|BOS>/<OK|FAIL|PEND>/<已观察收盘 c1|c2|c3 或 ->；列出待确认事件与被采用的成熟事件
        构建：与 HMI-STR 同一区间；实时：每根 H4 一行。不写段号（段号随窗口起点变化，A-59）
HMI-QLT-HIST,<sym>,live=0,def=,from=,to=,bars=,ok=,partial=,nodir=,nodata=,poor=,fair=,good=,few=,anchor=,legbad=,
        n=<趋势 K 线中 n = 0..5 的根数>,h=<101 个计数>,inst=,run=,init=        每次构建一行，在 HMI-BUILD-END 之前
等待      不另设行：与强度共用 HMI-STR-WAIT
```

`ReloadTest.ps1`（实现时增加，沿用 STR 的做法）：

- **QLT 判定类别**：同窗口重载、实时 vs 重建逐行全字段相同；def 不同 → NOT COMPARABLE；处理窗口 From < bar ≤ To。
- **逐行复算**（十进制精确）：每个事件按所列收盘与参考价重判 OK / FAIL / PEND（PEND ⇔ 少于 3 个收盘）、计数与 q_break；
  leg_pts / retr_pts 与价格一致（按价格小数位换算 point）、q_retrace 分段式；11 对 I/U → o、Σo、q_overlap；整数式 raw / score / tier；
  state / reason / NA 字段一致。
- **对照结构行**：每个事件须对应同一构建内一行 HMI-CTX（同根、BOS / TRANS_OK / TRANS_FAIL、方向 = 段方向、swing_px = 参考价）；
  段内 60 根内未列出的突破只能比所列 5 个成熟事件更老；anchor / anchor_bar = 本段最近一行 HMI-ANCHOR SET / MOVE；
  CHOCH 之后、新段之前不得出现 OK / PARTIAL。
- **直方图核对**：同 STR-HIST（各状态、等级、分箱、n 分布与本构建的 HMI-QLT 行不矛盾）。
- **`-Versus` v2.56 → v2.57 加法模式**、**`-Qlt` 分布记录**；`live_coverage.py --ver 2.57` 计 QLT 类别。

### Q-10 真实数据记录（EURUSD H4 1292 根，`--replay`；只作记录，不据此改定义）

```
前缀（每 37 根截断重算）一致；价格镜像后逐根全字段一致（0 差异）
状态        OK 561，PARTIAL / FEW 273，PARTIAL / FEW+ANCHOR 125，NODIR 322，NODATA 11
n 分布      趋势 K 线 959：n=0 73、1 187、2 138、3 175、4 160、5 226；成熟事件（去重）成功 58、失败 31
分项        Q_break P10 60 / P50 80 / P90 100；Q_retrace P10 40.9 / P50 100；Q_overlap P10 50.2 / P50 57.4 / P90 65.9
raw         P10 58.4 / P25 68.9 / P50 79.2 / P90 90.2；良好 414、一般 146、较差 1（共 561）
强度 × 质量  弱/较差 1、弱/一般 128、弱/良好 183、中等/一般 12、中等/良好 106、强/一般 6、强/良好 125
```

分母与成因（验收方 2026-10-27 复核口径，取代定义稿的「观察」一段）：

- 全部 H4 1292 根；已确认趋势且达到历史门槛 959 根；三项都有效、出总分 561 根（趋势根的 58.5%）。
- **「良好 74%」是可评分根中的比例**（414 / 561 = 73.80%）；占全部 H4 为 32.04%，其余含不可评分状态，不能统称质量差。
  相邻 H4 常使用同一组突破事件，561 根不是 561 个独立突破样本；也不外推为所有品种 H4 的通常分布。
- 三个因素共同作用：突破分在有总分的根上均值 81.57（加权贡献 32.63）—— 只采用已成熟且仍属当前段的事件，新段样本少、区间或过渡时
  不出总分，分布偏向存续且样本足够的趋势；回撤分均值 84.59（贡献 29.61），561 根中 324 根为 100（回撤不超过 1/3 即满分）；
  重叠分均值 57.78（贡献 14.45）。合成均值 76.68。例：突破 60、回撤 100、重叠 57.4 → 0.40×60 + 0.35×100 + 0.25×57.4 = 73.35，良好 ——
  「良好」是这套定义下的综合结构表现，不要求每个分项都良好。
- 等级占比偏高不是计算错误，也不为三档均分调权重或阈值（C-10）；将来如校准阈值，另立后续版本并改 def，不混入本版。
- 3 个成熟事件时突破分只有 0 / 33.33 / 66.67 / 100 四档（总分中该项每档约 13.33 分）：至少 3 个解决了「一个事件决定 40 分」，
  但不等于质量分平滑；保留低样本提示，不另加平滑或贝叶斯修正。

### Q-11 请验收方确认

```
C-1  开段突破（RANGE BOS / TRANS_OK / TRANS_FAIL）计入 Q_break 事件（S1）                         建议：是（可用率 58.5% vs 45.5%）
C-2  冻结参考价 = 主参考摆动点价格；同根一并处理的旧点不另算事件                                   建议：是
C-3  失败 = 收盘严格越过参考价（整数 point），不加突破余量；等于不算                               建议：是（原文）
C-4  提前失败也满 3 根才计入                                                                     建议：是（原文）
C-5  重叠每对 10⁻⁶ 向下取整；零波幅 K 线在前一根区间内按原公式得 0                                建议：是
C-6  回撤：leg_anchor 起算；极值从锚点 K 线的下一根算到当前根（含影线）；leg ≤ 0 → 不可用         建议：是
C-7  60 根 / 最近 5 个 / 至少 3 个；不跨段；n = 0–2 显示「样本不足 + 局部表现」                    （规则决策补充 §6.1）
C-8  NODATA 门槛 h < 11；状态与面板措辞（Q-5）；COMPACT 新增一行                                    建议：是
C-9  日志格式（Q-9）与 def 标识                                                                  建议：是
C-10 分布偏「良好」（Q-10）是否需要在实现前另立修订                                              建议：先按原文实现，MT5 多品种分布记录后再议
```

**确认记录（验收方「HMI v2.57 质量评分定义稿审核结论」，2026-10-27；包 C1F7B3BA…F538）：** 定义稿可进入 MQL 实现。C-1 至 C-9 按本稿建议固定；
C-10 保持 40 / 35 / 25 与 40 / 70，先实现，多品种分布在运行验收期并行记录。验收方复核：127/127、--replay 2/2、独立算式 1292 根
（事件成熟与取样、状态、三项、总分、显示舍入、等级）0 差异、MQL 24/24 与 v2.56r4 相同、461F006E、leg ≤ 10¹⁰ 下合成表达式上界
2.6532×10¹⁸ < 2⁶³。通过的是定义与离线模型，不是 v2.57 指标的运行验收。

### Q-12 实现（v2.57 开发版，未编译）

```
HMI_QualityEngine.mqh（新）  QltOnH4Bar(h) 在 H4ProcessBar 最后、StrOnH4Bar 之后（构建与实时同一点，Rule 51）；只读
  事件来源      HMI_H4ContextEngine.mqh 在 Context 取得趋势方向突破的两处写 g_ctx_brk_h / g_ctx_brk_dir / g_ctx_brk_px
                （段内 BOS；RANGE BOS / TRANS_OK / TRANS_FAIL），即本根实际产生的事件及其主参考摆动点价格（消费前取值）；
                只写不读，除质量外无人读；ResetEngine 清零。TRANS_SAMELEG、CHOCH、INTERNAL 不写
  跟踪状态      g_qev[]：当前段、最近 60 根内的突破（K 线序号、是否开段、冻结价）；段号 g_leg_seq 改变或 ctx 非趋势即清空
  锚点          g_anchor（BRI-12）的价格与摆动 K 线序号；极值每根从 a+1 扫到 h（不留增量状态）；不读 g_prot
  运算          整数：QLT_LCD 1320000、QLT_C_RET 462000、QLT_C_OVL 3、leg 上限 10¹⁰；double 只用于日志的 6 位小数
  记录          g_qlt[]（每根已处理 H4）；HMI-QLT（与 HMI-STR 同一区间）；HMI-QLT-HIST（HMI-STR-HIST 之后、BUILD-END 之前）
  面板          FULL：强度行之后一行（未构建时同样显示「等待数据」）；COMPACT：强度行之后一行，周期行顺延；等待与强度共用 g_str_wait
不变           全部现有日志行（含 HMI-STR）、输入与参数摘要 461F006E；版本 2.57
```

编译前的逻辑核对（`tools/quality_mql_mirror.py`）：把 QltOnH4Bar / QltLog / QltPanelText / QltPanelShort 逐行转写为 Python，按 MQL 的
取数方式（本根的突破、段号、锚点）喂入同一结构模型，与 quality_sim 比较 —— 场景序列与 EURUSD 1292 根及其镜像：HMI-QLT 行 3030 行
逐字符 0 差异、面板文字 12120 条 0 差异；`\uXXXX` 词表 41 条解码与注释一致。它看不到 MQL 语法与编译器行为，不代替编译与运行。

工具：`ReloadTest.ps1` QLT 类别（同窗口重载、实时 vs 重建；def 不同 → NOT COMPARABLE）、逐行复算（事件结果按所列收盘重判、计数、
回撤与价格一致、11 对重叠、整数合成、状态与原因）、对照本构建结构行（事件 = 当前段的 HMI-CTX 突破且冻结价相同、START = 开段那次、
未列出的段内突破只能比所列成熟事件更老或在 60 根之外、所列收盘 = 该根质量行的 close、锚点 = 最近一行 HMI-ANCHOR、ctx = 最近一行 HMI-CTX、
锚点不变时极值不回退）、处理窗口、直方图；`-Versus` v2.56 → v2.57 加法模式（HMI-STR 也须逐行相同）；`-Qlt` 分布记录。
工具 r2（验收方「HMI v2.57 开发版代码复核」两处 P2）：同一构建的 HMI-STR 与 HMI-QLT 必须覆盖同一组 H4 收盘（缺行或多行都报），
两次构建都缺质量明细时不再给出 IDENTICAL；`-LiveVsBuild` 对每个参与比较的构建各做一次完整的 STR / QLT 构建检查（明细、结构、直方图），
构建侧有错时不给 AGREE BOTH WAYS（STR 的同一缺口一并补上）。
`live_coverage.py --ver 2.57` 计 QLT 类别。

**不在本版：** 阶段（§7）、原因（§8）、变化箭头、完整趋势面板与等级颜色、旧长行截断（v2.58）；结构、保护点、BRI-08、Session、MODEL 规则不动。


## BRI-15 —— v2.58 最终面板：阶段、原因、强度箭头、排版（只显示；实现记录）

来源：《HMI 趋势面板改造需求（工程师版）》（docs/requirements/）§2 面板、§5.4 变化箭头、§7 当前阶段、§8 主要原因；验收方「HMI v2.57 运行验收结论与
最终面板收尾要求」（2026-10-28）：直接实现，不再另开质量定义轮；阶段、原因只读取现有结构与分项，不改变信号链；附加箭头与图案美化若影响收尾放到
后续；对新增阶段 / 原因给出可核对依据。下文 G-1 … G-14 是原文没有写到、实现时必须定下的取法，逐条写明，验收时可改。

强度（BRI-13）、质量（BRI-14）的定义与日志不变；结构、保护点、BRI-08、POI、Session、MODEL 不动；参数摘要 461F006E 不变（新输入只是显示样式）。

### S-1 当前阶段（原需求 §7，按优先级取第一个成立的）

记号：bar h = 刚处理的 H4；D = +1 多头 / −1 空头；T = 强度记录的 14 根 TR 之和（ATR14 = T / 14，与强度同一 ATR）；x、L、ext = 质量记录的
回撤项（leg_anchor 起算，x 已限制在 0..L）；价格一律整数 point。

| 代码 | 条件 | 面板 |
|---|---|---|
| NODATA | 强度 NODATA / HISTORY（已收盘 H4 不足 15 根） | 样本不足 |
| NOATR | 强度 NODATA / ATR（14 根 TR 全为 0） | 不可用 |
| TRANS | TRANSITION | 反转待确认 |
| RANGE | RANGE | 区间震荡 |
| BUILD | 趋势，但没有合法保护点（P-6a INVALID 且之后未 SET），或回撤项不可用（质量 LEG / SCALE） | 结构待完善 |
| DEEP | 3x > 2L（r > 2/3） | 深度回撤 |
| PUSH | refresh 且 near | 延续推进 |
| CONSOL | near 且非 refresh | 高位整理（多）/ 低位整理（空） |
| PULLBACK | 其余 | 正常回撤 |

```
refresh   bar h 的最高价（多）/ 最低价（空）严格越过本段 a+1 .. h−1 的极值（a = leg_anchor 摆动 K 线）；a+1 .. h−1 无 K 线 → 非 refresh
near      dist = D·(ext − C[h])（不限幅，ext 含本根），56·dist ≤ T  ⇔  dist ≤ 0.25·ATR14
```

### S-2 主要原因（原需求 §8）：最多两条，先状态，再风险；状态与风险都没有时才列强项

```
状态   PROT_BROKEN   TRANSITION 由有效收盘越过保护点打开（P-4）         多头保护低点已破 / 空头保护高点已破
       SWING_BROKEN  TRANSITION 由 P-6b 回退规则打开（该段无保护点）      多头低点已破（无保护点）/ 空头高点已破（无保护点）
       TIMEOUT       由 TRANSITION 超时（InpH4TransitionMaxBars）进入的 RANGE    过渡超 18 根未确认（显示输入的实际值）
       NO_PROT       BUILD：缺少保护点                                    缺少保护点
       LEG           BUILD：回撤项不可用                                  波段长度无效
风险   DEEP          3x > 2L                                              回撤偏深
       BRK_FAIL      质量记录采用的成熟事件中有失败                        近期突破失败
       COUNTER       S_mom = 0 且 recent < 0                              近期逆向运行
       CHOP          path > 0 且 S_eff < 35（100e < 35·path）              价格往返明显
强项   MOVE          S_move ≥ 65（100m ≥ 195T）                           同向推进明显
       RET           Q_retrace ≥ 70（num_r ≥ 70L，即 r ≤ 1/2）              回撤较浅
       BRK           n ≥ 3 且全部守住                                     突破全部守住
       EFF           S_eff ≥ 65                                           推进效率高
       MOM           S_mom ≥ 65（100q ≥ 65T）                             近期推进有力
       OVL           Q_overlap ≥ 70                                       K 线重叠少
趋势中一条都没有 → 无突出分项；NODATA / NOATR / 初始 RANGE → —
```

### S-3 强度箭头（原需求 §5.4）

强度 OK 时：ref = h − 3；ref 也是强度 OK 且同一趋势段（g_leg_seq 相同）→ d = 当前显示分 − ref 显示分：d ≥ 5 ↑，d ≤ −5 ↓，否则 →；
其余（不足 3 根、ref 未评分、跨段）→ 新趋势。

### S-4 面板

```
趋势面板（新，默认右上角，原需求 §2）            诊断面板（原面板，默认左上角）
  H4 趋势    ▲ 多头 / ▼ 空头 / 过渡 · 偏多待确认 /    COMPACT  POI n | SESSION hh:mm / no session（| LIQ WAITING）
             区间震荡（绿 / 红 / 黄 / 灰）                       周期行
  趋势强度   强 · 76/100 ↑ / 新趋势 / 暂不评级 / ...             ADR / ATR
  趋势质量   良好 · 82/100（5 次事件）/ 局部表现 ... /     FULL     版本行；H4 CONTEXT + BOS 计数 + 结构诊断；强度分项；质量分项；
             暂不评级 / ...                                       H4 POI；SESSION；LIQ HISTORY；CYCLE；ADR / ATR
  当前阶段   延续推进 ...
  主要原因   同向推进明显，回撤较浅
  数据截至   2026.10.28 16:00 H4 收盘（服务器时间）
```

- 等待（序列未同步）：方向、阶段写「等待数据」，强度 / 质量写「等待数据（上次有效结果 强 · 69/100）」（上次是有效分时），时间行
  「上次有效结果 <时间> H4 收盘（服务器时间）」；未构建：全部「等待数据」。
- 两个面板都有背景框（默认图表背景色，细边框），按实测文字宽度排版；每次重画先删后建，背景先建，保证压在之后画出的线上。
- 诊断面板的长行（CYCLE、H4 POI、LIQ HISTORY 等）超过 63 字符时折到下一行（缩进），不再截断：先在「|」处断，其次两个空格，再次任一空格，
  断点至少保留一半宽度（`stage_sim.wrap` = `StgWrap`）。
- 新输入（只是样式，不进参数摘要）：InpTrendCorner（默认右上）、InpTrendX / Y、InpTrendFontSize（9）、InpTrendLabelColor、
  InpPanelCtxTransColor（金色）、InpPanelBgColor（clrNONE = 图表背景）、InpPanelBorderColor。

### S-5 日志

```
HMI-STG,<sym>,live=,bar=,ctx=,stage=,reasons=<R1+R2|->,def=STG1-NEAR25-DEEP2.3-EFF35-POS65.70-ARR3.5,dir=,pend=UP|DOWN|-,
        chk=BREAK|FALLBACK|TIMEOUT|INIT|-,prot=1|0|NA,anchor_bar=,prev_ext=,bar_ext=,ext=,close=,dist_pts=,tr_sum=,refresh=,near=,
        arrow=UP|DOWN|FLAT|NEW|NA,ref_bar=,ref_score=,score=,inst=,run=,init=
        —— 与 HMI-STR / HMI-QLT 同一组 H4（构建：M5 窗口内收盘的；实时：每根）；段号不写（A-59）
HMI-STG-HIST,<sym>,live=0,def=,from=,to=,bars=,nodata=,noatr=,trans=,range=,build=,deep=,push=,consol=,pullback=,
        rs=<15 个原因计数，按 S-2 顺序>,up=,down=,flat=,new=,...   —— 每次构建一行，HMI-QLT-HIST 之后
```

可核对：每行的阶段与原因只由本行与同一根的 HMI-STR / HMI-QLT 决定（复算见 S-8）；chk 对照本构建 CHOCH 当根的 HMI-PROT BREAK / FALLBACK
行、RANGE 对照 HMI-CTX TIMEOUT 行；箭头的 ref_score 对照 ref 那根的 HMI-STR，同段与否对照 HMI-CTX 开段突破（str=1）；prev_ext 对照前一根
同锚点的 ext。

### S-6 原文没有写到的取法（实现时定下；可改）

```
G-1  回撤比例 r 与极值都取质量记录（leg_anchor 起算，BRI-14 Q-3 / 规则决策补充 §4.2），不读 protected_level；
     「缺少合法保护点」= protected_level 无效（P-6a），BRI-12 中它与 leg_anchor 由同一候选同时设定，二者有效性总相同
G-2  「刷新此前本段趋势极值」：严格越过 a+1 .. h−1 的极值（等于不算）；锚点后第一根没有「此前」→ 不算刷新
G-3  0.25 ATR 用强度的 ATR14（T / 14，同一 SeriesComputeATR 口径），收盘到「本段极值（含本根）」的距离；整数式 56·dist ≤ T
G-4  趋势中回撤项不可用（LEG / SCALE，leg ≤ 0 或超范围）同样归「结构待完善」（§7 第 4 级），原因写「波段长度无效」
G-5  TRANSITION 的原因按它是怎样打开的：P-4（越过保护点）或 P-6b（无保护点时越过最近摆动点）；整个过渡期保持。
     RANGE 只有超时进入时给原因；历史开头尚无趋势的 RANGE 不给
G-6  「窗口内存在已完成观察的失败 BOS」的窗口 = 质量的事件窗口（BRI-14：当前段、60 根、最近 5 个成熟事件）
G-7  path = 0（12 根收盘全部相同）时 S_eff = 0 但不叫「价格往返明显」
G-8  「按高分分项说明」：强度分项达到「强」的分界 65、质量分项达到「良好」的分界 70 才算高分，不另设参数；顺序固定
     MOVE、RET、BRK、EFF、MOM、OVL（原文示例「同向推进明显，回撤较浅」在前）。部分守住必然有失败事件 → 已是风险原因，
     所以强项里的突破只有「突破全部守住」
G-9  趋势中没有任何原因 → 「无突出分项」（由状态生成，不是赞美文案）；非趋势、样本不足 → 「—」
G-10 箭头按两个显示分（整数）之差，和面板上的两个数字一致；等级仍按未取整分数。同段 = 同一 g_leg_seq
G-11 TRANSITION / RANGE 时强度、质量行只写「暂不评级」，原因在阶段行（不再三行重复「反转待确认」）
G-12 等待时时间行写「上次有效结果 <时间>」；强度 / 质量的上次有效分只在上次是 OK 时给出（同 v2.56 / v2.57）
G-13 趋势面板默认右上角（原文 §2），诊断面板保留左上角，两者都可改角落；COMPACT 与 FULL 共用同一个趋势面板
G-14 短色条（§2「可配」）与其他图案美化不做（验收方：影响收尾则后续）
```

### S-7 实现（v2.58 开发版，未编译）

```
HMI_StageEngine.mqh（新）   StgOnH4Bar(h) 在 H4ProcessBar 最后、QltOnH4Bar 之后（构建与实时同一点，Rule 51）；只读强度 / 质量记录、
                            g_ctx / g_ctx_pending / g_ctx_time / g_prot.valid、g_h4[]；自己保留两项：上一根结束时 g_prot.valid
                            （判断 CHOCH 是 P-4 还是 P-6b）与本次过渡的打开方式。运算全为整数；HMI-STG / HIST；面板六行、诊断分项行、折行
HMI_ObjectManager.mqh       面板改为两个背景框（OM_DrawBox：测宽、两列对齐、四个角落均可）；OM_DrawTrendPanel；诊断面板逐行折行
HMI_Style.mqh               新样式输入（S-4）；HMI_Defs.mqh / H4M5_Identification.mq5：版本 2.58，调用点，ResetEngine，StgLogHist
不变                        全部现有日志行（含 HMI-STR / HMI-QLT）、交易参数与摘要 461F006E；没有改任何引擎
```

### S-8 核对

```
tools/stage_sim.py                86/86：§7 每一级与优先级、§8 每条原因与上限两条、各阈值精确边界（2/3、56·dist = T、S_eff 35、65 / 70）、
                                  等于极值不算刷新、箭头 ±5 / ±4 / 跨段 / 无参考、§2 三个示例逐字、等待 / 未构建 / 样本不足、行宽、折行；多空镜像
  --replay EURUSD_H1.csv          4/4：前缀一致（无前视）、镜像逐根一致、面板各行 ≤ 63 字符、除 NOATR 外各阶段都出现
tools/stage_mql_mirror.py         PASS：MQL 逐行转写，场景序列 + EURUSD 1292 根及镜像：HMI-STG 3172 行、面板文字 12688 条、随机长行折行
                                  4000 条，与模型 0 差异。看不到 MQL 语法，不代替编译
ReloadTest.ps1                    STG 类别：同窗口重载、实时 vs 重建（def 不同 → NOT COMPARABLE）；逐行用同一根的 HMI-STR / HMI-QLT 复算
                                  （抄录字段、极值与 refresh / near、阶段、原因、箭头）；对照本构建结构行（过渡打开方式、RANGE 来源、箭头
                                  参考分与同段、前一根极值）；STR / QLT / STG 同一组 H4；直方图（与 STR-HIST 互相对账）；-Versus v2.57 → v2.58
                                  加法模式（HMI-STR / HMI-QLT 也须逐行相同）；-Stg 分布记录
tools/logtests                    228/228（新增 g01–g28）；live_coverage_tests 28/28（--ver 2.58 计 STG）
```

EURUSD H4 回放（1292 根，只作记录）：趋势 959 根中 正常回撤 69.1%、结构待完善 12.8%、深度回撤 8.8%、延续推进 7.3%、高 / 低位整理 1.8%；
原因出现次数 近期突破失败 540、近期逆向运行 348、价格往返明显 348、回撤较浅 118、同向推进明显 113；无突出分项 2；箭头 ↑ 328 ↓ 406 → 151 新趋势 72。
「近期突破失败」多，是因为质量窗口保留最近 5 个成熟事件、最远 60 根（G-6）；按原文与已确认的质量窗口实现，不在本版另改。

**不在本版：** 短色条与图案美化（G-14）；任何评分、结构与信号规则。之后：编译与布局截图 → 最终统一五个交易日运行验收。
