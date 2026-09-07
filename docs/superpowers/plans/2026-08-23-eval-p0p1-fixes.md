# 统一评估集 P0/P1 缺陷修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复统一评估集两类核心缺陷——live_db 真值 SQL 缺租户隔离（P0）与 rubric 无 LLM 时关键词假阳性进 gate（P1），并补一致性守卫。

**Architecture:** `truth_query` 引入 `{tenant_id}` 占位符（先改数据、再立 schema 强制、judge 执行前渲染）；新增 `SKIP` 判定状态贯通 judge → runner → report → gate（gate 只拦 FAIL/ERROR/TIMEOUT）；守卫测试补租户配对/smoke 覆盖/tag 一致/超时上限四项检查。任务顺序保证每个 commit 全绿。

**Tech Stack:** Python 3 stdlib `unittest`（项目标准）、PyYAML；无新增依赖。

**Spec:** 无独立 spec 文档；依据 2026-08-23 对 `eval/` 的深度分析结论（P0/P1 缺陷清单）。关键事实内嵌于下方 Global Constraints，执行者无需回溯会话。

## Global Constraints

- 测试用 **unittest**（`python3 -m unittest discover tests`），不用 pytest。测试放 `tests/test_eval_*.py`。
- 运行时依赖（pymysql / anthropic）一律函数内延迟导入——本计划不改这些导入点，保持现状。
- **不修改** `tests/reservoir_profile.py`（既有约定，verify_output 为判分复用核心）。
- **Live DB 已验证事实**（2026-08-10 INFORMATION_SCHEMA 核实，勿信 table-schema.md）：`st_rsvr_r`、`att_res_flse_lim`、`srm_flood_history_base`、`model_result_files` 四表**均有 `tenant_id` 列**；`st_rsvr_r`/`srm_flood_history_base` 查询已在用 `deleted` 列；`att_res_flse_lim` 的 `flood_season_start/end`、`flse_lim_stag` 列被现网查询使用（存在无疑）。库为多租户共享单库 `powerelf_srm_yml`（tenant 1=垃圾桶 7160 行、17=石盘、18=三岔、19=测试、20=桃曲坡）。
- verdict 词表从 `{PASS,FAIL,ERROR,TIMEOUT}` 扩展为 `{PASS,FAIL,ERROR,TIMEOUT,SKIP}`。
- 租户↔水库配对事实：18↔sancha（三岔）、20↔taoqupo（桃曲坡）。
- 提交信息用中文 conventional commit，结尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。

---

### Task 1: `render_truth_query` 占位符渲染 + judge_live_db 接线

**Files:**
- Modify: `eval/lib/truth.py`（模块级新增函数）
- Modify: `eval/lib/judge.py:37-50`（`judge_live_db` 内接线）
- Test: `tests/test_eval_truth.py`（追加类）

**Interfaces:**
- Consumes: 现有 `EvalCase.env` dict（`case.env.get("SRM_TENANT_ID")`）。
- Produces: `truth.render_truth_query(query: str, tenant_id) -> str`——把子串 `"${tenant_id}"` 替换为 `str(tenant_id)`；无占位符原样返回。后续 Task 3 的 schema 校验按同一占位符字面量检查。

> 占位符字面量定为 `${tenant_id}`（带 `$` 前缀，避免与 YAML/SQL 里普通花括号文本混淆）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_eval_truth.py` 顶部 import 行改为：

```python
import unittest
from eval.lib.truth import extract_numbers, compare_with_tolerance, render_truth_query
```

文件末尾 `if __name__` 之前追加：

```python
class TestRenderTruthQuery(unittest.TestCase):
    def test_substitutes_placeholder(self):
        sql = "SELECT rz FROM st_rsvr_r WHERE deleted = 0 AND tenant_id = ${tenant_id} LIMIT 1"
        self.assertEqual(
            render_truth_query(sql, 18),
            "SELECT rz FROM st_rsvr_r WHERE deleted = 0 AND tenant_id = 18 LIMIT 1")

    def test_no_placeholder_unchanged(self):
        self.assertEqual(render_truth_query("SELECT 1", 18), "SELECT 1")

    def test_accepts_string_tenant(self):
        self.assertEqual(render_truth_query("t=${tenant_id}", "20"), "t=20")


