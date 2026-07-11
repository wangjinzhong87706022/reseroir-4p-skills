---
name: forecasting
description: "水库水文预报智能解读：降雨预报解读、水库影响估算、多源预报融合、水位趋势预测、预报精度评估、三岔水库预报决策。"
version: 1.0.0
author: SmartTwinRes Team
license: MIT
platforms: [linux, windows, macos]
metadata:
  hermes:
    tags: [water-conservancy, forecast, rainfall, hydrology]
    related_skills: []
prerequisites:
  env_vars: [SRM_DB_HOST, SRM_DB_PORT, SRM_DB_NAME, SRM_DB_USER, SRM_DB_PASSWORD]
---

# 水库水文预报智能解读 Skill v1.0

## TL;DR（最高优先，先读，每次回答都遵守）

> **每个回答必须 = 3 段，缺一即不合格**：
> ① **【依据】**开头 —— 一句话引《水文情报预报规范》**GB/T 22482**（如"依据 GB/T 22482 与预报规则…"）；
> ② **【分析】**中段 —— 核心数值与判断（≤6 行，结论先行）；
> ③ **【校验与依据】**结尾（**回答绝对最后内容**）—— **必须含 GB/T 22482 引用 + 安全校验（水位 vs 汛限 + 置信度）**。
>
> ⛔ **收尾段缺失或不含 GB/T 22482 = 整题不合格（E2/E4 双失）**。无论前面查询多繁，篇幅紧张就精简分析段保结尾段。
> 📌 数据只读 `query_forecast_data.py`（三岔 tenant 18，水位 ~460m 量级）；**勿自行查全库**（会混入非三岔站的 ~240m 数据）。

## 数据源优先级告警

> **⚠️ 数据源优先级（必须遵守）**：三岔水库的所有预报/实况/汛限/精度/历史数据**必须从本 skill 的 `scripts/query_forecast_data.py` 与 `scripts/query_forecast_analysis.py` 获取**（查询 `powerelf_srm_yml` 数据库）。**禁止**混用 water-situation / water-warning / rainfall / plan-generation 等 skill 的数据源——它们查询的是 `sl323` 全区域河道站或 `model_result_files(type=2)` 调度结果，不适用于水文预报解读。本 skill 只读 `model_result_files(type=1)` 预报来水过程，**不触发任何模型计算**。

## ⛔ 输出蓝图（开始分析前先规划这 3 段，分析后逐段填充）

> ⚡ **精炼输出（降生成延迟，弱端点必需）**：核心结论先行，**每段 ≤ 6 行**，只给关键数值与判断；**勿逐时罗列 72h 数据、勿铺大表**（需要时只取峰值/总量 2-3 个数）。长输出在弱本地端点下易超时卡死。

**无论什么预报任务，最终回答都必须包含这 3 段（按顺序），结尾段是回答合格的硬性标志：**

1. **【依据】**（开头）— 引出本次预报解读的规范框架：
   `依据《水文情报预报规范》GB/T 22482 与预报规则，对[本任务]分析如下：`

2. **【分析】**（中间）— 任务核心内容（见下方分类型填充表）

3. **【校验与依据】**（结尾，**必填模板，必须是回答的绝对最后内容**）：
   ```
   【安全校验】当前水位 {current_rz}m（取自 full_context.current_water_level.rz 字段），
     距汛限水位 {flood_limit}m（取自 full_context.flood_limit.value 字段）还有 Δm，[未超限/接近/超限]；
     多源融合置信度 [高/中/低]，源间分歧小时数 {disagreement_hours}（取自 fusion_detail 返回字段）。
   【精度状态】MAPE={avg_mape}（取自 accuracy_report.avg_mape 字段，gated 时标"精度待评定"）；
     置信度 [高/中/低]（依 forecast-rules.md 置信度模型）。
   【法规依据】依 GB/T 22482《水文情报预报规范》精度评定与发布原则，[预报结论可用/需人工复核/仅供参考]。
   ```

