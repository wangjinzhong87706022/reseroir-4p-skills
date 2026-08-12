# 统一评估集（eval set）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 6 套分散的硬编码 eval 集合 + ~400 道人工 markdown 题库统一成单一机器可消费评估集（`eval/`），复用现有 `verify_output` 引擎，cull 到 ~130 起步题，并把现有 unittest 接进 CI。

**Architecture:** 新建 `eval/` 目录（`run.py` + `lib/{schema,judge,truth,transport,report}.py` + `cases/*.yaml`），单一 schema（每题声明 `truth_source: inline|live_db|rubric`），单一 runner 按 truth_source 分发判分。规则判分复用 `tests/reservoir_profile.py::verify_output`。旧脚本/旧题库全保留（方案 A 渐进迁移）。eval set 本身 hermes-bound 不入 CI；CI 只接 `python3 -m unittest discover tests`。

**Tech Stack:** Python 3 stdlib `unittest`（项目标准，pytest 未装）、PyYAML、hermes CLI（运行时）、pymysql（live_db 运行时）、anthropic SDK（LLM-judge 可选运行时）。所有运行时依赖延迟导入，CI 只需 pyyaml。

**Spec:** `docs/superpowers/specs/2026-08-12-eval-set-consolidation-design.md`

## Global Constraints

- 测试用 **unittest**（`python3 -m unittest discover tests`），不用 pytest。新测试放 `tests/` 下，命名 `test_eval_*.py`，自动被 discover 与 CI 覆盖。
- 运行时依赖（pymysql / anthropic）一律**延迟导入**（函数内 import），保证 `unittest discover` 与 CI 无需它们即可 import。
- `eval/` 与 `eval/lib/` 各需 `__init__.py`（做成包），`cases/` 放数据无需 `__init__.py`。
- 复用 `tests/reservoir_profile.py::verify_output` 做规则判分核心；**不修改**该文件。
- 旧脚本（`test_skills.py`、各 `eval.py`/`eval_runner.py`）与旧 markdown 题库**一律不删不改逻辑**；markdown 仅在 Task 11 顶部加存档横幅。
- 退出码：runner 全 PASS=0，有 FAIL/ERROR=1。
- 提交信息用项目约定（中文 conventional commit），结尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。

## File Structure

| 文件 | 职责 |
|---|---|
| `eval/__init__.py` | 包标记（空） |
| `eval/lib/__init__.py` | 包标记（空） |
| `eval/lib/schema.py` | `EvalCase` dataclass + `load_file/load_all/validate`（零依赖） |
| `eval/lib/judge.py` | `judge_inline/judge_live_db/judge_rubric/llm_judge`（复用 verify_output） |
| `eval/lib/truth.py` | `extract_numbers/compare_with_tolerance/make_db_query_fn` |
| `eval/lib/transport.py` | `run_hermes`（hermes 子进程，env 注入） |
| `eval/lib/report.py` | `build_result/summarize/write_json/write_markdown` |
| `eval/run.py` | CLI：发现→过滤→传输→判分→报告→退出码 |
| `eval/cases/<6 skill>.yaml` | cull 后的起步题集（~130） |
| `eval/README.md` | 加题/跑评估指南 |
| `tests/test_eval_{schema,judge,truth,transport,report,runner,cases}.py` | 各 lib 单测（CI 覆盖） |
| `.github/workflows/auto-merge.yml` | 改：`Run tests on PR` 真跑 `unittest discover` + 装 pyyaml |
| 7 个旧 `tests/test-questions*.md` / `test-inputs.md` | 改：顶部加存档横幅 |

---

## Task 1: `eval/lib/schema.py` — EvalCase + 加载 + 校验

**Files:**
- Create: `eval/__init__.py`, `eval/lib/__init__.py`
- Create: `eval/lib/schema.py`
- Test: `tests/test_eval_schema.py`

**Interfaces:**
- Produces: `EvalCase`（字段见下）、`load_file(path)->list[EvalCase]`、`load_all(cases_dir)->list[EvalCase]`、`validate(case)->None`。后续所有 task 消费 `EvalCase`。

- [ ] **Step 1: 建包标记**

```bash
mkdir -p eval/lib eval/cases
printf '' > eval/__init__.py
printf '' > eval/lib/__init__.py
```

- [ ] **Step 2: 写失败测试 `tests/test_eval_schema.py`**

```python
import unittest, tempfile, textwrap
from pathlib import Path
from eval.lib.schema import EvalCase, load_file, load_all, validate

YAML = textwrap.dedent("""
forbidden_keywords: [三岔]
cases:
  - id: T1
    skill: forecasting
    category: 水位
    description: d
    question: q
    env: {SRM_TENANT_ID: 20, SRM_RESERVOIR_NAME: taoqupo}
    source: old::T1
    truth_source: inline
    expected_keywords: ["4420"]
    forbidden: [桃曲坡]
""")

class TestSchema(unittest.TestCase):
    def test_load_merges_file_forbidden(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.yaml"; p.write_text(YAML, encoding="utf-8")
            cases = load_file(p)
        self.assertEqual(len(cases), 1)
        c = cases[0]
        self.assertEqual(set(c.forbidden), {"三岔", "桃曲坡"})  # 题级 + 文件级取并集

    def test_load_all_detects_duplicate_id(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"a.yaml").write_text(YAML, encoding="utf-8")
            (Path(d)/"b.yaml").write_text(YAML, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_all(d)

    def test_validate_rejects_bad_truth_source(self):
        c = EvalCase(id="X", skill="forecasting", category="c", description="d",
                     question="q", env={"SRM_TENANT_ID": 18}, source="s", truth_source="bogus")
        with self.assertRaises(ValueError):
            validate(c)

    def test_validate_requires_truth_fields(self):
        base = dict(id="X", skill="forecasting", category="c", description="d",
                    question="q", env={"SRM_TENANT_ID": 18}, source="s")
        # live_db 缺 truth_query
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="live_db"))
        # rubric 缺 rubric
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="rubric"))
        # inline 缺 keywords 与 range
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="inline"))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m unittest tests.test_eval_schema -v`
Expected: FAIL（`ModuleNotFoundError: eval.lib.schema`）

- [ ] **Step 4: 写实现 `eval/lib/schema.py`**

