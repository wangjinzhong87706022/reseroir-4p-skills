# SQL 安全规则

> **适用范围**：SmartTwinRes 全部 skill 的 SQL 查询。
> **目的**：杜绝 SQL 注入、全表扫描、超长超时查询。

## 一、只读原则

- 所有 skill 脚本**只允许 SELECT / SHOW / DESCRIBE**。
- `lib/db.py` 的 `execute_query` 默认只读；写操作（INSERT/UPDATE/DELETE）必须用 `execute_write` 并显式 commit。
- **禁止**在 skill 脚本里执行 DDL（CREATE/ALTER/DROP）。

## 二、必有三要素

每条 SELECT 必须包含：

| 要素 | 原因 | 示例 |
|------|------|------|
| `WHERE` | 防全表扫描 | `WHERE tm >= %s` |
| `LIMIT` | 防返回爆炸 | `LIMIT 1000`（`MAX_ROWS` 上限） |
| 参数化 `%s` | 防 SQL 注入 | `WHERE stcd = %s` |

**禁止**字符串拼接 SQL（`f"WHERE stcd = '{stcd}'"`）—— 一律用 `params=(stcd,)`。

## 三、租户过滤（铁律）

所有查询水库数据的 SQL，**必须**按 `tenant_id` 过滤：

```python
from lib.tenant import current_tenant_id
tid = current_tenant_id()
sql = "SELECT * FROM st_stbprp_b WHERE tenant_id = %s AND tm >= %s LIMIT 1000"
rows = execute_query_list(sql, (tid, start_time))
```

**历史教训**：曾因漏过滤 tenant_id，导致三岔（18）查到桃曲坡（20）的水位数据，汛限水位判断错误。

详见 `shared/tenant-filtering-rules.md`。

## 四、JOIN 约束

- 每个 `JOIN` 必须有 `ON` 条件，**禁止**笛卡尔积（`FROM a, b WHERE a.id = b.id`）。
- 子查询层数 ≤ 3。

## 五、分区表（如有）

若表按时间 RANGE 分区，`WHERE` 必须包含时间范围，否则扫描全分区超时（30s 读超时）。

## 六、超时与重试

- `lib/db.py` 的 `connect_timeout=10s`、`read_timeout=30s`。
- 查询超时后**不重试**，直接报错让上层处理（避免雪崩）。

## 七、返回值契约

| 函数 | 返回 |
|------|------|
| `execute_query(sql, params)` | `{'data': list[dict], 'count': int, 'truncated': bool}` |
| `execute_query_list(sql, params)` | `list[dict]`（bare list，向后兼容） |
| `unpack(result)` | `list[dict]`（从 dict result 提取 data） |
| `query_one(sql, params)` | 单值或 None |
| `execute_write(sql, params)` | `int`（affected rows） |
