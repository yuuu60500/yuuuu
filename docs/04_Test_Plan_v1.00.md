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
