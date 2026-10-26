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

## 已执行的验证记录

### ✅ POI-01 / POI-02a（接受侧）—— PASS（2026-09-22，USDJPY H4，v2.11）

**被测对象：** `HMI_D61E_P4_2319_0`

```
对象锚点（对象列表读出）
  点1: 2026.09.14 16:00:00   价格 154.999
  点2: 2026.09.22 19:25:00   价格 154.269     （点2 时间 = redge，随时间右移）

H4 原始数据（数据窗口逐根读出）
  09.14 08:00   O 154.026  H 154.610  L 153.951  C 154.558   阳
  09.14 12:00   O 154.558  H 154.887  L 154.451  C 154.862   阳
  09.14 16:00   O 154.861  H 154.999  L 154.269  C 154.319   阴  <- OB
  09.14 20:00   O 154.318  H 154.425  L 153.984  C 154.333   阳
  09.15 00:00   O 154.338  H 154.668  L 154.211  C 154.667   阳
  09.15 04:00   O 154.665  H 154.892  L 154.614  C 154.738   阳  <- FVG 完成
```

**逐条核对**

| 规格条款 | 期望 | 实测 | 结果 |
|---------|------|------|------|
| Rule 5：POI = 完整 OB | 上边 = OB High | 154.999 == 154.999 | PASS |
| Rule 5：含影线非实体 | 下边 = OB Low | 154.269 == 154.269（实体为 154.861/154.319） | PASS |
| §4.2：OB 为反方向 K 线 | Bullish POI → 阴线 | C 154.319 < O 154.861 | PASS |
| §4.5：左边缘 = origin_time | = OB 的 time | 2026.09.14 16:00 | PASS |
| §4.3：同方向 FVG 存在 | low[i] > high[i-2] | 154.614 > 154.425 | PASS |
| §4.4 / Rule 6：连接合法 | gap = fvg_lo − ob_hi ≤ 0 | 154.425 − 154.999 = **−0.574**（Overlap） | PASS |
| CONF-14：OB 取离 FVG 最近的反方向 K 线 | 跳过 00:00 与 20:00（皆阳线），取 16:00 | 与实测一致 | PASS |

**结论：** 该 H4 POI 完全符合规格。FVG 下沿比 OB 高点低 57.4 pip，属深度 Overlap，
距离「正价格空隙」这条否决线很远。

> 说明：本条验证的是 **POI 的几何与 Rule 6 的接受侧**。
> 它**不**验证反未来函数与不重绘 —— 那需要 §3 的 Reload / Replay 比对；
> 也**不**验证 Rule 6 的**否决侧** —— 一个被正确接受的形态不能证明
> 「有正空隙时确实会被拒绝」，那是下面的 POI-02b。

---

### ⏳ POI-02b（否决侧）—— 待执行（v2.20 起可测）

**为什么需要单独测：**
POI-02a 证明的是「连接合法 → 建 POI」。Rule 6 的另一半是
「连接不合法 → **不**建 POI」。后者在图表上表现为**什么都没有**，
无法用观察证明 —— 可能是规则起作用了，也可能是那段行情根本没有候选 OB。
在 v2.20 之前，这条只有 `PANEL_FULL` 里的 `REJECTED-BY-GAP: n` 计数器，
计数器**无法与数据窗口对账**。

**v2.20 的做法：**
`POIOnBar()` 在某根 H4 FVG **没有**产出 POI 时，把它检查过、
但因空隙被否决的每一个 OB 候选连同**实测空隙点数**打印出来：

```
HMI-REJECT,<symbol>,H4POI,<BULL|BEAR>,fvg=<time>,fvg_lo=..,fvg_hi=..|ob=<time>,ob_hi=..,ob_lo=..,gap_pts=<n>
```

`gap_pts` 与判定用的是**同一个函数** `ConnectionGapPts()` ——
`ConnectionValid()` 只是对它的一次比较，因此日志与判定不可能各说各话。

**执行步骤**

1. 目标图表设 `InpLogSignals = true`，重新编译并加载 v2.20。
2. 任意目录下跑（脚本自己找日志目录）：
   ```
   .\ReloadTest.ps1 -Rejects -Days 5
   ```
   不加 `-Source` 即所有图表一起列；结果按品种写入
   `poi_rejects_<品种>_<周期>.txt`
3. 从列表里挑**一行**，在 H4 图表上用数据窗口逐根读出：
   - `ob=` 那根 K 线的 High / Low / Open / Close
   - `fvg=` 那根 K 线以及它前两根的 High / Low

**判定标准**

| 检查项 | 期望 |
|-------|------|
| 方向 | Bullish 候选必须是**阴线**（Close < Open），Bearish 必须是阳线 |
| FVG 真实存在 | Bullish：`low[i] > high[i-2]`；Bearish：`high[i] < low[i-2]` |
| 空隙为正 | Bullish：`fvg_lo − ob_hi > 0`；Bearish：`ob_lo − fvg_hi > 0` |
| 空隙数值一致 | 手算点数 == 日志里的 `gap_pts`（允许 0 点误差） |
| 容差 | `gap_pts > PipsToPts(InpH4ConnectTolerancePips)`（默认 0.0 pip → 容差 0 点） |
| **图表结果** | 该 OB 处**没有** POI 矩形 |

六项全中 = Rule 6 否决侧 PASS。任何一项不符 —— 尤其是「空隙为正却仍画出了矩形」
或「空隙为负却出现在拒绝列表里」—— 都是 Confirmed Bug。

> 若列表为空：说明这段行情里每根 H4 FVG 都找到了合法连接的 OB。
> 这**不是** PASS，只是样本不足；换品种或拉长历史再跑。

---

### ✅ 重绘测试（四品种）—— PASS（2026-09-23，v2.21）

AUDUSD / EURUSD / GBPUSD / USDJPY 四张 M5 图同时挂载，各自多次重建：

| 品种 | block 数 | 每个 block 行数 | 最后两次窗口 | 结果 |
|------|---------|---------------|------------|------|
| AUDUSD,M5 | 3 | 156 | **不同**（07:40→08:05 / 16:15→16:40） | IDENTICAL apart from cycle_id / block_id |
| EURUSD,M5 | 4 | 199 | 相同（08:05 / 16:40） | **IDENTICAL — 199 rows match exactly** |
| GBPUSD,M5 | 4 | 52 | 相同（07:55 / 16:40） | **IDENTICAL — 52 rows match exactly** |
| USDJPY,M5 | 3 | 143 | **不同**（05:35→07:45 / 14:30→16:40） | IDENTICAL apart from cycle_id / block_id |

**两点值得单独记下：**

1. **窗口滑动了行数却不变。** 四个品种的所有 block（含最早那次 `to=14:10`
   与最后那次 `to=16:40`）行数完全一致。窗口整体前移而历史标记数量不动，
   说明新数据没有改写旧结论。

2. **A-20 描述的重新编号被实测到了。** AUDUSD 与 USDJPY 的最后两次窗口不同，
   整行比对不等、剔除 `cycle_id` / `block_id` 后完全相等 —— 正是 A-20 预测的
   序号漂移。这同时是两件事的证据：
   - A-20 的机制成立（此前只有源码推理，现在有运行时证据）
   - v2.21 的修复有效：真重绘与重新编号被正确区分开了
   窗口相同的 EURUSD / GBPUSD 则连序号都一致，走的是更严的整行相等分支。

> 与前一条一样：**这仍然测不出未来函数**。见下面的 LIVE vs BUILD。

---

### ✅ POI-02b（Rule 6 否决侧）—— PASS（2026-09-23，AUDUSD H4，v2.21）

四品种一次跑出 31 条否决记录（EURUSD 那次的计数未截到）：

```
AUDUSD    8 refused FVG(s)
GBPUSD   14 refused FVG(s)
USDJPY    9 refused FVG(s)
```

**已核对：29 条可读行的 `gap_pts` 全部逐条手算复核，零误差。**

