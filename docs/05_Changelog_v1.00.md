# Changelog (Rule 74)

## v1.00 — Frozen Baseline

```
Version:  v1.00 (Specification Stage)
Date:     2026-09-21

Changed Functions:
  (none — 尚无代码)

Changed States:
  (none — 尚无代码)

Affected Modules:
  新建规格文档：
    README.md
    docs/01_Architecture_Spec_v1.00.md
    docs/02_Conflict_And_Business_Rule_Issues_v1.00.md
    docs/03_Module_Architecture_v1.00.md
    docs/04_Test_Plan_v1.00.md
    docs/05_Changelog_v1.00.md

Reason:
  Phase 1 — 按 Rule 63 输出 Architecture & Logic Specification；
  按 Rule 64 完成规则间冲突检查；
  按 Rule 65 输出 4 项 BUSINESS RULE ISSUE，均未擅自实施。

Trading Logic Changed:
  NO   —— 全部按现有业务规则字面定义，未新增过滤、未改变信号时序。

Compile Status:
  NOT COMPILE VERIFIED   （本阶段无代码，且环境无 MetaEditor）

Replay Status:
  NOT VERIFIED
```

---

## 版本规划 (Rule 74)

| 版本 | 含义 |
|------|------|
| `v1.00` | Frozen Baseline（当前） |
| `v1.01` | Bug Fix，不改业务逻辑 |
| `v1.10` | Minor Feature（例如新增诊断显示 BRI-04） |
| `v2.00` | Major Architecture / Business Logic Change（例如启用 BRI-01 / BRI-02） |

每次修改必须补一条完整记录：
`Version / Date / Changed Functions / Changed States / Affected Modules / Reason / Trading Logic Changed`。

---

## v1.00 — Spec Revision 2（裁决落地，Baseline 冻结前）

```
Version:  v1.00 (Specification Stage, revision 2)
Date:     2026-09-22

Changed Functions:
  (仍无代码) 新增计划函数：
    Phase5b_ArmedBarPA()
    PA_CheckEngulfingArmedBar() / PA_CheckRejectionArmedBar()
    BreakMargin() 改为三模式分派

Changed States:
  IdentificationCycle 新增 session_start_time（供 D-2 早腿约束使用）

Affected Modules:
  docs/01 §5.2 (D-3)、§9.5.1 (D-4)、§12.2 (D-2)、§13 P2 (D-4)、
          §17.2 Phase 5b (D-4)、附录 A/B (D-3/D-4/D-6)
  docs/02 Part D 裁决表 + BRI-01..04 状态更新 + CONF-01/03/04/07 结案
  docs/03 MarginMode enum、Phase5b 与 ARMED-bar PA 函数签名
  docs/04 MOB-03/03b、BPR-03b、PA-05/06/07、margin 模式压力用例

Reason:
  用户于 2026-09-22 签字批准 D-1 … D-7 全部裁决。

Trading Logic Changed:
  YES —— 三处，均已获明确批准：
    D-3  InpM5BlockLookbackFromTouch : 0 → 2
    D-4  PA ENGULFING / REJECTION 允许在 ARMED 当根确认（窄范围）
    D-2  BPR 早腿新增「≥ Session 起点」约束
  其余（D-1 / D-5 / D-6 默认 / D-7）不改变任何既有判定。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.00 — Implementation (Phase 3) + Audit Round 1

```
Version:  v1.00 (Implementation)
Date:     2026-09-22

Changed Functions:
  新建全部实现（约 2560 行）：
    H4M5_Identification.mq5 : OnInit / OnCalculate / OnDeinit
                              ProcessClosedM5Bar (Phase 0-7 含 Phase 5b)
                              H4ProcessBar / ResetEngine / BuildHistory / LogPhase7
    HMI_SwingEngine         : SwingDetect / SwingLastUnswept
    HMI_FVGEngine           : FvgDetect / ConnectionValid
    HMI_H4StructureEngine   : H4DetectBreak / H4ConsumeSwing
    HMI_H4ContextEngine     : H4ContextOnBar / CtxEnter / CtxDirection
    HMI_H4RangeEngine       : TRNewVersion / TRExtendOnSwing / LiqOnBar
    HMI_H4POIEngine         : POIOnBar / POIInvalidateOnBar / POITouchedBy
    HMI_M5BlockEngine       : SessionStart / SessionMaintain / M5BlocksOnFVG /
                              M5BlockInvalidate
    HMI_CycleManager        : Cycle_FreezeCISDReference / Cycle_FreezeMSSReference /
                              CycCreate / CycCloseActive / M5TouchArbitrate / ModelConfirm
    HMI_CISDEngine          : CISD_Check
    HMI_MSSEngine           : MSS_Check
    HMI_BPREngine           : BPR_Check / BPRLifecycle
    HMI_PriceActionEngine   : PA_Engulf / PA_Reject / PA_CheckBreakRetest +
                              ARMED-bar 入口（D-4）
    HMI_ObjectManager       : OM_ClaimInstance / OM_SyncAll / OM_Preview / OM_Trim
    HMI_AlertManager        : AlertFlush

Changed States:
  新增 M5Block.counter_dir（审计 A-01）
  新增 IdentificationCycle.logged_mask（Phase 7 CSV 日志去重）
  删除死字段 armed_drawn / 死变量 g_ctx_flipped_this_bar / g_last_bar0（审计 A-04）

Affected Modules:
  全部新建；docs/06 记录第一轮审计（A-01..A-10）

Reason:
  Phase 3 实现 + Rule 66 第一轮审计。

Trading Logic Changed:
  NO（相对已签字的 v1.00 spec revision 2；审计修复全部是显示 / 对象管理 / 死代码）

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.01 — Bug Fix（A-11 / A-05 / A-06），交易逻辑不变

```
Version:  v1.01
Date:     2026-09-22

Changed Functions:
  POIPush                 重写：逻辑窗口仍为 InpH4MaxPOIs，离开窗口的记录
                          降级为 POI_EXPIRED + out_of_window 而非删除；
                          物理淘汰只动已出窗记录，且永不动 Session 引用的那条
  POIReArmCheck           新增（A-06，默认关闭）
  SessionEndNow           新增 TIMEOUT 复触钩子（默认关闭）
  SessionStart            记录 session_count
  SessionMaintain         结束条件改为只认 POI_INVALID（Spec 5.1 字面）
  OM_Unregister           新增
  OM_DeleteOwner          新增：丢弃单个 owner 的图形而保留其记录（Spec 14.7）
  OM_SyncAll              POI 循环处理 out_of_window
  ProcessClosedM5BarPhase3 新增 POIReArmCheck 调用

Changed States:
  H4POI 新增 out_of_window / session_count / awaiting_leave
  MAX_POIS 16 -> 64（物理存储；逻辑窗口默认仍为 12）

Affected Modules:
  HMI_Defs / HMI_Params / HMI_H4POIEngine / HMI_M5BlockEngine /
  HMI_ObjectManager / H4M5_Identification.mq5

Reason:
  A-11：被挤出的 POI 记录被整条删除，导致图上僵尸矩形 + Session 悬空引用。
  A-05：上述悬空引用的直接后果。
  A-06：POI 复触做成默认关闭的开关，供后续 Replay 评估。

Trading Logic Changed:
  NO
  - A-11 修复的等价性证明见 docs/06（可触碰集合 / 失效路径 / Session 结束条件
    四项逐条一致）
  - A-06 的 InpPOIMaxSessions 默认 1，代码路径永不进入
  - A-05 的可观测行为刻意保持不变（未加 fail-safe，因为那会改变逻辑）

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED（新增 POI-06..POI-09 用例，其中 POI-07 就是 v1.00/v1.01 等价性回归）
```

---

## v1.10 — Minor Feature：样式全面参数化

```
Version:  v1.10
Date:     2026-09-22

Changed Functions:
  新增 HMI_Style.mqh          106 个样式 input + StyleZone / StyleText +
                              StylesInit() + POIStyleOf / BlockStyleOf /
                              BPRStyleOf / ModelStyleOf
  OM_Rect / OM_Text / OM_Level / OM_Panel
                              签名改为接收 StyleZone / StyleText，
                              不再接收裸 color + style，并统一应用 WIDTH
  OM_SyncAll / OM_Preview     全部调用点改为使用样式解析器
  OnInit                      新增 StylesInit() 调用（在任何绘图之前）

Changed States:
  无（样式不属于业务状态）

Affected Modules:
  HMI_Style.mqh（新建）/ HMI_Params.mqh（移出旧的颜色与字号）/
  HMI_ObjectManager.mqh / H4M5_Identification.mq5

Reason:
  用户要求每个显示元素可独立设置颜色 / 线型 / 线宽 / 字号。
  顺带修掉 A-13（ACTIVE 与 TOUCHED 在图上无法区分）。

Trading Logic Changed:
  NO
  样式层不被任何识别引擎引用；矩形几何、触碰判定、确认逻辑一行未动。
  可用 POI-07 等价性测试验证（CSV 信号日志应与 v1.01 逐行相同）。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.20 — Minor Feature：Kill Zone HIGH/LOW + 流动性默认打开

```
Version:  v1.20
Date:     2026-09-22

Changed Functions:
  新增 HMI_KillZone.mqh    47 个 input（4 个时段各自开关/命名/起止时分/
                           颜色/线型/线宽 + 通用参数）
                           KZInit / KZDayAnchor / KZContains / KZWindowEnd /
                           KZCollect（纯函数，只读已关闭 M5 序列）
  OM_SyncKillZones         新增：画 HIGH / LOW 两条线 + 可选标签，
                           并显式删除滚出范围的旧时段对象
  OM_KZDelete              新增
  OM_SyncAll               liquidity 循环重写：按侧限量 + 被扫即删线
  OM_Protected             KZ 与 LIQ 对象不参与通用裁剪（它们自管生命周期）
  OnInit                   新增 KZInit() 调用

