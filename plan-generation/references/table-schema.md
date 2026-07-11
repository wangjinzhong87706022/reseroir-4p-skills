# 表结构元数据

> **用途**：LLM 走"灵活路径"自己写 SQL 时的参考字典

## ⚠️ 大表判定标准

| 判定条件 | 示例 | 标记 |
|---------|------|------|
| 数据量 > 10万行 | st_rsvr_r（百万级）、st_pptn_r（百万级） | ⚠️ |
| 数据量未达10万但持续快速增长 | f_rnfl_h（万级，每天新增数百条） | ⚠️ |
| 静态参考数据（即使百条级） | att_res_stag_cap_disc、att_res_discharge_curve | 无 ⚠️ |

**安全规则**：
- 大表的数据提取查询（SELECT 返回多行）→ **必须**加时间范围 + LIMIT
- 大表的统计/聚合查询（COUNT/SUM/AVG）→ 视用户意图决定是否加时间范围
- 统计"全量数据质量"类问题 → 不加时间范围，直接执行
- 不确定时 → 默认加时间范围（保守策略）

---

## 总览

| 表名 | 中文名 | 数据量级 | 需时间过滤 | 增长速度 |
|------|--------|---------|-----------|---------|
| st_rsvr_r | 实时水位 | 百万级 ⚠️ | 是 | 每小时数条 |
| st_pptn_r | 实时雨情 | 百万级 ⚠️ | 是 | 每小时数条 |
| f_rnfl_h | 降雨预报 | 万级 ⚠️ | 是 | 每天数百条 |
| weather_warn | 气象预警 | 千级 | 否 | 每天0~数十条 |
| model_result_files | 历史预案 | 百级 | 推荐 | 每次生成1条 |
| dispatch_history | 调度历史 | 万级 | 通过 task_id 关联 | 每次生成数十条 |
| srm_flood_history_base | 历史洪水 | 十条级 | 否 | 偶尔新增 |
| srm_flood_history_result | 洪水结果 | 千级 | 否 | 随计算生成 |
| srm_scheduling_scenario | 调度场景 | 十条级 | 否 | 很少变化 |
| model_config | 系统配置 | 百级 | 否 | 偶尔修改 |
| att_res_flse_lim | 汛限水位 | 十条级 | 否 | 很少变化 |
| att_res_base | 水库基础 | 1条 | 否 | 极少变化 |
| att_res_stag_cap_disc | 水位库容曲线 | 百条级 | 否（静态） | 不变 |
| att_res_discharge_curve | 泄流曲线 | 百条级 | 否（静态） | 不变 |

### 使用规则

1. **⚠️ 大表的数据提取查询必加时间范围**：对标记为 ⚠️ 的表执行 SELECT 返回多行的查询时，`WHERE` 子句中必须包含时间字段的范围限制。统计/聚合查询（COUNT/SUM 等）视用户意图决定——"全量统计"类问题不需要加时间范围。
2. **软删除字段**：大部分表有 `deleted` 字段，查询时加 `AND deleted = 0`。
3. **租户隔离**：有 `tenant_id` 的表应优先过滤 `tenant_id = 18`。
4. **调度历史关联**：`dispatch_history` 不要按 `tm` 直接查，必须通过 `task_id` 关联 `model_result_files.taskid`。
5. **配置字段名**：`model_config` 的键名字段是 `config_key`，不是 `key_name`。
6. **汛限水位兜底**：`att_res_flse_lim` 可能为空，需回退到 `att_res_base.fl_low_lim_lev`。

---

## 详细表结构

---

### st_rsvr_r（实时水位）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 1234567890 | 唯一标识 |
| st_id | varchar(20) | 测站编码 | "61903000" | 筛选测站 |
| eq_id | varchar(20) | 设备编码 | "EQ001" | 筛选设备 |
| tm | datetime | 观测时间 | "2026-06-10 08:00:00" | **必须的时间过滤字段** |
| rz | decimal(10,3) | 水位（m） | 23.45 | 当前水位 / 水位趋势 |
| inq | decimal(10,3) | 入库流量（m³/s） | 150.5 | 入库流量分析 |
| otq | decimal(10,3) | 出库流量（m³/s） | 120.3 | 出库流量分析 |
| w | decimal(10,3) | 蓄水量（万m³） | 850.2 | 库容分析 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：任何非 `LIMIT 1` 的查询必须包含 `tm` 时间范围条件（如 `tm >= '2026-06-09' AND tm < '2026-06-10'`）。主测站 ID 从 `model_config` 的 `st_rsvr_r_master` 键获取。

