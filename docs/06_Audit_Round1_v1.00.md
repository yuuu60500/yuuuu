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
Status:                  **RESOLVED — 2026-09-22，v2.02 在 MetaEditor 编译通过
                         0 errors, 0 warnings（用户实测）**
                         过程中共暴露 2 个真实缺陷：
                           - 打包问题（v2.01：尖括号 include 需要拆两个目录）
                           - A-16（v2.02：CISD / MSS 引擎从未进入编译单元）
Confidence:              HIGH（编译器输出为证）
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
                       注：Reload 一致性对 Future Leak 是盲的 ——
                       有未来函数的实现每次重建都会自洽。见 docs/04 的 LIVE vs BUILD
Historical Repaint:    PASS          (2026-09-23 实测，四品种同时挂载：
                                     AUDUSD 156 / EURUSD 199 / GBPUSD 52 / USDJPY 143 行，
                                     每个品种全部 block 行数一致；EURUSD/GBPUSD 窗口相同
                                     逐字节相等，AUDUSD/USDJPY 窗口滑动后剔除序号相等)
H4/M5 Alignment:       PASS          (2026-09-23 实测：M2/M5/M15/M30 四种图表周期
                                     14 次构建结果完全一致，验证 §15.4 周期独立性)
H4 POI:                PARTIAL PASS  (POI-01 / POI-02a 接受侧已用真实数据逐条核对；
                                     POI-02b 否决侧 PASS —— AUDUSD 2026.09.03 一条
                                     完整追溯八项全中（FVG 存在 / 边界 / CONF-14 /
                                     OB 反方向 / 边界 / gap 14 点 / 图上无矩形），
                                     另 29 条 gap_pts 手算零误差；
                                     已排除「超上限删图形」的误判（12 上限，实际 3 个）；
                                     POI-03..09 仍未验证)
M5 OB:                 NOT VERIFIED
M5 Breaker:            NOT VERIFIED
ARMED:                 NOT VERIFIED
Cycle Management:      NOT VERIFIED
CISD:                  NOT VERIFIED
MSS:                   NOT VERIFIED
BPR:                   NOT VERIFIED
PA:                    NOT VERIFIED
Object Management:     PASS (static) / NOT VERIFIED (replay)
                       注：编译通过只证明语法与类型，不证明任何行为
Multi-instance:        PARTIAL PASS  (2026-09-23 实测：四个实例同时写同一日志，
                                     按 (SYMBOL,TF) 分组后各自结果互不污染；
                                     同图表多实例仍未测)
Historical vs Live:    PARTIAL PASS  (重建可复现已证；LIVE vs BUILD 首条样本通过 ——
                                     2026-09-25 USDJPY,M5 BPR，n=1，仅证明方法可用)
MetaEditor:            PASS          (v2.40, 0 errors / 0 warnings, 2026-09-24)
                       注：v2.04 / v2.10 因 A-19 实际不可编译，已于 v2.11 修复并复验
Replay:                NOT VERIFIED
```

**下一步（Rule 68 的节奏）：**
1. 在 MetaEditor 编译，回报完整 Errors / Warnings
2. 一次修一个，编译 → Replay → 下一个
3. 按 `docs/04_Test_Plan_v1.00.md` 逐条跑 Replay 与 Repaint 对比（开 `InpLogSignals` 导出 CSV）
4. 依据实测结果，把上表的 NOT VERIFIED 逐项改写

---

## 补充：v1.10 顺带修掉的显示缺口

### A-13
```
ID:                      A-13
Severity:                P2
Module:                  HMI_ObjectManager
Function:                OM_SyncAll (POI / block loops)
Location:                颜色与线型的三元表达式
Trigger:                 POI 或 M5 Block 进入 TOUCHED 状态
Expected Behavior:       状态机区分 ACTIVE 与 TOUCHED，图上也应当能区分
Actual Behavior:         颜色与线型只在 dead 上分叉，ACTIVE 与 TOUCHED 渲染完全相同；
                         用户无法一眼判断某个 POI 是"还在等价格"还是"已经触发过 Session"
Impact:                  可读性；不影响任何标记
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         给 TOUCHED 独立样式（ZS_POI_TOUCH / ZS_BLK_TOUCH）
Status:                  FIXED — v1.10
Confidence:              HIGH
```

### A-14（仍未修）
```
ID:                      A-14
Severity:                P3
Module:                  HMI_Params
Function:                —
Location:                InpShowRejectedOB
Trigger:                 用户拨动该参数
Expected Behavior:       BRI-04 的设计：用极淡虚线画出被 Gap 否决的 OB
Actual Behavior:         参数在全部源码中只出现 1 次（声明本身），没有任何地方读它，
                         拨动它没有任何效果
Impact:                  参数面板有一个假开关
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         实现绘制（约 20 行），或删掉该参数
Status:                  Potential Risk — 未修
Confidence:              HIGH
```

### A-15（v1.20 顺带修掉）
```
ID:                      A-15
Severity:                P2
Module:                  HMI_ObjectManager
Function:                OM_SyncAll (liquidity loop)
Location:                if(g_liq[i].swept) continue;
Trigger:                 一个流动性池被扫（SWEPT）
Expected Behavior:       该池的线应当从图上消失（或改样式）
Actual Behavior:         循环只是 continue，已经画出去的线既不更新也不删除，
                         永久停留在图上。v1.00/v1.10 里 InpShowLiquidity 默认关闭，
                         所以没暴露；一旦默认打开就会变成明显的脏图