Changed States:
  LiqPool 新增 vis 字段（A-15）
  绘图层新增 g_kzd_zone / g_kzd_anchor 追踪表（属于绘图层资产，非业务状态）

Affected Modules:
  HMI_KillZone.mqh（新建）/ HMI_Defs.mqh / HMI_Params.mqh /
  HMI_H4RangeEngine.mqh / HMI_ObjectManager.mqh / H4M5_Identification.mq5

Reason:
  用户要求：加 Kill Zone 时段标识（只要 HIGH/LOW，不要矩形）、每个时段线型颜色粗细
  可自定义、流动性默认打开。顺带修掉 A-15（被扫的流动性线永不删除）。

Trading Logic Changed:
  NO
  Kill Zone 不被 Phase 0-7 任何代码引用（见 D-8 的边界声明）；
  流动性在 v1.00 起就是 mark-only，本次只改显示默认值与数量上限。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.30 — Minor Feature：面板 ATR / ADR

```
Version:  v1.30
Date:     2026-09-22

Changed Functions:
  新增 HMI_Ranges.mqh   InpShowATR / InpShowADR / InpADRDays
                        RangesUpdate / RangesPips / RangesATRText / RangesADRText
  OM_SyncAll            调用 RangesUpdate()，面板改为使用 g_panel_line 滚动行号
                        （任一显示块关闭都不会在面板上留空行）

Changed States:
  无业务状态。新增绘图层变量 g_panel_line 与 ADR 缓存（g_adr / g_today_range 等）

Affected Modules:
  HMI_Ranges.mqh（新建）/ HMI_ObjectManager.mqh / HMI_Defs.mqh（版本号）/
  H4M5_Identification.mq5（版本号）

Reason:
  用户要求把 ATR 与 ADR 加到面板（不画线）。
  ATR 此前虽然已在内部逐根递推，但只在 MARGIN_ATR_FRAC 模式下被用到，且完全不可见；
  ADR 此前完全不存在（全库无任何 D1 逻辑）。

Trading Logic Changed:
  NO —— 见 D-9。HMI_Ranges.mqh 不被 Phase 0-7 引用；ATR 复用引擎已有的序列，
  不引入第二套可能与 margin 判定不一致的 ATR。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.31 — 面板瘦身（COMPACT 模式）

```
Version:  v1.31
Date:     2026-09-22

Changed Functions:
  OM_Panel            -> OM_PanelRow   改为接收显式 y 像素 + 支持四个角
  OM_DrawPanel        新增：先把行收集进数组，再按角落方向决定绘制顺序
  OM_PanelCycleLine   新增：只列「已成立」与「N/A」的模型，pending 不占字
  OM_SyncAll          面板段整体抽出，只剩一行 OM_DrawPanel()

Changed States:
  无。删除绘图层变量 g_panel_line（被行数组取代）

New / changed inputs:
  InpPanelMode      新增  PANEL_OFF / PANEL_COMPACT / PANEL_FULL，默认 COMPACT
  InpPanelCorner    新增  四个角可选，默认左上
  InpShowATR        默认 true -> false
  InpShowH4Context  删除（被 InpPanelMode 取代，否则会变成第二个死参数）

Reason:
  用户反馈 7 行面板太占图。COMPACT 只保留两样东西：
    1) Context 方向（决定当下是否可能出现任何东西）
    2) 当前 Cycle 里哪些模型已成立、哪些是 N/A
  其中 N/A 是唯一无法从图上读出的信息（没有冻结到参考 = 该模型本轮永不会出现），
  所以它最值得占像素。其余（标题行、POI/Gap 诊断行、SESSION 行）属于诊断，
  移入 PANEL_FULL。

Trading Logic Changed:
  NO —— 纯显示层。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED
```

---

## v1.32 — 面板按状态变色

```
Version:  v1.32
Date:     2026-09-22

Changed Functions:
  OM_PanelRow          新增 color 参数（不再统一用 TS_PANEL.clr）
  OM_DrawPanel         行数组旁增加并行的颜色数组
  CtxPanelColor        新增（HMI_Style.mqh）
  RangesADRUsedPct     新增（HMI_Ranges.mqh）：文字与颜色的唯一数据来源
  RangesADRColor       新增（HMI_Ranges.mqh）
  RangesADRText        改为复用 RangesADRUsedPct()

New inputs:
  InpPanelColorByContext  true         关掉即退回全面板单色
  InpPanelCtxBullColor    clrLimeGreen
  InpPanelCtxBearColor    clrTomato
  InpPanelCtxRangeColor   clrSilver    RANGE 与 TRANSITION 共用
  InpADRWarnPct           80.0
  InpADRExhaustPct        100.0
  InpADRWarnColor         clrOrange
  InpADRExhaustColor      clrRed

Reason:
  用户要求 Context 行按方向变色、ADR 行按消耗度变色。
  只做这两处 —— 变色在这两行能替代读字，其余行变色只是装饰。

  实现上把「百分比」抽成 RangesADRUsedPct()，让 [EXHAUSTED] 文字与颜色阈值
  共用同一个计算；否则两边各算一次，改了阈值就会出现「显示红色但没有
  EXHAUSTED 标记」这类自相矛盾。

Trading Logic Changed:
  NO —— 纯显示层。

Compile Status:
  NOT COMPILE VERIFIED
```

---

## v2.00 — Breaker 开关化，默认关闭

```
Version:  v2.00
Date:     2026-09-22

Changed Functions:
  M5BlocksOnFVG        新增两处 guard：
                         - 逆势 OB：关闭时直接 return，不再创建
                         - breaker 匹配循环：关闭时直接 return
  M5BlockInvalidate    breaker 候选生成加 guard
  LogPhase7            CSV 新增 anchor_type 列（OB / BREAKER）

Changed States:
  无新增字段。关闭时 g_brk[] 恒为空，counter_dir 恒为 false

New inputs:
  InpEnableBreaker = false

Reason:
  用户裁决 D-10。动机是简化审计面与编译面（A-09 仍未编译），
  并且 Breaker 在当前 Rule 11 约束下预计极少成立 ——
  瓶颈是「翻转方向的 FVG 必须与原 OB 区域 Touch/Overlap」，
  而价格击穿区域后继续位移产生的 FVG 通常落在区域上方，形成正空隙 → INVALID。

Trading Logic Changed:
  YES —— 默认行为改变，出厂状态不再满足 Rule 8 / Rule 11。
  已按 Rule 65 出具 BRI-05 并记录 D-10；规则原文保留未改写。
  InpEnableBreaker = true 即完整恢复。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  NOT VERIFIED（新增 BRK-00 与 POI-07b 用例）
```

---

## v2.01 — 打包修复：全部文件移入同一个文件夹

```
Version:  v2.01
Date:     2026-09-22

Changed Functions:
  无。唯一的代码改动是主文件第 19 行：
     #include <HMI/HMI_AlertManager.mqh>   ->   #include "HMI_AlertManager.mqh"

Changed States:
  无

Affected Modules:
  21 个 .mqh 从 MQL5/Include/HMI/ 移到 MQL5/Indicators/HMI/
  MQL5/Include/ 目录删除

Reason:
  用户第一次 F7 报 "file 'Include\HMI\HMI_AlertManager.mqh' not found"。
  尖括号 include 只在数据文件夹的 Include 下解析，所以安装必须精确地把文件拆到
  两个目录，任何一步错位都编译不过。第二个错误 "OnCalculate function not found"
  只是预处理在第 19 行中断后的连带结果，不是真的缺函数。

  21 个头文件之间本来就用引号互相引用（相对所在文件解析，与位置无关），
  所以只有主文件这一行需要改。改完之后安装 = 拖一个文件夹。

Trading Logic Changed:
  NO —— 未触碰任何逻辑，仅文件位置与一行 include 形式。

Compile Status:
  NOT COMPILE VERIFIED
  注意：上一次 F7 在第 19 行就中断，2800 行头文件一行都没被检查过，
  所以 "2 errors, 0 warnings" 完全不代表代码接近通过。
```

---

## v2.02 — 修复 A-16：CISD / MSS 引擎从未进入编译单元

```
Version:  v2.02
Date:     2026-09-22

Changed Functions:
  无。主文件 include 段从 1 行扩展为 5 行：
     HMI_AlertManager / HMI_CISDEngine / HMI_MSSEngine /
     HMI_BPREngine / HMI_PriceActionEngine

Changed States:
  无

Reason:
  第一次真实 F7 报 undeclared identifier 'CISD_Check' / 'MSS_Check'（共 8 个错误，
  其中 6 个是解析器连锁反应）。根因：主文件只 include AlertManager，
  靠传递性把其它模块拉进来；BPREngine 与 PriceActionEngine 碰巧被
  ObjectManager 拉进来了，CISDEngine 与 MSSEngine 没有。

  这是 docs/03「四个识别引擎互不 #include」原则的副作用 ——
  该原则正确（它在编译期保证 Rule 30 / 44），但它把 include 责任
  推给了调用方，而这一点当初没写进架构文档。现已补上。

Trading Logic Changed:
  NO —— 缺的是编译可见性，不是实现。CISD / MSS 的代码本身一行未动。

Compile Status:
  **PASS —— 2026-09-22 用户在 MetaEditor 实测 0 errors, 0 warnings。**
  这是本项目第一次达成 Rule 70 的目标，A-09 就此关闭。
  达成路径：v2.01 修打包（两目录 -> 单目录）、v2.02 修 A-16（缺 include）。

Replay Status:
  NOT VERIFIED —— 编译通过只证明语法与类型正确，
  不证明任何一条业务规则被正确实现。docs/04 全部用例仍未执行。
```

---

## v2.03 — 修复 A-17：面板文字被 MT5 截断在 63 字符

```
Version:  v2.03
Date:     2026-09-22

