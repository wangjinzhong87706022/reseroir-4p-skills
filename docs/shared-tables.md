# SmartTwinRes Skills 共用数据表 Schema

> **用途**: 所有 SmartTwinRes Skill 开发、诊断、查询的**唯一权威数据表参考**
> **维护**: SmartTwinRes Team
> **最后更新**: 2026-07-11

---

## 📋 文档说明

### 适用范围

本文档涵盖 **SmartTwinRes Skills 家族** (forecasting / plan-generation / simulation / early-warning / diagnosis-verification) 中**跨 skill 共用**的数据表。

### Skill 使用矩阵

| 表名 | forecasting | simulation | early-warning | plan-generation | diagnosis-verification |
|------|------------|-----------|--------------|----------------|----------------------|
| **st_rsvr_r** (水库水情) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **st_pptn_r** (降雨数据) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **srm_flood_history_base** | ✅ | ✅ | ❌ | ❌ | ✅ |
| **srm_flood_history_result** | ✅ | ✅ | ❌ | ❌ | ✅ |
| **model_result_files** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **ew_info_message** | ❌ | ❌ | ✅ | ❌ | ✅ |
| **weather_warn** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **f_rnfl_h** (降雨预报) | ✅ | ❌ | ❌ | ❌ | ❌ |
| **dispatch_history** | ✅ | ✅ | ❌ | ❌ | ❌ |

**统计**:
- 5/5 skill 共用: st_rsvr_r, st_pptn_r
- 3/5 skill 共用: srm_flood_history_base, srm_flood_history_result
- 2/5 skill 共用: model_result_files

---

## ⚠️ 全局规则

### 1. 大表判定标准

| 判定条件 | 示例 | 标记 |
|---------|------|------|
| 数据量 > 10万行 | st_rsvr_r (~19万), st_pptn_r (~26万) | ⚠️ |
| 数据量达万级且持续增长 | f_rnfl_h (逐时预报,每小时新增) | ⚠️ |
| 静态/配置参考数据 | att_res_flse_lim, model_config | 无 ⚠️ |

**安全规则**:
- 大表（⚠️）的多行提取查询（SELECT 返回多行）→ **必须**加时间范围条件 + LIMIT
- 大表的统计/聚合查询（COUNT/SUM/AVG）→ 视用户意图决定是否加时间范围
- 统计"全量数据质量"类问题 → 不加时间范围（整表聚合才有意义）
- 不确定时 → 默认加时间范围（保守策略）

### 2. tenant_id / deleted 过滤规则

#### 2.1 tenant_id 过滤规则

| 表名 | 有无 tenant_id | 过滤规则 | 典型值 |
|------|--------------|---------|--------|
| st_rsvr_r | ✅ 有 | `tenant_id = 18` | 三岔水库 |
| st_pptn_r | ✅ 有 | `tenant_id = 18` (部分 skill 不过滤) | 三岔水库 |
| srm_flood_history_base | ✅ 有 | `tenant_id = 18` | 三岔水库 |
| model_result_files | ✅ 有 | `tenant_id = 18` | 三岔水库 |
| ew_info_message | ✅ 有 | 不强制 (告警跨租户) | - |
| f_rnfl_h | ❌ **无** | ⚠️ **不要加 tenant 过滤** | - |
| weather_warn | ❌ **无** | ⚠️ **不要加 tenant 过滤** | - |
| weather_info | ❌ **无** | ⚠️ **不要加 tenant 过滤** | - |
| model_config | ✅ 有 | `tenant_id = 18` | 三岔水库 |

#### 2.2 deleted 过滤规则

| 表名 | 有无 deleted | 过滤规则 |
|------|-------------|---------|
| st_rsvr_r | ✅ 有 | `deleted = 0` |
| st_pptn_r | ✅ 有 | `deleted = 0` |
| srm_flood_history_base | ✅ 有 | `deleted = 0` |
| ew_info_message | ✅ 有 | `deleted = 0` |
| **model_result_files** | ❌ **无** | ⚠️ **不要加 deleted=0** |
| **weather_warn** | ❌ **无** | ⚠️ **不要加 deleted=0** |
| **att_res_flse_lim** | ❌ **无** | ⚠️ **不要加 deleted=0** |