| 检查项 | 结果 |
|-------|------|
| BULL 方向公式 `fvg_lo − ob_hi` | 29/29 与日志 `gap_pts` 完全一致 |
| BEAR 方向公式 `ob_lo − fvg_hi` | 同上 |
| 空隙为正 | 29/29 严格 > 0（容差 0 点） |
| 点值换算（5 位 / 3 位品种） | 29/29 正确 |

抽样（AUDUSD，5 位，1 点 = 0.00001）：

```
BEAR  ob_lo 0.71154 − fvg_hi 0.71026 = 0.00128 → 128 pts   日志 gap_pts=128
BULL  fvg_lo 0.70386 − ob_hi 0.70318 = 0.00068 →  68 pts   日志 gap_pts=68
```

USDJPY（3 位，1 点 = 0.001）：

```
BEAR  ob_lo 163.457 − fvg_hi 162.311 = 1.146 → 1146 pts    日志 gap_pts=1146
BULL  fvg_lo 160.774 − ob_hi 160.700 = 0.074 →   74 pts    日志 gap_pts=74
```

**被测样本（完整追溯一条）：AUDUSD 2026.09.03**

```
AUDUSD,H4POI,BULL,fvg=2026.09.03 12:00,fvg_lo=0.71727,fvg_hi=0.71785
                  |ob=2026.09.03 00:00,ob_hi=0.71713,ob_lo=0.71574,gap_pts=14
```

数据窗口逐根读出：

```
09.03 00:00   O 0.71675  H 0.71713  L 0.71574  C 0.71659   阴  <- OB 候选
09.03 04:00   O 0.71658  H 0.71727  L 0.71613  C 0.71680   阳
09.03 08:00   （未单独读；日志只列出一个候选，故它必为阳线）
09.03 12:00   O 0.71815  H 0.72067  L 0.71785  C 0.72047   阳  <- FVG 完成
```

| 检查项 | 期望 | 实测 | 结果 |
|-------|------|------|------|
| FVG 真实存在 | `low[i] > high[i-2]` | 0.71785 > 0.71727（缺口 58 点） | PASS |
| `fvg_lo` = `high[i-2]` | 0.71727 | High(04:00) = 0.71727 | PASS |
| `fvg_hi` = `low[i]` | 0.71785 | Low(12:00) = 0.71785 | PASS |
| CONF-14：取最近的反方向 K 线 | 跳过阳线 04:00，取 00:00 | 与实测一致 | PASS |
| §4.2：OB 为反方向 K 线 | Bullish → 阴线 | C 0.71659 < O 0.71675 | PASS |
| `ob_hi` / `ob_lo` = OB 的 High / Low | 0.71713 / 0.71574 | 完全一致 | PASS |
| Rule 6：空隙为正且超容差 | `fvg_lo − ob_hi = 14 点 > 0` | 与日志 `gap_pts=14` 一致 | PASS |
| **图表：该 OB 处无 POI 矩形** | 无 | 对象列表见下 | **PASS** |

**图表侧的证据（对象列表，Descrição = `H4 POI` 一组，完整 3 行）：**

```
HMI_F40A_P4_1953_1   锚点 2026.09.11 12:00   0.71857
HMI_F40A_P4_2043_1   锚点 2026.09.14 04:00   0.71567
HMI_F40A_P4_2161_1   锚点 2026.09.14 16:00   0.71490
```

标签锚点 = `(origin_time, hi)`（`HMI_ObjectManager.mqh:477`），
**没有任何一个锚在 2026.09.03 00:00，也没有任何一个价格是 0.71713。**

> **必须排除的一种误判：** 「图上没有」也可能是 POI 建了但因超出上限被删掉图形。
> 本例不成立 —— `InpH4MaxPOIs = 12`，实际只有 3 个 POI，
> `POIPush()` 的淘汰分支 `if(g_poi_n >= cap)` 从未执行，`out_of_window` 始终为 false。
> 所以 09.03 00:00 处没有矩形，只能是 `POIOnBar()` 当初就没建。

**结论：Rule 6 的否决侧成立。** 一条完整追溯 + 29 条 `gap_pts` 手算零误差。

> 教训（与 A-17 同源）：中途我曾按 H4 图截图判断「矩形左边缘在 9 月初」，
> 那是读错了日期轴。**图形位置只能用对象列表的锚点判定，不能用截图目测。**
> 这次没有据此改代码，因为结论压到了对象列表上。

> 顺带：v2.21 把三个品种的结果都写进同一个 `poi_rejects.txt`，
> 后一次覆盖前一次，屏幕上只留最后的 USDJPY。v2.22 已按品种分文件。

---

### ✅ Reload 一致性 —— PASS（2026-09-23，USDJPY，v2.13）

```
USDJPY,M5   -> 7 blocks    全部 rows=143
USDJPY,M15  -> 5 blocks    全部 rows=143
USDJPY,M2   -> 1 block     rows=143
USDJPY,M30  -> 1 block     rows=143

窗口一致：m5_bars=5000, h4_bars=500, from=2026.08.28 18:30, to=2026.09.23 03:25

--- USDJPY,M5 : comparing the last two builds ---
IDENTICAL - 143 rows match exactly. No repaint.
```

| 用例 | 结果 | 依据 |
|------|------|------|
| POI-05 / CISD-06 / MSS-06（Reload 一致性） | **PASS** | 同一图表两次重建逐字节相同 |
| §15.4 图表周期独立性 | **PASS** | **14 次独立构建、4 种图表周期（M2/M5/M15/M30），全部 143 行、窗口一致** |
| CONF-16 窗口滑动 | **符合预期** | block[0] 窗口早一根（18:25→03:20），行数仍为 143，滑出/滑入的 K 线均不带标记 |

**这个结果不能证明什么（重要）：**

```
Reload 一致性  =  「重建是数据窗口的纯函数」
              ≠  「没有使用未来数据」
```

若实现中存在未来函数，每次重建都会读到同样的未来 K 线，于是每次都产出同样的
（错误的）结果 —— 照样 IDENTICAL。**该测试对 Future Leak 是盲的。**

真正的 Future Leak 实测见下一节。

---

### 📊 标记产出的真实分布（2026-09-24 实测，四品种 M5）

规划 LIVE vs BUILD 时必须先知道这个,否则会把「安静」误判成「坏了」。

```
09.01 Tue    6        09.15 Tue   97
09.02 Wed   29        09.16 Wed   65
09.03 Thu   16        09.17 Thu    0   <-- 零标记交易日
09.04 Fri   37        09.18 Fri   47
09.07 Mon   24        09.21 Mon   34
09.08 Tue   69        09.22 Tue   19
09.09 Wed   61        09.23 Wed    9
09.10 Thu    1
09.11 Fri    0   <-- 零标记交易日
09.14 Mon   29

18 个交易日   合计 543   均值 30.2   中位数 26.5   最小 0   最大 97
零标记交易日 3/18 ≈ 17%
```

**三条必须记住的性质：**

1. **标记成簇。** 同一个 ARMED 周期会一次吐出 CISD / MSS / BPR / PA 多条 ——
   各品种最后三条标记的 `cycle_id` 完全相同（2212 / 2882 / 1158 / 2661）。
   所以 543 条背后的**独立事件**远少于 543。
2. **整天零产出是常态**，不是故障。09.11 与 09.17 都是完整的零标记交易日，
   而且两侧都是活跃日（09.16 有 65 条、09.18 有 47 条）。
   观测到的最长空窗是 09.10（1 条）到 09.14，跨周末约 4 天。
3. **均值不能当发生率用。** 1 到 97 的跨度下，
   「均值 30/天 → 4 小时该有 5 条」这种推断是无效的。
   本项目曾据此误判过一次「挂了 4 小时还是 0，是不是坏了」。

**「实时标不出来」与「引擎没产出」的区分方法：**

看**历史重建**的最后一条标记时间。重建与实时共用同一个
`ProcessClosedM5Bar()`（Rule 51），所以：

| 重建的最后一条标记 | 判断 |
|---|---|
| 也停在同一时刻 | 引擎确实没产出 —— 继续等，不是 bug |
| 一直标到最近，只有实时是空的 | `g_live` / `LogPhase7` 路径有问题 —— 查代码 |

