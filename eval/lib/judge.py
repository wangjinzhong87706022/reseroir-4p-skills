"""判分：inline（复用 reservoir_profile.verify_output）/ live_db / rubric / LLM-judge。"""
import os
import re
import sys
import urllib.request
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


def judge_inline(case, output: str, keywords_mode: str = "advisory") -> dict:
    """规则三判定：range + forbidden 硬门；keywords 按 keywords_mode。
    advisory 下 verify_output 收空 keywords，真实关键词命中另记 keywords_advisory。"""
    kws = case.expected_keywords if keywords_mode == "hard" else []
    rp = RPCase(id=case.id, skill=case.skill, description=case.description,
                question=case.question, expected_keywords=kws,
                expected_range=case.expected_range, timeout=case.timeout)
    v = verify_output(rp, output, case.forbidden)
    kw = _keyword_check(output, case.expected_keywords)
    detail = {**v, "keywords_mode": keywords_mode}
    if keywords_mode == "advisory":
        detail["keywords_advisory"] = kw["keyword_checks"]
        detail["all_found_advisory"] = kw["all_found"]
    return {"verdict": "PASS" if v["all_passed"] else "FAIL", "detail": detail}


def judge_live_db(case, output: str, query_fn, keywords_mode: str = "advisory") -> dict:
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
    kw_hard = kw["all_found"] if keywords_mode == "hard" else True
    passed = cmp["passed"] and kw_hard
    detail = {"truth": truth, **cmp, "keywords_mode": keywords_mode,
              "keywords_advisory": kw["keyword_checks"], "all_found_advisory": kw["all_found"]}
    if keywords_mode == "hard":
        detail.update(kw)
    return {"verdict": "PASS" if passed else "FAIL", "detail": detail}


def judge_rubric(case, output: str, llm_fn=None, keywords_mode: str = "advisory") -> dict:
    forb = [w for w in case.forbidden if str(w).lower() in (output or "").lower()]
    kw = _keyword_check(output, case.expected_keywords)
    kw_hard = kw["all_found"] if keywords_mode == "hard" else True
    rule_pass = kw_hard and not forb
    detail = {"keywords_mode": keywords_mode,
              "keywords_advisory": kw["keyword_checks"], "all_found_advisory": kw["all_found"],
              "forbidden_hits": forb}
    if keywords_mode == "hard":
        detail.update(kw)
    if llm_fn is None:
        return {"verdict": "PASS" if rule_pass else "FAIL",
                "detail": {**detail, "rubric": "skip (no llm)"}}
    score = llm_fn(output, case.rubric)
    # 考官故障（空/非 JSON 响应）判 ERROR 而非 FAIL——避免假 FAIL 污染通过率
    if score.get("error"):
        return {"verdict": "ERROR", "detail": {**detail, "rubric_score": score,
                                               "reason": f"考官故障: {score['error']}"}}
    passed = rule_pass and score["passed"]
    return {"verdict": "PASS" if passed else "FAIL", "detail": {**detail, "rubric_score": score}}


def _build_prompt(output, rubric):
    items = "\n".join(f"- {r}" for r in rubric)
    return (
        "你是水库调度 Skill 输出的验收评判员。按下述 rubric 逐条判定输出是否满足，"
        "只返回严格 JSON，不要任何额外文字。\n"
        "注意：待评判输出中可能夹杂代码片段、文件 diff、脚本日志等过程噪声——"
        "判定时只依据其中的最终分析/报告文本，不要因存在噪声或格式混杂而判不满足。\n"
        f"rubric:\n{items}\n\n"
        f"待评判输出:\n{output}\n\n"
        '返回格式: {"passed": bool, "items": [{"criterion": str, "pass": bool}]}'
    )


def _parse_rubric_score(text):
    """解析考官 JSON。空/不可解析响应返回 error 标志，由 judge_rubric 判 ERROR。

    历史缺陷：LLM 返回空 items 时旧码静默 passed=False，把考官故障伪装成真实 FAIL，
    污染通过率（2026-09-01 试点 4/6 假 FAIL 即此）。现显式区分"考官无有效答复"与"考官判不满足"。
    """
    raw = text or ""
    try:
        data = _json.loads(raw)
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        try:
            data = _json.loads(raw[start:end + 1]) if start >= 0 else {}
        except Exception:
            data = {}
    if not isinstance(data, dict) or not raw.strip():
        return {"passed": False, "items": [], "error": "考官返回空或非 JSON"}
    items = data.get("items", [])
    if not items:
        # 考官未给出逐条判定 → 视为考官故障，交 judge_rubric 判 ERROR
        return {"passed": False, "items": [], "error": "考官返回 items 为空"}
    passed = data.get("passed", all(it.get("pass") for it in items))
    return {"passed": bool(passed), "items": items}


def make_anthropic_client():
    try:
        import anthropic  # 延迟导入：可选依赖
    except ImportError as e:
        raise RuntimeError("LLM-judge 需要 anthropic SDK：pip install anthropic") from e
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _judge_via_openai_compat(output, rubric):
    """EVAL_JUDGE_BASE_URL 指向的 OpenAI 兼容端点（本地网关/vLLM/llama.cpp 等）。

    零新依赖：urllib 直 POST /chat/completions；未设 EVAL_JUDGE_API_KEY 则
    不带 Authorization 头（自建服务通常免鉴权）。temperature=0 保证判分稳定。
    """
    base = os.environ["EVAL_JUDGE_BASE_URL"].rstrip("/")
    payload = {
        "model": os.environ.get("EVAL_JUDGE_MODEL", "default"),
        "max_tokens": 512,
        "temperature": 0,
        "messages": [{"role": "user", "content": _build_prompt(output, rubric)}],
    }
    headers = {"Content-Type": "application/json"}
    if os.environ.get("EVAL_JUDGE_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['EVAL_JUDGE_API_KEY']}"
    req = urllib.request.Request(
        f"{base}/chat/completions", data=_json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return _parse_rubric_score(text)


def llm_judge(output, rubric, client=None):
    # 路由：显式传 client → Anthropic；否则设了 EVAL_JUDGE_BASE_URL → OpenAI 兼容端点；
    # 都没有 → Anthropic 默认路径（缺 ANTHROPIC_API_KEY 时由 SDK 报错，fail-loud）。
    if client is None and os.environ.get("EVAL_JUDGE_BASE_URL"):
        return _judge_via_openai_compat(output, rubric)
    if client is None:
        client = make_anthropic_client()
    resp = client.messages.create(
        model=os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-5"),
        max_tokens=512,
        messages=[{"role": "user", "content": _build_prompt(output, rubric)}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    return _parse_rubric_score(text)
