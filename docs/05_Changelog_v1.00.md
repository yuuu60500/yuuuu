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
