# 数据库凭据环境变量配置指南

> 适用：预案 (plan-generation) + 预演 (simulation) 两个 skill
> 背景：skill 的 DB 口令已从硬编码改为环境变量引用（治 auditor C2 过拟合 + 安全），本文说明如何配置这些环境变量，以及脚本内残留兜底值的处理。

> 🔴 **当前状态（2026-06-16 更新）：脚本兜底已全部清除，配置环境变量现在是硬性要求。**
>
> 以下文件已不再含任何口令兜底，**不配置环境变量，DB 查询会直接报错退出**：
> - `plan-generation/scripts/query_utils.py`（`SRM_DB_USER` / `SRM_DB_PASSWORD` 强制要求）
> - `simulation/scripts/query_simulation_data.py`（同上）
> - 两个 skill 的 `SKILL.md` 里 `mysql` 命令行（`-p"$SRM_DB_PASSWORD"`）
>
> **部署/运行前必须先完成第 3 节配置**，否则 hermes 执行到 DB 查询会报：
> `[DB] 环境变量 SRM_DB_PASSWORD 未设置。请配置 SRM_DB_* 环境变量后重试。`
>
> 快速配置（写进 `~/.bashrc` 或 hermes 启动脚本后 source / 重启）：
> ```bash
> export SRM_DB_HOST=127.0.0.1
> export SRM_DB_PORT=3306
> export SRM_DB_NAME=powerelf_srm_yml
> export SRM_DB_USER=root
> export SRM_DB_PASSWORD='真实密码'
> ```

---

## 1. 涉及的环境变量

两个 skill 的 frontmatter `prerequisites.env_vars` 声明了相同的 5 个变量：

| 变量 | 用途 | 默认值（兜底，见第 4 节） |
|------|------|--------------------------|
| `SRM_DB_HOST` | DB 主机 | `127.0.0.1` |
| `SRM_DB_PORT` | DB 端口 | `3306` |
| `SRM_DB_NAME` | 数据库名 | `powerelf_srm_yml` |
| `SRM_DB_USER` | DB 用户 | `root` |
| `SRM_DB_PASSWORD` | DB 口令 | （见下表，各脚本不同） |

---

## 2. 为什么需要配置

skill 的数据查询脚本用 `os.getenv('SRM_DB_PASSWORD', ...)` 读取口令。SKILL.md 里的 `mysql` 命令行也已改为 `-p"$SRM_DB_PASSWORD"` 引用环境变量。

**若不配置**：
- 预演脚本（`query_simulation_data.py`）兜底是**空字符串** → **连接失败**（`Access denied for user 'root'@'localhost' (using password: NO)`，已实测）
- 预案脚本（`query_utils.py`）兜底是硬编码 `123456aA.` → 能连，但口令仍在代码里（C2 过拟合/安全风险未根除）

**正确做法**：显式配置环境变量，让口令从代码（含兜底）中彻底移除。

---

## 3. 配置方法

### 方法 A（推荐，生产）：系统环境变量

写进 shell profile，让所有进程（含 hermes）继承：

```bash
# 写入 /etc/profile.d/srm_db.sh  或  ~/.bashrc
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD='真实密码'   # 生产环境替换为实际口令
```

生效：
```bash
source /etc/profile.d/srm_db.sh   # 或重开终端
# 重启 hermes 进程，确保子进程继承新环境
```

### 方法 B：hermes 启动脚本内 export

如果 hermes 由特定脚本/systemd 启动，把上面 5 行 `export` 加进启动脚本。关键：**hermes 的子进程（python `os.getenv`）必须能继承这些变量**。

### 方法 C：systemd 服务（若 hermes 是 service）

```ini
# /etc/systemd/system/hermes.service 的 [Service] 段
Environment="SRM_DB_HOST=127.0.0.1"
Environment="SRM_DB_PORT=3306"
Environment="SRM_DB_NAME=powerelf_srm_yml"
Environment="SRM_DB_USER=root"
Environment="SRM_DB_PASSWORD=真实密码"
# 或用 EnvironmentFile=/etc/hermes/db.env
```
改完 `systemctl daemon-reload && systemctl restart hermes`。

---

## 4. 脚本内残留的兜底值（生产前应清理）

配置环境变量后，为彻底根除硬编码，清理以下兜底：

| 文件 | 行 | 当前 | 建议改为 |
|------|----|------|---------|
| `plan-generation/scripts/query_utils.py` | 35 | `'password': os.getenv('SRM_DB_PASSWORD', '123456aA.')` | 移除兜底 + 无变量时报错退出（见下方代码） |
| `simulation/scripts/query_simulation_data.py` | 19 | `'password': os.getenv('SRM_DB_PASSWORD', '')` | 同上 |

**建议的无兜底实现**（强制要求配置，连不上时报清晰错误）：

```python
import os, sys

def _require_env(name):
    val = os.getenv(name)
    if not val:
        sys.exit(f"[DB] 环境变量 {name} 未设置。请配置 SRM_DB_* 环境变量（见 docs/db-credential-config.md）。")
    return val

DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),       # host/port/name 可留默认
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': _require_env('SRM_DB_USER'),
    'password': _require_env('SRM_DB_PASSWORD'),          # 口令/用户强制要求
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
}
```

---

## 5. 测试阶段建议

- **现在（测试环境）**：可暂保留脚本兜底值（否则预演脚本连不上 DB，eval 跑不动）
- **上生产前**：必须完成第 3 节配置 + 第 4 节清兜底，否则口令仍在代码里

---

## 6. 验证配置是否生效

```bash
# 确认变量已设
echo "$SRM_DB_PASSWORD"   # 应输出非空

# 测试脚本能连
cd SmartTwinRes-skills/plan-generation/scripts
python3 -c "from query_utils import get_connection; c=get_connection(); print('✅ 连接成功'); c.close()"
```

---

## 7. 安全注意

- 口令不要写进 git 仓库（`/etc/profile.d/srm_db.sh` 等应在 git 外，权限 `chmod 600`）
- 生产口令应与测试口令不同
- 若用 systemd EnvironmentFile，该文件权限设 `600 root:root`

---

## 关联
- auditor C2 检查（`skill-auditor.py`）会检测明文口令；配置环境变量 + 清兜底后，C2 转为 PASS
- 详见 `simulation/autoresearch-simulation/autoresearch-simulation/docs` 下 autoresearch 报告的 Exp 7（C2 过拟合）章节
