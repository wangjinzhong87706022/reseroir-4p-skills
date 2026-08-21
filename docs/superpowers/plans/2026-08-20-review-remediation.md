# 评审整改实施计划（review-2026-08-19）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭合 docs/review-2026-08-19.md 评审发现的全部红线缺口与一致性问题（S1-S5 / C1-C3 / H1-H4 / T1-T2），并完成三处待提交真修复。

**Architecture:** 全部为存量代码整改，无新功能。共享层改动（lib/db_write.py、lib/filters.py、lib/flood_limit.py）先落库并带单测，5 个 skill 的脚本随后迁移；每任务独立可测、独立提交。测试统一走 `python3 -m unittest discover tests`（CI 同款，CI 环境只装 pyyaml，无 MySQL/pymysql——所有新测试必须 mock DB 层）。

**Tech Stack:** 纯 Python 3（CI 3.11）、pymysql（运行时才有）、unittest + unittest.mock。

**Spec:** `docs/review-2026-08-19.md`（本计划的整改依据；执行者须同时读它）。**注意：该报告经 2026-08-20 复核存在 3 处勘误**——S1 `execute_write` 并非零引用（`forecasting/data/generate_*.py` 共 9 处在用，处置由"直接删"改为"剥离写通道"）；S4 除 `query_rainfall_forecast` 外还有 `query_multi_source_overview` 一处泄漏；S3 建议落档的 `docs/db-config.md` 不存在（改记 `docs/shared-tables.md`）。以本计划为准。

## Global Constraints

（源自项目既有安全纪律，每个任务隐含遵守）

- 只读 DB 原则：skill 脚本仅 SELECT/SHOW/DESCRIBE；写能力仅存在于 `lib/db_write.py`（本计划 Task 4 建立）。
- 参数化 `%s` 占位符，禁止 f-string/format 拼接任何用户值进 SQL。
- 查询必备 WHERE + LIMIT + `%s`；超时不重试。
- pymysql 下 DATE_FORMAT 的 `%m/%d` 字面量必须写 `%%m%%d`。
- 所有 tenant_id 经 `lib/tenant.py` 的 `resolve_tenant()` 取得，禁硬编码 18/20（测试里 env 设 `SRM_TENANT_ID` 是允许的）。
- DB 凭据走 env（SRM_DB_* → POWERELF_DB_*），`_require_env` fail-loud，不得引入新的弱默认。
- 测试命令统一 `python3 -m unittest discover tests -v`；新测试不得依赖真实 DB / pymysql 安装。
- 提交信息用中文 Conventional Commits（`fix(scope):`/`refactor(scope):`/`chore:`/`docs:`）。
- 不新增第三方依赖。

---

### Task 1: 提交三处待提交真修复 + H4（`SUPERVISOR_DIR` 补进 `__all__`）

**Files:**
- Modify: `lib/paths.py`（`__all__`，约 183-199 行）
- Commit（不动内容）: `plan-generation/scripts/query_plan_data.py`、`eval/cases/supervisor.yaml` 的既有未提交 diff

**Interfaces:**
- Consumes: 无
- Produces: 干净的工作树基线（后续任务的 diff 不与存量改动混淆）；`lib.paths.SUPERVISOR_DIR` 可被 `from lib.paths import *` 拿到。

- [ ] **Step 1: 确认当前未提交 diff 就是评审认定的三处**

```bash
git diff --stat
# 预期只有：eval/cases/supervisor.yaml(4行) / lib/paths.py(2行) / plan-generation/scripts/query_plan_data.py(9行)
git diff plan-generation/scripts/query_plan_data.py   # 应看到 DATE_FORMAT(NOW(), '%%m%%d')
```

- [ ] **Step 2: 补 H4 —— `SUPERVISOR_DIR` 加进 `__all__`**

用 Edit 在 `lib/paths.py` 的 `__all__` 列表中，把

```python
__all__ = [
    'PROJECT_ROOT',
```

替换为

```python
__all__ = [
    'PROJECT_ROOT',
    'SUPERVISOR_DIR',
```

- [ ] **Step 3: 全量回归**

Run: `python3 -m unittest discover tests`
Expected: 全部 PASS（0 failures, 0 errors）

- [ ] **Step 4: 分三个逻辑提交（只 add 指定文件，勿卷入未跟踪杂物）**

```bash
git add plan-generation/scripts/query_plan_data.py
git commit -m "fix(plan-generation): DATE_FORMAT 的 %m/%d 补 %% 转义（pymysql 占位符冲突）"

git add lib/paths.py
git commit -m "feat(lib): paths 新增 SUPERVISOR_DIR 与 get_skill_dir 的 supervisor 映射（eval/run.py 需要）"

git add eval/cases/supervisor.yaml
git commit -m "chore(eval): supervisor A 场景 timeout 600→1500 并移出 smoke 子集"
```

---

### Task 2: H3 乱码字节 + H1 三处死导入

**Files:**
- Modify: `supervisor/scripts/supervisor_state.py:444`（U+FFFD 坏字节）
- Modify: `early-warning/scripts/query_early_warning.py:20`、`diagnosis-verification/scripts/check_data_quality.py:26`、`supervisor/scripts/inspection_check.py:33`（删 `, _require_env`）

**Interfaces:**
- Consumes: 无
- Produces: 无符号变化（纯删除/修复）。

- [ ] **Step 1: 修乱码**

用 Edit 把 `supervisor_state.py:444` 的（注意旧串中间是 U+FFFD 替换字符，直接从文件复制旧串）

```python
                        "msg": f"未来预报 {rf_cnt}h �覆盖完整"})
```

替换为

```python
                        "msg": f"未来预报 {rf_cnt}h 覆盖完整"})
```

若 Edit 因坏字节无法精确匹配，改用 Python 修：

```bash
python3 - <<'EOF'
p = 'supervisor/scripts/supervisor_state.py'
s = open(p, encoding='utf-8').read()
assert '�' in s, '未找到替换字符'
open(p, 'w', encoding='utf-8').write(s.replace('�', ''))
EOF
```

- [ ] **Step 2: 验证字节级干净**

Run: `grep -c $'\xef\xbf\xbd' supervisor/scripts/supervisor_state.py; echo "exit=$?"`
Expected: 输出 0 且 `exit=1`（grep 无匹配）

- [ ] **Step 3: 删三处死导入**

每个文件把 `from lib.db import execute_query_list, _require_env  # noqa: E402` 改为 `from lib.db import execute_query_list  # noqa: E402`（三个文件同一形态，`# noqa` 注释保留原样）。

- [ ] **Step 4: 复核零残留 + 全量回归**

```bash
grep -rn "_require_env" --include="*.py" . | grep -v "lib/db.py" | grep -v worktrees
# 预期：无输出
python3 -m py_compile supervisor/scripts/supervisor_state.py \
  early-warning/scripts/query_early_warning.py \
  diagnosis-verification/scripts/check_data_quality.py \
  supervisor/scripts/inspection_check.py
python3 -m unittest discover tests
```

Expected: grep 无输出；py_compile 与 unittest 全部通过。

- [ ] **Step 5: Commit**

```bash
git add supervisor/scripts/supervisor_state.py \
  early-warning/scripts/query_early_warning.py \
  diagnosis-verification/scripts/check_data_quality.py \
  supervisor/scripts/inspection_check.py
git commit -m "chore: 清理三处死导入 _require_env 与 supervisor_state:444 乱码字节（H1/H3）"
```

---

### Task 3: H2 临时脚本清理 + .gitignore 防再生

**Files:**
- Delete: `supervisor/tmp_alarms.py`、`supervisor/tmp_diag_check.py`、`supervisor/tmp_inspect.py`、`diagnosis-verification/scripts/tmp_diag_final.py`、`diagnosis-verification/scripts/tmp_diag_water.py`、`diagnosis-verification/scripts/tmp_diag_water2.py`、`diagnosis-verification/scripts/tmp_diag_water3.py`
- Delete（**需用户确认，见计划开头决策点**）: `diagnosis-verification/scripts/diagnose_water_level_timeout.py`（137 行，历史排障脚本；默认删除）
- Modify: `.gitignore`（无则创建）

**Interfaces:** 无。

- [ ] **Step 1: 确认 7 个 tmp 文件均未被引用**

```bash
grep -rn "tmp_alarms\|tmp_diag_check\|tmp_inspect\|tmp_diag_final\|tmp_diag_water" \
  --include="*.py" --include="*.md" --include="*.yaml" . | grep -v worktrees | grep -v "docs/review-2026-08-19"
# 预期：无输出（评审报告自身的引用除外）
```