Changed Functions:
  PanelPush        新增：超过 58 字符按词边界折行
  OM_DrawPanel     全部行改为经 PanelPush 写入（含 ATR / ADR 行）

Changed States:
  无

Reason:
  首次实盘挂载（USDJPY M5）发现 Cycle 行被截断在 "PA REJE"。
  同一面板上 57 字符的 ADR 行与 49 字符的 Context 行完整显示，
  定位出 MT5 的 OBJPROP_TEXT 存在 63 字符上限。
  PANEL_FULL 的诊断行（约 68 字符）同样受影响。

  静态阅读无法发现这一条 —— 它属于平台行为，只有真跑才看得见。

Trading Logic Changed:
  NO —— 纯显示层。

Compile Status:
  PASS 于 v2.02；本次改动尚未编译验证。

Replay Status:
  NOT VERIFIED
```

---

## v2.04 — 撤销 v2.03（A-17 系误判）

```
Version:  v2.04
Date:     2026-09-22

Changed Functions:
  PanelPush        删除
  OM_DrawPanel     恢复为直接写入行数组（等同 v2.02）

Changed States:
  无

Reason:
  A-17 的前提不成立：面板文字**从未**被截断，是截图没把右侧截进去。
  用户直接确认。既然 63 字符上限这个前提是错的，
  折行反而会把本来一行显示得下的 Cycle 行拆成两行，更占地方。

  代码回到 v2.02 状态。docs/06 中 A-17 改为 WITHDRAWN 并保留，
  作为「截图不构成证据」的反面记录（Rule 67）。

  注意：v2.03 提交里**关于 Round 3 目视验证的表格仍然有效**
  （break margin / ADR / Kill Zone / 完整名称 / ARMED / Level 线 / Cycle 隔离），
  那部分不撤销。

Trading Logic Changed:
  NO

Compile Status:
  PASS 于 v2.02；v2.04 与其等价，但仍需你重新编译确认。
```

---

## v2.10 — Minor Feature：M5 层按图表周期自动隐藏

```
Version:  v2.10
Date:     2026-09-22

Changed Functions:
  M5LayerOn / M5LayerMask   新增（HMI_Style.mqh）
  OM_Rect / OM_Text / OM_Level
                            新增可选参数 tf_mask，写入 OBJPROP_TIMEFRAMES
                            默认 OBJ_ALL_PERIODS，行为不变
  OM_SyncAll / OM_Preview   M5 层的绘制点传入 M5LayerMask()

New input:
  InpM5Layer = M5LAYER_UPTO_M15    （默认值改变了显示行为）
     M5LAYER_OFF        完全不画
     M5LAYER_M5_ONLY    只在 M5 图上显示
     M5LAYER_UPTO_M15   M1 / M5 / M15 显示   ← 默认
     M5LAYER_ALWAYS     所有周期（v2.04 及之前的行为）

属于 M5 层的对象：
  M5 Block 矩形 / M5 OB ARMED 标签 / 六个模型标记 /
  CISD Level 与 MSS Break Level 线 / BPR 矩形 / PENDING TOUCH 预览

不受影响、任何周期都显示：
  H4 POI / Trading Range / Liquidity / Kill Zone HIGH-LOW / 面板

Reason:
  用户把指标挂到 H4 图上，M5 标记全部压成一团不可读
  （H4 每根 4 小时宽，数天的 M5 标记挤进几十根 K 线）。
  用 MT5 原生的 OBJPROP_TIMEFRAMES 解决，比再加一堆开关好：
  同一个实例挂在 H4 上自动只剩 POI + Kill Zone + 面板，
  切回 M5 细节层自动回来，不需要手动切换任何开关。

Trading Logic Changed:
  NO —— 纯显示层。对象是否绘制不影响任何内部状态或标记记录。

Compile Status:
  PASS 于 v2.02；v2.10 尚未编译验证。
```

---

## v2.11 — Trading Range 标签 + 修复 A-18 / A-19

```
Version:  v2.11
Date:     2026-09-22

Changed Functions:
  OM_SyncAll（trading range 段）  重写：版本切换时退休旧对象 + 绘制两个标签
  ResetEngine                     重置 g_tr_drawn_id

New inputs:
  InpTRangeShowLabel  = true
  InpTRangeTextColor  = clrSilver
  InpTRangeTextSize   = 7
  InpTRangeColor      默认由 clrSlateGray 改为 clrSilver（原色在深色背景上几乎不可见）

  说明：线的颜色 / 线型 / 线宽本来就有
  （InpTRangeColor / InpTRangeStyle / InpTRangeWidth，v1.10 起），
  本次新增的是**标签**及其文字样式。

标签文字：H4 RANGE HIGH / H4 RANGE LOW，画在右边缘，
          与 Kill Zone 的 "<NAME> HIGH / LOW" 命名保持一致。

修复：
  A-18  版本化 Trading Range 的旧版本矩形从不删除（与 A-15 同类）
  A-19  **我在 v2.04 撤销折行时误删了 Kill Zone 的四行声明，
        导致 v2.04 与 v2.10 无法编译。** 已恢复。

Trading Logic Changed:
  NO

Compile Status:
  **PASS —— 2026-09-22 用户实测 0 errors, 0 warnings（2856 ms）。**
  编译清单中 HMI_CISDEngine.mqh 与 HMI_MSSEngine.mqh 均在列，
  同时复核了 A-16 的修复确实生效。
```

---

## v2.12 — 构建标记 + Reload 测试脚本

```
Version:  v2.12
Date:     2026-09-23

Changed Functions:
  BuildHistory   在历史重建前后写 HMI-BUILD-BEGIN / HMI-BUILD-END
                 （仅当 InpLogSignals = true）
  LogPhase7      计数 g_log_count

New files:
  tools/ReloadTest.ps1   按标记切分日志、剥掉 MT5 时间戳前缀、比对最后两个 block

Reason:
  做 Reload 一致性测试时有三个坑，全部由标记解决：
   1. 日志是追加写的，两次运行混在同一个文件里 —— BEGIN/END 界定边界
   2. MT5 的时间戳前缀每次不同 —— 脚本按 'HMI-BUILD,' 切开只留载荷
   3. 若期间跨了新的 M5 K 线，历史窗口会整体前移一根，最老边缘的差异
      是合理的 —— BEGIN 的 from=/to= 直接暴露这件事，不必猜

Trading Logic Changed:
  NO —— 只增加日志输出，且全部在 InpLogSignals 之后。

Compile Status:
  NOT COMPILE VERIFIED（v2.11 PASS，本版改动待编译）
```

---

## v2.13 — Reload 脚本按图表分组 + OnInit 打印版本

```
Version:  v2.13
Date:     2026-09-23

Changed Functions:
  OnInit         增加一行 PrintFormat：版本 / 品种 / 周期 / instance tag

Changed Files:
  tools/ReloadTest.ps1   解析 MT5 的来源标签 (SYMBOL,TF)，按图表分组，
                         列出找到的所有来源，比对前必须用 -Source 指定一个

Reason:
  日志里同时有四个实例在写（USDCAD H4 / USDCAD M5 / USDJPY H1 / USDJPY H4），
  build block 互相交错。旧脚本只按 HMI-BUILD 过滤，会拿 USDCAD 的 block 去比
  USDJPY 的 block，报出来的差异毫无意义。
  同时日志此前无法分辨跑的是哪个版本 —— 一天里发了好几版，这是必须的。

Trading Logic Changed:
  NO —— 只增加日志与外部脚本。

Compile Status:
  NOT COMPILE VERIFIED
```

---

## v2.14 — Reload 一致性 PASS + 新增 LIVE vs BUILD 模式

```
Version:  v2.14
Date:     2026-09-23

Changed Functions:
  (none — 指标代码仅版本号)

Changed Files:
  tools/ReloadTest.ps1              新增 -LiveVsBuild
  docs/04_Test_Plan_v1.00.md        记录 Reload PASS；写明 Reload 测不出未来函数
  docs/06_Audit_Round1_v1.00.md     Rule 73 验收表更新

Reason:
  USDJPY v2.13：最后两次 M5 重建 143 行逐字节相同 —— 重绘测试 PASS。
  附带证据：M2 / M5 / M15 / M30 共 14 次重建在同一窗口上都是 143 行，
  直接印证 §15.4「引擎显式读 M5/H4，不依赖图表周期」。
  但 Reload **看不见**未来函数：会偷看未来的实现每次重建都偷看同一批未来
  K 线，自洽得很。因此 Future Leak 一栏保持 NOT VERIFIED，不借这次结果升级；
  真正能证伪它的是 -LiveVsBuild：实时行是逐根、只有过去时发出的。

Trading Logic Changed:
  NO

Compile Status:
  NOT COMPILE VERIFIED
```

---

## v2.20 — Rule 6 否决侧可对账（POI-02b）

```
Version:  v2.20
Date:     2026-09-23

Changed Functions:
  ConnectionGapPts()   新增 —— 从 ConnectionValid() 中抽出的「空隙点数」唯一算法
  ConnectionValid()    改为调用 ConnectionGapPts()，行为完全不变
  POIOnBar()           当一根 H4 FVG 最终没有产出 POI 时，把它检查过、
                       但因空隙被否决的每个 OB 候选连同实测 gap_pts 打印为
                       HMI-REJECT 行（仅当 InpLogSignals = true）

Changed States:
  (none)

Affected Modules:
  MQL5/Indicators/HMI/HMI_FVGEngine.mqh
  MQL5/Indicators/HMI/HMI_H4POIEngine.mqh
  tools/ReloadTest.ps1              新增 -Rejects
  docs/04_Test_Plan_v1.00.md        新增 POI-02b 否决侧测试流程；
                                    原「POI-01 / POI-02 PASS」改称 POI-02a（接受侧），
                                    因为那条记录只证明了接受侧
  README.md                         版本号

