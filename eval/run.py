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
from eval import data_prep  # noqa: E402  (场景注入层，见 eval/data/scenarios.yaml)


def parse_args(argv):
    p = argparse.ArgumentParser(description="统一评估集 runner")
    p.add_argument("--cases-dir", default=str(Path(__file__).parent / "cases"))
    p.add_argument("--report-dir", default=str(RESULTS_DIR))
    p.add_argument("--skill")
    p.add_argument("--subset", choices=["smoke", "full"])
    p.add_argument("--tag")
    p.add_argument("--id")
    p.add_argument("--truth", choices=["inline", "live_db", "rubric"])
    p.add_argument("--llm", action="store_true",
                   help="启用 LLM-judge（rubric 题）。考官二选一：ANTHROPIC_API_KEY（Anthropic）"
                        "或 EVAL_JUDGE_BASE_URL+EVAL_JUDGE_MODEL（OpenAI 兼容端点，如本地网关/vLLM）")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="每题之间休眠秒数（限流退避），默认 2，批量跑可设 0")
    p.add_argument("--mode", choices=["gate", "report"], default="gate",
                   help="gate=any non-PASS exit 1（CI 门禁）；report=永远 exit 0（只出报告）")
    p.add_argument("--timeout-cap", type=int, default=None,
                   help="每题超时上限（秒）：取 min(case.timeout, cap)，只压不抬。不传则用 case 原值")
    p.add_argument("--timeout-set", type=int, default=None,
                   help="每题超时下限抬到该值（秒）：取 max(case 自带 timeout, set)，只抬不压，"
                        "避免把 SUP1 等原生长超时题压短。与 --timeout-cap 互斥，--timeout-set 优先")
    p.add_argument("--list", action="store_true", help="仅列出用例")
    p.add_argument("--keywords-mode", choices=["hard", "advisory"], default="advisory",
                   help="expected_keywords 语义：advisory=只报告不判分（默认）；hard=一票否决（旧版）。"
                        "forbidden_keywords 恒为硬门；无 LLM 考官的 rubric 题自动回退 hard")
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
        wanted = {x.strip() for x in args.id.split(",") if x.strip()}
        out = [c for c in out if c.id in wanted]
    if args.truth:
        out = [c for c in out if c.truth_source == args.truth]
    return out


def _dispatch(case, out, query_fn, llm_on, keywords_mode="advisory"):
    if case.truth_source == "inline":
        return judge.judge_inline(case, out, keywords_mode)
    if case.truth_source == "live_db":
        if query_fn is None:
            return {"verdict": "ERROR", "detail": {"reason": "无 DB 连接"}}
        return judge.judge_live_db(case, out, query_fn, keywords_mode)
    # rubric
    llm_fn = None
    if llm_on and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EVAL_JUDGE_BASE_URL")):
        llm_fn = lambda o, r: judge.llm_judge(o, r)  # Anthropic 或 EVAL_JUDGE_BASE_URL（OpenAI 兼容）
    return judge.judge_rubric(case, out, llm_fn, keywords_mode)


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
        try:
            query_fn = truth.make_db_query_fn({})
        except Exception as e:
            print(f"警告: DB 连接失败，live_db 题将判 ERROR: {e}")
            # query_fn 保持 None → _dispatch 逐题返回 ERROR，run 继续且照写报告
    llm_on = llm_on or args.llm

    out_dir = Path(report_dir or args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir = out_dir / "transcripts"

    results = []
    prep = data_prep.Prep(out_dir)
    for i, c in enumerate(selected, 1):
        # 超时口径：--timeout-set 只抬不压 max(case 原值, set) > --timeout-cap 封顶 min() > case 原值
        # 2026-08-27 修正：旧实现直接覆盖，会把 SUP1 这类原生 1500s 的慢题压到 1000s → TIMEOUT 伪影
        if args.timeout_set:
            eff_timeout = max(c.timeout, args.timeout_set)
        elif args.timeout_cap:
            eff_timeout = min(c.timeout, args.timeout_cap)
        else:
            eff_timeout = c.timeout
        print(f"[{i}/{len(selected)}] {c.id} ({c.skill}/{c.category}) [timeout={eff_timeout}s]", flush=True)
        # 场景注入（eval/data/scenarios.yaml）：transport 前物化数据前提，判分后恢复。
        # 全量跑时 exclusive 场景自动跳过（data_prep.EXCLUSIVE_MAX_BATCH）。
        fx = prep.setup(c, len(selected))
        try:
            t0 = time.time()
            # 2026-08-27：transport 偶发基础设施异常（如 "read operation timed out"）重试一次，
            # 避免单点网络/IO 抖动毁掉一道题（SUP2 实例）。TIMEOUT 不重试（重试只是双倍耗时）。
            r, exc = None, None
            for attempt in (1, 2):
                try:
                    r = transport_fn(c.question, c.skill, c.env, eff_timeout, skill_dir=str(get_skill_dir(c.skill)))
                    break
                except Exception as e:
                    exc = e
                    if attempt == 1:
                        print(f"   .. transport 异常（{e}），重试 1 次", flush=True)
                        time.sleep(3)
            if r is not None:
                elapsed = time.time() - t0
                if r.get("timed_out"):
                    v = {"verdict": "TIMEOUT", "detail": {"reason": f"超时 {eff_timeout}s"}}
                elif not (r.get("answer") or "").strip():
                    # 未超时但无最终回复 = infra 故障（hermes 崩溃/空 stdout），判 ERROR 防假 FAIL
                    v = {"verdict": "ERROR", "detail": {"reason": "transport 未超时但返回空输出"}}
                else:
                    v = _dispatch(c, r["answer"], query_fn, llm_on, args.keywords_mode)
                out_preview = r.get("answer", "")
                transcript_path = transcripts_dir / f"{c.id}.txt"
                meta = (f"[answer_extracted={r.get('answer_extracted')}] "
                        f"[answer_chars={len(r.get('answer') or '')}]\n")
                report.write_transcript(transcript_path, meta + r.get("output", ""), r.get("stderr", ""))
            else:
                elapsed = time.time() - t0
                v = {"verdict": "ERROR", "detail": {"reason": f"用例异常(重试后仍失败): {exc}"}}
                out_preview = ""
                transcript_path = transcripts_dir / f"{c.id}.txt"
                report.write_transcript(transcript_path, "", f"runner exception: {exc}")
            status = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR", "TIMEOUT": "TIMEOUT"}.get(v["verdict"], "ERROR")
            if fx:
                v.setdefault("detail", {})["fixtures"] = fx
            results.append(report.build_result(c, status, elapsed, out_preview, v["detail"],
                                               transcript=str(transcript_path.resolve())))
            print(f"   -> {status}", flush=True)
        finally:
            if fx:
                prep.teardown(c)
        if i < len(selected):
            time.sleep(args.sleep)

    summary = report.summarize(results)
    # 运行元数据：judge_model 取环境（未设则 default）；keywords_mode 用 getattr 兜底（直接调 main 的旧测试未传旗标）
    summary["meta"] = {"judge_model": os.environ.get("EVAL_JUDGE_MODEL", "default"),
                       "keywords_mode": getattr(args, "keywords_mode", "advisory")}
    ensure_dirs()
    ts = time.strftime("%Y%m%d-%H%M%S")
    report.write_json(results, summary, out_dir / f"eval-{ts}.json")
    report.write_markdown(results, summary, out_dir / f"eval-{ts}.md")
    print(f"\n{summary['overall']}")
    if args.mode == "report":
        return 0  # report 模式：只出报告，退出码恒 0
    return 0 if summary["overall"]["pass"] == summary["overall"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