- [ ] **Step 2: 删除 7 个 tmp 脚本（未跟踪文件，rm 即可）**

```bash
rm supervisor/tmp_alarms.py supervisor/tmp_diag_check.py supervisor/tmp_inspect.py \
  diagnosis-verification/scripts/tmp_diag_final.py \
  diagnosis-verification/scripts/tmp_diag_water.py \
  diagnosis-verification/scripts/tmp_diag_water2.py \
  diagnosis-verification/scripts/tmp_diag_water3.py
```

- [ ] **Step 3: diagnose_water_level_timeout.py 按用户决策执行**

用户已确认的处置为准（默认：`rm diagnosis-verification/scripts/diagnose_water_level_timeout.py`；若用户选保留，则 `git mv` 式纳入版本管理并改名为非临时名称）。

- [ ] **Step 4: .gitignore 追加规则**

在 `.gitignore`（不存在则创建）末尾追加：

```gitignore
# 评审 H2：临时排障脚本不进版本库（docs/superpowers/plans/2026-08-20-review-remediation.md Task 3）
tmp_*.py
```

- [ ] **Step 5: 验证 git status 干净（tmp 类消失）+ 回归**

```bash
git status --short | grep tmp_ || echo "tmp 已清"
python3 -m unittest discover tests
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore
git add diagnosis-verification/scripts/diagnose_water_level_timeout.py 2>/dev/null || true
git commit -m "chore: 清理 8 个临时排障脚本并加 .gitignore 规则防再生（H2）"
```

（若 Step 3 选择删除且文件未跟踪，本提交只含 .gitignore。）

---

### Task 4: S1 写通道剥离 —— `lib/db_write.py`（勘误后方案）

**Files:**
- Create: `lib/db_write.py`
- Modify: `lib/db.py:265-291`（删 `execute_write` 及其分节注释；若 `lib/db.py` 有 `__all__` 含 `execute_write` 一并移除）
- Modify: `forecasting/data/generate_taoqupo_data.py:36`、`forecasting/data/generate_sancha_data.py:19`（import 拆分）
- Modify: `forecasting/data/generate_taoqupo_data.py:166,268`（mock DELETE 补 tenant，对齐 sancha 孪生实现）

**Interfaces:**
- Consumes: `lib.db.get_connection()`（签名不变）。
- Produces: `lib.db_write.execute_write(sql, params=None) -> int`——全仓唯一写出口，后续任何写需求只能走它。

- [ ] **Step 1: 创建 `lib/db_write.py`**

```python
#!/usr/bin/env python3
"""
db_write.py -- 显式受控的 DB 写通道（INSERT/UPDATE/DELETE）。

本模块是全仓唯一的写能力出口，仅供 forecasting/data/ 造数脚本
（generate_sancha_data.py / generate_taoqupo_data.py）在测试环境灌/清 mock 数据使用。

纪律（与 docs/统一共享层设计-20260807.md 一致）:
    1. 只读 skill 脚本（*/scripts/ 下任何文件）禁止 import 本模块；
       lib.db 保持纯只读（SELECT/SHOW/DESCRIBE）。
    2. 写 SQL 同样必须参数化 %s，禁止 f-string/format 拼接值。
    3. DELETE/UPDATE 的 WHERE 必须同时带 mock 标记与 tenant_id，
       防止误删他库生产行（评审 S1 + 勘误：原 lib.db.execute_write
       由 forecasting/data 两脚本共 9 处调用，2026-08-20 剥离至此）。
"""
from lib.db import get_connection  # 连接层复用：env 解析/池化/超时与只读通道一致

__all__ = ['execute_write']


def execute_write(sql, params=None):
    """
    Execute an INSERT/UPDATE/DELETE statement and return affected rows.

    Args:
        sql: SQL statement（%s 参数化）
        params: Query parameters

    Returns:
        int -- number of affected rows
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            rows = cursor.execute(sql, params)
            conn.commit()
            return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 2: 从 `lib/db.py` 删除写能力**

删除 `lib/db.py` 中如下整段（约 265-291 行，从分节注释到函数末尾）：

```python
# ---------------------------------------------------------------------------
# Utility: Execute non-query (INSERT/UPDATE/DELETE)
# ---------------------------------------------------------------------------

def execute_write(sql, params=None):
    ...（整个函数，269-290 行）...
```

并在文件头部 docstring 的能力清单里（若有"execute_write"字样）同步删除。检查 `grep -n "__all__" lib/db.py`：若 `__all__` 存在且含 `'execute_write'`，移除该项。

- [ ] **Step 3: 两个造数脚本切换 import**

`generate_taoqupo_data.py:36` 把

```python
from lib.db import execute_query, execute_write, get_connection, unpack  # noqa: E402
```

改为

```python
from lib.db import execute_query, get_connection, unpack  # noqa: E402
from lib.db_write import execute_write  # noqa: E402 -- 显式写通道（仅造数）
```

`generate_sancha_data.py:19` 把

```python
from lib.db import execute_query, execute_query_list, execute_write, get_connection, unpack  # noqa: E402
```

改为

```python
from lib.db import execute_query, execute_query_list, get_connection, unpack  # noqa: E402
from lib.db_write import execute_write  # noqa: E402 -- 显式写通道（仅造数）
```

- [ ] **Step 4: 修 taoqupo 两处无 tenant 的 mock DELETE**

`generate_taoqupo_data.py:166` 与 `:268` 把

```python
    execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
```

改为（与 `generate_sancha_data.py:135` 同形）：

```python
    execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK' AND tenant_id=%s", (TENANT,))
```

- [ ] **Step 5: 验证 —— 全仓写出口唯一化**

```bash
grep -rn "execute_write" --include="*.py" . | grep -v worktrees
# 预期仅 4 类行：lib/db_write.py 的 def 与 docstring、
#   generate_taoqupo_data.py / generate_sancha_data.py 的 from lib.db_write import execute_write 与调用
python3 -m py_compile lib/db_write.py forecasting/data/generate_taoqupo_data.py forecasting/data/generate_sancha_data.py
python3 -m unittest discover tests
```

Expected: grep 无 `lib/db.py` 命中；编译与测试全过。

- [ ] **Step 6: Commit**

```bash
git add lib/db_write.py lib/db.py forecasting/data/generate_taoqupo_data.py forecasting/data/generate_sancha_data.py
git commit -m "refactor(lib): 写能力自 lib.db 剥离至 lib/db_write.py 显式受控通道（S1，含 taoqupo mock DELETE 补 tenant）"
```

---

### Task 5: S4 forecasting `f_rnfl_h` 两处查询补 tenant（TDD）

**Files:**
- Modify: `forecasting/scripts/query_forecast_data.py`（:11 头注释、:26 tenant 策略注释、:47 import、:107-125 `query_rainfall_forecast`、:109 分节注释、:366-372 `query_multi_source_overview`）
- Test: `tests/test_tenant_isolation.py`（加 `_FC_SCRIPTS` 路径 + 新测试类）

**Interfaces:**
- Consumes: `lib.tenant.resolve_tenant(explicit: Optional[int]) -> int`。
- Produces: `query_forecast_data.query_rainfall_forecast(hours, limit, tenant_id=None, **_)`、`query_multi_source_overview(tenant_id=None, hours=DEFAULT_HOURS, **_)`——两函数此后 WHERE 含 `tenant_id = %s`。

- [ ] **Step 1: 写失败测试**

`tests/test_tenant_isolation.py` 顶部路径循环把

```python
for _p in (_PLAN_SCRIPTS, _SIM_SCRIPTS, _EW_SCRIPTS):
```

改为

```python
_FC_SCRIPTS = os.path.join(_REPO_ROOT, "forecasting", "scripts")
for _p in (_PLAN_SCRIPTS, _SIM_SCRIPTS, _EW_SCRIPTS, _FC_SCRIPTS):
```

文件末尾（`if __name__` 之前）加：

```python
# ===========================================================================
# forecasting/scripts/query_forecast_data.py —— S4：f_rnfl_h 补 tenant
# ===========================================================================
class TestForecastingTenantIsolation(unittest.TestCase):

    @patch('query_forecast_data.execute_query')
    def test_query_rainfall_forecast_filters_by_tenant(self, mock_eq):
        """query_rainfall_forecast (f_rnfl_h) 应含 tenant_id 过滤（S4）。"""
        from query_forecast_data import query_rainfall_forecast
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eq.return_value = {'data': [], 'count': 0, 'truncated': False}
        query_rainfall_forecast(hours=48)
        sql, params = mock_eq.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)

    @patch('query_forecast_data.execute_query')
    def test_multi_source_overview_hewind_filters_by_tenant(self, mock_eq):
        """multi_source_overview 的 f_rnfl_h 168h 聚合应含 tenant_id 过滤（S4 勘误第二处）。"""
        from query_forecast_data import query_multi_source_overview
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eq.return_value = {'data': [{}], 'count': 1, 'truncated': False}
        query_multi_source_overview()
        seen = []
        for c in mock_eq.call_args_list:
            sql = c[0][0]
            if 'f_rnfl_h' in sql:
                params = c[0][1] if len(c[0]) > 1 else c[1].get('params', ())
                seen.append((sql, params))
        self.assertTrue(seen, "f_rnfl_h 查询未被调用")
        for sql, params in seen:
            self.assertIn('tenant_id', sql)
            self.assertIn(20, params)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_tenant_isolation -v`
Expected: 2 个新测试 FAIL（`AssertionError: 'tenant_id' not found in ...`），其余 PASS。

- [ ] **Step 3: 实现**

`query_forecast_data.py:47` 把

```python
from lib.tenant import current_tenant_id  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)
```

改为

```python
from lib.tenant import current_tenant_id, resolve_tenant  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)
```

`:11` 头注释把 `rainfall_forecast        和风逐时降雨预报(f_rnfl_h,无 tenant)` 改为 `rainfall_forecast        和风逐时降雨预报(f_rnfl_h,tenant 过滤)`。

`:26` 把 `3. tenant 策略:多数表 tenant_id=18;f_rnfl_h/weather_warn/weather_info 无 tenant。` 改为 `3. tenant 策略:多数表 tenant_id=18;weather_warn/weather_info 无 tenant;f_rnfl_h 有 tenant_id(live DESCRIBE,2026-08-10 泄漏修复对齐)。`

`:107-125` 整段替换为：

```python
# ===========================================================================
# 2. rainfall_forecast —— 和风逐时降雨预报
#    源:f_rnfl_h;经 live DESCRIBE 确认有 tenant_id 列(plan-generation 同款修复);
#    deleted=0;窗口 NOW() → NOW()+hours。
# ===========================================================================
def query_rainfall_forecast(hours=DEFAULT_HOURS, limit=DEFAULT_LIMIT, tenant_id=None, **_):
    tid = resolve_tenant(tenant_id)
    sql = (
        "SELECT RN, YMDH, FYMDH, UNITNAME "
        "FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "  AND deleted=0 AND tenant_id = %s "
        "ORDER BY YMDH"
    )
    rows = unpack(execute_query(sql, (hours, tid), max_rows=limit))
    return {
        "source": "f_rnfl_h (和风天气)",
        "hours": hours,
        "count": len(rows),
        "data": rows,
    }