2026-09-24 的实测走的是第一种：重建窗口到 `09.24 12:35`，
最新一条标记是 EURUSD `09.23 04:00`。**实时路径已据此排除。**

**加快取样：** 多开几个品种的 M5 图即可，互不干扰（脚本按 `(SYMBOL,TF)` 分组）。
已在跑的图**不能**重载，否则实时样本清零。

---

### ⚠️ 2026-09-24 撤销：此前所有 `live rows: 0` 的结论作废

`tools/ReloadTest.ps1` 的 `-LiveVsBuild` 迭代的是 `$raw`（已过滤为只含
`HMI-BUILD` 的行），而 `HMI-LIVE,` 不含该子串 —— **实时行集结构上永远为空**
（A-27）。2026-09-23 至 09-24 期间脚本报出的每一个 `live rows: 0`
都是过滤器的产物，不是市场的事实。

据此写下的「行情安静，继续挂」的判断**没有依据**，已撤销。
v2.34 修复后需重新采样。

> 本条同时说明：一个**只可能返回一种结果**的测试比没有测试更糟 ——
> 它会持续产出看似有意义的结论。此后凡新增判定逻辑，
> 必须先构造一个应当返回「非零 / 失败」的情形验证它确实会返回。

---

### ✅ Context 状态机账目 —— PASS（2026-09-25，8 品种，v2.40，825 个事件）

每个 CHOCH 打开一个 TRANSITION，其结局只有 TRANS_OK / TRANS_FAIL / TIMEOUT 三种，
故 `CHOCH − (OK + FAIL + TIMEOUT)` 只能为 0 或 1（1 = 当前仍在 TRANSITION）。

| 品种 | CHOCH | OK + FAIL + TIMEOUT | 未结束 |
|---|---|---|---|
| AUDUSD | 16 | 8 + 7 + 1 | 0 |
| EURUSD | 12 | 5 + 5 + 2 | 0 |
| GBPUSD | 11 | 4 + 7 + 0 | 0 |
| NZDUSD | 14 | 8 + 6 + 0 | 0 |
| USDCAD | 10 | 4 + 5 + 1 | 0 |
| USDCHF | 16 | 8 + 7 + 1 | 0 |
| USDJPY | 10 | 6 + 3 + 1 | 0 |
| XAUUSD | 14 | 6 + 4 + 3 | **1** |

XAUUSD 的 1 与其最新事件 `str=0`（TRANSITION 中强度清零）一致。
交叉核对：USDJPY 图表面板 `str 12 CLEAN` == 日志最新 `str=12`；
面板由 MESSY 变为 CLEAN，是 v2.31 / v2.32 修复首次在实盘面板上可见。

**强度分布首次实测**（中位数 3–6、P90 8–18、最大 11–24）**不得用于定档** ——
这是 A-33 修复前的计数，包含重复计数造成的虚高。
脚本 `-Ctx` 已加入 A-33 特征检测（下界计数），修复前后对比用。

---

### 🟡 Future Leak 首条样本 —— PASS（n=1，2026-09-25，USDJPY,M5，v2.40）

```
实时   USDJPY,MODEL,1,3225,3225,OB,BPR,2026.09.25 16:00:00,157.503,...
重建   v2.40  from=2026.09.02 07:25  to=2026.09.25 16:20   (144 rows)
结果   comparable 1 | after rebuild 0 | other version 0 | aged out 0
       ALL 1 COMPARABLE LIVE MARKS SURVIVED THE REBUILD
```

该 BPR 在实时状态下逐根产生，重建时以完整数据复现，除序号外各字段一致。

**这只证明方法可用，不证明结论。** n=1，且只覆盖 BPR 一个模型。
「Future Leak: PASS」须待多品种、多模型（CISD / MSS / PA）样本累积后判定。

复核（同日，USDJPY,M5 再次重建 from=08:35 to=17:30，139 行）：同一条 BPR 仍在，
`comparable 1`，结果不变。其余 9 个图表源当日 `live rows 0`（全部标记来自重建），
样本数仍为 **n=1**。

### 🟡 Future Leak 第二轮 —— PASS（n=10，2026-09-29，仅 USDJPY,M5，v2.40）

```
挂载     2026-09-25 → 09-29（跨周末），日志 0923/0924/0925/0928/0929
实时行   USDJPY,M5 11 条；其余 9 个图表源 0 条
重建     v2.40  from=2026.09.04 07:35  to=2026.09.29 16:30   (201 行)
结果     comparable 10 | after rebuild 1 | other version 0 | aged out 0
         ALL 10 COMPARABLE LIVE MARKS SURVIVED THE REBUILD
```

判定标准（≥10 条 / ≥3 品种 / 出现过的模型都有样本）只满足第一条：
**单品种，不能下「Future Leak: PASS」。**

新版脚本给出的模型分布（同一次重建，10 条全部存活）：

```
BPR 2 | MSS 1 | PA BREAK-RETEST 1 | PA ENGULFING 2 | PA REJECTION 4
```

CISD 尚无实时样本。

**Phase 0b 实时验收：** `Select-String -Path .\*.log -Pattern 'HMI-GUARD'`
覆盖 0923–0929 五个日志，**0 行**。Phase 5 的 ARMED 前复核一次都没有需要拦截的情况 ——
即 Phase 0b 已在前面结束了所有不合格的 Session。（cycle 494 的历史 ARMED 时间：用户 2026-09-30 决定不核对，**未验证、已豁免**。）

其余图表不是没在运行：28–29 日志里 AUDUSD / EURUSD / GBPUSD / NZDUSD 均有
7–9 次重建、数百条 HMI-CTX 与数十条 HMI-REJECT。且这些图表 09.25 之后各次重建
行数不变（GBPUSD 52、NZDUSD 81、USDCAD 161、EURUSD 121），USDCHF 降到 0 ——
重建与实时一致地表明这些品种近期没有新标记。原因（Context 处于 RANGE /
TRANSITION 时按 BRI-07 不出新 setup，或别的原因）待 `-Live` 新增的两列确认。

脚本随之在 `-Live` 增加「最新标记时间」与「最后一次 H4 事件后的 Context」两列，
在 `-LiveVsBuild` 增加可比样本的模型分布。

途中暴露并修复的测试工具缺陷（均不涉及指标）：

| 编号 | 问题 | 表现 |
|---|---|---|
| A-35 | 把重建之后才产生的实时行、旧版本实时行、已移出窗口的实时行都算作「缺失」 | 16:00 的 BPR 被拿去对比 to=15:50 的重建 |
| A-35b | 取重建窗口时认了只写了开头、还没写结尾的半截重建（MT5 日志有缓冲） | 声称对比 to=16:20，实际用的却是 to=15:50 的行数据 |

正确顺序：**先攒实时行 → 再重载 → 等日志写完 → 再比对。**

---

### ✅ 同版本重建一致性 —— EURUSD,M5（2026-09-25，v2.40）

两次 v2.40 重建，窗口起点 05:40 → 07:15，行数 171 → 170。去掉序号后仅 1 条不同：

```
old only  PA ENGULFING  2026.09.02 16:15:00
新重建暖机结束 ~15:35，新重建第一条标记 09.02 20:00
```

新重建在 16:15 时尚未产出任何标记（暖机后还须 POI 触碰 → Session → block → ARMED），
而旧重建此时已在一个周期中途。归为 **converging**，其余 170 条完全一致。**无重绘。**

脚本据此新增 `converging` 类：只在旧重建中、且早于新重建第一条标记的差异。
该规则只覆盖窗口开头，窗口中段的真实重绘仍会落入 LOOK。

用新脚本复跑（用户，2026-09-25）：`converging 1`，LOOK 0，结论行「No repaint.」。

---

### Future Leak 测试 —— LIVE vs BUILD

```
HMI-LIVE   逐根实时产生：那一刻只有「到当前 K 线为止」的数据
HMI-BUILD  重建产生：整个窗口都在手上
```