### 3. taskid 三拼写说明

不同表里「任务ID」的列名/类型不一致,JOIN 时必须显式转换类型,否则会隐式截断或报类型不匹配:

| 表 | 列名 | 类型 | 拼写特点 |
|----|------|------|---------|
| `dispatch_history` | `task_id` | varchar(32) | **下划线** |
| `model_result_files` | `taskid` | **varbinary**(32) | **无下划线** + varbinary |
| `st_mx_preset_cal_r` | `taskid` | varchar | **无下划线** |

**JOIN 示例** (先转字符串再比较):
```sql
SELECT m.*, d.dispatch_opening
FROM model_result_files m
LEFT JOIN dispatch_history d
  ON d.task_id = CAST(m.taskid AS CHAR)
WHERE m.type = 1;
```

---

## 📊 核心共用表详解

---

### 1. st_rsvr_r (水库水情表) ⭐⭐⭐⭐⭐

**使用 Skill**: 5/5 (全部)

#### 字段说明

| 字段 | 类型 | 说明 | Skill 差异 |
|------|------|------|-----------|
| id | bigint | 主键 | - |
| **stcd** | varchar(20) | 测站编码 | forecasting/simulation: 从 config 读<br>early-warning: 可能有 st_id |
| **rz** | decimal(8,3) | 水位(m) | - |
| **inq** | decimal(10,3) | 入库流量(m³/s) | - |
| **otq** | decimal(10,3) | 出库流量(m³/s) | - |
| **w** | decimal(12,3) | 蓄水量(万m³) | - |
| **tm** | datetime | 观测时间 | **必须的时间过滤字段** |
| deleted | bit(1) | 是否删除 | - |
| tenant_id | bigint | 租户ID | - |

#### 查询规则

```sql
-- ✅ 正确: tenant_id=18 + deleted=0 + 时间范围
SELECT rz, inq, otq, w, tm
FROM st_rsvr_r
WHERE tenant_id = 18
  AND deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)  -- 时间范围（⚠️ 大表必须）
ORDER BY tm DESC
LIMIT 1000;

-- ❌ 错误: 无时间范围（大表全表扫描）
SELECT * FROM st_rsvr_r WHERE tenant_id = 18 AND deleted = 0;
```

#### 特殊注意

- ⚠️ **大表 (~19万行)**: 任何非 `LIMIT 1` 的查询必须加 `tm` 时间范围
- forecasting/simulation: master stcd 从 `model_config.st_rsvr_r_master` 读 (**不硬编码**)
- early-warning: 无 st_id 字段 (与 forecasting/simulation 不同)

---

### 2. st_pptn_r (降雨数据表) ⭐⭐⭐⭐⭐

**使用 Skill**: 4/5 (除 diagnosis-verification)

#### 字段说明

| 字段 | 类型 | 说明 | Skill 差异 |
|------|------|------|-----------|
| id | bigint | 主键 | - |
| st_id | bigint | 测站ID | - |
| **eq_code** | varchar(20) | 设备编码 | - |
| **p** | decimal(7,1) | 降雨量(mm) | - |
| **dr** | decimal(5,1) | 时段(h) | - |
| **tm** | datetime | 观测时间 | **必须的时间过滤字段** |
| deleted | bit(1) | 是否删除 | - |
| tenant_id | bigint | 租户ID | early-warning: 不过滤 |

#### 查询规则

```sql
-- ✅ 正确: 时间范围 + deleted=0
SELECT p, dr, tm
FROM st_pptn_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY tm DESC
LIMIT 1000;

-- ❌ 错误: 无时间范围（大表全表扫描）
SELECT * FROM st_pptn_r WHERE deleted = 0;
```

#### 特殊注意

- ⚠️ **大表 (~26万行)**: 必须加时间范围
- 数据采集频率约每小时数条

---

### 3. srm_flood_history_base (历史洪水基础表) ⭐⭐⭐

**使用 Skill**: 3/5 (forecasting, simulation, diagnosis-verification)

#### 字段说明