```

`query_multi_source_overview`（:368 起）签名与和风聚合改为（函数其余查询里的 `tenant_id` 一律换用 `tid`）：

```python
def query_multi_source_overview(tenant_id=None, hours=DEFAULT_HOURS, **_):
    tid = resolve_tenant(tenant_id)
    # 和风 168h 总量（f_rnfl_h 有 tenant_id，见 rainfall_forecast 分节注释）
    he = unpack(execute_query(
        "SELECT COUNT(*) AS n, ROUND(SUM(RN),2) AS total_mm, MAX(YMDH) AS latest "
        "FROM f_rnfl_h WHERE YMDH BETWEEN NOW() AND NOW()+INTERVAL 168 HOUR "
        "  AND deleted=0 AND tenant_id=%s", (tid,)))
```

（紧随其后的 `st_pptn_re_forecast` 聚合里 `(tenant_id,)` 改为 `(tid,)`；函数内其他 `tenant_id` 引用同步替换为 `tid`。）

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m unittest tests.test_tenant_isolation -v` 然后 `python3 -m unittest discover tests`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add forecasting/scripts/query_forecast_data.py tests/test_tenant_isolation.py
git commit -m "fix(forecasting): f_rnfl_h 两处查询补 tenant_id 过滤，对齐 live schema 与 plan-generation（S4）"
```

---

### Task 6: S2 `lib/filters.py` tenant 过滤参数化（TDD）

**Files:**
- Modify: `lib/filters.py`（`apply_tenant_filter` :68-130、`generate_where_clause` :252-302、`apply_table_filters` :177-208 组合处）
- Test: `tests/test_tenant_isolation.py`（新测试类）

**Interfaces:**
- Produces（契约变更，当前全仓零调用方，安全）:
  - `apply_tenant_filter(sql, table_name, tenant_id=None) -> tuple[str, tuple]`（返回 `(sql, params)`，params 含 tenant 值）
  - `generate_where_clause(table_name, extra_conditions=None, tenant_id=None) -> tuple[str, list]`
  - `apply_table_filters(...)` 同步改为返回 `(sql, params)` 二元组（读 :177-208 原签名后按同一规则穿参）。

- [ ] **Step 1: 写失败测试**

`tests/test_tenant_isolation.py` 的 `TestFiltersRuleTable` 之后加：

```python
class TestFiltersParametrized(unittest.TestCase):
    """S2：tenant 过滤必须 %s 参数化（返回 (sql, params)），禁 f-string 拼接。"""

    def setUp(self):
        sys.path.insert(0, os.path.join(_REPO_ROOT, 'lib'))
        import filters
        self.filters = filters

    def test_apply_tenant_filter_with_where(self):
        sql, params = self.filters.apply_tenant_filter(
            "SELECT * FROM st_rsvr_r WHERE deleted=0", "st_rsvr_r", tenant_id=18)
        self.assertEqual(params, (18,))
        self.assertIn("tenant_id = %s", sql)
        self.assertNotIn("tenant_id = 18", sql)

    def test_apply_tenant_filter_no_where(self):
        sql, params = self.filters.apply_tenant_filter(
            "SELECT * FROM st_rsvr_r", "st_rsvr_r", tenant_id=20)
        self.assertEqual(params, (20,))
        self.assertIn("tenant_id = %s", sql)

    def test_apply_tenant_filter_skips_unfiltered_table(self):
        sql, params = self.filters.apply_tenant_filter(
            "SELECT * FROM ew_info_message WHERE deleted=0", "ew_info_message", tenant_id=18)
        self.assertEqual(params, ())
        self.assertNotIn("tenant_id", sql)

    def test_apply_tenant_filter_rejects_bad_tenant(self):
        with self.assertRaises(ValueError):
            self.filters.apply_tenant_filter(
                "SELECT * FROM st_rsvr_r", "st_rsvr_r", tenant_id="18 OR 1=1")

    def test_generate_where_clause_parametrized(self):
        clause, params = self.filters.generate_where_clause("st_rsvr_r", tenant_id=18)
        self.assertIn("tenant_id = %s", clause)
        self.assertIn("deleted = 0", clause)
        self.assertEqual(params, [18])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_tenant_isolation.TestFiltersParametrized -v`
Expected: 前 5 个测试 FAIL（返回值还是裸 str，解包即 TypeError/ValueError）。

- [ ] **Step 3: 实现**

先读 `lib/filters.py:60-95`（`apply_tenant_filter` 的签名与 docstring，保持不动）与 `:133-250`（`apply_deleted_filter`/`apply_table_filters`/`validate_table_filter`）。然后：

3a. 在 `apply_tenant_filter` 上方新增私有校验函数（两个公开函数共用）：

```python
def _validate_tenant_id(tid):
    """tenant_id 强制非负整数（%s 参数化前的值校验）。"""
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        raise ValueError(
            f"tenant_id 必须为整数，收到 {tid!r}（类型 {type(tid).__name__}）。"
            f"显式传入请用整数，环境变量 SRM_TENANT_ID 也需为整数。"
        )
    if tid < 0:
        raise ValueError(f"tenant_id 不能为负数，收到 {tid}")
    return tid
```

3b. `apply_tenant_filter` 函数体（:96-130）改为（docstring 的 Returns 段同步改为"tuple[str, tuple] -- (带 tenant 过滤的 SQL, params)"）：

```python
    # 检查是否需要 tenant_id 过滤
    rule = TENANT_ID_FILTER_TABLES.get(base_table, {'filter': False})
    if not rule['filter']:
        return sql, ()

    # 获取 tenant_id 值：显式参数优先，否则从 env 解析（默认回退 18）
    tid = tenant_id if tenant_id is not None else current_tenant_id()
    tid = _validate_tenant_id(tid)

    # 判断 WHERE 子句位置（值一律走 %s 参数，杜绝字符串拼接——评审 S2）
    sql_upper = sql.upper().strip()

    if 'WHERE' in sql_upper:
        # 已有 WHERE 子句 → 追加 AND
        return f"{sql} AND tenant_id = %s", (tid,)

    # 无 WHERE 子句 → 新增 WHERE（避开 GROUP BY / ORDER BY / LIMIT）
    for keyword in ('GROUP BY', 'ORDER BY', 'LIMIT'):
        if keyword in sql_upper:
            insert_pos = sql_upper.index(keyword)
            return f"{sql[:insert_pos]}WHERE tenant_id = %s {sql[insert_pos:]}", (tid,)

    # 无其他关键字 → 直接在末尾添加
    return f"{sql} WHERE tenant_id = %s", (tid,)
