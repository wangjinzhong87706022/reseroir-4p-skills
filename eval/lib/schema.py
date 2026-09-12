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
    truth_expectation: Optional[dict] = None
    tolerance: float = 0.0
    rubric: list = field(default_factory=list)
    fixtures: list = field(default_factory=list)


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
    if case.truth_expectation is not None:
        if case.truth_source != "live_db":
            raise ValueError(f"{case.id}: truth_expectation 仅 live_db 题可用")
        bad = set(case.truth_expectation) - {"value", "tol", "min", "max"}
        if bad or not case.truth_expectation:
            raise ValueError(f"{case.id}: truth_expectation 键非法 {bad or '为空'}（允许 value/tol/min/max）")


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
        truth_expectation=d.get("truth_expectation"),
        rubric=list(d.get("rubric") or []),
        fixtures=_coerce_str_list(d.get("fixtures")),
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
