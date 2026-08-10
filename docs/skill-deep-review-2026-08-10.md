# SmartTwinRes-skills 深入评审与修复清单（2026-08-10）

> **用途**：本文档是 2026-08-10 对全仓库 6 个 Skill + 共享层 + supervisor 编排层的深入评审结论，**面向实施**。每个工作项给出确切的文件/行号、现状证据、目标状态、修复方法与验收方式，可被任何 coding Agent 直接认领实施，无需重新评审。
>
> **严重度**：`P0` 阻断（安全/正确性，必须立即修） · `P1` 重要（尽快修） · `P2` 改进 · `P3` 清理。
>
> **实施顺序**：见文末「六、推荐执行顺序」。**不要跳过「零、前置验证门」**。

---

## 一、系统背景（实施前必读）

- **产品**：水库智慧调度「四预智能体」——预报 forecasting / 预案 plan-generation / 预演 simulation / 预警 early-warning / 诊断 diagnosis-verification + `supervisor` 编排层。**安全攸关系统**：输出会进入汛限/泄洪调度决策。
- **Skill 直接位于仓库根目录**（不是 `skills/` 子目录）。6 个域 Skill + supervisor 各有 `SKILL.md`（LLM 提示词文档）+ `scripts/` + `references/`。
- **共享层**：`lib/`（`db.py`/`tenant.py`/`paths.py`/`bootstrap.py`/`filters.py`，唯一 DB/路径/租户入口）+ `shared/`（跨 Skill 知识库）。
- **租户模型**：一个水库 = 一个 tenant_id。三岔=`18`、桃曲坡=`20`（live DB 还有 `17`/`19`）。身份统一经 `lib/tenant.py` 的 `resolve_tenant()` 解析（显式参数 > `SRM_TENANT_ID` env > 默认 `18`）。
- **关键架构事实**：`lib/filters.py` 已提供 `apply_table_filters()` / `generate_where_clause()` 自动过滤助手，但**绝大多数 query 脚本绕过它、手写 SQL**——这是租户过滤系统性漏掉的直接原因（见 P0-1、P0-2）。

## 二、铁律与禁区（实施时不得违反）

1. **凭据**：DB 口令强制走 `SRM_DB_*` 环境变量，禁止硬编码；DB 唯一入口是 `lib/db.py`（`execute_query` / `execute_query_list` / `unpack`）。**禁止** `pymysql.connect` 直连出现在 skill 查询脚本里。
2. **租户**：业务代码禁止硬编码 `18`/`20`；所有水位/汛限/曲线/历史查询必须按 `tenant_id` 过滤。
3. **路径**：禁止硬编码绝对路径，一律用 `lib/paths.py`。
4. **只读**：skill 查询脚本只允许 `SELECT/SHOW/DESCRIBE`；写操作仅限 `data/` 生成器与 admin 工具。
5. **输出契约**：`simulation` 输出（`full_context` 等）被 supervisor 仲裁消费，**改结构前先查本清单 P0-3 / P1-1**。
6. **禁区——不要改动**：
   - 所有 `*.baseline` 文件（评估基准，靠约定保护，见 P3-7）。
   - `autoresearch*/` 下的 `results/`、`Q*.txt`、实验日志（评估产物）。
   - `pdfs/`、`pdfs_backup/`（gitignore，各 2-5GB 原始资料）。
7. **提交规范**：Conventional Commits 中文说明（`fix(supervisor): 中文说明`）。

## 三、标准导入片段（修复脚本时照抄）

**离线脚本**（`scripts/*.py`，`__file__` 可靠）：

```python
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))
from db import execute_query, execute_query_list, unpack
from tenant import resolve_tenant
```

