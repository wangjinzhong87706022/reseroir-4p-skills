# SQL 查询模板

> **用途**：LLM 走"灵活路径"时参考此文件拼接 SQL
> **参数格式**：
> - `{param}` — 必填参数，替换为实际值
> - `{param|default}` — 可选参数，default 为默认值（可保留默认不替换）
> - `{ 可选条件 }` — 整行为可选，不需要时删除该行

## 使用规则

1. 替换 `{...}` 占位符为实际值后执行
2. **不要移除 LIMIT 和 deleted=0**（安全保护）
3. ⚠️ 标记的模板涉及大表，务必保留时间范围条件
4. 拼接前先读 `table-schema.md` 确认字段名

---

## 单表快速查询（Q1–Q11）

### Q1: 最新水位（安全）

适用：查当前水情

```sql
SELECT rz, inq, otq, w, tm
FROM st_rsvr_r
WHERE deleted = 0 AND rz IS NOT NULL
ORDER BY tm DESC
LIMIT 1
```

### Q2: 指定时间范围水位 ⚠️

适用：查特定时间段的水位记录

```sql
SELECT tm, rz, inq, otq
FROM st_rsvr_r
WHERE deleted = 0
  AND tm BETWEEN '{start_time}' AND '{end_time}'
ORDER BY tm
LIMIT {limit|500}
```

### Q3: 最近N小时降雨 ⚠️

适用：查近期降雨情况

```sql
SELECT tm, p, dr, accumulate
FROM st_pptn_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL {hours|24} HOUR)
ORDER BY tm DESC
LIMIT {limit|500}
```

### Q4: 指定时间范围降雨统计 ⚠️

适用：按日汇总降雨量

```sql
SELECT DATE(tm) AS date,
       SUM(p) AS total_rainfall,
       MAX(p) AS peak_rainfall,
       COUNT(*) AS records
FROM st_pptn_r
WHERE deleted = 0
  AND tm BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59'
GROUP BY DATE(tm)
ORDER BY date
LIMIT {limit|100}
```

### Q5: 降雨预报

适用：未来降雨预报查询

```sql
SELECT ymdh, rn, pop, text, temp, wind_dir, wind_speed
FROM f_rnfl_h
WHERE deleted = 0
  AND ymdh >= '{start_time|NOW()}'
  AND ymdh <= DATE_ADD('{start_time|NOW()}', INTERVAL {hours|48} HOUR)
  AND fymdh = (
    SELECT MAX(fymdh)
    FROM f_rnfl_h
    WHERE ymdh >= '{start_time|NOW()}'
  )
ORDER BY ymdh
LIMIT {limit|100}
```

### Q6: 气象预警

适用：查询当前生效或已解除的气象预警

```sql
SELECT docid, docabstract, docpubtime, docpuburl, warn_status
FROM weather_warn
WHERE warn_status = '{status|1}'
{ AND docpubtime >= '{since_date}' }
ORDER BY docpubtime DESC
LIMIT {limit|10}
```

### Q7: 汛限水位

适用：查当前汛期对应的汛限水位

```sql
SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
FROM att_res_flse_lim
WHERE flood_season_start <= DATE_FORMAT('{date|NOW()}', '%m%d')
  AND flood_season_end >= DATE_FORMAT('{date|NOW()}', '%m%d')
LIMIT 1
```

> **注意**：如果查询结果为空，回退使用 `att_res_base.fl_low_lim_lev` 字段。

### Q8: 系统配置

适用：查询模型约束配置参数

```sql
SELECT config_key, value, tenant_id
FROM model_config
WHERE config_key IN ({keys|'max_water_level','min_water_level','max_drainage_capacity','safe_drainage_capacity'})
  AND deleted = 0
{ AND tenant_id = {tenant_id|18} }
ORDER BY tenant_id DESC, id DESC
```

### Q9: 历史预案列表

适用：查询已生成的调度预案，支持多条件筛选

```sql
SELECT id, scheme_id, alias, target_water_level, adjusted_water_level,
       start_time, end_time, create_time, extend
FROM model_result_files
WHERE type = 2
{ AND create_time BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59' }
{ AND CAST(adjusted_water_level AS DECIMAL(10,2)) BETWEEN {min_level} AND {max_level} }
{ AND alias LIKE '%{keyword}%' }
ORDER BY create_time DESC
LIMIT {limit|20}
```

### Q10: 历史洪水列表

适用：查询历史洪水事件记录

```sql
SELECT id, name, start_time, end_time, adjusted_water_level,
       target_water_level, status, rainfall_data, remake
FROM srm_flood_history_base
WHERE deleted = 0
{ AND status = {status|2} }
{ AND start_time BETWEEN '{start_date}' AND '{end_date}' }
{ AND name LIKE '%{keyword}%' }
ORDER BY create_time DESC
LIMIT {limit|20}
```