Impact:                  图上出现大量"已经被扫但仍然显示"的流动性线，
                         与 Rule 36 要求的可见真实性冲突
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         给 LiqPool 加 vis 字段，被扫或超出显示上限时删除其图形
Status:                  FIXED — v1.20
Confidence:              HIGH
```

---

## Audit Round 2 —— 首次真实编译反馈（2026-09-22）

> 这是本项目**第一个有证据的 Confirmed Bug**。此前所有条目都只能写
> `Potential Risk`，因为没有编译器、没有 Replay。编译器一跑就抓到了
> 静态通读六遍都没看出来的问题。

### A-16
```
ID:                      A-16
Severity:                P0
Module:                  H4M5_Identification.mq5 / include 拓扑
Function:                Phase4_Identification（主文件 134-135 行）
Location:                #include 链
Trigger:                 F7 编译
Expected Behavior:       六个识别引擎全部参与编译，Phase 4 能调用它们
Actual Behavior:         HMI_CISDEngine.mqh 与 HMI_MSSEngine.mqh
                         **从未被任何文件 include**，因此不在编译单元内。
                         编译器报 undeclared identifier 'CISD_Check' / 'MSS_Check'，
                         另外 6 个错误（',' unexpected / 'cy' some operator expected /
                         ')' unexpected）全是解析器遇到未知函数名后的连锁反应。
Impact:                  指标无法编译。即使能编译，六个模型里的两个（CISD 与 MSS）
                         也会静默缺席 —— 而这两个恰恰是规格里最核心的两个。
Root Cause:              主文件只 include 了 HMI_AlertManager.mqh，靠它逐层往下拉。
                         BPREngine 与 PriceActionEngine 是**碰巧**被 ObjectManager
                         拉进来的，不是设计；CISDEngine 与 MSSEngine 没有这个运气。
                         讽刺的是，这正是 docs/03「四个识别引擎互不 #include」
                         那条架构原则的副作用：既然它们互不引用，就必须由调用方
                         显式引用，而主文件没有。
Historical Repaint:      N/A
Future Leak:             N/A
Business Logic Impact:   NO（修复后逻辑与规格一致；缺失的是编译可见性，不是实现）
Recommended Fix:         主文件显式 include 它直接调用的每一个引擎
                         （include what you use）。include guard 让重复无害。
Status:                  FIXED — v2.02
Confidence:              HIGH（编译器输出为证）
```

**教训（值得写进流程）：** `docs/03` 用「引擎互不 include」来在编译期保证
Rule 30 / 44（模型不互相 Consume）。这条原则是对的，但它把「谁来 include 引擎」
的责任推给了调用方 —— 而这一点当初没有写进架构文档。已在 docs/03 补充。

---

## Audit Round 3 —— 首次实盘挂载反馈（2026-09-22，USDJPY M5）

### A-17 —— **撤回：不是 Bug（误判）**
```
ID:                      A-17
Severity:                （已撤回）
Module:                  HMI_ObjectManager
Claim:                   面板行文字被 MT5 在 63 字符处截断
Evidence Used:           两张截图中 Cycle 行都停在 "PA REJE"，
                         数得约 62-63 字符；同面板 57 与 49 字符的行完整显示
Actual:                  **文字没有被截断。** 两张截图都只是没把面板右侧截进画面。
                         用户于 2026-09-22 直接确认。
Root Cause of the Error: 我用截图里的字符数做推断，而不是先向用户求证。
                         上一轮我本来已经标注「这个我不确定，不想瞎改」，
                         下一轮却因为第二张截图停在同一位置就当成了证据 ——
                         两张图其实是同一种截图习惯，不是两个独立证据。
Status:                  **WITHDRAWN — NOT A BUG。v2.03 的折行已于 v2.04 撤销。**
Confidence:              —
```

> **记录这条的意义：** `docs/06` 是审计轨迹，一条错误的 `FIXED` 会污染它。
> 按 Rule 67 的精神，没有证据不能写 Confirmed —— 而"截图里看起来是这样"
> 不构成证据。这条留在文档里作为反面样本，不删除。

### 本轮同时验证通过的项目（首次获得实测证据）

| 项目 | 证据 |
|------|------|
| Break margin（BRI-03 / D-6） | USDJPY 3 位报价：`0.003 price / 3 points`，未退化为 0 |
| ADR（D-9） | `ADR(20): 134.6 pip / today 95.0 pip (71%) / left 39.6 pip`；首次显示 n/a 是 D1 历史未下载，属预期 |
| Kill Zone（D-8） | ASIA / LONDON / NY AM 三组 HIGH+LOW 全部绘制，带标签，**无时段矩形** |
| 完整名称（Rule 61） | `▲ CISD` / `▲ BPR` / `▲ PA REJECTION` / `▲ PA BREAK-RETEST`，无 C/M/B 缩写 |
| ▲▼ 字形 | `\x25B2` 转义在 Arial 下渲染正常 |
| ARMED（Rule 13） | 多个 `M5 OB ARMED` 标签，各自对应一个 M5 Block 矩形 |
| Level 线（Rule 24 / 62） | 多条 `CISD Level`，自 reference 时间画至确认后 |
| Cycle 隔离（Rule 14 / 43） | 每个 ARMED 之后跟随其自身的 `▲ CISD`，未见单 Cycle 重复同模型 |

> 以上属于**目视确认**，不等于 `docs/04` 的用例通过。
> Rule 71 / 72 要求的逐根 Replay 与 Reload 对比仍未执行，
> 因此验收表中相关项仍为 NOT VERIFIED。

---

## Audit Round 4（2026-09-22）

### A-18
```
ID:                      A-18
Severity:                P2
Module:                  HMI_ObjectManager
Function:                OM_SyncAll（trading range 段）
Location:                OM_Name(TT_TR, version_id, 0)
Trigger:                 每一次 BOS / CHOCH / Forward Extension 产生新的
                         TradingRange 版本