**索引建议**：`(st_id, tm)` 复合索引，`tm` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 查最近24小时水位
SELECT tm, rz, inq, otq, w
FROM st_rsvr_r
WHERE st_id = (SELECT value FROM model_config WHERE config_key = 'st_rsvr_r_master' AND deleted = 0 AND tenant_id = 18 LIMIT 1)
  AND tm >= NOW() - INTERVAL 24 HOUR
  AND deleted = 0
ORDER BY tm DESC;

-- ❌ 危险: 没有时间范围，全表扫描百万行
SELECT * FROM st_rsvr_r WHERE st_id = '61903000' AND deleted = 0;
```

**特殊注意**：
- 主测站 ID 不要硬编码，从 `model_config.config_key = 'st_rsvr_r_master'` 动态获取
- 水位单位为米（m），流量单位为 m³/s，蓄水量单位为 万m³
- 数据采集频率约每小时数条，查询 7 天以上范围时注意数据量

---

### st_pptn_r（实时雨情）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 9876543210 | 唯一标识 |
| st_id | varchar(20) | 测站编码 | "61903000" | 筛选测站 |
| eq_id | varchar(20) | 设备编码 | "EQ002" | 筛选设备 |
| eq_code | varchar(20) | 设备编码（备用） | "P001" | 备用设备标识 |
| stcd | varchar(20) | 测站代码 | "61903000" | 筛选测站（与 st_id 可能重复） |
| tm | datetime | 观测时间 | "2026-06-10 08:00:00" | **必须的时间过滤字段** |
| p | decimal(10,2) | 时段降雨量（mm） | 5.3 | 当前时段雨量 |
| dr | decimal(10,2) | 时段长（h） | 1.0 | 降雨历时 |
| pdr | decimal(10,2) | 时段降雨量（备用） | 5.3 | 备用雨量字段 |
| accumulate | decimal(10,2) | 累计降雨量（mm） | 45.8 | 累计雨量统计 |
| day_accumulate | decimal(10,2) | 日累计降雨量（mm） | 23.5 | 日雨量统计 |
| month_accumulate | decimal(10,2) | 月累计降雨量（mm） | 120.6 | 月雨量统计 |
| year_accumulate | decimal(10,2) | 年累计降雨量（mm） | 580.3 | 年雨量统计 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：任何非 `LIMIT 1` 的查询必须包含 `tm` 时间范围条件。主测站 ID 从 `model_config` 的 `st_pptn_r_master` 键获取。

**索引建议**：`(st_id, tm)` 复合索引，`tm` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 查最近24小时雨量
SELECT tm, p, accumulate, day_accumulate
FROM st_pptn_r
WHERE st_id = (SELECT value FROM model_config WHERE config_key = 'st_pptn_r_master' AND deleted = 0 AND tenant_id = 18 LIMIT 1)
  AND tm >= NOW() - INTERVAL 24 HOUR
  AND deleted = 0
ORDER BY tm DESC;

-- ❌ 危险: 没有 tm 范围的全表扫描
SELECT * FROM st_pptn_r WHERE st_id = '61903000' AND deleted = 0 ORDER BY tm DESC;
```

**特殊注意**：
- 有多个累计字段（日/月/年），按需选择
- `st_id` 和 `stcd` 可能存储相同值，优先用 `st_id`
- 数据采集频率约每小时数条

---

