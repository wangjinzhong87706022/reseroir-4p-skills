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
    p.add_argument("--sleep", type=float, default=2.0,
                   help="每题之间休眠秒数（限流退避），默认 2，批量跑可设 0")
    p.add_argument("--mode", choices=["gate", "report"], default="gate",
                   help="gate=any non-PASS exit 1（CI 门禁）；report=永远 exit 0（只出报告）")
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
        try:
            query_fn = truth.make_db_query_fn({})
        except Exception as e:
            print(f"警告: DB 连接失败，live_db 题将判 ERROR: {e}")
            # query_fn 保持 None → _dispatch 逐题返回 ERROR，run 继续且照写报告
    llm_on = llm_on or args.llm

    results = []
    for i, c in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {c.id} ({c.skill}/{c.category})", flush=True)
        t0 = time.time()
        try:
            r = transport_fn(c.question, c.skill, c.env, c.timeout, skill_dir=str(get_skill_dir(c.skill)))
            elapsed = time.time() - t0
            if r.get("timed_out"):
                v = {"verdict": "TIMEOUT", "detail": {"reason": f"超时 {c.timeout}s"}}
            else:
                v = _dispatch(c, r.get("output", ""), query_fn, llm_on)
            out_preview = r.get("output", "")
        except Exception as exc:
            elapsed = time.time() - t0
            v = {"verdict": "ERROR", "detail": {"reason": f"用例异常: {exc}"}}
            out_preview = ""
        status = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR", "TIMEOUT": "TIMEOUT"}.get(v["verdict"], "ERROR")
        results.append(report.build_result(c, status, elapsed, out_preview, v["detail"]))
        print(f"   -> {status}", flush=True)
        if i < len(selected):
            time.sleep(args.sleep)

    summary = report.summarize(results)
    ensure_dirs()
    out_dir = Path(report_dir or args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    report.write_json(results, summary, out_dir / f"eval-{ts}.json")
    report.write_markdown(results, summary, out_dir / f"eval-{ts}.md")
    print(f"\n{summary['overall']}")
    if args.mode == "report":
        return 0  # report 模式：只出报告，退出码恒 0
    return 0 if summary["overall"]["pass"] == summary["overall"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