> ⛔ **参数取值规则（铁律）**：汛限水位、设计/校核洪水位、预警阈值、降雨阈值、精度阈值等**所有约束值一律从你已拿到的 `full_context` / `model_config` / `accuracy_report` / `fusion_detail` 返回 JSON 里读对应字段填入**（如 `{flood_limit}`、`{warning_red_level}`、`{mape_high_threshold}`）。**严禁照抄本 skill 里出现的任何参考数字**——本 skill 正文及 `references/` 中出现的趋势预警水位、三岔特征水位、降雨/精度阈值等**仅是"参考标注"**（具体数值见 `references/forecast-rules.md` 第七节与 `references/table-schema.md` 末尾的"参考值"表），不是三岔实测阈值，照抄进判定即错。安全校验是**纯文字填写**，**绝不为它另写 Python / execute_code**（多余代码会拖慢甚至卡死回答）。

> ⛔ **结尾段优先**：无论前面查询/计算多繁重，**【校验与依据】必须是回答最后内容**。篇幅紧张就精简分析段保结尾段——结尾段缺失 = 整题不合格（E2/E4 双失）。

### 各任务类型的【分析】段内容

| 任务类型 | 第 2 段【分析】应包含 | 第 3 段引用侧重 |
|---------|----------------------|-----------------|
| 预报解读 | 降雨预报量级 + 时序 + 预见期 + 数据源 | GB/T 22482 + forecast-rules.md |
| 水库影响估算 | 预报降雨→入库流量→水位趋势 + 触发区间（规则 6 命中时出【估算值 ±20%】） | forecast-rules.md（规则 6/7） |
| 多源融合 | 四源对齐表 + 分歧统计 + 采信裁决 + 各源置信度 | multi-source-fusion.md |
| 趋势预测 | 水位过程线 + 预报峰值 + 预见期标注 + 越限判断 | forecast-rules.md（规则 1/3） |
| 预报精度 | 按源 MAPE + 合格率 + 置信分级 + gated 状态（空表绝不编数字） | GB/T 22482 + knowledge-base.md |
| 实况 / 知识问答 | 直接回答（当前水位 / 气象预警 / 汛限） | 简短即可，但涉及水位仍须结尾安全校验 |

> 💡 **工作流**：先写第 1 段 → 做完整分析填第 2 段 → **必须**写第 3 段。即使第 2 段是"无数据""预报陈旧""纯知识问答"，只要涉及水位/预报，第 3 段也不得省略。

**法规 / 标准库（填第 1/3 段时复制使用，述原则不编条款号）：**
- 《水文情报预报规范》**GB/T 22482** — 预报精度评定（合格率 / MAPE）、预见期与发布规范（最直接国标依据）
- 《水文情报预报规范》**SL 250-2000** — 行业版，误差量级与 GB/T 22482 同源
- 《防洪法》— 汛期不得擅自在汛限水位以上蓄水；洪水预报由水文机构发布
- 《水库大坝安全管理条例》— 设计/校核洪水位须经安全鉴定确定
- GB/T 50138-2010《水位观测标准》— 观测精度影响预报输入质量
- 预报规则 — 预警等级 / 置信度 / 影响估算触发（见下方"预报规则速查"与 `references/forecast-rules.md`）

## 第一步 — 判断场景（决策路由）

根据用户意图选择场景、查询策略与知识参考（5 意图 + 实况）：

| 用户意图 | 场景分类 | 查询策略 | 知识参考 |
|---------|---------|---------|---------|
| 未来降雨/水位预报如何 | 预报解读 | 快捷路径：`--type full_context` | forecast-rules.md |
| 这场雨对水库影响多大、要不要预泄 | 水库影响估算 | 快捷路径：`full_context` + 场景脚本 `query_forecast_analysis.py --type fusion_detail` | forecast-rules.md（规则 6/7） |
| 几个源报的不一样、采信哪个 | 多源融合 | 场景脚本：`query_forecast_analysis.py --type fusion_detail` | multi-source-fusion.md |
| 未来水位趋势、会不会超汛限 | 趋势预测 | `full_context` + `--type water_level_curve` + `--type model_forecast_result` | forecast-rules.md（规则 1/3） |
| 预报准不准、精度多少 | 预报精度 | 场景脚本：`query_forecast_analysis.py --type accuracy_report`（gated） | knowledge-base.md + forecast-rules.md（规则 5） |
| 当前水位多少、有无气象预警 | 实况查询 | 快捷路径：`--type full_context`（取 current_water_level + weather_warning） | 直答，仍需结尾安全校验 |
| 预报和实测差多少 | 预报对照 | 场景脚本：`query_forecast_analysis.py --type forecast_timeline` | multi-source-fusion.md |
| 历史上类似水位发生过什么 | 历史类比 | 场景脚本：`query_forecast_analysis.py --type similar_floods --water-level {值}` | forecast-rules.md |
| 多源降雨宏观对比 | 多源聚合 | `full_context` + `--type multi_source_overview`（或 `fusion_detail`） | multi-source-fusion.md |
| 预报发布规范 / 精度评定原则 | 知识问答 | 不查库，直接读知识 | knowledge-base.md |