class TestJudgeLiveDbRendersTenant(unittest.TestCase):
    def test_placeholder_resolved_before_query(self):
        """judge_live_db 必须先把 ${tenant_id} 渲染成真实租户再交给 query_fn。"""
        from eval.lib.schema import EvalCase
        from eval.lib import judge
        captured = {}
        c = EvalCase(id="X", skill="forecasting", category="c", description="d",
                     question="q", env={"SRM_TENANT_ID": 18}, source="s",
                     truth_source="live_db",
                     truth_query="SELECT rz FROM st_rsvr_r WHERE tenant_id = ${tenant_id}",
                     tolerance=1.0)

        def qf(sql):
            captured["sql"] = sql
            return [{"rz": 462.5}]

        r = judge.judge_live_db(c, "当前水位 462 m", qf)
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(captured["sql"],
                         "SELECT rz FROM st_rsvr_r WHERE tenant_id = 18")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_truth -v`
Expected: `ImportError: cannot import name 'render_truth_query'`

- [ ] **Step 3: 最小实现**

`eval/lib/truth.py` 在 `compare_with_tolerance` 之后追加：

```python
TENANT_PLACEHOLDER = "${tenant_id}"


def render_truth_query(query: str, tenant_id) -> str:
    """把 truth_query 里的 ${tenant_id} 替换为真实租户 ID（多租户共享库，
    真值 SQL 不带租户过滤会取到别家水库的行——见 2026-08-23 分析 P0-1）。"""
    return (query or "").replace(TENANT_PLACEHOLDER, str(tenant_id))
```

顶部 import 行改为：

```python
from eval.lib.truth import (
    TENANT_PLACEHOLDER, compare_with_tolerance, extract_numbers, render_truth_query)
```

`judge_live_db` 第一行 `rows = query_fn(case.truth_query)` 改为：

```python
    rows = query_fn(render_truth_query(case.truth_query,
                                       case.env.get("SRM_TENANT_ID")))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_eval_truth tests.test_eval_judge -v`
Expected: 全部 PASS（judge 测试里的 truth_query 无占位符，replace 是 no-op，不受影响）

- [ ] **Step 5: 提交**

```bash
git add eval/lib/truth.py eval/lib/judge.py tests/test_eval_truth.py
git commit -m "feat(eval): truth_query 支持 \${tenant_id} 占位符渲染并接入 live_db 判分

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 用例 SQL 租户化 + 容差统一 + SIM26 题面对齐（纯数据变更）

**Files:**
- Modify: `eval/cases/forecasting.yaml`（F7/F12/F22）
- Modify: `eval/cases/plan-generation.yaml`（PG6/PG7/PG12）
- Modify: `eval/cases/simulation.yaml`（SIM26/SIM27）
- Modify: `eval/cases/diagnosis-verification.yaml`（DV6）

**Interfaces:**
- Consumes: Task 1 的 `${tenant_id}` 渲染机制（数据从此开始携带占位符）。
- Produces: 9 道 live_db 题全部租户化；本任务不新增任何校验逻辑（schema 强制在 Task 3），保证 commit 全绿。

**水位真值 SQL（5 处，字符串完全相同）：**

旧：
```sql
SELECT rz FROM st_rsvr_r WHERE rz IS NOT NULL AND deleted = 0 ORDER BY tm DESC LIMIT 1
```
新：
```sql
SELECT rz FROM st_rsvr_r WHERE rz IS NOT NULL AND deleted = 0 AND tenant_id = ${tenant_id} ORDER BY tm DESC LIMIT 1
```
出现位置：forecasting.yaml F7(:87)、F12(:141)；plan-generation.yaml PG6(:95)；simulation.yaml SIM27(:335)；diagnosis-verification.yaml DV6(:94)。同文件内用全局替换一次完成。