Reason:
  POI-02a 证明的是「连接合法 → 建 POI」。Rule 6 的另一半「连接不合法 → 不建 POI」
  在图表上表现为**什么都没有**，无法用观察证明 —— 可能是规则起了作用，
  也可能那段行情根本没有候选 OB。此前只有面板上的 REJECTED-BY-GAP 计数器，
  计数器无法与数据窗口对账。现在每个被否决的组合都带着实测点数落到日志里。
  抽出 ConnectionGapPts() 是为了让「判定」与「日志」共用同一个算法 ——
  否则两者可能对同一组形态各说各话（与此前 RangesADRUsedPct 同一个教训）。

Trading Logic Changed:
  NO —— 新增的全是 InpLogSignals 之后的打印；ConnectionValid() 的重构
        是行为等价的提取，未改任何阈值、过滤或信号时序（Rule 68/69）。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-23，2886 ms，AVX2 + FMA3）

Replay Status:
  POI-02b   待执行（流程见 docs/04）
```

---

## v2.21 — 修复 A-20 / A-21：LIVE vs BUILD 的比对键与跨天日志

```
Version:  v2.21
Date:     2026-09-23

Changed Functions:
  (none — 指标源码只改版本号字符串)

Changed Files:
  tools/ReloadTest.ps1              -LiveVsBuild 改为按事件比对，剔除
                                    cycle_id / block_id 两列（A-20）；
                                    Reload 比对在整行不等时追加一次
                                    「剔除序号」复核，区分重新编号与真重绘；
                                    新增 -Days N，合并最近 N 个日志文件（A-21）
  docs/04_Test_Plan_v1.00.md        写明比对键与跨天注意事项
  docs/06_Audit_Round1_v1.00.md     新增 Audit Round 5：A-20、A-21

Reason:
  A-20：日志行第 4、5 列是 g_next_id 自增序号，每次 init 重置为 1；
        SeriesAppend() 只追加不裁剪，实时会话的窗口比重载后的窗口更靠前，
        最老区间里分配过的 id 全部消失，之后 id 整体前移。
        逐字节比对整行会把「重新编号」误报成未来函数 —— 即将开始的四品种
        跨天挂机必然踩中。
  A-21：MT5 每天新开一个日志文件，脚本只读最新一个，跨天样本被静默截断。

  两条都是**测试工具**的缺陷，不是指标的缺陷。指标的 id 只是簿记且出现在
  图形对象名里，为迁就脚本去改它属于 Rule 68/69 禁止的顺手重构 ——
  缺陷在比对方法，就在比对方法上修。

Trading Logic Changed:
  NO —— 指标源码未改动任何逻辑。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-23，2886 ms，AVX2 + FMA3）

Replay Status:
  POI-02b       待执行
  Future Leak   待执行（四品种 Live 测试进行中）
```

---

## v2.22 — 修复 A-22 / A-23：脚本自己找日志目录，-Source 变可选

```
Version:  v2.22
Date:     2026-09-23

Changed Functions:
  (none — 指标源码只改版本号字符串)

Changed Files:
  tools/ReloadTest.ps1   新增 Find-LogDir()：当前目录 →
                         %APPDATA%\MetaQuotes\Terminal\*\MQL5\Logs 中
                         .log 最新的那个；另给 -LogDir 手动覆盖（A-22）
                         -Source 改为可选，不给则遍历日志里的全部图表；
                         给了但不在列表里则明确报错（A-23）
                         三个输出文件改为写回日志目录并按品种命名
  docs/04_Test_Plan_v1.00.md     更新调用方式
  docs/06_Audit_Round1_v1.00.md  新增 A-22、A-23

Reason:
  用户在 C:\Users\<name> 直接跑脚本，得到 CommandNotFoundException。
  这是同一类坑的第二次：第一次是把脚本放进了 Terminal\<ID>\logs
  而不是 Terminal\<ID>\MQL5\Logs。一个测试工具要求用户先手工找到
  一个哈希命名的目录、而同一终端下还有两个都叫 Logs 的目录 ——
  这个前提本身就是缺陷，应该由脚本自己解决。
  同时 -Source 手写品种名在多品种测试里很容易因券商后缀
  （EURUSD.a / EURUSDm / EURUSD#）静默匹配不到，看起来像「没有样本」。

Trading Logic Changed:
  NO —— 指标源码未改动任何逻辑。

Compile Status:
  PASS — 0 errors / 0 warnings（v2.21 实测，2026-09-23；本版指标源码
         仅版本号字符串变化）

Replay Status:
  POI-02b       待执行
  Future Leak   待执行（四品种 Live 测试进行中）
```

---

## 测试记录 —— POI-02b PASS（无代码改动）

```
Version:  v2.22（未改动）
Date:     2026-09-23

Changed Functions:
  (none)

Affected Modules:
  docs/04_Test_Plan_v1.00.md     POI-02b 由「待执行」改为 PASS，附完整追溯
  docs/06_Audit_Round1_v1.00.md  Rule 73 验收表 H4 POI 一栏更新
  README.md                      Phase 6 状态

Reason:
  v2.20 加的 HMI-REJECT 诊断在四品种上取得 31 条样本。
  取 AUDUSD 2026.09.03 一条完整追溯：FVG 三根原始 OHLC、OB 的反方向性与
  High/Low、CONF-14 的回溯顺序、Rule 6 的 14 点空隙，全部与日志一致；
  对象列表确认 09.03 00:00 处无 POI 矩形，且已排除「超上限删图形」的误判
  （InpH4MaxPOIs = 12，实际仅 3 个 POI，淘汰分支从未执行）。

Trading Logic Changed:
  NO —— 本次只写文档。
```

---

## v2.30 — Minor Feature：失效 POI 可隐藏

```
Version:  v2.30
Date:     2026-09-24

Changed Functions:
  OM_SyncAll()   H4 POI 绘制段增加一个提前分支：
                 dead（INVALIDATED / EXPIRED）且 InpShowDeadH4POI = false 时，
                 删除该 POI 已有的矩形与标签并标记 vis = -2

Changed States:
  (none) —— 只动 vis 这个纯绘图字段；
            state / out_of_window / 去重 / 日志一律不变（AX-6：状态 ≠ 绘图）

New Input:
  InpShowDeadH4POI = true   （默认保持 v1.00 以来的行为）

Affected Modules:
  MQL5/Indicators/HMI/HMI_Params.mqh
  MQL5/Indicators/HMI/HMI_ObjectManager.mqh

Reason:
  用户反馈图上失效 POI 堆积、影响阅读。POI-04 规定失效后「样式改变、矩形不
  保留」——这是有意的设计（记录比价位活得久），所以默认值不变，只给一个开关。

  实现上必须**删除**而不是**跳过**：跳过只会让最后一次画出的矩形永远留在图上，
  这正是 A-15（已扫流动性线不删）与 A-18（旧版本 Trading Range 不删）的同一个
  坑。因此走 OM_DeleteOwner 并置 vis = -2，与 out_of_window 分支同一套约定。

Trading Logic Changed:
  NO —— 纯显示。不改任何阈值、过滤、信号时序；同一份 CSV 日志在开关两种取值
        下逐行相同（Rule 68/69）。

Compile Status:
  NOT COMPILE VERIFIED   （v2.21/2.22 为最后一次实测 PASS；本版待 F7）

Replay Status:
  不影响已通过项；建议顺带跑一次 POI-04 确认「开关 = true 时行为与此前一致」
```

---

## v2.31 — 修复 A-25：MESSY 的置位条件回到规格

```
Version:  v2.31
Date:     2026-09-24

Changed Functions:
  H4ContextOnBar()   CTX_BULLISH / CTX_BEARISH 的 CHOCH 分支：删去 g_ctx_messy = true
                     CTX_TRANSITION 的失败分支：新增 g_ctx_messy = true

Changed States:
  g_ctx_messy 的**置位时机**改变。该变量不参与任何判定
  （全仓只被 HMI_ObjectManager.mqh:360,376 两行面板文字读取）。

Affected Modules:
  MQL5/Indicators/HMI/HMI_H4ContextEngine.mqh

Reason:
  规格 docs/01 第 202-204 行：
      MESSY : 出现过至少一次**失败的 TRANSITION**
  实现却写在「每一次 CHOCH」上，而真正代表失败 TRANSITION 的分支
  （brk != g_ctx_pending，原趋势恢复）完全没碰这个变量。
  CHOCH 之后 TRANSITION 可能成功 —— 那是正常的趋势反转，不是「乱」，
  规格没要求标记它。

  按 Rule 65，规格本身就是业务规则，把实现改回规格属 bugfix，
  不构成规则变更，因此不需要另行裁决。

Trading Logic Changed:
  NO —— g_ctx_messy 不被任何引擎读取，只影响面板那一个词。
        信号、时序、日志完全不变。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  不影响任何已通过项（CSV 日志逐行不变）
```

---

## v2.32 — 裁决 BRI-06：MESSY 按 Context 腿复位

```
Version:  v2.32
Date:     2026-09-24

Changed Functions:
  CtxEnter()   新增 g_ctx_messy = false

Changed States:
  g_ctx_messy 的**生命周期**：由「只在 OnInit 复位」改为
  「每次建立新 Context 腿时复位」。不参与任何判定。

Affected Modules:
  MQL5/Indicators/HMI/HMI_H4ContextEngine.mqh

Reason:
  规格只写「出现过至少一次失败的 TRANSITION」，未写作用范围（BRI-06）。
  已向用户提出两个选项，用户答 No preference 并授权裁决，采用「每条腿独立」：
    - 与并列的 strength 一致（CtxEnter 时重置为 1），两字段描述同一段结构
    - 否则 500 根 H4 里必然出现过失败 TRANSITION，字段恒为真、不承载信息
  语义：这条 Context 腿是否从一次失败的 TRANSITION 中诞生。

  顺序要点：TRANSITION 失败分支自身调用 CtxEnter，所以 v2.31 加的置位
  必须排在 CtxEnter 之后 —— 已确认（HMI_H4ContextEngine.mqh:98-101）。