若某个标记实时产生时是 A，重建后变成 B（或消失 / 多出），
说明重建用到了当时不可能拥有的数据 —— 这就是 Rule 51「Historical Build ≈ Live Replay」
的实测，也是唯一能证伪 Future Leak 的日志级方法。

**比对键：不含 cycle_id / block_id（A-20）**

日志行的第 4、5 列是 `g_next_id` 自增序号，每次 init 重置为 1。
而 `SeriesAppend()` 只追加不裁剪：跑了 K 根 M5 的实时会话，窗口是
`[T0-5000, T0+K]`；此刻重载得到的窗口是 `[T0+K-5000, T0+K]`。
最老的 K 根连同其中分配过的 id 一起消失，之后所有 id 整体前移。

**因此这两列在 live 与 rebuild 之间必然不同，逐字节比对整行会把
「重新编号」误报成未来函数。** 脚本自 v2.21 起按事件本身比对：

```
dir / anchor / model / confirm_time / price / ref_time / ref_level
```

这七项里任何一项变了，才是真信号。

**步骤：**

1. `InpLogSignals = true`，**让图表持续运行**，直到有新的标记在实时状态下确认
   （日志里出现 `HMI-LIVE,` 开头的行）
2. 期间**不要**重载图表 —— 重载会把已有的实时标记变成重建标记，样本归零
3. 重载一次（切周期往返）
4. ```powershell
   .\ReloadTest.ps1 -LiveVsBuild -Days 5
   ```
   - 脚本自 v2.22 起**自己找日志目录**（当前目录 →
     `%APPDATA%\MetaQuotes\Terminal\<ID>\MQL5\Logs` 中 .log 最新的那个），
     在哪个目录跑都行；找不到时用 `-LogDir "<路径>"` 指定（A-22）。
   - **不加 `-Source` 就是全部图表一起跑**。手写品种名是个坑：
     券商会加后缀（`EURUSD.a` / `EURUSDm` / `EURUSD#`），写错了会静默匹配不到。
   - 跨天挂机**必须**带 `-Days N`：MT5 每天新开一个日志文件，
     昨天的实时行在昨天的文件里，不带这个参数会静默丢样本（A-21）。

**判定：**

| 输出 | 结论 |
|------|------|
| `ALL n LIVE MARKS SURVIVED THE REBUILD.` | 本窗口内**未见** Future Leak |
| `n LIVE mark(s) do NOT appear in the rebuild` | **确认 Future Leak 或实时/重建路径不一致** |

> 成本说明：需要等实时确认出新标记，可能要数小时。这是这项测试无法回避的代价。

---

## 2. 逐模块 Replay Test (Rule 71)

### 2.1 H4 POI

| 用例 | 步骤 | 期望 |
|------|------|------|
| POI-01 Formation | 定位一个 H4 Bullish OB + Bullish FVG | 矩形在 **FVG 第三根 K 线收盘**时出现，不早于此 |
| POI-02a Gap Accept | 定位一个 OB 与 FVG 重叠 / 相接的形态 | 产生 POI，边界 = OB 的 High / Low |
| POI-02b Gap Reject | 用 `-Rejects` 列出被否决的候选，逐根对数据窗口 | 空隙为正且 > 容差，且该 OB 处**无**矩形（Rule 6） |
| POI-03 Touch | 价格回落触碰 POI | 触碰 K 线收盘时 POI → TOUCHED，同时 Refinement Session 建立 |
| POI-04 Invalidation | H4 收盘跌破 POI 下沿 − margin | POI → INVALIDATED，样式改变，**矩形不消失** |
| POI-05 Reload | 在 POI-03 之后 Refresh / 切周期 / 重启 MT5 | POI 的 confirm_time / zone / state 完全一致 |
| POI-06 窗口挤出（A-11） | 连续创建超过 `InpH4MaxPOIs` 个 POI | 最旧的 POI **图形消失**（不是停留在存活样式）；其内部记录仍在且为 `POI_EXPIRED` |
| POI-07 v1.00 等价性（A-11） | 同一区间跑 v1.00 与 v1.01，导出 CSV | 两份信号日志**逐行完全相同** |
| POI-07b v2.00 等价性（D-10） | 与 v1.x 对比时**必须先设 `InpEnableBreaker = true`** | 设为 true 后逐行相同；设为 false 时差异应**仅限**于 Breaker 锚定的 Cycle（用 CSV 的 `anchor_type` 列核对） |
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
| BRK-00 开关（D-10） | `InpEnableBreaker = false`（默认）→ 全区间**不得**出现任何 `M5 BREAKER ARMED`，且逆势 M5 OB 一个都不该被创建；设为 true 后以下用例才适用 |
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

### 3.0 Reload 一致性测试（最快能证伪重绘的做法）

**前置：** v2.12 起，每次历史重建会在日志里写一对标记，
用于界定「一次构建」的边界，并暴露窗口是否滑动：

```
HMI-BUILD-BEGIN,USDJPY,m5_bars=5000,h4_bars=500,from=2026.09.05 12:35,to=2026.09.22 19:20
HMI-BUILD,...            <- 每个确认的标记一行
HMI-BUILD-END,USDJPY,marks=137,cycles=20,pois=12,blocks=64
```

**步骤：**

1. 指标参数 `InpLogSignals = true`
   （改参数本身就会触发一次重新初始化 → 完整重建 → 写下第 1 个 block）
2. 在 `<数据文件夹>\MQL5\Logs` 里 Shift+右键 → 在此处打开 PowerShell
3. `.\ReloadTest.ps1` —— 确认能看到 1 个 block
4. **强制重建**（三选一，可靠性从高到低）：
   - 切周期 M5 → M15 → M5
   - 改一个纯显示参数（例如 `InpPanelX` 10 → 11）
   - 移除指标再重新添加
   > 注意：图表「刷新」**不一定**触发重建 —— 它不重新调用 `OnInit`。
   > 用上面三种之一，并用步骤 5 确认 block 数确实增加了。
5. `.\ReloadTest.ps1 -Compare`

**判定：**

| 输出 | 含义 |
|------|------|
| `IDENTICAL - N rows match exactly` | 本区间**无重绘**，POI-05 / CISD-06 / MSS-06 通过 |
| `DIFFERENCES: n` 且 `WINDOW MOVED` 同时出现，差异只在最老边缘 | 窗口滑动，非重绘（见 CONF-16） |
| `DIFFERENCES: n`，差异出现在中间任意位置 | **重绘或未来函数，真问题** |

脚本位于仓库 `tools/ReloadTest.ps1`。

---

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

除信号行之外，还有**诊断行**（不是信号，不代表任何标记）：

```
HMI-CTX,<symbol>,<BOS|CHOCH|TRANS_OK|TRANS_FAIL|TRANS_SAMELEG|TIMEOUT>,
        dir=<UP|DOWN>,live=<0|1>,ctx=<BULLISH|BEARISH|RANGE|TRANSITION>,
        str=<n>,messy=<0|1>,bar=<确认破坏的H4收盘时间>,
        swing=<被破坏的摆动点时间>,swing_px=<价格>,close=<破坏时收盘价>
```

每次 Context 状态变化输出一行，记录的是**这次事件留下的状态**。
在此之前 Context 这条链没有任何可对账的输出 —— `str N` 与 `MESSY`
都只能照单全收。有了它可以：

- 把面板上的 `str N` 从日志里**逐个数回来**
- 核对 Rule 3（`TRANS_SAMELEG` 就是被新鲜度判据挡掉的那些破坏）
- 验证 A-25 / BRI-06 的修复（`TRANS_FAIL` 的行里 `messy` 应为 1，
  紧随其后的 `BOS` 行里 `str` 应从 1 重新起算）
- 统计强度的真实分布，**据此定分档阈值，而不是拍脑袋**

用 `.\ReloadTest.ps1 -Ctx -Days 5` 读取：按品种给出各事件计数、
强度的 min / P33 / median / P67 / P90 / max，以及当前值所处的分位；
同时导出 `ctx_events.csv`。

