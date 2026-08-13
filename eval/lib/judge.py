"""判分：inline（复用 reservoir_profile.verify_output）/ live_db / rubric / LLM-judge。"""
import re
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests.reservoir_profile import TestCase as RPCase, verify_output  # noqa: E402
from eval.lib.truth import compare_with_tolerance  # noqa: E402
import json as _json  # noqa: E402

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
    raw = first[list(first)[0]] if isinstance(first, dict) else first[0]
    try:
        truth = float(raw)
    except (TypeError, ValueError):
        return {"verdict": "ERROR", "detail": {"reason": f"真值非数值: {first!r}"}}
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


def _build_prompt(output, rubric):
    items = "\n".join(f"- {r}" for r in rubric)
    return (
        "你是水库调度 Skill 输出的验收评判员。按下述 rubric 逐条判定输出是否满足，"
        "只返回严格 JSON，不要任何额外文字。\n"
        f"rubric:\n{items}\n\n"
        f"待评判输出:\n{output}\n\n"
        '返回格式: {"passed": bool, "items": [{"criterion": str, "pass": bool}]}'
    )


def _parse_rubric_score(text):
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
    return _parse_rubric_score(text)
