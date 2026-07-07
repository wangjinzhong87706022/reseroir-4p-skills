# 性能优化配置

## 默认查询参数

### 查询范围限制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **时间范围** | 最近 7 天 | 避免全表扫描 |
| **分页大小** | 50 条 | 平衡性能和数据量 |
| **最大分页** | 200 条 | 防止内存溢出 |
| **排序方式** | 时间倒序 | 最新的在前面 |

### 动态参数调整

当用户指定时间范围或数量时，使用用户参数：

```
用户: "查看最近3天的告警"
→ 使用 INTERVAL 3 DAY

用户: "查看最近100条告警"
→ 使用 LIMIT 100

用户: "查看2026年5月的告警"
→ 使用 create_time >= '2026-05-01' AND create_time < '2026-06-01'
```

## 查询模板（带默认参数）

### 查询活跃告警

```sql
-- 默认最近7天，最多50条
SELECT id, ew_name, st_code, eq_code, ew_type, level_r, content, 
       value, gather_time, message_confirm, create_time
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY 
  CASE level_r WHEN '1' THEN 1 WHEN '2' THEN 2 WHEN '3' THEN 3 WHEN '4' THEN 4 END,
  create_time DESC
LIMIT 50;
```

### 查询高级别告警

```sql
-- 默认最近30天
SELECT id, ew_name, st_code, eq_code, ew_type, level_r, content, 
       value, gather_time, message_confirm, create_time
FROM ew_info_message 
WHERE deleted = 0
  AND level_r IN ('1', '2')
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY create_time DESC
LIMIT 50;
```

### 查询告警统计

```sql
-- 默认最近30天
SELECT level_r, COUNT(*) as count
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY level_r
ORDER BY level_r;
```

### 查询特定测站告警

```sql
-- 默认最近30天
SELECT id, ew_name, level_r, value, gather_time, message_confirm
FROM ew_info_message 
WHERE st_code = '606K2155' AND deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY gather_time DESC
LIMIT 50;
```

### 查询告警趋势

```sql
-- 默认最近30天
SELECT DATE(create_time) as date, level_r, COUNT(*) as count
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(create_time), level_r
ORDER BY date, level_r;
```

### 查询关联告警

```sql
-- 默认最近30天
SELECT id, ew_name, st_code, ew_type, level_r, value, gather_time
FROM ew_info_message
WHERE deleted = 0
  AND st_code = #{stCode}
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY gather_time DESC
LIMIT 50;
```

### 查询设备当前值

```sql
-- 水位
SELECT rz as current_value, tm as current_time
FROM st_rsvr_r WHERE eq_code = #{eqCode} ORDER BY tm DESC LIMIT 1;

-- 降雨
SELECT p as current_value, tm as current_time
FROM st_pptn_r WHERE eq_code = #{eqCode} ORDER BY tm DESC LIMIT 1;

-- 渗压
SELECT water_pressure as current_value, tm as current_time
FROM st_pressure_r WHERE eq_code = #{eqCode} ORDER BY tm DESC LIMIT 1;

-- 渗流
SELECT percolation as current_value, tm as current_time
FROM st_percolation_r WHERE eq_code = #{eqCode} ORDER BY tm DESC LIMIT 1;
```

### 查询告警规则

```sql
SELECT id, name, ew_type, level_r, st_code, extend
FROM ew_info_rules
WHERE deleted = 0
ORDER BY ew_type, level_r;
```

## 性能基准

| 查询类型 | 预期时间 | 数据量 |
|----------|----------|--------|
| 查询活跃告警 | < 0.1s | 50条 |
| 查询高级别告警 | < 0.1s | 50条 |
| 查询告警统计 | < 0.05s | 4条 |
| 查询告警趋势 | < 0.1s | 30天 |
| 查询设备当前值 | < 0.05s | 1条 |

## 索引建议

```sql
-- 添加联合索引
CREATE INDEX idx_deleted_create_time ON ew_info_message(deleted, create_time);
CREATE INDEX idx_level_deleted ON ew_info_message(level_r, deleted);
CREATE INDEX idx_st_code_deleted ON ew_info_message(st_code, deleted);
CREATE INDEX ew_rules_id ON ew_info_message(ew_rules_id);
```

## 性能优化措施

1. **时间范围限制**：默认查询最近7天或30天数据
2. **分页限制**：默认最多返回50条记录
3. **本地数据库**：使用 127.0.0.1 避免网络延迟
4. **索引优化**：确保关键字段有索引

## 查询优化建议

### 避免全表扫描

```sql
-- ❌ 错误：全表扫描
SELECT * FROM ew_info_message WHERE deleted = 0;

-- ✅ 正确：带时间范围
SELECT * FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### 避免大分页

```sql
-- ❌ 错误：大分页
SELECT * FROM ew_info_message 
WHERE deleted = 0
LIMIT 10000;

-- ✅ 正确：合理分页
SELECT * FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
LIMIT 50;
```

### 使用索引字段

```sql
-- ❌ 错误：使用非索引字段
SELECT * FROM ew_info_message 
WHERE ew_name LIKE '%水位%';

-- ✅ 正确：使用索引字段
SELECT * FROM ew_info_message 
WHERE st_code = '606K2155' AND deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY);
```