```

3c. `generate_where_clause`（:272-302）改为（docstring 的 Returns/Examples 同步改，Example 变为返回 `('WHERE tenant_id = %s AND deleted = 0 AND tm >= NOW() - INTERVAL 24 HOUR', [18])`）：

```python
    base_table = table_name.split()[0].strip()

    conditions = []
    params = []

    # tenant_id 过滤（值走 %s 参数——评审 S2）
    rule = TENANT_ID_FILTER_TABLES.get(base_table, {})
    if rule.get('filter', False):
        tid = tenant_id if tenant_id is not None else current_tenant_id()
        tid = _validate_tenant_id(tid)
        conditions.append("tenant_id = %s")
        params.append(tid)

    # deleted 过滤
    if DELETED_FILTER_TABLES.get(base_table, False):
        conditions.append("deleted = 0")

    # 额外条件
    if extra_conditions:
        conditions.extend(extra_conditions)

    if not conditions:
        return "", []

    return "WHERE " + " AND ".join(conditions), params
```

3d. `apply_table_filters`（:177-206）改为（签名 `-> str` 改 `-> tuple`；docstring 的 Returns 改"tuple[str, tuple] -- (过滤后 SQL, tenant params)"，Examples 的期望值改为 `('SELECT rz, ... WHERE tenant_id = %s AND deleted = 0 ORDER BY tm DESC LIMIT 1', (18,))`）：

```python
    if apply_tenant:
        sql, params = apply_tenant_filter(sql, table_name, tenant_id)
    else:
        params = ()
    if apply_deleted:
        sql = apply_deleted_filter(sql, table_name)
    return sql, params
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归 + 确认零调用方**

```bash
python3 -m unittest tests.test_tenant_isolation -v
python3 -m unittest discover tests
grep -rn "apply_tenant_filter\|generate_where_clause\|apply_table_filters" --include="*.py" . | grep -v worktrees | grep -v "lib/filters.py" | grep -v test_
# 预期：无输出（生产代码零调用方，契约变更是安全的）
```

- [ ] **Step 5: Commit**

```bash
git add lib/filters.py tests/test_tenant_isolation.py
git commit -m "refactor(lib): filters 的 tenant 过滤改 %s 参数化返回 (sql, params)，消除 f-string 拼接（S2）"
```

---

### Task 7: S3 `ew_info_message` 跨租户设计决策落档（文档，无行为变更）

**Files:**
- Modify: `docs/shared-tables.md`（文末追加决策章节）
- Modify（一行指针）: `early-warning/scripts/query_early_warning.py` 头注释、`supervisor/scripts/supervisor_state.py` `cmd_health` 的告警堆积查询处、`diagnosis-verification/scripts/check_data_quality.py` `check_alerts` 的 docstring

**Interfaces:** 无代码接口变化。

**决策（本计划采纳"记录"而非"补过滤"）**：告警由中央引擎写入、行内无水库归属维度；`cmd_health` 是运维探针需全局视角；`lib/filters.py` 规则表自始标注 `filter:False`。三方理由指向"全库可见是有意设计"。代价（A 库高级告警抬高 B 库场景 D 仲裁）按"防洪优先、宁高勿低"接受。

- [ ] **Step 1: `docs/shared-tables.md` 文末追加**

```markdown
---

## ew_info_message：跨租户可见（显式设计决策）

**决策**（2026-08-20，评审 S3 落档）：告警表 `ew_info_message` 在全部 skill 中
不做 tenant_id 过滤，保持全库可见。

**理由**：
1. 告警由中央告警引擎写入，行内无水库归属维度可用；
2. supervisor `cmd_health` 告警堆积探针需要全局视角；
3. `lib/filters.py` 规则表自始标注 `ew_info_message: filter:False`（告警跨租户，不强制）。

**已知影响面（接受）**：
- early-warning 的告警查询与 diagnosis-verification `check_alerts` 会看到
  其他水库的告警；
- supervisor 场景 D 仲裁（`arbitrate_emergency`）消费 `query_high_level` 输出，
  A 库高级告警可能抬高 B 库应急风险判定——按"防洪优先、宁高勿低"原则接受。

**变更条件**：若告警表将来增加水库/租户归属列，须重评本决策并补
`tenant_id = %s` 过滤。
```

- [ ] **Step 2: 三处代码加一行指针注释**

- `early-warning/scripts/query_ew_warning.py` 头部 docstring 的 tenant 策略行（若无则头注释任意合适位置）加：`# ew_info_message 跨租户可见为显式设计决策，见 docs/shared-tables.md`
- `supervisor_state.py` `cmd_health` 的 `# 告警堆积（ew_info_message 未确认 + 高级别）` 注释改为：`# 告警堆积（ew_info_message 未确认 + 高级别；跨租户可见为设计决策，见 docs/shared-tables.md）`
- `check_data_quality.py` `check_alerts` docstring 加同款一句。

- [ ] **Step 3: 回归 + Commit**

```bash
python3 -m unittest discover tests
git add docs/shared-tables.md early-warning/scripts/query_early_warning.py \
  supervisor/scripts/supervisor_state.py diagnosis-verification/scripts/check_data_quality.py
git commit -m "docs(shared-tables): 显式记录 ew_info_message 跨租户可见的设计决策与影响面（S3）"
```

---

### Task 8: S5 simulation `srm_flood_history_result` 防御性 tenant（含 live DESCRIBE 前置）

**Files:**
- Modify（分支 A 时）: `simulation/scripts/query_simulation_data.py:154-200`（`query_flood_result` / `query_flood_result_curve` / `query_flood_inflow` / `query_flood_statistics` 四函数）
- Modify（任一分支）: `docs/shared-tables.md`
- Test（分支 A 时）: `tests/test_tenant_isolation.py`

**Interfaces:**
- Produces（分支 A）: 四函数签名统一为 `def query_flood_xxx(flood_id, tenant_id=None)`，WHERE 增加 `AND tenant_id = %s`。

- [ ] **Step 1: live DESCRIBE 确认列（只读操作）**

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from lib.db import execute_query_list
cols = execute_query_list("DESCRIBE srm_flood_history_result")
print([c['Field'] for c in cols])
EOF
```

- 有 `tenant_id` 列 → 走分支 A；无 → 走分支 B。
- 若本机无凭据（`_require_env` 报错退出），**直接走分支 B**（不得为跑 DESCRIBE 而造弱默认凭据）。

- [ ] **Step 2（分支 A）: 写失败测试**

`tests/test_tenant_isolation.py` 的 `TestSimulationDataTenantIsolation` 类内追加：

```python
    @patch('query_simulation_data.execute_query_list')
    def test_query_flood_result_filters_by_tenant(self, mock_eql):
        """query_flood_result (srm_flood_history_result) 应含防御性 tenant 过滤（S5）。"""
        from query_simulation_data import query_flood_result
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eql.return_value = []
        query_flood_result(flood_id=1)
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)
```

Run: `python3 -m unittest tests.test_tenant_isolation.TestSimulationDataTenantIsolation -v`
Expected: 新测试 FAIL。

- [ ] **Step 3（分支 A）: 实现**

先读 `simulation/scripts/query_simulation_data.py:141-200`。对四个函数应用同一变换（以 `query_flood_result` 为例，其余三个同形）：

```python
def query_flood_result(flood_id, tenant_id=None):
    """查询洪水调度结果（srm_flood_history_result；防御性 tenant 过滤——
    flood_id 虽来自 tenant 过滤过的 base 表，仍防 flood_id 被旁路传入，评审 S5）"""
    tid = resolve_tenant(tenant_id)
    sql = """  # ← 保留原 SELECT 列与 JOIN，只在 WHERE 追加
      ...
      WHERE flood_id = %s AND tenant_id = %s
      ...
    """
    rows = execute_query_list(sql, (flood_id, tid))  # ← 参数顺序与 %s 顺序一致
    ...
