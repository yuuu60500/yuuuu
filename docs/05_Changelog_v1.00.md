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