> ⛔ **字段读取措辞（防 execute_code 死循环）**：回答时凡提到阈值/约束，措辞一律"**full_context 返回的 `flood_limit` 字段**""**accuracy_report 返回的 `avg_mape` 字段**"。**严禁**写"去查询汛限水位""去计算 MAPE"——这类措辞会触发 Hermes 反复调 execute_code 直到卡死。阈值已在你执行 `--type full_context` / `accuracy_report` 时一次性取回，**直接读字段填入即可**。

## 第二步 — 执行查询

> **执行前必读**：脚本依赖 `pymysql` 与 `dbutils`，环境已预装。直接用 `python3` 运行脚本，**不要**先用 `import pymysql` 测试环境——每次会话浪费 3-6 次 exec 调用。脚本入口在 `${HERMES_SKILL_DIR}/scripts/`。

### 快捷路径（强烈推荐优先）

查询 `--type full_context` 一次取回 **5 类核心数据**（当前水位 + 和风降雨预报 + 汛限 + 气象预警 + 配置 + `_meta`）——**瘦身以降上下文重量/延迟**。重项按意图另取：

```bash
# 核心 5 项(预报解读/影响/趋势/实况 都够用)
python3 scripts/query_forecast_data.py --type full_context
# 按意图补取(每次最多 1~2 个,勿一次全取,以免上下文过重卡死弱端点):
#   趋势/影响 → --type water_level_curve  /  --type model_forecast_result
#   多源融合  → --type multi_source_overview  (或 query_forecast_analysis.py --type fusion_detail)
#   精度      → --type forecast_accuracy_stats  (空表自动 gated)
#   历史相似  → --type historical_floods
# 灵活参数示例:
python3 scripts/query_forecast_data.py --type rainfall_forecast --hours 168
```

> **full_context 优先 + 按需补取**：先 `full_context`（5 项核心），再按意图补 **1~2 个**专项 `--type`。**严禁一次取全部 11 类**——上下文过重会拖慢/卡死弱本地端点。

`query_forecast_data.py` 全部 12 个 `--type`：`current_water_level` / `rainfall_forecast` / `weather_warning` / `flood_limit` / `model_forecast_result` / `zonal_rainfall_forecast` / `water_level_curve` / `historical_floods` / `forecast_accuracy_stats` / `multi_source_overview` / `config` / `full_context`。

### 场景脚本（高效单任务，分析型 4 类型）

```bash
python3 scripts/query_forecast_analysis.py --type fusion_detail        # 四源逐时对齐 + 分歧标注
python3 scripts/query_forecast_analysis.py --type accuracy_report      # 按源 MAPE + 置信分级（gated）
python3 scripts/query_forecast_analysis.py --type forecast_timeline    # 预报 vs 实测对照时间轴 + bias/MAE
python3 scripts/query_forecast_analysis.py --type similar_floods --water-level 459.18
```

### 灵活路径（自定义 SQL）

三步流程：

1. 先读 `${HERMES_SKILL_DIR}/references/table-schema.md` 了解 14 张预报表结构（含 tenant/deleted/taskid 用法规则）
2. 参考 `${HERMES_SKILL_DIR}/references/sql-templates.md` 选择 Q1–Q12 / J1–J4 / A1 参数化模板
3. 替换 `{参数}` 为实际值后执行（务必遵守下方 SQL 安全规则）

## 第三步 — SQL 安全规则（灵活路径必须遵守）