### f_rnfl_h（降雨预报）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 100001 | 唯一标识 |
| fymdh | datetime | 预报发布时间 | "2026-06-10 08:00:00" | 区分预报批次 |
| ymdh | datetime | 预报目标时间 | "2026-06-11 14:00:00" | 预报的时刻 |
| rn | decimal(10,2) | 预报降雨量（mm） | 12.5 | 预报雨量值 |
| pop | varchar(10) | 降雨概率（%） | "80" | 降雨可能性 |
| text | varchar(100) | 天气描述 | "中雨" | 天气文字描述 |
| temp | decimal(5,1) | 温度（℃） | 28.5 | 气温预报 |
| wind_dir | varchar(20) | 风向 | "东南风" | 风向信息 |
| wind_speed | varchar(20) | 风速 | "3-4级" | 风力等级 |
| icon | varchar(20) | 天气图标代码 | "10" | 前端图标映射 |
| unitname | varchar(10) | 数据来源标识 | "1" | 区分预报来源 |
| comments | varchar(255) | 备注 | "台风影响" | 附加说明 |
| type | tinyint | 预报类型 | 1 | 区分预报模式 |
| precip | decimal(10,2) | 降水量（mm） | 12.5 | 备用降水量字段 |
| cloud | varchar(50) | 云量信息 | "多云" | 云况描述 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：有两个时间字段 — `fymdh`（发布时间）和 `ymdh`（目标时间）。获取最新预报时必须先取 `MAX(fymdh)` 确定最新批次，再按 `ymdh` 查具体时段。

**索引建议**：`(fymdh, ymdh)` 复合索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取最新一批3天逐时预报
SELECT ymdh, rn, pop, text, temp
FROM f_rnfl_h
WHERE fymdh = (SELECT MAX(fymdh) FROM f_rnfl_h WHERE type = 1 AND deleted = 0)
  AND type = 1
  AND deleted = 0
ORDER BY ymdh ASC;

-- ❌ 危险: 没指定 fymdh，可能返回多批次混合数据
SELECT * FROM f_rnfl_h WHERE type = 1 AND deleted = 0 ORDER BY ymdh;
```

**特殊注意**：
- **type 含义**：1 = 3天逐时预报，2 = 2小时5分钟间隔预报，3 = 72小时逐时预报
- **unitname 含义**：1 = 中央气象台/和风天气（QWeather），2 = 扬州气象，4 = ECMWF
- `rn` 和 `precip` 可能存储相同值，优先用 `rn`
- 不同 `unitname` 来源的预报数据格式可能不同，合并使用时注意

---

### weather_warn（气象预警）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 200001 | 唯一标识 |
| docid | varchar(50) | 文档ID | "WARN20260610001" | 预警唯一编号 |
| docabstract | text | 预警摘要内容 | "预计未来6小时内..." | 预警详情 |
| chnlname | varchar(50) | 预警类型名称 | "暴雨预警" | 预警分类 |
| model_type | varchar(20) | 预警级别代码 | "01" | 预警等级标识 |
| docpubtime | datetime | 发布时间 | "2026-06-10 08:00:00" | 预警发布时间 |
| docpuburl | varchar(255) | 预警详情链接 | "http://..." | 跳转链接 |
| update_time | datetime | 更新时间 | "2026-06-10 10:00:00" | 最近更新 |
| warn_status | tinyint | 预警状态 | 1 | 是否生效 |

**⚠️ 强制规则**：无，小表不需要强制时间过滤。

**索引建议**：`warn_status` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 查询当前生效的预警
SELECT docid, chnlname, model_type, docabstract, docpubtime
FROM weather_warn
WHERE warn_status = 1
ORDER BY docpubtime DESC;

-- ✅ 安全: 查询最近7天的所有预警（含已解除）
SELECT * FROM weather_warn
WHERE docpubtime >= NOW() - INTERVAL 7 DAY
ORDER BY docpubtime DESC;
```

**特殊注意**：
- `warn_status`：1 = 生效中，2 = 已解除
- `model_type` 编码对应不同预警级别（如蓝色/黄色/橙色/红色）
- 数据量小，可以直接全表扫描而不影响性能

---

