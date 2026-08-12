"""判分：inline（复用 reservoir_profile.verify_output）/ live_db / rubric / LLM-judge。"""
import re
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests.reservoir_profile import TestCase as RPCase, verify_output  # noqa: E402
from eval.lib.truth import compare_with_tolerance  # noqa: E402

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
