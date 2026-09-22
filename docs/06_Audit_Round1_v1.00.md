# Audit Round 1 — v1.00 Implementation  (+ v1.01 fixes)

**日期：** 2026-09-22
**范围：** `MQL5/Indicators/HMI/H4M5_Identification.mq5` + `MQL5/Include/HMI/*.mqh`（约 2560 行）
**方法：** Rule 66 的 P0 → P3 顺序静态审计，格式遵循 Rule 67。

> **证据声明（Rule 67）：**
> 本环境**没有 MetaEditor / MT5 / 历史数据**，未执行任何编译与 Replay。
> 因此本轮**不存在** `Confirmed Bug` 级别的结论。
> 已修复项标注 `FIXED (static)`，未验证项一律标注 `Potential Risk`。

---

## 已修复（本轮）

### A-01
```
ID:                      A-01
Severity:                P1
Module:                  HMI_ObjectManager
Function:                OM_SyncAll (M5 block loop)
Location:                block drawing filter
Trigger:                 Refinement Session 结束后（g_sess.active == false）
                         仍有逆势 Block 记录存在
Expected Behavior:       InpShowCounterDirBlocks = false 时，逆势 Block（Breaker 原料）
                         在任何时刻都不绘制
Actual Behavior:         过滤条件依赖 g_sess.active 与 g_sess.dir；Session 结束后
                         g_sess.dir 仍是旧值但条件整体短路，逆势 Block 会被画出来
Impact:                  图表噪音；用户可能把逆势原料 Block 误读为可交易区域
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO（纯显示）
Recommended Fix:         在 M5Block 增加 counter_dir 字段，创建时一次性判定，
                         绘图层只读该字段
Status:                  FIXED (static)
Confidence:              HIGH
```

### A-02
```
ID:                      A-02
Severity:                P1
Module:                  HMI_ObjectManager
Function:                OM_Trim
Location:                object registry trimming
Trigger:                 对象数量超过 InpObjectHistoryLimit
Expected Behavior:       只裁剪历史图形对象
Actual Behavior:         注册表按创建顺序裁剪，而 Instance Marker 是**第一个**注册的对象，
                         因此会被优先删除；marker 一旦消失，该 Instance Tag 就被释放，
                         另一个实例可能抢占同一 tag，且 OnDeinit 的按前缀清理会失效
Impact:                  多实例互删对象（违反 Rule 55）；Context 面板闪烁
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         OM_Protected()：marker（_MK_）与面板（_CX_）永不参与裁剪
Status:                  FIXED (static)
Confidence:              HIGH
```

### A-03
```
ID:                      A-03
Severity:                P2
Module:                  HMI_ObjectManager / HMI_H4POIEngine
Function:                OM_RightEdge / level line t2 / POIInvalidateOnBar
Location:                datetime 运算
Trigger:                 编译期类型推导
Expected Behavior:       "bars x seconds" 先以整数算完再转 datetime
Actual Behavior:         写成 (datetime)N * PeriodSeconds(...)，先把 N 转成 datetime 再乘，
                         语义可行但依赖隐式类型提升，且易触发编译告警
Impact:                  潜在编译 Warning（Rule 70 目标是 0 Warnings）
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         (datetime)((long)N * PeriodSeconds(tf))；年龄比较改用 (long) 比较
Status:                  FIXED (static)
Confidence:              MEDIUM
```

### A-04
```
ID:                      A-04
Severity:                P3
Module:                  HMI_H4ContextEngine / HMI_Defs / 主文件
Function:                CtxEnter / IdentificationCycle / OnCalculate
Location:                g_ctx_flipped_this_bar、armed_drawn、g_last_bar0
Trigger:                 —
Expected Behavior:       无死变量
Actual Behavior:         三个变量只写不读（Context 变化诊断实际由 H4ProcessBar 的
                         before != g_ctx 完成，ARMED 绘制由 drawn_mask bit 6 完成）
Impact:                  可维护性；潜在编译 Warning
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         删除
Status:                  FIXED (static)
Confidence:              HIGH
```