### model_result_files（历史预案）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 300001 | 唯一标识 |
| taskid | varchar(50) | 任务ID | "TASK20260610001" | 关联调度历史的键 |
| scheme_id | bigint | 调度场景ID | 1 | 关联 srm_scheduling_scenario |
| version | int | 版本号 | 3 | 方案版本 |
| file_name | varchar(255) | 文件名 | "dispatch_20260610.json" | 结果文件名 |
| file_path | varchar(500) | 文件存储路径 | "/data/results/..." | 文件路径 |
| start_time | datetime | 模拟开始时间 | "2026-06-10 08:00:00" | 方案起算时间 |
| end_time | datetime | 模拟结束时间 | "2026-06-12 08:00:00" | 方案结束时间 |
| type | tinyint | 结果类型 | 1 | 区分数据类型 |
| extend | text | 扩展信息（JSON） | '{"schedulingTarget":...}' | 方案参数详情 |
| alias | varchar(100) | 方案别名 | "常规调度方案A" | 人类可读名称 |
| target_water_level | decimal(10,3) | 目标水位（m） | 22.50 | 预期控制水位 |
| adjusted_water_level | varchar(20) | 调整后水位 | "23.10" | 实际调整水位（VARCHAR！） |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |
| create_time | datetime | 创建时间 | "2026-06-10 09:00:00" | 记录创建时间 |

**⚠️ 强制规则**：无强制时间过滤（百级数据量），但推荐按 `create_time` 排序取最新。

**索引建议**：`taskid` 单列索引，`(tenant_id, create_time)` 复合索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取最新预案
SELECT id, taskid, scheme_id, type, alias, target_water_level,
       adjusted_water_level, start_time, end_time, extend
FROM model_result_files
WHERE deleted = 0 AND tenant_id = 18
ORDER BY create_time DESC
LIMIT 1;

-- ✅ 安全: 按 taskid 关联查调度明细
SELECT mrf.alias, mrf.target_water_level, dh.tm, dh.dispatch_opening, dh.gate_opening_flow
FROM model_result_files mrf
JOIN dispatch_history dh ON dh.task_id = mrf.taskid AND dh.deleted = 0
WHERE mrf.taskid = 'TASK20260610001'
  AND mrf.deleted = 0
ORDER BY dh.tm ASC;
```

**特殊注意**：
- **type 含义**：1 = 预报来水过程，2 = 调度流量过程，3 = 滚动预报，4 = 调度闸门开度，5 = 轮播流量过程，6 = 轮闸门开度
- **`adjusted_water_level` 是 VARCHAR 类型**！数值比较时必须 `CAST(adjusted_water_level AS DECIMAL(10,3))`
- `extend` 字段是 JSON 字符串，包含 `schedulingTarget`、`schedulingModel`、`maxWaterLevel` 等关键参数，可用 `JSON_EXTRACT` 解析
- `taskid` 是关联 `dispatch_history` 的桥梁

---

### dispatch_history（调度历史）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 400001 | 唯一标识 |
| tm | datetime | 调度时刻 | "2026-06-10 10:00:00" | 该步的对应时间 |
| dispatch_opening | decimal(10,3) | 闸门开度（m） | 2.5 | 闸门开度值 |
| gate_opening_flow | decimal(10,3) | 闸门出流（m³/s） | 180.5 | 闸门流量 |
| task_id | varchar(50) | 关联任务ID | "TASK20260610001" | **关联 model_result_files.taskid** |
| create_time | datetime | 创建时间 | "2026-06-10 09:00:00" | 记录创建时间 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：**不要直接按 `tm` 查询此表！** 必须通过 `task_id` 关联 `model_result_files.taskid` 获取数据。单独按 `tm` 查询会混淆不同调度方案的数据。

**索引建议**：`task_id` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 通过 task_id 关联获取某方案的调度过程
SELECT dh.tm, dh.dispatch_opening, dh.gate_opening_flow
FROM dispatch_history dh
WHERE dh.task_id = 'TASK20260610001'
  AND dh.deleted = 0
ORDER BY dh.tm ASC;

-- ✅ 安全: 从最新预案获取调度历史
SELECT dh.tm, dh.dispatch_opening, dh.gate_opening_flow
FROM dispatch_history dh
JOIN model_result_files mrf ON mrf.taskid = dh.task_id AND mrf.deleted = 0
WHERE mrf.id = 300001
  AND dh.deleted = 0
ORDER BY dh.tm ASC;

-- ❌ 危险: 直接按 tm 查，混淆不同方案
SELECT * FROM dispatch_history WHERE tm >= '2026-06-10' AND deleted = 0;
```

**特殊注意**：
- `task_id` 对应 `model_result_files.taskid`（注意两边字段名不同）
- 每个调度方案会产生数十条时间步记录
- `dispatch_opening` 单位为米（m），`gate_opening_flow` 单位为 m³/s