Expected Behavior:       图上任何时刻只有当前版本的 Trading Range
Actual Behavior:         版本化设计（Rule 4）让每个新版本拿到新的 version_id，
                         于是生成**新的对象名**；旧版本的矩形从未被删除，
                         长期运行会在图上堆积多个历史区间框。
                         与 A-15（被扫流动性线不删）属于同一类：
                         「对象名随状态变化」却没有配套的退休逻辑。
Impact:                  图面混乱；用户可能把过期区间当成当前区间
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO（纯显示）
Recommended Fix:         追踪已绘制的 version_id，换版本时先删旧的三个对象
Status:                  FIXED — v2.11
Confidence:              HIGH
```

### A-19 —— **我自己在 v2.04 引入的回归**
```
ID:                      A-19
Severity:                P0
Module:                  HMI_ObjectManager
Function:                （编译期）
Location:                #define MAX_PANEL_ROWS 与 OM_KZDelete 之间
Trigger:                 F7 编译
Expected Behavior:       v2.04 只撤销 v2.03 的折行
Actual Behavior:         撤销时按「注释起点 → OM_KZDelete」整段删除，
                         把夹在中间的 Kill Zone 追踪声明一并删掉：
                           #define MAX_KZ_DRAWN 64
                           int      g_kzd_zone[MAX_KZ_DRAWN];
                           datetime g_kzd_anchor[MAX_KZ_DRAWN];
                           int      g_kzd_n = 0;
                         **v2.04 与 v2.10 均无法编译**（undeclared identifier）。
                         两版都已发布，但用户尚未编译，所以没有暴露。
Impact:                  两个已发布版本不可用
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         恢复四行声明
Status:                  **FIXED & VERIFIED — v2.11 编译通过 0 errors / 0 warnings
                         （用户实测，编译清单中 HMI_CISDEngine.mqh 与
                         HMI_MSSEngine.mqh 均在列，同时复核了 A-16 的修复有效）**
Confidence:              HIGH
```

**教训:** 按「起点字符串 → 终点字符串」整段删除,会连带删掉期间**后来插入**的内容。
撤销一个改动时,应当按该改动自身的边界删除,而不是按当前文件里两个锚点之间的范围。
本轮已加入一个简单的静态自检(列出全局标识符,逐个确认有声明),
但它**替代不了编译器** —— 这正是 A-09 之后本项目反复验证的一点。

---

## Audit Round 5（2026-09-23，启动四品种 Live 测试之前）

### A-20 —— **测试工具缺陷：LIVE vs BUILD 用了会漂移的序号做比对键**

```
Severity:                P1（不影响指标输出，但会让 Future Leak 测试报假阳性）
Rule Violated:           Rule 52 / Rule 72（测试必须能判真伪）
Location:                tools/ReloadTest.ps1  -LiveVsBuild
Trigger:                 挂机跑出 HMI-LIVE 行后 reload，再跑 -LiveVsBuild
Expected Behavior:       同一个真实事件在 live 行与 rebuild 行中一致
Actual Behavior:         日志行第 4、5 列是 cycle_id / block_id，
                         它们来自 g_next_id 这个**自增序号**：
                           HMI_Defs.mqh:266     long g_next_id = 1;
                           H4M5_Identification.mq5:187   g_next_id = 1;（每次 init 重置）
                         而 SeriesAppend() 只追加、从不裁剪（HMI_Series.mqh），
                         所以一个跑了 K 根 M5 的实时会话，其窗口是
                           [T0-5000, T0+K]
                         但此刻重新加载得到的窗口是
                           [T0+K-5000, T0+K]
                         最老的 K 根被丢掉，其中分配过的每一个 id 随之消失，
                         之后所有 id 整体前移。
                         原脚本逐字节比对整行 → 同一事件因序号不同被判为
                         "LIVE mark does NOT appear in the rebuild"，
                         即**把重新编号误报成未来函数**。
Evidence:                源码直读（三处，见上）。只要实时期间有任意一个
                         id 分配事件落在被丢弃的最老区间内即触发；
                         跨天挂机必然发生。
                         **2026-09-23 实测确认：** AUDUSD,M5 与 USDJPY,M5
                         的最后两次重建窗口不同，整行比对不等、剔除
                         cycle_id / block_id 后 156 / 143 行完全相等 ——
                         正是本条描述的序号漂移，且无任何真实重绘。
                         同一次运行里窗口相同的 EURUSD / GBPUSD 走整行
                         相等分支，证明修复没有把真差异一并掩盖。
Impact:                  Future Leak 测试不可信（假阳性）
Historical Repaint:      NO
Future Leak:             NO   —— 这是测试工具的缺陷，不是指标的缺陷
Business Logic Impact:   NO
Recommended Fix:         比对键改为事件本身：dir / anchor / model /
                         confirm_time / price / ref_time / ref_level，
                         剔除第 4、5 列。Reload 比对保持整行（更严），
                         仅在整行不等时再用剔除序号的键复核一次，
                         以便区分「重新编号」与「真重绘」。
Status:                  **FIXED — v2.21（脚本层修复，指标未改一行）**
Confidence:              HIGH
```

> **为什么不去改指标让 id 稳定：** id 只是簿记，且出现在图形对象名里；
> 为了迁就一个测试脚本去改它属于 Rule 68/69 明令禁止的「顺手重构」。
> 缺陷在比对方法，就在比对方法上修。

### A-21 —— **测试工具缺陷：MT5 每天新开一个日志文件，脚本只读最新一个**

```
Severity:                P2
Rule Violated:           Rule 52
Location:                tools/ReloadTest.ps1（Get-ChildItem *.log | Select -Last 1）
Trigger:                 跨天挂机后再 reload 比对
Expected Behavior:       能看到这次挂机期间的全部 HMI-LIVE 行
Actual Behavior:         昨天的 live 行在昨天的 .log 里，今天 reload 写进今天的
                         .log。脚本只读最新一个文件 → live rows 显示为 0 或
                         只剩今天的几条，**静默丢样本**。
