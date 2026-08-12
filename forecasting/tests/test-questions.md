> ⚠️ 已迁入 `eval/cases/forecasting.yaml`（统一评估集）。本文件为历史存档，不再维护，仅作题源追溯。新题请加到 `eval/cases/`。

# 预报 Skill 测试问题集（v1，技术向，SQL 可验证）

> **测试对象**: SmartTwinRes-skills/forecasting/
> **数据基础**: 三岔水库（成都市东部新区），powerelf_srm_yml 数据库（127.0.0.1:3306）
> **设计原则**: 技术向、SQL 可验证、每题标 expected 数据点（供 Task 9 eval 逐点核对）
> **生成日期**: 2026-06-22
> **配套**: v2 业务向口语题见 `test-questions-v2.md`；极端题所需数据见 `data/scenarios/*.sql`

---

## 水库基础信息（三岔基线，供 expected 数据点引用）

| 属性 | 值 | 来源/SQL |
|------|-----|---------|
| 水库名称 | 三岔水库 | att_res_base |
| 流域面积 | 161.25 km² | att_res_base |
| 正常蓄水位 / 汛限（主汛期） | 462.500 m | `att_res_flse_lim` flood_season_name='主汛期'；兜底 `att_res_base.fl_low_lim_lev` |
| 设计洪水位 | 461.960 m | 工程设计（仅参考） |
| 校核洪水位 | 462.880 m | `model_config` config_key='max_water_level'，tenant_id=18 |
| 死水位 | 451.000 m | `model_config` config_key='min_water_level'，tenant_id=18 |
| 下游安全泄量 | 95.1 m³/s | 工程设计（仅参考） |
| 最大下泄能力 | 191/192 m³/s | att_res_discharge_curve |
| 水位 master stcd | '3' | `model_config` config_key='st_rsvr_r_master' |
| 雨量 master stcd | '46' | `model_config` config_key='st_pptn_r_master' |

> ⚠️ 上述阈值仅供 expected 核对；判定逻辑必须从 `model_config` / `att_res_flse_lim` 动态读取，**严禁硬编码**。

---

## 一、预报解读类（Easy）

### Q1: 未来 24h 逐时降雨预报
**问题**: 未来 24 小时三岔水库流域的逐时降雨预报情况如何？峰值雨强出现在什么时候？
**Expected 数据点**:
- 命中 `f_rnfl_h`，无 tenant 过滤（该表无 tenant_id 列）
- 取最新批次：先 `MAX(FYMDH)`，再按 `YMDH BETWEEN NOW() AND NOW()+24h` 取行
- `RN` 列名大写
- 给出峰值 RN（mm/h）及其 YMDH 时刻
**验证 SQL**: `SELECT RN, YMDH, FYMDH FROM f_rnfl_h WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 24 HOUR) AND deleted=0 ORDER BY YMDH LIMIT 1000`

### Q2: 降雨预报累计量与预警等级
**问题**: 未来 48 小时累计预报降雨量是多少？是否达到暴雨/大暴雨/红色预警级别（>100mm/24h）？
**Expected 数据点**:
- SUM(RN) over YMDH ∈ [NOW, NOW+48h]
- ≥100mm/24h → 标注"红色预警级别"（与 `data/scenarios/extreme_storm.sql` 对齐）
- 判据应可配置，不硬编码 100
**验证 SQL**: `SELECT SUM(RN) AS total_mm FROM f_rnfl_h WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 48 HOUR) AND deleted=0`

### Q3: 预报雨强分布与峰值时刻
**问题**: 预报的最大小时雨强（mm/h）是多少？出现在未来第几小时？
**Expected 数据点**: `MAX(RN)` + 对应 YMDH - NOW() 的小时差
**验证 SQL**: `SELECT MAX(RN) AS peak_rn, SUBSTRING_INDEX(GROUP_CONCAT(YMDH ORDER BY RN DESC), ',', 1) AS peak_at FROM f_rnfl_h WHERE YMDH>NOW() AND deleted=0`