---

### srm_flood_history_base（历史洪水）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 500001 | 唯一标识 |
| name | varchar(100) | 洪水名称 | "20260610号洪水" | 洪水标识 |
| remake | varchar(255) | 备注 | "台风暴雨引发" | 附加说明 |
| start_time | datetime | 洪水开始时间 | "2026-06-10 08:00:00" | 时间范围 |
| end_time | datetime | 洪水结束时间 | "2026-06-12 20:00:00" | 时间范围 |
| adjusted_water_level | decimal(10,3) | 调整后水位（m） | 24.80 | 最终水位 |
| target_water_level | decimal(10,3) | 目标水位（m） | 22.50 | 预期控制水位 |
| status | tinyint | 计算状态 | 2 | 是否完成 |
| rainfall_data | text | 降雨数据（JSON数组） | '[{"tm":"...","p":5.3}]' | 输入降雨过程 |
| rsvr_remake | varchar(255) | 水库说明 | "水位超汛限" | 水库情况描述 |
| river_remake | varchar(255) | 河道说明 | "下游水位偏高" | 河道情况描述 |
| pptn_remake | varchar(255) | 雨情说明 | "面雨量85mm" | 降雨情况描述 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：无，数据量极小（十条级）。

**索引建议**：`status` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 查询已完成的洪水记录
SELECT id, name, start_time, end_time, adjusted_water_level, target_water_level, status
FROM srm_flood_history_base
WHERE deleted = 0 AND status = 2
ORDER BY start_time DESC;

-- ✅ 安全: 获取指定洪水的基础信息和结果
SELECT b.name, b.start_time, b.end_time, b.status, r.type_name, r.vals
FROM srm_flood_history_base b
JOIN srm_flood_history_result r ON r.flood_id = b.id
WHERE b.id = 500001 AND b.deleted = 0
ORDER BY r.type, r.sort;
```

**特殊注意**：
- **status 含义**：0 = 待计算，1 = 计算中，2 = 已完成，3 = 计算失败
- `rainfall_data` 是 JSON 数组格式，每个元素含 `tm`（时间）和 `p`（降雨量）
- 此表是 `srm_flood_history_result` 的父表，通过 `flood_id` 关联

---

### srm_flood_history_result（洪水结果）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 600001 | 唯一标识 |
| type | tinyint | 结果类型 | 1 | 区分数据类型 |
| type_name | varchar(50) | 类型名称 | "入库流量" | 人类可读的类型描述 |
| vals | text | 数值序列（JSON数组） | '[100,120,150,...]' | 过程线数据 |
| flood_id | bigint | 关联洪水ID | 500001 | **关联 srm_flood_history_base.id** |
| tm | datetime | 时间戳 | "2026-06-10 08:00:00" | 对应时刻 |
| sort | int | 排序号 | 1 | 同类型的排序 |

**⚠️ 强制规则**：必须通过 `flood_id` 过滤，否则会返回不同洪水的结果混合。

**索引建议**：`(flood_id, type)` 复合索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取指定洪水的入库流量过程
SELECT tm, vals, type_name
FROM srm_flood_history_result
WHERE flood_id = 500001 AND type = 1
ORDER BY sort ASC;

-- ✅ 安全: 获取指定洪水的所有结果类型
SELECT type, type_name, tm, vals
FROM srm_flood_history_result
WHERE flood_id = 500001
ORDER BY type, sort;

-- ❌ 危险: 不指定 flood_id，混合不同洪水数据
SELECT * FROM srm_flood_history_result WHERE type = 1 ORDER BY tm;
```

**特殊注意**：
- **type 含义**：1 = 入库流量，2 = 出库流量，3 = 坝前水位，4 = 河道水位，5 = 河道流量，6 = 降雨过程，7 = 统计信息
- `vals` 是 JSON 数组，存储数值序列（过程线数据点）
- 每个洪水 ID 下可能有多种 type 的结果
- `sort` 字段用于保持同一 type 内的时序排列

---