---

### A-11  （本轮新发现，A-05 的真正根因）
```
ID:                      A-11
Severity:                P1
Module:                  HMI_H4POIEngine
Function:                POIPush
Location:                数组满时的驱逐
Trigger:                 H4 POI 数量达到 InpH4MaxPOIs（default 12）后再创建新 POI
Expected Behavior:       Spec 4.6 / 14.7 / AX-4：被挤出逻辑窗口的 POI
                         标记为 POI_EXPIRED，**记录保留**，只丢弃图形
Actual Behavior:         整条记录被移出数组直接消失，导致两个后果：
                         (1) 它的 Rectangle 停留在"存活样式"僵在图上，
                             直到被对象裁剪顺手删掉（违反 Rule 36 的可见真实性）
                         (2) 活跃 Session 持有的 poi_id 变成悬空引用 → A-05
Impact:                  图上出现内部已不存在、却仍以存活样式显示的 POI
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO（修复后可触碰的 POI 集合逐条相同，见下方等价性证明）
Recommended Fix:         物理存储扩到 MAX_POIS = 64，逻辑窗口仍然是 InpH4MaxPOIs；
                         离开窗口的记录降级为 POI_EXPIRED + out_of_window，
                         绘图层一次性删除其图形（Spec 14.7 的字面实现）
Status:                  FIXED (static) — v1.01
Confidence:              HIGH
```

**等价性证明（为什么这不是交易逻辑改变）：**

| 检查点 | v1.00 | v1.01 |
|--------|-------|-------|
| 可触碰集合 | 被删除的记录不在数组里 → 不可触碰 | 记录仍在，但状态被强制为 `POI_EXPIRED`，而 `POITouchedBy` 只接受 `POI_ACTIVE` → 不可触碰 |
| 能否再被 INVALIDATED | 记录不存在 → 否 | `POIInvalidateOnBar` 跳过非 ACTIVE/TOUCHED → 否 |
| 能否再被 age-out | 否 | 同上 → 否 |
| Session 是否因它结束 | `POIFindById` 返回 -1 → 检查被跳过 → 不结束 | `SessionMaintain` 改为只认 `POI_INVALID`（Spec 5.1 字面），而该记录永远到不了 INVALID → 不结束 |

四条全部一致 ⇒ **标记结果逐条相同**。唯一变化是图上那个僵尸矩形消失了。

---

## 未修复 / 待 Replay 验证（Potential Risk）

### A-05
```
ID:                      A-05
Severity:                P1
Module:                  HMI_M5BlockEngine
Function:                SessionMaintain
Location:                POIFindById(g_sess.poi_id) 返回 -1 的分支
Trigger:                 活跃 Session 对应的 H4 POI 被 InpH4MaxPOIs 上限挤出数组
Expected Behavior:       POI 被挤出后，其 Session 应当随之结束
Actual Behavior:         POIFindById 返回 -1，POI 失效检查被跳过，
                         Session 只能靠 CONTEXT_FLIP 或 TIMEOUT 结束
Impact:                  极端情况下 Session 比预期多活一段时间；不产生错误标记，
                         但 Block 搜索窗口比业务意图长
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   YES（Session 生命周期）
Recommended Fix:         Session 直接缓存 poi_hi / poi_lo / poi_confirm_time，
                         或在 POI 被挤出时主动结束引用它的 Session
Status:                  PARTIALLY FIXED — v1.01。根因（A-11 的记录删除）已修，
                         悬空引用在实践中不再可能出现（记录要撑过 52 次新 POI 创建
                         才会被物理淘汰，而 Session 最长仅 288 根 M5 = 1 天）。
                         **可观测行为刻意保持不变**：Session 仍然只因
                         POI_INVALID / CONTEXT_FLIP / TIMEOUT 结束。
                         用户明确要求不改交易逻辑，故未加"引用丢失即结束"的 fail-safe。
Confidence:              MEDIUM
```

