# SmartTwinRes-skills 评审修复实施方案（2026-08-10）

> **配套文档**：`docs/skill-deep-review-2026-08-10.md`（评审清单 + 第十节复核结论）。本方案是它的**实施视图**——把评审与复核的结论（含对 P0-3 的就地裁决、对 5 个漏项的吸收）拆成 9 个有序阶段，每项给位置、改动、代码片段、验收。
>
> **裁决摘要**（来自对第十节复核的评估）：
> - 接受复核 10 条中的 **9 条**；P0-3 **保留 P0 但改精确措辞**（复核建议降 P1，理由是 `arbitrator.py:88-95` 的 simulation 侧"守卫"仍生效——但该段是**非阻断告警**，`decision` 仍为 `accept`，且下泄维度零存活覆盖，故不降级）。
> - **漏项 B（filters.py 相对导入）必须最先修**：它卡住了 P0-1 推荐的"路由到助手"路径——先做 Phase 1，P0-1 才走得通。
>
> **执行原则**：每阶段收尾跑该阶段验收门；P0 全部清零前不动 P2/P3。每阶段可独立开 PR。提交规范 `fix(scope): 中文说明`，Co-Authored-By 收尾。

---

## Phase 0 — 前置验证门（桃曲坡 tenant_id 核验）

**为什么最先**：若桃曲坡独立库的 `tenant_id` 列全 `NULL`，批量加 `AND tenant_id=20` 会**静默返回空集**（比报错更危险）。必须先确认有值。

**实施**：在桃曲坡库（`SRM_TENANT_ID=20`）跑只读核验：
```sql
SELECT tenant_id, COUNT(*) FROM att_res_flse_lim       GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) FROM st_rsvr_r              GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) FROM srm_flood_history_base  GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) FROM model_result_files      GROUP BY tenant_id;
```

**分支决策**：
| 结果 | 动作 |
|------|------|
| `20` 有行数 | ✅ 直接进 Phase 1/2 |
| 仅 `NULL` | 先回填 `UPDATE <表> SET tenant_id=20 WHERE tenant_id IS NULL;`（需 DBA 确认无副作用）再继续 |
| 列不存在 | live schema 已确认列都在，排除（若真缺失则 ALTER TABLE 补列 + 回填） |

**验收**：核验结果记录到本文件 Phase 0 下方（或 PR 描述），确认 `20` 有数据。

---

## Phase 1 — 导入基础设施统一（解锁 P0-1）

**目标**：解决「漏项 B」——`lib/filters.py:16` 的包内相对导入与全仓库裸导入风格不兼容，使 filters 助手在两种导入模式下都可用。**此阶段不做业务逻辑改动，只通导入。**

### 1.1　filters.py 兼容双导入模式
**位置**：`lib/filters.py:16`
```python
# 现状（仅包导入可用）：
from .tenant import current_tenant_id

# 改为（兼容裸导入 sys.path 含 .../lib 与包导入 from lib.filters 两种）：
try:
    from .tenant import current_tenant_id      # 包导入：from lib.filters import ...
except ImportError:
    from tenant import current_tenant_id        # 裸导入：sys.path 含 .../lib
```

