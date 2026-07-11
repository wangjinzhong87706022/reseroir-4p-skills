# SQL 查询模板（预报场景）

> **用途**：LLM 走"灵活路径"时参考此文件拼接 SQL
> **参数格式**：
> - `{param}` — 必填参数，替换为实际值
> - `{param|default}` — 可选参数，default 为默认值（可保留默认不替换）
> - `{ 可选条件 }` — 整行为可选，不需要时删除该行

## 使用规则

1. 替换 `{...}` 占位符为实际值后执行
2. **不要移除 LIMIT 和 deleted=0**（按表，见 `table-schema.md` 规则1：`model_result_files`/`weather_warn`/`att_res_flse_lim` **无** deleted 列）
3. ⚠️ 标记的模板涉及大表，务必保留时间范围条件
4. **master stcd 绝不硬编码**，一律走 `model_config` 子查询
5. **taskid JOIN 必须 CAST**：`ON s.taskid = CAST(m.taskid AS CHAR)`
6. **tenant 策略**：st_*/srm_flood_history_base/forecast_accuracy_record/dispatch_history/model_config 加 `tenant_id = 18`；`f_rnfl_h`/`weather_info`/`weather_warn` **无 tenant 列，不加**
7. 拼接前先读 `table-schema.md` 确认字段名（注意 `f_rnfl_h` 列名大写 `RN/YMDH/FYMDH`）

---

## 单表查询（Q1–Q12，对应 query_forecast_data.py 的 12 个 --type）

### Q1: 实时水位 ⚠️

适用表：`st_rsvr_r`（19万行⚠️）｜tenant：=18｜对应 `--type current_water_level`

```sql
SELECT rz, inq, otq, w, tm, stcd
FROM st_rsvr_r
WHERE tenant_id = 18 AND deleted = 0
  AND stcd = (SELECT value FROM model_config
              WHERE config_key = 'st_rsvr_r_master' AND tenant_id = 18 AND deleted = 0 LIMIT 1)
ORDER BY tm DESC
LIMIT {limit|1}
```

### Q2: 降雨预报（和风逐时）⚠️

适用表：`f_rnfl_h`（无 tenant）｜对应 `--type rainfall_forecast`

```sql
SELECT RN, YMDH, FYMDH, UNITNAME
FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {hours|48} HOUR)
  AND deleted = 0
ORDER BY YMDH
LIMIT {limit|1000}
```

### Q3: 气象预警（生效中）

适用表：`weather_warn`（**无 tenant，无 deleted**）｜对应 `--type weather_warning`

```sql
SELECT docid, docabstract, chnlname, docpubtime, warn_status
FROM weather_warn
WHERE warn_status = '1'
ORDER BY docpubtime DESC
LIMIT {limit|20}
```

### Q4: 汛限水位（分汛期，带回退）

适用表：`att_res_flse_lim`（无 deleted）→ 回退 `att_res_base`｜对应 `--type flood_limit`

```sql
-- 主查询:当前汛期行
SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
FROM att_res_flse_lim
WHERE tenant_id = 18
  AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
  AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')
LIMIT 1
```

> **回退策略**：若上面返回空 → 取主汛期行；仍空 → `SELECT fl_low_lim_lev FROM att_res_base WHERE tenant_id=18 AND deleted=0 ORDER BY update_time DESC LIMIT 1`。**严禁硬编码 462.5**。

### Q5: 模型预报结果（CAST JOIN）⚠️

适用表：`model_result_files`（无 deleted）⟕ `st_mx_preset_cal_r`｜对应 `--type model_forecast_result`

```sql
SELECT m.taskid, m.target_water_level, m.adjusted_water_level, m.create_time,
       m.type AS file_type,
       s.tm, s.type AS series_type, s.vals, s.step
FROM model_result_files m
JOIN st_mx_preset_cal_r s ON s.taskid = CAST(m.taskid AS CHAR)
WHERE m.tenant_id = 18
  AND m.create_time = (SELECT MAX(create_time) FROM model_result_files
                       WHERE tenant_id = 18 AND create_time <= NOW())
  AND s.type IN ('21', '22')
ORDER BY s.tm
LIMIT {limit|1000}
```

### Q6: 分区降雨预报 ⚠️

适用表：`st_pptn_re_forecast`（无 stcd，按 re_id）｜tenant：=18｜对应 `--type zonal_rainfall_forecast`

```sql
SELECT drp, dyp, intv, wth, tm, re_id
FROM st_pptn_re_forecast
WHERE tenant_id = 18 AND deleted = 0
  AND tm BETWEEN NOW() - INTERVAL 48 HOUR AND NOW() + INTERVAL 168 HOUR
ORDER BY tm
LIMIT {limit|1000}
```

### Q7: 水位过程线（近 12h）⚠️

