# 数据库连接配置

> **标准文档**：完整的配置规范和命名空间说明见 [`docs/db-credential-config.md`](docs/db-credential-config.md)。

## 连接信息

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **主机** | ${SRM_DB_HOST:-127.0.0.1} | SmartResMatrix 数据库（本地运行目标；`192.168.100.103` 仅作迁移只读源） |
| **端口** | ${SRM_DB_PORT:-3306} | MySQL 8.0.46 默认端口 |
| **数据库** | ${SRM_DB_NAME:-powerelf_srm_yml} | 水库业务数据库 |
| **用户** | ${SRM_DB_USER:-root} | 只读用户 |
| **密码** | ${SRM_DB_PASSWORD} | 数据库密码（**必须通过环境变量设置，严禁写入本仓库**） |

## 连接命令

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p"$SRM_DB_PASSWORD" powerelf_srm_yml
```

## 环境变量设置

```bash
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD   # 预先从 application-prod.yaml 取值并 export；严禁写入本仓库
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

### 逐时降雨预报表 (f_rnfl_h)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| RN | decimal(7,1) | 降水量(mm) |
| YMDH | datetime | 预报时间 |
| FYMDH | datetime | 发布时间 |
| UNITNAME | varchar(50) | 发布单位(1=和风天气) |

**注意**: `f_rnfl_h` **不加 tenant 过滤**（无可用 tenant 字段/无需过滤）。

### 预报模型计算结果表 (st_mx_preset_cal_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| type | int | 类型（21=入库流量预报, 22=出库流量预报） |
| vals | double | 结果值 |
| taskid | varchar | 任务ID（**varchar** 拼写，见末尾 taskid 三拼写说明） |
| tm | datetime | 时间点 |

### 模型结果文件表 (model_result_files)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| target_water_level | varchar(50) | 目标水位 |
| adjusted_water_level | varchar(50) | 起调水位 |
| extend | text | 扩展字段(JSON) |
| taskid | varbinary(32) | 任务ID（**varbinary** 拼写，见末尾 taskid 三拼写说明） |
| type | tinyint | 类型(1=预报,2=预案调度流速,...) |

**注意**: `model_result_files` **无 `deleted` 列**，查询时不要加 `deleted = 0` 过滤。

### 实测降雨数据表 (st_pptn_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| p | decimal(7,1) | 降雨量(mm) |
| dr | decimal(5,1) | 时段(h) |
| dyp | decimal(7,1) | 日降雨量(mm) |
| tm | datetime | 观测时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

### 降雨预报表 (st_pptn_re_forecast)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| drp | decimal(7,1) | 预报降雨量(mm) |
| re_id | bigint | 关联预报ID |
| tm | datetime | 预报时间 |
| deleted | bit(1) | 是否删除 |

### 天气预报表 (weather_info)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| fx_date | varchar(20) | 预报日期 |
| temp_max | varchar(10) | 最高温度 |
| temp_min | varchar(10) | 最低温度 |
| text_day | varchar(50) | 白天天气 |
| text_night | varchar(50) | 夜间天气 |
| precip | varchar(10) | 降水量 |

**注意**: `weather_info` / `weather_warn` **无 `tenant_id` 列**，不要加 tenant 过滤。

### 气象预警表 (weather_warn)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| docid | varchar(100) | 预警ID |
| docabstract | text | 预警内容 |
| docpubtime | varchar(50) | 发布时间 |
| warn_status | varchar(5) | 状态(1=正在预警,2=解除) |

**注意**: `weather_info` / `weather_warn` **无 `tenant_id` 列**，不要加 tenant 过滤。

### 调度历史表 (dispatch_history)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| tm | datetime | 预报时刻 |
| dispatch_opening | varchar(50) | 闸门开度 |
| gate_opening_flow | varchar(50) | 闸门流量(m³/s) |
| task_id | varchar(32) | 关联 model_result_files.taskid（**下划线** 拼写，见末尾 taskid 三拼写说明） |
| create_time | datetime | 创建时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

**关联方式**: 通过 `task_id` 与 `model_result_files.taskid` 关联，不直接按 tm 查询。

### 汛限水位表 (att_res_flse_lim)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| flse_lim_stag | decimal(8,3) | 汛限水位(m) |
| flood_season_name | varchar(50) | 汛期名称 |
| flood_season_start | varchar(10) | 汛期开始(MMdd) |
| flood_season_end | varchar(10) | 汛期结束(MMdd) |
| deleted | bit(1) | 是否删除 |

### 系统配置表 (model_config)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| config_key | varchar(100) | 配置键 |
| value | text | 配置值 |
| tenant_id | bigint | 租户ID |
| deleted | bit(1) | 是否删除 |

## 重要 Caveats（查询时务必遵守）

1. **`f_rnfl_h` 不加 tenant 过滤** —— 该表无可用 tenant 字段，直接按 YMDH/FYMDH 时间窗口查询即可。
2. **`weather_info` / `weather_warn` 无 `tenant_id` 列** —— 查询这两张表时不要拼 `AND tenant_id = ...` 条件。
3. **`model_result_files` 无 `deleted` 列** —— 查询时不要加 `deleted = 0` 过滤（否则会报未知列错误）。

### taskid 三种拼写说明

不同表里「任务ID」的列名/类型不一致，JOIN 时必须显式转换类型，否则会隐式截断或报类型不匹配：

| 表 | 列名 | 类型 |
|----|------|------|
| `dispatch_history` | `task_id` | varchar(32) — **下划线** |
| `model_result_files` | `taskid` | **varbinary**(32) |
| `st_mx_preset_cal_r` | `taskid` | **varchar** — 无下划线 |

JOIN 示例（先转字符串再比较）：

```sql
SELECT m.*, d.dispatch_opening
FROM model_result_files m
LEFT JOIN dispatch_history d
  ON d.task_id = CAST(m.taskid AS CHAR)
WHERE m.type = 1;
```

## 索引建议

```sql
-- 降雨预报查询优化
CREATE INDEX idx_rnfl_h_ymdh ON f_rnfl_h(YMDH);
CREATE INDEX idx_rnfl_h_fymdh ON f_rnfl_h(FYMDH);

-- 水情查询优化
CREATE INDEX idx_rsvr_r_tm ON st_rsvr_r(tm, deleted);

-- 预报模型结果查询优化
CREATE INDEX idx_mx_preset_cal_taskid ON st_mx_preset_cal_r(taskid);
```