### 1.2　统一标准导入片段（吸收 P1-13）
**位置**：`shared/db-connection.md:36-38`、本仓库各 `SKILL.md` 的「标准导入片段」段
- 现状矛盾：片段写 `from db import`，现网脚本普遍 `from lib.db import`。
- **裁决**：以**裸导入**为唯一标准（`sys.path.insert(0, .../lib)` + `from db import` / `from tenant import`），因为 Hermes 暂存脚本里 `__file__` 不可靠、`lib` 包路径不可靠。统一 `shared/db-connection.md` 与所有 SKILL.md 片段为：

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query, execute_query_list, unpack
from tenant import resolve_tenant
```

**验收**：
```bash
# 裸导入下 filters 不再崩
SRM_SKILLS_ROOT=$(pwd) python3 -c "
import sys; sys.path.insert(0, '$PWD/lib')
import filters; print(filters.apply_table_filters('SELECT * FROM st_rsvr_r', 'st_rsvr_r'))
"
# 包导入下也成立
python3 -c "from lib.filters import apply_table_filters; print('pkg OK')"
```

---

## Phase 2 — 租户隔离根治（P0-2 根因 → P0-1 批量）

**依赖**：Phase 0 通过、Phase 1 完成（filters 助手可用）。

### 2.1　修根因：filters.py 规则表误标（P0-2）
**位置**：`lib/filters.py:35`（TENANT_ID_FILTER_TABLES）、`:49`（DELETED_FILTER_TABLES）
```python
# TENANT_ID_FILTER_TABLES
'att_res_flse_lim': {'filter': True},   # False→True（live DB 确认有 tenant_id）
# 同步核查并修正：att_res_stag_cap_disc / att_res_discharge_curve 等曲线表
# DELETED_FILTER_TABLES：确认 att_res_flse_lim 是否有 deleted 列；有则 True，无则保留 False 并注释
```
**同步**：`forecasting/references/table-schema.md:39`（及 plan-generation/simulation 同名）标注"有 tenant_id"，顶部加"**以 live DB `DESCRIBE` 为唯一真相源**"。

### 2.2　批量补租户过滤（P0-1，按复核修正后的精确范围）

> ⚠️ **范围已据第十节复核 10.3.2 修正**：early-warning 不是"16 条全漏"。实测其 16 个查询中 ~11 条命中 `ew_info_message`（`filters.py:30` 有意 `filter:False`，告警跨租户），真正需补的只有 **2 条**（`st_rsvr_r:161`、`st_pptn_r:172`）。

| 文件 | 精确修复范围 | 改法 |
|------|------------|------|
| `early-warning/scripts/query_early_warning.py` | **仅 `:161` st_rsvr_r、`:172` st_pptn_r** | 走 `apply_table_filters` 助手；其余 ew_info_message/weather_warn 保持不过滤 |
| `diagnosis-verification/scripts/check_data_quality.py` | `check_water_level`/`check_rainfall_forecast`/`check_alerts` 中命中 `st_rsvr_r`/`st_pptn_r`/`srm_flood_history_base` 的查询 | 补 `AND tenant_id=%s` + `resolve_tenant()`；`f_rnfl_h` 经 forecasting 确认无 tenant 列可豁免 |
| `plan-generation/scripts/query_plan_analysis.py` | **9/9 查询**（脚本未 import tenant） | 文件头加 `from tenant import resolve_tenant`；每条 WHERE 补过滤 |
| `plan-generation/scripts/query_plan_data.py` | `query_flood_limit`/`query_historical_plans`/`query_similar_plans`/`query_scenarios`/`query_recent_rainfall`（10/15 漏） | 同上；汛限表依赖 2.1 修对的规则 |
| `simulation/scripts/query_simulation_data.py` | 5 个 `srm_flood_history_*`（仅 flood_id）+ `query_similar_floods`/`query_scenarios`/`query_recent_rainfall` | `AND tenant_id=%s` 与 flood_id 并列 |
| `supervisor/scripts/inspection_check.py:43,48` | `eq_equip_base` 设备总数/类型分布 | 确认该表有 tenant_id 则补；无则输出标注"跨租户全量" |

**推荐改法（根治）**：能走 `lib/filters.py` 助手的优先走助手（`apply_table_filters(sql, table, tenant_id)` 或 `generate_where_clause(table, extra_conditions, tenant_id)`），规则集中一处。不便改造的查询手工补。

**【需产品决策】`ew_info_message`**：`filters.py:30` 标 `filter:False`（"告警跨租户"）。**默认保持不过滤**；若产品要求按库隔离，再改规则表 + 同步 early-warning。

### 2.3　补租户隔离回归测试（P3-5 提前到此，防回归）
新增 `tests/test_tenant_isolation.py`：mock 双 tenant（18/20）数据，对每个修复的查询断言"只回本租户行"。
```python
# 骨架：对每个 query 函数，注入 18/20 各 N 行，断言结果只含当前 tenant
def test_plan_query_flood_limit_isolated(monkeypatch):
    monkeypatch.setenv('SRM_TENANT_ID', '20')
    # mock execute_query_list 返回含 18/20 两行
    rows = query_flood_limit()
    assert all(r['tenant_id'] == 20 for r in rows), '串库！'
```

**验收**：
```bash
python3 -m unittest discover tests
# 关键表查询都带 tenant_id（FROM 或 JOIN）
grep -rnE "(FROM|JOIN)\s+(st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)" \
  --include=*.py early-warning/ plan-generation/ simulation/ diagnosis-verification/ supervisor/