适用表：`st_rsvr_r`｜tenant：=18｜对应 `--type water_level_curve`

```sql
SELECT rz, tm
FROM st_rsvr_r
WHERE tenant_id = 18 AND deleted = 0
  AND stcd = (SELECT value FROM model_config
              WHERE config_key = 'st_rsvr_r_master' AND tenant_id = 18 AND deleted = 0 LIMIT 1)
  AND tm >= NOW() - INTERVAL 12 HOUR
ORDER BY tm
```

### Q8: 历史洪水列表

适用表：`srm_flood_history_base`｜tenant：=18｜对应 `--type historical_floods`

```sql
SELECT id, name, start_time, end_time, target_water_level, adjusted_water_level,
       rainfall_data, status, data_source
FROM srm_flood_history_base
WHERE tenant_id = 18 AND deleted = 0
ORDER BY start_time DESC
LIMIT {limit|10}
```

### Q9: 预报精度统计（gated，先探测）

适用表：`forecast_accuracy_record`（mock 新表，可能为空）｜tenant：=18｜对应 `--type forecast_accuracy_stats`

```sql
-- 先探测表存在且非空(空 → 返回 gated 结构,绝不编造)
SELECT COUNT(*) AS c FROM forecast_accuracy_record WHERE tenant_id = 18;

-- 非空后聚合
SELECT COUNT(*) AS sample_count,
       ROUND(AVG(mape), 3) AS avg_mape,
       ROUND(MAX(mape), 3) AS max_mape,
       ROUND(MIN(mape), 3) AS min_mape,
       MAX(issued_tm) AS latest_issued
FROM forecast_accuracy_record WHERE tenant_id = 18
```

> **gated 策略**：表为空/查询失败 → 返回 `{"status":"insufficient","message":"精度数据不足/暂不可信"}`，不编数字。

### Q10: 多源降雨聚合

适用表：`f_rnfl_h` + `st_pptn_re_forecast` + `weather_info` + NMC fixture｜对应 `--type multi_source_overview`

```sql
-- 源1: 和风 168h 总量(无 tenant)
SELECT COUNT(*) AS n, ROUND(SUM(RN), 2) AS total_mm, MAX(YMDH) AS latest
FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND NOW() + INTERVAL 168 HOUR AND deleted = 0;

-- 源2: 分区 168h 总量(tenant=18)
SELECT COUNT(*) AS n, ROUND(SUM(drp), 2) AS total_mm, MAX(tm) AS latest
FROM st_pptn_re_forecast
WHERE tenant_id = 18 AND deleted = 0
  AND tm BETWEEN NOW() AND NOW() + INTERVAL 168 HOUR;

-- 源3: weather_info 近 30d(无 tenant)
SELECT COUNT(*) AS n, MAX(fx_date) AS latest_fx, MIN(fx_date) AS earliest_fx
FROM weather_info
WHERE fx_date >= CURDATE() - INTERVAL 30 DAY;
-- 源4: NMC fixture 文件存在性(脚本层判断 data/scenarios/nmc_rainfall_24.json)
```

### Q11: 系统配置（关键键）

适用表：`model_config`｜tenant：=18｜对应 `--type config`

```sql
SELECT config_key, value
FROM model_config
WHERE tenant_id = 18 AND deleted = 0
  AND config_key IN ('max_water_level', 'min_water_level',
                     'st_rsvr_r_master', 'st_pptn_r_master', 'Forecast_Q')
```

### Q12: full_context（聚合全部）

> 不写单一 SQL，由脚本聚合 Q1–Q11 全部结果 + `_meta{as_of, tenant, hours}`。对应 `--type full_context`。**SKILL.md 主入口优先调此类型**。

---

## 关联查询（J1–J4）

### J1: 预报 vs 实测降雨对照时间轴 ⚠️

适用表：`f_rnfl_h`（无 tenant）⟕ `st_pptn_r`（tenant=18）｜对应 `--type forecast_timeline`

```sql
-- 预报(未来)
SELECT YMDH, RN, FYMDH FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {hours|48} HOUR)
ORDER BY YMDH LIMIT {limit|1000};

-- 实测(过去同窗口,master stcd)
SELECT tm, dr FROM st_pptn_r
WHERE tenant_id = 18 AND deleted = 0
  AND stcd = (SELECT value FROM model_config
              WHERE config_key = 'st_pptn_r_master' AND tenant_id = 18 AND deleted = 0 LIMIT 1)
  AND tm >= NOW() - INTERVAL {hours|48} HOUR
ORDER BY tm LIMIT {limit|1000};
-- 脚本按 YYYY-MM-DD HH:00:00 对齐,计算 bias/MAE
```

### J2: 预案调度时序（CAST JOIN）

