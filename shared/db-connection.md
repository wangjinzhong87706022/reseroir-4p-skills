# DB 连接标准

> **适用范围**：SmartTwinRes 全部 skill 的数据库连接。
> **唯一入口**：`lib/db.py`（`from db import execute_query, execute_query_list, unpack`）。

## 一、环境变量命名空间（优先级）

```
SRM_DB_*  →  POWERELF_DB_*  →  默认值
（优先）       （兼容）         （兜底）
```

| 配置项 | 变量名 | 默认值 | 必填 |
|-------|--------|--------|------|
| 主机 | `SRM_DB_HOST` / `POWERELF_DB_HOST` | `127.0.0.1` | 否 |
| 端口 | `SRM_DB_PORT` / `POWERELF_DB_PORT` | `3306` | 否 |
| 数据库 | `SRM_DB_NAME` / `POWERELF_DB_NAME` | `powerelf_srm_yml` | 否 |
| 用户 | `SRM_DB_USER` / `POWERELF_DB_USER` | （无） | **是** |
| 密码 | `SRM_DB_PASSWORD` / `POWERELF_DB_PASSWORD` | （无） | **是** |
| 行数上限 | `SRM_DB_MAX_ROWS` | `1000` | 否 |

**注意**：默认库名是 `powerelf_srm_yml`，不是你以为的其他名字。

## 二、凭据保护（铁律）

- **禁止硬编码口令**。`lib/db.py` 的 `_require_env` 强制从环境变量读取，缺失即 `sys.exit`。
- 新脚本直接 `from db import execute_query`，不要自己实现连接逻辑。
- 如果部署环境会清洗 `*PASSWORD*` 类变量（如 DeerFlow sandbox），需补文件回退（从 gitignored `.env` 读）。SmartTwinRes 当前部署不涉及 sandbox 清洗，暂不需要。

## 三、标准导入片段

### 3.1 LLM 运行时（Hermes 暂存脚本，`__file__` 不可靠）

```python
# 标准导入片段（照抄，禁手写 pymysql.connect / 硬编码密码）
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

**为什么用 `SRM_SKILLS_ROOT` env**：Hermes 暂存脚本里 `__file__` 不可靠，必须用 env 变量定位共享层。

### 3.2 离线脚本（`scripts/` 下，`__file__` 可靠）

```python
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

## 四、连接池

`lib/db.py` 自动尝试 `dbutils.pooled_db.PooledDB`（maxconnections=10）；若 `dbutils` 未安装，回退到单连接模式。skill 脚本无需关心。

## 五、超时配置

| 超时 | 值 | 配置位置 |
|------|---|---------|
| 连接超时 | 10s | `DB_CONFIG['connect_timeout']` |
| 读取超时 | 30s | `DB_CONFIG['read_timeout']` |

查询超时后**不重试**，直接报错让上层处理。

## 六、序列化

`lib/db.py` 自动把 `datetime` → `%Y-%m-%d %H:%M:%S`、`Decimal` → `float`、`timedelta` → 秒数。skill 脚本无需手动转换。

## 七、参考

- 标准文档：`docs/db-credential-config.md`
- 设计文档：`docs/统一共享层设计-20260807.md`
- 共享 SQL 规则：`shared/sql-safety-rules.md`
- 共享租户规则：`shared/tenant-filtering-rules.md`