| 字段 | 类型 | 说明 | Skill 差异 |
|------|------|------|-----------|
| id | bigint | 主键 | - |
| **name** | varchar(200) | 洪水名称 | - |
| **start_time** | datetime | 开始时间 | - |
| **end_time** | datetime | 结束时间 | - |
| **adjusted_water_level** | decimal(8,3) | 起调水位(m) | - |
| **target_water_level** | decimal(8,3) | 目标末水位(m) | - |
| **status** | int | 状态 | 0=待计算,1=计算中,2=成功,3=失败 |
| **rainfall_data** | text | 降雨数据(JSON) | - |
| **data_source** | int | 数据来源 | simulation/diagnosis: 1=历史真实,2=Agent虚拟,3=用户手动 |
| **agent_task_id** | varchar(64) | Agent任务ID | simulation/diagnosis: Agent创建时填写 |
| deleted | bit(1) | 是否删除 | - |
| tenant_id | bigint | 租户ID | diagnosis-verification: 可能不过滤 |

#### 查询规则

```sql
-- ✅ 正确: deleted=0 + 状态过滤
SELECT id, name, start_time, end_time, adjusted_water_level, target_water_level
FROM srm_flood_history_base
WHERE deleted = 0
  AND status = 2  -- 仅已完成
ORDER BY start_time DESC
LIMIT 20;

-- simulation/diagnosis: 包含 Agent 虚拟场景
SELECT * FROM srm_flood_history_base
WHERE deleted = 0
  AND data_source IN (1, 2)  -- 包含历史真实 + Agent虚拟
ORDER BY start_time DESC;
```

#### 特殊注意

- simulation v1.9.3 新增 `data_source` 和 `agent_task_id` 字段
- `rainfall_data` 为 JSON 格式,需在应用层解析

---

### 4. model_result_files (模型结果文件表) ⭐⭐

**使用 Skill**: 2/5 (forecasting, simulation)

#### 字段说明

| 字段 | 类型 | 说明 | 特殊规则 |
|------|------|------|---------|
| id | bigint | 主键 | - |
| **taskid** | **varbinary(32)** | 任务ID | ⚠️ **varbinary**,JOIN 需 CAST |
| **type** | tinyint | 结果类型 | **1=预报来水过程,2=调度流量过程** |
| target_water_level | varchar(50) | 目标水位(m) | VARCHAR,数值比较需 CAST |
| adjusted_water_level | varchar(50) | 起调水位(m) | VARCHAR,数值比较需 CAST |
| extend | text | 扩展信息(JSON) | - |
| create_time | datetime | 创建时间 | - |
| tenant_id | bigint | 租户ID | - |
| **deleted** | — | **无此列** | ⚠️ **不要加 deleted=0** |

#### 查询规则

```sql
-- ✅ 正确: type=1 (预报来水过程) + 无 deleted 过滤
SELECT taskid, type, target_water_level, adjusted_water_level, create_time
FROM model_result_files
WHERE type = 1
  AND tenant_id = 18
  AND create_time <= NOW()
ORDER BY create_time DESC
LIMIT 10;

-- ❌ 错误: 加了不存在的 deleted=0
SELECT * FROM model_result_files WHERE type = 1 AND deleted = 0;
```

#### 特殊注意

- ⚠️ **无 deleted 列**: 不要加 `AND deleted = 0`
- ⚠️ **taskid 为 varbinary**: JOIN 时必须 `CAST(taskid AS CHAR)`
- ⚠️ **水位列为 VARCHAR**: 数值比较需 `CAST(adjusted_water_level AS DECIMAL(10,3))`
- **type 字段**: 1=预报来水过程, 2=调度流量过程 (forecasting 用 type=1, simulation 用 type=2)

---

### 5. ew_info_message (告警消息表) ⭐⭐

**使用 Skill**: 2/5 (early-warning, diagnosis-verification)

#### 字段说明