Trading Logic Changed:
  NO —— g_ctx_messy 全仓只被面板两行文字读取，不被任何引擎读取。

Compile Status:
  NOT COMPILE VERIFIED

Replay Status:
  不影响任何已通过项（CSV 日志逐行不变）
```

---

## v2.33 — 新增 HMI-CTX 结构诊断日志

```
Version:  v2.33
Date:     2026-09-24

Changed Functions:
  CtxLog()           新增。纯输出，不被任何引擎读取
  H4ContextOnBar()   各分支记录一个诊断标签 kind，函数末尾统一输出一行；
                     TIMEOUT 分支单独输出。控制流未改动

Changed States:
  (none) —— 新增的 kind / vdir 是函数内局部变量

Affected Modules:
  MQL5/Indicators/HMI/HMI_H4ContextEngine.mqh
  tools/ReloadTest.ps1              新增 -Ctx：事件计数 + 强度分位 + CSV 导出
  docs/04_Test_Plan_v1.00.md        记录行格式与用途

Reason:
  面板上的 `str N` 与 `MESSY` 此前无法验证也无法比较 —— Context 这条链
  没有任何落到日志或图表上的输出。用户希望强度能以「一目了然」的方式呈现，
  而任何分档阈值若由我拟定就是凭空捏造；要按数据定，先得有数据。

  同时它补上了 A-25 / BRI-06 的验收手段：TRANS_FAIL 行的 messy 应为 1，
  其后 BOS 行的 str 应从 1 重新起算。

  前缀刻意避开 HMI-BUILD / HMI-LIVE：重绘比对脚本按 `HMI-BUILD,` 切分，
  共用前缀会让诊断行被计入标记行，污染已通过的行数比对。

Trading Logic Changed:
  NO —— 全部在 InpLogSignals 之后，且不改任何控制流、阈值或状态字段。
        CSV 信号日志逐行不变。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-24，3138 ms，AVX2 + FMA3；v2.40 构建，涵盖 v2.34–v2.40）

Replay Status:
  不影响任何已通过项
```

---

## v2.36 — 阶段 0：数据一致性与对象登记前置修复

```
Version:  v2.36
Date:     2026-09-24

Changed Functions:
  OM_Register()      按名查重后再登记（需求书 §9.1）
  SeriesAppend()     新增返回码 SA_RELOAD / SA_NOT_READY / SA_NONE；
                     「终端尚未交付」不再与「没有新 K 线」共用 0（A-30）；
                     重新读取最后一根已知 K 线并比对 OHLC，
                     发现被就地修正则要求重建（A-32）；
                     部分交付（got < want）一律不追加，下一 tick 重试
  OnCalculate()      prev_calculated == 0 触发重建（需求书 §9.3）；
                     H4 返回 SA_NOT_READY 时**不推进 M5**

Changed States:
  (none) —— 状态字段与阈值均未改动

Affected Modules:
  MQL5/Indicators/HMI/HMI_ObjectManager.mqh
  MQL5/Indicators/HMI/HMI_Series.mqh
  MQL5/Indicators/HMI/H4M5_Identification.mq5

Reason:
  工程师需求书 §9 的前置修复，本版完成剩余三项
  （§9.1 登记去重、§9.2 跨周期同步、§9.3 历史修正重建）。
  §9.4 参数校验已于 v2.35 完成，§9.5 脚本已于 v2.34 完成。

  A-30 的关键在于：H4 滞后时 SeriesAppend 旧实现返回 0，与「没有新 K 线」
  无法区分，于是 M5 照常推进、用的却是尚未到达那根 H4 的旧 Context，
  且这些 M5 永不重算 —— 实时与重建必然分叉，正是 Rule 51 要防的情形。
  现在 H4 未就绪时直接等下一 tick：M5 K 线不会丢，晚一点没有代价。

Trading Logic Changed:
  NO —— 未改动任何阈值、过滤或信号时序。
  但**实时输出的时机**会变：H4 未就绪时本 tick 不再处理 M5，
  改为下一 tick 处理。产出的标记内容不变，这正是 Rule 51 的要求。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-24，3138 ms，AVX2 + FMA3；v2.40 构建，涵盖 v2.34–v2.40）

Replay Status:
  四品种重绘基线（156 / 199 / 52 / 143）需重跑确认未受影响 —— 这是本版的验收条件
```

---

## v2.38 — Phase 0b：已有 Session 生命周期与资格检查（A-29 / BRI-07(b)）

```
Version:  v2.38
Date:     2026-09-24

Changed Functions:
  ProcessClosedM5Bar()  新增 Phase 0b（紧随 H4 同步、先于 Phase 1），
                        SessionMaintain() 从 Phase 3 移至此处
  SessionMaintain()     context 判定拆成两条：DIR_NONE → SE_CONTEXT_NEUTRAL，
                        方向不符 → SE_CONTEXT_FLIP

Changed States:
  SessionEnd 枚举**追加** SE_CONTEXT_NEUTRAL（追加在末尾，既有值编号不变）

Affected Modules:
  MQL5/Indicators/HMI/H4M5_Identification.mq5
  MQL5/Indicators/HMI/HMI_M5BlockEngine.mqh
  MQL5/Indicators/HMI/HMI_Defs.mqh
  docs/01_Architecture_Spec_v1.00.md   §17.2 冻结相位表新增 Phase 0b

Reason:
  用户 2026-09-24 签字的 Phase 0b 规格。
  旧守卫 `CtxDirection() != DIR_NONE && CtxDirection() != g_sess.dir`
  在 RANGE / TRANSITION 下第一半恒为假，守卫整体失效（A-29）。

Trading Logic Changed:
  **YES —— 仅限 RANGE / TRANSITION 情形。**
  逐条对照旧代码：
    · POI 失效 / 反向翻转 / 超时：旧代码在 Phase 3 结束 Session 时，
      SessionExpireOpenBlocks() 已把同根 Phase 1 新建的 block 过期，
      ARMED 在其后的 Phase 5 —— 故**标记输出不变**，仅不再「先建后删」
    · RANGE / TRANSITION：旧守卫从不触发，Session 一直存活并可 ARMED ——
      **本版起在进入该状态的那一根即结束**，这是唯一的信号变化

  图形上一处可见差异：超时 / 失效那一根，原本会先被 Phase 2 判为 INVALID
  的 ACTIVE block，现在在 0b 就被 EXPIRED，Phase 2 跳过它。两者都是死亡样式。

  已核对不会泄漏：BrkCandPush 仅在 g_sess.active && session_id 匹配时触发，
  0b 结束后同根 Phase 2 不会再生出 breaker 候选。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-24，3138 ms，AVX2 + FMA3；v2.40 构建，涵盖 v2.34–v2.40）

Replay Status:
  四品种基线**预期会变**（RANGE / TRANSITION 期间的周期消失）。
  验收应检查：消失的每一条标记，其 ARMED 时刻 H4 context 必为 RANGE / TRANSITION
```

---

## v2.39 — BRI-07(a)：新 Session 只接受与当前 H4 同向的 POI

```
Version:  v2.39
Date:     2026-09-24

Changed Functions:
  POITouchedBy()   CtxDirection() == DIR_NONE 时直接返回 -1；
                   循环内跳过方向与当前 H4 不一致的 POI

Changed States:
  (none)

Reason:
  工程师规则决策补充 §5（用户转交，「冲突时以本补充为准」）：
    H4 RANGE / TRANSITION → 禁止新 session
    H4 反向趋势           → 只允许新方向
    禁止时不得把 POI 标记为已触碰、不得消耗 session 配额
  与 v2.38 一起关闭 A-29。

  过滤放在搜索循环**内部**而非外部：POITouchedBy 返回同根最新被触碰的 POI，
  守卫若放在外面，一个不合格的新 POI 会遮住同根被触碰的合格旧 POI。
  被过滤的 POI 保持 POI_ACTIVE、session_count 不变。

Trading Logic Changed:
  **YES** —— RANGE / TRANSITION 期间及反向趋势中触碰旧方向 POI，
  不再开启 Session，因而不再产生对应的 block / ARMED / 标记。

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-24，3138 ms，AVX2 + FMA3；v2.40 构建，涵盖 v2.34–v2.40）

Replay Status:
  与 v2.38 合并验收：四品种基线预期变化，消失的每一条标记，
  其触碰时刻 H4 context 必为 RANGE / TRANSITION 或与 POI 反向
```

---

## v2.40 — 签字边界 1–3 落地：Phase 5 复查 + 时序与可见性确认

```
Version:  v2.40
Date:     2026-09-24

边界 1  新 Session 必须检查方向
  Phase 3：v2.39 已满足（POITouchedBy 循环内过滤，先检查后改状态）
  Phase 5：**本版新增** M5TouchArbitrate 复查
           block.session_id == g_sess.id  且  CtxDirection() == g_sess.dir
           由这两项拦下时输出 HMI-GUARD 行（InpLogSignals 之后）

边界 2  新 Session 不追溯本根 FVG —— **现有代码已满足，未改动**
  证据：M5BlocksOnFVG 全仓唯一调用点在 Phase 1（H4M5_Identification.mq5:117），
        只接收本根 FvgDetect 的结果；Phase 1 时 Session 尚未建立，
        首行 `if(!g_sess.active ...) return;` 直接返回。
        其余遍历 g_m5fvg 的只有 BPR 引擎，产出的是 BPR 区而非 block。
        InpM5BlockLookbackFromTouch 仅出现在 OB 回溯下限的计算中。