```python
"""统一评估集：题目 schema + 加载 + 校验。零 hermes/DB 依赖。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml

VALID_TRUTH = {"inline", "live_db", "rubric"}


@dataclass
class EvalCase:
    id: str
    skill: str
    category: str
    description: str
    question: str
    env: dict
    source: str
    truth_source: str
    timeout: int = 300
    tags: list = field(default_factory=list)
    expected_keywords: list = field(default_factory=list)
    expected_range: Optional[dict] = None
    forbidden: list = field(default_factory=list)
    truth_query: Optional[str] = None
    tolerance: float = 0.0
    rubric: list = field(default_factory=list)


def _coerce_str_list(lst):
    return [str(x) for x in (lst or [])]


def validate(case: EvalCase) -> None:
    for req in ("id", "skill", "category", "description", "question", "env", "source", "truth_source"):
        if not getattr(case, req):
            raise ValueError(f"{case.id}: 缺必填字段 {req}")
    if case.truth_source not in VALID_TRUTH:
        raise ValueError(f"{case.id}: truth_source 非法 {case.truth_source!r}")
    if "SRM_TENANT_ID" not in case.env:
        raise ValueError(f"{case.id}: env 缺 SRM_TENANT_ID")
    if case.truth_source == "inline" and not case.expected_keywords and not case.expected_range:
        raise ValueError(f"{case.id}: inline 题需 expected_keywords 或 expected_range")
    if case.truth_source == "live_db" and not case.truth_query:
        raise ValueError(f"{case.id}: live_db 题需 truth_query")
    if case.truth_source == "rubric" and not case.rubric:
        raise ValueError(f"{case.id}: rubric 题需 rubric")


def _case_from_dict(d: dict, file_forbidden: list) -> EvalCase:
    case = EvalCase(
        id=d["id"], skill=d["skill"], category=d["category"], description=d["description"],
        question=d["question"], env=dict(d.get("env") or {}), source=d["source"],
        truth_source=d["truth_source"], timeout=int(d.get("timeout", 300)),
        tags=list(d.get("tags") or []),
        expected_keywords=_coerce_str_list(d.get("expected_keywords")),
        expected_range=d.get("expected_range"),
        forbidden=_coerce_str_list(d.get("forbidden")) + _coerce_str_list(file_forbidden),
        truth_query=d.get("truth_query"), tolerance=float(d.get("tolerance", 0.0)),
        rubric=list(d.get("rubric") or []),
    )
    validate(case)
    return case


def load_file(path) -> list:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"{path}: 顶层需为 dict，含 cases 列表")
    file_forbidden = _coerce_str_list(data.get("forbidden_keywords"))
    return [_case_from_dict(dict(c), file_forbidden) for c in data["cases"]]


def load_all(cases_dir) -> list:
    all_cases, seen = [], set()
    for p in sorted(Path(cases_dir).glob("*.yaml")):
        for c in load_file(p):
            if c.id in seen:
                raise ValueError(f"重复 id: {c.id} (在 {p})")
            seen.add(c.id)
            all_cases.append(c)
    return all_cases
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest tests.test_eval_schema -v`
Expected: 4 PASS

- [ ] **Step 6: 提交**

```bash
git add eval/__init__.py eval/lib/__init__.py eval/lib/schema.py tests/test_eval_schema.py
git commit -m "feat(eval): EvalCase schema + 加载校验（统一评估集 Task 1）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: `eval/lib/judge.py` — inline 判分（复用 verify_output）

**Files:**
- Create: `eval/lib/judge.py`
- Test: `tests/test_eval_judge.py`

**Interfaces:**
- Consumes: `tests.reservoir_profile.verify_output`（不修改它）、`eval.lib.schema.EvalCase`
- Produces: `judge_inline(case, output)->{"verdict": "PASS"|"FAIL", "detail": dict}`。后续 task 复用同文件 `_keyword_check`、`_extract_numbers`。

- [ ] **Step 1: 写失败测试 `tests/test_eval_judge.py`**

```python
import unittest
from eval.lib.schema import EvalCase
from eval.lib import judge


def _case(**kw):
    base = dict(id="X", skill="forecasting", category="c", description="d", question="q",
                env={"SRM_TENANT_ID": 18}, source="s", truth_source="inline")
    base.update(kw)
    return EvalCase(**base)