| 字段 | 类型 | 说明 | 特殊规则 |
|------|------|------|---------|
| id | bigint | 主键 | - |
| **ew_name** | varchar(255) | 告警名称 | - |
| **st_code** | varchar(255) | 测站编码 | - |
| **level_r** | char(2) | 告警级别 | 1=红色(I级),2=橙色(II级),3=黄色(III级),4=蓝色(IV级) |
| **value** | varchar(255) | 告警值 | - |
| **gather_time** | datetime | 采集时间 | - |
| **message_confirm** | bit(1) | 是否确认 | 0=未确认,1=已确认 |
| deleted | bit(1) | 是否删除 | - |
| tenant_id | bigint | 租户ID | 通常不过滤 (告警跨租户) |

#### 查询规则

```sql
-- ✅ 正确: deleted=0 + 时间范围 + 级别排序
SELECT id, ew_name, st_code, level_r, value, gather_time, message_confirm
FROM ew_info_message
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY
  CASE level_r WHEN '1' THEN 1 WHEN '2' THEN 2 WHEN '3' THEN 3 WHEN '4' THEN 4 END,
  create_time DESC
LIMIT 50;

-- ❌ 错误: 无时间范围（大表可能百万级）
SELECT * FROM ew_info_message WHERE deleted = 0;
```

#### 特殊注意

- 告警级别排序: 红色(I级) → 橙色(II级) → 黄色(III级) → 蓝色(IV级)
- 通常不过滤 tenant_id (告警可能跨租户)

---

### 6. f_rnfl_h (和风逐时降雨预报) ⭐⭐⭐

**使用 Skill**: 1/5 (仅 forecasting)

#### 字段说明

| 字段 | 类型 | 说明 | 特殊规则 |
|------|------|------|---------|
| id | bigint | 主键 | - |
| **RN** | decimal(7,1) | 预报降雨量(mm) | **列名大写** |
| **YMDH** | datetime | 预报目标时间 | **列名大写** |
| **FYMDH** | datetime | 预报发布时间 | **列名大写** |
| UNITNAME | varchar(50) | 发布单位 | 1=和风天气 |
| deleted | bit(1) | 是否删除 | - |
| **tenant_id** | — | **无此列** | ⚠️ **不要加 tenant 过滤** |

#### 查询规则

```sql
-- ✅ 正确: 无 tenant 过滤 + 按 FYMDH 取最新批次
SELECT RN, YMDH, FYMDH, UNITNAME
FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 48 HOUR)
  AND FYMDH = (SELECT MAX(FYMDH) FROM f_rnfl_h WHERE type = 1 AND deleted = 0)
  AND deleted = 0
ORDER BY YMDH;

-- ❌ 错误: 加了不存在的 tenant_id
SELECT * FROM f_rnfl_h WHERE tenant_id = 18 AND deleted = 0;
```

#### 特殊注意

- ⚠️ **无 tenant_id 列**: 不要加 tenant 过滤
- ⚠️ **列名大写**: RN, YMDH, FYMDH, UNITNAME (MySQL 大小写不敏感,但保持大写与现网一致)
- **取最新预报**: 先 `MAX(FYMDH)` 确定最新批次,再按 YMDH 查具体时段

---

## 📚 辅助表速查

### att_res_flse_lim (汛限水位表)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| **flse_lim_stag** | decimal(8,3) | 汛限水位(m) |
| flood_season_name | varchar(50) | 汛期名称 |
| flood_season_start | varchar(10) | 汛期开始(MMdd) |
| flood_season_end | varchar(10) | 汛期结束(MMdd) |
| **deleted** | — | **无此列** |

**查询规则**:
- ⚠️ **无 deleted 列**: 不要加 `deleted = 0`
- 按当前日期 `DATE_FORMAT(NOW(), '%m%d')` 匹配汛期
- 非汛期回退到 `att_res_base.fl_low_lim_lev`

### model_config (系统配置表)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| **config_key** | varchar(100) | 配置键 (**不是 key_name**) |
| **value** | text | 配置值 |
| tenant_id | bigint | 租户ID |
| deleted | bit(1) | 是否删除 |

**关键配置键**:
- `st_rsvr_r_master`: 主水位测站编码 ( forecasting/simulation 用)
- `st_pptn_r_master`: 主雨量测站编码 (forecasting/simulation 用)
- `max_water_level`, `min_water_level`: 水位阈值
- `max_drainage_capacity`, `safe_drainage_capacity`: 泄量阈值