Impact:                  跨天测试的样本被无声截断
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         新增 -Days N，按时间升序合并最近 N 个日志文件
Status:                  **FIXED — v2.21**
Confidence:              HIGH
```

### A-22 —— **测试工具缺陷：脚本要求用户先切到正确目录**

```
Severity:                P2（挡住测试，不影响指标）
Rule Violated:           Rule 52
Location:                tools/ReloadTest.ps1（Get-ChildItem *.log 用相对路径）
Trigger:                 用户在 C:\Users\<name> 直接跑 .\ReloadTest.ps1
Actual Behavior:         CommandNotFoundException —— 脚本不在当前目录。
                         此前已踩过一次同类坑（用户把脚本放进了
                         Terminal\<ID>\logs 而不是 Terminal\<ID>\MQL5\Logs）。
                         一个测试工具要求先手工找到一个哈希命名的目录、
                         而且同一个终端下还有两个都叫 Logs 的目录，
                         这个前提本身就是缺陷。
Impact:                  测试启动失败，且失败信息与真正的原因无关
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         脚本自行定位：当前目录 →
                         %APPDATA%\MetaQuotes\Terminal\*\MQL5\Logs 中
                         .log 最新的那个；另给 -LogDir 手动覆盖。
                         输出文件也写回日志目录而不是当前目录。
Status:                  **FIXED — v2.22**
Confidence:              HIGH
```

### A-23 —— **测试工具缺陷：-Source 需要手写品种名**

```
Severity:                P2
Rule Violated:           Rule 52
Location:                tools/ReloadTest.ps1
Trigger:                 券商品种带后缀（EURUSD.a / EURUSDm / EURUSD#）
Actual Behavior:         手写的 -Source 匹配不到任何 source，脚本按
                         「没有 block」处理 —— 静默给出空结果，
                         看起来像「没有样本」而不是「名字写错了」。
Impact:                  多品种测试容易得到假的「无样本」结论
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         -Source 改为可选：不给就遍历日志里出现的全部图表；
                         给了但不在列表里则明确报错，而不是返回空。
Status:                  **FIXED — v2.22**
Confidence:              HIGH
```

### A-24 —— **测试工具缺陷：多品种跑 -Rejects 时输出文件互相覆盖**

```
Severity:                P3
Rule Violated:           Rule 52
Location:                tools/ReloadTest.ps1 v2.21（Set-Content poi_rejects.txt）
Trigger:                 用循环对四个品种连跑 -Rejects
Actual Behavior:         三次都写同一个 poi_rejects.txt，后一次覆盖前一次；
                         屏幕上四份结果都在，落地文件只剩最后一个品种。
Impact:                  多品种样本只能靠滚屏回看，容易漏
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         输出文件名带上品种与周期
Status:                  **FIXED — v2.22（已按 poi_rejects_<SYM>_<TF>.txt 命名）**
Confidence:              HIGH
```

---

## Audit Round 6（2026-09-24，用户询问面板字段含义时发现）

### A-25 —— **MESSY 的置位条件与规格不符**

```
Severity:                P2（仅显示，不影响任何判定）
Rule Violated:           规格 docs/01 §Context（第 202-204 行）
Location:                HMI_H4ContextEngine.mqh:62, 73
Trigger:                 任意一次 CHOCH
Expected Behavior:       规格原文：
                           quality = { CLEAN, MESSY }
                                     MESSY : 出现过至少一次**失败的 TRANSITION**
                         即只有 CTX_TRANSITION 分支里 brk != g_ctx_pending
                         （原趋势恢复）那一条才应置位。
Actual Behavior:         置位发生在 CTX_BULLISH / CTX_BEARISH 遇到反向破坏时，
                         也就是**每一次 CHOCH**：

                           ev = EV_CHOCH_DOWN;
                           g_ctx_messy = true;          // <-- 这里
                           CtxEnter(CTX_TRANSITION, DIR_BEAR, t);

                         而真正的「TRANSITION 失败」分支完全没有碰这个变量。
                         CHOCH 之后 TRANSITION 可能成功（趋势正常反转，属健康
                         结构）也可能失败；规格只想标记后者，实现标记了全部。
Evidence:                源码直读 + 规格原文；另有运行时佐证 ——
                         用户 USDCAD,M5 面板同时显示 `str 17` 与 `MESSY`。
                         strength 表示本轮 17 次同向 BOS、期间零 CHOCH，
                         若二者描述同一段结构则不可能同时成立。
Impact:                  面板质量字段几乎恒为 MESSY，失去区分能力
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   NO —— 全仓 grep，g_ctx_messy 只被面板的两行文字读取
                         （HMI_ObjectManager.mqh:360, 376），不参与任何判定
Recommended Fix:         置位移到 CTX_TRANSITION 的失败分支；
                         CHOCH 本身不再置位。
Status:                  **FIXED — v2.31。置位移到 CTX_TRANSITION 的失败分支，
                         CHOCH 分支不再置位。按 Rule 65，规格本身即业务规则，
                         把实现改回规格属 bugfix，不需要另行裁决。**
Confidence:              HIGH
```

### BRI-06 —— **BUSINESS RULE ISSUE：MESSY 的作用范围未定义**

```
规则原文（docs/01 第 202-204 行）:
  quality = { CLEAN, MESSY }
            MESSY : 出现过至少一次失败的 TRANSITION

