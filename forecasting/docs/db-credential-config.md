# 数据库连接配置标准

## 命名空间说明

本仓库包含两类 Skill，连接不同数据库时使用不同环境变量前缀：

| Skill 家族 | 环境变量前缀 | 默认数据库 | 说明 |
|-----------|------------|-----------|------|
| **SmartTwinRes** (forecasting / plan-generation / simulation / early-warning) | `SRM_DB_*` | `powerelf_srm_yml` | 水库业务主库 |
| **powerelf** (powerelf-early-warning / powerelf-data-governance / powerelf-monitor) | `POWERELF_DB_*` | `powerelf_srm_yml` (默认) / `powerelf_data` (实际) | 本地监测/预警库 |

> ⚠️ 两套环境变量对应**不同数据库实例**，即使默认库名相同，实际连接也可能指向不同库。配置时请确认对应正确的 Skill 家族。

---

## 一、SmartTwinRes 家族配置（`SRM_DB_*`）

### 环境变量

```bash
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD='your_password'
```

### 实现方式

#### 方式 A：SmartTwinRes 专用 `query_utils.py`

适用于 forecasting / plan-generation / simulation / early-warning 等使用 `query_utils.py` 的 Skill：

```python
# scripts/query_utils.py
import os

def _require_env(name):
    """敏感凭据强制从环境变量读取，无值则报错退出（杜绝硬编码口令）。"""
    val = os.getenv(name)
    if not val:
        sys.exit(f"[DB] 环境变量 {name} 未设置。请配置 SRM_DB_* 环境变量后重试")
    return val

DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': _require_env('SRM_DB_USER'),
    'password': _require_env('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
}
```

#### 方式 B：powerelf 兼容 `lib/db.py`

适用于希望兼容 powerelf 生态的 Skill，支持 `POWERELF_DB_*` + `SRM_DB_*` 双前缀回退：

```python
# lib/db.py
import os

DB_HOST = os.getenv("POWERELF_DB_HOST") or os.getenv("SRM_DB_HOST", "localhost")
DB_PORT = int(os.getenv("POWERELF_DB_PORT") or os.getenv("SRM_DB_PORT", "3306"))
DB_NAME = os.getenv("POWERELF_DB_NAME") or os.getenv("SRM_DB_NAME", "powerelf_srm_yml")
DB_USER = os.getenv("POWERELF_DB_USER") or os.getenv("SRM_DB_USER", "root")
DB_PASSWORD = os.getenv("POWERELF_DB_PASSWORD") or os.getenv("SRM_DB_PASSWORD", "")
```

**优先级**：`POWERELF_DB_*` > `SRM_DB_*` > 默认值

---

## 二、powerelf 家族配置（`POWERELF_DB_*`）

### 环境变量

```bash
export POWERELF_DB_HOST=127.0.0.1
export POWERELF_DB_PORT=3306
export POWERELF_DB_NAME=powerelf_data   # 或 powerelf_srm_yml
export POWERELF_DB_USER=root
export POWERELF_DB_PASSWORD='your_password'
```

> ⚠️ powerelf 家族的默认数据库通常是 `powerelf_data`（本地监测库），与 SmartTwinRes 的 `powerelf_srm_yml`（业务主库）不同。

---

## 三、标准化约定（SmartTwinRes Skill 开发规范）

### 1. 环境变量命名

- **SmartTwinRes Skill** 统一使用 `SRM_DB_*` 前缀
- **powerelf Skill** 统一使用 `POWERELF_DB_*` 前缀
- 禁止在 Skill 代码中硬编码任何凭据值

### 2. 配置读取方式

#### 脚本（forecasting / plan-generation / simulation）

```python
# 推荐：直接使用 scripts/query_utils.py
from query_utils import execute_query, execute_query_list, unpack

result = execute_query("SELECT * FROM st_rsvr_r WHERE deleted=0 LIMIT 100")
```

#### 交互式分析（early-warning）

```python
# 推荐：使用 lib/db.py
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from db import query, query_multi, close_all

rows = query("SELECT * FROM ew_info_message WHERE deleted=0")
close_all()
```

### 3. 错误提示

无凭据时统一提示格式：

```text
[DB] 环境变量 SRM_DB_PASSWORD 未设置。请配置 SRM_DB_* 环境变量后重试（见 db-config.md）。
```

