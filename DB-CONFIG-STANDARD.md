# SmartTwinRes Skills 数据库环境变量配置标准

**版本**: 1.0
**生效日期**: 2026-07-09
**适用范围**: SmartTwinRes 家族所有 Skill（forecasting / plan-generation / simulation / early-warning / diagnosis-verification / supervisor）

> **唯一真相源**：本文档与 `shared/db-connection.md` 内容重叠，以 `shared/db-connection.md` 为准（P2-9）。本文件保留作为根目录入口。

---

## 一、命名空间标准

### 1.1 优先级规则

所有 SmartTwinRes Skill 统一采用以下优先级读取数据库配置：

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

### 1.2 实现代码

```python
import os
import sys

def _require_env(name):
    """敏感凭据强制从环境变量读取，无值则报错退出。"""
    val = os.getenv(name)
    if not val:
        sys.exit(f"[DB] 环境变量 {name} 未设置。请配置 SRM_DB_* 环境变量后重试")
    return val

DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST') or os.getenv('POWERELF_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT') or os.getenv('POWERELF_DB_PORT', '3306')),
    'user': os.getenv('SRM_DB_USER') or os.getenv('POWERELF_DB_USER') or _require_env('SRM_DB_USER'),
    'password': os.getenv('SRM_DB_PASSWORD') or os.getenv('POWERELF_DB_PASSWORD') or _require_env('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME') or os.getenv('POWERELF_DB_NAME', 'powerelf_srm_yml'),
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 30,
}
```

---

## 二、已适配 Skill 清单

| Skill | 文件路径 | 适配日期 | 状态 |
|-------|---------|---------|------|
| **forecasting** | `scripts/query_forecast_data.py` | 2026-07-09 | ✅ 已适配 |
| **plan-generation** | `scripts/query_plan_data.py` | 2026-07-09 | ✅ 已适配 |
| **simulation** | `scripts/query_simulation_data.py` | 2026-07-09 | ✅ 已适配 |
| **early-warning** | `scripts/query_early_warning.py` | 2026-07-09 | ✅ 已适配（修复硬编码密码） |
| **diagnosis-verification** | `scripts/check_data_quality.py` | 2026-08-10 | ✅ 已适配（补 tenant 过滤） |
| **supervisor** | `scripts/inspection_check.py` | 2026-08-10 | ✅ 已适配（补 tenant 过滤） |

---

## 三、用户配置指南

### 3.1 一次性配置（推荐）

```bash
# 编辑 shell 配置文件
cat >> ~/.bashrc << 'EOF'
# SmartTwinRes Skills 数据库配置
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD='your_password'
EOF

source ~/.bashrc
```

### 3.2 systemd 服务配置

```ini
[Service]
Environment="SRM_DB_HOST=127.0.0.1"
Environment="SRM_DB_PORT=3306"
Environment="SRM_DB_NAME=powerelf_srm_yml"
Environment="SRM_DB_USER=root"
Environment="SRM_DB_PASSWORD=your_password"
```

### 3.3 验证配置

```bash
# 检查环境变量
env | grep -E "SRM_DB_|POWERELF_DB_"

# 测试连接
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME" -e "SELECT 1"
```

---

## 四、与其他 Skill 家族的兼容性

### 4.1 powerelf 家族

powerelf 家族 Skill（powerelf-early-warning / powerelf-data-governance / powerelf-monitor）使用 `POWERELF_DB_*` 作为主命名空间，`SRM_DB_*` 作为 fallback。

**关键区别**：
- powerelf 家族默认连接 `powerelf_data`（本地监测库）
- SmartTwinRes 家族默认连接 `powerelf_srm_yml`（业务主库）

### 4.2 同时使用两个家族

```bash
# SmartTwinRes Skill 使用
export SRM_DB_NAME=powerelf_srm_yml

# powerelf Skill 使用（覆盖默认）
export POWERELF_DB_NAME=powerelf_data
```

---

## 五、标准化检查清单

新建或修改 SmartTwinRes Skill 时，必须遵守：

- [ ] 使用 `SRM_DB_*` 作为主命名空间
- [ ] 支持 `POWERELF_DB_*` fallback（兼容 powerelf 生态）
- [ ] 凭据从环境变量读取，**禁止硬编码**
- [ ] 无凭据时调用 `_require_env()` 报错退出
- [ ] 连接超时：10s，读取超时：30s
- [ ] charset 使用 `utf8mb4`
- [ ] 错误提示引用 `docs/db-credential-config.md`

---

## 六、历史问题

### 6.1 early-warning 硬编码密码（已修复）

**问题**：`query_early_warning.py` 曾硬编码密码 `'123456aA.'`
**修复**：2026-07-09 改为环境变量读取
**影响**：所有 early-warning 脚本调用已适配新标准

---

## 七、参考文档

- **标准文档**：[forecasting/docs/db-credential-config.md](../forecasting/docs/db-credential-config.md)
- **powerelf 模式**：[powerelf-data-governance/lib/db.py](https://github.com/your-org/hermes-agent/blob/master/skills/powerelf/lib/db.py)

---

*维护：SmartTwinRes Team*
*最后更新：2026-07-09*
