# 测试层多水库参数化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `test_skills.py` 从三岔硬编码改造成 per-reservoir yaml 驱动的多水库测试框架，支持双水库回归 + 自动防串库。

**Architecture:** 纯逻辑（yaml 加载 + 三判定 keywords/range/forbidden + 数值提取）抽到 `tests/reservoir_profile.py`，用 unittest 单测覆盖；`test_skills.py` 改为 profile 驱动的 runner（hermes 子进程注入 `SRM_TENANT_ID`/`SRM_RESERVOIR_NAME` env）；每水库一个 yaml 用例集；顺手补 `f_rnfl_h` 查询的 tenant 过滤。

**Tech Stack:** Python 3 标准库 + PyYAML 6.0.3（已装）+ unittest（项目无 pytest）；hermes CLI；MySQL `powerelf_srm_yml`。

## Global Constraints

- **不引入新依赖**：PyYAML 已装；单测用 **unittest**（`python3 -m unittest`），不要 pytest。
- **hermes 调用**：`hermes chat -q "<question>" --skills <skill_id> -Q --max-turns 25 --yolo`，子进程必须注入 env。
- **租户身份**：`SRM_TENANT_ID` + `SRM_RESERVOIR_NAME` 两个 env 决定 agent 读哪个 profile / 查哪个 tenant 的数据。
- **现网表已有 tenant_id**：`f_rnfl_h`、曲线表均已有 `tenant_id` 列（代码旧注释"无 tenant"已过时）。
- **DB 环境**：运行前 `set -a; source /root/.hermes/.env; set +a` 加载 `SRM_DB_*`。
- **提交规范**：每个 Task 末尾 commit，message 末尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- **分支**：`feat/multi-reservoir`（当前分支，直接提交）。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `tests/__init__.py` | 使 tests 成包（空文件） | 新建 |
| `tests/reservoir_profile.py` | 数据类 + yaml 加载 + 三判定逻辑 + 数值提取（纯逻辑，无 hermes/DB） | 新建 |
| `tests/test_judge.py` | unittest 单测：判定逻辑 + yaml 加载 | 新建 |
| `tests/reservoirs/sancha.yaml` | 三岔用例集（迁移现有 F1-F6/PG1-3/SIM1-2） | 新建 |
| `tests/reservoirs/taoqupo.yaml` | 桃曲坡静态类用例集 | 新建 |
| `test_skills.py` | profile 驱动 runner + env 注入 + CLI + 修 TEST_RESULTS_DIR bug | 改 |
| `forecasting/scripts/query_forecast_data.py` | `query_rainfall_forecast` 补 tenant 过滤 | 改 |
| `forecasting/scripts/query_forecast_analysis.py` | `query_fusion_detail` 的 f_rnfl_h 段补 tenant 过滤 | 改 |
| `plan-generation/scripts/query_plan_data.py` | `query_rainfall_forecast` 补 tenant 过滤（含子查询） | 改 |

---

### Task 1: 判定逻辑 + profile 数据类 + yaml 加载（TDD / unittest）

**Files:**
- Create: `tests/__init__.py`、`tests/reservoir_profile.py`、`tests/test_judge.py`

**Interfaces:**
- Produces: `ReservoirProfile`、`TestCase`（dataclass）；`load_reservoir(path: Path) -> ReservoirProfile`；`load_all_reservoirs(base: Path) -> dict[str, ReservoirProfile]`；`verify_output(case, output, forbidden_keywords) -> dict`；`_extract_numbers(text) -> list[float]`。Task 3 依赖这些。

- [ ] **Step 1: 写失败单测 `tests/test_judge.py`**