```

要点：原 WHERE 里的 `flood_id = %s` 之后追加 `AND tenant_id = %s`；params 元组 `(flood_id, tid)`。四个函数逐一同样处理（curve/inflow/statistics 的 SQL 各自保留原列，仅动 WHERE 与 params）。`resolve_tenant` 已在该文件 import（:23）。

- [ ] **Step 4（分支 A）: 测试通过 + 全量回归**

Run: `python3 -m unittest tests.test_tenant_isolation -v && python3 -m unittest discover tests`
Expected: 全部 PASS。

- [ ] **Step 5（分支 B）: 记录间接隔离**

`docs/shared-tables.md` 追加：

```markdown
---

## srm_flood_history_result：依赖 flood_id 间接隔离

经 live DESCRIBE 确认无 tenant_id 列（2026-08-20，评审 S5）。隔离依赖上游
`query_historical_floods`（`srm_flood_history_base` 按 tenant 过滤）给出的
flood_id；禁止任何调用方从用户输入直接传 flood_id 绕过 base 表。
```

并在四个函数的 docstring 各加一句：`# 无 tenant 列，依赖 base 表 flood_id 间接隔离（docs/shared-tables.md）`

- [ ] **Step 6: Commit（按实际分支二选一）**

```bash
# 分支 A
git add simulation/scripts/query_simulation_data.py tests/test_tenant_isolation.py
git commit -m "fix(simulation): srm_flood_history_result 四查询补防御性 tenant 过滤（S5）"
# 分支 B
git add simulation/scripts/query_simulation_data.py docs/shared-tables.md
git commit -m "docs(simulation): 记录 flood_result 系列依赖 flood_id 间接隔离（S5）"
```

---

### Task 9: C1 `eval/lib/truth.py` 复用 `lib.db` 连接（消弱默认）

**Files:**
- Modify: `eval/lib/truth.py:17-28`（`_connect`）
- Test: `tests/test_eval_truth.py`

**Interfaces:**
- Consumes: `lib.db.get_connection() -> pymysql conn`（DictCursor、env 解析、connect/read 超时、`_require_env` fail-loud）。
- Produces: `_connect(env)` 签名不变（测试接缝保留），实现改为委托 `lib.db`。

- [ ] **Step 1: 写测试（含 CI 无 pymysql 的 skip 守卫）**

`tests/test_eval_truth.py` 的 `TestTruth` 类内追加（文件顶部已有 unittest import）：

```python
    def test_connect_delegates_to_lib_db(self):
        # C1：_connect 应复用 lib.db 连接（同 env 解析/超时/fail-loud），
        # 而非自带 root/空密码弱默认。CI 无 pymysql 时跳过。
        try:
            import pymysql  # noqa: F401
        except ImportError:
            self.skipTest("pymysql 未安装（CI 环境）")
        from unittest.mock import patch
        from eval.lib import truth
        sentinel = object()
        with patch('lib.db.get_connection', return_value=sentinel) as m:
            self.assertIs(truth._connect({}), sentinel)
        m.assert_called_once_with()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_truth -v`
Expected: `test_connect_delegates_to_lib_db` FAIL（当前 `_connect` 自建 pymysql.connect，不调 lib.db）。

- [ ] **Step 3: 实现**

`eval/lib/truth.py:17-28` 整体替换为：

```python
def _connect(env):
    """复用 lib.db 连接：env 解析(SRM_DB_*→POWERELF_DB_*→fail-loud)、
    连接/读取超时、DictCursor 与只读通道完全一致（评审 C1：消除双份连接
    逻辑与 root/空密码弱默认）。保留本函数作为测试接缝。"""
    from lib.db import get_connection  # 延迟导入：CI 无 DB/未装 pymysql 时不必引入
    return get_connection()
```

- [ ] **Step 4: 回归（含既有接缝测试）**

Run: `python3 -m unittest tests.test_eval_truth -v && python3 -m unittest discover tests`
Expected: 全部 PASS（`test_make_query_fn_uses_injected_port` 用 fake 替换 `_connect`，不受影响）。

- [ ] **Step 5: Commit**

```bash
git add eval/lib/truth.py tests/test_eval_truth.py
git commit -m "refactor(eval): truth._connect 复用 lib.db 连接，消除双份配置与 root/空密码弱默认（C1）"
```

---

### Task 10: C2 汛限水位统一 `lib/flood_limit.py`（TDD）

**Files:**
- Create: `lib/flood_limit.py`
- Modify: `plan-generation/scripts/query_plan_data.py:96-131`、`simulation/scripts/query_simulation_data.py:41-76`、`forecasting/scripts/query_forecast_data.py:147-207`
- Test: Create `tests/test_flood_limit.py`；Modify `tests/test_tenant_isolation.py:35-44`（`query_flood_limit` 的 patch 目标）

**Interfaces:**
- Produces: `lib.flood_limit.current_flood_limit(tenant_id=None) -> dict`，归一化返回：
  - `{'status': 'ok', 'flse_lim_stag', 'flood_season_name', 'flood_season_start', 'flood_season_end', 'source'}`（命中汛期行）
  - `{'status': 'fallback', ...同字段, 'flood_season_name': '非汛期', 'source': 'att_res_base'}`（回退正常蓄水位）
  - `{'status': 'missing'}`
- 行为契约（统一后语义，以 forecasting 的最全语义为准）：区间未命中 → 回退"主汛期"行（防洪更保守）→ 再回退 `att_res_base` → missing。跨年汛期不支持（reservoir profile 2026-08-06 确认两库汛期均在同年内），注释说明。

- [ ] **Step 1: 写失败测试**

Create `tests/test_flood_limit.py`：

```python
#!/usr/bin/env python3
"""lib/flood_limit 汛限单一实现测试（C2）——mock DB 层，无真实 DB。"""
import os
import sys
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _season_row(name='主汛期', s='0601', e='1031', stag=786.0):
    return {'flse_lim_stag': stag, 'flood_season_name': name,
            'flood_season_start': s, 'flood_season_end': e}


class TestCurrentFloodLimit(unittest.TestCase):

    @patch('lib.flood_limit.execute_query_list')
    def test_in_season_match(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[_season_row()], []]
        r = fl.current_flood_limit(18)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['flse_lim_stag'], 786.0)
        # tenant 必须参数化传入
        sql, params = mock_eql.call_args_list[0][0]
        self.assertIn('tenant_id = %s', sql)
        self.assertIn(18, params)

    @patch('lib.flood_limit.execute_query_list')
    def test_out_of_season_falls_back_to_main_season(self, mock_eql):
        """区间未命中 → 回退主汛期行（forecasting 语义，防洪更保守）。"""
        import lib.flood_limit as fl
        mock_eql.side_effect = [[_season_row('次汛期', '0601', '0630'),
                                 _season_row('主汛期', '0701', '0930', stag=785.0)], []]
        r = fl.current_flood_limit(20)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['flood_season_name'], '主汛期')
        self.assertEqual(r['flse_lim_stag'], 785.0)

    @patch('lib.flood_limit.execute_query_list')
    def test_no_season_rows_falls_back_to_base(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[], [{'fl_low_lim_lev': 790.0}]]
        r = fl.current_flood_limit(18)
        self.assertEqual(r['status'], 'fallback')
        self.assertEqual(r['flse_lim_stag'], 790.0)
        self.assertEqual(r['flood_season_name'], '非汛期')

    @patch('lib.flood_limit.execute_query_list')
    def test_missing(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[], []]
        self.assertEqual(fl.current_flood_limit(18), {'status': 'missing'})

    def test_cross_year_documented_unsupported(self):
        """跨年汛期不支持——契约写进 docstring，本测试钉住源码里的说明。"""
        import lib.flood_limit as fl
        self.assertIn('跨年', fl.__doc__)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_flood_limit -v`
Expected: `ModuleNotFoundError: No module named 'lib.flood_limit'`。

- [ ] **Step 3: 实现 `lib/flood_limit.py`**

