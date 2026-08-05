"""Reservoir test profile: yaml 加载 + 三判定逻辑（纯逻辑，无 hermes/DB 依赖）。

供 test_skills.py 加载各水库用例集并对 hermes 输出做判定：
  - keywords: 子串匹配（大小写不敏感）
  - range:    从输出提取数值，任一落入 [min,max] 即过
  - forbidden: 顶层继承的禁词，命中任一即整体 FAIL（防串库）
"""
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


def _coerce_keywords(lst) -> list:
    """yaml 可能把纯数字项解析成 float/int；禁词/关键词统一转 str（verify_output 按子串匹配）。"""
    return [str(x) for x in (lst or [])]


def load_reservoir(path: Path) -> ReservoirProfile:
    """加载单个水库 yaml → ReservoirProfile。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cases = []
    for c in (data.get("cases") or []):
        c = dict(c)
        c["expected_keywords"] = _coerce_keywords(c.get("expected_keywords"))
        cases.append(TestCase(**c))
    return ReservoirProfile(
        name=data["name"],
        tenant_id=int(data["tenant_id"]),
        display_name=data.get("display_name", data["name"]),
        forbidden_keywords=_coerce_keywords(data.get("forbidden_keywords")),
        cases=cases,
    )


def load_all_reservoirs(base: Path) -> dict:
    """base 目录下所有 *.yaml → {name: ReservoirProfile}。"""
    profiles = {}
    for p in sorted(Path(base).glob("*.yaml")):
        prof = load_reservoir(p)
        profiles[prof.name] = prof
    return profiles
