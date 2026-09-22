# H4 Context → M5 Identification Indicator

**Version:** spec v1.00 (frozen baseline) / code v2.00
**Platform:** MetaTrader 5 / MQL5 Custom Indicator
**Mode:** Trend-Following Only
**Purpose:** MARK ONLY — Detect / Confirm / Track / Mark / Invalidate

---

## 0. 最重要原则 (Frozen)

### Rule 1 — MARK ONLY

本指标只负责：

| 负责 | 不负责 |
|------|--------|
| Detect | 自动 Entry |
| Confirm | Buy / Sell |
| Track | SL / TP |
| Mark | Position Size |
| Invalidate | 自动订单 / 胜率判断 / 是否值得交易 |

**本指标不是 Entry System。不得改造为 Entry Indicator。**

### Rule 2 — 顺势模式

v1.00 只实现 Trend-Following。不实现 Counter-Trend。

> **v2.00 默认值偏离声明：** `InpEnableBreaker = false`，
> 因此**出厂状态不产生 M5 Breaker Block**，不满足 Rule 8 / Rule 11。
> 代码实现完整保留，设为 `true` 即恢复。详见 `docs/02` 的 BRI-05 / D-10。

---

## 核心链路 (Frozen Pipeline)

```
H4 Context
  → H4 Trend / Structure
  → H4 Trading Range
  → H4 Liquidity
  → H4 POI (完整 OB，FVG 仅验证)
  → 价格触碰有效 H4 POI
  → 启动 M5 Refinement
  → 有效 M5 Block (OB / Breaker，必须 Touch/Overlap FVG)
  → M5 Block 被价格触碰
  → M5 BLOCK ARMED
  → Identification Cycle
  → CISD / MSS / BPR / PA ENGULFING / PA REJECTION / PA BREAK-RETEST
  → MARK ONLY
  → Trader Decision
```

不得跳过 `H4 POI → M5 Block → ARMED` 直接在任意 M5 区域寻找 Identification 模型。

---

## 文档索引

| 文件 | 内容 |
|------|------|
| [docs/01_Architecture_Spec_v1.00.md](docs/01_Architecture_Spec_v1.00.md) | 完整架构与逻辑规格 (Rule 63 的 20 个章节) |
| [docs/02_Conflict_And_Business_Rule_Issues_v1.00.md](docs/02_Conflict_And_Business_Rule_Issues_v1.00.md) | 规则冲突分析 + BUSINESS RULE ISSUE (Rule 64 / Rule 65) |
| [docs/03_Module_Architecture_v1.00.md](docs/03_Module_Architecture_v1.00.md) | 代码架构：文件 / 模块 / Enum / Struct / 调用顺序 |
| [docs/04_Test_Plan_v1.00.md](docs/04_Test_Plan_v1.00.md) | Replay Test Plan + Repaint Test Plan (Rule 71 / Rule 72) |
| [docs/05_Changelog_v1.00.md](docs/05_Changelog_v1.00.md) | 版本记录 (Rule 74) |
| [docs/06_Audit_Round1_v1.00.md](docs/06_Audit_Round1_v1.00.md) | 第一轮代码审计 (Rule 66 / 67) |

---

## 当前阶段状态

| 项目 | 状态 |
|------|------|
| Phase 1 — Architecture & Logic Specification | **COMPLETE** |
| Phase 2 — Conflict Resolution / Business Rule Sign-off | **COMPLETE** (D-1..D-7 signed off 2026-09-22) |
| Phase 3 — MQL5 Implementation | **COMPLETE** (v1.00, ~2560 lines) |
| Phase 4 — Audit (P0–P3) | **ROUND 1 DONE** (6 fixed, 5 potential risks) |
| Phase 5 — MetaEditor Compile | **NOT COMPILE VERIFIED** |
| Phase 6 — Visual Replay / Repaint Test | **NOT VERIFIED** |

## 源码

```
MQL5/Indicators/HMI/H4M5_Identification.mq5     入口 / OnInit / OnCalculate / Phase 0-7
MQL5/Include/HMI/HMI_Defs.mqh                   enum / struct / 全局状态
MQL5/Include/HMI/HMI_Params.mqh                 功能 input（Rule 60：阈值不散落）
MQL5/Include/HMI/HMI_Style.mqh                  样式 input：颜色 / 线型 / 线宽 / 字号
MQL5/Include/HMI/HMI_KillZone.mqh               Kill Zone 时段 HIGH/LOW（纯显示，见 D-8）
MQL5/Include/HMI/HMI_Ranges.mqh                 面板 ATR / ADR（纯显示，见 D-9）
MQL5/Include/HMI/HMI_Util.mqh                   整数 point 比较 / pip / 时间工具
MQL5/Include/HMI/HMI_Series.mqh                 M5 / H4 显式取数 + break margin（D-6）
MQL5/Include/HMI/HMI_SwingEngine.mqh            fractal swing（带 confirm_time）
MQL5/Include/HMI/HMI_FVGEngine.mqh              FVG + OB/FVG 连接判定
MQL5/Include/HMI/HMI_H4StructureEngine.mqh      BOS / CHOCH
MQL5/Include/HMI/HMI_H4ContextEngine.mqh        4 状态 Context 机
MQL5/Include/HMI/HMI_H4RangeEngine.mqh          版本化 Trading Range + Liquidity
MQL5/Include/HMI/HMI_H4POIEngine.mqh            H4 POI 全生命周期
MQL5/Include/HMI/HMI_M5BlockEngine.mqh          Refinement Session / M5 OB / Breaker
MQL5/Include/HMI/HMI_CycleManager.mqh           ARMED 仲裁 / Reference 冻结 / Cycle 隔离
MQL5/Include/HMI/HMI_CISDEngine.mqh             CISD（不引用其它模型）
MQL5/Include/HMI/HMI_MSSEngine.mqh              MSS（不引用其它模型）
MQL5/Include/HMI/HMI_BPREngine.mqh              BPR（不引用其它模型）
MQL5/Include/HMI/HMI_PriceActionEngine.mqh      PA x3（不引用其它模型）
MQL5/Include/HMI/HMI_ObjectManager.mqh          唯一允许调用 Object* 的模块
MQL5/Include/HMI/HMI_AlertManager.mqh           Phase 7 告警
```

安装：把 `MQL5/` 下的两个目录复制到 MT5 数据目录的对应位置，挂在 **M5** 图表上。

> **NOT COMPILE VERIFIED** —— 本仓库的代码从未经过 MetaEditor 编译，
> 也从未在 MT5 上跑过 Replay。任何"0 Errors / 0 Warnings"或"Replay PASS"的说法
> 都必须由真实运行结果支撑（Rule 70 / 71 / 72）。