### 4. 连接池配置

```python
# 连接池参数（SmartTwinRes 标准）
{
    'maxconnections': 5,
    'connect_timeout': 10,   # 连接超时（秒）
    'read_timeout': 30,      # 读取超时（秒）
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}
```

---

## 四、快速配置（用户视角）

### 一次性设置（推荐）

```bash
# 编辑 ~/.bashrc 或 ~/.zshrc
echo 'export SRM_DB_HOST=127.0.0.1' >> ~/.bashrc
echo 'export SRM_DB_PORT=3306' >> ~/.bashrc
echo 'export SRM_DB_NAME=powerelf_srm_yml' >> ~/.bashrc
echo 'export SRM_DB_USER=root' >> ~/.bashrc
echo 'export SRM_DB_PASSWORD="your_password"' >> ~/.bashrc
source ~/.bashrc
```

### 按会话临时设置

```bash
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD="your_password"
```

### systemd 服务配置（长期运行）

```ini
[Service]
Environment="SRM_DB_HOST=127.0.0.1"
Environment="SRM_DB_PORT=3306"
Environment="SRM_DB_NAME=powerelf_srm_yml"
Environment="SRM_DB_USER=root"
Environment="SRM_DB_PASSWORD=your_password"
```

---

## 五、Hermes Agent 集成

Hermes Agent 在执行 Skill 时，会自动继承当前 shell 的环境变量。因此：

1. **在启动 Hermes 前**设置好 `SRM_DB_*` / `POWERELF_DB_*` 环境变量
2. **Hermes 子进程**（如 `execute_code`、`hermes -z`）自动继承这些变量
3. **无需在对话中澄清**或让用户输入——配置一次，全局生效

### 验证配置

```bash
# 检查环境变量是否生效
env | grep -E "SRM_DB_|POWERELF_DB_"

# 测试连接
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME" -e "SELECT 1"
```

---

## 六、常见问题

### Q1: 提示 `环境变量 SRM_DB_PASSWORD 未设置`

**原因**：环境变量未 export 或 Hermes 未继承

**解决**：
```bash
# 1. 确认变量已设置
echo $SRM_DB_PASSWORD

# 2. 如果为空，重新 export
export SRM_DB_PASSWORD="your_password"

# 3. 重启 Hermes（如果是 systemd 服务）
systemctl --user restart hermes-gateway
```

### Q2: 两个 Skill 家族环境变量冲突

**原因**：`POWERELF_DB_*` 和 `SRM_DB_*` 指向不同数据库

**解决**：为不同 Skill 家族分别设置，或使用统一的 `SRM_DB_*` 并确保数据库一致

```bash
# 方案 A：统一使用 SRM_DB_*（推荐，如果两个家族连同一个库）
export SRM_DB_HOST=127.0.0.1
export SRM_DB_NAME=powerelf_srm_yml
# POWERELF_DB_* 会自动 fallback 到 SRM_DB_*

# 方案 B：分别设置（如果连接不同库）
export SRM_DB_NAME=powerelf_srm_yml      # SmartTwinRes
export POWERELF_DB_NAME=powerelf_data    # powerelf
```

### Q3: 如何在不修改代码的情况下切换数据库

**方法**：修改环境变量即可，无需改动任何 Skill 代码

```bash
# 切换到测试库
export SRM_DB_NAME=powerelf_srm_yml_test
export SRM_DB_HOST=192.168.100.103
```

---

## 七、数据库选择决策树

```
是否需要连接数据库？
│
├─ 是 SmartTwinRes Skill (forecasting / plan-generation / simulation / early-warning)
│   └─ 使用 SRM_DB_* 环境变量（脚本内已集成 query_utils.py）
│
├─ 是 powerelf Skill (powerelf-early-warning / powerelf-data-governance / powerelf-monitor)
│   └─ 使用 POWERELF_DB_* 环境变量（lib/db.py 自动 fallback 到 SRM_DB_*）
│
└─ 新建 Skill？
    ├─ 属于 SmartTwinRes 家族 → 使用 SRM_DB_*，参考 forecasting/scripts/query_utils.py
    └─ 属于 powerelf 家族 → 使用 POWERELF_DB_*，参考 powerelf-data-governance/lib/db.py
```

---

*最后更新：2026-07-09*
*维护者：SmartTwinRes Team / Powerelf Team*