冲突/缺口:
  「出现过」的范围没有写明，有两种互斥的读法：

  (a) 本轮 Context 之内 —— 与相邻的 strength 一致（strength 在
      CtxEnter 时重置为 1），两个字段描述同一段结构。
  (b) 整个加载的历史之内 —— 当前实现的行为（只在 OnInit 复位）。

  按 (b)，500 根 H4 ≈ 4 个月里必然出现过 CHOCH / 失败 TRANSITION，
  因此 MESSY 事实上恒为真，该字段不再承载信息。
  按 (a)，需要在 CtxEnter 时一并复位 g_ctx_messy。

影响范围:
  仅面板显示。不涉及 POI / Session / ARMED / 六个模型 / 日志。

我未擅自选择:
  这是业务语义问题，按 Rule 65 不由我决定。
  A-25（置位条件）与本条（作用范围）是两个独立问题，
  按 Rule 68 应分别裁决、分别修改。

需要你裁决:
  1. MESSY 应在**失败的 TRANSITION** 时置位，还是保持现在的**每次 CHOCH**？
  2. 它应在新 Context 建立时**复位**（每轮趋势独立评价），
     还是**永不复位**（整段历史的累计标记）？

裁决（2026-09-24）:
  第 1 问不属于业务裁决 —— 规格已写明「失败的 TRANSITION」，
  把实现改回规格是 bugfix（A-25，v2.31 已修）。

  第 2 问已向用户提出两个选项，用户答「No preference」，授权我裁决。
  **采用「每条 Context 腿独立」**，理由：
    - 与并列显示的 strength 一致（strength 在 CtxEnter 时重置为 1），
      两个字段描述同一段结构，不会再出现 str 17 + MESSY 这种自相矛盾
    - 「永不复位」下 500 根 H4 ≈ 4 个月里必然出现过失败 TRANSITION，
      字段恒为真，不承载信息
  语义确定为：**这条 Context 腿是否从一次失败的 TRANSITION 中诞生**。

  实现要点：TRANSITION 失败分支调用了 CtxEnter（失败恢复在引擎眼里
  就是开了一条新腿），所以置位必须在 CtxEnter **之后**，否则刚置上就被清掉。

  推论：按此语义该值只可能是 0 或 1 —— 一条腿里再出现 CHOCH 就已经
  离开这条腿了，不可能在同一条腿内攒第二次失败。布尔量是对的，
  不需要改成计数器。

  TRANSITION 状态本身显示 CLEAN：它尚未成功也尚未失败，无所谓「诞生自」。

状态:
  **RESOLVED — v2.32**
```

---

## Audit Round 7 —— 外部评审来件（2026-09-24）

> 来件共 8 条。以下逐条以代码查证，**不照单全收**：
> 有证据的记 Confirmed Bug，只有推理的记 Potential Risk，
> 属业务语义的按 Rule 65 转 BUSINESS RULE ISSUE，
> 机制描述有出入的照实更正。

### A-26 —— **预览标签的重复登记挤掉真实标记**（来件第 1 条，成立）

```
Severity:                P1
Location:                HMI_ObjectManager.mqh  OM_Preview()
Trigger:                 Session 活跃且价格位于某个 Block 区间内
Expected Behavior:       登记表条目数 == 实际对象数
Actual Behavior:         OM_Preview() 删除自己的标签却未调用 OM_Unregister：
                           ObjectDelete(0, nm);        // 缺 OM_Unregister(nm)
                           ...
                           OM_Text(nm, ...);           // 删过了 -> 创建成功 -> 再登记一次
                         它由定时器驱动（H4M5_Identification.mq5:310，
                         下限 50 ms），**每秒可重复登记十余次**。
                         g_obj_n 涨过 InpObjectHistoryLimit（500）后，
                         OM_Trim() 从表头删起，表头正是最老的真实对象
                         （POI / M5 Block / ARMED / 模型标签），
                         而 OM_Protected() 只保护 MARK / CTX / KZ / LIQ。
                         → 一个预览标签的重复登记，换掉一个真实信号标签。
                         另：MAX_OBJREG = 1024，两根 M5 之间可能有数千次预览，
                         打满后 OM_Register 静默返回，新对象再也进不了表。
Evidence:                源码直读。全仓 6 处 ObjectDelete，其余 5 处
                         （OM_DeleteOwner / KZ / 面板 / Trim / DeleteOwnAll）
                         均已注销或整表清零，仅此一处漏掉。
Impact:                  图表上的信号标记被逐个删除 —— 指标唯一的输出
Historical Repaint:      NO（状态不变，只是对象被删）
Future Leak:             NO
Business Logic Impact:   NO
Recommended Fix:         删除后补 OM_Unregister(nm)
Status:                  **FIXED — v2.34**
Confidence:              HIGH

更正：来件称「重复登记」。后果完全属实，机制是**删除时漏注销**，
不是双重登记 —— OM_Rect / OM_Text / OM_Level 都只在 ObjectCreate
成功时登记，本身没有重复登记的路径。
```

### A-27 —— **验证脚本把实时行全过滤掉了（我自己的缺陷）**（来件第 5 条，成立）

```
Severity:                P0（使 Future Leak 测试恒为假阴性）
Location:                tools/ReloadTest.ps1  Show-LiveVsBuild()
Trigger:                 任何一次 -LiveVsBuild
Expected Behavior:       扫描全部日志行，统计 HMI-LIVE
Actual Behavior:         $raw = $all | Where-Object { $_ -match 'HMI-BUILD' }
                         而实时扫描迭代的正是 $raw。
                         'HMI-LIVE,' 不含子串 'HMI-BUILD'，
                         **$live 结构上永远为空**。
Evidence:                源码直读 + 用户实测复现（日志确有 LIVE 记录，
                         脚本仍报 0 条）。
Impact:                  2026-09-23 至 09-24 期间所有「live rows: 0」
                         的结论**全部作废**。我据此判断「行情安静、继续挂」，
                         **该判断没有依据**。
                         受影响的还有我在 docs/04 写下的那段
                         「重建的最后一条标记时间可用于区分引擎没产出
                         与实时路径坏了」—— 该推理本身仍成立，
                         但当时用来支撑它的 live=0 是无效输入。
