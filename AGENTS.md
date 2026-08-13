# AGENTS.md — SmartTwinRes Skills

智慧水利水库运行管理矩阵平台的 Claude Code / Hermes Agent Skill 集合（预报 forecasting / 预案 plan-generation / 预演 simulation / 预警 early-warning / 诊断 diagnosis-verification + supervisor 编排层）。**无构建系统**：纯 Python 3（CI 用 3.11），无 requirements.txt / pyproject；核心依赖 `pymysql`，预演编排服务另需 `flask`/`numpy`/`requests`（`pip install pymysql flask numpy requests`）。所有文档、注释、提交信息用简体中文；提交用 Conventional Commits 风格（`feat/fix/docs(scope): 中文说明`）。Git 远端：`github.com/wangjinzhong87706022/reseroir-4p-skills`（注意拼写 reseroir）。

## 目录布局（注意：Skill 直接位于仓库根目录，不是 skills/ 子目录）

- `lib/` — 共享库，唯一 DB / 路径 / 租户入口：`db.py`（连接）、`bootstrap.py`（三层定位：`SRM_SKILLS_ROOT` env → 候选根 → RuntimeError）、`paths.py`（路径，含 `get_skill_dir()` / `get_reservoir_dir()`）、`tenant.py`（水库身份）、`filters.py`。脚本靠 `sys.path.insert(0, .../lib)` 引入。
- `shared/` — 跨 skill 共享知识库：`sql-safety-rules.md`（SQL 安全规则）、`tenant-filtering-rules.md`（租户过滤铁律）、`db-connection.md`（DB 连接标准）、`common-schema/`（跨 skill 复用的表结构）。各 skill 的 `references/` 只保留本 skill 专属知识。
- `<skill>/` — 每个 Skill：`SKILL.md`（核心文档，含固化"标准导入片段"）、`scripts/`（`query_<domain>_data.py`）、`references/`、`tests/`、`data/`、`db-config.md`、`models/`（simulation / plan-generation 有 dispatch/flood-routing/xaj 模型，`start_models.sh` 启动）。
- `supervisor/` — 四预智能体编排层：`scripts/scene_router.py`、`supervisor_state.py`（SQLite 事件库）、`arbitrator.py`、`orchestrator.py`、`inspection_check.py`；`references/dag_order.py` 定义四场景 DAG。
- `autoresearch-*/`、`autoresearch/` — 实验产物（results、Q*.txt、日志、`SKILL.md.baseline`）。**不要改动 `.baseline` 文件或重跑实验**，那是评估基准。
- `pdfs/`、`pdfs_backup/` 已被 gitignore（各 2-5GB 原始资料）；文本提取物在 `pdf_text_analysis/`。

## 命令

```bash
python3 -m unittest discover tests          # supervisor 单元测试，无需 DB（28 个用例）
python3 test_skills.py --list                # 端到端用例清单
python3 test_skills.py --skill forecasting   # E2E：需 Hermes 平台 + 真实 DB（CI 中已注释禁用）
bash supervisor/demo.sh                      # 四场景一键演示（需 DB）
```

格式规范：PEP 8 + `black`（无配置文件）。没有 lint 命令。

## 非显而易见的坑