```python
#!/usr/bin/env python3
"""
flood_limit.py -- 汛限水位单一实现（评审 C2 统一）。

此前 plan-generation / simulation / forecasting 三处各自实现
"今天是否在汛期、取对应汛限"，行为细节（回退链、跨年）各异；本模块是唯一权威实现。

行为契约:
    1. att_res_flse_lim 按 MMdd 区间匹配当前汛期行（tenant 过滤，全部 %s 参数化）。
       跨年汛期（如 1101→次年0331）不支持——经 reservoir profile 确认（2026-08-06）
       桃曲坡整体 0601-1031 / 三岔无汛期分段，两库汛期均在同年内；
       接入跨年汛期水库时需补区间判断。
    2. 区间未命中 → 回退"主汛期"行（若存在；防洪更保守）。
    3. 无任何汛期行 → att_res_base.fl_low_lim_lev（deleted=0）作"非汛期"参考。
    4. 都没有 → {'status': 'missing'}；禁止硬编码水库数值。
"""
from datetime import datetime

from lib.db import execute_query_list
from lib.tenant import resolve_tenant

_TODAY_MD = datetime.now().strftime('%m%d')  # 进程内固定（CLI 短生命周期）


def current_flood_limit(tenant_id=None):
    """返回归一化汛限 dict；字段与行为契约见模块 docstring。"""
    tid = resolve_tenant(tenant_id)

    rows = execute_query_list(
        "SELECT flse_lim_stag, flood_season_name, "
        "       flood_season_start, flood_season_end "
        "FROM att_res_flse_lim "
        "WHERE tenant_id = %s "
        "ORDER BY id",
        (tid,),
    )
    today = _TODAY_MD
    in_season = next(
        (r for r in rows
         if r.get('flood_season_start') and r.get('flood_season_end')
         and r['flood_season_start'] <= today <= r['flood_season_end']),
        None,
    )
    if in_season is None:
        in_season = next(
            (r for r in rows if r.get('flood_season_name') == '主汛期'), None)

    if in_season:
        return {
            'status': 'ok',
            'flse_lim_stag': in_season.get('flse_lim_stag'),
            'flood_season_name': in_season.get('flood_season_name'),
            'flood_season_start': in_season.get('flood_season_start'),
            'flood_season_end': in_season.get('flood_season_end'),
            'source': "att_res_flse_lim({})".format(in_season.get('flood_season_name')),
        }

    base = execute_query_list(
        "SELECT fl_low_lim_lev "
        "FROM att_res_base "
        "WHERE fl_low_lim_lev IS NOT NULL AND deleted = 0 AND tenant_id = %s "
        "ORDER BY id "
        "LIMIT 1",
        (tid,),
    )
    if base:
        return {
            'status': 'fallback',
            'flse_lim_stag': base[0].get('fl_low_lim_lev'),
            'flood_season_name': '非汛期',
            'flood_season_start': None,
            'flood_season_end': None,
            'source': 'att_res_base',
        }
    return {'status': 'missing'}
```

- [ ] **Step 4: 跑新测试确认通过**

Run: `python3 -m unittest tests.test_flood_limit -v`
Expected: 5 个测试全 PASS。

- [ ] **Step 5: 三个 skill 迁移为薄包装（保持各自返回形状不变）**

5a. `plan-generation/scripts/query_plan_data.py`：import 区加 `from lib.flood_limit import current_flood_limit`；`query_flood_limit`（:96-131）整函数替换为：

```python
def query_flood_limit(tenant_id=None):
    """查询当前汛限水位（实现统一至 lib.flood_limit.current_flood_limit，评审 C2）"""
    lim = current_flood_limit(tenant_id)
    if lim['status'] == 'missing':
        # 无兜底硬编码值——汛限必须来自数据库。缺失时返回空，由调用方处理。
        return []
    return [{
        'flse_lim_stag': lim['flse_lim_stag'],
        'flood_season_name': lim['flood_season_name'],
        'flood_season_start': lim['flood_season_start'],
        'flood_season_end': lim['flood_season_end'],
    }]
```

5b. `simulation/scripts/query_simulation_data.py`：同样加 import；`query_flood_limit`（:41-76）替换为：

```python
def query_flood_limit(tenant_id=None):
    """查询当前汛限水位（实现统一至 lib.flood_limit.current_flood_limit，评审 C2）"""
    lim = current_flood_limit(tenant_id)
    if lim['status'] == 'missing':
        # 无兜底硬编码值——汛限必须来自数据库。缺失返回空，禁止编造数值。
        return []
    return [{
        'flse_lim_stag': lim['flse_lim_stag'],
        'flood_season_name': lim['flood_season_name'],
        'flood_season_start': lim['flood_season_start'],
        'flood_season_end': lim['flood_season_end'],
    }]
```

5c. `forecasting/scripts/query_forecast_data.py`：加 import；删除 `_pick_in_season_flse_lim`（:152-181）；`query_flood_limit`（:184-207）替换为：

```python
def query_flood_limit(tenant_id=None, **_):
    """汛限水位（实现统一至 lib.flood_limit.current_flood_limit，评审 C2）"""
    lim = current_flood_limit(tenant_id)
    if lim['status'] == 'missing':
        return {"status": "missing",
                "message": "汛限水位既无 att_res_flse_lim 也无 att_res_base 行"}
    if lim['status'] == 'fallback':
        return {"field": "fl_low_lim_lev", "value": lim['flse_lim_stag'],
                "source": "att_res_base (fallback)"}
    return {
        "field": "flse_lim_stag",
        "value": lim['flse_lim_stag'],
        "source": lim['source'],
        "flood_season": lim['flood_season_name'],
        "flood_season_start": lim['flood_season_start'],
        "flood_season_end": lim['flood_season_end'],
    }
```

（`datetime` import 保留——`_now_iso` 仍在用。）

- [ ] **Step 6: 迁移既有测试的 patch 目标**

`tests/test_tenant_isolation.py:35-44` 的 `test_query_flood_limit_filters_by_tenant` 把

```python
    @patch('query_plan_data.execute_query_list')
```

改为

```python
    @patch('lib.flood_limit.execute_query_list')
```

（函数体不变——wrapper 经 lib 层执行，tenant 断言依旧成立。）

- [ ] **Step 7: 全量回归**

Run: `python3 -m unittest discover tests`
Expected: 全部 PASS（含 `tests/test_flood_limit.py` 与迁移后的 tenant 测试）。

- [ ] **Step 8: Commit**

```bash
git add lib/flood_limit.py tests/test_flood_limit.py \
  plan-generation/scripts/query_plan_data.py \
  simulation/scripts/query_simulation_data.py \
  forecasting/scripts/query_forecast_data.py tests/test_tenant_isolation.py
git commit -m "refactor(lib): 三处汛限查询统一为 lib.flood_limit.current_flood_limit（C2，含主汛期回退语义）"
```

---

### Task 11: C3 supervisor 去再导出 + 复用 `lib.paths.ensure_path`

**Files:**
- Modify: `supervisor/scripts/orchestrator.py:34-48`（inline `_ensure_path` + asdict 再导入）、`:184`、`:527`（另两处 `_ensure_path` 调用）
- Modify: `supervisor/scripts/arbitrator.py:24-34`（inline `_ensure_path` 与过时注释）

**Interfaces:**
- Consumes: `lib.paths.ensure_path(*paths)`（supervisor_state.py:395 已在用的同款 helper）。
- Produces: orchestrator 不再从 arbitrator 再导出 `asdict`；两文件的 `_ensure_path` 内联副本删除。

- [ ] **Step 1: orchestrator 顶部替换**

`orchestrator.py:34-48` 把

```python
# 让脚本能被 import：去重插入脚本目录与仓库根，避免 reload/反复 import 造成 sys.path 膨胀。
# 注意：不 import lib.paths——lib 包初始化会触发 lib.db 的模块级凭据检查（无 SRM_DB_* 时退出），
# 而本脚本在测试（无凭据环境）中也会被 import。
def _ensure_path(*paths):
    for p in paths:
        p = os.path.abspath(p)
        if p not in sys.path:
            sys.path.insert(0, p)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ensure_path(os.path.dirname(os.path.abspath(__file__)), _REPO_ROOT)
from supervisor_state import _connect, _state_dir  # noqa: E402
from scene_router import route  # noqa: E402
from arbitrator import (arbitrate_plan_vs_simulation, arbitrate_dam_diagnosis,
                        arbitrate_emergency, arbitrate_risk_levels, asdict)  # noqa: E402
```

替换为（lib.db 已惰性化，旧顾虑失效——supervisor_state.py:395 已直接 import lib.paths 为先例）：

```python
# 让脚本能被 import：去重插入脚本目录与仓库根（复用 lib.paths.ensure_path；
# lib.db 已惰性 _ensure_db_config，import 不再触发凭据检查——旧内联理由失效，评审 C3）。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)  # 先保证 lib 可导入
from lib.paths import ensure_path  # noqa: E402
ensure_path(os.path.dirname(os.path.abspath(__file__)), _REPO_ROOT)
from supervisor_state import _connect, _state_dir  # noqa: E402
from scene_router import route  # noqa: E402
from arbitrator import (arbitrate_plan_vs_simulation, arbitrate_dam_diagnosis,
                        arbitrate_emergency, arbitrate_risk_levels)  # noqa: E402
from dataclasses import asdict  # noqa: E402 -- 直连标准库，不再经 arbitrator 再导出（C3）
```