### Q4: 预报时效覆盖
**问题**: 当前降雨预报覆盖到未来多长时间？是否存在覆盖断档？
**Expected 数据点**: `MAX(YMDH)` - NOW() 小时数；若 <72h 应提示"预见期不足"
**验证 SQL**: `SELECT MIN(YMDH), MAX(YMDH), COUNT(*) FROM f_rnfl_h WHERE YMDH>NOW() AND deleted=0`

### Q5: 预报发布时间（陈旧判定）
**问题**: 当前降雨预报是什么时候发布的？距今多久？
**Expected 数据点**: `MAX(FYMDH)` 及其与 NOW() 的差值；若 >6h 应触发"陈旧预报"提示（对应 `data/scenarios/stale_forecast.sql`）
**验证 SQL**: `SELECT MAX(FYMDH) AS latest_issue, TIMESTAMPDIFF(HOUR, MAX(FYMDH), NOW()) AS age_h FROM f_rnfl_h WHERE deleted=0`

---

## 二、水库影响类（Medium）

### Q6: 预报降雨对水位的预期影响
**问题**: 若未来 24h 降雨预报累计 100mm，预计三岔水库水位会上涨多少？
**Expected 数据点**:
- 流域面积 161.25 km²（从 att_res_base 动态读）
- 估算入库增量 = 降雨量 × 面积 × 径流系数（不硬编码）
- 通过水位-库容曲线（att_res_stag_cap_disc）推算水位抬升
- 不硬编码当前水位，从 st_rsvr_r 最新行读

### Q7: 当前水位与汛限距离
**问题**: 当前水位距汛限水位 462.500m 还有多少余量？按预报降雨是否可能超汛限？
**Expected 数据点**:
- 当前 rz（st_rsvr_r 最新，master stcd='3'，不硬编码）
- 汛限从 `att_res_flse_lim`/`att_res_base.fl_low_lim_lev` 读，值约 462.500
- 余量 = 汛限 - rz（约 3.32m 量级）
- 给出"按预报降雨是否逼近汛限"的判断

### Q8: 是否逼近死水位
**问题**: 当前水位距离死水位 451m 有多远？长期无雨情况下水位会如何变化？（对应 `data/scenarios/drought.sql`）
**Expected 数据点**:
- 当前 rz - 死水位(451) 余量
- 死水位从 `model_config` config_key='min_water_level' 读，不硬编码
- 若 rz ≤ 死水位 + 1m → 提示"逼近死水位，兴利风险"

### Q9: 入库/出库流量对比
**问题**: 当前入库流量与出库流量是多少？水库是在蓄水还是泄水？
**Expected 数据点**: st_rsvr_r 最新行 `inq` / `otq`；`inq > otq` → 蓄水
**验证 SQL**: `SELECT rz, inq, otq, tm FROM st_rsvr_r WHERE rz IS NOT NULL ORDER BY tm DESC LIMIT 1`

### Q10: 库容与水位关系
**问题**: 当前水位对应的蓄水量（库容）是多少？距汛限水位对应的库容还有多少蓄量空间？
**Expected 数据点**: 当前 `w`（st_rsvr_r）+ 水位-库容曲线 `att_res_stag_cap_disc` 在汛限点插值
**验证 SQL**: `SELECT stag, cap FROM att_res_stag_cap_disc WHERE stag <= (SELECT rz FROM st_rsvr_r ORDER BY tm DESC LIMIT 1) ORDER BY stag DESC LIMIT 1`

---

## 三、多源融合类（Hard）

### Q11: 四源降雨预报对比
**问题**: 和风（f_rnfl_h）、分区预报（st_pptn_re_forecast）、实测降雨（st_pptn_r）当前对未来同一时段的预报/实测是否一致？分歧有多大？
**Expected 数据点**:
- f_rnfl_h：按 YMDH 聚合 RN
- st_pptn_re_forecast：按 tm 聚合 drp（多 re_id 取均值）
- st_pptn_r：实测 drp（仅过去时段）
- 源间差 >20mm → 标注"四源分歧"（对应 `data/scenarios/source_disagreement.sql`）