### A-06
```
ID:                      A-06
Severity:                P2
Module:                  HMI_H4POIEngine
Function:                POITouchedBy
Location:                只接受 POI_ACTIVE
Trigger:                 Session 因 TIMEOUT 结束后，价格再次回到同一个 H4 POI
Expected Behavior:       规则集未定义
Actual Behavior:         该 POI 已是 POI_TOUCHED，不会再次开启 Session，
                         即「一个 POI 一生只触发一次 Refinement」
Impact:                  长时间盘整的 POI 只有第一次反应会被精细化
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   YES（潜在漏标）
Recommended Fix:         InpPOIMaxSessions（**default 1 = v1.00 行为，逐 tick 相同**）。
                         设为 >1 时：仅当 Session 以 SE_TIMEOUT 结束、POI 仍为 TOUCHED
                         且未离开逻辑窗口时，标记 awaiting_leave；
                         之后必须有一根已关闭 M5 K 线的 [low, high] **完全脱离** POI 区间，
                         该 POI 才回到 POI_ACTIVE 并可再次触发 Session。
                         「必须先完全离开」是防止 Session 在价格仍压在 POI 内时
                         超时后逐根无限重启的关键闸门。
                         SE_POI_INVALID / SE_CONTEXT_FLIP / SE_NEW_SESSION 一律不复触。
Status:                  IMPLEMENTED AS OPT-IN — v1.01，默认关闭。
                         默认值下 awaiting_leave 永不被置位，代码路径永不进入。
Confidence:              HIGH
```

### A-07
```
ID:                      A-07
Severity:                P2
Module:                  主文件 ProcessClosedM5Bar
Function:                Phase 1 vs Phase 3 顺序
Location:                Phase 顺序（Spec 17.2 固定）
Trigger:                 H4 POI 触碰的同一根 M5 K 线上恰好完成一个顺势 FVG
Expected Behavior:       规格规定 Phase 1（结构）先于 Phase 3（Session）
Actual Behavior:         触碰那一根上 Session 尚未建立，M5BlocksOnFVG 直接返回，
                         该 FVG 不会生成 Block；最早的 Block 来自触碰后一根
Impact:                  理论漏标一个极罕见形态（进场方向 FVG 恰好完成于触碰根）
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO（Rule 7 本就要求从触碰开始）
Recommended Fix:         不修 —— 改顺序会破坏 Spec 17.2 的确定性保证
Status:                  Potential Risk（已知且可接受）
Confidence:              HIGH
```

### A-08
```
ID:                      A-08
Severity:                P3
Module:                  HMI_Series
Function:                SeriesAppend
Location:                g_m5 / g_h4 的 append-only 策略
Trigger:                 指标连续运行数周不重载
Expected Behavior:       内存有界
Actual Behavior:         数组只增不减（为了让 runtime bar index 永久稳定）。
                         一年 M5 ≈ 75000 根 ≈ 4.5 MB
Impact:                  内存缓慢增长；不影响正确性
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         如需上限：触发一次完整 rebuild（会重置 runtime 索引），
                         但会重建对象，需权衡
Status:                  Potential Risk（低）
Confidence:              HIGH
```

### A-09
```
ID:                      A-09
Severity:                P1
Module:                  全部
Function:                —
Location:                —
Trigger:                 在 MetaEditor 中首次编译
Expected Behavior:       0 Errors / 0 Warnings（Rule 70）
Actual Behavior:         未知 —— 本环境无 MetaEditor，未执行任何编译
Impact:                  语法 / 类型 / MQL5 API 签名错误尚未被机器验证
Historical Repaint:      N/A
Future Leak:             N/A
Business Logic Impact:   NO
Recommended Fix:         用户在 MetaEditor 编译并回报完整错误/告警列表，
                         按 Rule 68（一次一个）修复
Status:                  NOT COMPILE VERIFIED
Confidence:              HIGH（对"未验证"这一事实本身）
```

