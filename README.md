# H4 Context → M5 Identification Indicator

**Version:** v1.00 (Specification Stage — NO CODE YET)
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

---

## 当前阶段状态

| 项目 | 状态 |
|------|------|
| Phase 1 — Architecture & Logic Specification | **COMPLETE** |
| Phase 2 — Conflict Resolution / Business Rule Sign-off | **COMPLETE** (D-1..D-7 signed off 2026-09-22) |
| Phase 3 — MQL5 Implementation | **IN PROGRESS** |
| Phase 4 — Audit (P0–P3) | **NOT STARTED** |
| Phase 5 — MetaEditor Compile | **NOT COMPILE VERIFIED** |
| Phase 6 — Visual Replay / Repaint Test | **NOT VERIFIED** |

本仓库当前**不包含任何 MQL5 源码**。规格阶段结束、冲突项确认后才进入实现。