**LLM 运行时**（Hermes 暂存脚本，`__file__` 不可靠）：

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query, execute_query_list, unpack
from tenant import resolve_tenant
```

> ⚠️ 现网实际脚本普遍用 `from lib.db import ...`（见 P1-13，需统一）。

---

## 四、P0 — 阻断级（安全/正确性，立即修）

### 【零、前置验证门】桃曲坡库 tenant_id 是否已填值

**在批量实施 P0-1 之前必须先跑**（只读）。因为如果桃曲坡独立库的 `tenant_id` 列存在但**全 NULL**，加 `AND tenant_id=20` 会**静默返回空集**（查询不报错但没数据，比报错更危险）。

```sql
-- 在桃曲坡库（SRM_TENANT_ID=20）执行
SELECT tenant_id, COUNT(*) FROM att_res_flse_lim GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) FROM st_rsvr_r         GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) FROM srm_flood_history_base GROUP BY tenant_id;
```

- 看到 `20` 有行数 → 放心批量补 filter（P0-1）。
- 只看到 `NULL` → **先回填** `UPDATE <表> SET tenant_id=20 WHERE tenant_id IS NULL;` 再补 filter。
- 列不存在 → live schema 已确认列都在（curve 表带 tenant_id/res_guid），排除。

> 结论（来自上一轮讨论）：**保留 tenant_id 过滤，不为桃曲坡单库特判**。共享代码 + 近零成本 + 防御本仓库 #1 历史 bug 类（`9ad7054` 曲线查询跨库串库修复）。

---

### P0-1　租户隔离系统性失效（约 50 条查询漏过滤）

**严重度**：P0（安全）　**依赖**：先做【前置验证门】与 P0-2

**现状**：下列脚本的查询函数未加 `tenant_id` 过滤，三岔(18)/桃曲坡(20)数据会串库，直接影响汛限/历史预案/雨量判定——历史 bug 同形复发。

| 文件 | 漏过滤范围 |
|------|-----------|
| `early-warning/scripts/query_early_warning.py` | **全部 16 个查询函数零过滤**（query_unconfirmed/query_by_level/query_recent/query_water_level/query_rainfall 等） |
| `diagnosis-verification/scripts/check_data_quality.py` | `check_water_level()` / `check_rainfall_forecast()` / `check_alerts()` 三个函数零过滤 |
| `plan-generation/scripts/query_plan_analysis.py` | **9/9 查询零过滤**，脚本甚至未 `import tenant` |
| `plan-generation/scripts/query_plan_data.py` | 15 条中仅 5 条过滤；`query_flood_limit`/`query_historical_plans`/`query_similar_plans`/`query_scenarios`/`query_recent_rainfall` 漏过滤 |
| `simulation/scripts/query_simulation_data.py` | 5 个 `srm_flood_history_*` 仅按 flood_id 过滤无 tenant；`query_similar_floods`/`query_scenarios`/`query_recent_rainfall` 漏过滤 |
| `supervisor/scripts/inspection_check.py:43,48` | `eq_equip_base` 设备总数/类型分布查询漏过滤（其余 anomaly/offline/defect/gates 有过滤） |

**目标**：每条 SQL 的 WHERE 含 `AND tenant_id = %s`，参数元组带 `resolve_tenant(tenant_id)`。

**修复（推荐——根治，而非逐条打补丁）**：
1. 优先让这些脚本**路由到 `lib/filters.py` 助手**：用 `apply_table_filters(sql, table_name, tenant_id)` 或 `generate_where_clause(table_name, extra_conditions, tenant_id)` 拼装 WHERE。这样过滤规则集中在一处，杜绝再次遗漏。
2. 不便改造的查询，手工补：函数签名加 `tenant_id=None`，首位 `tid = resolve_tenant(tenant_id)`，SQL 的 WHERE 追加 `AND tenant_id = %s`，`execute_query_list(sql, (..., tid))`。
3. 对照 P0-2：`lib/filters.py` 规则表里 `att_res_flse_lim` 当前误标 `filter:False`，修对后助手才能正确处理汛限表。

**【需决策】`ew_info_message`**：`lib/filters.py:30` 将其标为 `filter:False`（注释"告警跨租户,不强制"）。early-warning 多个查询命中此表。需产品确认：告警是确实跨租户共享，还是应按库隔离？**默认保持 `filter:False`**，除非产品明确要求隔离。

**验收**：
```bash
# 每个脚本的关键表查询都应能在 WHERE 里找到 tenant_id
grep -rn "tenant_id" early-warning/scripts/ plan-generation/scripts/ simulation/scripts/ diagnosis-verification/scripts/check_data_quality.py supervisor/scripts/inspection_check.py | wc -l
# 双 tenant 数据隔离测试（见 P3-5）：mock 18/20 数据，断言每条查询只回本租户行
```

---

### P0-2　根因：lib/filters.py 与 table-schema 误标汛限表无 tenant_id

**严重度**：P0（这是 P0-1 的根因）　**位置**：
- `lib/filters.py:35` → `'att_res_flse_lim': {'filter': False}`，注释"以下表无 tenant_id 列"
- `forecasting/references/table-schema.md:39`（及 plan-generation/simulation 同名文件）
- 同理核查 `att_res_stag_cap_disc`、`att_res_discharge_curve` 等曲线表

**现状**：标注声称汛限/曲线表无 `tenant_id` 列。但 **live DB 权威 schema 确认这些表都有 `tenant_id`**（curve 表另带 `res_guid`；tenant map 17/18/19/20）。开发者信了 lib/doc，于是 `query_flood_limit` 漏过滤——桃曲坡会读到三岔汛限 462.5m（实应 786.8m）。

**目标**：lib 规则表与各 `table-schema.md` 与 live DB 对齐。

**修复**：
1. `lib/filters.py`：`'att_res_flse_lim': {'filter': True}`（及确认有 tenant_id 的其他曲线表）。
2. 各 `table-schema.md`：表结构标注"有 tenant_id"；顶部加一行"**以 live DB `DESCRIBE` 为唯一真相源，本文档仅辅助**"。
3. 长期：把跨 Skill 表结构迁到 `shared/common-schema/`（兑现"唯一真相源"，见 P2-6）。

**验收**：`python3 -c "from lib.filters import TENANT_ID_FILTER_TABLES as t; assert t['att_res_flse_lim']['filter'] is True"`。

---

### P0-3　仲裁安全闭环失效（plan-gen full_context 缺峰值字段）

**严重度**：P0（正确性，安全闭环）　**依赖**：与 P1-1（输出契约）一起改

**现状**：
- `plan-generation/scripts/query_plan_data.py:337-351` `query_full_context()` 返回的 dict **不含** `max_level` / `max_discharge`（`max_water_level` 仅嵌套在 `config` 子字典里，无顶层键）。
- `supervisor/scripts/orchestrator.py:340-344` 读 `plan.get("max_level")` 等键 → 恒为 `None`。
- `supervisor/scripts/arbitrator.py:69,79,190` 的守卫 `if plan_level is not None` 恒为 `False` → **规则 1（方案水位>仿真→adjust）与规则 2（下泄>安全泄量→reject）是死代码**。
- 结果：**无论方案多危险，场景 A/D 仲裁永远返回 `accept`**。

**目标**：plan-gen `full_context` 输出与 simulation `M4` 契约对齐的显式峰值键，仲裁规则恢复生效。

**修复**（任一）：
- **方案 A（推荐）**：`query_full_context` 增加 `'max_level'`/`'max_discharge'` 汇总键（从 `scenarios`/`current_water_level` 提取峰值，参考 `simulation/scripts/query_simulation_data.py:268-280` 的 M4 写法）。
- **方案 B**：在 orchestrator 端仿 `_extract_sim_peaks` 增加 plan 峰值提取。

**【关键验收——别再被测试骗了】**：现有 supervisor 测试用 `_seed_stage` 直接注入 `{"max_level": 786.95, "max_discharge": 100}`，**绕过了真实 plan-gen 输出**，所以这个 P0 一直没被发现。必须补一个**真实下游契约测试**（见 P3-5）：用 `query_full_context()` 实际返回值喂给 arbitrator，断言危险水位时返回 `adjust`/`reject` 而非 `accept`。

---

### P0-4　硬编码密码清除

**严重度**：P0（安全）　**位置**：
- `diagnosis-verification/scripts/hermes_diagnose_runner.py:33` → `'password': os.getenv('SRM_DB_PASSWORD', '123456aA.')`
- `early-warning/SKILL.md:52`（及 :360 附近）→ `mysql -h 127.0.0.1 ... -p123456aA. powerelf_srm_yml`
- 同文件 `hermes_diagnose_runner.py:144-149` 绕过 `lib/db.py` 直连 `pymysql.connect(**DB_CONFIG)`。

**目标**：密码零硬编码；统一走 `lib/db.py`。

**修复**：
1. `hermes_diagnose_runner.py`：删本地 `DB_CONFIG`，改 `from lib.db import execute_query_list, get_connection`；密码缺失应 `_require_env('SRM_DB_PASSWORD')` 报错退出，不留默认值。
2. `early-warning/SKILL.md`：`-p"$SRM_DB_PASSWORD"`，与 forecasting/plan-generation/simulation 的 SKILL.md 一致。

**验收**：`grep -rnE "123456aA\.|'-p[^\"']" --include=*.py --include=*.md .`（应只剩无害示例或为空）。

---

### P0-5　lib/paths.sh 指向不存在的 skills/ 子目录

**严重度**：P0（基础设施）　**位置**：`lib/paths.sh:11`

**现状**：`export SKILLS_DIR="$PROJECT_ROOT/skills"`，但 Skill 直接在根目录（`paths.py:27` 正确为 `SKILLS_DIR = PROJECT_ROOT`）。`skills/` 目录不存在 → 一旦 `source lib/paths.sh`，所有 `$FORECASTING_DIR` 等指向空路径。

**修复**：`export SKILLS_DIR="$PROJECT_ROOT"`（顺手把 :10 的 `SMARTTWINRES_ROOT` 与 Python 侧 `PROJECT_ROOT` 命名统一，见 P3-6）。

**验收**：`source lib/paths.sh && test -d "$FORECASTING_DIR" && echo OK`。

---

## 五、P1 — 重要（尽快修）

### P1-1　full_context 输出契约三态漂移

**位置**：`forecasting/.../query_forecast_data.py:184-207` vs `simulation/.../query_simulation_data.py:41-76` vs `plan-generation/.../query_plan_data.py:86-120`
**现状**：`full_context.flood_limit` 在 forecasting=dict、plan/simulation=list[dict]；`current_water_level` 数组 vs 字段（supervisor README:150 已抱怨）。仲裁器解析脆弱，静默拿 `None`。
**目标**：三 Skill 关键字段统一为平铺标量 + `*_source`/`*_raw` 辅助字段，或在 supervisor 侧写显式适配器 + shape 断言。
**与 P0-3 的关系**：一起改，统一 `full_context` 契约。

### P1-2　scene_router DAILY_STRONG 吞掉大坝诊断(B)

**位置**：`supervisor/scripts/scene_router.py:82-86`
**现状**：实测"每日监测渗压数据异常"被路由到 C（日常）而非 B（大坝诊断）。`DAILY_STRONG` 只让步于 `EMERGENCY_STRONG`，渗压/位移/渗流等大坝安全信号被压制。
**修复**：DAILY_STRONG 检查增加 B 场景强词排除（渗压/渗流/位移/裂缝/扬压力/沉降），或改为"仅当无 B/D 命中时才归 C"。加单测覆盖该 case。

### P1-3　status='error' 孤儿状态

**位置**：`supervisor/scripts/orchestrator.py:596`（写 `status='error'`）vs `supervisor/scripts/supervisor_state.py:511`（`cmd_status` choices 不含 error）、`:163-164`（queue 只列 running/awaiting）、`:340`（replay 也不含 error）
**现状**：error 事件从 queue **和** replay 都消失，运维完全看不见。
**修复**：`cmd_status` choices 加 `'error'`；queue/replay 查询纳入 `'error'`；或 orchestrator 改用语义已存在的 `'aborted'`。

### P1-4　仲裁 stages 查询不过滤 status

**位置**：`supervisor/scripts/orchestrator.py:305-309` → `SELECT stage, result_json FROM stage_results WHERE event_id=?`
**现状**：未加 `AND status='ok'`，异常路径（单阶段重跑）会消费 error 阶段脏数据做仲裁。
**修复**：加 `AND status='ok'`，或 unpack 后校验 stage status。

### P1-5　场景 A step2 缺 --json

**位置**：`supervisor/scripts/orchestrator.py:67-69`（不带 --json）vs `:84-86`（场景 B step1 带 --json）
**现状**：`check_data_quality.py` 不带 `--json` 输出中文 key 人类可读文本，`_unpack_stage_result` 解析失败返回 `{}`，step2 成死数据（现被"仲裁不消费 step2"掩盖）。
**修复**：统一两处调用都带 `--json`（或让 `check_data_quality.py` 的 `as_json=False` 分支也输出结构化数据）。

### P1-6　demo.sh timeout 与七步编排不匹配

**位置**：`supervisor/demo.sh:42`（timeout 180s）vs `orchestrator.py:131`（per-stage 60s × 7 步 = 420s）
**现状**：极端情况 demo 会 kill 正在执行的编排器，留残破 stage 结果与 `running` 状态事件。
**修复**：demo.sh timeout 提到 ≥480s，或 per-stage timeout 降到 ~20s。

### P1-7　模型泄流曲线非单调（物理错误）

**位置**：`plan-generation/models/dispatch_model.py:269-275` 与 `flood_routing.py:202-208`（DEFAULT_DC_CURVE）
**现状**：曲线点 `(462.0,99),(462.5,94),(463.0,100)`——水位升高泄量反降（99→94），违反堰流 Q∝H^1.5。线性插值代码 `interpolate_wl_to_flow` 假定单调，会算出"水位涨但泄量减"的矛盾结果，进入削峰率/安全余量判定。
**修复**：核实 462.5 应≈96-97 或删除该点，使曲线严格单调递增；插值入口加单调性断言。

### P1-8　simulation_service 三岔常量硬编码

**位置**：`simulation/models/simulation_service.py`（1039 行，**0 处 tenant 引用**）散布 20+ 处：`initial_wl=459.18` / `flood_limit=462.88` / `safe_drainage_capacity=95.1` / `max_drainage_capacity=192` / `wl_score=100-(wl-455)*10`；另有 `flood_routing.py:83`、`xaj_model.py:246,279`。
**现状**：service 不读 `SRM_TENANT_ID`/`SRM_RESERVOIR_NAME`，桃曲坡（788m 量级）部署一旦调用方漏传参会**默认套三岔曲线/汛限**。
**修复**：service 启动读 reservoir profile / `model_config`，把默认值改 `None` 并缺失时 **fail-loud**（报错而非套三岔）；或强制必传参。

### P1-9　early-warning/SKILL.md 技术引用全面修正

**位置**：`early-warning/SKILL.md`（6 个 SKILL.md 里质量最差，评 2/5）
**现状/修复**：
- `:144-169`：删除不存在的 `/opt/git/hermes-agent/skills/powerelf/lib/db.py` 路径和不存在的 API `query_multi()`/`close_all()`（lib.db 实际只导出 `execute_query`/`execute_query_list`/`unpack`/`query_one`）。替换为「三、标准导入片段」引用。
- `:128-133`：SQL 示例占位符 `#{id}`/`#{关键词}`/`#{eqCode}`（MyBatis 风格）→ pymysql `%s`。
- `:16`：`prerequisites.env_vars` 用 `POWERELF_DB_*`（旧命名空间）→ `SRM_DB_*`（主命名空间，与其余 5 个 SKILL.md 一致）。
- `:52`：硬编码密码见 P0-4。