边界 3  不改 H4 可见性 —— **现有代码已满足，未改动**
  证据：H4VisibleTo(h4_open, m5_open) = h4_open + 4h <= m5_open
        Phase 0b 只读 g_ctx / g_poi，不直接访问 H4 序列。

Changed Functions:
  M5TouchArbitrate()   armable 追加 session_id 与当前方向复查

Changed States:
  (none)

Trading Logic Changed:
  **预期 NO。** Phase 0b 已结束不合格 Session，SessionExpireOpenBlocks
  已过期旧 Session 的 block，本复查按推理不应成为拦截项。
  若日志出现 HMI-GUARD，说明存在绕过这两处的路径 —— 那是需要追查的缺陷，
  不是复查在正常工作。

验收要点（签字版）:
  · 不合格 Session 在本根 Phase 1 不创建 block   —— 0b 先结束，M5BlocksOnFVG 首行返回
  · Phase 2 不新增 breaker 候选                   —— BrkCandPush 需 g_sess.active 且 id 匹配
  · Phase 5 不新 ARMED                            —— armable 需 g_sess.active + 本版复查
  · 已有 ARMED cycle 照常                         —— Phase 4 针对 g_active_cyc，不看 Session

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-24，3138 ms，AVX2 + FMA3；v2.40 构建，涵盖 v2.34–v2.40）
```

---

## v2.41 — A-37 标记链诊断日志（仅日志）

```
Version:  v2.41
Date:     2026-09-30
签字:     用户 2026-09-30「好」（A-37 选项 b）

New Log Lines（全部受 InpLogSignals 控制，任何引擎都不读取）:
  HMI-POI,<sym>,NEW,id=,dir=,lo=,hi=,origin=,bar=<confirm>
  HMI-POI,<sym>,OUT,id=,dir=,was=<离窗前状态>,bar=      被挤出 InpH4MaxPOIs 窗口
  HMI-POI,<sym>,INVALID,id=,dir=,was=,bar=               H4 收盘击穿
  HMI-POI,<sym>,EXPIRED,id=,dir=,was=ACTIVE,bar=          超过 InpH4POIMaxAgeBars
  HMI-SESS,<sym>,START,id=,poi=,dir=,bar=                 POI 被触碰、Session 开始
  HMI-SESS,<sym>,END,id=,poi=,dir=,reason=,bar=           POI_INVALID / CONTEXT_FLIP /
                                                          CONTEXT_NEUTRAL / TIMEOUT / NEW_SESSION
  HMI-BLK,<sym>,NEW,id=,sess=,dir=,type=OB|BREAKER,counter=,bar=
  HMI-ARM,<sym>,block=,sess=,dir=,bar=

Changed Functions（每处只增加一条 PrintFormat）:
  POIPush()             NEW；离窗降级前记录 OUT（只记第一次离窗）
  POIInvalidateOnBar()  INVALID / EXPIRED
  SessionStart()        START
  SessionEndNow()       END
  BlkPush()             NEW
  CycCreate()           ARMED
  HMI_Util.mqh          新增 PoiStateName / SessEndName / DiagT（仅供日志）

Changed States:
  (none)

Trading Logic Changed:
  NO —— 新增代码只有 PrintFormat 与三个只返回字符串的函数。

Reason:
  A-37：USDCAD / NZDUSD 等 7 个品种趋势持续数日而无任何标记，
  原日志只覆盖 Context 与 Rule 6 否决，无法判断链条停在哪一环。
  重建会把整个窗口的链条一次输出，无需等待实时。

Tooling:
  tools/ReloadTest.ps1 -Chain   读取每个图表最近一次完整重建，按
                                POI → Session → block → ARMED → 标记 计数，
                                指出自最后一条标记以来链条停在哪一步

Test Impact:
  版本号变化：Future Leak 实时样本在 v2.41 上重新累积。
  v2.40 的结论（USDJPY 10/10 存活）保留在 docs/04，不受影响。

Compile Status:
  未单独编译 —— 随 v2.42 一起编译通过（2026-09-30）
```

---

## v2.42 — BRI-09：PD / PW / PM 水平位与统一的 Liquidity Sweep 判定（含 v2.41 诊断日志）

```
Version:  v2.42
Date:     2026-09-30
签字:     BRI-09 S-1…S-6 全部同意（用户 2026-09-30）；
          用户要求「用新的版本测试」—— v2.41 未单独发布，其诊断日志随本版一起测试

New Module:
  HMI_LiquidityLevels.mqh
    LiqM5OnBar()       Phase 1b。换期 → 判定 → 事件
    LiqLevelsRoll()    日 / 周 / 月变化时由已消费 H4 求上一周期高低（S-2）
    PrevTradingDay()   PDH/PDL 可跳过周日短时段（InpPDSkipSunday）
    LiqJudge()         S-3：越过（+margin）→ N 根内收回 = SWEEP，否则 BROKEN；S-4 只判一次
    LiqEmit()          事件记录 + HMI-BUILD/LIVE LIQ 行（与 MODEL 行同列布局）

Changed Functions:
  LiqOnBar()           删除「H4 影线碰到即 swept」（S-5）；只保留登记 BSL/SSL
  LiqPush()            初始化 lq_state / pierce_index
  ProcessClosedM5Bar() Phase 1 之后、warm-up 返回之前调用 LiqM5OnBar
  ResetEngine()        LiqLevelsReset()
  OM_SyncAll()         六条水平线（重合价位合并标签，已判定的线止于判定那根）；
                       SWEEP / BROKEN 标签，保留 InpLiqSweepDays 天
  OM_Protected()       PL 线不参与裁剪；新增 OM_DeleteName()

Changed States:
  LiqPool  + lq_state, pierce_index；swept 语义改为「已判定（SWEEP 或 BROKEN）」

New Inputs:
  InpLiqSweepReclaimBars = 3     InpPDSkipSunday = true
  InpShowPD / InpShowPW / InpShowPM = true
  InpShowLiqEvents = true        InpLiqSweepDays = 5
  Style: 六条线各自独立 —— Inp{PDH,PDL,PWH,PWL,PMH,PML}{Color,Style,Width}
         （用户 2026-09-30 要求可逐条调颜色 / 线型 / 粗细；标签颜色跟随各自的线）
         InpPLTextSize / InpLiqSweepColor / InpLiqBrokenColor / InpLiqEventTextSize

Trading Logic Changed:
  NO（S-1）—— POI / Session / Block / Cycle / 模型均不读取本模块任何状态。
  显示变化：H4 BSL/SSL 线消失的时点由「H4 影线碰到」改为「M5 判定 SWEEP/BROKEN」。

Also in this build (v2.41, 未单独发布):
  HMI-POI / HMI-SESS / HMI-BLK / HMI-ARM 诊断日志（A-37），仅日志

Tooling:
  ReloadTest.ps1  -Live / -Quiet / -Chain 的「最新标记」只取 MODEL 行；
                  -Chain 另列 LIQ 事件；-LiveVsBuild 模型分布含 LIQ <level> <kind>

Compile Status:
  PASS — 0 errors / 0 warnings（用户实测，2026-09-30，3031 ms，AVX2 + FMA3；v2.42 构建，涵盖 v2.41 诊断日志）
```

---

## v2.43 — A-34：面板 H4 ATR 与结构引擎同一时点

```
Version:  v2.43
Date:     2026-09-30
签字:     用户 2026-09-30「1-3 暂且不用修改，只修改 4」

Changed Functions:
  RangesATRText()   H4 ATR 读 g_h4_atr[g_h4_cursor - 1]（结构引擎已消费的最后一根），
                    不再读 g_h4_atr[g_h4_n - 1]（已追加但可能尚未消费的一根）

Changed States:
  (none)

Trading Logic Changed:
  NO —— 仅面板显示。M5 ATR 不变（M5 追加即处理，无游标差）。

Not in this version（用户决定暂缓）:
  A-33 BOS 去重 / BRI-08 CISD·MSS 首次有效收盘 / protected_level · leg_anchor

Compile Status:
  NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.44 — 构建身份写入日志（仅日志）

```
Version:  v2.44
Date:     2026-09-30
来源:     工程师审查（2026-09-30）一.3 / 三.2

Changed:
  BuildHistory()  HMI-BUILD-BEGIN 追加
                    ver=<HMI_VERSION> params=<8 位摘要> inst=<实例> build=<本实例第几次构建>
                    warmup_end=<第一根允许出标记的 M5 开盘时间，取自数据，不再估算>
                  HMI-BUILD-END 追加 build=
  ParamsDigest()  新增。对所有能改变标记 / Context / 流动性事件的输入做 FNV-1a 摘要；
                  显示、样式、提醒类输入不计入（改颜色不会让两次构建「不可比」）
  #property version  2.40 → 与 HMI_VERSION 一致（此后每版同步）

Trading Logic Changed:  NO

Tooling（tools/ReloadTest.ps1，同日）:
  删除 converging / carried / warm-up 自动放行分类（审查一.1，可放过真实漏标）
  不再按「有没有 LIQ 行」推断版本升级（审查一.2）；版本与参数一律读 BEGIN 行
  重载比较：仅同版本且同参数摘要才比；比较区间 = 两次真实预热之后 ∩ 两个窗口；
            窗口起点不同则再加 -SettleHours（默认 24）；区间内任何差异 = MISMATCH，
            区间外 = 待复核（PENDING REVIEW）；只有区间内一致且无待复核才说
            「no repaint found」，且只针对该区间
  实时 vs 重建：每对相邻完整构建之间的实时段，在可证明覆盖的 K 线上
            双向比对（实时有重建无 / 重建有实时无）；版本或参数不同、未记录 → 待复核

Compile Status:  随 v2.46 一起编译
```

---

## v2.45 — 流动性状态跨重载保持（审查二）