适用表：`model_result_files`（无 deleted）⟕ `dispatch_history`（tenant=18）

```sql
SELECT m.taskid, m.alias, m.target_water_level, m.adjusted_water_level,
       m.start_time, m.end_time, m.extend,
       d.tm, d.dispatch_opening, d.gate_opening_flow
FROM model_result_files m
LEFT JOIN dispatch_history d ON d.task_id = CAST(m.taskid AS CHAR) AND d.deleted = 0
WHERE m.type = 2 AND m.tenant_id = 18
  AND m.create_time = (SELECT MAX(create_time) FROM model_result_files
                       WHERE tenant_id = 18 AND type = 2)
ORDER BY d.tm
```

### J3: 多源降雨逐时对齐（fusion）

适用表：`f_rnfl_h` + `st_pptn_re_forecast` + `weather_info` + NMC fixture｜对应 `--type fusion_detail`

```sql
-- 和风逐时
SELECT YMDH, RN FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {hours|48} HOUR)
ORDER BY YMDH LIMIT {limit|1000};

-- 分区(同小时多 re_id 取均值)
SELECT tm, drp, re_id FROM st_pptn_re_forecast
WHERE tenant_id = 18 AND deleted = 0
  AND tm BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {hours|48} HOUR)
ORDER BY tm LIMIT {limit|1000};

-- weather_info 30d 日总量
SELECT fx_date, precip FROM weather_info
WHERE fx_date >= CURDATE() - INTERVAL 30 DAY ORDER BY fx_date;
-- NMC fixture 脚本层解析(diamond14_rainfall_24_json 外壳),取 contours max 值
-- 分歧标注: 逐小时 max-min RN > 20mm → disagreement=true
```

### J4: 相似洪水（按峰值水位接近度）

适用表：`srm_flood_history_base`｜tenant：=18｜对应 `--type similar_floods`

```sql
SELECT id, name, start_time, end_time,
       adjusted_water_level AS peak_water_level,
       target_water_level, status, data_source,
       ABS(adjusted_water_level - {water_level}) AS delta_m
FROM srm_flood_history_base
WHERE tenant_id = 18 AND deleted = 0
  AND adjusted_water_level IS NOT NULL
ORDER BY ABS(adjusted_water_level - {water_level})
LIMIT {limit|10}
```

> **峰值代理列**：`srm_flood_history_base` 无显式 peak_water_level，用 `adjusted_water_level`（起调水位）作为峰值代理。

---

## 精度分析（A1）

### A1: 精度报告（按源 MAPE + 置信分级 + gated）

适用表：`forecast_accuracy_record`｜tenant：=18｜对应 `--type accuracy_report`

```sql
-- 探测(空 → gated_flag=true, 绝不编造)
SELECT COUNT(*) AS c FROM forecast_accuracy_record WHERE tenant_id = 18;

-- 总体统计
SELECT COUNT(*) AS sample_count,
       ROUND(AVG(mape), 3) AS avg_mape,
       ROUND(MAX(mape), 3) AS max_mape,
       ROUND(MIN(mape), 3) AS min_mape,
       MAX(issued_tm) AS latest_issued,
       MIN(issued_tm) AS earliest_issued
FROM forecast_accuracy_record WHERE tenant_id = 18;

-- 按来源拆分
SELECT source, COUNT(*) AS sample_count,
       ROUND(AVG(mape), 3) AS avg_mape,
       ROUND(MAX(mape), 3) AS max_mape,
       ROUND(MIN(mape), 3) AS min_mape
FROM forecast_accuracy_record WHERE tenant_id = 18
GROUP BY source ORDER BY avg_mape;
```

> **置信分级（脚本层）**：MAPE<15%=高 / 15~30%=中 / >30%=低。`gated_flag` 恒 true（精度回灌链路 C1 缺陷未修），数据可信但需人工复核。

---

## 模板适用速查

| 用户意图 | 用哪个模板 | 主表 |
|---------|-----------|------|
| 当前水位多少 | Q1 / Q7 | st_rsvr_r |
| 未来下不下雨 | Q2 | f_rnfl_h |
| 有没有气象预警 | Q3 | weather_warn |
| 汛限水位是多少 | Q4 | att_res_flse_lim |
| 模型预报的来水过程 | Q5 | model_result_files ⟕ st_mx_preset_cal_r |
| 分区降雨预报 | Q6 | st_pptn_re_forecast |
| 预报准不准 | Q9 / A1 | forecast_accuracy_record |
| 多个源对比 | Q10 / J3 | f_rnfl_h + 多源 |
| 预报和实测差多少 | J1 | f_rnfl_h ⟕ st_pptn_r |
| 历史上类似水位 | J4 | srm_flood_history_base |
| 一键全量上下文 | Q12 (full_context) | 全部 |