### P1-10　plan-generation/SKILL.md 围栏未闭合 + 误导

**位置**：`plan-generation/SKILL.md:122`（```bash 未闭合）、`:180`
**现状**：围栏未闭合导致「full_context 优先原则」段及后续命令被当成同一代码块正文，提示词渲染破损；`:180` 写"历史预案/洪水：已按租户隔离，无需额外过滤"——实际 `query_plan_data.py` 这两类查询恰好漏过滤（P0-1），直接误导 LLM 别修。
**修复**：补闭合 ```；`:180` 改为"已由脚本过滤，灵活路径自定义 SQL **必须**补 `tenant_id=%s`"。

### P1-11　lib/db.py 连接池初始化无锁

**位置**：`lib/db.py:62-80` `_get_pool()`
**现状**：`if _pool is not None` 检查与 `_pool = PooledDB(...)` 赋值之间无锁，TOCTOU 竞态。Flask supervisor 是多线程环境，并发首调可能创建多个 `PooledDB(maxconnections=5)` → MySQL 连接数耗尽。
**修复**：`threading.Lock()` 包裹 pool 初始化（双重检查锁定）。

### P1-12　引用不存在的 docs/db-credential-config.md

**位置**：`lib/db.py:11,36`（含 `_require_env` 用户可见错误提示）、`forecasting/scripts/query_utils.py:8`、`plan-generation/scripts/query_utils.py:8`、`shared/db-connection.md:75`
**现状**：四处引用 `docs/db-credential-config.md`，但该文件在仓库根**不存在**（只在 `forecasting/docs/` 有 per-skill 副本）。缺凭据时 `sys.exit` 打出的指引是死链。
**修复**：统一改为引用 `shared/db-connection.md`；删 forecasting/docs/ 重复副本。