> 前缀特意不用 `HMI-BUILD` / `HMI-LIVE` —— 重绘比对脚本按 `HMI-BUILD,`
> 切分，若共用前缀，这些诊断行会被当成标记行计入，污染已经通过的
> 143 / 199 / 52 / 156 那组行数。`live=` 字段承担区分实时与重建的职责。

另一条：



```
HMI-REJECT,<symbol>,H4POI,<dir>,fvg=..,fvg_lo=..,fvg_hi=..|ob=..,ob_hi=..,ob_lo=..,gap_pts=<n>
```

在某根 H4 FVG 未能产出 POI 时输出，用于 POI-02b 对账。它只读不写，
不参与任何状态迁移；关闭 `InpLogSignals` 即完全消失。

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
MetaEditor:            PASS         (v2.40, 0 errors / 0 warnings, 2026-09-24)
Replay:                NOT VERIFIED
```


---

### v2.42 验收清单（BRI-09 + A-37 诊断）

```
1  编译 0 errors（Rule 70）
2  图上：六条水平线（PD 蓝 / PW 紫 / PM 金，虚线），重合价位只有一个合并标签
   对照券商 D1 / W1 / MN1 K 线核对数值（数据窗口）
3  SWEEP / BROKEN 标签只出现在 M5 层，保留最近 5 天
4  日志：HMI-BUILD,<sym>,LIQ,... 行；`-Source` 重载对比与 `-LiveVsBuild` 一并覆盖
5  -Chain：A-37 各品种链条停在哪一步
6  回归：v2.40 的 MODEL 标记在 v2.42 重建中不变（S-1 只标记）——
   用 v2.40 与 v2.42 各一次重建的 MODEL 行对比
```


### ✅ v2.42 回归 —— MODEL 标记不受 BRI-09 影响（2026-09-30，USDJPY,M5）

```
run1  v2.40  from=2026.09.07 03:40  to=2026.09.30 12:35
run2  v2.42  from=2026.09.07 05:25  to=2026.09.30 14:20   246 行（MODEL 205 + LIQ 41）
only one build has LIQ rows (version upgrade) - comparing MODEL rows only
IDENTICAL apart from cycle_id / block_id - 205 rows. No repaint.
```

S-1（只标记、不过滤）实测成立：加入 PD/PW/PM 与 sweep 判定后，模型标记逐行不变。


### v2.45 流动性重载一致性模拟（2026-09-30，离线，`tools/liq_reload_sim.py`）

```
模型   随机游走 M5 → 聚合 H4 → 已消费 H4 求 PD/PW/PM → S-3 判定 → v2.45 H4 回放
比较   连续运行（07.01 起） vs 三个较晚起点的重建，8 组随机种子，共 24 次重建
区间   重建的真实预热结束 + 24 h 之后
v2.45 (H4 pre-scan)    rebuilds 24  mismatching 0
v2.42 (no pre-scan)    rebuilds 24  mismatching 6
       例：seed 4，重建起点 09.09 → 重建独有 09.18 01:00 PMH SWEEP
           （连续运行中 PMH 在窗口之前已被越过，重建当作从未触发，再次出事件）
```

该模拟复现了审查二的问题，并验证修复后的规则层行为。**它不替代编译和实盘运行**：
MQL 实现仍需按下方 v2.46 验收清单实测。

### v2.46 验收清单（审查一至三 + Phase 0b / BRI-07 回归）

```
1  编译 0 errors
2  版本：每张图 `starting on` 与 BEGIN 行 ver= 均为 2.46；属性页版本 2.46
3  同版本重载：`.\ReloadTest.ps1 -Source "<图>,M5"`（先重载该图两次）
     期望：同一窗口 → IDENTICAL inside the comparable region
           窗口移动 → 区间内 0 MISMATCH；区间前差异列为 PENDING REVIEW
4  实时 vs 重建：`-LiveVsBuild` 双向 0 MISMATCH；按版本 / 参数分开
5  流动性：带「?」的价位（PMH? 等）= M5 覆盖前已被越过；重载前后同一价位不得出现两次事件
6  标签：同根同价的 PDH/PWH 等合并为一个标签；同根不同类型逐层错开
7  回归：Phase 0b / BRI-07 —— `Select-String -Path .\*.log -Pattern 'HMI-GUARD'` 仍为 0；
          `-Chain` 各品种「未触碰、INVALID、Context 同向」仍为 0
          v2.43 → v2.46 跨版本：MODEL 行只允许在窗口起点附近变化（M5 起点对齐）
```


### v2.48 验收清单（替代上面的 v2.46 清单；只验收本轮缺陷修复，不含趋势升级）

```
0  编译 0 errors / 0 warnings（截图）
1  版本：每张图 `starting on` 与 BEGIN 行 ver= 均为 2.48
2  多实例：`Select-String -Path .\20*.log -Pattern ',inst=' | Select-Object -First 3` 有输出；
          同一品种同一周期挂两个实例时，脚本提示 split as SYMBOL#INSTANCE
3  共用 M5：BEGIN 行 from= 回到未对齐的原始起点（不再落在 00/04/08… 整点）
4  流动性回放：`Select-String -Path .\20*.log -Pattern 'HMI-LIQ-REPLAY' | Select-Object -Last 8`
          have_from 早于或等于 need_from，unknown=0；unknown>0 时说明终端 M5 历史不够远
5  同版本重载：同一张图重载两次 → `-Source "<图>,M5"`
          同一窗口：IDENTICAL inside the comparable region
          窗口移动：区间内 0 MISMATCH；区间前差异为 PENDING REVIEW
6  实时 vs 重建：挂一段时间后 `-LiveVsBuild`，双向 0 MISMATCH
7  回归：`HMI-GUARD` 0 行；`-Chain` 各品种「未触碰、INVALID、Context 同向」0
          v2.43 → v2.48 跨版本：MODEL 行 upgrade regression 0 difference
          （v2.47 撤销了 M5 裁剪，模型标记应与 v2.43 完全一致）
```

回放证据（规则层模型 `tools/liq_reload_sim.py`；不替代以上实测）：
```
PIPS  v2.42 4/18 · v2.46 0/18 · v2.47 0/18
ATR   v2.42 4/18 · v2.46 0/18 · v2.47 0/18
ATR 系数 2.0 定向：v2.46 2/48（PMH BROKEN 仅连续运行有）· v2.47 0/48
```

### v2.52 验收清单（基础修复阶段；以 v2.48 交易规则为基线，任何参数下 MODEL 不变）

已由验收方确认（v2.51，2026-10-05）：编译 0/0、规则撤回、随包测试复现、参数摘要与 v2.48 相同。

```
0  编译 0 errors / 0 warnings（v2.52 只改流动性模块与主文件日志）
1  版本：`starting on` v2.52 run= init=；BEGIN ver=2.52，params= 与 v2.48 相同
2  固定窗口回归：v2.48 与 v2.52 并排 → `-Source <v2.48 源> -Versus <v2.52 源>`
          → 「0 difference(s) over N / N MODEL row(s), same window and parameters」，N > 0；
          InpStopIdentificationOnBlockInvalidation = true 再做一次
3  有限 Max bars（A-53）：把「Max bars in chart」设为约 20000 后重启终端、挂指标。看 HMI-LIQ-REPLAY：
          capped=1；req_from 不早于 floor；fail 从不出现 CAP；got > 0 时 state=READY 或 waiting 只含可恢复条目；
          同一 init 内 HMI-LIQ-HIST 的 ARRIVED / SETTLED / BEFORE_FLOOR 至多一次，且其后的 END 为 liq=READY；
          unknown>0（被截断的条目）是信息提示
4  延迟下载：删除该品种本地历史后挂指标 → state=WAITING（fail=LOAD 或 NOT_BUILT）→ ARRIVED → READY；
          再重载一次（一开始就 READY），两次 READY 构建 `-Source` → MODEL / LIQ 两行均 IDENTICAL over …
5  超过快速探测：首个构建 WAITING 后断网 > 5 分钟 → HMI-LIQ-HIST SLOW（带 err / fail），面板仍 WAITING；
          恢复网络 → ARRIVED → READY。断网期间不得出现 liq=READY 的 END