### srm_scheduling_scenario（调度场景）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 1 | 唯一标识 |
| name | varchar(100) | 场景名称 | "正常调度" | 场景标识 |
| scheduling_target | varchar(50) | 调度目标 | "flood_control" | 调度目标类型 |
| scheduling_model | varchar(50) | 调度模型 | "XAJ" | 使用的模型 |
| remark | varchar(255) | 备注 | "汛期常规调度" | 附加说明 |
| extend | text | 扩展参数（JSON） | '{"maxWaterLevel":25.5}' | 详细参数配置 |
| def_flg | tinyint | 是否默认场景 | 1 | 标识默认方案 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：无，数据量极小（十条级）。

**索引建议**：`def_flg` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取默认调度场景
SELECT id, name, scheduling_target, scheduling_model, extend
FROM srm_scheduling_scenario
WHERE def_flg = 1 AND deleted = 0
LIMIT 1;

-- ✅ 安全: 列出所有可用场景
SELECT id, name, scheduling_target, scheduling_model, def_flg
FROM srm_scheduling_scenario
WHERE deleted = 0
ORDER BY def_flg DESC, id ASC;
```

**特殊注意**：
- `def_flg = 1` 表示默认场景，系统会优先使用此场景
- `extend` 是 JSON 字符串，可能包含 `maxWaterLevel`、`minWaterLevel`、`schedulingTarget` 等参数
- `scheduling_model` 标识使用的调度模型（如 XAJ 新安江模型等）
- 此表很少变化，可缓存

---

### model_config（系统配置）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 700001 | 唯一标识 |
| config_key | varchar(100) | 配置键名 | "max_water_level" | **按 key 查配置** |
| value | varchar(500) | 配置值 | "25.50" | 配置内容 |
| remark | varchar(255) | 说明 | "水库最高允许水位" | 配置描述 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：**字段名是 `config_key`，不是 `key_name`！** 同一个 `config_key` 可能有多条记录（不同 `tenant_id`），优先取 `tenant_id = 18`。

**索引建议**：`(config_key, tenant_id)` 复合索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取最高允许水位
SELECT value FROM model_config
WHERE config_key = 'max_water_level' AND deleted = 0 AND tenant_id = 18
LIMIT 1;

-- ✅ 安全: 获取实时水位测站ID
SELECT value FROM model_config
WHERE config_key = 'st_rsvr_r_master' AND deleted = 0 AND tenant_id = 18
LIMIT 1;

-- ❌ 危险: 用错字段名
SELECT value FROM model_config WHERE key_name = 'max_water_level';  -- 字段名错误！
```

**特殊注意**：
- **关键配置项列表**：
  - `max_water_level` — 水库最高允许水位（m）
  - `min_water_level` — 水库最低允许水位（m）
  - `max_drainage_capacity` — 最大泄洪能力（m³/s）
  - `safe_drainage_capacity` — 安全泄量（m³/s）
  - `st_rsvr_r_master` — 实时水位主测站 ID
  - `eq_rsvr_r_master` — 实时水位主设备 ID
  - `st_pptn_r_master` — 实时雨情主测站 ID
- `value` 是 VARCHAR 类型，数值比较时需 `CAST(value AS DECIMAL(10,3))`
- 优先使用 `tenant_id = 18` 过滤

---

### att_res_flse_lim（汛限水位）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 800001 | 唯一标识 |
| flse_lim_stag | decimal(10,3) | 汛限水位（m） | 22.00 | 汛限水位值 |
| flood_season_name | varchar(50) | 汛期名称 | "主汛期" | 汛期描述 |
| flood_season_start | varchar(4) | 汛期开始（MMDD） | "0601" | 判断是否在汛期 |
| flood_season_end | varchar(4) | 汛期结束（MMDD） | "0930" | 判断是否在汛期 |
| res_guid | varchar(50) | 水库GUID | "RES001" | 关联水库 |
| collect_time | datetime | 采集时间 | "2026-01-01 00:00:00" | 数据更新时间 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：**此表在本地环境可能为空！** 查询时若结果为空，必须回退到 `att_res_base.fl_low_lim_lev` 作为汛限水位。

**索引建议**：`res_guid` 单列索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取当前汛期的汛限水位（带回退）
SELECT COALESCE(
  (SELECT flse_lim_stag FROM att_res_flse_lim
   WHERE deleted = 0
     AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
     AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')
   LIMIT 1),
  (SELECT fl_low_lim_lev FROM att_res_base WHERE deleted = 0 LIMIT 1)
) AS flood_limit_level;

