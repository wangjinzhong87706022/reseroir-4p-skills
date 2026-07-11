> ⚠️ **已废弃**：本文件已被 `sql-templates.md` 替代。
> 新项目请使用 `${HERMES_SKILL_DIR}/references/sql-templates.md` 中的参数化模板。
> 本文件仅保留作为历史参考。

# SQL 查询参考

## 一、数据收集查询

### 1.1 当前水位

```sql
-- 最新水位
SELECT rz AS water_level, inq AS inflow, otq AS outflow, w AS storage, tm
FROM st_rsvr_r
WHERE deleted = 0
ORDER BY tm DESC
LIMIT 1;

-- 过去6小时水位变化（趋势分析用）
SELECT rz, inq, otq, tm
FROM st_rsvr_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
ORDER BY tm DESC;
```

### 1.2 降雨预报

```sql
-- 未来48h逐时降雨
SELECT ymdh AS forecast_time, rn AS rainfall_mm, pop AS probability,
       text AS weather_desc, temp AS temperature
FROM f_rnfl_h
WHERE deleted = 0
  AND ymdh >= NOW()
  AND ymdh <= DATE_ADD(NOW(), INTERVAL 48 HOUR)
ORDER BY ymdh;

-- 降雨总量统计
SELECT SUM(rn) AS total_rainfall, COUNT(*) AS hours
FROM f_rnfl_h
WHERE deleted = 0
  AND ymdh >= NOW()
  AND ymdh <= DATE_ADD(NOW(), INTERVAL 48 HOUR);

-- 按天汇总降雨
SELECT DATE(ymdh) AS date, SUM(rn) AS daily_rainfall
FROM f_rnfl_h
WHERE deleted = 0
  AND ymdh >= NOW()
  AND ymdh <= DATE_ADD(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(ymdh)
ORDER BY date;
```

### 1.3 气象预警

```sql
-- 活跃预警
SELECT docid, docabstract, docpubtime, docpuburl
FROM weather_warn
WHERE warn_status = '1'
ORDER BY docpubtime DESC;

-- 最近解除的预警
SELECT docid, docabstract, docpubtime, warn_status
FROM weather_warn
WHERE warn_status = '2'
ORDER BY docpubtime DESC
LIMIT 5;
```

### 1.4 汛限水位

```sql
-- 当前汛限水位
SELECT flse_lim_stag AS flood_limit_level,
       flood_season_name,
       flood_season_start,
       flood_season_end
FROM att_res_flse_lim
WHERE deleted = 0
  AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
  AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')
LIMIT 1;

-- 所有汛期配置
SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
FROM att_res_flse_lim
WHERE deleted = 0
ORDER BY flood_season_start;
```

### 1.5 系统配置

```sql
-- 水位约束配置
SELECT key_name, value
FROM model_config
WHERE key_name IN (
    'max_water_level',           -- 最高允许水位
    'min_water_level',           -- 最低允许水位
    'max_drainage_capacity',     -- 防洪最大下泄能力
    'safe_drainage_capacity'     -- 下游安全泄量
)
AND deleted = 0;

-- 所有模型配置
SELECT key_name, value
FROM model_config
WHERE deleted = 0
ORDER BY key_name;
```

## 二、历史数据查询

### 2.1 历史预案

```sql
-- 历史预案列表
SELECT id, scheme_id, alias, target_water_level, adjusted_water_level,
       start_time, end_time, create_time, extend
FROM model_result_files
WHERE type = 2 AND deleted = 0
ORDER BY create_time DESC
LIMIT 10;

-- 按方案ID查询
SELECT id, scheme_id, alias, target_water_level, adjusted_water_level,
       start_time, end_time, create_time, extend
FROM model_result_files
WHERE scheme_id LIKE '%2025%' AND type = 2 AND deleted = 0
ORDER BY create_time DESC;

-- 预案调度历史（闸门开度和流量）
SELECT d.tm, d.dispatch_opening, d.gate_opening_flow
FROM dispatch_history d
JOIN model_result_files m ON d.task_id = m.taskid
WHERE m.scheme_id = '具体方案ID'
ORDER BY d.tm;
```

### 2.2 历史洪水

```sql
-- 历史洪水列表
SELECT id, name, start_time, end_time, adjusted_water_level,
       target_water_level, status, remake
FROM srm_flood_history_base
WHERE status = 2 AND deleted = 0
ORDER BY create_time DESC
LIMIT 10;

-- 历史洪水结果曲线
SELECT type, type_name, tm, vals
FROM srm_flood_history_result
WHERE flood_id = #{floodId}
ORDER BY type, tm;

-- 历史洪水统计指标
SELECT type_name, vals
FROM srm_flood_history_result
WHERE flood_id = #{floodId} AND type = 7;
```