### P1-13　标准 import 片段与现网不一致

**位置**：`shared/db-connection.md:36-38`
**现状**：标准片段写 `from db import execute_query`，但全部实际 skill 脚本用 `from lib.db import execute_query`。LLM 照抄片段会生成与现网不一致的 import。
**修复**：片段统一为 `from lib.db import execute_query, execute_query_list, unpack` + `from lib.tenant import resolve_tenant`（与「三、标准导入片段」一致）。

### P1-14　删除死脚本 forecasting/tmp_query_water.py

**位置**：`forecasting/tmp_query_water.py:1-51`
**现状**：直连 `pymysql.connect`（绕过 lib/db.py）、硬编码 `stcd='3'`、无 tenant_id、`DESCRIBE st_rsvr_r`（DDL 类）。是危险"灵活路径"样本。
**修复**：删除（已有 `query_forecast_data.py --type current_water_level` 替代）。

### P1-15　test_skills.py SKILLS 表补全 3→6

**位置**：`test_skills.py:62-84`
**现状**：SKILLS 表只注册 forecasting/plan-generation/simulation，缺 early-warning/diagnosis-verification/supervisor。"新增 Skill 注册守卫"形同虚设。
**修复**：补充三个 SkillDefinition（即使 E2E 需 Hermes 平台，`--list` 至少应覆盖全部）。

### P1-16　DB-CONFIG-STANDARD.md 适配清单补全

**位置**：`DB-CONFIG-STANDARD.md:5,58-63`
**现状**：适用范围与已适配清单只列 4 个 skill，漏 diagnosis-verification/supervisor。
**修复**：补两行（并见 P2-9，考虑与 shared/db-connection.md 合并以单一真相源）。

---

## 六、P2 — 改进

### 模型数值（domain-critical，建议尽早）

- **P2-1** `plan-generation/models/xaj_model.py:134` — XAJ 全产流判据 `if PE + A >= 1:` 量纲不符（mm vs 无量纲），标准应为 `PE+A >= WMM`（=WM*(1+B)）；:140 行用 `WM*pow(...)` 应为 `WMM*pow(...)`。偏低估全产流触发。核对《水文预报》公式后修正，加解析解单测。
- **P2-2** `plan-generation/models/flood_routing.py:134-139` — 超限软约束 `current_wl=max_wl; current_cap=wl_to_cap(max_wl)` 直接丢弃超额水体，破坏质量守恒。改为转 `extra_outflow` 或记 `spill_volume`。
- **P2-3** `xaj_model.py:285-287,316-317` — 全局可变模型实例 + Flask `threaded=True`，不同 `watershed_area` 并发互相覆写（桃曲坡 1335 / 三岔 161.25 并发算错）。改 per-request 实例化或 `threading.local()`。
- **P2-4** `dispatch_model.py:19` — `from scipy.optimize import minimize_scalar, minimize` 死 import（实为规则法）。删除，docstring 改"规则法调度"。
- **P2-5** `flood_routing.py:143-144` — O(n²) 累加，改 `np.cumsum` / running sum。
- **P2-17** `xaj_model.py:145-147` — 土壤含水更新缺 WU→WL→DW 级联充填，与三层蒸散发模型不闭合。补标准级联 + 算例验证。