```
Version:  v2.45
Date:     2026-09-30

Problem:
  周期价位与 H4 流动性池在重建时一律从 INTACT 开始，但 5000 根 M5 未必覆盖
  本周期早期。月初已扫过的 PMH，重建窗口不含月初时会被当作从未触发，
  月底再次穿越即再出一次事件 —— 连续运行不会。

Changed:
  SeriesAlignM5ToH4()  新增。M5 窗口起点对齐到 H4 边界（最多丢弃 47 根，均在预热内），
                       使第一根 M5 之前的每根 H4 都完整
  PLPreScan()          新增。周期起点早于第一根 M5 的价位，用已消费的 H4 回放
                       [周期起点, 第一根 M5)：任一根越过（+margin）→ LQ_UNKNOWN；
                       H4 历史够不到周期起点 → LQ_UNKNOWN
  LiqOnBar()           第一根 M5 之前收盘的 H4：对已确认的流动性池做同样的越过检查 → LQ_UNKNOWN
  LiqJudge()           LQ_UNKNOWN 视为已判定：不再判定、不出事件
  显示                 UNKNOWN 价位标签加「?」（如 PMH?），线止于越过的那根 H4

LQ_UNKNOWN 的含义:
  在 M5 覆盖开始之前已被越过 —— 已触发，但当时是 SWEEP 还是 BROKEN 无法判断。
  这是审查要求的「历史不足时标记未知，不要假定未触发」。

Known limit:
  InpBreakMarginMode = MARGIN_ATR_FRAC 时，回放用第一根 M5 的 margin（ATR 预热为 0 → 回退 pips），
  与逐根 M5 的 ATR margin 可能略有差别。PIPS / POINTS 模式完全一致。

Verification（离线模拟，与 MQL 逻辑逐条对应）:
  见 docs/04「v2.45 流动性重载一致性模拟」

Trading Logic Changed:
  标记链 NO。M5 窗口起点对齐会使窗口最前 ≤47 根 M5 不再参与 —— 均在预热内，
  同版本两次构建之间无影响；与旧版本比较时窗口起点附近的差异属预期。

Compile Status:  随 v2.46 一起编译
```

---

## v2.46 — 流动性标签显示（审查三）

```
Version:  v2.46
Date:     2026-09-30

Changed:
  OM_SyncAll()     同一根 K 线、同方向、同价位、同类型的 SWEEP/BROKEN 合并为一个标签
                   （如「PDH·PWH SWEEP」）；同根同方向的其它标签按
                   InpLabelStackOffsetPips 逐层错开，不再重叠。日志仍逐条记录
  OM_Protected()   SWEEP/BROKEN 标签（LE）不参与对象裁剪 —— 数量上限 64；
                   实时运行中被裁剪、重建后又画出，会让两者显示不同的标签集合
  #property version  2.46

Trading Logic Changed:  NO（仅显示）

Compile Status:
  NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.47 — 流动性回放改用 M5，恢复历史 ATR 阈值；撤销共用 M5 裁剪

```
Version:  v2.47
Date:     2026-09-30
来源:     工程师复核 v2.46（2026-09-30）：共用 M5 裁剪 / 历史 ATR 阈值还原

Reverted (v2.45):
  SeriesAlignM5ToH4()   删除 —— 为流动性裁剪了所有引擎共用的 g_m5，影响面过大
  PLPreScan() / LiqOnBar 中的 H4 回放   删除 —— 用窗口第 0 根的 margin
                        （ATR 预热期为 0 → 回退 pips）代替历史阈值

New:
  g_lr[] / g_lr_atr[]   仅本模块使用的「窗口之前」M5 K 线（CopyRates，按需加载，
                        起点 = 最早一个需要回放的价位 / 池的开始时间 - 3 天）
  LiqReplay()           窗口第 0 根：周期价位（起点早于窗口）与流动性池（确认早于窗口）
                        从各自起点在 g_lr 上逐根执行与实时完全相同的 S-3 判定，
                        每根使用自身 ATR(14) 的 margin；不输出事件，只恢复状态
  LiqAtrAt()            窗口第 0–13 根借用 g_lr 末尾计算 ATR —— 接缝处的阈值
                        与更早开始的连续运行一致
  LiqJudgeBar()         实时与回放共用的单根判定；回放中已越过、尚在 N 根等待期内的
                        状态以负索引带入窗口，计数不断
  HMI-LIQ-REPLAY 日志   need_from / have_from / bars / unknown

LQ_UNKNOWN 的含义收窄为: 已加载的 M5 历史够不到该价位 / 池的起点。

Verification（tools/liq_reload_sim.py，规则层模型）:
  PIPS  v2.42 4/18 不一致 · v2.46 0/18 · v2.47 0/18
  ATR   v2.42 4/18 · v2.46 0/18 · v2.47 0/18
  ATR（系数 2.0，定向场景）v2.46 2/48 不一致（例：PMH BROKEN 仅连续运行有）· v2.47 0/48

Trading Logic Changed:  标记链 NO；共用 M5 恢复为 v2.44 行为
Compile Status:         随 v2.48 一起编译
```

---

## v2.48 — 多实例日志关联

```
Version:  v2.48
Date:     2026-09-30
来源:     工程师复核 v2.46：多实例日志关联

Changed:
  所有 HMI 日志行末尾追加 ,inst=<实例>（BEGIN 行原已有）:
    MODEL / LIQ 事件行、BUILD-END、CTX、REJECT、GUARD、POI、SESS、BLK、ARM、LIQ-REPLAY
  MT5 只给日志行标 (品种,周期)；同一品种同一周期挂两个实例时，
  两者的构建与实时行过去会被当成同一来源互相配对。

Tooling:
  ReloadTest.ps1 读入后先取出并去掉行尾 ,inst=，其余解析规则不变；
  同一 (品种,周期) 出现多个实例时拆成「品种#实例,周期」，各自比对。
  已用两个交错实例的模拟日志验证：实例 0002 丢失的事件被单独判为 MISMATCH，
  实例 0001 不受影响。

Trading Logic Changed:  NO（仅日志）
Compile Status:         NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.49 — 代码审查修复：仲裁落选 Block 的反手 ARMED、锚块轮转、重启残留对象

```
Version:  v2.49
Date:     2026-10-01
来源:     代码审查（2026-10-01，v2.48 全部源文件静态通读；未编译）

Trading logic (D-11, BRI-10 —— docs/02):
  M5TouchArbitrate   TOUCHED 的 Block 只在「新的触碰」上参与仲裁：上一根已收盘 M5
                     K 线不与该 Block 相交。规格 §7.2 允许 TOUCHED → ARMED（后续 K 线
                     再次触碰），§8.3 又要求 ARMED 前置状态为 ACTIVE；v2.48 把「仍在
                     区间内」当作再次触碰，同一根上落选的 Block 下一根反手 ARMED，
                     一根前刚建立的 Cycle 被关闭并全部 PASS。
                     InpArmRequiresFreshTouch = true（默认）；false 恢复 v2.48 行为。进入参数摘要。
  H4ContextOnBar     TRANSITION 超时那根 H4 的收盘仍做突破判定：此前超时即返回，
                     落在同一根上的突破被跳过。超时后同根突破 = RANGE 行的 BOS（§2.3）。

Fixed:
  BlkPush            轮转不再丢掉当前 ACTIVE Cycle 的 ARMED 锚块（Cycle 无时限，锚块
                     迟早成为最老记录；丢掉后 Phase 2 的 BlockFindById 找不到，
                     D-5 / ANCHOR INVALIDATED 静默失效）。与 POIPush 保护 Session POI 同理。
  OM_ClaimInstance   实例标记写入 run=<终端进程 id>（临时终端全局变量 HMI_RUN_ID，不落盘，
                     终端退出即消失）。OnInit 先清掉 run id 不同的实例标记及其全部对象：
                     终端被杀 / 崩溃 / 重启后随图表保存下来的旧对象此前永远留在图上
                     （旧代码见到旧标记只是换下一个 tag）。无 run= 的旧版标记不动。
                     日志：HMI: removed the objects of instance XXXX left by a previous terminal run
  SessionStart       SE_NEW_SESSION 的 end_time / 日志改为该根收盘时间，与其他结束原因一致。
  KillZone           MAX_KZ_INST 40 → 64；InpKZDays 超出容量时 OnInit 打印提示，此前静默丢弃最早几天。

Not changed (按规格 / 待观察):
  Cycle 无时限 —— §9.3 / Rule 15 字面，D-1 / D-5 已裁决；BPR 晚腿上界为 now（§12）
  A-32 精确比较的重建频率 —— 先看日志 BEGIN 行 build= 计数
  OnTimer —— MT5 的 K 线只在下一个 tick 到来时才成为 shift 1，定时器看不到更早的已收盘 K 线

Trading Logic Changed:  YES（D-11 默认开；TRANSITION 超时根）—— 与 v2.48 不可做重绘比对
Compile Status:         NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.50 — 规则基线恢复；流动性历史等待与恢复（P1）；构建日志严格校验（P2）

```
Version:  v2.50
Date:     2026-10-02
来源:     验收方「HMI v2.49 阶段验收报告」（2026-10-01）+ 用户范围决定（2026-10-02）

Reverted (v2.49 → v2.48 行为; 两项各自独立出版本):
  M5TouchArbitrate   撤回 D-11「离开后重新触碰才能 ARMED」；InpArmRequiresFreshTouch 删除，参数摘要恢复 37 项
  H4ContextOnBar     撤回「TRANSITION 超时当根继续判定 BOS」，超时进入 RANGE 后立即返回
  两项变化保留于提交 30a288b 与随包交付的补丁 D-11_fresh_touch.patch / timeout_bar_bos.patch
  （均可干净套用于 v2.50），BRI-10 保持 OPEN

