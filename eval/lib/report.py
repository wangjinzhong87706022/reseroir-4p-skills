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