### 文档/契约漂移

- **P2-6** `shared/common-schema/` — README 声称"唯一真相源"收录 2 表，实际只有 README、零 schema 文件。要么补 `st_stbprp_b.md`/`st_rvfcch_b.md`，要么降级措辞为"规划中"。
- **P2-7** forecasting vs plan-generation 的 `table-schema.md` 同名表量级矛盾（forecasting 说 st_rsvr_r=19万；plan-gen 说百万级）。以现网实测为准统一，或抽到 common-schema。
- **P2-8** `supervisor/SKILL.md:150-151` 引用不存在的 `references/dag-scenarios.md`/`arbitration.md`（只有 `dag_order.py`）。创建或修正引用。
- **P2-9** 根目录 `DB-CONFIG-STANDARD.md` 与 `shared/db-connection.md` 内容重复、漂移风险。以 shared 版为唯一真相源，根版改链接或删。
- **P2-13** `lib/db.py` 的 `MAX_ROWS`/`truncated` 契约零消费方——截断时所有调用方静默丢数据。至少 `execute_query_list` 在 `truncated=True` 时 `log.warning`，或在 sql-safety-rules 强调消费方应检查。
- **P2-20** 多个 SKILL.md 结尾段硬引"依据《三岔水库调度规程》"——桃曲坡部署引错水库。改 `${reservoir_profile}调度规程` 占位。

### 死代码/重复

- **P2-12** `forecasting/scripts/query_utils.py` 与 `plan-generation/scripts/query_utils.py` 完全相同的 re-export 副本（plan-gen 那份零消费者）；`lib/db.py:228` `query_one()` 零调用方。迁移唯一消费者（`forecasting/data/generate_forecast_data.py:29`）改 `from lib.db import` 后删两份 + query_one。
- **P2-14** `simulation/autoresearch-simulation/` 229 文件/2.3MB 死代码堆（4 份 `results.*.bak`、5 份 `SKILL.md.v*`、嵌套副本 `autoresearch-simulation/autoresearch-simulation/`、十几个 `test-runner-*.sh` + `log-*.log`）。.gitignore 排除或迁 `archive/`，保留最新 `results.json` + `CHECKPOINT.md`。
- **P2-19** `simulation/scripts/query_simulation_data.py:21` `from lib.db import ..., DB_CONFIG` 把含密码句柄的配置暴露到 query 脚本 namespace。仅 import 用到的 query 函数。

### 水库 profile 不对称

- **P2-10** `reservoirs/sancha/inspection-items.md`、`defect-disposal.md` 是桃曲坡模板直接复制，内容标"待三岔核对"（坝高 61m、7 孔闸门等不适用三岔）。若三岔需要巡检能力则从正式预案补全；否则标 stub 并在 SKILL.md 提示跳过。
- **P2-11** `reservoirs/sancha/identity.md`（48 行）vs `taoqupo/identity.md`（109 行）结构不对称（缺防洪标准/枢纽建筑物/安全鉴定/启闭设备）。`characteristic-levels.md` 自承"预警阈值/洪峰分级/监测站网清单待补"。从调度规程补全或标注"数据从 model_config 动态读取"。
- **P2-18** `forecasting/data/generate_forecast_data.py:35,1229` 等数据生成器硬编码 `MOCK_TENANT=18`/SQL 内 `tenant_id=18`（虽是 data/ 生成器，仍违反铁律）。改 `resolve_tenant()` 或显式 `# noqa` 注释"数据生成器需固定 tenant"。

### 健壮性

- **P2-15** `supervisor/scripts/supervisor_state.py:63` SQLite 未开 WAL（journal_mode=delete），多进程并发写锁竞争。加 `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=10000`。
- **P2-16** `scene_router.py:91` 子串误匹配——"位移上涨"（水位语境）匹配 B 的"位移"（deformation）。易混词用边界匹配；`"渗漏"`（D 关键词）降为 B 或加上下文判定。

---

## 七、P3 — 清理

- **P3-1** `lib/bootstrap.py:19-23` `_KNOWN_ROOTS` 硬编码 `/home/scada/...`、`/opt/git/...` 绝对路径（违反铁律 3）。用 `Path(__file__).resolve().parents[1]` 作首选候选，仅留 `Path.home()/"SmartTwinRes-skills"` 兜底。
- **P3-2** `lib/db.py:145,152` `MAX_ROWS` 在 import 时绑定、函数默认参数在定义时绑定，import 后设 `SRM_DB_MAX_ROWS` 不生效。改 `max_rows=None` 默认 + 函数体内延迟读。
- **P3-3** `lib/db.py:24-27` `__all__` 导出私有 `_require_env`（下划线前缀）。去下划线改 `require_env`，或让调用方改用其他方式。
- **P3-4** `plan-generation/autoresearch-plan-skill/eval.py:102` pymysql 直连。改 `from lib.db import get_connection`。
- **P3-5** **缺测试层（放大了所有 P0）**：全栈无租户隔离单测；supervisor 测试用 `_seed_stage` 注入假峰值掩盖 P0-3。建议加 `tests/test_tenant_isolation.py`（mock 双 tenant 数据，断言每条 query 只回本租户行）+ 真实下游契约测试层（不注入假数据，用 `query_full_context()` 实际返回喂 arbitrator）。
- **P3-6** import 片段写法不统一（`from db` vs `from lib.db`）；`paths.sh` 的 `SMARTTWINRES_ROOT` vs `paths.py` 的 `PROJECT_ROOT` 命名不统一。
- **P3-7** 6 份 `*.baseline` 仅靠 AGENTS.md 约定保护，无 CI 守卫。加 pre-commit hook 校验 .baseline 不变，或接受当前约定。
- **P3-8** `orchestrator.py:331` 注释"场景A/D"误导（D 已在 :322 return）；`:184,526` 与 `supervisor_state.py:231` 裸 `sys.path.insert` 未走已有的 `_ensure_path` 去重 helper。

---

## 八、推荐执行顺序（高杠杆优先）