1. **LIMIT**：数据提取查询（SELECT 返回多行）必须加 `LIMIT`，最大不超过 1000
2. **时间范围**：大表（⚠️ 标记：`st_rsvr_r` 19 万、`st_pptn_r` 26 万、`f_rnfl_h` 8 千、`st_mx_preset_cal_r`、`st_pptn_re_forecast`）的多行提取必须加时间范围；统计/聚合按意图区分（用户明确"全量统计"则不加，提到时间范围则按指定过滤，意图不明先确认）
3. **`deleted=0`（按表对待，不要无脑加）**：`model_result_files` / `weather_warn` / `att_res_flse_lim` **无 deleted 列 → 不要加 `AND deleted = 0`**；其余预报表（`st_*`、`f_rnfl_h`、`srm_flood_history_base`、`st_pptn_re_forecast`、`att_res_base`、`model_config`、`forecast_accuracy_record`、`weather_info`）有 deleted 列 → 加
4. **`f_rnfl_h` 不加 tenant 过滤**：该表无可用 tenant 字段，直接按 `YMDH` / `FYMDH` 时间窗口查询（`weather_info` / `weather_warn` 同样无 tenant，亦不加）
5. **taskid JOIN 必须 CAST**：三拼写不一致——`dispatch_history.task_id`（varchar 下划线）、`model_result_files.taskid`（varbinary 无下划线）、`st_mx_preset_cal_r.taskid`（varchar 无下划线）。JOIN 时 `ON s.taskid = CAST(m.taskid AS CHAR)`，否则隐式截断/类型不匹配
6. **禁止 `SELECT *`**：明确列出需要的字段
7. **只读**：禁止 `UPDATE / DELETE / INSERT / DROP / ALTER`

## 查询策略指引（按场景细化）

| 场景 | 数据范围 | 时间窗口 | 推荐路径 |
|------|---------|---------|---------|
| 预报解读 | 当前水位 + 和风 168h 预报 + 气象预警 + 汛限 | 未来 168h | 快捷路径：`--type full_context` |
| 水库影响估算 | full_context + 四源对齐 + 模型来水过程 | 未来 48~168h | 快捷路径 + 场景脚本 `fusion_detail` |
| 多源融合 | 和风 168h + 分区 + weather_info + NMC fixture | 未来 24~168h | 场景脚本 `query_forecast_analysis.py --type fusion_detail` |
| 趋势预测 | 水位过程线 + 模型预报来水 + 汛限 | 近 12h 实测 + 未来 72h | `full_context` + `water_level_curve` + `model_forecast_result` |
| 预报精度 | forecast_accuracy_record（gated） | 回溯 7~30d | 场景脚本 `accuracy_report` |
| 历史类比 | 相似洪水（按峰值水位接近度） | 不限 | 场景脚本 `similar_floods --water-level {值}` |
| 预报对照 | 预报 vs 实测降雨 | 过去 48h ~ 未来 48h | 场景脚本 `forecast_timeline` |
| 实况/知识问答 | 当前水位 + 气象预警 + 汛限 | 只看当前 | 快捷路径 + 知识文件 |

### 水库范围限定（重要）

> 所有查询默认针对**三岔水库**（`tenant_id = 18`），master 测站从 `model_config` 读，**不要查询全区域数据**。

- 水位/流量：`st_rsvr_r` master stcd 取 `model_config.config_key = 'st_rsvr_r_master'`（**禁止硬编码 '3'**；快捷查询 `--type config` 一次取回关键键）
- 实测降雨：`st_pptn_r` master stcd 取 `model_config.config_key = 'st_pptn_r_master'`（**禁止硬编码 '46'**；同上 `--type config` 可取）
- 预报降雨：`f_rnfl_h` / `st_pptn_re_forecast`（`f_rnfl_h` 无 tenant；分区表按 `re_id`、tenant=18）
- 汛限：`att_res_flse_lim` 当汛期行 → 回退 `att_res_base.fl_low_lim_lev`（**严禁硬编码数值**）

## 数据库

```bash
# 连接示例（SRM_DB_* 环境变量须预先 export；库名默认 powerelf_srm_yml，见 docs/db-credential-config.md）
mysql -h "${SRM_DB_HOST:-127.0.0.1}" -P "${SRM_DB_PORT:-3306}" \
      -u "${SRM_DB_USER:-root}" "$SRM_DB_NAME" -p"${SRM_DB_PASSWORD}"
```