Recommended Fix:         改为迭代 $all
Status:                  **FIXED — v2.34 同批（脚本层）**
Confidence:              HIGH

教训：-Live 模式迭代 $all 是对的，-LiveVsBuild 迭代 $raw 是错的，
两处相隔 150 行、写于不同版本。**同一份数据的两条读取路径必须共用
一个取数函数**，否则迟早分叉 —— 与 ConnectionGapPts / RangesADRUsedPct
是同一个教训，这次我没有及时套用。
```

### A-28 —— **SwingLeft / SwingRight 小于 1 时越界**（来件第 7 条，成立）

```
Severity:                P3（需用户填入非默认值才能触发）
Location:                HMI_SwingEngine.mqh  SwingDetect()
Trigger:                 InpH4SwingRight <= 0 或 InpM5SwingRight <= 0
Actual Behavior:         int c = n - R;
                         R = 0  -> c = n，右侧确认循环不执行，
                                   分形在「无右侧确认」下成立，违反 AX-3
                         R < 0  -> c > n，同上，且在最新一根时
                                   r[c] 读出数组末尾之外
Evidence:                源码直读；MQL5 的 input int 无范围约束
Impact:                  非默认设置下可能越界读或产生不可确认的摆动点
Historical Repaint:      可能（无右侧确认的摆动点会被后续 K 线推翻）
Future Leak:             R<0 时读取 h 之后的 K 线 —— 是
Business Logic Impact:   NO（默认值 2/2 下行为不变）
Recommended Fix:         L < 1 || R < 1 直接返回；并要求 c < n
Status:                  **FIXED — v2.35**
Confidence:              HIGH
```

### A-29 —— **RANGE / TRANSITION 下旧 POI 仍能开启识别周期**（来件第 3 条，成立）

```
Severity:                P1（会产出 Rule 2 不该存在的标记）
Location:                H4M5_Identification.mq5:128-135（Phase 3 触碰分支）
                         HMI_M5BlockEngine.mqh:57 SessionStart()
                         HMI_M5BlockEngine.mqh:81 SessionMaintain()
Expected Behavior:       Rule 2：v1.00 仅顺势。
                         CtxDirection() 自己的注释即写明：
                           return(DIR_NONE);   // RANGE / TRANSITION: no new setups
Actual Behavior:         两处都没有拦住：
                         1) SessionStart() 内无任何 Context 判断，
                            Phase 3 只要 POITouchedBy(n) >= 0 就调用它。
                            POIOnBar() 有 `if(dir != CtxDirection()) return;`
                            所以 RANGE/TRANSITION 下不会**新建** POI，
                            但此前趋势中建立、仍为 POI_ACTIVE 的旧 POI
                            被触碰时照样开 Session。
                         2) SessionMaintain() 的翻转守卫是
                              if(CtxDirection() != DIR_NONE &&
                                 CtxDirection() != g_sess.dir) ...
                            RANGE / TRANSITION 下 CtxDirection() == DIR_NONE，
                            第一个条件为假，**守卫整体不生效**，
                            已有 Session 可以一路存活进 RANGE。
                         → Session -> M5 Block -> ARMED -> 识别周期 -> 标记
Evidence:                源码直读。代码自身的注释「no new setups」
                         即为作者意图，实现未落实。
Impact:                  在无主导趋势时产出趋势跟随标记
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   **YES —— 修复会改变信号输出**
Status:                  **FIXED —— v2.38（Phase 0b，已有 Session）
                         + v2.39（POITouchedBy 资格过滤，新 Session）**
Confidence:              HIGH
```

### A-30 —— **H4 尚未就绪时 M5 按旧 Context 计算且不补算**（来件第 2 条，Potential Risk）

```
Severity:                P1（若成立）
Location:                H4M5_Identification.mq5:294-300
Trigger:                 终端交付 H4 新 K 线晚于 M5
Reasoning:               int ah = SeriesAppend(PERIOD_H4, ...);
                         int am = SeriesAppend(PERIOD_M5, ...);
                         if(ah < 0 || am < 0) { g_ready = false; return; }
                         if(am > 0) { for(...) ProcessClosedM5Bar(n); }

                         H4 数据滞后时 SeriesAppend 返回 0（不是负数），
                         不触发重建。随后的 M5 K 线被处理，Phase 0 只能
                         消费 g_h4 里已有的 H4 —— 即**旧 Context**。
                         H4 补到之后由游标消费，但**那几根 M5 不会重算**。
                         重建时两条序列都完整 → 结果可能不同，
                         这正是 Rule 51（Historical Build ≈ Live Replay）
                         要防的情形。
Evidence:                **仅源码推理，无运行时证据。**
                         是否真的发生取决于券商与终端的 H4 交付时序。
Impact:                  实时与重建结果不一致
Status:                  **Potential Risk —— 待实测**
Confidence:              MEDIUM

如何证伪/证实：这恰好就是 LIVE vs BUILD 测试的目标。
该测试此前因 A-27 恒为假阴性，修复后才具备检出能力。
```

### A-31 —— **重载后实时周期标签可能消失**（来件第 4 条，判定为 A-30 的症状）

```
Severity:                —
Reasoning:               ResetEngine() 先 OM_DeleteOwnAll() 再 BuildHistory()，
                         所有图形都从重建后的状态重画。因此「实时留下的标签
                         重载后消失」当且仅当**重建没有复现那些周期**。
                         而重建为何可能不复现，正是 A-30；
                         在 A-26 修复前也可能是标记已被 OM_Trim 删除。
Status:                  **不单列 —— 归入 A-30（成因）与 A-26（已修）**
Confidence:              MEDIUM