6  分开报告：WAITING 构建 vs READY 构建 → MODEL IDENTICAL over …，LIQ PENDING
7  日志校验：`pwsh -File tools\logtests\Run-LogTests.ps1` → 35/35；
          人工删去某构建 END 的 build=、或任一行的 ,run=…,init=… → INCOMPLETE
8  同版本重载：MODEL / LIQ 两行均 IDENTICAL over a / b row(s)（行数 > 0）
9  实时 vs 重建：`-LiveVsBuild` 双向 0 MISMATCH，live events compared > 0
10 重启残留：强杀 terminal64.exe → 重启 → `removed the objects of instance`
```

离线证据（不替代以上实测）：`python3 tools/liq_wait_sim.py` 12/12（严格终端；`--logic v2.51` 8/12，
`--logic v2.50` 2/12）；`Run-LogTests.ps1` v2.52 脚本 35/35（v2.51 脚本 26/35，v2.50 脚本 8/35）。

### v2.53 验收清单（BOS 去重；基线 v2.52 = 63379fd）

```
0  编译 0 errors / 0 warnings
1  版本：starting on v2.53；BEGIN ver=2.53；默认参数下 params=461F006E（与 v2.52 相同）
2  去重可见：日志出现 HMI-CTX-DEDUP（also>0）；`-Ctx`（A-61 / A-62 / A-63）：
          「swing consumed twice in one build」必须为 0 proven、0 pending，且全部构建 COMPLETE and read ——
          同一完整构建内同一摆动点被消费两次，是日志可证明的缺陷；不完整构建、无效消费记录、
          与 also= 不符的去重列表只列为 pending（附原因），既不作确证，也不能当作 0 通过；
          「A-33 stale BOS」的 suspect（同段更早的收盘在最早可能确认时间之后、以超过余量越过该点 —— 确认时间是日历估算，
          假设中间不缺 H4 K 线）与 pending（价格缺失 / 非数值、精度不一致、余量逐根或未记录）逐条人工核对，
          都不计为已确证的重复计数；InpH4SwingRight 非默认时加 -H4SwingRight <n>），
          强度分布明显低于 v2.52（离线样本最大强度 17 → 7）
3  必验场景（离线，python3 tools/h4_dedup_sim.py 4/4）：
          一根收盘越过多个旧高后停留只计一次 BOS；空头对称；新摆动结构被有效突破产生新事件
4  实时 vs 重建：`-LiveVsBuild` → MODEL / LIQ 双向 0 MISMATCH，「+ N H4 structure event(s)」N > 0；
          只因强度编号不同的条目为 PENDING REVIEW（说明见 A-56），事件 / 主参考点 / 状态不同则为 MISMATCH
          一段实时区间中间不能有终端休眠 / 断线（A-60）：工具把两次构建之间的每根 K 线都当作实时处理过。
          休眠前先重载一次收尾；跨了休眠的区间不作证据（用当天日志 `-Days 1`，或按 docs/evidence 的方法
          只比较实时最后一条记录之前的 K 线）
5  同版本重载：MODEL / LIQ / CTX 三行均 IDENTICAL。两次构建必须是同一窗口：同一根 M5 内连续重载两次
          （Ctrl+I -> HMI -> 属性 -> 确定，两次），BEGIN 的 from / to / warmup_end 相同。
          终端自动重建（prev_calculated = 0 / K 线被修订）窗口会移动：预热结束后的第一个会话在各自的
          首根非预热 K 线开始，其 TIMEOUT 及会话末段的块 / ARMED / 周期随之不同，差异可落在
          「warm-ups + 24 h」之后（2026-10-08 实测，见 docs/evidence/v2.53_reload_window_edge.txt）——不作验收证据
6  对比 v2.52（固定窗口，四品种）：v2.52 与 v2.53 两个实例同一根 M5 内挂上，
          `-Source <v2.52 源> -Versus <v2.53 源>` 逐品种（A-57 判据）：
            verdicts 行 UNEXPLAINED = 0
            PENDING_ATTRIBUTION = 0；不为 0 时逐条给出人工结论（attribution_*.txt 每行一条）后方可通过
            「H4 state: identical」→ 链路差异必须为 none
          链路行先核对生命周期（A-58），再看上游是否已解释：
            SESS 开始晚于其 POI 确认；BLK 确认 ≥ 会话开始、早于会话结束（NEW_SESSION 结束可同根）；
            ARMED 晚于块确认、在会话开始之后且结束之前、方向与会话一致；
            MODEL 在其周期 ARMED 之后、不晚于下一个 ARMED（同根周期切换允许）；
            ARMED 当根只允许 PA ENGULFING / REJECTION（D-4，默认开；构建关闭 D-4 时加 -NoArmedBarPA）
            违反 → UNEXPLAINED；父节点 / 时间 / 结束信息缺失 → PENDING；父节点为 UNEXPLAINED 的子行 → PENDING
            另一版的会话结束只解释其后的块 / ARMED，不解释更早的差异
          每品种保存控制台输出与 attribution_*.txt，作为「去重引起的 H4 状态、POI、Session、MODEL 差异」清单
7  运行记录（验收方 2026-10-07 要求，每项随证据保存）：
          - 4 / 5：各类别实际比较的行数（MODEL / LIQ / CTX；live events compared）。某类没有事件 = 尚无该类一致性样本，
            不算通过；出现 PENDING REVIEW 须写明原因
          - 6：图表的 InpPAAllowArmedBarConfirm（D-4）。为 false 时归因必须加 -NoArmedBarPA
          - 6：图表的 InpStopIdentificationOnBlockInvalidation（D-5）。为 true 时块失效提前关闭周期没有日志行，
            工具不覆盖这一关闭边界：相关周期按图表与记录人工核对，不能把工具输出当作该路径已自动验证
```

离线证据：`docs/evidence/v2.53_h4_dedup_offline.txt`（场景 4/4；EURUSD 回放全部差异可追溯，H4 状态 0 分歧）；
`Run-LogTests.ps1` 修订脚本 60/60（v2.53r2 脚本 52/60，交付的 v2.53 脚本 41/60，v2.52 脚本 35/60；
c15–c25 为 A-58 生命周期用例，其中 c17 / c20 / c22 / c24 是合法边界，新旧脚本都须通过）；`h4_dedup_sim.py` 场景 4/4、归因防护 6/6
（Python 模型不含 M5 链路，生命周期核对只在 ReloadTest.ps1 与日志用例中）。
验收方已确认（2026-10-06）：v2.53 编译 0/0、45/45、4/4、12/12、params=461F006E。
验收方已确认（2026-10-07）：v2.53r3 工具修补通过——MQL 23/23 与 v2.53 字节相同，60/60，独立复测 12/12；
剩余为 MT5 运行证据（第 4、5、6 项及第 7 项记录）。通过后冻结 v2.53，再开始 v2.54 保护点与波段锚点。
验收方 MT5 复核（2026-10-09）：v2.53r3 冻结为开发与回退基线。结果按适用范围记录 ——
  第 5 项 同窗口重载一致（MODEL 743/743、LIQ 389/389、CTX 107/107；GBPUSD / USDCHF 的 MODEL 为样本不足，不写通过）；
  移动窗口存在已解释的历史标记差异（A-59，保留为后续独立改进，不并入 v2.54）；
  第 4 项 不中断区间的实时 vs 重建一致（10-09 连续运行 MODEL 14 / LIQ 5 / H4 2；10-08 休眠前 LIQ 7 / H4 1）；
  跨休眠区间不按连续实时覆盖验收（A-60，覆盖心跳另立）；
  第 6 项 v2.52 vs v2.53 四品种 MT5 比较：**未执行**，不填 PASS（离线 EURUSD 回放只是补充证据）；
  第 2 项 `-Ctx` 的 27 次 stale BOS 为诊断误报（A-61，工具另行修订）。
用户决定（2026-10-08）：不做第 6 项 MT5 跨版本比较。v2.53 与 v2.52 的差异以离线证据为准
（`docs/evidence/v2.53_h4_dedup_offline.txt`：EURUSD 回放 156 条差异全部 explained，PENDING 0，UNEXPLAINED 0）；
MT5 运行验收为第 4 项（实时 vs 重建）与第 5 项（同版本重载），8 个品种，默认参数（D-4 开、D-5 关）。

### v2.54 验收清单（保护点与波段锚点，BRI-12 修订稿 2；基线 v2.53r3）

```
0  编译 0 errors / 0 warnings（v2.54 开发版、r2：验收方 2026-10-13 MetaEditor 5.0.0.6230 X64 均 0/0）
1  版本：starting on v2.54；BEGIN ver=2.54；默认参数下 params=461F006E（无新输入）
2  新日志行（InpLogSignals = true）：HMI-PROT / HMI-ANCHOR / HMI-CTX-INTERNAL，均带 inst / run / init
          每个趋势段（leg=）的第一行为 SET 或 INVALID；段以 BREAK 或 FALLBACK 结束，同根有 ANCHOR RESET
          每条 CHOCH（HMI-CTX）同根有 HMI-PROT BREAK 或 FALLBACK；BREAK 的 level = 该 CHOCH 的 swing_px
          ADVANCE：多头 level > prev、空头 level < prev；KEEP_WORSE：cand 不优于 level
          `-Ctx`：transitions 平衡；swing consumed twice 0 proven / 0 pending（HMI-CTX-INTERNAL 计入）；
          level installed already broken 0 proven（A-65；ATR 余量下为 pending，逐条核对）