1. **前置验证门**（零）→ 确认桃曲坡库 tenant_id 有值。
2. **根因**（P0-2）→ 修 `lib/filters.py` + table-schema 的 tenant 标注。**先于 P0-1**，否则补的 filter 会被错误规则表干扰。
3. **租户隔离批量修复**（P0-1）→ 优先路由到 `lib/filters` 助手；**同步加 P3-5 租户隔离单测**防回归。
4. **仲裁闭环**（P0-3 + P1-1）→ 统一 `full_context` 契约 + 补真实下游契约测试（别再用假数据）。
5. **清凭据**（P0-4 + P1-11/12/13）→ 删硬编码密码、db.py pool 加锁、统一文档引用与 import 片段。
6. **基础设施零散 P0/P1**（P0-5、P1-2~P1-6）→ paths.sh、scene_router、status=error、stages 过滤、--json、demo timeout。
7. **模型物理正确性**（P1-7、P1-8、P2-1~P2-5、P2-17）→ 泄流曲线单调化、常量参数化、XAJ 判据/水量平衡/线程安全。
8. **文档/死代码清理**（P1-9/10/14~16、P2-6~P2-14、P2-19/20）→ SKILL.md 修正、common-schema 兑现、重复副本删除、autoresearch 死代码归档。
9. **水库 profile 对齐**（P2-10/11/18）→ sancha profile 补全。
10. **收尾**（P3 全部）。

---

## 九、整体验收门（实施完成后跑）

```bash
# 1. 单元测试全绿（无需 DB）
python3 -m unittest discover tests

# 2. 租户隔离 grep 守卫：关键表查询都应带 tenant_id
grep -rnE "FROM (st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)" \
  --include=*.py early-warning/ plan-generation/ simulation/ diagnosis-verification/ supervisor/
# 抽查上述命中行的上下文，确认 WHERE 含 tenant_id（或调用 apply_table_filters）

# 3. 零硬编码密码
grep -rnE "123456aA\.|password.*['\"]" --include=*.py --include=*.md .   # 应无业务命中

# 4. 仲裁闭环：用真实 plan-gen 输出喂 arbitrator，危险水位应返回 adjust/reject（非 accept）
python3 test_skills.py --list                    # 应列出全部 6 skill
python3 -c "from lib.filters import TENANT_ID_FILTER_TABLES as t; \
  assert t['att_res_flse_lim']['filter'] is True; print('filter rule OK')"
source lib/paths.sh && test -d "$FORECASTING_DIR" && echo "paths.sh OK"
```

**完成标志**：P0 全部清零且上方验收全绿；P1 完成度 ≥ 80%；租户隔离单测与真实下游契约测试已入库。

---

*评审来源：2026-08-10 四路并行深度评审（共享层/测试基建 · supervisor 编排 · 三预数据技能 · 预警诊断/跨切一致性）。所有 P0 锚点行号已人工复核。*

---

## 十、评估意见（2026-08-10 对本文档的复核）

> 本节是对上述评审清单本身的复核结论，基于逐条对照真实代码（`lib/filters.py` / `lib/db.py` / `lib/tenant.py` / `lib/paths.py` / `lib/paths.sh` / `supervisor/scripts/arbitrator.py` / `supervisor/scripts/orchestrator.py` / `supervisor/scripts/scene_router.py` / `plan-generation/scripts/query_plan_data.py` / `diagnosis-verification/scripts/hermes_diagnose_runner.py`）得出。目的是修正精度偏差、补齐漏项、调整误判的严重度，使本清单可作为实施依据直接分发。

### 10.1 总体判断

这份评审**质量很高、可实施性优秀**：几乎每条都带文件名、行号、现状证据、修复方法、验收命令，具备真正的可认领性。「零、前置验证门」「根因(P0-2)先于批量补丁(P0-1)」「依赖排序」等设计体现了真正的工程审慎——「补丁会让情况更糟(桃曲坡 tenant_id 全 NULL 时静默返回空集)」这类陷阱被提前识别，是高水平评审的标志。

但逐条核查后发现存在：**一个关键技术误判**（P0-3 严重度被高估）、**若干精度偏差**（行号/字段名/逻辑描述）、以及**5 个被漏掉的隐患**。下文分类说明并给出修订建议。

### 10.2 准确且高价值的条目（核查通过）

| 条目 | 核查结果 | 评价 |
|------|----------|------|
| **P0-2** filters.py 误标 `att_res_flse_lim: {filter: False}` | 实测 `filters.py:35` 确为 `{'filter': False}`，且 `:49` DELETED 表也漏了它 | 根因找得准。汛限表漏过滤会直接导致桃曲坡读三岔汛限，安全攸关。 |
| **P0-4** 硬编码密码 `'123456aA.'` | 实测 `hermes_diagnose_runner.py:33` 确有默认密码，`:144-149` 确实 `pymysql.connect(**DB_CONFIG)` 直连绕过 `lib/db.py` | 断言精确，定位准确。 |
| **P0-5** `paths.sh` 指向不存在的 `skills/` | 实测 `paths.sh:11` `export SKILLS_DIR="$PROJECT_ROOT/skills"`；而 `paths.py:27` 正确为 `SKILLS_DIR = PROJECT_ROOT` | 真 bug，`source lib/paths.sh` 后所有 `*_DIR` 指向空路径。 |
| **P1-3** `status='error'` 孤儿状态 | orchestrator 写 error，但 `supervisor_state.py` 的 `cmd_status` choices / queue / replay 均不含 error | 属实，运维盲区。 |
| **P1-7** 泄流曲线非单调 `(462.0,99),(462.5,94),(463.0,100)` | 物理上违反堰流 Q∝H^1.5，插值代码假定单调 | 属实，进入削峰率判定会出错。 |
| **P1-11** 连接池初始化无锁 | 实测 `db.py:62-80` `_get_pool()` 检查与赋值之间无 `threading.Lock` | 属实，Flask `threaded=True` 下 TOCTOU 竞态真实存在。 |
| **P3-1** `bootstrap.py` `_KNOWN_ROOTS` 硬编码绝对路径 | 违反铁律 3，但属于清理级 | 定级合理。 |

### 10.3 有精度偏差或技术误判的条目

