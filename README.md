# H4 Context → M5 Identification Indicator

**Version:** spec v1.00 (frozen baseline) / code **v2.58r4 — official baseline, accepted 2026-11-06** (docs/baselines/v2.58r4.md)
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
| [docs/06_Audit_Round1_v1.00.md](docs/06_Audit_Round1_v1.00.md) | 审计记录（第 1 轮起，至 Audit Round 53 正式封版）(Rule 66 / 67) |
| [docs/07_Baselines.md](docs/07_Baselines.md) | 各版本可回退基线索引 |
| [docs/baselines/v2.58r4.md](docs/baselines/v2.58r4.md) | **当前正式使用基线**：源码 / EX5 / 工具指纹、参数配置、已知限制、五日结果、封版与归档 |
| [docs/evidence/](docs/evidence/) | 各版本运行与离线核对记录（五日运行：`v2.58r4_five_day_run.txt`、`v2.58r4_five_day_live_h4.tsv`） |

---

## 当前状态（2026-11-06）

**v2.58r4 是正式使用基线**：验收方「HMI v2.58r4 五日验收通过与正式封版结论」（2026-11-06）判定通过，正式封版落地使用；
「正式归档审核确认」（同日）核对源码、EX5、回退源码与归档指纹一致。本轮开发与验收已结束。详见 [docs/baselines/v2.58r4.md](docs/baselines/v2.58r4.md)。

| 项目 | 状态 |
|------|------|
| 源码 | `MQL5/Indicators/HMI`，26 个文件，提交 `2386f8f`（之后只改文档） |
| 编译 | 0 errors / 0 warnings（用户与验收方，2026-10-29） |
| 正式 EX5 | `H4M5_Identification.ex5`，328788 字节，SHA256 `4A3BB167…5DBB` |
| 参数 | 默认 `461F006E`；ATR 配置 `A047970C`（只改 `InpBreakMarginMode = MARGIN_ATR_FRAC`） |
| 离线 / 工具 | stage_sim 102/102、mirror PASS、logtests 228/228、live_coverage_tests 28/28 |
| 五日运行验收 | 10-30、11-02 至 11-05：469 次构建完整、无运行时错误；100 组实时 H4 强度 / 质量 / 阶段与重建一致；实时 MODEL / LIQ / CTX / PROT / B8 0 差异；每日重载可比区间一致（11-02 三张图窗口移动，区间前记 PENDING REVIEW） |
| 回退 | v2.57 基线 `833c7a3`（[docs/baselines/v2.57.md](docs/baselines/v2.57.md)） |
| 保留限制 | 移动窗口（A-59）、编号随窗口重排（A-20）、MSS C5 原生罕见分支只有离线覆盖；P3 原因文字与一个输入显示名留后续独立版本 |

### 早期阶段记录（2026-09，历史，不代表当前状态）

| 项目 | 状态 |
|------|------|
| Phase 1 — Architecture & Logic Specification | **COMPLETE** |
| Phase 2 — Conflict Resolution / Business Rule Sign-off | **COMPLETE** (D-1..D-7 signed off 2026-09-22) |
| Phase 3 — MQL5 Implementation | **COMPLETE** (v1.00, ~2560 lines) |
| Phase 4 — Audit (P0–P3) | **ROUND 4** (10 fixed, 5 potential risks, 1 withdrawn) |
| Phase 5 — MetaEditor Compile | **PASS** — v2.40, 0 errors / 0 warnings (2026-09-24) |
| Phase 6 — Visual Replay / Repaint Test | **进行中** —— POI-01 / POI-02a（接受侧）/ POI-02b（否决侧）、四品种重绘一致性、图表周期独立性均已 PASS；Future Leak（LIVE vs BUILD）待测 |

## 源码

```
MQL5/Indicators/HMI/             <- 整个指标就这一个文件夹
   H4M5_Identification.mq5          入口 / OnInit / OnCalculate / Phase 0-7
   HMI_Defs.mqh                     enum / struct / 全局状态
   HMI_Params.mqh                   功能 input（Rule 60：阈值不散落）
   HMI_Style.mqh                    样式 input：颜色 / 线型 / 线宽 / 字号
   HMI_KillZone.mqh                 Kill Zone 时段 HIGH/LOW（纯显示，见 D-8）
   HMI_Ranges.mqh                   面板 ATR / ADR（纯显示，见 D-9）
   HMI_Util.mqh                     整数 point 比较 / pip / 时间工具
   HMI_Series.mqh                   M5 / H4 显式取数 + break margin（D-6）
   HMI_SwingEngine.mqh              fractal swing（带 confirm_time）
   HMI_FVGEngine.mqh                FVG + OB/FVG 连接判定
   HMI_H4StructureEngine.mqh        BOS / CHOCH
   HMI_H4ContextEngine.mqh          4 状态 Context 机
   HMI_H4RangeEngine.mqh            版本化 Trading Range + Liquidity
   HMI_LiquidityLevels.mqh          BRI-09 流动性水平 / SWEEP / BROKEN（只标记）
   HMI_H4POIEngine.mqh              H4 POI 全生命周期
   HMI_M5BlockEngine.mqh            Refinement Session / M5 OB / Breaker
   HMI_CycleManager.mqh             ARMED 仲裁 / Reference 冻结 / Cycle 隔离
   HMI_CISDEngine.mqh               CISD（不引用其它模型）
   HMI_MSSEngine.mqh                MSS（不引用其它模型）
   HMI_BPREngine.mqh                BPR（不引用其它模型）
   HMI_PriceActionEngine.mqh        PA x3（不引用其它模型）
   HMI_StrengthEngine.mqh           v2.56 趋势强度（BRI-13，只显示）
   HMI_QualityEngine.mqh            v2.57 趋势质量（BRI-14，只显示）
   HMI_StageEngine.mqh              v2.58 当前阶段 / 主要原因 / 强度箭头 / 面板文字（BRI-15，只显示）
   HMI_ObjectManager.mqh            唯一允许调用 Object* 的模块
   HMI_AlertManager.mqh             Phase 7 告警
```

安装：把 `MQL5/Indicators/HMI` **整个文件夹**复制到 MT5 数据文件夹的 `MQL5\Indicators\` 下，
挂在 **M5** 图表上。**不需要动 `Include` 目录。** ATR 配置的图：在输入参数里把 `InpBreakMarginMode` 改为 `MARGIN_ATR_FRAC`，
其余保持默认（或加载自己保存的 .set）；构建日志的 `params=` 应为 `A047970C`。

> **历史记录（2026-09-22，v2.02）：** 当时编译 PASS、Replay NOT VERIFIED、`docs/04` 用例尚未执行。
> 此后各版本均以真实 MT5 运行结果验收（Rule 71 / 72），当前状态见上方「当前状态」与 `docs/04` 各版本清单。