- [ ] **Step 1: 替换 5 处水位真值 SQL**

对 4 个 cases yaml 分别执行上述旧→新替换（Edit 工具 `replace_all: true`，每文件命中数：forecasting 2、plan-generation 1、simulation 1、diagnosis-verification 1）。

- [ ] **Step 2: PG7 汛限查询重写（租户过滤 + 确定性排序）**

`eval/cases/plan-generation.yaml` PG7（:107）：

旧：
```yaml
    truth_query: "SELECT flse_lim_stag FROM att_res_flse_lim WHERE flood_season_start <= DATE_FORMAT(NOW(), '%m%d') AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d') LIMIT 1"
```
新：
```yaml
    truth_query: "SELECT flse_lim_stag FROM att_res_flse_lim WHERE tenant_id = ${tenant_id} AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d') AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d') ORDER BY flood_season_start DESC LIMIT 1"
```
（`ORDER BY flood_season_start DESC` 用的是 WHERE 里已引用的列，消除跨季/跨租户 `LIMIT 1` 取行不确定性。）

- [ ] **Step 3: 两条 COUNT 真值租户化 + 容差对齐**

`eval/cases/forecasting.yaml` F22（:260）：
```yaml
    truth_query: "SELECT COUNT(*) AS cnt FROM srm_flood_history_base WHERE deleted = 0 AND tenant_id = ${tenant_id}"
```
tolerance 保持 2.0 不动。

`eval/cases/simulation.yaml` SIM26（:320-324）整题改为：
```yaml
  - id: SIM26
    skill: simulation
    category: 历史经验_异常
    description: 历史洪水总数 live_db（真值口径=本租户全部非删除记录）
    question: "系统里总共存了多少条历史洪水记录？"
    env: {SRM_TENANT_ID: 18, SRM_RESERVOIR_NAME: sancha}
    timeout: 120
    tags: [live_db]
    source: simulation/tests/test-questions.md::Q65
    truth_source: live_db
    truth_query: "SELECT COUNT(*) AS cnt FROM srm_flood_history_base WHERE deleted = 0 AND tenant_id = ${tenant_id}"
    tolerance: 2.0
    expected_keywords: ["历史", "洪水"]
```
（三处修正：题面原问"有完整预演结果的几场"与 COUNT 全表的口径不符→改问总数；tolerance 50.0→2.0 对齐 F22 先例；SQL 补租户。）注意：与 F22 题面近似是跨 skill 重复，属预期（测的是不同 skill 的取数能力），不去重。

`eval/cases/plan-generation.yaml` PG12（:162-163）：
```yaml
    truth_query: "SELECT COUNT(*) AS cnt FROM model_result_files WHERE type = 2 AND tenant_id = ${tenant_id}"
    tolerance: 2.0
```
（tolerance 20.0→2.0，理由同 F22 注释：两侧几乎同时读同一张表，漂移只来自并发写入。）

- [ ] **Step 4: 验证加载与计数**

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from eval.lib.schema import load_all; cs=load_all('eval/cases'); print(len(cs)); print(sum(1 for c in cs if c.truth_source=='live_db'))"`
Expected: 输出 `133` 与 `9`

- [ ] **Step 5: 全量单测确认无回归**

Run: `python3 -m unittest discover tests`
Expected: OK（本任务未动任何代码路径）

- [ ] **Step 6: 提交**