**查询规则**: `WHERE config_key = 'st_rsvr_r_master' AND tenant_id = 18 AND deleted = 0`

### dispatch_history (调度历史表)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| tm | datetime | 预报时刻 |
| dispatch_opening | varchar(50) | 闸门开度 |
| gate_opening_flow | varchar(50) | 闸门流量(m³/s) |
| **task_id** | varchar(32) | 关联 model_result_files.taskid (**下划线**) |
| create_time | datetime | 创建时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

**查询规则**:
- ⚠️ **不要按 tm 直接查**: 必须通过 `task_id` 关联 `model_result_files.taskid`
- ⚠️ **task_id 有下划线**: 与 `model_result_files.taskid` (无下划线) 不同

---

## 🔗 关键 JOIN 关系

### 1. model_result_files ⟕ st_mx_preset_cal_r

```sql
SELECT m.taskid, m.target_water_level, m.adjusted_water_level,
       s.tm, s.type AS series_type, s.vals
FROM model_result_files m
JOIN st_mx_preset_cal_r s
  ON s.taskid = CAST(m.taskid AS CHAR)  -- ⚠️ varbinary → varchar CAST
WHERE m.type = 1
  AND m.tenant_id = 18
  AND s.type IN ('21', '22')  -- 21=流量, 22=水位
ORDER BY s.tm;
```

### 2. model_result_files ⟕ dispatch_history

```sql
SELECT m.taskid, m.create_time,
       d.dispatch_opening, d.gate_opening_flow
FROM model_result_files m
LEFT JOIN dispatch_history d
  ON d.task_id = CAST(m.taskid AS CHAR)  -- ⚠️ task_id (下划线) ⟕ taskid (无下划线)
WHERE m.type = 2
  AND m.tenant_id = 18
ORDER BY m.create_time DESC;
```

### 3. srm_flood_history_base ⟕ srm_flood_history_result

```sql
SELECT b.name, b.start_time, b.end_time,
       r.type_name, r.vals, r.tm, r.sort
FROM srm_flood_history_base b
JOIN srm_flood_history_result r
  ON r.flood_id = b.id
WHERE b.id = %s
  AND b.deleted = 0
  AND r.deleted = 0
ORDER BY r.type, r.tm;
```

---

## 🚀 快速查询模板

### 模板 1: 查询当前水位 (5/5 skill 通用)

```sql
SELECT rz, inq, otq, w, tm
FROM st_rsvr_r
WHERE deleted = 0
  AND rz IS NOT NULL
ORDER BY tm DESC
LIMIT 1;
```

### 模板 2: 查询最近降雨 (4/5 skill 通用)

```sql
SELECT p, dr, tm
FROM st_pptn_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL %s HOUR)
ORDER BY tm DESC
LIMIT %s;
```

### 模板 3: 查询历史洪水 (3/5 skill 通用)

```sql
SELECT id, name, start_time, end_time,
       adjusted_water_level, target_water_level, status
FROM srm_flood_history_base
WHERE deleted = 0
  AND status = 2  -- 仅已完成
ORDER BY start_time DESC
LIMIT %s;
```

### 模板 4: 查询告警堆积 (2/5 skill 通用)

```sql
SELECT COUNT(*) as count,
       SUM(CASE WHEN level_r = '1' THEN 1 ELSE 0 END) as 红色,
       SUM(CASE WHEN level_r = '2' THEN 1 ELSE 0 END) as 橙色,
       SUM(CASE WHEN level_r = '3' THEN 1 ELSE 0 END) as 黄色,
       SUM(CASE WHEN level_r = '4' THEN 1 ELSE 0 END) as 蓝色
FROM ew_info_message
WHERE deleted = 0
  AND message_confirm = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL %s DAY);
```

---

## 📏 索引建议

### 水位/降雨查询 (高频)

```sql
-- st_rsvr_r 时间范围查询优化
CREATE INDEX idx_rsvr_r_tm_deleted ON st_rsvr_r(tm, deleted);

-- st_pptn_r 时间范围查询优化
CREATE INDEX idx_pptn_r_tm_deleted ON st_pptn_r(tm, deleted);

-- 按测站查询优化
CREATE INDEX idx_rsvr_r_stcd_tm ON st_rsvr_r(stcd, tm);
CREATE INDEX idx_pptn_r_stcd_tm ON st_pptn_r(stcd, tm);
```