# 抽查命中行上下文确认 WHERE 含 tenant_id 或调用 apply_table_filters
```

---

## Phase 3 — 仲裁安全闭环（P0-3 保留 P0 + 精确措辞 + P1-1 契约）

**裁决说明（写入 PR 描述）**：复核建议降 P1，理由"`arbitrator.py:88-95` simulation 侧守卫仍生效"。**驳回降级**：该段是**非阻断告警**——代码注释原文"不否决（passed 不变）"，`decision` 仍 `accept`。且 **Rule 2（下泄>安全泄量→reject，:78-86）依赖 `plan_discharge`，plan-gen 不输出 → 完全死掉，下泄维度零存活覆盖**。泄洪系统里"下泄超安全泄量也不否决"是 P0。**仅接受措辞修正**。

### 3.1　plan-gen full_context 补峰值字段（P0-3 方案 A）
**位置**：`plan-generation/scripts/query_plan_data.py:337-351`
```python
def query_full_context(hours=48):
    scenarios = unpack(query_scenarios())
    cur = unpack(query_current_water_level())
    # 从 scenarios / current 提取峰值，与 simulation M4 契约对齐
    levels = [s.get("max_level") or s.get("highest_level")
              for s in scenarios if isinstance(s, dict)]
    discharges = [s.get("max_discharge") or s.get("discharge")
                  for s in scenarios if isinstance(s, dict)]
    return {
        'current_water_level': cur,
        'flood_limit': query_flood_limit(),
        'config': query_config(),
        'historical_plans': unpack(query_historical_plans(10)),
        'historical_floods': unpack(query_historical_floods(10)),
        'scenarios': scenarios,
        'recent_rainfall': unpack(query_recent_rainfall(24)),
        'water_level_curve': unpack(query_water_level_curve()),
        'discharge_curve': unpack(query_discharge_curve()),
        # ↓↓↓ 新增：仲裁消费的显式峰值键
        'max_level': max(levels) if levels else None,
        'max_discharge': max(discharges) if discharges else None,
    }
```
> 若 `scenarios` 不含峰值，则改方案 B：在 `orchestrator.py` 仿 `_extract_sim_peaks` 加 plan 峰值提取（`orchestrator.py:339-344` 已有 `plan.get("max_level") or plan.get("highest_level") or plan.get("max_water_level")` 回退链，补上数据源即可）。

### 3.2　统一 full_context 契约（P1-1）
**位置**：`forecasting/.../query_forecast_data.py:184-207`、`simulation/.../query_simulation_data.py:41-76`、`plan-generation/.../query_plan_data.py:86-120`
- 现状：`flood_limit` 在 forecasting=dict、plan/simulation=list；`current_water_level` 数组 vs 字段。
- **目标**：三 skill 关键字段统一为**平铺标量** + `*_source` 辅助字段。例：
  ```python
  'flood_limit': 786.8, 'flood_limit_source': 'att_res_flse_lim',
  'current_water_level': 785.2, 'current_water_level_source': 'st_rsvr_r@stcd=3',
  ```
- 或在 supervisor 侧写显式适配器 + shape 断言（`assert isinstance(fc.get('flood_limit'), (int,float))`）。

### 3.3　补真实下游契约测试（关键——别再被假数据骗）
**现状**：supervisor 测试用 `_seed_stage` 直接注入 `{"max_level":786.95}`，绕过真实 plan-gen 输出，掩盖了 P0-3。
**新增** `tests/integration/test_arbitration_contract.py`：用 `query_full_context()` **实际返回值**（mock DB 返回结构化数据）喂 `arbitrate_plan_vs_simulation`，断言：
- 危险水位（plan_level > flood_limit）→ `decision in ('adjust','reject')`，**非 `accept`**
- 下泄超安全泄量（plan_discharge > safe_discharge）→ `decision == 'reject'`

**验收**：
```bash
python3 -m unittest tests.integration.test_arbitration_contract
# 断言：危险方案不再 accept
```

---

## Phase 4 — 凭据与连接安全（P0-4 + 漏项 C charset + P1-11 锁）

### 4.1　清硬编码密码 + 改走 lib/db.py（P0-4，吸收漏项 C charset）
**位置**：`diagnosis-verification/scripts/hermes_diagnose_runner.py:29-35`（DB_CONFIG）、`:144-149`（pymysql.connect）、`early-warning/SKILL.md:52`（mysql -p 示例）
```python
# 删除本地 DB_CONFIG（含 '123456aA.' 默认密码 + 缺 charset），改：
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))
from db import execute_query_list, get_connection   # charset/超时/池化由 lib/db.py 统一
# 原 check_database() 的 pymysql.connect(**DB_CONFIG) → get_connection()
```
- `early-warning/SKILL.md:52`：`-p"$SRM_DB_PASSWORD"`（与 forecasting 等 5 个 SKILL.md 一致）。
- **漏项 C 自动消解**：改走 `lib/db.py` 后 `charset='utf8mb4'`（`db.py:51`）自动生效，中文查询不再乱码。

### 4.2　连接池加锁（P1-11）
**位置**：`lib/db.py:59-91`
```python
import threading
_pool = None
_pool_lock = threading.Lock()