### Q12: 多源融合判定与建议
**问题**: 当和风预报与分区预报分歧 >20mm 时，应采信哪一方？融合策略是什么？
**Expected 数据点**:
- 提出融合策略（取均值/取最大/按历史精度加权）
- 不编造单一"正确源"
- 关联 `forecast_accuracy_record` 按源 MAPE 加权（若数据足够）

### Q13: 实测对照预报（偏差分析）
**问题**: 过去 24 小时实测降雨与同期预报降雨的偏差（MAE/MAPE）是多少？
**Expected 数据点**:
- forecast_timeline 思路：f_rnfl_h 中 YMDH 已过去的行（预报值）vs st_pptn_r 同 tm 的 drp（实测值）
- 需存在 forecast-observed 同 tm 重叠行（对应 `data/scenarios/extreme_storm.sql` 的重叠段）
- MAE = AVG(|forecast - actual|)

### Q14: NMC 中央台预报对照
**问题**: NMC 中央气象台 24h 降雨预报（fixture）与和风预报是否一致？谁更激进？
**Expected 数据点**:
- 读取 `data/scenarios/nmc_rainfall_24.json`（JSONP fixture）
- 与 f_rnfl_h 最新 24h SUM(RN) 对比
- 给出"哪源更激进"的判断

### Q15: 模型预报来水过程
**问题**: 模型预报的未来入库流量过程线（st_mx_preset_cal_r type=21）是什么？峰值流量多少？
**Expected 数据点**:
- JOIN `model_result_files`（type=1，最新 create_time）`st_mx_preset_cal_r`（type='21'）
- JOIN 时 `ON s.taskid = CAST(m.taskid AS CHAR)`
- 给出峰值 vals 与对应 tm

---

## 四、趋势预测类（Medium）

### Q16: 未来 12h 水位趋势
**问题**: 按当前入库/出库流量与降雨预报，未来 12 小时水位会怎么变？会上涨还是回落？
**Expected 数据点**:
- 当前 rz / inq / otq（st_rsvr_r 最新）
- 未来降雨累计（f_rnfl_h NOW→NOW+12h SUM(RN)）
- 模型水位过程线 `st_mx_preset_cal_r` type='22'
- 给出趋势方向（涨/落）与幅度量级

### Q17: 削峰率估算
**问题**: 若入库洪峰为 X m³/s（从模型预报读），当前出库能力下的削峰率是多少？
**Expected 数据点**:
- 入库洪峰 = MAX(st_mx_preset_cal_r type='21' vals)
- 出库能力 ≤ 安全泄量 95.1 m³/s（工程设计参考，不硬编码进判定）
- 削峰率 = (洪峰 - 出库) / 洪峰

### Q18: 何时达峰
**问题**: 预报的水位/流量峰值出现在未来第几小时？
**Expected 数据点**: `st_mx_preset_cal_r` type='22' 的 MAX(vals) 对应 tm
**验证 SQL**: `SELECT tm, vals FROM st_mx_preset_cal_r WHERE type='22' AND taskid LIKE 'MOCK%' ORDER BY vals DESC LIMIT 1`

### Q19: 趋势预警阈值
**问题**: 若预报水位将超过设计洪水位 461.96m / 校核洪水位 462.88m，应在什么时刻触发预警？
**Expected 数据点**:
- 阈值从 model_config `max_water_level` 读（=462.88），不硬编码 461.96/462.88
- 给出超过阈值的最早 tm
**验证 SQL**: `SELECT MIN(tm) FROM st_mx_preset_cal_r WHERE type='22' AND vals > 462.88 AND taskid LIKE 'MOCK%'`

### Q20: 回退/退水段判断
**问题**: 预报的水位过程线什么时候开始退水？退水速率多少？
**Expected 数据点**: vals 由升转降的拐点 tm，退水段斜率
**验证 SQL**: `SELECT tm, vals FROM st_mx_preset_cal_r WHERE type='22' AND taskid LIKE 'MOCK%' ORDER BY tm`