- [ ] **Step 2: orchestrator 其余 `_ensure_path` 调用点**

`:184`、`:527` 两处 `_ensure_path(...)` 调用保持语句不动（名字未变——现在是 `lib.paths.ensure_path` 的别名）。确认无其他 `_ensure_path` 定义残留：

```bash
grep -n "_ensure_path" supervisor/scripts/orchestrator.py
# 预期：仅 import 行 + 3 处调用（:44 一带、:184、:527），无 def
```

- [ ] **Step 3: arbitrator 顶部替换**

`arbitrator.py:24-34` 把

```python
# 让脚本能被 import（上级目录加入 path，读取 references）。
# 内联去重 helper：不 import lib.paths——lib 包初始化会触发 lib.db 凭据检查，
# 而本脚本在测试（无凭据环境）中也会被 import
def _ensure_path(*paths):
    for p in paths:
        p = os.path.abspath(p)
        if p not in sys.path:
            sys.path.insert(0, p)

_ensure_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
```

替换为：

```python
# 让脚本能被 import（上级目录加入 path，读取 references）。复用 lib.paths.ensure_path
# （lib.db 已惰性 _ensure_db_config，import 不触发凭据检查——旧内联理由失效，评审 C3）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根
from lib.paths import ensure_path  # noqa: E402
ensure_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
```

（arbitrator 自己的 `from dataclasses import dataclass, field, asdict` 保留——它自身在用。）

- [ ] **Step 4: 回归（arbitrator/scene_router/orchestrator 相关测试全在 tests/）**