3  离线：python3 tools/h4_protect_sim.py → 45/45（含 A-66 判定注入）；--replay 退出码 0：前缀无重绘、
          P1 不变量在固定余量与 ATR 0.20 两种模式都为 0（docs/evidence/v2.54_protect_offline.txt）
4  实时 vs 重建、同窗口重载：方法同 v2.53 第 4、5 项（不中断区间；同一根 M5 内连续重载两次）。
          r3 起 PROT 行（HMI-PROT / HMI-ANCHOR / HMI-CTX-INTERNAL）是独立判定类别：重载须「PROT IDENTICAL」，
          实时 vs 重建的 protected-level rows 双向一致；只差 leg 序号为 PENDING REVIEW。
          默认固定余量与 ATR_FRAC 各保留一份日志；ATR 下「level installed already broken」的 pending
          须用逐根余量 / 图表数据核对，不能按 0 proven 直接通过
5  跨版本 v2.53 vs v2.54（固定窗口：同品种两张图，同一根 M5 内各重建一次）：
          `-Source <v2.53 源> -Versus <v2.54 源>`（BRI-12 模式，r4 起）。判据：verdicts 行 UNEXPLAINED = 0；
          PENDING_ATTRIBUTION = 0，不为 0 时逐条给出人工结论（attribution_*.txt 每行一条）后方可通过；
          第一处状态差异须落在 P-4 / P-5 / P-7 / 已处理摆动点的具体行上，分歧区间内的行只在起点已解释时计为已解释；
          链路行仍先核对生命周期（A-58）。离线：python3 tools/h4_protect_attr.py → 0 / 0、9/9
6  状态（2026-10-20，Audit Round 28 / 29）：**冻结为受限开发与回退基线**（验收方确认；覆盖工具 r8 修正方向字段与身份异常）。
          覆盖范围与保留限制见 docs/baselines/v2.54.md；XAUUSD MODEL 实时路径未覆盖，后续有自然样本时更新该项。
   运行状态（2026-10-19，Audit Round 27；验收方 v2.54r6 复核 2026-10-16）：重载、两轮跨版本归因通过；实时 vs 重建已覆盖的行全部一致，
          但按「实例 × 类别」记录，未覆盖的类别不写通过。实时类别 MODEL / LIQ / CTX / PROT 分别计数：
          `python3 tools/live_coverage.py <日志按日期>`（同一日志文件内相邻两次完整构建之间；证据 v2.54_live_coverage_*.txt）。
          10-14 .. 10-16 当日区间（MODEL / LIQ / CTX / PROT）：EURUSD 默认 1/2/2/2、EURUSD ATR 1/2/2/2、USDJPY 0/3/1/2、
          AUDUSD 2/4/1/0、XAUUSD 0/0/0/0，差异 0。跨休眠（A-60）只核对休眠前醒着的部分，两方向一致：
          XAUUSD LIQ 2 / CTX 1 / PROT 2、USDJPY MODEL 1 —— 单列，是否计入由验收方判定。
          缺：XAUUSD 当日区间全部类别（MODEL 连跨休眠也没有）、USDJPY 当日 MODEL、AUDUSD PROT。
          10-19 补测后（合计到 10-19）：EURUSD 两实例、AUDUSD 四类齐全；XAUUSD 当日区间只有 LIQ 2，MODEL 无任何样本，
          CTX / PROT 只有跨休眠；USDJPY MODEL 只有跨休眠与边界行（13:35 MSS，重建原样存在，按窗口不计入）。
          补测方法：五个 v2.54 图开机后各刷新一次；白天每隔一两小时、以及看到实时事件后过一根完整 M5，刷新一次；
          休眠前必须再刷新一次（10-14、10-15 的 6 条实时行就是因为休眠前没刷新而没进当日区间）；跨午夜提交两天日志。
          冻结判定按实际覆盖的类别写范围；EURUSD ATR 的 3 条 stale-BOS pending 保持人工核对状态。
   运行状态（2026-10-16，Audit Round 26）：第 4 项同窗口重载五实例全部 IDENTICAL（含 PROT），实时 vs 重建全部一致
          （XAUUSD v2.54 样本不足）；第 5 项两个同窗口样本共 2029 条差异全部可追溯。—— 下面是 10-15 的记录：
   运行状态（2026-10-15，Audit Round 25）：第 5 项四品种已完成（1074 条差异全部可追溯）；第 4 项实时 vs 重建 10-14 区间已完成
          （XAUUSD v2.54 缺不中断区间的事件样本）；同窗口重载缺 —— 终端「属性 → 确定」不改参数不重建。
          重载方法改为：图表右键「刷新 / Atualizar」两次（同一根 M5 内），以 Experts 页出现两行 HMI-BUILD-BEGIN 为准；
          不出现时改用显示参数 InpKZTextSize（不在参数摘要内）7 → 8 → 7 各确定一次
```

### v2.55 验收清单（BRI-08：CISD / MSS 首次有效收盘；基线 v2.54 受限基线）

```
0  编译 0 errors / 0 warnings（v2.55 开发版：验收方 2026-10-20 MetaEditor X64 0 / 0；r2 只改工具，MQL 相同）
1  版本：starting on v2.55；BEGIN ver=2.55；默认参数下 params=461F006E（无新输入）
2  新日志行（InpLogSignals = true；docs/02 BRI-08 修订稿 2 B8-5）：
          HMI-REF 每个 ARMED 每模型一行（CISD / MSS），与 HMI-ARM 同一 cycle、armed 相同；
          HMI-BRK 每次 CISD / MSS 确认一行，与 MODEL 行同 cycle、level、确认根；均带 live / inst / run / init
          CISD：state=OK 时 level = cand_level；NA_BROKEN 时 brk_bar ∈ [run_from 后一根, A]，brk_close 按 brk_mp 越过 cand_level
          MSS：c5diff 每条按 armed_mp 与检查根余量复核 o / n 两种判定；old_* 只读，与 v2.54 同窗口 MODEL 行一致
3  离线：python3 tools/bri08_sim.py → 372/372（29 场景 × 多空 × v2.54 / v2.55；每周期每模型一次；MSS 摆动点由 SwingDetect 生成）
          ReloadTest 日志用例 131/131（e01–e16：多空两向全部可归因；BRK / REF / c5diff / 其余行 / SHIFT / 窗口篡改须 UNEXPLAINED
          或 NOT JUDGED；B8 类别的重载与实时。r2 e17–e21：确认在本周期 ARMED 当根、在下一次 ARMED 之后、同周期同模型两行
          → UNEXPLAINED；缺 ARMED → PENDING；在下一次 ARMED 当根确认 → 允许）；python3 tools/live_coverage_tests.py → 16/16