---

## 五、预报精度类（gated，专测"数据不足"路径）

### Q21: 各源历史预报精度
**问题**: 和风/NMC/模型各预报源的历史平均精度（MAPE）是多少？
**Expected 数据点**:
- **这是 gated 路径测试题**：`forecast_accuracy_record` 在本地为 mock 60 行，但现网/部分环境可能为空
- 数据足够 → 按 source 聚合 AVG(mape)，置信分级（<15% 高 / 15-30% 中 / >30% 低）
- 数据不足 → 返回 `status: insufficient`，**绝不编造精度数字**
**验证 SQL**: `SELECT source, AVG(mape) FROM forecast_accuracy_record WHERE deleted=0 GROUP BY source`

### Q22: 精度不足时的响应（gated）
**问题**: 如果预报精度数据不足以统计（记录 <10 条），系统应该如何响应？
**Expected 数据点**:
- 预期返回 gated 结构 `{status: "insufficient", available: <n>, threshold: 10}`
- 明确提示"数据不足，无法给出可信精度评估"
- **这是 Task 2 gated 机制的预期行为**，不是 bug

### Q23: 预报-实测偏差时序
**问题**: 过去 7 天预报与实测降雨的逐日偏差趋势是改善还是恶化？
**Expected 数据点**:
- 需 forecast-observed 重叠时段（extreme_storm.sql 重叠段提供）
- 按日聚合 |forecast-actual|/actual
- 若重叠不足 → gated

### Q24: 精度置信分级
**问题**: 当前预报源的精度置信度（高/中/低）如何？
**Expected 数据点**: MAPE → 置信分级映射（<15% 高 / 15-30% 中 / >30% 低），不硬编码阈值

### Q25: 精度门控触发条件
**问题**: 什么条件下系统会判定"精度数据不足"？阈值是多少？
**Expected 数据点**:
- 记录数 < threshold（threshold 可配置，默认 10）
- 或某源在该时间窗内完全无记录
- 返回 gated 而非编造

---

## 六、历史相似洪水类（Medium）

### Q26: 历史相似洪水匹配
**问题**: 当前预报未来 24h 降雨 100mm、起调水位约 459m，历史上有没有降雨量级和起调水位相似的洪水？
**Expected 数据点**:
- 查 `srm_flood_history_base`，按 `adjusted_water_level`（峰值代理列）近 459m + rainfall_data JSON 降雨量近 100mm 排序
- 返回相似洪水列表（name/start_time/adjusted_water_level）

### Q27: 历史洪水削峰率参考
**问题**: 历史洪水中削峰率最高的是哪一场？当时是怎么调度的？
**Expected 数据点**:
- 查 `srm_flood_history_base` status=2（完成）的记录
- 削峰率 = (入库洪峰 - 出库) / 入库洪峰（从 rainfall_data 或相关字段）

### Q28: 相似洪水的调度经验
**问题**: 与当前条件最相似的历史洪水，当时的调度策略是什么？可借鉴什么？
**Expected 数据点**:
- 命中 Q26 找到的相似洪水
- 提取其调度参数（闸门开度、目标水位等）

### Q29: 历史洪水覆盖完整性
**问题**: 系统中有多少条历史洪水记录？哪些已完成计算（status=2）？
**Expected 数据点**: COUNT by status
**验证 SQL**: `SELECT status, COUNT(*) FROM srm_flood_history_base WHERE deleted=0 GROUP BY status`

### Q30: 历史洪水降雨特征
**问题**: 历史洪水的降雨历时与峰值雨强有什么分布规律？
**Expected 数据点**:
- 从 rainfall_data JSON 解析历时与峰值
- 给出"短历时强降雨" vs "长历时绵绵雨"的归类

---

## 七、预报管理类（Easy/Medium）