- **连接**：主机 `SRM_DB_HOST` / 端口 `SRM_DB_PORT` / 库名 `SRM_DB_NAME`（默认 `powerelf_srm_yml`）/ 只读用户 `SRM_DB_USER` / 密码经 `SRM_DB_PASSWORD` 环境变量（**严禁写入任何文件**）
- **预报核心表**：`st_rsvr_r`(水情) · `f_rnfl_h`(和风逐时预报,无 tenant) · `st_pptn_re_forecast`(分区预报) · `model_result_files`(type=1 预报来水,无 deleted) ⟕ `st_mx_preset_cal_r`(type 21 流量/22 水位) · `weather_info`(30d 日总量) · `weather_warn`(气象预警) · `forecast_accuracy_record`(精度,gated) · `att_res_flse_lim`(汛限,无 deleted) · `srm_flood_history_base`(历史洪水)

## 预报规则速查

> 📖 **完整规则**：`${HERMES_SKILL_DIR}/references/forecast-rules.md`（9 条 IF/ELIF + C2 拦截清单）

### 置信度模型（规则 4/5）

| 数据源 | 单源置信度 | 依据 |
|--------|-----------|------|
| NMC 24h（中央气象台 fixture） | 高 | 官方权威源 |
| 分区模型 `st_pptn_re_forecast` | 高 | 本地水文模型站点校准 |
| 模型来水 `st_mx_preset_cal_r` | 高 | 经过产汇流演算 |
| 和风 168h 逐时 `f_rnfl_h` | 中 | 商业源，长预见期衰减 |
| 和风 30d 日总量 `weather_info` | 中 | 长期趋势，日精度 |

**综合置信度裁决**（规则 4）：NMC + 模型两高源一致 → 高；仅和风单源或源间分歧大（`disagreement_hours` 占比超 `{disagree_ratio_threshold}`）→ 中；默认保守 → 中。

**预报精度置信度**（规则 5，阈值取自 `model_config`，参考标注：高 `<{mape_high_threshold}`、中 `≤{mape_medium_threshold}`、低 `>` 该值；`gated_flag=true` 时结论加"待复核"）。

### 预警等级阈值（规则 1/2/3，**全部字段读取**）

> ⛔ **阈值来源铁律**：所有预警阈值从 `full_context` / `model_config` / `att_res_flse_lim` 字段读取。**严禁**把 docs/33 趋势预警标注值（蓝/黄/橙/红四档水位，具体数值见 `references/forecast-rules.md` 第一节"阈值来源说明"）或三岔特征水位参考值（汛限/设计/校核三档，具体数值见 `references/table-schema.md` 末尾"水库特征水位参考"表）当字面常量写进 IF 分支——两者**不在同一高程基准**，存在不一致。判定只信运行时读到的字段值。

- **规则 1（水位趋势预警）**：`{current_rz}` 与 `{warning_blue/yellow/orange/red_level}`（从预警配置字段读）逐级比较
- **规则 2（降雨预报预警）**：`{forecast_rain_24h}`（多源融合后值）与 `{rainfall_blue/yellow/orange/red_threshold}`（从配置读）逐级比较
- **规则 3（特征水位越限，应急触发）**：`{current_rz}` 与 `{flood_limit}` / `{design_level}` / `{check_level}`（从 model_config / 工程文件字段读）比较

### 影响估算触发（规则 6/7）

触发条件（任一满足即输出 `【估算值 ±20%】` 区间，而非点估）：
- `{forecast_rain_24h} >= {impact_rain_threshold}`（参考标注 50mm/24h，**从配置读**）
- `{current_rz}` 接近 `{flood_limit}`（差值 `<= {near_limit_margin}`，参考标注 1.0m，**从配置读**）
- 多源分歧大（综合置信度 = 中且涉及防洪）

触发后输出须含：① 预计最高水位区间 ② 预计最大入库流量区间 ③ 洪峰到达时间区间 ④ 超汛限概率（数据不足标"未知"）⑤ 数据源标注 ⑥ 复核提示（gated 时加"精度链路待复核"）。

> 上述 `{impact_rain_threshold}` / `{near_limit_margin}` 等参考值仅在 `forecast-rules.md` 第七节作"参考标注"出现，**不进判定表达式**（skill-auditor C2 拦截）。

## 安全约束（不可违反）

> 📖 **法规依据**：`${HERMES_SKILL_DIR}/references/knowledge-base.md`