Run: `python3 -m unittest discover tests`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add supervisor/scripts/orchestrator.py supervisor/scripts/arbitrator.py
git commit -m "refactor(supervisor): asdict 直连 dataclasses、复用 lib.paths.ensure_path，删两处过时内联（C3）"
```

---

### Task 12: T1 `cmd_health` 拆出纯函数 `evaluate_health`（TDD）

**Files:**
- Modify: `supervisor/scripts/supervisor_state.py`（`cmd_health` :387-470 一带拆分；乱码已在 Task 2 修复，此处搬运的是干净文案）
- Test: Create `tests/test_health_judgment.py`

**Interfaces:**
- Produces: `supervisor_state.evaluate_health(stcd: str, wl: dict, rf: dict, al: dict) -> tuple[list, str, dict]`——返回 `(checks, overall, derived)`；纯函数、零 lib 依赖、无 DB，可在无 DB 环境单测。
- `cmd_health` 保留为"查 DB + 调判定"的探针壳。

- [ ] **Step 1: 写失败测试**

Create `tests/test_health_judgment.py`：

```python
#!/usr/bin/env python3
"""evaluate_health 纯函数健康判定测试（T1）——无 DB、无 lib 依赖。"""
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_REPO_ROOT, "supervisor", "scripts")
for _p in (_REPO_ROOT, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from supervisor_state import evaluate_health


def _wl(age_h):
    return {"age_h": age_h, "max_tm": "2026-08-20 08:00:00", "cnt": 5}


def _rf(cnt):
    return {"cnt": cnt, "max_ymdh": "2026-08-27 08:00:00"}


def _al(total, high=0):
    return {"total": total, "high": high}


class TestEvaluateHealth(unittest.TestCase):

    def test_all_ok(self):
        checks, overall, d = evaluate_health("TQP", _wl(1.0), _rf(200), _al(3))
        self.assertEqual(overall, "ok")
        self.assertEqual(len(checks), 3)

    def test_stale_water_warns(self):
        checks, overall, _ = evaluate_health("TQP", _wl(9.0), _rf(200), _al(3))
        self.assertEqual(overall, "warn")
        self.assertTrue(any(c["item"] == "st_rsvr_r" and c["status"] == "warn"
                            for c in checks))

    def test_no_water_is_error(self):
        _, overall, _ = evaluate_health("TQP", _wl(None), _rf(0), _al(0))
        self.assertEqual(overall, "error")

    def test_low_forecast_coverage_warns(self):
        checks, overall, _ = evaluate_health("TQP", _wl(1.0), _rf(100), _al(3))
        self.assertEqual(overall, "warn")
        self.assertTrue(any(c["item"] == "f_rnfl_h" and c["status"] == "warn"
                            for c in checks))

    def test_alarm_pile_warns(self):
        checks, overall, d = evaluate_health("TQP", _wl(1.0), _rf(200), _al(1500, 12))
        self.assertEqual(overall, "warn")
        self.assertEqual(d["al_total"], 1500)
        self.assertEqual(d["al_high"], 12)

    def test_forecast_ok_msg_clean(self):
        """钉住 H3：ok 文案不得再出现 U+FFFD 替换字符。"""
        checks, _, _ = evaluate_health("TQP", _wl(1.0), _rf(200), _al(3))
        rf_ok = next(c for c in checks if c["item"] == "f_rnfl_h")
        self.assertEqual(rf_ok["msg"], "未来预报 200h 覆盖完整")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_health_judgment -v`
Expected: `ImportError: cannot import name 'evaluate_health'`。

- [ ] **Step 3: 实现——在 `cmd_health` 定义之前插入纯函数**

`supervisor_state.py` `cmd_health`（:387）之前插入：

```python
def evaluate_health(stcd, wl, rf, al):
    """纯函数健康判定（无 DB/无 lib 依赖，可无 DB 单测——评审 T1）。

    Args:
        stcd: 水位站码（用于 msg 文案）
        wl: st_rsvr_r 聚合行（max_tm/age_h/cnt）
        rf: f_rnfl_h 聚合行（cnt/max_ymdh）
        al: ew_info_message 聚合行（total/high）

    Returns:
        (checks, overall, derived) — checks 为三条判定，
        overall ∈ ok/warn/error，derived 为派生数值（供 detail 回填）。
    """
    wl_age = float(wl["age_h"]) if wl["age_h"] is not None else None
    rf_cnt = int(rf["cnt"]) if rf["cnt"] is not None else 0
    al_total = int(al["total"] or 0)
    al_high = int(al["high"] or 0)

    checks = []
    if wl_age is None:
        checks.append({"item": "st_rsvr_r", "status": "error",
                        "msg": f"无 {stcd} 数据"})
    elif wl_age > 6:
        checks.append({"item": "st_rsvr_r", "status": "warn",
                        "msg": f"水位数据过期 {wl_age}h（阈值 6h，cron 可能停摆）"})
    else:
        checks.append({"item": "st_rsvr_r", "status": "ok",
                        "msg": f"水位新鲜（age={wl_age}h）"})

    if rf_cnt < 168:
        checks.append({"item": "f_rnfl_h", "status": "warn",
                        "msg": f"未来预报仅 {rf_cnt}h（阈值 168h，--forecast 未跑）"})
    else:
        checks.append({"item": "f_rnfl_h", "status": "ok",
                        "msg": f"未来预报 {rf_cnt}h 覆盖完整"})

    if al_total > 1000:
        checks.append({"item": "ew_info_message", "status": "warn",
                        "msg": f"告警堆积 {al_total} 条（阈值 1000，需确认清理）"})
    else:
        checks.append({"item": "ew_info_message", "status": "ok",
                        "msg": f"告警数量正常（{al_total} 条，高级别 {al_high}）"})

    overall = "ok" if all(c["status"] == "ok" for c in checks) else (
        "error" if any(c["status"] == "error" for c in checks) else "warn")
    return checks, overall, {"wl_age": wl_age, "rf_cnt": rf_cnt,
                             "al_total": al_total, "al_high": al_high}
```

- [ ] **Step 4: `cmd_health` 改为薄壳**

`cmd_health` 内，三条查询语句（:403-424）原样保留；把从 `rf_cnt = int(...)`（:417）到 `overall = ...`（:454）的判定段替换为：

```python
    checks, overall, derived = evaluate_health(stcd, wl, rf, al)
```

返回 dict（:456 起）中 `"detail"` 的三个字段改为用 `derived`：

```python
        "detail": {
            "st_rsvr_r": {"stcd": stcd, "max_tm": wl["max_tm"],
                          "age_h": derived["wl_age"], "rows": wl["cnt"]},
            "f_rnfl_h": {"future_rows": derived["rf_cnt"], "max_ymdh": rf["max_ymdh"]},
            "ew_info_message": {"unconfirmed": derived["al_total"],
                                "high_level": derived["al_high"]},
        },
```

（返回 dict 的 overall/reservoir/tenant_id/checks 键保持原样。）

- [ ] **Step 5: 回归**

Run: `python3 -m unittest tests.test_health_judgment tests.test_supervisor_state_ops -v && python3 -m unittest discover tests`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add supervisor/scripts/supervisor_state.py tests/test_health_judgment.py
git commit -m "refactor(supervisor): cmd_health 拆出纯函数 evaluate_health，恢复无 DB 可测性（T1）"
```

---

### Task 13: T2 模块级 `TENANT` 改函数内动态解析 + `--tenant` CLI

**Files:**
- Modify: `supervisor/scripts/inspection_check.py`（:33 import、:37 `TENANT` 常量、:44/51/57/64/71/79 共 7 处 `(TENANT,)`、:122 `main`）
- Modify: `diagnosis-verification/scripts/check_data_quality.py`（:27 import、:29 常量、:49/86/112 共 3 处、:274 `main`）
- Test: `tests/test_tenant_isolation.py`（新测试类）

**Interfaces:**
- Consumes: `lib.tenant.resolve_tenant(explicit=None) -> int`（每次调用重读 `SRM_TENANT_ID`）。
- Produces: 两脚本 `--tenant` CLI 参数（`parser.add_argument("--tenant", type=int, ...)`）；函数内动态解析，import 复用时身份可随 env 改变。

- [ ] **Step 1: 盘点两文件使用点（执行时以实读为准）**

```bash
grep -n "TENANT" supervisor/scripts/inspection_check.py diagnosis-verification/scripts/check_data_quality.py
grep -n "add_argument\|def main" supervisor/scripts/inspection_check.py diagnosis-verification/scripts/check_data_quality.py
```

- [ ] **Step 2: 写失败测试**

`tests/test_tenant_isolation.py` 文末（`if __name__` 前）加（`_SUP_SCRIPTS`/`_DV_SCRIPTS` 路径若无则照 `_EW_SCRIPTS` 样式补进顶部循环）：

```python
# ===========================================================================
# T2：模块级 TENANT 改函数内动态解析——env 后置修改必须生效
# ===========================================================================
class TestDynamicTenantResolution(unittest.TestCase):

    @patch('inspection_check.execute_query_list')
    def test_inspection_check_tenant_dynamic(self, mock_eql):
        """import 后再改 SRM_TENANT_ID，查询参数必须跟着变（T2）。"""
        import inspection_check
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = []
        # 调用 inspection_check 里第一个使用 tenant 的查询函数
        # （执行 Task 13 时以 Step 1 盘点的实际函数名为准，此处为示意 fn）
        fn = getattr(inspection_check, _INSPECTION_TENANT_FN)
        fn()
        sql, params = mock_eql.call_args[0]
        self.assertIn(20, params)

    @patch('check_data_quality.execute_query_list')
    def test_check_data_quality_tenant_dynamic(self, mock_eql):
        """import 后再改 SRM_TENANT_ID，查询参数必须跟着变（T2）。"""
        import check_data_quality
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = [{'total': 0}]
        fn = getattr(check_data_quality, _CDQ_TENANT_FN)
        fn()
        sql, params = mock_eql.call_args[0]
        self.assertIn(20, params)
```

并在文件顶部常量区定义（已盘点：inspection_check 第一个 tenant 查询函数是 `overview()`，check_data_quality 是 `check_water_level()`）：

```python
_INSPECTION_TENANT_FN = 'overview'
_CDQ_TENANT_FN = 'check_water_level'
```

注意 mock 返回值形状须与被测函数的消费方式匹配：`check_water_level` 内是 `execute_query_list(sql, (TENANT,))[0]`（取首行后读键），故 Step 2 代码里 mock 给 `[{'total': 0}]`；`overview` 若同样取 `[0]`，把 `mock_eql.return_value = []` 改为非空单行 dict（以运行时报错为准，缺键按需补）。测试断言核心只有一条：**params 里出现 import 之后设置的 20**。

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest tests.test_tenant_isolation.TestDynamicTenantResolution -v`
Expected: FAIL——两脚本当前用 import 时冻结的模块级 `TENANT`，params 里是设 env 前的旧值（18）。

- [ ] **Step 4: 实现（两文件同一变换）**

4a. import 行把 `from lib.tenant import current_tenant_id` 改为 `from lib.tenant import resolve_tenant`。

4b. 删除模块级常量行 `TENANT = current_tenant_id()`。

4c. 所有 `(TENANT,)` 替换为 `(resolve_tenant(),)`（inspection_check 7 处、check_data_quality 3 处）。

4d. `main()` 的 `parser.parse_args()` 之后加：

```python
    if getattr(args, 'tenant', None) is not None:
        os.environ['SRM_TENANT_ID'] = str(args.tenant)
```

argparse 定义处加（两文件同款）：

```python
    parser.add_argument('--tenant', type=int,
                        help='水库租户 ID（18=三岔/20=桃曲坡，默认取 SRM_TENANT_ID）')
```

- [ ] **Step 5: 回归**

Run: `python3 -m unittest tests.test_tenant_isolation -v && python3 -m unittest discover tests`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add supervisor/scripts/inspection_check.py diagnosis-verification/scripts/check_data_quality.py tests/test_tenant_isolation.py
git commit -m "refactor: inspection_check/check_data_quality tenant 改函数内动态解析并支持 --tenant（T2）"
```

---

### Task 14: 全量回归 + 评审报告勘误落档

**Files:**
- Modify: `docs/review-2026-08-19.md`（文末脚注之前追加勘误节）

**Interfaces:** 无。

- [ ] **Step 1: 全量回归（CI 同款）**

```bash
python3 -m unittest discover tests
git status --short   # 应只剩 docs/review-2026-08-19.md 与本计划文件
git log --oneline -13  # 核对 Task 1-13 的提交齐整
```

- [ ] **Step 2: 追加勘误**

在 `docs/review-2026-08-19.md` 的末尾脚注行 `*本评审全程只读……*` 之前插入：

```markdown
---

## 附：勘误（2026-08-20 复核）

1. **S1 勘误（重大）**：本报告称 `execute_write` "没有任何调用方（grep 无引用）"——
   **不准确**。`forecasting/data/generate_taoqupo_data.py`（5 处）与
   `generate_sancha_data.py`（4 处）均在用（mock 造数 DELETE/INSERT）。
   处置已由"直接删除"改为"写能力剥离至 `lib/db_write.py` 显式受控通道"
   （见 docs/superpowers/plans/2026-08-20-review-remediation.md Task 4）。
2. **S4 补充**：forecasting 缺 tenant 的 `f_rnfl_h` 查询不止
   `query_rainfall_forecast` 一处；`query_multi_source_overview` 的 168h 聚合
   同样缺失，已一并修复（同计划 Task 5）。
3. **S3 勘误（轻微）**：本报告建议落档的 `docs/db-config.md` 并不存在
   （`query_forecast_data.py:33` 的指引已过时）；决策改记于
   `docs/shared-tables.md`（同计划 Task 7）。
```

- [ ] **Step 3: Commit**

```bash
git add docs/review-2026-08-19.md
git commit -m "docs(review): 勘误 S1 零引用论断、S4 第二处泄漏点与 db-config.md 失效指引"
```

---

## 决策点（执行前需用户确认）

1. **Task 3 / `diagnose_water_level_timeout.py`（137 行）**：删除还是改名归档？本计划默认删除（历史排障 scratch）。
2. **Task 7 / S3**：本计划采纳"显式记录跨租户设计"而非"补 tenant 过滤"（理由见 Task 7）。若你倾向补过滤，Task 7 改为给 early-warning 12 个告警查询 + `check_alerts` + `cmd_health` 加 `tenant_id = %s` 并同步翻转 `lib/filters.py` 规则表——工作量约 3 倍，且需先确认告警行确有归属维度。

## Self-Review 记录

- **覆盖**：S1(T4)/S2(T6)/S3(T7)/S4(T5)/S5(T8)/C1(T9)/C2(T10)/C3(T11)/H1-H2(T2,T3)/H3(T2)/H4(T1)/T1(T12)/T2(T13)/三处待提交(T1)/勘误(T14)——评审处置表 P0-P4 全部落任务。
- **类型一致性**：`current_flood_limit` 返回 dict 的键在 T10 定义并被三个 wrapper 消费一致；`evaluate_health` 的 `(checks, overall, derived)` 在 T12 定义与消费一致；`apply_tenant_filter` 的 `(sql, params)` 契约在 T6 测试与实现一致。
- **已知残留**（有意不做，记档备查）：forecasting 其余函数的 `tenant_id=DEFAULT_TENANT` 默认值（`get_master_stcd` 等）仍属 import 时刻冻结——S4 涉及的三个函数已改为 `None + resolve_tenant`，其余留待后续按需统一；`weather_warn`/`weather_info` 无 tenant 列为 schema 事实，不在整改范围。