### Q31: 预报任务列表
**问题**: 最近有哪些预报任务（model_result_files type=1）？最新一次是什么时候？
**Expected 数据点**: type=1（无 deleted 列），按 create_time DESC
**验证 SQL**: `SELECT taskid, create_time, target_water_level, adjusted_water_level FROM model_result_files WHERE type=1 AND tenant_id=18 ORDER BY create_time DESC LIMIT 10`

### Q32: 预报文件关联的过程线
**问题**: 给定一个预报 taskid，如何取其完整来水过程线？
**Expected 数据点**:
- JOIN `model_result_files`(taskid) → `st_mx_preset_cal_r`(taskid)
- JOIN 时 `ON s.taskid = CAST(m.taskid AS CHAR)`（taskid varbinary vs varchar）
- type IN ('21','22')

### Q33: 预报配置项
**问题**: 预报相关的系统配置（master stcd、水位阈值、预报文件名）有哪些？
**Expected 数据点**:
- `model_config` config_key IN ('st_rsvr_r_master','st_pptn_r_master','max_water_level','min_water_level','Forecast_Q')
- tenant_id=18 优先
**验证 SQL**: `SELECT config_key, value FROM model_config WHERE tenant_id=18 AND config_key LIKE '%master%' OR config_key IN ('max_water_level','min_water_level','Forecast_Q') AND deleted=0`

### Q34: 预报批次管理
**问题**: f_rnfl_h 中有多少个预报批次（FYMDH）？最新批次覆盖多少小时？
**Expected 数据点**: COUNT(DISTINCT FYMDH)，最新批次的 YMDH 覆盖数
**验证 SQL**: `SELECT COUNT(DISTINCT FYMDH), MAX(FYMDH) FROM f_rnfl_h`

### Q35: 预报数据清理
**问题**: 如何识别和清理 mock 预报数据（不影响真实数据）？
**Expected 数据点**:
- f_rnfl_h: `COMMENTS='MOCK'`
- st_rsvr_r/st_pptn_r: `creator='MOCK'`
- st_pptn_re_forecast: `re_id>=9000`
- model_result_files/st_mx_preset_cal_r: `taskid LIKE 'MOCK%'` / `alias='MOCK'`
- 提供一键清理 SQL

---

## 八、综合场景类（含极端，Expert）

> ⚠️ 本类题目依赖 `data/scenarios/*.sql` 灌入的极端场景数据。运行 eval 前需先 load 全部 scenario seed。

### Q36: 红色预警级别暴雨应对
**问题**: 当前预报未来 24h 降雨 130mm（>100mm 红色预警级别），水库应如何响应？（对应 `extreme_storm.sql`）
**Expected 数据点**:
- f_rnfl_h SUM(RN) NOW→NOW+24h ≈ 130mm
- 当前水位（st_rsvr_r 最新）
- 预报水位过程线（st_mx_preset_cal_r type='22'）
- 判断是否逼近汛限 462.500，给出调度建议

### Q37: 长期干旱应对
**问题**: 过去 7 天几乎无降雨、水位逼近死水位 451m，应如何调度保供水？（对应 `drought.sql`）
**Expected 数据点**:
- st_pptn_r 近 7d SUM(drp) ≈ 0
- st_rsvr_r rz 接近 451（死水位，model_config 读）
- 建议兴利保供，减少下泄

### Q38: 四源分歧下的决策
**问题**: 和风预报 24h 120mm，分区预报仅 60mm，分歧 60mm。应如何采信？（对应 `source_disagreement.sql`）
**Expected 数据点**:
- f_rnfl_h SUM(RN) vs st_pptn_re_forecast AVG(drp) 同 tm 差 >20mm
- 给出融合策略与保守/激进方案对比

### Q39: 预报有实测空
**问题**: 预报显示某时段有降雨，但该时段已过且实测降雨为空。是预报失败还是实测缺失？（对应 `null_actual.sql`）
**Expected 数据点**:
- f_rnfl_h 过去时段 YMDH 有 RN>0
- st_pptn_r 同 tm 无记录或 drp 为 NULL
- 判断"实测缺失"而非"预报失败"，提示数据质量问题