- **数字必出输入**：回答里的所有定量结论（水位、流量、降雨、MAPE）必须来自脚本返回字段，**严禁编造**（docs/33 §4.3）。数据缺失时用降级话术（见"数据缺失处理"），不得臆测
- **估算值 ±20%**：触发影响估算时，所有定量结论以区间呈现并注明数据源与置信度
- **置信度标注**：每个预报结论必须带高/中/低置信度（依规则 4/5）
- **HITL 三闸门**：① 数据来源校验（脚本返回字段为准）② 安全校验（水位距汛限）③ 法规依据引用（结尾段）——任一闸门未过即降级或提示人工复核
- **字段读取措辞（防 execute_code 死循环）**：阈值/约束一律"**full_context 返回的 `flood_limit` 字段**""**accuracy_report 返回的 `avg_mape` 字段**"等；**严禁**"去查询汛限""去计算 MAPE"等措辞，会触发 Hermes 反复调 execute_code 卡死
- **特征水位越限即应急触发**：`{current_rz} >= {check_level}` → 紧急调度（全力泄洪 + 人员转移），须提示人工介入

## 引用规范

回答涉及法规、标准、技术要求时，**必须**注明出处：

| 引用类型 | 格式 | 示例 |
|---------|------|------|
| 国家标准 | 标准号 + 述原则 | "依 GB/T 22482《水文情报预报规范》精度评定原则" |
| 行业标准 | 标准号 | "依 SL 250-2000 误差量级" |
| 法律法规 | 《名称》（述法律精神） | "依《防洪法》，汛期不得擅自在汛限水位以上蓄水" |
| 预报规则 | "根据预报规则" | "根据预报规则，多源分歧大时综合置信度降为中" |

> ⛔ **禁止编造条款号**：GB/T 22482 / SL 250 的精度评定具体条款号在 `knowledge-base.md` 标 `[条款号待核]`，**未确证前只述原则**（"依 GB/T 22482 精度评定原则"），**不得**写"依 GB/T 22482 第 X 条"。《防洪法》第 38/40/41 等条款与预报的逐条对应同样待核，引用时述法律精神即可。

## 多源融合速查

> 📖 **完整框架**：`${HERMES_SKILL_DIR}/references/multi-source-fusion.md`

**四源对齐表**：

| 数据源 | 表 | 预见期 | 粒度 | 置信度 | 关键字段 |
|--------|----|--------|------|--------|---------|
| 和风 168h | `f_rnfl_h` | 168h | 逐时 1h | 中 | RN / YMDH / FYMDH（无 tenant） |
| 和风 30d | `weather_info` | 30d | 日总量 | 中 | precip / fx_date（无 tenant） |
| NMC 24h | 中央气象台 fixture | 24h | 等值面 max | 高 | contours（JSONP fixture） |
| 分区模型 | `st_pptn_re_forecast` | 168h | 逐时 1h（按 re_id） | 高 | drp / tm / re_id（tenant=18） |

**融合是 LLM 推理过程，非固定算法**：脚本 `fusion_detail` 只产出对齐时间轴 + 逐时分歧标注（`disagreement_threshold_mm` 字段，参考 20mm），**不输出融合后单一数值**。采信裁决参考 `forecast-rules.md` 规则 9（NMC 覆盖采 NMC / 模型与和风同向采模型 / 源间反向取保守较大值 + 【估算值 ±20%】）。

**NMC HTTP fixture**：位于 `${HERMES_SKILL_DIR}/data/scenarios/nmc_rainfall_24.json`，生产 NMC（`typhoon.nmc.cn`）返回 JSONP 外壳 `diamond14_rainfall_{type}_json({...})`，脚本 `_parse_nmc_fixture` 剥外壳取 `contours[].value` 的 max 代表该源强度上限。fixture 标 `source: "NMC-MOCK"`，Agent 见此标记须在结论标注"基于 mock fixture，非实时数据"。

## 精度评估速查

> 📖 **完整原则**：`${HERMES_SKILL_DIR}/references/knowledge-base.md`（GB/T 22482 精度评定）

**数据充分性闸门**（决定能否给精度结论）：

| 回溯样本量 | 闸门状态 | 处理 |
|-----------|---------|------|
| `< 7d` | 不足 | 标"精度待评定（样本不足）"，**绝不输出 MAPE 数字** |
| `7~30d` | 有限 | 给 MAPE 但标"样本有限，谨慎采用" |
| `>= 30d` | 充分 | 正常给 MAPE + 合格率 + 置信分级 |