-- ✅ 安全: 查看所有汛期配置
SELECT flood_season_name, flse_lim_stag, flood_season_start, flood_season_end
FROM att_res_flse_lim
WHERE deleted = 0
ORDER BY flood_season_start;
```

**特殊注意**：
- `flood_season_start` / `flood_season_end` 是 **MMDD 格式的字符串**（如 "0601"、"0930"），不是日期类型
- 判断当前是否在汛期：`flood_season_start <= DATE_FORMAT(NOW(), '%m%d') AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')`
- **本地环境可能为空**，务必做回退处理

---

### att_res_base（水库基础信息）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 900001 | 唯一标识 |
| res_name | varchar(100) | 水库名称 | "某某水库" | 水库名称 |
| fl_low_lim_lev | decimal(10,3) | 防洪限制水位（m） | 22.00 | 汛限水位（兜底值） |
| dead_level | decimal(10,3) | 死水位（m） | 15.00 | 最低运行水位 |
| total_cap | decimal(10,3) | 总库容（万m³） | 5200.00 | 水库总库容 |
| res_guid | varchar(50) | 水库GUID | "RES001" | 全局唯一标识 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：无，通常只有 1 条记录。

**索引建议**：无需特殊索引

**常用查询模式**：
```sql
-- ✅ 安全: 获取水库基础信息
SELECT res_name, fl_low_lim_lev, dead_level, total_cap
FROM att_res_base
WHERE deleted = 0
LIMIT 1;
```

**特殊注意**：
- 通常只有 **1 条记录**
- `fl_low_lim_lev` 是汛限水位的兜底值，当 `att_res_flse_lim` 为空时使用
- 死水位 `dead_level` 是水库允许的最低运行水位

---

### att_res_stag_cap_disc（水位库容曲线）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| stag | decimal(10,3) | 水位（m） | 22.000 | 水位插值 |
| cap | decimal(10,3) | 库容（万m³） | 4200.000 | 对应库容 |

**⚠️ 强制规则**：无，静态参考数据。无 `deleted` 字段。

**索引建议**：`stag` 单列索引（用于插值查询）

**常用查询模式**：
```sql
-- ✅ 安全: 查询完整的水位-库容曲线
SELECT stag, cap FROM att_res_stag_cap_disc ORDER BY stag ASC;

-- ✅ 安全: 根据当前水位估算库容（线性插值思路）
SELECT stag, cap FROM att_res_stag_cap_disc
WHERE stag <= 23.45 ORDER BY stag DESC LIMIT 1;
SELECT stag, cap FROM att_res_stag_cap_disc
WHERE stag >= 23.45 ORDER BY stag ASC LIMIT 1;
-- 然后在应用层做线性插值
```

**特殊注意**：
- **无 `deleted` 字段**，查询时不需要加 `deleted = 0` 条件
- 这是**静态参考数据**，不会变化
- 水位与库容是离散对应关系，中间值需线性插值
- `cap` 单位为 万m³

---

### att_res_discharge_curve（泄流曲线）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| stag | decimal(10,3) | 水位（m） | 23.000 | 水位插值 |
| q | decimal(10,3) | 泄流量（m³/s） | 350.000 | 对应泄流能力 |

**⚠️ 强制规则**：无，静态参考数据。无 `deleted` 字段。

**索引建议**：`stag` 单列索引（用于插值查询）

**常用查询模式**：
```sql
-- ✅ 安全: 查询完整的泄流曲线
SELECT stag, q FROM att_res_discharge_curve ORDER BY stag ASC;

-- ✅ 安全: 根据当前水位估算泄流能力
SELECT stag, q FROM att_res_discharge_curve
WHERE stag <= 23.45 ORDER BY stag DESC LIMIT 1;
SELECT stag, q FROM att_res_discharge_curve
WHERE stag >= 23.45 ORDER BY stag ASC LIMIT 1;
-- 然后在应用层做线性插值
```

**特殊注意**：
- **无 `deleted` 字段**，查询时不需要加 `deleted = 0` 条件
- 这是**静态参考数据**，不会变化
- 水位与泄流量是离散对应关系，中间值需线性插值
- `q` 单位为 m³/s
