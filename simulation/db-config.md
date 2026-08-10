# 数据库连接配置

## 连接信息

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **主机** | ${SRM_DB_HOST:-127.0.0.1} | SmartResMatrix 数据库 |
| **端口** | ${SRM_DB_PORT:-3306} | MySQL 默认端口 |
| **数据库** | ${SRM_DB_NAME:-powerelf_srm_yml} | 水库业务数据库 |
| **用户** | ${SRM_DB_USER:-root} | 只读用户 |
| **密码** | ${SRM_DB_PASSWORD} | 数据库密码（必须通过环境变量设置） |

## 环境变量设置

```bash
export SRM_DB_HOST=192.168.100.103
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD=***  # 禁止明文口令，从凭据存储读取
```

## 核心数据表

### 水库水情表 (st_rsvr_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| rz | decimal(8,3) | 水位(m) |
| inq | decimal(10,3) | 入库流量(m³/s) |
| otq | decimal(10,3) | 出库流量(m³/s) |
| w | decimal(12,3) | 蓄水量(万m³) |
| tm | datetime | 观测时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

### 汛限水位表 (att_res_flse_lim)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| flse_lim_stag | decimal(8,3) | 汛限水位(m) |
| flood_season_name | varchar(50) | 汛期名称 |
| flood_season_start | varchar(10) | 汛期开始(MMdd) |
| flood_season_end | varchar(10) | 汛期结束(MMdd) |
| deleted | bit(1) | 是否删除 |

### 水位-库容曲线表 (att_res_stag_cap_disc)

| 字段 | 类型 | 说明 |
|------|------|------|
| stag | decimal(8,3) | 水位(m) |
| cap | decimal(12,3) | 库容(万m³) |

### 泄流曲线表 (att_res_discharge_curve)

| 字段 | 类型 | 说明 |
|------|------|------|
| stag | decimal(8,3) | 水位(m) |
| q | decimal(10,3) | 流量(m³/s) |

### 系统配置表 (model_config)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| config_key | varchar(100) | 配置键 |
| value | text | 配置值 |
| tenant_id | bigint | 租户ID |
| deleted | bit(1) | 是否删除 |

### 历史洪水基础表 (srm_flood_history_base)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| name | varchar(200) | 名称 |
| remake | text | 描述 |
| start_time | datetime | 洪水开始时间 |
| end_time | datetime | 洪水结束时间 |
| adjusted_water_level | decimal(8,3) | 起调水位(m) |
| target_water_level | decimal(8,3) | 目标末水位(m) |
| status | int | 状态(0=待计算,1=计算中,2=成功,3=失败) |
| rainfall_data | text | 降雨数据(JSON) |
| data_source | int | 数据来源(1=历史真实,2=Agent虚拟,3=用户手动) |
| agent_task_id | varchar(64) | Agent任务ID |
| deleted | bit(1) | 是否删除 |

### 历史洪水结果表 (srm_flood_history_result)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| type | int | 类型(1=入库流量,2=出库流量,3=水库水位,4=河道水位,5=河道流量,6=降雨,7=统计指标) |
| vals | double | 结果值 |
| flood_id | bigint | 关联洪水ID |
| tm | datetime | 时间点 |
| type_name | varchar(50) | 类型名称 |
| sort | int | 排序 |
| deleted | int | 是否删除(0=否) |
| tenant_id | bigint | 租户ID |
| create_time | datetime | 创建时间 |
| update_time | datetime | 更新时间 |

### 调度场景表 (srm_scheduling_scenario)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| name | varchar(200) | 场景名称 |
| scheduling_target | varchar(50) | 调度目标 |
| scheduling_model | varchar(50) | 调度模式 |
| extend | text | 扩展字段(JSON) |
| def_flg | bit(1) | 是否默认 |
| deleted | bit(1) | 是否删除 |

### 模型结果文件表 (model_result_files)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| scheme_id | varchar(64) | 方案ID |
| alias | varchar(255) | 别名 |
| target_water_level | varchar(50) | 目标水位 |
| adjusted_water_level | varchar(50) | 起调水位 |
| start_time | datetime | 开始时间 |
| end_time | datetime | 结束时间 |
| type | tinyint | 类型(1=预报,2=预案调度流速,...) |
| extend | text | 扩展字段(JSON) |
| deleted | bit(1) | 是否删除 |

### 降雨数据表 (st_pptn_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| p | decimal(7,1) | 降雨量(mm) |
| dr | decimal(5,1) | 时段(h) |
| tm | datetime | 观测时间 |
| deleted | bit(1) | 是否删除 |

## 数据迁移：srm_flood_history_base 增加 data_source 字段

### 变更说明

为区分历史真实洪水和 Agent 虚拟场景，需在 `srm_flood_history_base` 表增加 `data_source` 和 `agent_task_id` 字段。

### 迁移 SQL

```sql
-- 1. 增加 data_source 字段
ALTER TABLE srm_flood_history_base
  ADD COLUMN data_source INT DEFAULT 1
  COMMENT '数据来源: 1=历史真实, 2=Agent虚拟场景, 3=用户手动创建';

-- 2. 增加 agent_task_id 字段
ALTER TABLE srm_flood_history_base
  ADD COLUMN agent_task_id VARCHAR(64)
  COMMENT 'Agent任务ID（Agent创建时填写）';

-- 3. 审计：确认现有数据
SELECT status, data_source, COUNT(*)
FROM srm_flood_history_base
WHERE deleted = 0
GROUP BY status, data_source;
```

### 数据隔离策略

| 调用方 | data_source 过滤 | 说明 |
|--------|-----------------|------|
| 前端历史洪水列表 | `data_source = 1` | 只看真实历史 |
| Agent 查询相似洪水 | `data_source IN (1, 2)` | 包含虚拟场景 |
| 用户手动创建 | `data_source = 3` | 前端手动录入 |

### 注意事项

- 执行 ALTER 前先审计现有数据，确认 status=2 的记录都是真实历史洪水
- 如有测试/虚拟记录，手动设置 data_source=3：
  ```sql
  UPDATE srm_flood_history_base
  SET data_source = 3
  WHERE name LIKE '%测试%' OR name LIKE '%虚拟%';
  ```
- data_source 默认值为 1（历史真实），确保现有数据不受影响