### Q40: 水位超汛限紧急调度
**问题**: 当前水位已达 462.8m，超过汛限 462.5m 且逼近校核洪水位 462.88m。应如何紧急调度？（对应 `over_flood_limit.sql`）
**Expected 数据点**:
- st_rsvr_r rz ≥ 462.5（汛限，att_res_flse_lim 读）
- 紧急模式：最大泄流，受安全泄量 95.1 m³/s 约束
- 给出下泄方案与风险提示

### Q41: 陈旧预报识别
**问题**: 当前降雨预报的发布时间（FYMDH）距今已超过 6 小时。预报是否可信？应如何处理？（对应 `stale_forecast.sql`）
**Expected 数据点**:
- MAX(FYMDH) 距 NOW() >6h
- 触发"陈旧预报"提示，建议等待新批次或降权使用
- 给出处理建议

### Q42: 复合极端场景
**问题**: 同时遭遇：暴雨红色预警 + 水位逼近汛限 + 四源分歧 + 陈旧预报。应如何综合研判与决策？
**Expected 数据点**:
- 综合 Q36+Q38+Q40+Q41
- 多维交叉风险标注
- 给出最保守调度建议（宁可错防）

### Q43: 预报失效边界
**问题**: 当预报数据完全缺失（f_rnfl_h 无未来行）时，系统应如何降级响应？
**Expected 数据点**:
- f_rnfl_h YMDH>NOW() COUNT=0
- 降级策略：基于实测 + 历史相似 + 当前水位生成保守方案
- 明确提示"无降雨预报，结果仅供参考"

### Q44: 预报-实测重叠段偏差
**问题**: 在暴雨事件中，预报与实测同 tm 重叠段的偏差有多大？是否系统性偏大/偏小？
**Expected 数据点**:
- extreme_storm.sql 提供的同 tm 重叠小时
- 计算偏差方向（系统性偏大/偏小）
- 给出预报校准建议

### Q45: 极端退水段风险
**问题**: 暴雨峰值过后，退水段若持续高水位，泄流能力是否足够？会不会超安全泄量？
**Expected 数据点**:
- st_mx_preset_cal_r type='21' 退水段 otq
- 安全泄量 95.1 m³/s（工程设计参考，不硬编码）
- 若 otq > 95.1 → 提示"超安全泄量，下游风险"

---

## 问题统计

| 类别 | 数量 | 难度 | 依赖 scenario |
|------|------|------|--------------|
| 预报解读 | 5 | Easy | stale_forecast |
| 水库影响 | 5 | Medium | drought |
| 多源融合 | 5 | Hard | source_disagreement, extreme_storm |
| 趋势预测 | 5 | Medium | — |
| 预报精度（gated） | 5 | Medium | — |
| 历史相似洪水 | 5 | Medium | — |
| 预报管理 | 5 | Easy | — |
| 综合场景（含极端） | 10 | Expert | extreme_storm, drought, source_disagreement, null_actual, over_flood_limit, stale_forecast |
| **合计** | **45** | | |

---

## Expected 数据点核对约定（供 Task 9 eval）

- 每个 Q 的 `Expected 数据点` 列出 eval 应在响应中核到的关键事实
- **数值类**：核对响应中是否给出该数值（或量级正确），允许 ±5% 容差
- **判定类**：核对响应中的方向性判断（涨/落、安全/危险、采信哪源）
- **gated 类（Q21-Q25）**：核对是否走"数据不足"分支（若环境数据不足）或给出精度数字（若数据足够），两者择一即可
- **SQL 类**：核对响应中给出的 SQL 是否命中正确的表与列（列名大小写、tenant 过滤、deleted 处理）

---

*生成时间: 2026-06-22*
*数据库: powerelf_srm_yml (127.0.0.1:3306)*
*水库: 三岔水库（成都市东部新区）*
*配套: data/scenarios/*.sql（极端场景 seed）*