### A-10
```
ID:                      A-10
Severity:                P2
Module:                  HMI_ObjectManager
Function:                OM_SyncAll
Location:                每根新 K 线全量同步
Trigger:                 每根已关闭 M5 K 线
Expected Behavior:       Rule 59：不每 tick 重建
Actual Behavior:         满足（只在新 K 线同步，bar 0 只走节流预览），
                         但新 K 线时会对全部活跃 zone 重设属性（~150 对象）
Impact:                  每 5 分钟一次的小开销；不违反 Rule 59
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         如 Replay 中出现卡顿，可只在 vis 变化或右边界变化时更新
Status:                  Potential Risk（性能，低）
Confidence:              MEDIUM
```

---

## P0 复查结论（无发现）

| P0 项 | 结论 | 依据 |
|-------|------|------|
| Future Leak | 未发现 | 所有确认路径只读 `<= n` 的已关闭 K 线；MSS 的 C1、H4 的 `h4_open + 4h <= m5_open`、Block/POI 的 `confirm_time <= m5[n].time` 三处硬闸 |
| Historical Repaint | 未发现 | 确认后只改 `state` 与绘图样式，`cfm_time / cfm_price / *_level / *_ref_time` 写入后再无赋值点 |
| Array Out of Range | 未发现 | 全部定长数组 + `SafeIdx` + 每个循环边界逐一复核；push 函数均先驱逐后写入 |
| Wrong Timeframe Mapping | 未发现 | 不存在任何跨周期 index 相等假设；唯一映射点是 `H4VisibleTo()` |
| State Corruption | 未发现 | Cycle 采用「取出副本 → 修改 → 写回」；所有 Reference 均为 Cycle 成员，无模块级残留 |

## P1 复查结论

| P1 项 | 结论 |
|-------|------|
| Object Name | 格式 `HMI_{INST}_{TT}_{id}_{sub}`，最长约 24 字符（上限 63）；显示文字全部走 `OBJPROP_TEXT` |
| Multi-instance Conflict | Instance Claim 协议 + `OnDeinit` 只删自己前缀；A-02 已修 |
| MSS Reference Validity | C1–C5 全部实现（含 C5 的「已被吃掉」回扫） |
| CISD Reference Validity | ARMED 时冻结一次，此后无任何赋值点 |
| Cycle Leakage | 结构上不可能：无模块级 Reference 变量 |
| BPR Lifecycle | CONFIRMED/ACTIVE/TOUCHED/INVALID 全实现，失效立即改样式 |
| Block Lifecycle | 8 个状态齐备；TOUCHED 与 ARMED 的区分按 Spec 7.1 实现 |

---

## Rule 73 验收表（当前真实状态）

```
Architecture:          PASS          (规格 + 代码结构一致)
Code Version:          v1.01         (v1.00 spec baseline 未变)
Business Logic:        PASS          (D-1..D-7 已裁决并落地)
Future Leak:           PASS (static) / NOT VERIFIED (replay)
Historical Repaint:    PASS (static) / NOT VERIFIED (replay)
H4/M5 Alignment:       PASS (static) / NOT VERIFIED (replay)
H4 POI:                NOT VERIFIED
M5 OB:                 NOT VERIFIED
M5 Breaker:            NOT VERIFIED
ARMED:                 NOT VERIFIED
Cycle Management:      NOT VERIFIED
CISD:                  NOT VERIFIED
MSS:                   NOT VERIFIED
BPR:                   NOT VERIFIED
PA:                    NOT VERIFIED
Object Management:     PASS (static) / NOT VERIFIED (replay)
Multi-instance:        PASS (static) / NOT VERIFIED (replay)
Historical vs Live:    NOT VERIFIED
MetaEditor:            NOT COMPILE VERIFIED
Replay:                NOT VERIFIED
```

**下一步（Rule 68 的节奏）：**
1. 在 MetaEditor 编译，回报完整 Errors / Warnings
2. 一次修一个，编译 → Replay → 下一个
3. 按 `docs/04_Test_Plan_v1.00.md` 逐条跑 Replay 与 Repaint 对比（开 `InpLogSignals` 导出 CSV）
4. 依据实测结果，把上表的 NOT VERIFIED 逐项改写