> ⛔ **C1 缺陷依赖说明（gated）**：`forecast_accuracy_record` 是 Task 2 引入的 mock 新表，本地与现网均可能为空，且回灌链路（预报→实测对齐写入精度表）尚未修复。因此 `query_forecast_analysis.py --type accuracy_report` 返回的 `gated_flag` **恒为 true**——意为"数据可信但需人工复核"。**表为空时返回 `{"status":"insufficient"}` 结构，绝不编造 MAPE / 合格率数字**。置信分级（高/中/低）阈值取自 `model_config`（参考标注：`<{mape_high_threshold}`=高、`≤{mape_medium_threshold}`=中、`>`=低）。

## 数据缺失处理

| 数据缺失 | 降级话术 |
|---------|---------|
| 水位 `rz` 为 NULL | 提示"当前水位数据不可用（st_rsvr_r 最新行 rz 为空），建议核查测站" |
| 降雨预报 `f_rnfl_h` 空 | 提示"和风逐时预报为空，多源融合缺一源，综合置信度降为中" |
| 模型预报 `model_forecast_result` 空 | 提示"无最新模型预报来水过程，影响估算仅基于降雨源，标【估算值 ±20%】" |
| 精度表 `< 30d`（或空） | gated：标"精度待评定（样本不足）"，**绝不编数字**（见"精度评估速查"） |
| **陈旧预报**（`full_context._meta.as_of` 或最新预报 `tm` 距今 `> 6h`） | 提示"**预报陈旧，距今超 6h，仅供参考**，建议等待新一轮预报发布" |
| 汛限字段空 | 回退 `att_res_base.fl_low_lim_lev`，仍空则提示"汛限未配置，结论暂不可用" |
| NMC fixture 缺失 | 标"NMC 源不可用（fixture 缺失），融合置信度降为中" |

## API 模式（可选）

如需直读后端已算好的预报 REST 接口（**只读已算结果，非触发模型调用**）：

```bash
export API_BASE=http://127.0.0.1:48080/admin-api

# 示例：拉取最新一场模型预报结果（只读已算结果）
curl -X GET "$API_BASE/model/forecast/latest?tenantId=18" \
  -H "Authorization: Bearer ${SRM_TOKEN:-}"

# 示例：拉取 NMC 实时降雨等值面（生产 rainfallController 实时拉 typhoon.nmc.cn）
curl -X GET "$API_BASE/model/rainfall/nmc?type=24"
```

> ⛔ 本 skill 默认走 `scripts/` 脚本读库；API 模式仅当后端已暴露预报只读接口且脚本取不到时使用。**严禁** POST 任何触发模型计算的端点（那是 plan-generation / simulation 的职责）。

## 知识库文件索引

当需要深入分析时，读取对应 `references/*.md` 文件（**先读再答，不凭记忆**）：

| 文件路径 | 内容 | 何时读取 |
|---------|------|---------|
| `${HERMES_SKILL_DIR}/references/table-schema.md` | 14 张预报表结构 + 6 条用法规则（tenant/deleted/taskid）+ 特征水位参考 | 自己写 SQL 前、不确定字段名/有无 deleted/taskid 拼写时 |
| `${HERMES_SKILL_DIR}/references/sql-templates.md` | 19 个参数化 SQL 模板（Q1–Q12 / J1–J4 / A1）+ 适用速查 | 灵活路径查询、模板拼接时 |
| `${HERMES_SKILL_DIR}/references/forecast-rules.md` | 9 条 IF/ELIF 规则（等级/置信度/影响/分歧）+ C2 拦截清单 | 判定预警等级、置信度、影响估算、多源分歧时 |
| `${HERMES_SKILL_DIR}/references/multi-source-fusion.md` | 四源对齐表 + 融合推理框架 + NMC fixture 说明 | 处理多源对比/融合/分歧时 |
| `${HERMES_SKILL_DIR}/references/knowledge-base.md` | 法规标准（GB/T 22482 / SL 250 / 防洪法）+ 精度评定原则 + 待核事项 | 引用法规、精度评定、标准条款时 |
| `${HERMES_SKILL_DIR}/references/INDEX.md` | 场景/关键词 → 文件路由表 | 不确定读哪个文件时 |
