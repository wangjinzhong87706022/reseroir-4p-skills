# tenant_id / deleted 过滤规则使用示例

本文件展示如何在 SmartTwinRes Skills 中使用 `lib.filters` 模块自动应用表过滤规则。

---

## 📋 快速开始

### 1. 导入过滤模块

```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from lib.db import execute_query_list
from lib.filters import apply_table_filters, generate_where_clause
```

---

## 💻 使用示例

### 示例 1: 查询当前水位 (st_rsvr_r)

```python
def query_current_water_level():
    """查询当前水位 (自动应用 tenant_id=18 + deleted=0)"""
    sql = "SELECT rz, inq, otq, w, tm FROM st_rsvr_r ORDER BY tm DESC LIMIT 1"
    sql = apply_table_filters(sql, 'st_rsvr_r')
    # 结果: "SELECT rz, inq, otq, w, tm FROM st_rsvr_r WHERE tenant_id = 18 AND deleted = 0 ORDER BY tm DESC LIMIT 1"
    return execute_query_list(sql)
```

### 示例 2: 查询最近降雨 (st_pptn_r + 时间范围)

```python
def query_recent_rainfall(hours=24):
    """查询最近降雨"""
    base_sql = "SELECT p, dr, tm FROM st_pptn_r"
    where = generate_where_clause(
        'st_pptn_r',
        extra_conditions=[f'tm >= DATE_SUB(NOW(), INTERVAL {hours} HOUR)']
    )
    sql = f"{base_sql} {where} ORDER BY tm DESC LIMIT 1000"
    return execute_query_list(sql)
```

### 示例 3: 查询历史洪水 (srm_flood_history_base)

```python
def query_historical_floods(status=2, limit=10):
    """查询历史洪水 (已完成状态)"""
    sql = "SELECT id, name, start_time, end_time, adjusted_water_level, target_water_level FROM srm_flood_history_base"
    where = generate_where_clause(
        'srm_flood_history_base',
        extra_conditions=['status = %s']
    )
    sql = f"{sql} {where} ORDER BY start_time DESC LIMIT %s"
    return execute_query_list(sql, (status, limit))
```

### 示例 4: 查询告警堆积 (ew_info_message)

```python
def query_unconfirmed_alerts(days=7):
    """查询未确认告警 (告警跨租户,不强制 tenant_id 过滤)"""
    sql = "SELECT COUNT(*) as count FROM ew_info_message"
    where = generate_where_clause(
        'ew_info_message',
        extra_conditions=[
            'message_confirm = 0',
            f'create_time >= DATE_SUB(NOW(), INTERVAL {days} DAY)'
        ]
    )
    sql = f"{sql} {where}"
    return execute_query_list(sql)
```

### 示例 5: 查询模型结果 (model_result_files)

```python
def query_model_results(result_type=1, limit=10):
    """查询模型结果 (⚠️ model_result_files 无 deleted 列)"""
    sql = "SELECT taskid, type, target_water_level, adjusted_water_level, create_time FROM model_result_files"
    where = generate_where_clause(
        'model_result_files',
        extra_conditions=['type = %s']
    )
    sql = f"{sql} {where} ORDER BY create_time DESC LIMIT %s"
    return execute_query_list(sql, (result_type, limit))
```

### 示例 6: 查询降雨预报 (f_rnfl_h)

```python
def query_rainfall_forecast(hours=48):
    """查询降雨预报 (⚠️ f_rnfl_h 无 tenant_id 列)"""
    sql = "SELECT RN, YMDH, FYMDH, UNITNAME FROM f_rnfl_h"
    where = generate_where_clause(
        'f_rnfl_h',
        extra_conditions=[
            'YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR)',
            'deleted = 0'
        ]
    )
    sql = f"{sql} {where} ORDER BY YMDH ASC"
    return execute_query_list(sql, (hours,))
```

---

## 🔍 验证过滤规则

```python
from lib.filters import validate_table_filter

# 验证表过滤规则
need_tenant, need_deleted, msg = validate_table_filter('st_rsvr_r')
print(msg)  # "tenant_id=18, deleted=0"

need_tenant, need_deleted, msg = validate_table_filter('model_result_files')
print(msg)  # "tenant_id=18, ⚠️ 无 deleted 列"

need_tenant, need_deleted, msg = validate_table_filter('f_rnfl_h')
print(msg)  # "⚠️ 无 tenant_id 列,不过滤, deleted=0"
```

---

## ⚠️ 常见错误

### ❌ 错误 1: 对无 tenant_id 的表添加 tenant 过滤

```python
# ❌ 错误: f_rnfl_h 无 tenant_id 列
sql = "SELECT * FROM f_rnfl_h WHERE tenant_id = 18 AND deleted = 0"

# ✅ 正确: 使用过滤函数
sql = apply_table_filters("SELECT * FROM f_rnfl_h WHERE deleted = 0", 'f_rnfl_h')
```

### ❌ 错误 2: 对无 deleted 列的表添加 deleted 过滤

```python
# ❌ 错误: model_result_files 无 deleted 列
sql = "SELECT * FROM model_result_files WHERE type = 1 AND deleted = 0"

# ✅ 正确: 使用过滤函数
sql = apply_table_filters("SELECT * FROM model_result_files WHERE type = 1", 'model_result_files')
```

### ❌ 错误 3: 硬编码 tenant_id

```python
# ❌ 错误: 硬编码 tenant_id
sql = f"SELECT * FROM st_rsvr_r WHERE tenant_id = {some_variable} AND deleted = 0"

# ✅ 正确: 使用过滤函数,统一从配置读
sql = apply_table_filters("SELECT * FROM st_rsvr_r", 'st_rsvr_r')
```

---

## 📏 编码规范

### 1. 强制使用过滤函数

```python
# ❌ 错误: 手动拼接 WHERE 子句,容易遗漏
sql = f"SELECT * FROM st_rsvr_r WHERE deleted = 0 AND tm >= ..."

# ✅ 正确: 使用过滤函数,自动应用规则
sql = apply_table_filters("SELECT * FROM st_rsvr_r", 'st_rsvr_r')
```

### 2. 注释标注

```python
# ✅ 正确: 注释说明过滤规则
sql = "SELECT rz, inq, otq, w, tm FROM st_rsvr_r"
sql = apply_table_filters(sql, 'st_rsvr_r')  # tenant_id=18 + deleted=0
```

### 3. 避免硬编码表名

```python
# ❌ 错误: 硬编码表名
def get_water_level():
    return execute_query_list("SELECT rz FROM st_rsvr_r WHERE deleted = 0 LIMIT 1")

# ✅ 正确: 使用表名变量
def get_water_level():
    table = 'st_rsvr_r'
    sql = f"SELECT rz FROM {table} {generate_where_clause(table)} LIMIT 1"
    return execute_query_list(sql)
```

---

**维护**: SmartTwinRes Team
**最后更新**: 2026-07-11