P1 (A-47) 流动性历史等待与恢复:
  LiqReplay          三态 READY / WAITING / UNKNOWN；WAITING = 回放够不到起点且服务器元数据未到或服务器有该段；
                     永久 UNKNOWN 仅当 SERIES_SERVER_FIRSTDATE 晚于起点
  OnTimer            WAITING 时每 5 秒非阻塞探测（CopyRates 到本地数组）；到位 → TryBuild() 重建一次（唯一路径）；
                     60 次仍未到 / 服务器确认没有 → UNKNOWN 定格，定时器停
  TryBuild           OnCalculate 首次 / 历史刷新 / 定时重试共用的唯一重建入口
  LiqReplayAvail     边界复核：ATR 模式不足 15 根回放 K 线 → 无可回放起点（原取最后一根 ATR=0 按 pips 回退）
  日志               HMI-LIQ-REPLAY 加 state= attempt=；HMI-LIQ-HIST ARRIVED / GAVE_UP / SERVER_LACKS；
                     BUILD-END 加 liq= liqev= unknown=；面板 WAITING 提示（COMPACT 后缀 / FULL 单行）

P2 (A-48) 构建日志严格校验:
  指标               每行 ,inst=,run=<终端进程 id>,init=<初始化序号>（临时终端全局变量，CAS 自增）；
                     BEGIN / END / 事件 / 诊断 / starting on 一致携带
  ReloadTest.ps1     单一构建块解析器供所有模式使用；COMPLETE = END build 与 BEGIN 相同 + run/init 相同 +
                     块内每行 run/init 相同 + marks= 等于 MODEL 行数 + liqev= 等于 LIQ 行数；
                     缺 END / 重复 BEGIN / 错号 END / 数量不符 / 身份不符 → INCOMPLETE 不比对不 PASS；
                     -Chain 只读最新 COMPLETE 块；LIVE vs BUILD 排除异身份实时行；
                     任一构建 liq=WAITING → LIQ 行 PENDING、MODEL 照常；MODEL / LIQ 数量分开显示；
                     修正单来源时 sources found 显示块数的旧问题
                     合成日志 9 组验证通过（PowerShell 7.4.6）

Kept from v2.49:    BlkPush 锚块保护、重启残留实例清理、SE_NEW_SESSION 收盘时间、KillZone 容量（均不触碰标记链）

Trading Logic Changed:  NO（相对 v2.48；v2.49 的两项变化已撤回）
Compile Status:         NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.51 — 验收方 v2.50 复核：流动性逐条等待、等待不靠计数结束、日志缺字段即不完整、跨版本比较需有效区间；锚点轮转撤出

```
Version:  v2.51
Date:     2026-10-02
来源:     验收方「HMI v2.50 验收复核报告」（2026-10-02）

P1 (A-49) 流动性历史逐条判定:
  LiqStartLost      够不到的条目：起点早于历史下限 / 已加载 K 线从下限开始 / 终端已持有起点前 3 天
                    → 永久 UNKNOWN；否则 pending。任何 pending → WAITING
  LiqHistoryFloor   服务器首根与 Max bars 截断后最老一根，取较晚者；均未知 = 0（不等于「没有」）
  LiqHistoryProbe   目标 = 最早的仍可恢复 pending 起点（每次按最新下限重算）；
                    ARRIVED / BEFORE_FLOOR / SETTLED → 重建一次
  日志              HMI-LIQ-REPLAY 加 waiting= wait_from= floor=；BUILD-END 加 liqwait=
P1 (A-50) 等待只由重建结束:
  OnTimer           60 次快速探测（5 s）后改 60 s 慢速，HMI-LIQ-HIST,SLOW，状态仍 WAITING，
                    面板 slow retry；不再有「次数到了就 READY」
P2 (A-51) 日志严格校验:
  ReloadTest.ps1    ver >= 2.50 或带 run/init 的构建：缺身份 = 身份不符；块内全部带标签行（含诊断）校验；
                    END 必填 build/marks/liqev/liq/unknown（2.51 起 liqwait，且与 liq 一致）；
                    实时行同规则，不符 → 该对 PENDING
P2 (A-52) 跨版本可比性:
  ReloadTest.ps1    先查参数；无共同区间 → NOT COMPARABLE；无 MODEL 行 → INSUFFICIENT SAMPLE；
                    输出比较行数；窗口移动 → PENDING REVIEW；新增 -Source <a> -Versus <b> 做固定窗口版本回归
Withdrawn:
  BlkPush           A-42 锚点轮转保护撤回到 anchor_rotation.patch（可改变 MODEL，单独出版本）

Tools:
  tools/liq_wait_sim.py      P1 状态机模型（镜像 MQL 函数）9 个场景；--v250 对照
  tools/logtests/            25 组合成日志 + cases.json + Run-LogTests.ps1（仅需 PowerShell）
Patches (package / Patches_withdrawn): D-11_fresh_touch / timeout_bar_bos / anchor_rotation，
                           单独或一起均可干净套用于 v2.51

Kept from v2.49 (do not touch the mark chain):
  重启残留实例清理（绘图）、SE_NEW_SESSION 收盘时间（日志 / end_time 无读取方）、KillZone 容量（显示）

Trading Logic Changed:  NO（相对 v2.48，任何参数下；参数摘要与 v2.48 相同）
Compile Status:         NOT COMPILE VERIFIED（Rule 70）
```

---

## v2.52 — 验收方 v2.51 复核：历史请求不越过下限；build 字段必须有效；无判定样本不给通过

```
Version:  v2.52
Date:     2026-10-05
来源:     验收方「HMI v2.51 验收复核报告」（2026-10-05；v2.51 编译 0 errors / 0 warnings）

P1 (A-53) 历史请求按下限收紧:
  LiqHistoryFloor   截断时取 SERIES_FIRSTDATE（按周期的已构建 M5 首根）
  LiqRequestFrom    max(起点 - 3 天, 下限)；回放与探测共用
  LiqReplay         先读下限；因下限丢失的条目不扩大请求
  LiqLossKind       回放与探测共用的丢失判定（floor / short / pending）
  日志              HMI-LIQ-REPLAY: req_from got err fail m5_first capped short；SLOW: err fail
P2 (A-54) build 字段:
  ReloadTest.ps1    v2.44+ 与严格格式：BEGIN / END 的 build 必须是正整数，缺失或非法即 INCOMPLETE
P2 (A-55) 判定样本:
  ReloadTest.ps1    同版本比较逐类结论（MODEL / LIQ）；无参与判定的行 → INSUFFICIENT SAMPLE；
                    LiveVsBuild 过滤后为空的构建对不计入可比较

Tools:
  tools/liq_wait_sim.py   终端按文档返回 -1（越过 TERMINAL_MAXBARS、需下载）；--lenient 为旧的裁剪终端；
                          --logic v2.51 / v2.50 对照；新增 R1 R2 R3 容量场景。v2.52 12/12
  tools/logtests          35 组（新增 b01–b06 build 字段、w01–w04 判定样本）。v2.52 脚本 35/35

Trading Logic Changed:  NO（相对 v2.48，任何参数下；参数摘要与 v2.48 相同）
Compile Status:         NOT COMPILE VERIFIED（v2.51 已由验收方编译通过；v2.52 只改动流动性模块与主文件日志）
```

---

## v2.53 — BOS 去重（A-33）：一根 H4 至多一次结构事件

```
Version:  v2.53
Date:     2026-10-06
来源:     用户 2026-10-06：v2.52 固定为开发基线；v2.53 只处理 BOS 去重
Baseline: v2.52 = 63379fd（docs/baselines/v2.52.md：源码指纹、241 个输入默认值、params=461F006E、测试记录）

Trading logic (BRI-11 读法甲):
  H4ConsumeSameDirBroken   新增。结构事件发生时，同一根收盘按同一余量突破的其它已确认、未处理同向摆动点
                           一并标记已处理（含 TRANS_SAMELEG）。触发条件与主参考点不变
  H4ContextOnBar           调用上者；CtxLog 加 also=；also>0 记 HMI-CTX-DEDUP
Not changed:               余量、保护点、评分、TR、流动性池、参数（参数摘要仍 461F006E）

Tools:
  tools/h4_dedup_sim.py    H4 结构层 + H4 POI 链离线模型（v2.52 / v2.53），必验场景 4/4；真实 EURUSD 回放
  tools/params_digest.py   按源码计算默认参数摘要（v2.48 / v2.52 / v2.53 均 461F006E）
  tools/ReloadTest.ps1     HMI-CTX 作为判定类别（重载、实时 vs 重建）；跨版本逐条归因（A-56）
  tools/logtests           45 组（新增 c01–c10）

Evidence:  docs/evidence/v2.53_h4_dedup_offline.txt
Trading Logic Changed:  YES —— 结构事件与强度；H4 状态仅在陈旧点推动 TRANSITION / RANGE 时改变
Compile Status:         NOT COMPILE VERIFIED（本环境无 MetaEditor）
```

---

## v2.53 工具修订（A-57）—— 跨版本归因只认具体证据（MQL5 不变）

```
Date:     2026-10-07
来源:     验收方「HMI v2.53 验收复核报告」（2026-10-06）P2
MQL5:     不变（与验收方编译的 v2.53 字节相同，HMI_VERSION 仍 2.53）

tools/ReloadTest.ps1   跨版本归因三档：explained（具体链接）/ UNEXPLAINED（可证明非去重）/ PENDING_ATTRIBUTION（人工复核），
                       逐条写入 attribution_<旧源>__<新源>.txt；链路 POI -> SESS -> BLK -> ARM -> MODEL 实例内按 id、跨版本按稳定字段对应；
                       H4 收盘 / 摆动点价位一致性与强度规则核对；取消按时间先后的自动解释
tools/h4_dedup_sim.py  同规则；归因防护自测 6/6
tools/logtests         49 组（c05–c08 改为新判据；c06 补完整链；新增 c11–c14 反例）；合成诊断行改为真实字段顺序
```