#### 10.3.1 【P0-3 措辞修正，定级不变】原描述"完全裸奔"不准，但 P0 成立

**文档原断言**：「无论方案多危险，场景 A/D 仲裁永远返回 `accept`」，定级 P0。

**复核结论**：P0 定级正确，但现状描述需精确化。逐条核查 `arbitrator.py` 三条规则在 plan-gen 缺峰值字段（`max_level`/`max_discharge`）时的存活情况：

| 规则 | 位置 | 依赖字段 | plan-gen 输出该字段？ | 失效时行为 | 存活判定 |
|------|------|----------|----------------------|-----------|----------|
| **Rule 1** 方案水位 > 仿真水位 → adjust | `:69-76` | `plan_level`、`sim_level` | plan: ❌ / sim: ✅ | `plan_level` 为 None → 条件短路，不触发 | **失效**（交叉校验维度） |
| **Rule 2** 下泄 > 安全泄量 → reject | `:79-86` | `plan_discharge` | plan: ❌ | `plan_discharge` 为 None → 条件短路，不触发 | **失效**（下泄否决维度，零替补） |
| **Rule 1b** 仿真超汛限 → 风险提示 | `:88-95` | `sim_level`、`flood_limit` | sim: ✅ / flood_limit: 运行时传入 | `sim_level > flood_limit` 时仅 `issues.append` + 设 `suggestion`，**不改 `decision`、不改 `passed`** | **存活，但非阻断告警** |

**关键证据（代码注释原文）**：
```python
# 规则1b: 仿真结果自身是否超汛限
# 超汛限是风险提示：记录 issue + suggestion，不否决（passed 不变）  ← 代码注释原文
if flood_limit is not None and sim_level is not None and sim_level > flood_limit:
    res.issues.append(...)           # 只追加一条提示
    res.suggestion = "..."           # 只给建议
    # 注意：没有改 res.decision，没有改 res.passed
```

**精确现状**：
1. **两条拦截规则（交叉校验 Rule 1 + 下泄否决 Rule 2）失效**——plan-gen 不输出 `max_level`/`max_discharge`，两个条件均短路为 False。
2. **下泄维度零覆盖**：Rule 2 是唯一对"下泄超安全泄量"的拦截，它死掉后没有任何替补。一个"水位安全但下泄超安全泄量"的危险方案会一路 `accept`，**连告警都没有**（Rule 1b 只看 `sim_level` 超汛限，不看泄量）。
3. **仅 Rule 1b 非阻断超汛限告警存活**：它不改 `decision`（仍 `accept`）、不改 `passed`（仍 `True`），是告警而非守卫。但原断言"仲裁永远返回 accept"对 `decision` 字段是**字面成立**的——即便仿真超汛限，`decision` 也只是停留在 `accept`（Rule 1b 不改它），唯一变 `adjust`/`reject` 的路径（Rule 1/2）已死。

**为什么仍是 P0**：在一个泄洪调度系统里，"下泄超安全泄量也不会被否决（Rule 2 死）"+"方案水位高于仿真也不修正（Rule 1 死）"= **两条安全拦截规则同时失效**。Rule 1b 的非阻断告警不构成有效防线——它不拦截、不否决，运维若没盯着 issues 列表就看不见。这是 P0 级安全漏洞。

**修订建议**：
- **保留 P0-3 的 P0 定级**。
- 现状描述改为：「两条拦截规则（交叉校验 Rule 1 + 下泄否决 Rule 2）因 plan-gen 缺 `max_level`/`max_discharge` 而失效；下泄维度零存活覆盖；仅剩 Rule 1b 非阻断超汛限告警（不改 decision/passed，不构成拦截）。`decision` 字段对所有危险方案恒为 `accept`。」
- 这比原文档"仲裁永远 accept"（漏说 Rule 1b 告警存活）和复核初稿"退化为单边守卫"（把告警当守卫，高估保护力）**双方的原措辞都更准**。
- 第八节「推荐执行顺序」第 4 步保持原优先级（仲裁闭环仍是高杠杆项）。

#### 10.3.2 【自相矛盾】P0-1 的 early-warning 归类

**文档内部矛盾**：
- P0-1 表格把 `early-warning/scripts/query_early_warning.py` 列为「全部 16 个查询零过滤」。
- 但同条目【需决策 `ew_info_message`】段又说 `ew_info_message` 默认保持 `filter:False`（告警跨租户）。

**问题**：若 early-warning 主要查 `ew_info_message`（filters.py 已标 filter:False），则它不应被列入 P0 漏过滤名单；若它也查 `st_rsvr_r`/`st_pptn_r`（需过滤），则需厘清具体函数。

**修订建议**：核查 early-warning 16 个查询函数实际命中的表集合，按表逐一标注「需过滤/合理不过滤」，修正 P0-1 表格中 early-warning 一行的范围描述。

#### 10.3.3 【行号/逻辑偏差】P1-2 scene_router

**文档断言**：`scene_router.py:82-86` DAILY_STRONG 吞掉大坝诊断(B)。

**实际核查**（`scene_router.py:75-98`）：路由顺序为 EMERGENCY_STRONG→D，DAILY_STRONG→C，再走 keyword 匹配。方向对，但描述不精确：实际是 DAILY_STRONG **优先于** keyword 匹配，把"渗压异常"这类本应走 B 关键词的信号先截到 C。修复建议（DAILY_STRONG 增加 B 强词排除）合理，但行号 `:91` 子串误匹配(P2-16)与 `:82-86` 的 DAILY_STRONG 截断是**两个独立问题**，文档未明确区分。

**修订建议**：P1-2 与 P2-16 合并描述为「scene_router 关键词匹配的两个独立缺陷」，分别给出修复点。

#### 10.3.4 【import 完整性未核查】arbitrator.py 的 `asdict`

orchestrator `:349` `return asdict(result)` 依赖 `from dataclasses import asdict`。文档完全没核查 arbitrator.py 的 import 完整性。若漏了 `asdict`，场景 A/D 仲裁会 AttributeError。（实测确认 arbitrator.py 顶部有 `from dataclasses import dataclass, asdict`，此条**不是 bug**，但文档应记录已核查。）

### 10.4 文档漏掉的问题（新增 5 条）