```bash
git add eval/cases/
git commit -m "fix(eval): 9 处 live_db truth_query 补租户过滤，PG7 加确定性排序，COUNT 容差对齐 ±2

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: schema.validate 三项增强（占位符强制 / range 结构 / 租户合法值）

**Files:**
- Modify: `eval/lib/schema.py:34-47`（`validate`）及模块常量区
- Modify: `tests/test_eval_runner.py:73`（live_db fixture 的 truth_query 补占位符）
- Test: `tests/test_eval_schema.py`（追加用例）

**Interfaces:**
- Consumes: Task 1 的 `TENANT_PLACEHOLDER = "${tenant_id}"` 字面量（schema 内自定义同名常量，避免 eval.lib 循环依赖——schema.py 定位为零内部依赖）。
- Produces: `validate()` 新增三条拒绝规则；此后所有 live_db 题不带占位符无法加载。

- [ ] **Step 1: 写失败测试**

`tests/test_eval_schema.py` 的 `TestSchema` 类内追加：

```python
    def test_live_db_requires_tenant_placeholder(self):
        base = dict(id="X", skill="forecasting", category="c", description="d",
                    question="q", env={"SRM_TENANT_ID": 18}, source="s")
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="live_db",
                              truth_query="SELECT rz FROM st_rsvr_r LIMIT 1"))
        # 带占位符则通过
        validate(EvalCase(**base, truth_source="live_db",
                          truth_query="SELECT rz FROM st_rsvr_r WHERE tenant_id = ${tenant_id}"))

    def test_expected_range_must_be_well_formed(self):
        base = dict(id="X", skill="forecasting", category="c", description="d",
                    question="q", env={"SRM_TENANT_ID": 18}, source="s",
                    truth_source="inline", expected_keywords=["水位"])
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, expected_range={"min": 459}))          # 缺 max
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, expected_range={"min": 463, "max": 459}))  # min>=max
        validate(EvalCase(**base, expected_range={"min": 459, "max": 463}))      # 合法

    def test_tenant_id_must_be_known(self):
        base = dict(id="X", skill="forecasting", category="c", description="d",
                    question="q", source="s", truth_source="inline",
                    expected_keywords=["水位"])
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, env={"SRM_TENANT_ID": 99}))
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, env={"SRM_TENANT_ID": "abc"}))
        validate(EvalCase(**base, env={"SRM_TENANT_ID": 18}))
        validate(EvalCase(**base, env={"SRM_TENANT_ID": "20"}))  # 字符串数字也可
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_schema -v`
Expected: 新增 3 条 FAIL/ERROR（validate 尚无对应规则）

- [ ] **Step 3: 实现**

`eval/lib/schema.py` 顶部常量区（`VALID_TRUTH` 之后）追加：

```python
KNOWN_TENANT_IDS = frozenset({17, 18, 19, 20})  # 17=石盘 18=三岔 19=测试 20=桃曲坡
TENANT_PLACEHOLDER = "${tenant_id}"
```

`validate()` 中 `if case.truth_source == "live_db" and not case.truth_query:` 之后追加：

```python
    if case.truth_source == "live_db" and TENANT_PLACEHOLDER not in (case.truth_query or ""):
        raise ValueError(f"{case.id}: live_db truth_query 必须含 {TENANT_PLACEHOLDER}（多租户共享库）")
    if case.expected_range is not None:
        rng = case.expected_range
        try:
            lo, hi = float(rng["min"]), float(rng["max"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{case.id}: expected_range 需为含数值 min/max 的 dict: {rng!r}") from e
        if lo >= hi:
            raise ValueError(f"{case.id}: expected_range min>=max: {rng!r}")
    try:
        tenant = int(case.env.get("SRM_TENANT_ID"))
    except (TypeError, ValueError) as e:
        raise ValueError(f"{case.id}: SRM_TENANT_ID 非法: {case.env.get('SRM_TENANT_ID')!r}") from e
    if tenant not in KNOWN_TENANT_IDS:
        raise ValueError(f"{case.id}: SRM_TENANT_ID={tenant} 不在已知租户表 {sorted(KNOWN_TENANT_IDS)}")
```

- [ ] **Step 4: 更新受影响的既有 fixture**

`tests/test_eval_runner.py` :73 行内，把子串 `'SELECT rz FROM st_rsvr_r LIMIT 1'` 替换为 `'SELECT rz FROM st_rsvr_r WHERE tenant_id = ${tenant_id} LIMIT 1'`（该行是写临时 YAML 的 Python 字符串，只动 SQL 子串，其余不动）。

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m unittest discover tests`
Expected: OK（真实 cases 已在 Task 2 全部合规）

- [ ] **Step 6: 提交**

```bash
git add eval/lib/schema.py tests/test_eval_schema.py tests/test_eval_runner.py
git commit -m "feat(eval): schema 校验 live_db 租户占位符、expected_range 结构与租户合法值

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: judge_rubric 无 LLM 时 SKIP 语义

**Files:**
- Modify: `eval/lib/judge.py:53-63`（`judge_rubric`）
- Test: `tests/test_eval_judge.py::TestRubricJudge`

**Interfaces:**
- Consumes: 无新依赖。
- Produces: `judge_rubric(case, output, llm_fn=None)` 无 LLM 时返回 `{"verdict": "SKIP", ...}` 或 `{"verdict": "FAIL", ...}`；带 LLM 时行为不变（rule∧LLM）。新语义：**禁词命中或关键词未全中 → FAIL（保留负信号）；否则 SKIP（不再以弱关键词给假阳性 PASS）**。Task 5 的 runner/report/gate 依赖该 verdict 字符串。

- [ ] **Step 1: 改写失败测试**

`tests/test_eval_judge.py::TestRubricJudge` 整类替换为：

```python
class TestRubricJudge(unittest.TestCase):
    def test_skip_without_llm_when_rule_layer_passes(self):
        """无 LLM 且规则层通过 → SKIP（不再给关键词假阳性 PASS，评审 2026-08-23 P1-3）。"""
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        r = judge.judge_rubric(c, "当前水位 462 m")
        self.assertEqual(r["verdict"], "SKIP")
        self.assertEqual(r["detail"]["rubric"], "skip (no llm)")

    def test_fail_without_llm_on_forbidden(self):
        c = _case(truth_source="rubric", rubric=["x"], forbidden=["桃曲坡"])
        r = judge.judge_rubric(c, "桃曲坡 结果", None)
        self.assertEqual(r["verdict"], "FAIL")

    def test_fail_without_llm_on_missing_keywords(self):
        """无 LLM 时关键词缺失仍 FAIL（负信号保留，只有弱阳性被降级为 SKIP）。"""
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        r = judge.judge_rubric(c, "答非所问")
        self.assertEqual(r["verdict"], "FAIL")

    def test_with_llm(self):
        c = _case(truth_source="rubric", rubric=["必须给数值"])
        fake = lambda out, rub: {"passed": True, "items": [{"criterion": "必须给数值", "pass": True}]}
        r = judge.judge_rubric(c, "ok", fake)
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("rubric_score", r["detail"])

    def test_rule_pass_but_llm_fail(self):
        """规则层过 + LLM 判不过 → FAIL（AND 语义回归，评审 P10）。"""
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        fake = lambda out, rub: {"passed": False, "items": [{"criterion": "必须给数值", "pass": False}]}
        r = judge.judge_rubric(c, "当前水位 462 m", fake)
        self.assertEqual(r["verdict"], "FAIL")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_judge.TestRubricJudge -v`
Expected: `test_skip_without_llm_when_rule_layer_passes` FAIL（现实现返回 PASS）

- [ ] **Step 3: 实现**

`eval/lib/judge.py::judge_rubric` 中无 LLM 分支整体替换：

旧：
```python
    if llm_fn is None:
        return {"verdict": "PASS" if rule_pass else "FAIL",
                "detail": {**kw, "forbidden_hits": forb, "rubric": "skip (no llm)"}}
```
新：
```python
    if llm_fn is None:
        # 无 LLM 时规则层只保留负信号：禁词/关键词缺失 → FAIL；
        # 规则层通过也只能判 SKIP（关键词匹配太弱，不足以证明满足 rubric）
        if not rule_pass:
            return {"verdict": "FAIL",
                    "detail": {**kw, "forbidden_hits": forb, "rubric": "rule-layer fail (no llm)"}}
        return {"verdict": "SKIP",
                "detail": {**kw, "forbidden_hits": forb, "rubric": "skip (no llm)"}}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover tests`
Expected: 此刻 `tests.test_eval_runner` 可能出现非零退出码断言失败吗？——不会：现有 runner 测试全用 inline/live_db 题，不含 rubric。Expected: OK

- [ ] **Step 5: 提交**

```bash
git add eval/lib/judge.py tests/test_eval_judge.py
git commit -m "feat(eval): rubric 无 LLM 时规则层通过改判 SKIP，消除关键词假阳性进 gate

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: SKIP 贯通 runner / report / gate

**Files:**
- Modify: `eval/run.py:111`（status 映射）与 `eval/run.py:125-127`（gate 退出码）
- Modify: `eval/lib/report.py`（`summarize`/`write_markdown`）
- Test: `tests/test_eval_report.py`、`tests/test_eval_runner.py`

**Interfaces:**
- Consumes: Task 4 的 `"SKIP"` verdict 字符串。
- Produces: `summarize()` 返回结构变为 `{"by_skill": {skill: {cat: {pass, skip, total, rate}}}, "overall": {pass, skip, total, rate}}`；gate 语义 = 无 FAIL/ERROR/TIMEOUT 即退出码 0（SKIP 放行）。

- [ ] **Step 1: 写失败测试（report）**

`tests/test_eval_report.py`：

(a) `test_summarize_skill_category` 断言替换为（增加 SKIP 题）：

```python
    def test_summarize_skill_category(self):
        results = [
            report.build_result(_c("1", "f", "水位"), "PASS", 1, "o", {}),
            report.build_result(_c("2", "f", "水位"), "FAIL", 1, "o", {}),
            report.build_result(_c("3", "f", "降雨"), "PASS", 1, "o", {}),
            report.build_result(_c("4", "f", "降雨"), "SKIP", 1, "o", {}),
        ]
        s = report.summarize(results)
        self.assertEqual(s["overall"], {"pass": 2, "skip": 1, "total": 4, "rate": 0.5})
        self.assertEqual(s["by_skill"]["f"]["水位"], {"pass": 1, "skip": 0, "total": 2, "rate": 0.5})
```

(b) `test_write_markdown_marks_pass_and_fail` 追加 SKIP 渲染断言：

```python
    def test_write_markdown_marks_pass_and_fail(self):
        """PASS=[x]、FAIL=[ ]、SKIP=[-]——防止 mark 语义再反（03a16b6 前的 bug）。"""
        import tempfile
        results = [
            report.build_result(_c("1", "f", "c"), "PASS", 1, "o", {}),
            report.build_result(_c("2", "f", "c"), "FAIL", 1, "o", {}),
            report.build_result(_c("3", "f", "c"), "SKIP", 1, "o", {}),
        ]
        with tempfile.TemporaryDirectory() as d:
            mp = Path(d) / "r.md"
            report.write_markdown(results, report.summarize(results), mp)
            md = mp.read_text()
            self.assertIn("- [x] 1 ", md)
            self.assertIn("- [ ] 2 ", md)
            self.assertIn("- [-] 3 ", md)
```

- [ ] **Step 2: 写失败测试（runner gate）**

`tests/test_eval_runner.py::TestRunner` 追加：

```python
    def test_gate_skip_does_not_block(self):
        """rubric 无 LLM 判 SKIP 后，gate 只拦 FAIL/ERROR/TIMEOUT（退出码 0）。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "forecasting.yaml").write_text(
                "cases:\n"
                "  - {id: R1, skill: forecasting, category: c, description: d, question: q,\n"
                "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: rubric,\n"
                "     rubric: [要点], expected_keywords: [水位]}\n", encoding="utf-8")
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                return {"output": "当前水位 462 m", "stderr": "", "exit_code": 0, "timed_out": False}
            rc = _quiet_main(["--cases-dir", d, "--report-dir", d], transport_fn=fake_transport)
            self.assertEqual(rc, 0)  # SKIP 放行
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_report tests.test_eval_runner -v`
Expected: 新增/改写的 3 处 FAIL（summarize 无 skip 键、mark 无 [-]、gate 对 SKIP 返回 1）

- [ ] **Step 4: 实现 report.py**

`summarize` 整体替换：

```python
def summarize(results):
    agg = defaultdict(lambda: {"pass": 0, "skip": 0, "total": 0})
    for r in results:
        a = agg[(r["skill"], r["category"])]
        a["total"] += 1
        if r["status"] == "PASS":
            a["pass"] += 1
        elif r["status"] == "SKIP":
            a["skip"] += 1
    by_skill = {}
    for (skill, cat), v in sorted(agg.items()):
        by_skill.setdefault(skill, {})[cat] = {
            "pass": v["pass"], "skip": v["skip"], "total": v["total"],
            "rate": round(v["pass"] / v["total"], 3)}
    total = len(results)
    p = sum(1 for r in results if r["status"] == "PASS")
    sk = sum(1 for r in results if r["status"] == "SKIP")
    return {"by_skill": by_skill,
            "overall": {"pass": p, "skip": sk, "total": total,
                        "rate": round(p / total, 3) if total else 0}}
```

`write_markdown` 中总览行与表格头/行替换：

```python
    lines = ["# 评估报告", "",
             f"总通过率: {o['pass']}/{o['total']} = {o['rate']}（SKIP {o.get('skip', 0)} 不计入门禁）", ""]
```
```python
        lines += [f"## {skill}", "| category | pass/total | skip | rate |", "|---|---|---|---|"]
        lines += [f"| {c} | {v['pass']}/{v['total']} | {v['skip']} | {v['rate']} |" for c, v in cats.items()]
```
```python
    mark = lambda s: {"PASS": "x", "SKIP": "-"}.get(s, " ")
```

- [ ] **Step 5: 实现 run.py**

`:111` status 映射行替换为：

```python
        status = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR",
                  "TIMEOUT": "TIMEOUT", "SKIP": "SKIP"}.get(v["verdict"], "ERROR")
```

gate 退出码（原 `return 0 if summary["overall"]["pass"] == summary["overall"]["total"] else 1`）替换为：

```python
    blocked = [r for r in results if r["status"] not in ("PASS", "SKIP")]
    return 0 if not blocked else 1
```
（`--mode report` 分支保持在其上方先行 `return 0` 不变。）

- [ ] **Step 6: 跑全量测试确认通过**

Run: `python3 -m unittest discover tests`
Expected: OK

- [ ] **Step 7: 提交**

```bash
git add eval/run.py eval/lib/report.py tests/test_eval_report.py tests/test_eval_runner.py
git commit -m "feat(eval): SKIP 贯通 runner/report，gate 仅拦 FAIL/ERROR/TIMEOUT

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 守卫测试四项增强 + tag/smoke 数据修补

**Files:**
- Modify: `tests/test_eval_cases.py`（追加 4 个测试）
- Modify: `eval/cases/forecasting.yaml`（F12 加 tag）
- Modify: `eval/cases/plan-generation.yaml`（PG6/PG7 加 tag）
- Modify: `eval/cases/simulation.yaml`（SIM27 加 smoke）
- Modify: `eval/cases/early-warning.yaml`（EW29 加 smoke）
- Modify: `eval/cases/supervisor.yaml`（SUP6 加 smoke）

**Interfaces:**
- Consumes: `load_all`（既有）。
- Produces: CI 守卫覆盖——租户↔水库配对已知、live_db tag⇔truth_source 一致、每 skill ≥1 smoke、单题 timeout ≤1800。

- [ ] **Step 1: 先写失败守卫测试**

`tests/test_eval_cases.py::TestCases` 追加：

```python
    KNOWN_PAIRS = {(18, "sancha"), (20, "taoqupo")}  # 17=石盘/19=测试暂无用例，入库后再扩

    def test_env_tenant_reservoir_pairing_known(self):
        for c in load_all(CASES_DIR):
            pair = (c.env.get("SRM_TENANT_ID"), c.env.get("SRM_RESERVOIR_NAME"))
            self.assertIn(pair, self.KNOWN_PAIRS, f"{c.id}: 租户/水库配对未知或不一致 {pair}")

    def test_live_db_tag_matches_truth_source(self):
        """tag 'live_db' ⇔ truth_source=='live_db'，防 --tag live_db 过滤漂移（F12/PG6/PG7 曾漏标）。"""
        for c in load_all(CASES_DIR):
            tagged = "live_db" in c.tags
            self.assertEqual(tagged, c.truth_source == "live_db",
                             f"{c.id}: tag={c.tags} 与 truth_source={c.truth_source} 不一致")

    def test_every_skill_has_smoke(self):
        skills = {c.skill for c in load_all(CASES_DIR)}
        smoked = {c.skill for c in load_all(CASES_DIR) if "smoke" in c.tags}
        self.assertEqual(set(), skills - smoked, f"缺 smoke 快速门: {skills - smoked}")

    def test_timeout_bounded(self):
        for c in load_all(CASES_DIR):
            self.assertLessEqual(c.timeout, 1800, f"{c.id}: 单题 timeout {c.timeout}s 超上限")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_eval_cases -v`
Expected: `test_live_db_tag_matches_truth_source` FAIL（F12/PG6/PG7 漏标）；`test_every_skill_has_smoke` FAIL（simulation/early-warning/supervisor 缺）

- [ ] **Step 3: 修补用例数据**

- forecasting.yaml F12（timeout 行下）加一行：`    tags: [live_db]`
- plan-generation.yaml PG6、PG7 各加：`    tags: [live_db]`
- simulation.yaml SIM27：`tags: [live_db]` → `tags: [smoke, live_db]`
- early-warning.yaml EW29（timeout: 60 下）加：`    tags: [smoke]`
- supervisor.yaml SUP6（timeout: 60 下）加：`    tags: [smoke]`

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover tests && python3 eval/run.py --subset smoke --list | wc -l`
Expected: 测试 OK；smoke 列表行数 = 16（原 13 + SIM27/EW29/SUP6 新 3）

- [ ] **Step 5: 提交**

```bash
git add tests/test_eval_cases.py eval/cases/
git commit -m "test(eval): 守卫补配对/smoke覆盖/tag一致/超时上限四项，修 live_db tag 漂移与 smoke 盲区

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: README 同步

**Files:**
- Modify: `eval/README.md`

**Interfaces:** 无代码接口；文档与实现对齐。

- [ ] **Step 1: 更新四处描述**

1. 「跑评估」节末尾追加一行：
   ```
   rubric 题无 `--llm` 时规则层只保留负信号：通过判 SKIP（不计入门禁、报告标 `[-]`），缺失关键词/命中禁词仍判 FAIL。
   ```
2. 「加题」节示例的 `truth_source: inline` 注释块后追加提示：
   ```
   live_db 题的 truth_query 必须包含 `${tenant_id}` 占位符（如 `WHERE tenant_id = ${tenant_id}`），加载时强制校验。
   ```
3. 「truth_source 三类」表格 live_db 行「必填字段」列改为：
   ```
   `truth_query`（必含 `${tenant_id}`）+ `tolerance`（水位建议 1.0，历史计数建议 2.0）
   ```
   rubric 行「判分方式」列改为：
   ```
   默认规则层负信号（keywords 缺失/forbidden 命中→FAIL，否则 SKIP）；`--llm` 才按 rubric 打分且 gate 生效
   ```
4. 「判分实现」节首条后追加：
   ```
   - `eval/lib/truth.py::render_truth_query` — live_db 真值 SQL 的 `${tenant_id}` 渲染（多租户共享库防串库）
   ```

- [ ] **Step 2: 核对文档与实现一致**

Run: `grep -n "tenant_id\|SKIP" eval/README.md`
Expected: 上述四处均可见，且无遗留「历史计数建议 50.0」旧口径。

- [ ] **Step 3: 提交**

```bash
git add eval/README.md
git commit -m "docs(eval): README 同步租户占位符强制与 SKIP 门禁语义

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务后）

- [ ] `python3 -m unittest discover tests` 全绿
- [ ] `python3 eval/run.py --list | wc -l` 仍为 133
- [ ] `git log --oneline -7` 七个提交依次可读