若 A-26 / A-30 都处理完仍出现此现象，再作为独立缺陷重开。
```

### A-32 —— **历史修正不触发重建**（来件第 6 条，Potential Risk）

```
Severity:                P2
Location:                HMI_Series.mqh  SeriesAppend()
Reasoning:               仅当 iBarShift(...) < 0（最后一根已知 K 线消失）
                         才返回 -1 触发重建。若券商修正的是更早一根的
                         OHLC 而不删除任何 K 线，则无任何检测，
                         g_h4 / g_m5 里留着旧值，而重建会读到新值。
Evidence:                源码直读。真实发生频率未知。
Impact:                  实时与重建不一致
Status:                  **Potential Risk —— 待实测**
Confidence:              MEDIUM
```

### BRI-07 —— **BUSINESS RULE ISSUE：RANGE / TRANSITION 下的 Session 处置**

```
关联: A-29

规则原文:
  Rule 2 —— v1.00 仅顺势，不做逆势
  CtxDirection() 注释 —— "RANGE / TRANSITION: no new setups"

缺口:
  规格说明了「不产生新 setup」，但没有写明两件事：

  (a) RANGE / TRANSITION 期间，价格触碰一个**此前趋势中建立的**旧 POI，
      是否允许开启新的 Refinement Session？
  (b) 一个在趋势中开启、期间 Context 转入 RANGE / TRANSITION 的
      **已有** Session，应当立即结束，还是允许跑完？

  这两问的答案会改变信号输出，因此不由我裁决。

我的建议（仅供参考，未实施）:
  (a) 不允许。代码自身注释已写 "no new setups"，
      SessionStart() 加一道 CtxDirection() 判断即可，与 POIOnBar() 一致。
  (b) 立即结束，理由 SE_CONTEXT_FLIP 已存在且语义贴合；
      但也可以论证「TRANSITION 只是待定、允许跑完更合理」——
      这正是我不替你决定的原因。

  若选「立即结束」，SessionMaintain() 的守卫需改为：
      if(CtxDirection() != g_sess.dir) SessionEndNow(SE_CONTEXT_FLIP, t);
  去掉 `!= DIR_NONE` 这半个条件 —— 正是它让守卫在 RANGE 下失效。

需要你裁决: (a) 与 (b) 各选一个。
```

### BRI-08 —— **BUSINESS RULE ISSUE：缓慢穿越突破缓冲区时的破坏判定**（来件第 8 条）

```
关联: CISD / MSS / BOS 全部走 BreakUp / BreakDown

规则现状:
  破坏要求单根收盘价越过「参考价位 ± margin」。

缺口:
  价格若以小于 margin 的幅度逐根爬过参考价位，
  每一根的收盘都在 level 与 level+margin 之间，
  则**永远不判定为破坏**，尽管价格早已实质穿越。
  之后该摆动点可能被消费或随窗口滑出，破坏就此漏报。

两种可能的业务定义（我不替你选）:
  (a) 维持现状 —— margin 是「单根收盘必须一次性越过」的强度门槛，
      爬过去本就不算有效破坏
  (b) 改为「首次收盘越过 level 即记为破坏，margin 仅用于过滤
      同一根内的假突破」

影响范围:
  Context 的 BOS/CHOCH、CISD、MSS 全部受影响 —— 这是**核心信号定义**，
  按 Rule 65 绝不由我擅自更改。

需要你裁决: (a) 还是 (b)？若选 (b)，需要重跑全部已通过的 replay 测试。
```

---

## Audit Round 8 —— 工程师需求书附带的技术论断（2026-09-24）

### A-33 —— **单次推进被重复计为多次 BOS**（需求书 §4.1，成立）

```
Severity:                P1
Location:                HMI_SwingEngine.mqh   SwingLastUnswept()
                         HMI_H4StructureEngine.mqh  H4ConsumeSwing()
Trigger:                 一根 H4 收盘同时越过多个同向、已确认、未扫的摆动点
Expected Behavior:       一次结构推进 = 一次 BOS
Actual Behavior:         SwingLastUnswept() 从新往老返回**第一个**符合条件的点，
                         H4ConsumeSwing() 只把**那一个**标记为 swept。
                         同次穿越下方/上方的其余旧摆动点仍是未扫状态，
                         于是后续 K 线即便**没有任何新推进**也能逐根消费它们。

失效场景（已确认未扫高点 1.1000 / 1.1010 / 1.1020）:
    收盘 1.1050 -> 取 1.1020 -> BOS        strength +1
    收盘 1.1045 -> 取 1.1010 -> BOS        strength +1   (价格在下跌)
    收盘 1.1040 -> 取 1.1000 -> BOS        strength +1   (继续下跌)
  一次推进产出三次 BOS，且期间价格是回落的。

Evidence:                源码直读 + 上述可推演场景。
                         旁证：用户 USDCAD 面板显示 str 17，
                         数值高得反常，与本缺陷方向一致。
Impact:                  1) g_ctx_strength 系统性虚高 —— 面板强度不可信
                         2) 每次 BOS 触发 TRNewVersion()，Trading Range 版本虚增
                         3) 旧摆动点被提前消费，之后真正跌破该水平时不再产生事件
                         4) CTX_TRANSITION 下可用一个**早已被越过**的旧水平
                            确认反转（需求书 §4.2 称为「回退补计」）
                            —— 这会改变 Context 状态，进而改变 CtxDirection()，
                            进而改变 POIOnBar() 是否建 POI