#### 【漏项 A】`lib/paths.py:127` `get_reservoir_dir` 硬编码 `'sancha'`

```python
name = name or os.getenv('SRM_RESERVOIR_NAME', 'sancha')
```

违反「业务代码禁止硬编码水库身份」铁律。应改用 `tenant.DEFAULT_RESERVOIR_NAME` 常量，与 `tenant.py:26` 保持单一真相源。文档 P2-11 提到了 profile 不对称，但没抓到这个**硬编码回退点**。

**定级**：P2（改进，与 P2-11 合并）。

#### 【漏项 B】`lib/filters.py:16` 相对导入与裸导入风格不兼容

filters.py 使用包内相对导入 `from .tenant import current_tenant_id`，这要求 `lib/` 被当作 Python package（有 `__init__.py`）。但项目的标准导入片段用的是 `sys.path.insert(0, .../lib)` + `from db import ...`（**裸名导入**，非包导入）。

两种导入风格混用会导致：
- 若调用方 `from lib.filters import ...`（包导入）→ filters.py 内部的 `from .tenant` 成立。
- 若调用方 `sys.path.insert(.../lib); from filters import ...`（裸导入）→ filters.py 内部的 `from .tenant` **报 ImportError**。

文档 P1-13 提到了 `from db` vs `from lib.db` 的不统一，但**没指出 filters.py 的相对导入在裸导入模式下会直接崩**这个更严重的问题。

**定级**：P1（正确性，影响 filters 助手可用性）。

#### 【漏项 C】`hermes_diagnose_runner.py` 的 `DB_CONFIG` 缺 `charset`

对比 `lib/db.py:51` 有 `'charset': 'utf8mb4'`，而 `hermes_diagnose_runner.py:29-35` 的 `DB_CONFIG` **没有 charset**——中文表名/字段（如"渗压""位移"）查询会出现乱码或编码错误。文档 P0-4 只点了"硬编码密码"和"绕过 lib/db.py"，**漏了这个更隐蔽的 charset 缺失问题**。

**定级**：P1（正确性，中文数据读取必出错）。

#### 【漏项 D】`test_skills.py --list` 实际注册数未实测

文档 P1-15 说「`--list` 至少应覆盖全部 6 skill」，但没核查 `test_skills.py` 是否真的只注册了 3 个。这是一个**可一键验证却没验证**的断言，降低了可信度。

**修订建议**：在「九、整体验收门」中加一步 `python3 test_skills.py --list` 的实测断言，把"应该"变成"实测"。

#### 【漏项 E】第九节验收门第 2 条 grep 守卫漏网 JOIN 表

验收命令：
```bash
grep -rnE "FROM (st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)" \
  --include=*.py early-warning/ plan-generation/ simulation/ diagnosis-verification/ supervisor/
```

只 grep `FROM (表名)`，但 **JOIN 子句里的表名不会被这个正则匹配**——JOIN 表的 tenant 过滤同样易漏，验收脚本没覆盖。

**修订建议**：正则扩展为 `(FROM|JOIN)\s+(st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)`，覆盖 JOIN 形态。

### 10.5 结构与方法论评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **可实施性** | 5/5 | 几乎每条都带文件:行号、修复方法、验收命令，Agent 可直接认领 |
| **严重度分级** | 4/5 | P0/P1/P2/P3 分层清晰，但 P0-3 误判（见 10.3.1） |
| **依赖排序** | 5/5 | 「先 P0-2 根因再 P0-1 批量」「先前置验证门」的依赖链正确，避免了补错 filter |
| **验收闭环** | 4/5 | 第九节验收门设计好，但第 2 条 grep 守卫漏网 JOIN 表（见 10.4 漏项 E） |
| **前置验证门** | 5/5 | 「零、前置验证门」识别了"补丁让情况更糟"的陷阱，是高水平评审的标志 |
| **精度（行号/字段）** | 3.5/5 | P0-3 的行号和"恒为 False"断言有误；部分字段名需复核 |
| **完整性** | 4/5 | 覆盖面广，但漏了 10.4 的 5 个问题，尤其 charset 缺失和 filters.py 相对导入崩坏 |

### 10.6 修订建议汇总

1. **P0-3 降级为 P1**（见 10.3.1），修正表述为"方案-仿真交叉校验失效，仲裁退化为 simulation 单边守卫"；第八节「推荐执行顺序」第 4 步相应降级。
2. **新增 P1**：`lib/filters.py:16` 相对导入 `from .tenant` 与项目裸导入风格不兼容，裸导入下会崩（见 10.4 漏项 B）。
3. **新增 P1**：`hermes_diagnose_runner.py` 的 `DB_CONFIG` 缺 `charset: 'utf8mb4'`，中文查询会乱码（见 10.4 漏项 C）。
4. **修正 P0-1**：厘清 early-warning 16 个查询函数实际命中的表集合，按表逐一标注「需过滤/合理不过滤」，解决与【需决策 ew_info_message】段的内部矛盾（见 10.3.2）。
5. **新增 P2**：`lib/paths.py:127` `get_reservoir_dir` 硬编码 `'sancha'` 回退，应改用 `tenant.DEFAULT_RESERVOIR_NAME`（见 10.4 漏项 A，与 P2-11 合并）。
6. **修正第九节验收门**：
   - 第 2 条 grep 守卫正则扩展为 `(FROM\|JOIN)\s+(...)`，覆盖 JOIN 表（见 10.4 漏项 E）。
   - 新增一步 `python3 test_skills.py --list` 的实测断言（见 10.4 漏项 D）。
7. **P1-2 与 P2-16 合并**描述为「scene_router 关键词匹配的两个独立缺陷」，分别给出修复点（见 10.3.3）。
8. **记录已核查**：arbitrator.py 顶部 `from dataclasses import asdict` 存在，P0-3 依赖的 `asdict` 调用不会 AttributeError（见 10.3.4）。

---

*复核来源：2026-08-10 对本文档的逐条代码对照核查（lib/ 全部模块 + supervisor 3 脚本 + plan-gen/diagnosis 关键脚本 + paths.sh）。所有 10.4 漏项均经实测确认。*