class TestInlineJudge(unittest.TestCase):
    def test_pass_on_keywords_and_range(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        out = "当前水位 462.5 m"
        r = judge.judge_inline(c, out)
        self.assertEqual(r["verdict"], "PASS")

    def test_fail_when_range_misses(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        r = judge.judge_inline(c, "当前水位 500 m")
        self.assertEqual(r["verdict"], "FAIL")

    def test_fail_on_forbidden(self):
        c = _case(expected_keywords=["水位"], forbidden=["桃曲坡"])
        r = judge.judge_inline(c, "桃曲坡 当前水位 462 m")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("桃曲坡", r["detail"]["forbidden_hits"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_judge -v`
Expected: FAIL（`cannot import ... judge`）

- [ ] **Step 3: 写实现 `eval/lib/judge.py`**

```python
"""判分：inline（复用 reservoir_profile.verify_output）/ live_db / rubric / LLM-judge。"""
import re
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests.reservoir_profile import TestCase as RPCase, verify_output  # noqa: E402

_NUM_RE = re.compile(r"-?\d+\.?\d*")


def _extract_numbers(text):
    return [float(m) for m in _NUM_RE.findall(text or "")]


def _keyword_check(output, keywords):
    text = (output or "").lower()
    checks = [{"keyword": k, "found": str(k).lower() in text} for k in (keywords or [])]
    return {"keyword_checks": checks, "all_found": all(c["found"] for c in checks)}


def judge_inline(case, output: str) -> dict:
    """规则三判定：keywords + range + forbidden（顶层与题级已在 load 时并集进 case.forbidden）。"""
    rp = RPCase(id=case.id, skill=case.skill, description=case.description,
                question=case.question, expected_keywords=case.expected_keywords,
                expected_range=case.expected_range, timeout=case.timeout)
    v = verify_output(rp, output, case.forbidden)
    return {"verdict": "PASS" if v["all_passed"] else "FAIL", "detail": v}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_judge -v`
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/judge.py tests/test_eval_judge.py
git commit -m "feat(eval): inline 判分复用 verify_output（Task 2）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: `eval/lib/truth.py` — live_db 比较逻辑 + query_fn 工厂

**Files:**
- Create: `eval/lib/truth.py`
- Test: `tests/test_eval_truth.py`

**Interfaces:**
- Consumes: 无（纯逻辑 + 延迟 pymysql）
- Produces: `extract_numbers(text)->list[float]`、`compare_with_tolerance(numbers, truth, tolerance)->dict`、`make_db_query_fn(env)->Callable[[str],list]`。judge.py Task 4 消费 `compare_with_tolerance`。

- [ ] **Step 1: 写失败测试 `tests/test_eval_truth.py`**

```python
import unittest
from eval.lib.truth import extract_numbers, compare_with_tolerance


class TestTruth(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_numbers("水位 462.5m，降 12.3"), [462.5, 12.3])

    def test_compare_pass(self):
        r = compare_with_tolerance([462.4, 500.0], 462.5, 1.0)
        self.assertTrue(r["passed"])  # 462.4 在容差内

    def test_compare_fail(self):
        r = compare_with_tolerance([500.0], 462.5, 1.0)
        self.assertFalse(r["passed"])

    def test_make_query_fn_uses_injected_port(self):
        # make_db_query_fn 返回的闭包应执行给定 SQL；这里只验证它可调用且延迟导入
        from eval.lib import truth
        called = {}
        def fake_connect(*a, **k):
            class Cur:
                def execute(self, sql): called["sql"] = sql
                def fetchall(self): return [{"v": 7}]
                def __enter__(self): return self
                def __exit__(self, *a): pass
            class Conn:
                def cursor(self): return Cur()
            return Conn()
        orig = truth._connect
        truth._connect = fake_connect
        try:
            q = truth.make_db_query_fn({})
            rows = q("SELECT 1")
        finally:
            truth._connect = orig
        self.assertEqual(rows, [{"v": 7}])
        self.assertEqual(called["sql"], "SELECT 1")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_truth -v`
Expected: FAIL（`cannot import ... truth`）

- [ ] **Step 3: 写实现 `eval/lib/truth.py`**

```python
"""live_db 真值：纯比较逻辑 + DB query_fn 工厂（端口自 plan-gen eval.py::get_ground_truth）。"""
import os
import re

_NUM_RE = re.compile(r"-?\d+\.?\d*")


def extract_numbers(text):
    return [float(m) for m in _NUM_RE.findall(text or "")]


def compare_with_tolerance(numbers, truth, tolerance):
    passed = any(abs(n - truth) <= tolerance for n in numbers)
    return {"truth": truth, "tolerance": tolerance, "extracted": list(numbers), "passed": passed}


def _connect(env):
    """延迟导入 pymysql；连接参数读 SRM_DB_* env。可被测试替换。"""
    import pymysql  # 延迟导入：CI 无需安装
    return pymysql.connect(
        host=os.environ.get("SRM_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("SRM_DB_PORT", "3306")),
        user=os.environ.get("SRM_DB_USER", "root"),
        password=os.environ.get("SRM_DB_PASSWORD", ""),
        database=os.environ.get("SRM_DB_NAME", "powerelf_srm_yml"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def make_db_query_fn(env):
    """返回 Callable[[sql:str], list[dict]]。env 仅用于将来按租户切库；当前读全局 SRM_DB_*。"""
    conn = _connect(env)

    def _q(sql):
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    return _q
```

> 实施提示：若 `plan-generation/autoresearch-plan-skill/eval.py::get_ground_truth` 用的是别的连接方式（非 pymysql/非 DictCursor），按那个为准改 `_connect`，保持 `make_db_query_fn(env)` 签名不变。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_truth -v`
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/truth.py tests/test_eval_truth.py
git commit -m "feat(eval): live_db 真值比较 + query_fn 工厂（Task 3）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: `eval/lib/judge.py` — live_db + rubric 判分

**Files:**
- Modify: `eval/lib/judge.py`（追加两个函数）
- Modify: `tests/test_eval_judge.py`（追加用例）

**Interfaces:**
- Consumes: `eval.lib.truth.compare_with_tolerance`
- Produces: `judge_live_db(case, output, query_fn)->dict`、`judge_rubric(case, output, llm_fn=None)->dict`。`llm_fn` 签名 `(output, rubric)->{"passed":bool, "items":list}`，None 时 rubric 部分 skip。

- [ ] **Step 1: 追加失败测试到 `tests/test_eval_judge.py`**（在文件末尾 `unittest.main()` 之前插入）

```python
class TestLiveDbJudge(unittest.TestCase):
    def test_pass(self):
        c = _case(truth_source="live_db", truth_query="SELECT rsvr_rz FROM st_rsvr_r LIMIT 1",
                  tolerance=1.0, expected_keywords=["水位"])
        qf = lambda sql: [{"rsvr_rz": 462.5}]
        r = judge.judge_live_db(c, "当前水位 462.4 m", qf)
        self.assertEqual(r["verdict"], "PASS")

    def test_error_when_empty(self):
        c = _case(truth_source="live_db", truth_query="SELECT x", tolerance=1.0)
        r = judge.judge_live_db(c, "out", lambda sql: [])
        self.assertEqual(r["verdict"], "ERROR")


class TestRubricJudge(unittest.TestCase):
    def test_skip_without_llm(self):
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        r = judge.judge_rubric(c, "当前水位 462 m")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["detail"]["rubric"], "skip (no llm)")

    def test_fail_rule_layer_forbidden(self):
        c = _case(truth_source="rubric", rubric=["x"], forbidden=["桃曲坡"])
        r = judge.judge_rubric(c, "桃曲坡 结果", None)
        self.assertEqual(r["verdict"], "FAIL")

    def test_with_llm(self):
        c = _case(truth_source="rubric", rubric=["必须给数值"])
        fake = lambda out, rub: {"passed": True, "items": [{"criterion": "必须给数值", "pass": True}]}
        r = judge.judge_rubric(c, "ok", fake)
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("rubric_score", r["detail"])
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_judge -v`
Expected: 新用例 FAIL（`judge_live_db`/`judge_rubric` 不存在）

- [ ] **Step 3: 追加实现到 `eval/lib/judge.py`**（文件顶部已有的 `from tests.reservoir_profile ...` 之后追加 import；末尾追加函数）

在文件 import 区追加：
```python
from eval.lib.truth import compare_with_tolerance  # noqa: E402
```
在文件末尾追加：
```python
def judge_live_db(case, output: str, query_fn) -> dict:
    rows = query_fn(case.truth_query)
    if not rows:
        return {"verdict": "ERROR", "detail": {"reason": "truth_query 无结果"}}
    first = rows[0]
    truth = float(first[list(first)[0]]) if isinstance(first, dict) else float(first[0])
    cmp = compare_with_tolerance(_extract_numbers(output), truth, case.tolerance)
    kw = _keyword_check(output, case.expected_keywords)
    passed = cmp["passed"] and kw["all_found"]
    return {"verdict": "PASS" if passed else "FAIL", "detail": {"truth": truth, **cmp, **kw}}


def judge_rubric(case, output: str, llm_fn=None) -> dict:
    forb = [w for w in case.forbidden if str(w).lower() in (output or "").lower()]
    kw = _keyword_check(output, case.expected_keywords)
    rule_pass = kw["all_found"] and not forb
    if llm_fn is None:
        return {"verdict": "PASS" if rule_pass else "FAIL",
                "detail": {**kw, "forbidden_hits": forb, "rubric": "skip (no llm)"}}
    score = llm_fn(output, case.rubric)
    passed = rule_pass and score["passed"]
    return {"verdict": "PASS" if passed else "FAIL",
            "detail": {**kw, "forbidden_hits": forb, "rubric_score": score}}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_judge -v`
Expected: 全部（inline 3 + live_db 2 + rubric 3）PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/judge.py tests/test_eval_judge.py
git commit -m "feat(eval): live_db + rubric 判分（Task 4）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: `eval/lib/judge.py` — LLM-judge adapter（anthropic，可注入）

**Files:**
- Modify: `eval/lib/judge.py`（追加 `llm_judge`）
- Modify: `tests/test_eval_judge.py`（追加 FakeClient 用例）

**Interfaces:**
- Produces: `llm_judge(output, rubric, client=None)->{"passed":bool,"items":list[{"criterion","pass"}]}`。`client` 协议：`client.messages.create(model=,max_tokens=,messages=)->resp`，`resp.content` 为含 `.text` 的块列表。None 时延迟 `import anthropic` 建客户端（需 `ANTHROPIC_API_KEY`）。

- [ ] **Step 1: 追加失败测试**（`tests/test_eval_judge.py`）

```python
class TestLlmJudge(unittest.TestCase):
    def test_parses_strict_json(self):
        class B:
            def __init__(self, t): self.text = t
        class R:
            def __init__(self, t): self.content = [B(t)]
        class Client:
            def __init__(self, t): self._t = t
            class messages:
                @staticmethod
                def create(**kw):
                    return R('{"passed": true, "items": [{"criterion": "必须给数值", "pass": true}]}')
        r = judge.llm_judge("out", ["必须给数值"], client=Client())
        self.assertTrue(r["passed"])
        self.assertEqual(len(r["items"]), 1)

    def test_build_prompt_lists_all_rubric(self):
        prompt = judge._build_prompt("输出X", ["a", "b"])
        self.assertIn("a", prompt)
        self.assertIn("b", prompt)
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_judge.TestLlmJudge -v`
Expected: FAIL（`llm_judge`/`_build_prompt` 不存在）

- [ ] **Step 3: 追加实现到 `eval/lib/judge.py`**

```python
import json as _json


def _build_prompt(output, rubric):
    items = "\n".join(f"- {r}" for r in rubric)
    return (
        "你是水库调度 Skill 输出的验收评判员。按下述 rubric 逐条判定输出是否满足，"
        "只返回严格 JSON，不要任何额外文字。\n"
        f"rubric:\n{items}\n\n"
        f"待评判输出:\n{output}\n\n"
        '返回格式: {"passed": bool, "items": [{"criterion": str, "pass": bool}]}'
    )


def _parse_rubric_score(text, n):
    try:
        data = _json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        data = _json.loads(text[start:end + 1]) if start >= 0 else {}
    items = data.get("items", [])
    passed = data.get("passed", all(it.get("pass") for it in items)) if items else False
    return {"passed": bool(passed), "items": items}


def make_anthropic_client():
    import os
    try:
        import anthropic  # 延迟导入：可选依赖
    except ImportError as e:
        raise RuntimeError("LLM-judge 需要 anthropic SDK：pip install anthropic") from e
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def llm_judge(output, rubric, client=None):
    if client is None:
        client = make_anthropic_client()
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=512,
        messages=[{"role": "user", "content": _build_prompt(output, rubric)}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    return _parse_rubric_score(text, len(rubric))
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_judge.TestLlmJudge -v`
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/judge.py tests/test_eval_judge.py
git commit -m "feat(eval): LLM-judge adapter（可注入 client，延迟导入）（Task 5）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: `eval/lib/transport.py` — hermes 子进程（env 注入）

**Files:**
- Create: `eval/lib/transport.py`
- Test: `tests/test_eval_transport.py`

**Interfaces:**
- Consumes: 无
- Produces: `run_hermes(question, skill_id, env, timeout, skill_dir=None, _runner=subprocess.run)->{"output","stderr","exit_code","timed_out"}`。run.py Task 8 调用它（可注入 `_runner`）。

- [ ] **Step 1: 写失败测试 `tests/test_eval_transport.py`**

```python
import unittest
from eval.lib import transport


class FakeCompleted:
    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


class TestTransport(unittest.TestCase):
    def test_cmd_and_env_injection(self):
        seen = {}
        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            seen["env"] = kw["env"]
            seen["cwd"] = kw.get("cwd")
            return FakeCompleted(stdout="水位 462 m")
        r = transport.run_hermes("Q?", "forecasting", {"SRM_TENANT_ID": 20}, 60,
                                 skill_dir="/tmp/skill", _runner=fake_run)
        self.assertEqual(seen["cmd"], ["hermes", "chat", "-q", "Q?", "--skills", "forecasting", "-Q"])
        self.assertEqual(seen["env"]["SRM_TENANT_ID"], "20")
        self.assertIn("PATH", seen["env"])  # 合并了 os.environ
        self.assertEqual(seen["cwd"], "/tmp/skill")
        self.assertEqual(r["output"], "水位 462 m")
        self.assertFalse(r["timed_out"])

    def test_timeout(self):
        import subprocess
        def boom(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)
        r = transport.run_hermes("Q", "s", {}, 1, _runner=boom)
        self.assertTrue(r["timed_out"])
        self.assertIsNone(r["exit_code"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_transport -v`
Expected: FAIL（`cannot import ... transport`）

- [ ] **Step 3: 写实现 `eval/lib/transport.py`**

```python
"""hermes 子进程调用。端口自 test_skills.py::SkillTestRunner.run_test_case。"""
import os
import subprocess


def run_hermes(question, skill_id, env, timeout, skill_dir=None, _runner=subprocess.run):
    cmd = ["hermes", "chat", "-q", question, "--skills", skill_id, "-Q"]
    full_env = {**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}}
    try:
        r = _runner(cmd, capture_output=True, text=True, timeout=timeout,
                    cwd=str(skill_dir) if skill_dir else None, env=full_env)
        return {"output": (r.stdout or "").strip(), "stderr": (r.stderr or "").strip(),
                "exit_code": r.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"output": "", "stderr": "", "exit_code": None, "timed_out": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_transport -v`
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/transport.py tests/test_eval_transport.py
git commit -m "feat(eval): hermes transport（env 注入 + 超时）（Task 6）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: `eval/lib/report.py` — 结果/汇总/JSON/Markdown

**Files:**
- Create: `eval/lib/report.py`
- Test: `tests/test_eval_report.py`

**Interfaces:**
- Produces: `build_result(case, status, elapsed, output, verdict_detail)->dict`、`summarize(results)->{"by_skill":..., "overall":{"pass","total","rate"}}`、`write_json(results,summary,path)`、`write_markdown(results,summary,path)`。

- [ ] **Step 1: 写失败测试 `tests/test_eval_report.py`**

```python
import json, unittest
from pathlib import Path
from eval.lib.schema import EvalCase
from eval.lib import report


def _c(i, skill, cat):
    return EvalCase(id=i, skill=skill, category=cat, description="d", question="q",
                    env={"SRM_TENANT_ID": 18}, source="s", truth_source="inline")


class TestReport(unittest.TestCase):
    def test_build_result_truncates(self):
        r = report.build_result(_c("1", "f", "c"), "PASS", 1.234, "x" * 600, {})
        self.assertTrue(r["output"].endswith("..."))
        self.assertEqual(r["elapsed_seconds"], 1.23)

    def test_summarize_skill_category(self):
        results = [
            report.build_result(_c("1", "f", "水位"), "PASS", 1, "o", {}),
            report.build_result(_c("2", "f", "水位"), "FAIL", 1, "o", {}),
            report.build_result(_c("3", "f", "降雨"), "PASS", 1, "o", {}),
        ]
        s = report.summarize(results)
        self.assertEqual(s["overall"], {"pass": 2, "total": 3, "rate": 0.667})
        self.assertEqual(s["by_skill"]["f"]["水位"], {"pass": 1, "total": 2, "rate": 0.5})

    def test_write_json_and_markdown(self):
        import tempfile
        results = [report.build_result(_c("1", "f", "c"), "PASS", 1, "o", {})]
        s = report.summarize(results)
        with tempfile.TemporaryDirectory() as d:
            jp, mp = Path(d) / "r.json", Path(d) / "r.md"
            report.write_json(results, s, jp)
            report.write_markdown(results, s, mp)
            self.assertEqual(json.loads(jp.read_text())["summary"]["overall"]["pass"], 1)
            self.assertIn("# 评估报告", mp.read_text())

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_report -v`
Expected: FAIL（`cannot import ... report`）

- [ ] **Step 3: 写实现 `eval/lib/report.py`**

```python
"""评估报告：逐题结果 + skill×category 汇总 + JSON/Markdown 落盘。"""
import json
from collections import defaultdict
from pathlib import Path


def build_result(case, status, elapsed, output, verdict_detail):
    out = output or ""
    out = (out[:500] + "...") if len(out) > 500 else out
    return {"id": case.id, "skill": case.skill, "category": case.category,
            "description": case.description, "question": case.question,
            "status": status, "elapsed_seconds": round(elapsed, 2),
            "output": out, "verdict": verdict_detail}


def summarize(results):
    agg = defaultdict(lambda: {"pass": 0, "total": 0})
    for r in results:
        a = agg[(r["skill"], r["category"])]
        a["total"] += 1
        if r["status"] == "PASS":
            a["pass"] += 1
    by_skill = {}
    for (skill, cat), v in sorted(agg.items()):
        by_skill.setdefault(skill, {})[cat] = {
            "pass": v["pass"], "total": v["total"], "rate": round(v["pass"] / v["total"], 3)}
    total = len(results)
    p = sum(1 for r in results if r["status"] == "PASS")
    return {"by_skill": by_skill, "overall": {"pass": p, "total": total, "rate": round(p / total, 3) if total else 0}}


def write_json(results, summary, path):
    Path(path).write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def write_markdown(results, summary, path):
    o = summary["overall"]
    lines = ["# 评估报告", "",
             f"总通过率: {o['pass']}/{o['total']} = {o['rate']}", ""]
    for skill, cats in summary["by_skill"].items():
        lines += [f"## {skill}", "| category | pass/total | rate |", "|---|---|---|"]
        lines += [f"| {c} | {v['pass']}/{v['total']} | {v['rate']} |" for c, v in cats.items()]
        lines.append("")
    lines.append("## 逐题")
    mark = lambda s: "x" if s != "PASS" else "PASS"
    lines += [f"- [{mark(r['status'])}] {r['id']} ({r['skill']}/{r['category']}) — {r['description']}"
              for r in results]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_report -v`
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add eval/lib/report.py tests/test_eval_report.py
git commit -m "feat(eval): 报告汇总 + JSON/Markdown 落盘（Task 7）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: `eval/run.py` — CLI（发现/过滤/分发/报告/退出码）

**Files:**
- Create: `eval/run.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: 全部前序 lib；`lib/paths.py`（`get_skill_dir`、`RESULTS_DIR`、`ensure_dirs`）——沿用 `test_skills.py` 的 `sys.path.insert(0, lib)` 用法。
- Produces: `main(argv, transport_fn=None, query_fn=None, llm_on=False, report_dir=None)->int`（退出码）；`parse_args(argv)`；`filter_cases(cases, args)`。

- [ ] **Step 1: 写失败测试 `tests/test_eval_runner.py`**

```python
import pathlib
import unittest
from eval import run as runmod  # eval/run.py 是合法模块名（eval/__init__.py 已在 Task 1 建立）


class TestRunner(unittest.TestCase):

    def _cases_yaml(self, tmp):
        (pathlib.Path(tmp) / "forecasting.yaml").write_text(
            "cases:\n"
            "  - {id: F1, skill: forecasting, category: c, description: d, question: q1,\n"
            "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: inline,\n"
            "     expected_keywords: [水位]}\n"
            "  - {id: F2, skill: forecasting, category: c, description: d, question: q2,\n"
            "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: inline,\n"
            "     expected_keywords: [不存在词]}\n", encoding="utf-8")

    def test_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            rc = runmod.main(["--list", "--cases-dir", d])
            self.assertEqual(rc, 0)

    def test_filter_and_run_with_fake_transport(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                return {"output": "当前水位 462 m", "stderr": "", "exit_code": 0, "timed_out": False}
            rc = runmod.main(["--skill", "forecasting", "--cases-dir", d,
                              "--report-dir", d], transport_fn=fake_transport)
            self.assertEqual(rc, 1)  # F2 FAIL（缺"不存在词"）→ 有 FAIL → 退出码 1

    def test_all_pass_exit_zero(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                # 让两题都过：输出含两题的关键词
                return {"output": "水位 不存在词 都在", "stderr": "", "exit_code": 0, "timed_out": False}
            rc = runmod.main(["--cases-dir", d, "--report-dir", d], transport_fn=fake_transport)
            self.assertEqual(rc, 0)

if __name__ == "__main__":
    unittest.main()
```

> 注意：`main` / `parse_args` / `filter_cases` 须挂在 `eval/run.py` 模块顶层（非 `__main__` guard 内），测试才能 `from eval import run` 后调用。`sys.exit(main())` 放在 `if __name__ == "__main__":` 下。

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_runner -v`
Expected: FAIL（`eval/run.py` 不存在 / `main` 不存在）

- [ ] **Step 3: 写实现 `eval/run.py`**

```python
#!/usr/bin/env python3
"""统一评估集 runner：发现 → 过滤 → 传输 → 判分 → 报告 → 退出码。

用法：
  python3 eval/run.py --list
  python3 eval/run.py --skill forecasting
  python3 eval/run.py --subset smoke
  python3 eval/run.py --truth live_db            # 仅跑某类真值
  python3 eval/run.py --llm                        # 启用 LLM-judge（需 ANTHROPIC_API_KEY）
"""
import argparse
import os
import sys
import time
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from paths import get_skill_dir, RESULTS_DIR, ensure_dirs  # noqa: E402  (项目 lib/paths.py)
from eval.lib.schema import load_all  # noqa: E402
from eval.lib import judge, transport, truth, report  # noqa: E402


def parse_args(argv):
    p = argparse.ArgumentParser(description="统一评估集 runner")
    p.add_argument("--cases-dir", default=str(Path(__file__).parent / "cases"))
    p.add_argument("--report-dir", default=str(RESULTS_DIR))
    p.add_argument("--skill")
    p.add_argument("--subset", choices=["smoke", "full"])
    p.add_argument("--tag")
    p.add_argument("--id")
    p.add_argument("--truth", choices=["inline", "live_db", "rubric"])
    p.add_argument("--llm", action="store_true", help="启用 LLM-judge（rubric 题）")
    p.add_argument("--list", action="store_true", help="仅列出用例")
    return p.parse_args(argv)


def filter_cases(cases, args):
    out = cases
    if args.skill:
        out = [c for c in out if c.skill == args.skill]
    if args.subset == "smoke":
        out = [c for c in out if "smoke" in c.tags]
    if args.tag:
        out = [c for c in out if args.tag in c.tags]
    if args.id:
        out = [c for c in out if c.id == args.id]
    if args.truth:
        out = [c for c in out if c.truth_source == args.truth]
    return out


def _dispatch(case, out, query_fn, llm_on):
    if case.truth_source == "inline":
        return judge.judge_inline(case, out)
    if case.truth_source == "live_db":
        if query_fn is None:
            return {"verdict": "ERROR", "detail": {"reason": "无 DB 连接"}}
        return judge.judge_live_db(case, out, query_fn)
    # rubric
    llm_fn = None
    if llm_on and os.environ.get("ANTHROPIC_API_KEY"):
        llm_fn = lambda o, r: judge.llm_judge(o, r)  # 真实客户端
    return judge.judge_rubric(case, out, llm_fn)


def main(argv=None, transport_fn=None, query_fn=None, llm_on=False, report_dir=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cases = load_all(args.cases_dir)
    selected = filter_cases(cases, args)
    if args.list:
        for c in selected:
            print(f"{c.id}\t{c.skill}\t{c.category}\t{c.truth_source}\t{c.description}")
        return 0

    if transport_fn is None:
        transport_fn = transport.run_hermes
    if query_fn is None and any(c.truth_source == "live_db" for c in selected):
        query_fn = truth.make_db_query_fn({})  # 建一次连接复用
    llm_on = llm_on or args.llm

    results = []
    for i, c in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {c.id} ({c.skill}/{c.category})", flush=True)
        t0 = time.time()
        r = transport_fn(c.question, c.skill, c.env, c.timeout, skill_dir=str(get_skill_dir(c.skill)))
        elapsed = time.time() - t0
        if r.get("timed_out"):
            v = {"verdict": "TIMEOUT", "detail": {"reason": f"超时 {c.timeout}s"}}
        else:
            v = _dispatch(c, r.get("output", ""), query_fn, llm_on)
        status = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR", "TIMEOUT": "TIMEOUT"}.get(v["verdict"], "ERROR")
        results.append(report.build_result(c, status, elapsed, r.get("output", ""), v["detail"]))
        print(f"   -> {status}", flush=True)
        if i < len(selected):
            time.sleep(2)  # 限流退避

    summary = report.summarize(results)
    ensure_dirs()
    out_dir = Path(report_dir or args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    report.write_json(results, summary, out_dir / f"eval-{ts}.json")
    report.write_markdown(results, summary, out_dir / f"eval-{ts}.md")
    print(f"\n{summary['overall']}")
    return 0 if summary["overall"]["pass"] == summary["overall"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

> 实施提示：`lib/paths.py` 的 `RESULTS_DIR` 与 `get_skill_dir` 沿用 `test_skills.py` 既有用法；若实际导出名不同，按 `test_skills.py:33-40` 的 import 为准调整，保持 `main()` 签名不变。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_runner -v`
Expected: 3 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover tests -v`
Expected: 全部 eval 测试 + 既有 85 用例 PASS（个别 health 用例 SKIP）

- [ ] **Step 6: 提交**

```bash
git add eval/run.py tests/test_eval_runner.py
git commit -m "feat(eval): 统一 runner CLI（发现/过滤/分发/报告/退出码）（Task 8）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: 6 个 `cases/*.yaml` 起步集（cull 到 ~130）+ README

**Files:**
- Create: `eval/cases/forecasting.yaml`, `plan-generation.yaml`, `simulation.yaml`, `early-warning.yaml`, `diagnosis-verification.yaml`, `supervisor.yaml`
- Create: `eval/README.md`
- Test: `tests/test_eval_cases.py`

**Cull 规则（来自 spec §10，逐 skill 执行）：**
1. v1（技术向）与 v2（业务/口语向）合并：每 category 各留覆盖代表题，语义重复去重。
2. 优先留带 ground truth 的：forecasting `test-questions.md` 里带 `Expected 数据点` 的全留，转 `live_db`（`truth_query` 查 `st_rsvr_r.rsvr_rz` 等）或 `inline + expected_range`。
3. 每 category 留 1 正常 + 1 边界 + 1 异常（异常题来自 simulation `_异常/_边界` 分类、early-warning missing-data/high-risk SQL 场景）。
4. 目标存量：forecasting ~25 / plan-generation ~25 / simulation ~30 / early-warning ~30 / supervisor ~10 / diagnosis-verification ~10 ≈ **130**。
5. 每题 `source` 字段溯源旧文件（如 `forecasting/tests/test-questions.md::Q3`、`test_skills.py::F1`、`supervisor/demo-output/A-...json`）。

**题源清单（implementer 逐文件读取后精选）：**
- forecasting: `forecasting/tests/test-questions.md`（带 `Expected 数据点`）、`test-questions-v2.md`、`test_skills.py FORECASTING_TESTS F1-F6`
- plan-generation: `plan-generation/tests/test-questions.md`、`-v2.md`、`autoresearch-plan-skill/eval.py TEST_INPUTS`（5 道，已 100%）
- simulation: `simulation/tests/test-questions.md`、`autoresearch-simulation/questions.tsv`（按 `evaluator.py CATEGORY_MAP` 的 22 类各留代表）
- early-warning: `early-warning/autoresearch-v3/test-inputs.md`（103 题按 `test-data-scenarios.md` 15 场景矩阵各留代表）
- supervisor: 由 `supervisor/demo-output/A|B|C|D-*.json`（四场景）转 4 组题（每组正常+边界）
- diagnosis-verification: `diagnosis-verification/tests/test-cases.md`（5 道）+ 少量补

- [ ] **Step 1: 写 schema/count 守卫测试 `tests/test_eval_cases.py`**

```python
import unittest
from pathlib import Path
from eval.lib.schema import load_all

CASES_DIR = Path(__file__).resolve().parents[1] / "eval" / "cases"
TARGETS = {  # skill -> (min, max)
    "forecasting": (20, 30), "plan-generation": (20, 30), "simulation": (25, 35),
    "early-warning": (25, 35), "supervisor": (8, 15), "diagnosis-verification": (8, 15),
}


class TestCases(unittest.TestCase):
    def test_all_load_and_unique(self):
        cases = load_all(CASES_DIR)
        self.assertGreater(len(cases), 0)

    def test_per_skill_counts_in_target(self):
        cases = load_all(CASES_DIR)
        from collections import Counter
        cnt = Counter(c.skill for c in cases)
        for skill, (lo, hi) in TARGETS.items():
            self.assertIn(skill, cnt, f"缺 skill: {skill}")
            self.assertGreaterEqual(cnt[skill], lo, f"{skill} 题太少 {cnt[skill]}")
            self.assertLessEqual(cnt[skill], hi, f"{skill} 题太多 {cnt[skill]}")

    def test_total_in_balanced_band(self):
        cases = load_all(CASES_DIR)
        self.assertGreaterEqual(len(cases), 100)
        self.assertLessEqual(len(cases), 180)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_eval_cases -v`
Expected: FAIL（`eval/cases/` 无 yaml）

- [ ] **Step 3: 写 6 个 YAML 文件**

每个文件结构（示例 `forecasting.yaml` 开头；其余按 cull 规则填）：

```yaml
# forecasting 评估集（cull 自 forecasting/tests/test-questions*.md + test_skills.py F1-F6）
# 顶层 forbidden_keywords 可留空；taoqupo 专用文件可顶层禁 ["三岔"]
forbidden_keywords: []
cases:
  - id: F1
    skill: forecasting
    category: 水位查询
    description: 查询当前水位
    question: "查询三岔水库当前水位（只返回数值）"
    env: {SRM_TENANT_ID: 18, SRM_RESERVOIR_NAME: sancha}
    timeout: 60
    tags: [smoke]
    source: test_skills.py::F1
    truth_source: inline
    expected_keywords: ["水位", "m"]
    expected_range: {min: 459, max: 463}
  - id: F2
    skill: forecasting
    category: 水位查询
    description: 水位 live_db 校验
    question: "三岔水库当前水位是多少？"
    env: {SRM_TENANT_ID: 18, SRM_RESERVOIR_NAME: sancha}
    source: forecasting/tests/test-questions.md::水位题
    truth_source: live_db
    truth_query: "SELECT rsvr_rz FROM st_rsvr_r WHERE stcd='三岔站' ORDER BY idtm DESC LIMIT 1"
    tolerance: 1.0
    expected_keywords: ["水位"]
  # …继续按 cull 规则补到 ~25 题，覆盖 各 category × 正常/边界/异常
```

> 其余 5 个文件同理：`plan-generation.yaml` 把 `eval.py` 的 5 道原样迁入（`source: eval.py::T1`）+ cull 到 ~25；`simulation.yaml` 按 22 类各留代表到 ~30；`early-warning.yaml` 按 15 场景矩阵留代表到 ~30；`supervisor.yaml` 由 demo-output 四场景转 ~10；`diagnosis-verification.yaml` 现有 5 + 补到 ~10。每题 `env` 至少含 `SRM_TENANT_ID`（三岔=18 / 桃曲坡=20）。`truth_source` 按题选：可数值校验→`inline`/`live_db`；报告/叙述类→`rubric`（rubric 要点从对应 SKILL.md 的验收清单抄）。

- [ ] **Step 4: 写 `eval/README.md`**

```markdown
# 统一评估集（eval/）

## 跑评估（需 hermes 平台 + 真网 DB）
    python3 eval/run.py --list
    python3 eval/run.py --skill forecasting
    python3 eval/run.py --subset smoke
    python3 eval/run.py --llm          # 启用 LLM-judge（需 ANTHROPIC_API_KEY）

报告输出到 `results/eval-<ts>.{json,md}`。退出码：全 PASS=0，否则=1。

## 加题
在 `cases/<skill>.yaml` 的 `cases:` 下加一条，必填：id（全库唯一）/ skill / category / description / question / env（含 SRM_TENANT_ID）/ source / truth_source，再按 truth_source 配字段（见 schema §6）。`truth_source`：inline（关键词/区间/禁词）、live_db（truth_query + tolerance）、rubric（rubric 要点 + 可选 LLM）。

## 判分
inline/live_db 零依赖规则判分（复用 `tests/reservoir_profile.py::verify_output`）；rubric 默认规则层 + skip，`--llm` 才按 rubric 打分。

## 与旧资产的关系（方案 A 渐进迁移）
本集取代旧硬编码集合（`test_skills.py` / 各 `eval.py`）与人工 markdown 题库（已标存档）。旧脚本暂不删，后续逐文件退役。
```

- [ ] **Step 5: 运行确认通过**

Run: `python3 -m unittest tests.test_eval_cases -v`
Expected: 3 PASS

- [ ] **Step 6: 提交**

```bash
git add eval/cases/ eval/README.md tests/test_eval_cases.py
git commit -m "feat(eval): 6 skill 起步题集（cull ~130）+ README（Task 9）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: CI 接 `unittest discover`

**Files:**
- Modify: `.github/workflows/auto-merge.yml:30-47`（Install dependencies + Run tests on PR）

**Interfaces:**
- 无新接口；让 PR 真跑 `python3 -m unittest discover tests`（无 DB，~85+ 用例）。

- [ ] **Step 1: 改 Install dependencies 步骤（第 30-33 行）**

把：
```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          # Add any Python dependencies needed for test_skills.py
```
改为：
```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pyyaml
```

- [ ] **Step 2: 改 Run tests on PR 步骤（第 35-47 行）**

把：
```yaml
      - name: Run tests on PR
        if: github.event_name == 'pull_request'
        env:
          HERMES_YOLO_MODE: 1
          SRM_DB_HOST: ${{ secrets.SRM_DB_HOST }}
          SRM_DB_PORT: ${{ secrets.SRM_DB_PORT }}
          SRM_DB_NAME: ${{ secrets.SRM_DB_NAME }}
          SRM_DB_USER: ${{ secrets.SRM_DB_USER }}
          SRM_DB_PASSWORD: ${{ secrets.SRM_DB_PASSWORD }}
        run: |
          echo "Running multi-skill tests..."
          # Uncomment below when hermes is available in CI
          # python3 test_skills.py --all --timeout 300
```
改为（unittest 无需 DB secret；hermes 行保留注释）：
```yaml
      - name: Run tests on PR
        if: github.event_name == 'pull_request'
        run: |
          echo "Running unit/integration tests (no DB required)..."
          python3 -m unittest discover tests
          # Uncomment below when hermes is available in CI
          # python3 test_skills.py --all --timeout 300
```

- [ ] **Step 3: 本地验证这条命令就是 CI 要跑的**

Run: `python3 -m unittest discover tests`
Expected: 全部 PASS（个别 health 用例 SKIP），退出码 0

- [ ] **Step 4: 校验 workflow YAML 语法**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/auto-merge.yml'))"`
Expected: 无异常

- [ ] **Step 5: 提交**

```bash
git add .github/workflows/auto-merge.yml
git commit -m "ci: PR 真跑 unittest discover（无需 DB）+ 装 pyyaml（Task 10）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: 旧 markdown 题库标存档

**Files:**
- Modify（顶部加横幅，不改其余内容）：
  - `plan-generation/tests/test-questions.md`、`test-questions-v2.md`
  - `forecasting/tests/test-questions.md`、`test-questions-v2.md`
  - `simulation/tests/test-questions.md`
  - `early-warning/autoresearch-v3/test-inputs.md`
  - `diagnosis-verification/tests/test-cases.md`

**Interfaces:** 无（纯文档标注）。

- [ ] **Step 1: 给每个文件顶部加横幅**

横幅内容（`<skill>` 替换为对应 skill 名）：
```
> ⚠️ 已迁入 `eval/cases/<skill>.yaml`（统一评估集）。本文件为历史存档，不再维护，仅作题源追溯。新题请加到 `eval/cases/`。
```
用 Edit 工具在每个文件**首行之前**插入该横幅 + 空行。逐文件操作（不要用 sed 批量，避免误伤）。

- [ ] **Step 2: 验证横幅已加**

Run: `grep -rL "已迁入 \`eval/cases" plan-generation/tests/test-questions*.md forecasting/tests/test-questions*.md simulation/tests/test-questions.md early-warning/autoresearch-v3/test-inputs.md diagnosis-verification/tests/test-cases.md`
Expected: 无输出（全部文件都含横幅）

- [ ] **Step 3: 提交**

```bash
git add plan-generation/tests/test-questions*.md forecasting/tests/test-questions*.md simulation/tests/test-questions.md early-warning/autoresearch-v3/test-inputs.md diagnosis-verification/tests/test-cases.md
git commit -m "docs(eval): 旧 markdown 题库标存档（已迁入 eval/cases）（Task 11）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 验收（整体）

跑完所有 task 后：
- [ ] `python3 -m unittest discover tests` 全绿（含新增 `test_eval_*` 7 个文件 + 既有 85）
- [ ] `python3 eval/run.py --list` 列出 ~130 题，无 schema 错
- [ ] `python3 eval/run.py --subset smoke` 在现网（hermes+DB）跑通，产出 `results/eval-*.{json,md}`，逐题 status 明确
- [ ] CI workflow 已改：PR 跑 `unittest discover` + 装 pyyaml
- [ ] 7 个旧 markdown 顶部已标存档；旧脚本未被修改
- [ ] 对应 spec `docs/superpowers/specs/2026-08-12-eval-set-consolidation-design.md` §13 全部成功标准达成