```python
import unittest
from pathlib import Path
from tests.reservoir_profile import (
    verify_output, _extract_numbers, load_reservoir, TestCase,
)


class TestExtractNumbers(unittest.TestCase):
    def test_int_and_float(self):
        self.assertEqual(_extract_numbers("水位 786.8m，约 786"), [786.8, 786.0])

    def test_none_when_no_number(self):
        self.assertEqual(_extract_numbers("无数据"), [])

    def test_negative(self):
        self.assertEqual(_extract_numbers("蒸发 -15.7"), [-15.7])


class TestVerifyOutput(unittest.TestCase):
    def _case(self, **kw):
        base = dict(id="X", skill="s", description="d", question="q",
                    expected_keywords=["786.8", "汛限"])
        base.update(kw)
        return TestCase(**base)

    def test_keywords_pass(self):
        c = self._case()
        r = verify_output(c, "主汛限水位 786.8m", forbidden=[])
        self.assertTrue(r["all_passed"])
        self.assertEqual(r["forbidden_hits"], [])

    def test_keywords_miss_fails(self):
        c = self._case()
        r = verify_output(c, "正常蓄水位 788.5m", forbidden=[])
        self.assertFalse(r["all_passed"])

    def test_range_pass_when_any_in_range(self):
        c = self._case(expected_range={"min": 786.5, "max": 787.0})
        r = verify_output(c, "约 786.8 到 790 之间", forbidden=[])
        self.assertTrue(r["range_passed"])

    def test_range_fail_when_none_in_range(self):
        c = self._case(expected_range={"min": 786.5, "max": 787.0})
        r = verify_output(c, "水位 790.5m", forbidden=[])
        self.assertFalse(r["range_passed"])
        self.assertFalse(r["all_passed"])

    def test_forbidden_hit_overrides_to_fail(self):
        c = self._case()
        r = verify_output(c, "汛限 786.8 参考 三岔 水库", forbidden=["三岔", "462.5"])
        self.assertEqual(r["forbidden_hits"], ["三岔"])
        self.assertFalse(r["all_passed"])

    def test_no_range_skips_range_check(self):
        c = self._case()  # 无 expected_range
        r = verify_output(c, "汛限 786.8", forbidden=[])
        self.assertNotIn("range_passed", r)  # 无该字段视为不检查


class TestLoadReservoir(unittest.TestCase):
    def test_load_minimal_yaml(self):
        import tempfile, os
        yml = """
name: taoqupo
tenant_id: 20
display_name: 桃曲坡水库
forbidden_keywords: [三岔, 462.5]
cases:
  - id: TQ-PG1
    skill: plan-generation
    description: 汛限
    question: 主汛限水位？
    expected_keywords: [786.8, 汛限]
    expected_range: {min: 786.5, max: 787.0}
    timeout: 120
"""
        d = tempfile.mkdtemp()
        p = Path(d) / "taoqupo.yaml"
        p.write_text(yml, encoding="utf-8")
        prof = load_reservoir(p)
        self.assertEqual(prof.name, "taoqupo")
        self.assertEqual(prof.tenant_id, 20)
        self.assertEqual(prof.forbidden_keywords, ["三岔", "462.5"])
        self.assertEqual(len(prof.cases), 1)
        self.assertEqual(prof.cases[0].id, "TQ-PG1")
        self.assertEqual(prof.cases[0].expected_range, {"min": 786.5, "max": 787.0})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑单测确认失败**

Run: `python3 -m unittest tests.test_judge -v`
Expected: FAIL（`ModuleNotFoundError: tests.reservoir_profile`）

- [ ] **Step 3: 实现 `tests/__init__.py`（空文件）+ `tests/reservoir_profile.py`**

`tests/__init__.py`：空文件。

`tests/reservoir_profile.py`：
```python
"""Reservoir test profile: yaml 加载 + 三判定逻辑（纯逻辑，无 hermes/DB 依赖）。"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_NUMBER_RE = re.compile(r"-?\d+\.?\d*")


@dataclass
class TestCase:
    id: str
    skill: str
    description: str
    question: str
    expected_keywords: list = field(default_factory=list)
    expected_range: Optional[dict] = None   # {"min": float, "max": float}
    timeout: Optional[int] = None


@dataclass
class ReservoirProfile:
    name: str                       # = SRM_RESERVOIR_NAME
    tenant_id: int                  # = SRM_TENANT_ID
    display_name: str
    forbidden_keywords: list = field(default_factory=list)
    cases: list = field(default_factory=list)   # list[TestCase]


def _extract_numbers(text: str) -> list:
    """从文本提取所有数值（含小数/负数）。"""
    out = []
    for m in _NUMBER_RE.findall(text or ""):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def verify_output(case: TestCase, output: str, forbidden: list) -> dict:
    """三判定：keywords（子串，大小写不敏感）+ range（任一数值落区间）+ forbidden（任一命中即 FAIL）。

    返回 {keyword_checks, all_keywords_found, range_passed(可选),
          forbidden_hits, all_passed, reasons}。
    """
    text = (output or "").lower()
    reasons = []

    # 1. keywords
    keyword_checks = []
    all_kw = True
    for kw in (case.expected_keywords or []):
        found = str(kw).lower() in text
        keyword_checks.append({"keyword": kw, "found": found})
        if not found:
            all_kw = False
    if not all_kw:
        reasons.append("keywords 未全命中")

    # 2. range（可选）
    range_passed = None
    if case.expected_range:
        lo = case.expected_range["min"]
        hi = case.expected_range["max"]
        nums = _extract_numbers(output)
        range_passed = any(lo <= n <= hi for n in nums)
        if not range_passed:
            reasons.append(f"无数值落在 [{lo}, {hi}]")

    # 3. forbidden（顶层继承）
    forbidden_hits = [w for w in (forbidden or []) if str(w).lower() in text]
    if forbidden_hits:
        reasons.append(f"命中禁词: {forbidden_hits}")

    all_passed = all_kw and (range_passed is None or range_passed) and not forbidden_hits
    result = {
        "keyword_checks": keyword_checks,
        "all_keywords_found": all_kw,
        "forbidden_hits": forbidden_hits,
        "all_passed": all_passed,
        "reasons": reasons,
    }
    if case.expected_range:
        result["range_passed"] = range_passed
    return result


def load_reservoir(path: Path) -> ReservoirProfile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cases = [TestCase(**c) for c in (data.get("cases") or [])]
    return ReservoirProfile(
        name=data["name"],
        tenant_id=int(data["tenant_id"]),
        display_name=data.get("display_name", data["name"]),
        forbidden_keywords=data.get("forbidden_keywords") or [],
        cases=cases,
    )


def load_all_reservoirs(base: Path) -> dict:
    """base 目录下所有 *.yaml → {name: ReservoirProfile}。"""
    profiles = {}
    for p in sorted(Path(base).glob("*.yaml")):
        prof = load_reservoir(p)
        profiles[prof.name] = prof
    return profiles
```

- [ ] **Step 4: 跑单测确认通过**

Run: `python3 -m unittest tests.test_judge -v`
Expected: 7 个 test 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/reservoir_profile.py tests/test_judge.py
git commit -m "feat(tests): 判定逻辑 + reservoir profile 加载（unittest 覆盖）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: sancha + taoqupo yaml 用例集

**Files:**
- Create: `tests/reservoirs/sancha.yaml`、`tests/reservoirs/taoqupo.yaml`

**Interfaces:**
- Consumes: `load_reservoir`（Task 1）。
- Produces: 两个 yaml，供 Task 3 的 runner 加载。

- [ ] **Step 1: 写 `tests/reservoirs/sancha.yaml`**（迁移现有 FORECASTING/PLAN/SIMULATION 用例，数值不变）

```yaml
name: sancha
tenant_id: 18
display_name: 三岔水库
forbidden_keywords: [桃曲坡, 786.8, 788.5, 790.5, 788.54]
cases:
  - {id: SC-F1, skill: forecasting, description: 查询当前水位,
     question: 查询三岔水库当前水位（只返回数值）,
     expected_keywords: [462, 水位, m], timeout: 60}
  - {id: SC-F2, skill: forecasting, description: 未来24小时降雨预报,
     question: 未来24小时三岔水库流域的逐时降雨预报情况如何？,
     expected_keywords: [mm, 降雨, 预报], timeout: 120}
  - {id: SC-F3, skill: forecasting, description: 查询汛限水位,
     question: 当前三岔水库的汛限水位是多少？,
     expected_keywords: [汛限, 水位], timeout: 60}
  - {id: SC-F4, skill: forecasting, description: 查询气象预警,
     question: 当前有哪些气象预警？, expected_keywords: [预警], timeout: 120}
  - {id: SC-F5, skill: forecasting, description: 数据时效性,
     question: 当前预报数据的时效性如何？, expected_keywords: [时效], timeout: 120}
  - {id: SC-F6, skill: forecasting, description: 综合查询,
     question: 综合分析三岔水库当前水情和未来24小时降雨情况,
     expected_keywords: [水位, 降雨], timeout: 120}
  - {id: SC-PG1, skill: plan-generation, description: 查询当前水情,
     question: 三岔水库当前水情怎么样？, expected_keywords: [水位], timeout: 120}
  - {id: SC-PG2, skill: plan-generation, description: 查询汛限水位,
     question: 当前汛限水位是多少？, expected_keywords: [汛限], timeout: 120}
  - {id: SC-PG3, skill: plan-generation, description: 生成调度预案,
     question: 根据当前情况生成一个调度预案, expected_keywords: [预案, 调度], timeout: 180}
  - {id: SC-SIM1, skill: simulation, description: 查询当前水位和配置,
     question: 查询三岔水库当前水位和系统配置, expected_keywords: [水位, 配置], timeout: 120}
  - {id: SC-SIM2, skill: simulation, description: 查询历史洪水,
     question: 查询历史洪水记录, expected_keywords: [历史, 洪水], timeout: 120}
```

- [ ] **Step 2: 写 `tests/reservoirs/taoqupo.yaml`**（只列静态数据类用例；实时类不列）

```yaml
name: taoqupo
tenant_id: 20
display_name: 桃曲坡水库
forbidden_keywords: [三岔, 462.5, 462.88, 451]
cases:
  - {id: TQ-PG1, skill: plan-generation, description: 查询主汛限水位,
     question: 桃曲坡水库的主汛限水位是多少米？,
     expected_keywords: [786.8, 汛限], expected_range: {min: 786.5, max: 787.0}, timeout: 120}
  - {id: TQ-PG2, skill: plan-generation, description: 设计/校核洪水位,
     question: 桃曲坡水库的设计洪水位和校核洪水位各是多少米？,
     expected_keywords: [788.54, 790.5], timeout: 120}
  - {id: TQ-PG3, skill: plan-generation, description: 校核总泄量,
     question: 桃曲坡水库校核洪水位的总泄量是多少？,
     expected_keywords: [2331], expected_range: {min: 2300, max: 2340}, timeout: 120}
  - {id: TQ-PG4, skill: plan-generation, description: 校核库容(防误读5720),
     question: 桃曲坡水库校核洪水位790.5m对应的库容是多少万立方米？,
     expected_keywords: [4420], expected_range: {min: 4400, max: 4450}, timeout: 120}
  - {id: TQ-F1, skill: forecasting, description: 查询汛限水位,
     question: 当前桃曲坡水库的汛限水位是多少？,
     expected_keywords: [786.8, 汛限], expected_range: {min: 786.5, max: 787.0}, timeout: 120}
  - {id: TQ-SIM1, skill: simulation, description: 特征水位/配置查询,
     question: 查询桃曲坡水库的特征水位和系统配置, expected_keywords: [786.8], timeout: 120}
```

- [ ] **Step 3: 验证两 yaml 能被加载（结构 + 用例数）**

Run:
```bash
python3 -c "
from pathlib import Path
from tests.reservoir_profile import load_all_reservoirs
ps = load_all_reservoirs(Path('tests/reservoirs'))
for n,p in ps.items():
    print(n, 'tenant=',p.tenant_id,'cases=',len(p.cases),'forbidden=',p.forbidden_keywords)
"
```
Expected: `sancha tenant= 18 cases= 11 ...` 与 `taoqupo tenant= 20 cases= 6 ...`，无异常。

- [ ] **Step 4: Commit**

```bash
git add tests/reservoirs/sancha.yaml tests/reservoirs/taoqupo.yaml
git commit -m "feat(tests): sancha + taoqupo reservoir 用例集 yaml

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: test_skills.py 改造（profile 驱动 + env 注入 + CLI + 修 TEST_RESULTS_DIR）

**Files:**
- Modify: `test_skills.py`（整体重构数据来源与 runner；保留报告生成骨架）

**Interfaces:**
- Consumes: `tests/reservoir_profile.py` 全部（Task 1）；两 yaml（Task 2）。
- Produces: `python3 test_skills.py --reservoir taoqupo` / `--all-reservoirs` 可用。

**当前关键 bug**：`test_skills.py:497,556` 用了 `TEST_RESULTS_DIR`，但从未定义（lib/paths.py 只导出 `RESULTS_DIR`）→ main() 必 NameError。本任务一并修复。

- [ ] **Step 1: 改 import + 路径，加载 reservoir profile**

文件顶部（替换原 SKILLS/ALL_TESTS 硬编码块）。在 `from paths import ...` 之后加：
```python
# 多水库 profile（替代原硬编码 SKILLS / ALL_TESTS）
sys.path.insert(0, str(Path(__file__).parent / "tests"))
from reservoir_profile import (  # noqa: E402
    ReservoirProfile, TestCase, load_all_reservoirs,
)

RESERVOIRS_DIR = PROJECT_ROOT / "tests" / "reservoirs"
TEST_RESULTS_DIR = RESULTS_DIR   # 修复原 TEST_RESULTS_DIR 未定义 bug
```
保留 `SkillDefinition` / `SKILLS`（仍用于 skill 元数据 name/description/skill_dir）。

- [ ] **Step 2: `run_test_case` 注入 env + 调 `verify_output`**

替换 `run_test_case` 中 `subprocess.run(cmd, capture_output=True, text=True, timeout=..., cwd=str(skill.skill_dir))` 与 `_verify_output` 调用：
```python
            # 注入水库身份（关键：多水库测试成立的前提）
            env = {
                **os.environ,
                "SRM_TENANT_ID": str(profile.tenant_id),
                "SRM_RESERVOIR_NAME": profile.name,
            }
            cmd = [
                "hermes", "chat", "-q", test_case.question,
                "--skills", test_case.skill, "-Q", "--max-turns", "25", "--yolo",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=test_case.timeout or self.timeout,
                cwd=str(skill.skill_dir), env=env,
            )
            output = result.stdout.strip()
            verification = verify_output(test_case, output, profile.forbidden_keywords)
```
> `run_test_case` 签名改为 `run_test_case(self, test_case, skill, profile)`；`_verify_output` 方法删除（改用 reservoir_profile.verify_output）。`_print_result` 适配新 verification 字段（forbidden_hits / range_passed / reasons）。

- [ ] **Step 3: `run_skill_tests` / `run_all_tests` 改为按 profile 驱动**

把原先遍历 `ALL_TESTS` 改为遍历 `profile.cases`，并按 skill 分组。新增按 profile 遍历的入口：
```python
    def run_reservoir(self, profile, only_skill=None, only_case=None):
        """跑单个水库的全部（或限定 skill/case）用例。"""
        results = []
        cases = profile.cases
        if only_case:
            cases = [c for c in cases if c.id == only_case]
        if only_skill:
            cases = [c for c in cases if c.skill == only_skill]
        for i, tc in enumerate(cases, 1):
            skill = next((s for s in SKILLS if s.id == tc.skill), None)
            if skill is None:
                continue
            print(f"\n进度: [{i}/{len(cases)}] {profile.display_name} {tc.id}")
            results.append(self.run_test_case(tc, skill, profile))
            if i < len(cases):
                time.sleep(2)
        return results
```
`generate_report` / `_generate_markdown_report` / `_generate_json_report`：统计维度从 `skill_id` 改为 `(reservoir, skill)`——给 result dict 加 `"reservoir": profile.name` 字段，报告按 reservoir 一级分组。

- [ ] **Step 4: `main()` CLI 加 `--reservoir` / `--all-reservoirs`，`--list` 按水库分组**

argparse 加：
```python
    parser.add_argument("--reservoir", help="指定水库（sancha/taoqupo），默认读 SRM_RESERVOIR_NAME env")
    parser.add_argument("--all-reservoirs", action="store_true", help="跑 tests/reservoirs/*.yaml 全部（双水库回归）")
```
调度逻辑（替换原 `if args.test_case / elif args.skill / elif args.all` 块）：
```python
    profiles = load_all_reservoirs(RESERVOIRS_DIR)
    if args.all_reservoirs:
        all_results = []
        for name, prof in profiles.items():
            print(f"\n{'#'*80}\n# 水库: {prof.display_name} ({name}, tenant={prof.tenant_id})\n{'#'*80}")
            all_results += runner.run_reservoir(prof, only_skill=args.skill, only_case=args.test_case)
        results = all_results
    else:
        rname = args.reservoir or os.environ.get("SRM_RESERVOIR_NAME") or "sancha"
        prof = profiles.get(rname)
        if prof is None:
            print(f"❌ 未知水库: {rname}；可用: {', '.join(profiles)}"); sys.exit(1)
        results = runner.run_reservoir(prof, only_skill=args.skill, only_case=args.test_case)
```
`--list` 改为按水库分组：
```python
    if args.list:
        for name, prof in profiles.items():
            print(f"\n== {prof.display_name} (tenant={prof.tenant_id}, forbidden={prof.forbidden_keywords}) ==")
            for c in prof.cases:
                print(f"  {c.id:<10} {c.skill:<16} {c.description}")
        sys.exit(0)
```

- [ ] **Step 5: 静态校验（不跑 hermes）——`--list` + python 编译**

Run: `python3 -c "import ast; ast.parse(open('test_skills.py').read())"` 然后 `python3 test_skills.py --list`
Expected: 编译无语法错；`--list` 输出 sancha（11 case）+ taoqupo（6 case），按水库分组。

- [ ] **Step 6: 单水库 dry smoke（跑 1 个最快用例确认 env 注入通）**

Run:
```bash
set -a; source /root/.hermes/.env; set +a
python3 test_skills.py --reservoir taoqupo --test-case TQ-PG1 --timeout 180
```
Expected: TQ-PG1 PASS（命中 786.8 / 汛限，range 通过，forbidden 0），证明 env 注入 + profile 驱动 + 三判定端到端打通。

- [ ] **Step 7: Commit**

```bash
git add test_skills.py
git commit -m "feat(test): test_skills 改 profile 驱动 + hermes env 注入 + 三判定 + --reservoir CLI

- 修复 TEST_RESULTS_DIR 未定义 bug
- 删除 _verify_output，改用 reservoir_profile.verify_output
- main: --reservoir/--all-reservoirs/--list 按水库分组

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: f_rnfl_h 查询补 tenant 过滤（3 脚本）

**Files:**
- Modify: `forecasting/scripts/query_forecast_data.py:105-122`
- Modify: `forecasting/scripts/query_forecast_analysis.py:87-94`
- Modify: `plan-generation/scripts/query_plan_data.py:35-55`

**Interfaces:** 无新接口；纯 SQL 补 `AND tenant_id=%s`，签名加/复用 `tenant_id` 参数。

> 三处现状：`f_rnfl_h` 表已有 `tenant_id bigint NOT NULL default 1`，但查询都不过滤（代码旧注释"无 tenant"过时）。补过滤 + 更新注释。

- [ ] **Step 1: 改 `forecasting/scripts/query_forecast_data.py`**

把 `query_rainfall_forecast`（108-122 行）改为：
```python
# ===========================================================================
# 2. rainfall_forecast —— 和风逐时降雨预报
#    源:f_rnfl_h；表已有 tenant_id 列，按 tenant 过滤；deleted=0；窗口 NOW() → NOW()+hours。
# ===========================================================================
def query_rainfall_forecast(hours=DEFAULT_HOURS, limit=DEFAULT_LIMIT,
                            tenant_id=DEFAULT_TENANT, **_):
    sql = (
        "SELECT RN, YMDH, FYMDH, UNITNAME "
        "FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "  AND deleted=0 AND tenant_id=%s "
        "ORDER BY YMDH"
    )
    rows = unpack(execute_query(sql, (hours, tenant_id), max_rows=limit))
    return {
        "source": "f_rnfl_h (和风天气)",
        "hours": hours,
        "count": len(rows),
        "data": rows,
    }
```
同步把文件顶部 docstring 第 11、26 行的"f_rnfl_h ... 无 tenant"改为"f_rnfl_h ... 已按 tenant 过滤"。

- [ ] **Step 2: 改 `forecasting/scripts/query_forecast_analysis.py`**

把 `query_fusion_detail` 内的 hefeng 段（90-94 行）改为（加 `tenant_id` + 补 `deleted=0`）：
```python
    # --- 源 1:和风 168h 逐时（按 tenant 过滤） ---
    hefeng = unpack(execute_query(
        "SELECT YMDH, RN FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "  AND deleted=0 AND tenant_id=%s "
        "ORDER BY YMDH",
        (hours, tenant_id), max_rows=limit))
```
（函数已有 `tenant_id=DEFAULT_TENANT` 参数，直接复用。）同步更新第 21、23、174 行"f_rnfl_h 无 tenant"注释。

- [ ] **Step 3: 改 `plan-generation/scripts/query_plan_data.py`**

把 `query_rainfall_forecast`（35-55 行）改为（主查询 + 子查询都按 tenant 限定）：
```python
def query_rainfall_forecast(hours=48, source=None, tenant_id=None):
    """查询降雨预报（取最新发布的一批数据，按 tenant 过滤）"""
    tid = resolve_tenant(tenant_id)
    conditions = [
        "deleted = 0",
        "tenant_id = %s",
        "ymdh >= NOW()",
        "ymdh <= DATE_ADD(NOW(), INTERVAL %s HOUR)",
        "fymdh = (SELECT MAX(fymdh) FROM f_rnfl_h WHERE ymdh >= NOW() AND tenant_id = %s AND deleted = 0)",
    ]
    params = [tid, hours, tid]

    if source:
        conditions.append("unitname = %s")
        params.append(source)

    sql = (
        "SELECT ymdh, rn, pop, text, temp, wind_dir, wind_speed, unitname"
        " FROM f_rnfl_h"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY ymdh"
    )
    return execute_query(sql, params)
```
> 注意：原 params 顺序是 `[hours]`；改后 `[tid, hours, tid]`（对应 conditions 里 tenant_id、hours、子查询 tenant_id 三个占位符），`source` 追加末尾。

- [ ] **Step 4: 验证三个脚本能 import 且 tenant 过滤生效**

Run:
```bash
set -a; source /root/.hermes/.env; set +a
echo "--- forecast_data (默认 tenant=18) ---"
python3 forecasting/scripts/query_forecast_data.py rainfall_forecast 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print('count=',d.get('count'))" || true
echo "--- plan rainfall_forecast --tenant 20 ---"
python3 plan-generation/scripts/query_plan_data.py --type rainfall_forecast --tenant 20 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print('count=',d.get('count',len(d.get('data',[]))))" || true
```
Expected: 不报 SQL 错（确认 `tenant_id` 占位符数量与 params 对齐）；count 为当前该 tenant 的预报行数（桃曲坡预报未接入可能为 0，三岔可能非 0）。

- [ ] **Step 5: Commit**

```bash
git add forecasting/scripts/query_forecast_data.py forecasting/scripts/query_forecast_analysis.py plan-generation/scripts/query_plan_data.py
git commit -m "fix(forecast): f_rnfl_h 查询补 tenant_id 过滤（表已有列，3 脚本）

plan 版含 MAX(fymdh) 子查询也按 tenant 限定；analysis 版补 deleted=0；
同步更新过时的'无 tenant'注释。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 双水库回归验收

**Files:** 无（纯运行验收）

- [ ] **Step 1: 三岔回归（单水库）**

Run:
```bash
set -a; source /root/.hermes/.env; set +a
python3 test_skills.py --reservoir sancha --timeout 300
```
Expected: 退出码 0；SC-F1..SIM2 全 PASS（实时数据齐全）。

- [ ] **Step 2: 桃曲坡（单水库）**

Run: `python3 test_skills.py --reservoir taoqupo --timeout 300`
Expected: 退出码 0；TQ-* 6 个静态用例全 PASS（786.8 / 788.54 / 790.5 / 2331 / 4420 命中，forbidden 0）。

- [ ] **Step 3: 双水库回归（最终验收）**

Run: `python3 test_skills.py --all-reservoirs --timeout 300`
Expected: 退出码 0；报告按 (reservoir × skill) 分组；**sancha 全绿 + taoqupo 全绿 + 全程 forbidden_hits = 0**。

- [ ] **Step 4: 失败则诊断**

若 taoqupo 某用例 FAIL：看报告 `reasons`——keywords 未命中（检查 agent 输出 / question 文案）、range 未落区间（检查数值提取）、forbidden 命中（定位串库来源，检查 env 注入与 profile）。修正后回到 Step 2。

- [ ] **Step 5: 收尾 commit（若有验收中修正）**

```bash
git add -A
git commit -m "test: 双水库回归验收通过（sancha + taoqupo，forbidden 0）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec 覆盖**：
- §2 架构（独立 yaml 集）→ Task 1+2+3 ✓
- §3 yaml schema → Task 1 ReservoirProfile/TestCase + Task 2 实例 ✓
- §4 三判定 → Task 1 verify_output + test_judge ✓
- §5 两水库用例集 → Task 2 ✓
- §6 hermes env 注入 → Task 3 Step 2 ✓
- §7 CLI → Task 3 Step 4 ✓
- §8 回归策略/报告/退出码 → Task 3 Step 3 + Task 5 ✓
- §9.1 f_rnfl_h 顺手修复 → Task 4 ✓
- §10 weather_warn 不碰 → 计划无相关任务（正确，留平台层）✓
- §11 YAGNI（不做 skip/渲染/5skill）→ 计划均未涉及 ✓

**2. 占位扫描**：无 TBD/TODO；每个 code step 均有完整代码或精确 before/after；Task 3 的报告字段适配给了明确指引（`(reservoir, skill)` 维度 + `reasons`）。

**3. 类型/命名一致**：`verify_output(case, output, forbidden)` 在 Task 1 定义、Task 3 Step 2 同名调用一致；`ReservoirProfile.tenant_id/forbidden_keywords/cases` 跨任务一致；`run_reservoir(profile, only_skill, only_case)` 定义（Task 3 Step 3）与调用（Step 4）一致；f_rnfl_h params 顺序在 Task 4 Step 3 显式说明。

**4. 额外修复**：TEST_RESULTS_DIR bug（spec 未提，探索发现）纳入 Task 3 Step 1——合理（改造 main 时必然触及）。