4  同窗口重载（同一根 M5 内刷新两次）：MODEL / LIQ / CTX / PROT / B8 五类 IDENTICAL
5  实时 vs 重建：五类分别计数（`python3 tools/live_coverage.py --ver 2.55 <日志>`，B8 = REF / BRK），已覆盖行 0 差异；
          未覆盖的类别写「无样本」，不写通过
6  跨版本 v2.54 vs v2.55（同品种两张图，同一根 M5 内各重建一次）：`-Source <v2.54> -Versus <v2.55>`（BRI-08 模式）
          判据：other rows that differ 0；verdicts UNEXPLAINED 0、PENDING 0；每条差异归 B8-C5 / SLOW / SHIFT / NA 之一；
          r2 起两版每条 CISD / MSS MODEL 先过周期时序（n > A，不晚于下一次 ARMED）与每周期每模型一行
          窗口不同 → NOT JUDGED，不作通过
7  运行状态（2026-10-20，Audit Round 32）：第 0 项 0 / 0；第 1 项 ver=2.55、461F006E / A047970C；第 6 项两组同窗口样本（14:58、15:33）
          五对各 23 条全部可归因，其余行 0 差异（B8-C5 在真实窗口中为 0）；第 4 项 v2.55 五实例五类 IDENTICAL；
          第 5 项 v2.55 实时仅 35 分钟、无实时行 —— 待补
   运行状态（2026-10-26，Audit Round 34）：第 6 项三组同窗口样本（10-20 14:58、15:33，10-21 09:14）全部可归因；第 4 项三组 IDENTICAL；
          第 5 项五类各至少一个品种有当日区间样本、0 差异（USDCAD / USDCHF 的 MODEL 与 B8，EURUSD / AUDUSD 的 LIQ / CTX / PROT）；
          XAUUSD MODEL 无样本；B8-C5 真实窗口为 0（只有离线覆盖）
   运行状态（2026-10-26 下午，Audit Round 39）：第 5 项 XAUUSD 默认 MODEL 7 / B8 8（首个黄金实时 MODEL）、GBPUSD B8 2、USDCHF MODEL 1，
          全部 0 差异；合计日内 MODEL 12 / LIQ 31 / CTX 5 / PROT 8 / B8 16；B8-C5 仍 0
   验收结论（2026-10-26，Audit Round 35）：受限通过，v2.55r3 留档为开发与回退基线（docs/baselines/v2.55.md）。
          未覆盖：XAUUSD MODEL 实时路径、B8-C5 原生差异分支、GBPUSD 与黄金 ATR 日内样本；跨周末 USDCAD PROT 2 行 PENDING REVIEW
          （全日志 RESULT NOT PASSED，不改写）
```

### v2.56 验收清单（BRI-13 修订稿 2：三项合成趋势强度，只显示；基线 v2.55 受限基线）

```
0  编译 0 errors / 0 warnings（新文件 HMI_StrengthEngine.mqh；源文件全部 ASCII 或 UTF-8，面板中文由 \uXXXX 解码）
1  版本：starting on v2.56；BEGIN ver=2.56；默认参数 params=461F006E 不变；HMI-STR 的 def=STR1-N12K3-M3R1-W45.35.20-T35.65
2  新日志行（InpLogSignals = true；BRI-13 T-9）：
          HMI-STR   构建中 M5 窗口内每根 H4 一行、实时每根 H4 一行；ReloadTest 逐行复算 score / tier / 分项（失败即不通过）
          HMI-STR-HIST 每次构建一行（END 之前）：ok + nodir + nodata = bars，分箱和 = ok，与本构建 HMI-STR 行一致
          HMI-STR-WAIT 只在实时等待时出现，不比较
3  离线：python3 tools/strength_sim.py → 81/81（验收方三组对照、分项独立变化、封顶、35 / 65 未取整边界、数据不足、
          方向、窗口、Context 引擎当根、面板文字；多空镜像）；--replay EURUSD_H1.csv → 前缀一致、镜像 0 差异、分布记录
          ReloadTest 日志用例 160/160（s01–s28：STR 重载一致 / 缺行 / 分数、分项、方向、NODIR 字段篡改 / 直方图计数、缺失、to /
          同根两行 / def 改变 → 不可比较 / def 未知 / 边界行复算 / 实时一致、缺行、篡改、def 改变 / v2.55 → v2.56 加法一致、
          链路行改变、MODEL 改变、窗口不同、强度行失败、无强度行、旧版带强度行；r2 s26–s28：强度行晚于构建最后一根 M5 /
          早于第一根、直方图 to 越界 —— 验收方反例）
          python3 tools/live_coverage_tests.py → 22/22（+3：v2.56 STR 一致、分数改变、缺行）
4  同窗口重载（同一根 M5 内刷新两次）：MODEL / LIQ / CTX / PROT / B8 / STR 六类 IDENTICAL，STR 逐行复算全部通过
5  实时 vs 重建：STR 按 H4 收盘逐行全字段相同（ReloadTest -LiveVsBuild；python3 tools/live_coverage.py --ver 2.56）；
          0 行写「无样本」，不写通过
6  跨版本 v2.55 vs v2.56（同品种两张图，同一根 M5 内各重建一次）：-Source <v2.55> -Versus <v2.56>
          判据：「IDENTICAL apart from the strength rows」—— 除 HMI-STR / HMI-STR-HIST 外逐行相同（身份字段除外）；
          任何其他差异 UNEXPLAINED；窗口不同 NOT JUDGED
7  分布记录：ReloadTest -Str（各图最新构建的 HMI-STR-HIST，按参数摘要与 def 合并）—— 记录，不据此改阈值
8  面板截图：默认 COMPACT 的「强度 … /100」与下一行「数据截至 … H4 收盘」；FULL；暂不评级（区间或过渡）、样本不足或等待数据
          （可用刚挂图的第一屏）；FULL 的 H4 CONTEXT 行显示「BOS 计数」「结构诊断」；中文字符正常显示（不是方框），面板行数正常
```
   运行状态（2026-10-26，Audit Round 37）：第 0 项开发版 0 / 0（验收方，X64 Regular）；验收方复核 79/79、2/2、157/157、22/22、
          461F006E、独立三项算术 1292 根 0 差异；r2 修三处 P2（处理窗口校验、COMPACT 分数时间、RELOAD 即时等待），待重新编译与 MT5 运行
   运行状态（2026-10-26，Audit Round 38）：r2 编译 0 / 0（验收方）；第 3 项 160/160、79/79、22/22 复核通过；第 1 项 461F006E。
          第 4–8 项（重载六类、实时 vs 重建、v2.55 vs v2.56、-Str、截图）待 MT5 运行
   运行状态（2026-10-26 本地 15:41，Audit Round 40）：10 张 v2.56 挂图（ver=2.56、461F006E / A047970C 与配对的 v2.55 相同）；
          第 4 项同窗口重载 5 组（EURUSD 两实例、XAUUSD 两实例、AUDUSD）六类 IDENTICAL、STR 全部复算通过；
          第 6 项 5 对 v2.55 / v2.56「IDENTICAL apart from the strength rows」（XAUUSD 两对另列 REPLAY attempt= 实例元数据）；
          第 7 项 -Str 10 图记录；第 8 项 COMPACT 截图（USDCAD）；第 5 项实时 STR 尚无样本（挂图后未过 H4 收盘）；FULL 截图待补
          工具 r3（attempt= 元数据）：logtests 162/162
   r4（2026-10-26）：COMPACT 截图显示第一行在第 63 个字符截断（OBJ_LABEL 上限）—— 分数移到第二行与时间同行；需重新编译、
          第 8 项截图以 r4 为准。FULL 的 POI 行、CYCLE 行、LIQ WAITING 行及 TRANSITION 下 COMPACT 第一行在 v2.55 已超 63 字符
          （原有，显示阶段处理）
   r4 编译 0 / 0（用户 2026-10-26）；第 8 项 COMPACT（r4）与 FULL 截图已有，暂不评级（USDJPY 过渡）截图待补；第 5 项待 H4 收盘后