1. **数据库凭据强制走环境变量**，缺失即 `sys.exit`：`SRM_DB_*` → `POWERELF_DB_*` → 默认值；默认库名是 `powerelf_srm_yml`（不是你以为的名字）。**禁止硬编码口令**，`db.py` 已统一处理，新脚本直接 `from db import execute_query`。
2. **租户（多水库）**：所有 tenant_id 一律经 `lib/tenant.py` 解析，业务代码禁止硬编码 18/20。默认 18=三岔 sancha；桃曲坡需 `export SRM_TENANT_ID=20 SRM_RESERVOIR_NAME=taoqupo`。SQL 中的水位/汛限查询必须按 tenant 过滤（历史上有过漏过滤的 bug）。
3. **路径**：禁止硬编码绝对路径，一律用 `lib/paths.py`（`PROJECT_ROOT`、`get_skill_dir()`、`get_reservoir_dir()` 等）。
4. `tests/` 用标准库 `unittest`（pytest 未安装）；`tests/integration/test_supervisor_e2e.py` **不连真实 DB**——用临时 `SRM_STATE_DIR` 的 SQLite State 注入结构化 stage 结果，断言四场景仲裁/报告里程碑。整套 `tests/` + `tests/integration/` 在 CI 里以 `python3 -m unittest discover tests` 跑，无 DB、无 hermes。
5. simulation 各脚本的**输出契约已统一**（`full_context` 等），改输出结构前先查 `docs/` 与近期评审文档，避免破坏 supervisor 的仲裁消费方。
6. 新增 Skill 需同步注册到 `test_skills.py` 的 `SKILLS` 表和 `DB-CONFIG-STANDARD.md` 的适配清单。

## 共享层定位（SRM_SKILLS_ROOT）

`lib/bootstrap.py` 实现三层定位，所有 skill 脚本统一使用：

```
SRM_SKILLS_ROOT env（部署契约，主路径）
  → 候选根兜底（_KNOWN_ROOTS 元组遍历，dev 便利）
  → RuntimeError（找不到 lib/db.py 时）
```

**为什么需要 env 变量**：Hermes 暂存脚本里 `__file__` 不可靠，必须用 env 变量定位共享层。

### 标准导入片段（各 SKILL.md 已固化，生成代码时照抄）

**LLM 运行时**（Hermes 暂存脚本，`__file__` 不可靠）：

```python
# 标准导入片段（照抄，禁手写 pymysql.connect / 硬编码密码）
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

**离线脚本**（`scripts/` 下，`__file__` 可靠）：

```python
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

### 共享资源索引

| 资源 | 路径 | 用途 |
|------|------|------|
| DB 连接库 | `$SRM_SKILLS_ROOT/lib/db.py` | 唯一 DB 入口（`execute_query` / `execute_query_list` / `unpack`） |
| 三层定位器 | `$SRM_SKILLS_ROOT/lib/bootstrap.py` | `locate_root()` / `locate_lib()` / `locate_shared()` |
| 路径配置 | `$SRM_SKILLS_ROOT/lib/paths.py` | `PROJECT_ROOT` / `get_skill_dir()` / `get_reservoir_dir()` |
| 租户解析 | `$SRM_SKILLS_ROOT/lib/tenant.py` | `current_tenant_id()` / `resolve_tenant()` |
| SQL 安全规则 | `$SRM_SKILLS_ROOT/shared/sql-safety-rules.md` | 只读原则、必有三要素、JOIN 约束 |
| 租户过滤铁律 | `$SRM_SKILLS_ROOT/shared/tenant-filtering-rules.md` | tenant_id 过滤、多水库适配流程 |
| DB 连接标准 | `$SRM_SKILLS_ROOT/shared/db-connection.md` | 环境变量命名空间、标准导入片段 |
| 跨 skill 表结构 | `$SRM_SKILLS_ROOT/shared/common-schema/` | 唯一真相源，避免各 skill references/ 漂移 |

### 部署环境变量清单

```bash
# 共享层定位（必须，部署契约）
export SRM_SKILLS_ROOT=/home/scada/SmartTwinRes-skills

# 数据库连接（必须，凭据保护）
export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root SRM_DB_PASSWORD=***

# 水库身份（可选，缺省三岔 tenant 18）
export SRM_TENANT_ID=20 SRM_RESERVOIR_NAME=taoqupo  # 桃曲坡
```

### query_utils.py 副本收口说明

`forecasting/scripts/query_utils.py` 与 `plan-generation/scripts/query_utils.py` 已是纯 re-export（从 `lib.db` 重新导出）。新代码**直接** `from lib.db import execute_query, execute_query_list, unpack`，不再依赖本地 `query_utils.py`。本地副本保留仅为向后兼容，后续可删。