### 告警查询 (early-warning/diagnosis)

```sql
-- 告警级别+时间范围查询
CREATE INDEX idx_ew_info_level_time ON ew_info_message(level_r, create_time);

-- 未确认告警查询
CREATE INDEX idx_ew_info_confirm_deleted ON ew_info_message(message_confirm, deleted, create_time);
```

### 历史洪水查询 (forecasting/simulation/diagnosis)

```sql
-- 状态+时间范围查询
CREATE INDEX idx_flood_history_status_time ON srm_flood_history_base(status, create_time);

-- 洪水结果关联
CREATE INDEX idx_flood_result_flood_id ON srm_flood_history_result(flood_id, type);
```

### 模型结果查询 (forecasting/simulation)

```sql
-- 按类型+创建时间查询
CREATE INDEX idx_model_result_type_time ON model_result_files(type, create_time);

-- taskid JOIN 优化
CREATE INDEX idx_model_result_taskid ON model_result_files(taskid);
CREATE INDEX idx_mx_preset_cal_taskid ON st_mx_preset_cal_r(taskid);
```

### 降雨预报查询 (forecasting)

```sql
-- 逐时预报查询
CREATE INDEX idx_rnfl_h_fymdh_ymdh ON f_rnfl_h(fymdh, ymdh);

-- 按类型+时间查询
CREATE INDEX idx_rnfl_h_type_ymdh ON f_rnfl_h(type, ymdh);
```

---

## 🔗 相关文档

### Skill 专用文档

| Skill | 文档路径 | 说明 |
|-------|---------|------|
| **forecasting** | `forecasting/references/table-schema.md` | 预报场景详细表结构 (371 行) |
| **plan-generation** | `plan-generation/references/table-schema.md` | 预案场景详细表结构 (630 行) |
| **simulation** | `simulation/db-config.md` | 预演场景表结构 |
| **early-warning** | `early-warning/db-config.md` | 告警场景表结构 |
| **diagnosis-verification** | `diagnosis-verification/db-config.md` | 诊断场景表结构 |

### 配置标准文档

| 文档路径 | 说明 |
|---------|------|
| `../DB-CONFIG-STANDARD.md` | SmartTwinRes Skills 数据库配置标准 |
| `../docs/db-credential-config.md` | 数据库凭据环境变量配置指南 |
| `../lib/db.py` | 统一数据库连接库 (Python) |

---

## 📝 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-07-11 | v1.0 | 初始版本,整合 5 个 skill 的共用表 Schema |
| 2026-07-11 | v1.0 | 添加 skill 使用矩阵、tenant/deleted 过滤规则、JOIN 示例 |
| 2026-07-11 | v1.0 | 迁移至 SmartTwinRes-skills/docs/ 统一文档目录 |

---

## ew_info_message：跨租户可见（显式设计决策）

**决策**（2026-08-20，评审 S3 落档）：告警表 `ew_info_message` 在全部 skill 中
不做 tenant_id 过滤，保持全库可见。

**理由**：
1. 告警由中央告警引擎写入，行内无水库归属维度可用；
2. supervisor `cmd_health` 告警堆积探针需要全局视角；
3. `lib/filters.py` 规则表自始标注 `ew_info_message: filter:False`（告警跨租户，不强制）。

**已知影响面（接受）**：
- early-warning 的告警查询与 diagnosis-verification `check_alerts` 会看到
  其他水库的告警；
- supervisor 场景 D 仲裁（`arbitrate_emergency`）消费 `query_high_level` 输出，
  A 库高级告警可能抬高 B 库应急风险判定——按"防洪优先、宁高勿低"原则接受。

**变更条件**：若告警表将来增加水库/租户归属列，须重评本决策并补
`tenant_id = %s` 过滤。

---

*维护: SmartTwinRes Team*  
*来源: forecasting/references/table-schema.md + plan-generation/references/table-schema.md*