### 2.3 调度场景模板

```sql
-- 默认场景
SELECT id, name, scheduling_target, scheduling_model, extend
FROM srm_scheduling_scenario
WHERE def_flg = 1 AND deleted = 0
LIMIT 1;

-- 所有场景
SELECT id, name, scheduling_target, scheduling_model, extend, def_flg
FROM srm_scheduling_scenario
WHERE deleted = 0
ORDER BY def_flg DESC, create_time DESC;
```

## 三、分析查询

### 3.1 降雨趋势分析

```sql
-- 最近24h逐时降雨
SELECT DATE_FORMAT(tm, '%Y-%m-%d %H:00:00') AS hour, SUM(p) AS hourly_rainfall
FROM st_pptn_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY hour
ORDER BY hour;

-- 最近7天日降雨
SELECT DATE(tm) AS date, SUM(p) AS daily_rainfall
FROM st_pptn_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY date
ORDER BY date;
```

### 3.2 水位趋势分析

```sql
-- 过去24h水位变化
SELECT DATE_FORMAT(tm, '%Y-%m-%d %H:00:00') AS hour,
       AVG(rz) AS avg_level, MAX(rz) AS max_level, MIN(rz) AS min_level
FROM st_rsvr_r
WHERE deleted = 0
  AND tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY hour
ORDER BY hour;

-- 水位涨幅计算
SELECT
    (SELECT rz FROM st_rsvr_r WHERE deleted = 0 ORDER BY tm DESC LIMIT 1) AS current_level,
    (SELECT rz FROM st_rsvr_r WHERE deleted = 0
     AND tm <= DATE_SUB(NOW(), INTERVAL 6 HOUR)
     ORDER BY tm DESC LIMIT 1) AS level_6h_ago,
    (SELECT rz FROM st_rsvr_r WHERE deleted = 0
     AND tm <= DATE_SUB(NOW(), INTERVAL 12 HOUR)
     ORDER BY tm DESC LIMIT 1) AS level_12h_ago;
```

### 3.3 预案效果分析

```sql
-- 预案执行效果（预报vs实际）
-- 需要关联 model_result_files 和 st_rsvr_r

-- 最高水位对比
SELECT
    m.alias,
    m.target_water_level AS planned_target,
    MAX(r.rz) AS actual_max_level
FROM model_result_files m
LEFT JOIN st_rsvr_r r ON r.tm BETWEEN m.start_time AND m.end_time
WHERE m.type = 2 AND m.deleted = 0 AND r.deleted = 0
GROUP BY m.id, m.alias, m.target_water_level
ORDER BY m.create_time DESC
LIMIT 10;
```

## 四、复合查询（完整上下文）

```sql
-- 完整上下文数据（用于 Agent 一次性获取所有信息）

-- 1. 当前水位
SELECT rz, inq, otq, w, tm FROM st_rsvr_r WHERE deleted = 0 ORDER BY tm DESC LIMIT 1;

-- 2. 未来48h降雨
SELECT ymdh, rn, pop, text FROM f_rnfl_h
WHERE deleted = 0 AND ymdh >= NOW() AND ymdh <= DATE_ADD(NOW(), INTERVAL 48 HOUR)
ORDER BY ymdh;

-- 3. 活跃预警
SELECT docid, docabstract, docpubtime FROM weather_warn WHERE warn_status = '1';

-- 4. 汛限水位
SELECT flse_lim_stag FROM att_res_flse_lim
WHERE deleted = 0
  AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
  AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')
LIMIT 1;

-- 5. 约束配置
SELECT key_name, value FROM model_config
WHERE key_name IN ('max_water_level','min_water_level','max_drainage_capacity','safe_drainage_capacity')
  AND deleted = 0;

-- 6. 历史预案（最近5条）
SELECT id, alias, target_water_level, adjusted_water_level, start_time, end_time
FROM model_result_files WHERE type = 2 AND deleted = 0 ORDER BY create_time DESC LIMIT 5;

-- 7. 历史洪水（最近5条）
SELECT id, name, start_time, end_time, adjusted_water_level, status
FROM srm_flood_history_base WHERE status = 2 AND deleted = 0 ORDER BY create_time DESC LIMIT 5;
```
