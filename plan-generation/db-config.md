# 数据库连接配置

## 连接信息

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **主机** | 127.0.0.1（默认，可通过 SRM_DB_HOST 环境变量覆盖） | SmartResMatrix 数据库 |
| **端口** | 3306 | MySQL 默认端口 |
| **数据库** | powerelf_srm_yml | 水库业务数据库 |
| **用户** | root | 只读用户 |
| **密码** | ${SRM_DB_PASSWORD} | 数据库密码（必须通过环境变量设置，禁止明文） |

## 连接命令

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME"
```

## 环境变量设置

```bash
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD=***  # 禁止明文口令，从凭据存储读取
```

## 核心数据表

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
| humidity | varchar(10) | 湿度 |
| pressure | varchar(10) | 气压 |
| vis | varchar(10) | 能见度 |

### 逐时降雨预报表 (f_rnfl_h)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| fymdh | datetime | 发布时间 |
| ymdh | datetime | 预报时间 |
| rn | decimal(7,1) | 降水量(mm) |
| pop | int | 降水概率(%) |
| text | varchar(50) | 天气描述 |
| temp | varchar(10) | 温度 |
| wind_dir | varchar(20) | 风向 |
| wind_speed | varchar(10) | 风速 |
| unitname | varchar(50) | 发布单位(1=和风天气) |
| deleted | bit(1) | 是否删除 |

### 气象预警表 (weather_warn)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| docid | varchar(100) | 预警ID |
| docabstract | text | 预警内容 |
| docpubtime | varchar(50) | 发布时间 |
| docpuburl | varchar(500) | 发布链接 |
| warn_status | varchar(5) | 状态(1=正在预警,2=解除) |
| update_time | varchar(50) | 更新时间 |

### 水库水情表 (st_rsvr_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| st_id | bigint | 测站ID |
| eq_code | varchar(20) | 设备编码 |
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
| res_guid | varchar(50) | 水库GUID |
| deleted | bit(1) | 是否删除 |

### 历史洪水表 (srm_flood_history_base)

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
| rsvr_remake | text | 水库水情描述 |
| river_remake | text | 河道水情描述 |
| pptn_remake | text | 雨情描述 |
| deleted | bit(1) | 是否删除 |

### 历史洪水结果表 (srm_flood_history_result)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| type | int | 类型(1=入库流量,2=出库流量,3=水位,4=河道水位,5=河道流量,6=降雨,7=统计指标) |
| vals | double | 结果值 |
| flood_id | bigint | 关联洪水ID |
| tm | datetime | 时间 |
| type_name | varchar(50) | 类型名称 |
| sort | int | 排序 |

### 模型结果文件表 (model_result_files)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| taskid | varchar(32) | 任务ID |
| scheme_id | varchar(64) | 方案ID |
| version | varchar(255) | 版本号 |
| file_name | varchar(255) | 文件名 |
| file_path | varchar(512) | 文件路径 |
| start_time | datetime | 开始时间 |
| end_time | datetime | 结束时间 |
| type | tinyint | 类型(1=预报,2=预案调度流速,3=滚动预报,4=预案开度,5=轮播流速,6=轮播开度) |
| extend | text | 扩展字段(JSON) |
| alias | varchar(255) | 别名 |
| target_water_level | varchar(50) | 目标水位 |
| adjusted_water_level | varchar(50) | 起调水位 |
| deleted | bit(1) | 是否删除 |

### 调度场景表 (srm_scheduling_scenario)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| name | varchar(200) | 场景名称 |
| scheduling_target | varchar(50) | 调度目标 |
| scheduling_model | varchar(50) | 调度模式 |
| remark | text | 描述 |
| extend | text | 扩展字段(JSON，含水位/流量约束) |
| def_flg | bit(1) | 是否默认 |
| deleted | bit(1) | 是否删除 |

### 系统配置表 (model_config)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| config_key | varchar(100) | 配置键 |
| value | text | 配置值 |
| tenant_id | bigint | 租户ID |
| deleted | bit(1) | 是否删除 |

### 降雨数据表 (st_pptn_r)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| st_id | bigint | 测站ID |
| eq_code | varchar(20) | 设备编码 |
| p | decimal(7,1) | 降雨量(mm) |
| dr | decimal(5,1) | 时段(h) |
| tm | datetime | 观测时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

### 调度历史表 (dispatch_history)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| tm | datetime | 预报时刻 |
| dispatch_opening | varchar(50) | 闸门开度 |
| gate_opening_flow | varchar(50) | 闸门流量(m³/s) |
| task_id | varchar(32) | 关联 model_result_files.taskid |
| create_time | datetime | 创建时间 |
| deleted | bit(1) | 是否删除 |
| tenant_id | bigint | 租户ID |

**关联方式**: 通过 `task_id` 与 `model_result_files.taskid` 关联，不直接按 tm 查询。

### 水库基础信息表 (att_res_base)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| res_name | varchar(100) | 水库名称 |
| fl_low_lim_lev | decimal(8,3) | 汛限水位/正常蓄水位(m) — att_res_flse_lim 为空时的降级数据源 |
| dead_level | decimal(8,3) | 死水位(m) |
| total_cap | decimal(12,3) | 总库容(万m³) |
| res_guid | varchar(50) | 水库GUID |
| deleted | bit(1) | 是否删除 |

**注意**: 通常只有 1 条记录。当 att_res_flse_lim 表无数据时，使用 fl_low_lim_lev 作为参考水位。

## 索引建议

```sql
-- 降雨预报查询优化
CREATE INDEX idx_rnfl_h_ymdh ON f_rnfl_h(ymdh, deleted);

-- 水情查询优化
CREATE INDEX idx_rsvr_r_tm ON st_rsvr_r(tm, deleted);

-- 预警查询优化
CREATE INDEX idx_weather_warn_status ON weather_warn(warn_status);

-- 历史洪水查询优化
CREATE INDEX idx_flood_history_status ON srm_flood_history_base(status, deleted);
```