### Q11: 调度场景模板

适用：查询可用的调度场景配置

```sql
SELECT id, name, scheduling_target, scheduling_model, extend, def_flg
FROM srm_scheduling_scenario
WHERE deleted = 0
{ AND scheduling_target = '{target}' }
{ AND def_flg = 1 }
ORDER BY def_flg DESC, create_time DESC
```

---

## 关联查询（J1–J4）

### J1: 预案详情 + 调度时序

适用：查预案基本信息及其对应的逐时段调度操作

```sql
SELECT m.id, m.alias, m.target_water_level, m.adjusted_water_level,
       m.start_time, m.end_time, m.extend,
       d.tm, d.dispatch_opening, d.gate_opening_flow
FROM model_result_files m
LEFT JOIN dispatch_history d ON m.taskid = d.task_id
WHERE m.id = {plan_id}
  AND m.type = 2
ORDER BY d.tm
```

### J2: 预案时段实测水位

适用：查某预案执行期间的实测水位数据，用于对比分析

```sql
SELECT r.tm, r.rz, r.inq, r.otq
FROM st_rsvr_r r
WHERE r.deleted = 0
  AND r.rz IS NOT NULL
  AND r.tm BETWEEN (
    SELECT start_time FROM model_result_files WHERE id = {plan_id}
  ) AND (
    SELECT end_time FROM model_result_files WHERE id = {plan_id}
  )
ORDER BY r.tm
LIMIT 1000
```

### J3: 预案执行效果对比

适用：对比预案目标水位与实际水位的差异

```sql
SELECT m.id, m.alias,
       m.target_water_level AS planned_target,
       m.adjusted_water_level AS initial_level,
       MAX(r.rz) AS actual_max_level,
       AVG(r.rz) AS actual_avg_level
FROM model_result_files m
LEFT JOIN st_rsvr_r r
  ON r.tm BETWEEN m.start_time AND m.end_time
  AND r.deleted = 0
WHERE m.type = 2
{ AND m.start_time BETWEEN '{start_date}' AND '{end_date}' }
GROUP BY m.id, m.alias, m.target_water_level, m.adjusted_water_level
ORDER BY m.create_time DESC
LIMIT {limit|10}
```

### J4: 洪水结果曲线

适用：查询某次洪水事件的各类结果曲线数据（水位、流量、降雨等）

```sql
SELECT type, type_name, tm, vals
FROM srm_flood_history_result
WHERE flood_id = {flood_id}
ORDER BY type, tm
LIMIT 2000
```

---

## 聚合统计（A1–A4）

### A1: 水位变化趋势

适用：按小时聚合水位变化趋势

```sql
SELECT DATE_FORMAT(tm, '%Y-%m-%d %H:00:00') AS hour,
       AVG(rz) AS avg_level,
       MAX(rz) AS max_level,
       MIN(rz) AS min_level,
       COUNT(*) AS data_points
FROM st_rsvr_r
WHERE deleted = 0
  AND rz IS NOT NULL
  AND tm BETWEEN '{start_time}' AND '{end_time}'
GROUP BY hour
ORDER BY hour
LIMIT {limit|500}
```

### A2: 预案生成统计

适用：按日统计预案生成数量和平均水位

```sql
SELECT DATE(create_time) AS date,
       COUNT(*) AS plan_count,
       AVG(CAST(target_water_level AS DECIMAL(10,2))) AS avg_target,
       AVG(CAST(adjusted_water_level AS DECIMAL(10,2))) AS avg_initial
FROM model_result_files
WHERE type = 2
{ AND create_time BETWEEN '{start_date}' AND '{end_date}' }
GROUP BY DATE(create_time)
ORDER BY date
LIMIT {limit|100}
```

### A3: 相似预案匹配（按水位接近度）

适用：根据水位查找历史上相似场景的预案

```sql
SELECT id, alias, target_water_level, adjusted_water_level,
       start_time, end_time, extend,
       ABS(CAST(adjusted_water_level AS DECIMAL(10,2)) - {water_level}) AS diff
FROM model_result_files
WHERE type = 2
  AND adjusted_water_level IS NOT NULL
{ AND CAST(adjusted_water_level AS DECIMAL(10,2)) BETWEEN {min_level} AND {max_level} }
ORDER BY diff
LIMIT {limit|5}
```

### A4: 降雨总量预报

适用：汇总指定时段的预报降雨量

```sql
SELECT SUM(rn) AS total_rainfall,
       COUNT(*) AS hours,
       MAX(rn) AS peak_hourly,
       AVG(rn) AS avg_hourly
FROM f_rnfl_h
WHERE deleted = 0
  AND ymdh >= '{start_time}'
  AND ymdh <= '{end_time}'
  AND fymdh = (
    SELECT MAX(fymdh)
    FROM f_rnfl_h
    WHERE ymdh >= '{start_time}'
  )
```