def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:                        # 双重检查锁定
        if _pool is not None:
            return _pool
        try:
            from dbutils.pooled_db import PooledDB
            _pool = PooledDB(creator=pymysql, maxconnections=5,
                             **DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        except ImportError:
            _pool = 'single'
        return _pool
```

### 4.3　修正文档死链（P1-12）
**位置**：`lib/db.py:11,36`（含 `_require_env` 用户可见错误提示）、`forecasting/scripts/query_utils.py:8`、`plan-generation/scripts/query_utils.py:8`、`shared/db-connection.md:75`
- `docs/db-credential-config.md` → `shared/db-connection.md`（根目录该文件不存在）。

**验收**：
```bash
grep -rnE "123456aA\.|db-credential-config" --include=*.py --include=*.md .   # 应无业务命中
python3 -c "import threading, sys; sys.path.insert(0,'lib'); import db; db._get_pool(); print('pool lock OK')"
```

---

## Phase 5 — 基础设施 P0/P1 散项

| # | 位置 | 改动 |
|---|------|------|
| P0-5 | `lib/paths.sh:11` | `export SKILLS_DIR="$PROJECT_ROOT"`（删 `/skills`） |
| 漏项 A | `lib/paths.py:127` | `name = name or os.getenv('SRM_RESERVOIR_NAME', DEFAULT_RESERVOIR_NAME)`（从 `tenant` 导入常量，单一真相源） |
| P1-2 | `supervisor/scripts/scene_router.py:82-86` | DAILY_STRONG 检查增加 B 强词排除（渗压/渗流/位移/裂缝/扬压力/沉降），或改"仅当无 B/D 命中才归 C"。**与 P2-16（:91 子串误匹配）是两个独立缺陷，分别修**（吸收 10.3.3） |
| P1-3 | `supervisor/scripts/orchestrator.py:596` vs `supervisor_state.py:511,163,340` | `cmd_status` choices 加 `'error'`；queue/replay 查询纳入 `'error'`；或 orchestrator 改用 `'aborted'` 语义 |
| P1-4 | `supervisor/scripts/orchestrator.py:305-309` | stages 查询加 `AND status='ok'`（防消费 error 阶段脏数据） |
| P1-5 | `supervisor/scripts/orchestrator.py:67-69` | 场景 A step2 调 check_data_quality.py 补 `--json`（与场景 B step1 一致） |
| P1-6 | `supervisor/demo.sh:42` | timeout 180s → ≥480s（或 per-stage 降到 ~20s） |
| 10.3.4 | `supervisor/scripts/arbitrator.py:22` | 已核查 `from dataclasses import asdict` 存在——在 SKILL.md/PR 记录"已验证 asdict 非缺陷" |

**验收**：
```bash
source lib/paths.sh && test -d "$FORECASTING_DIR" && echo "paths.sh OK"
python3 -c "from lib.paths import get_reservoir_dir; import os; os.environ.pop('SRM_RESERVOIR_NAME',None); print(get_reservoir_dir())"  # 不再硬编码 'sancha' 字面量
python3 -m unittest discover tests
```

---

## Phase 6 — 模型物理正确性

| # | 位置 | 改动 |
|---|------|------|
| P1-7 | `plan-generation/models/dispatch_model.py:269-275`、`flood_routing.py:202-208` | DEFAULT_DC_CURVE 改单调递增：核实 `(462.0,99),(462.5,94),(463.0,100)` 中 462.5 应≈96-97 或删点；插值入口加断言 `assert all(curve[i][1] <= curve[i+1][1] for i in range(len(curve)-1))` |
| P1-8 | `simulation/models/simulation_service.py`（20+ 处 459.18/462.88/95.1/192） | service 启动读 reservoir profile / model_config；默认值改 `None`，缺失 **fail-loud**（报错而非套三岔）；强制必传或 env 驱动 |
| P2-1 | `plan-generation/models/xaj_model.py:134,140` | 全产流判据 `PE+A>=1` → `PE+A>=WMM`（=WM*(1+B)）；:140 `WM*pow`→`WMM*pow`。对照《水文预报》公式 + 解析解单测 |
| P2-2 | `flood_routing.py:134-139` | 超限软约束别丢水体：超额转 `extra_outflow` 或记 `spill_volume` |
| P2-3 | `xaj_model.py:285-287,316-317` | 去全局可变实例，改 per-request 实例化或 `threading.local()`（防 Flask threaded 并发覆写 watershed_area） |
| P2-4 | `dispatch_model.py:19` | 删 `from scipy.optimize import`（死 import，实为规则法） |
| P2-5 | `flood_routing.py:143-144` | O(n²) 累加 → `np.cumsum` / running sum |
| P2-17 | `xaj_model.py:145-147` | 补 WU→WL→DW 级联充填 + 算例验证 |

**验收**：新增模型单测（单调性断言、XAJ 解析解对照、水量平衡守恒检查 `Σinflow ≈ Σoutflow ± Δstorage`）。

---

## Phase 7 — 文档与死代码清理

- **P1-9** `early-warning/SKILL.md`（评分 2/5，最差）：删 `:144-169` 不存在的 `/opt/git/hermes-agent/...` 路径与 `query_multi`/`close_all` API，换标准导入片段；`:128-133` SQL 占位 `#{}`→`%s`；`:16` `POWERELF_DB_*`→`SRM_DB_*`；`:52` 密码见 Phase 4。
- **P1-10** `plan-generation/SKILL.md`：`:122` 补闭合 ```；`:180` "已按租户隔离,无需过滤"→"灵活路径自定义 SQL **必须**补 `tenant_id=%s`"。
- **P1-14** 删 `forecasting/tmp_query_water.py`（死脚本：直连、硬编码 stcd、无 tenant、DESCRIBE）。
- **P1-15** `test_skills.py:62-84` SKILLS 表补 early-warning/diagnosis-verification/supervisor（3→6）。
- **P1-16** `DB-CONFIG-STANDARD.md` 适配清单补 diagnosis/supervisor；并按 P2-9 与 `shared/db-connection.md` 合并为单一真相源。
- **P2-6** `shared/common-schema/` 补 `st_stbprp_b.md`/`st_rvfcch_b.md` 兑现"唯一真相源"，或降级 README 措辞。
- **P2-7** forecasting vs plan-gen `table-schema.md` 量级矛盾，以现网实测统一。
- **P2-8** `supervisor/SKILL.md:150` 引用不存在的 `dag-scenarios.md`/`arbitration.md`，创建或修正。
- **P2-12** 删两份 `query_utils.py` 重复副本（迁唯一消费者 `forecasting/data/generate_forecast_data.py:29` 改 `from lib.db import`）+ `lib/db.py:228` `query_one()` 死代码。
- **P2-13** `MAX_ROWS.truncated` 零消费方：`execute_query_list` 在 `truncated=True` 时 `log.warning`。
- **P2-14** `simulation/autoresearch-simulation/` 229 文件死代码堆归档到 `archive/` 或 .gitignore，保留最新 `results.json`+`CHECKPOINT.md`。
- **P2-19** `simulation/scripts/query_simulation_data.py:21` 去掉 `DB_CONFIG` 导入（仅 import 用到的 query 函数）。
- **P2-20** 各 SKILL.md 结尾"《三岔水库调度规程》"→`${reservoir_profile}调度规程` 占位。

**验收（吸收漏项 D/E，加强验收门）**：
```bash
# 漏项 E：grep 守卫覆盖 JOIN
grep -rnE "(FROM|JOIN)\s+(st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)" \
  --include=*.py early-warning/ plan-generation/ simulation/ diagnosis-verification/ supervisor/
# 漏项 D：实测注册数（把"应该"变"实测"）
python3 test_skills.py --list    # 应列出全部 6 skill
```

---

## Phase 8 — 水库 profile 对齐 + 收尾（P2-10/11/18、P3）

- **P2-10** `reservoirs/sancha/inspection-items.md`、`defect-disposal.md` 是桃曲坡模板复制（标"待三岔核对"）：从三岔正式预案补全，或标 stub + SKILL.md 提示跳过。
- **P2-11** `reservoirs/sancha/identity.md`（48 行）补防洪标准/枢纽建筑物/安全鉴定/启闭设备；`characteristic-levels.md` 补预警阈值/洪峰分级/监测站网。
- **P2-18** `forecasting/data/generate_forecast_data.py:35,1229` 硬编码 `MOCK_TENANT=18` → `resolve_tenant()`。
- **P3-1** `lib/bootstrap.py:19-23` `_KNOWN_ROOTS` 用 `Path(__file__).resolve().parents[1]` 作首选候选。
- **P3-2** `lib/db.py:145,152` `MAX_ROWS` 改函数体内延迟读（`max_rows=None` 默认）。
- **P3-3** `lib/db.py:24-27` `__all__` 去 `_require_env`（或去下划线改 `require_env`）。
- **P3-4** `plan-generation/autoresearch-plan-skill/eval.py:102` 直连改 `from lib.db import get_connection`。
- **P3-7** `.baseline` 加 pre-commit hook 校验不变（或接受约定保护）。
- **P3-8** `orchestrator.py:331` 注释"场景A/D"→"场景A"；裸 `sys.path.insert` 改走 `_ensure_path`。

---

## 总体验收门（全部完成后跑）

```bash
# 1. 单测全绿（无需 DB）
python3 -m unittest discover tests

# 2. 租户隔离：关键表 FROM/JOIN 查询都带 tenant_id
grep -rnE "(FROM|JOIN)\s+(st_rsvr_r|st_pptn_r|att_res_flse_lim|srm_flood_history_base|model_result_files)" \
  --include=*.py early-warning/ plan-generation/ simulation/ diagnosis-verification/ supervisor/

# 3. 零硬编码密码
grep -rnE "123456aA\." --include=*.py --include=*.md .   # 应空

# 4. 仲裁闭环（真实契约，非假数据）
python3 -m unittest tests.integration.test_arbitration_contract

# 5. filters 双导入模式可用
python3 -c "import sys; sys.path.insert(0,'lib'); import filters; print(filters.apply_table_filters('SELECT * FROM st_rsvr_r','st_rsvr_r'))"

# 6. 实测 skill 注册数
python3 test_skills.py --list    # 6 个

# 7. paths.sh 可用
source lib/paths.sh && test -d "$FORECASTING_DIR" && echo OK
```

**完成标志**：P0（Phase 0-5 中所有 P0 项）全部清零且上述 7 条全绿；P1 完成度 ≥ 80%；租户隔离单测 + 真实下游契约测试已入库；每个 Phase 一个 PR，PR 描述引用本方案对应小节。

---

## 阶段依赖图

```
Phase 0 (核验) ──┐
                 ├─→ Phase 1 (导入统一) ──→ Phase 2 (租户隔离)
                 │                              │
                 │                              ↓
                 │                Phase 3 (仲裁闭环, 依赖 P1-1 契约)
                 │
Phase 4 (凭据/锁) ─────────────────────────── 独立，可并行
Phase 5 (基础设施散项) ─────────────────────── 独立，可并行
Phase 6 (模型) ────────────────────────────── 依赖 P1-8 读 profile，建议在 Phase 2 后
Phase 7 (文档/死代码) ─────────────────────── 独立，可并行
Phase 8 (profile/收尾) ───────────────────── 最后
```

**关键路径**：Phase 0 → 1 → 2 → 3（租户隔离 + 仲裁闭环是安全攸关主线）。Phase 4/5/7 可与主线并行开 PR。Phase 6 最好紧跟 Phase 2（常量参数化依赖 profile 与 tenant 解析就绪）。

---

*本方案是对 `docs/skill-deep-review-2026-08-10.md`（含第十节复核）的实施裁决。P0-3 保留 P0、措辞按复核证据修正；9 条复核意见已吸收到对应 Phase。*