Historical Repaint:      NO
Future Leak:             NO
Business Logic Impact:   **YES —— 修复会改变 Context 与全部下游信号**
Status:                  **OPEN —— 属 v2.00 级变更，见下方评估**
Confidence:              HIGH
```

### A-34 —— **面板 ATR 游标与结构引擎游标不一致**（需求书 §3，成立）

```
Severity:                P2
Location:                HMI_Ranges.mqh RangesATRText()   使用 g_h4_atr[g_h4_n - 1]
                         H4M5_Identification.mq5 Phase 0  使用 g_h4_cursor
Actual Behavior:         SeriesAppend() 把新 H4 追加进 g_h4 后 g_h4_n 立即增大，
                         但 Phase 0 只在 H4VisibleTo() 允许时才推进 g_h4_cursor。
                         两者之间存在窗口：面板显示的是**尚未送入结构引擎**
                         的那根 H4 的 ATR，而 Context / strength / messy
                         仍停留在旧游标的状态。
Impact:                  面板同一行里混合了两个时点的数据
Business Logic Impact:   NO（仅显示）
Recommended Fix:         面板一律读 g_h4_cursor - 1，与结构状态同源
Status:                  **OPEN**
Confidence:              HIGH
```

### 对需求书 §9.1 的更正

```
需求书称「ObjectCreate 返回 true 不代表首次创建」。

我无法从这里查证 MQL5 的确切语义（本环境无 MT5），但有反证：
  若 ObjectCreate 对已存在对象返回 true，则 OM_Rect / OM_Text / OM_Level
  的 `else OM_Register(name)` 会在**每次同步**重新登记每一个对象。
  用户对象列表中有 321 个对象，而 InpObjectHistoryLimit = 500 ——
  两次同步内 g_obj_n 就会越过 500，OM_Trim 将持续删除标记，
  图表从第一天起就不可能稳定。实测并非如此。

  故 ObjectCreate 对已存在对象**大概率返回 false**，
  A-26 的机制（OM_Preview 删除后漏注销）成立，
  而「每次创建都重复登记」不成立。

不过：**按名唯一登记本身是正确的防御性要求，与语义无关。**
无论 ObjectCreate 如何返回，OM_Register 都应先查重。
建议采纳该要求，本条更正只针对机制描述，不反对该修改。
```

### A-35 —— **测试工具缺陷：LIVE vs BUILD 把不可比的实时行也算作缺失**

```
Severity:                P1（会把排序问题误报为未来函数）
Location:                tools/ReloadTest.ps1  Show-LiveVsBuild()
Trigger:                 2026-09-25 首次 v2.40 实测，USDJPY,M5
Actual Behavior:         重建窗口 to=2026.09.25 15:50（最后一根 15:55 收盘），
                         实时 BPR 确认于 16:00（15:55 开盘那根）。
                         重建发生在该 K 线收盘之前，不可能包含它，
                         脚本却报「1 LIVE mark do NOT appear in the rebuild」。
                         同类问题还有两种：旧版本（v2.21）留下的实时行
                         与新版本重建比较；窗口滑动后已移出窗口的实时行。
Evidence:                用户实测截图；时间关系可逐根推算。
Future Leak:             NO —— 该条不构成未来函数证据
Recommended Fix:         按日志先后与版本给每条实时行分类，只比对
                         「同版本、早于最后一次重建、落在重建窗口内」的行；
                         其余分别报告为 after rebuild / other version / aged out。
Status:                  **FIXED —— 脚本层**
Confidence:              HIGH
```

附带排除一个疑点：v2.36 的 OHLC 校验读取的是 g_m5 / g_h4 中最后一根
**已收盘** K 线（SeriesLoad / SeriesAppend 均从 shift 1 取数），
不会因当前 K 线跳动而每 tick 触发重建。

### A-36 —— **挂载时同一窗口连续重建 13 次**（2026-09-25 实测，Potential Risk）

```
Severity:                P3（性能 / 日志噪声；未见结果差异）
Location:                H4M5_Identification.mq5  OnCalculate() 的两条重建路径：
                         prev_calculated == 0，或 SeriesAppend() 返回 SA_RELOAD
Trigger:                 XAUUSD,M5 首次挂载 v2.40（本地 12:24:57）
Actual Behavior:         `starting on` 1 次，`HMI-BUILD-BEGIN` 16 次。
                         其中 13 次在 12:24:57.492 – 12:24:58.547 之间（约 1.1 秒），
                         窗口完全相同（from=09.01 09:10, to=09.25 14:15），
                         每次 130 行。之后 3 次分别在 to=15:50 / 16:00 / 17:30，
                         其中 15:50、17:30 与其余所有图表同时发生（终端级事件）。
Evidence:                用户日志检索（两个计数 + 前 20 行）。
Future Leak:             NO —— 每次都是完整重建，13 次结果行数相同；
                         重建不改变已写出的实时行，LIVE vs BUILD 比对不受影响。
Reasoning:               两条路径都不打印原因，日志无法区分。最可能的解释是
                         挂载时终端仍在同步 XAUUSD 的历史：同步期间终端反复以
                         prev_calculated = 0 调用，或缓存中最后一根 K 线被同步
                         修正而触发 A-32 的 OHLC 校验。两者都是 A-32 设计的正确反应。
                         另见一个次要竞态：iBarShift 与按位置 CopyRates 之间若恰好
                         开新 K 线，sh 偏移 1，时间比对不符 → 多一次重建（无害）。
Impact:                  挂载后约 1 秒的重复计算与图形重画；稳态下未见重复
                         （之后约 3 小时仅 3 次，2 次为全图表同时）。
Recommended Fix:         暂不修改。若稳态下出现连续重建，再加一行诊断日志
                         HMI-RELOAD,<sym>,reason=PREV0|H4_GONE|H4_REVISED|M5_GONE|M5_REVISED
                         （仅日志，需升版本号，会使现有实时样本归入 other version）。
Status:                  **Potential Risk —— 观察中**
Confidence:              MEDIUM（原因为推断，现象为实测）
```
