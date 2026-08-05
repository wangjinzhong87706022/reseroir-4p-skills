#!/usr/bin/env python3
"""
orchestrator.py -- Supervisor DAG 编排主脚本（场景 A：汛期暴雨研判调度七步闭环）。

把 forecasting → diagnosis → inspection → simulation → plan-generation → [仲裁] → chatbi
按顺序编排执行，每个阶段结果写入 SQLite State，支持断点续跑与 HITL 检查点。

用法:
    # 一键完整编排（从场景识别到仲裁）
    python3 scripts/orchestrator.py run --trigger "暴雨预警，水位超汛限" \
        [--flood-limit 786.8 --safe-discharge 500] [--dry-run]

    # 断点续跑：只执行 State 中未完成的阶段
    python3 scripts/orchestrator.py resume --event A-20260805-001 [--flood-limit 786.8]

    # 只执行单阶段（便于调试/子 skill 单独调用）
    python3 scripts/orchestrator.py stage --event A-20260805-001 --stage step1

设计原则:
    1. 阶段执行 = 调用子 skill 的现成脚本（query_forecast_data.py / query_plan_data.py / ...），
       Supervisor 不重写专业逻辑，只做编排。
    2. 每阶段结果以 JSON 写入 State；仲裁(step6) 依赖 step4(simulation) 与 step5(plan-gen) 结果。
    3. step5→step6 之间是 HITL 检查点：--approve 显式传入才继续；否则停在 awaiting_approval。
    4. --dry-run 模式只打印将执行的命令，不真正执行（用于验证 DAG 顺序）。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# 让脚本能被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from supervisor_state import _connect, _state_dir  # noqa: E402
from scene_router import route  # noqa: E402
from arbitrator import arbitrate_plan_vs_simulation, asdict  # noqa: E402

# ===========================================================================
# DAG 定义：stage → (agent, 调用命令模板)
# ===========================================================================

# 各子 skill 脚本的仓库相对路径（以仓库根为基准）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

STAGE_CMDS = {
    # 场景 A：汛期暴雨研判调度（七步）
    "A": {
        "step1": ("forecasting",
                  ["python3", str(REPO_ROOT / "forecasting/scripts/query_forecast_data.py"),
                   "--type", "full_context"]),
        "step2": ("diagnosis-verification",
                  ["python3", str(REPO_ROOT / "diagnosis-verification/scripts/check_data_quality.py"),
                   "--type", "all"]),
        "step3": ("inspection",
                  ["python3", str(REPO_ROOT / "supervisor/scripts/inspection_check.py"),
                   "--type", "all"]),
        "step4": ("simulation",
                  ["python3", str(REPO_ROOT / "simulation/scripts/query_simulation_data.py"),
                   "--type", "full_context"]),
        "step5": ("plan-generation",
                  ["python3", str(REPO_ROOT / "plan-generation/scripts/query_plan_data.py"),
                   "--type", "full_context"]),
        "step6": ("arbitrator", None),   # 特殊：由本脚本在内存中执行仲裁
        "step7": ("chatbi", None),       # 特殊：报告生成（占位，输出模板）
    },
    # 场景 B：大坝安全智能诊断（五步）
    "B": {
        "step1": ("diagnosis-verification",
                  ["python3", str(REPO_ROOT / "diagnosis-verification/scripts/check_data_quality.py"),
                   "--type", "all"]),
        "step2": ("inspection",
                  ["python3", str(REPO_ROOT / "supervisor/scripts/inspection_check.py"),
                   "--type", "defects"]),
        "step3": ("simulation",
                  ["python3", str(REPO_ROOT / "simulation/scripts/query_simulation_data.py"),
                   "--type", "full_context"]),
        "step4": ("arbitrator", None),   # 风险定级 + 处置建议（内存执行）
        "step5": ("chatbi", None),       # 诊断报告（内存执行）
    },
    # 场景 C：日常精细化管控（三步）
    "C": {
        "step1": ("forecasting",
                  ["python3", str(REPO_ROOT / "forecasting/scripts/query_forecast_data.py"),
                   "--type", "full_context"]),
        "step2": ("simulation",
                  ["python3", str(REPO_ROOT / "simulation/scripts/query_simulation_data.py"),
                   "--type", "full_context"]),
        "step3": ("chatbi", None),       # 日报台账（内存执行）
    },
    # 场景 D：应急响应（五步）
    "D": {
        "step1": ("early-warning",
                  ["python3", str(REPO_ROOT / "early-warning/scripts/query_early_warning.py"),
                   "--type", "high_level", "--days", "7"]),
        "step2": ("plan-generation",
                  ["python3", str(REPO_ROOT / "plan-generation/scripts/query_plan_data.py"),
                   "--type", "full_context"]),
        "step3": ("simulation",
                  ["python3", str(REPO_ROOT / "simulation/scripts/query_simulation_data.py"),
                   "--type", "full_context"]),
        "step4": ("arbitrator", None),   # 仲裁 + HITL（内存执行）
        "step5": ("chatbi", None),       # 应急报告 + 推送（内存执行）
    },
}

# 各场景的特殊阶段（内存执行）：{scene: {"arbitrate": stage, "report": stage}}
SPECIAL_STAGES = {
    "A": {"arbitrate": "step6", "report": "step7"},
    "B": {"arbitrate": "step4", "report": "step5"},
    "C": {"arbitrate": None,   "report": "step3"},
    "D": {"arbitrate": "step4", "report": "step5"},
}


def run_stage_cmd(cmd, dry_run=False) -> dict:
    """执行子 skill 命令，返回 (ok, stdout_text)。超时 60s。"""
    if dry_run:
        return {"dry_run": True, "cmd": " ".join(str(c) for c in cmd)}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {"ok": r.returncode == 0, "stdout": r.stdout[:4000], "stderr": r.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


def do_arbitration(event_id, conn, flood_limit, safe_discharge) -> dict:
    """step6 仲裁：读 step4(simulation) + step5(plan-gen) 结果交叉校验"""
    stages = {
        s["stage"]: dict(s) for s in conn.execute(
            "SELECT stage, result_json FROM stage_results WHERE event_id=?",
            (event_id,),
        ).fetchall()
    }
    sim = json.loads(stages.get("step4", {}).get("result_json") or "{}")
    plan = json.loads(stages.get("step5", {}).get("result_json") or "{}")
    # 从 full_context 结果中提取水位/泄量（若子 skill 脚本输出符合约定字段）
    sim_vals = {
        "max_level": sim.get("max_level") or sim.get("water_level") or sim.get("highest_level"),
        "max_discharge": sim.get("max_discharge") or sim.get("discharge"),
    }
    plan_vals = {
        "max_level": plan.get("max_level") or plan.get("highest_level") or plan.get("max_water_level"),
        "max_discharge": plan.get("max_discharge") or plan.get("discharge"),
    }
    result = arbitrate_plan_vs_simulation(
        plan_vals, sim_vals,
        flood_limit=flood_limit, safe_discharge=safe_discharge,
    )
    return asdict(result)


def do_report(event_id, conn) -> dict:
    """step7 chatbi：生成研判报告（占位模板，后续接 powerelf chatbi）"""
    stages = conn.execute(
        "SELECT stage, agent, status FROM stage_results WHERE event_id=? ORDER BY stage",
        (event_id,),
    ).fetchall()
    return {
        "report_md": (
            f"# 暴雨研判报告（event={event_id}）\n\n"
            + "\n".join(
                f"- **{s['stage']}** [{s['agent']}] → {s['status']}"
                for s in stages if s["status"] in ("ok", "skipped")
            )
            + "\n\n*生成: supervisor orchestrator (占位)*"
        )
    }


def execute_dag(event_id, scene, conn, flood_limit, safe_discharge, dry_run, approve):
    """按 DAG 顺序执行所有未完成阶段"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from references.dag_order import DAG_ORDER

    dag = DAG_ORDER.get(scene, [])
    if not dag:
        print(json.dumps({"error": f"场景 {scene} 无 DAG 定义"}, ensure_ascii=False))
        return

    done = {s["stage"] for s in conn.execute(
        "SELECT stage FROM stage_results WHERE event_id=? AND status IN ('ok','skipped')",
        (event_id,),
    ).fetchall()}
    steps_to_run = [s for s in dag if s not in done]

    print(json.dumps({
        "event_id": event_id,
        "scene": scene,
        "dag": dag,
        "steps_to_run": steps_to_run,
        "dry_run": dry_run,
    }, ensure_ascii=False, indent=2))

    if dry_run:
        # 打印将执行的命令
        for stage in steps_to_run:
            agent, cmd = STAGE_CMDS.get(scene, {}).get(stage, (None, None))
            print(f"  [{stage}] {agent}: {' '.join(map(str, cmd)) if cmd else '(内存执行)'}")
        return

    for stage in steps_to_run:
        agent, cmd = STAGE_CMDS.get(scene, {}).get(stage, (None, None))

        # HITL 检查点：场景 A/D 的仲裁阶段前需人工确认
        special = SPECIAL_STAGES.get(scene, {})
        arbitrate_stage = special.get("arbitrate")
        if stage == arbitrate_stage and not approve:
            conn.execute("UPDATE events SET status='awaiting_approval' WHERE event_id=?",
                         (event_id,))
            conn.commit()
            print(json.dumps({
                "checkpoint": "HITL",
                "message": f"方案已生成（场景{scene}），等待人工确认后再仲裁",
                "hint": "确认后重跑: orchestrator.py resume --event "
                        f"{event_id} --approve [--flood-limit X]",
            }, ensure_ascii=False, indent=2))
            return

        if stage in (special.get("arbitrate"), special.get("report")):
            # 内存执行（仲裁/报告）
            result = do_arbitration(event_id, conn, flood_limit, safe_discharge) \
                if stage == arbitrate_stage else do_report(event_id, conn)
            status = "ok"
            print(f"  [{stage}] {agent} → {json.dumps(result, ensure_ascii=False)[:300]}")
        else:
            # 调用子 skill 脚本
            out = run_stage_cmd(cmd, dry_run=False)
            status = "ok" if out.get("ok") else "error"
            result = out
            print(f"  [{stage}] {agent} → ok={out.get('ok')} "
                  f"stdout={str(out.get('stdout',''))[:150]}")

        # 写入 State
        conn.execute(
            "INSERT OR REPLACE INTO stage_results (event_id, stage, agent, result_json, status, ts) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (event_id, stage, agent, json.dumps(result, ensure_ascii=False)[:8000], status),
        )
        conn.commit()

    # 全部完成后更新事件状态
    conn.execute("UPDATE events SET status='done', updated_at=datetime('now') WHERE event_id=?",
                 (event_id,))
    conn.commit()
    print(json.dumps({"event_id": event_id, "status": "done"},
                     ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Supervisor DAG 编排")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="一键编排：识别场景 → 建事件 → 执行 DAG")
    p_run.add_argument("--trigger", required=True, help="触发信号/用户输入")
    p_run.add_argument("--flood-limit", type=float, default=None, help="汛限水位(m)")
    p_run.add_argument("--safe-discharge", type=float, default=None, help="下游安全泄量(m³/s)")
    p_run.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    p_run.add_argument("--approve", action="store_true", help="跳过 HITL 检查点直接仲裁")
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="断点续跑：执行未完成阶段")
    p_resume.add_argument("--event", required=True)
    p_resume.add_argument("--flood-limit", type=float, default=None)
    p_resume.add_argument("--safe-discharge", type=float, default=None)
    p_resume.add_argument("--approve", action="store_true")
    p_resume.set_defaults(func=cmd_resume)

    p_stage = sub.add_parser("stage", help="执行单阶段（调试用）")
    p_stage.add_argument("--event", required=True)
    p_stage.add_argument("--stage", required=True)
    p_stage.add_argument("--flood-limit", type=float, default=None)
    p_stage.add_argument("--safe-discharge", type=float, default=None)
    p_stage.set_defaults(func=cmd_stage)

    args = parser.parse_args()
    args.func(args)


def cmd_run(args):
    routed = route(args.trigger)
    if routed["scene"] == "UNKNOWN":
        print(json.dumps(routed, ensure_ascii=False, indent=2))
        return
    conn = _connect()
    from supervisor_state import cmd_new
    # 复用 supervisor_state 的事件创建逻辑
    import argparse as _argparse
    na = _argparse.Namespace(scene=routed["scene"], risk=None, trigger=args.trigger)
    created = cmd_new(na)
    event_id = created["event_id"]
    execute_dag(event_id, routed["scene"], conn,
                args.flood_limit, args.safe_discharge, args.dry_run, args.approve)
    conn.close()


def cmd_resume(args):
    conn = _connect()
    ev = conn.execute("SELECT scene, status FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        print(json.dumps({"error": f"事件不存在: {args.event}"}, ensure_ascii=False))
        conn.close()
        return
    execute_dag(args.event, ev["scene"], conn,
                args.flood_limit, args.safe_discharge, dry_run=False, approve=args.approve)
    conn.close()


def cmd_stage(args):
    """单阶段执行（调试）：从 DAG 中取该阶段命令执行并写 State"""
    conn = _connect()
    ev = conn.execute("SELECT scene FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        print(json.dumps({"error": f"事件不存在: {args.event}"}, ensure_ascii=False))
        conn.close()
        return
    agent, cmd = STAGE_CMDS.get(ev["scene"], {}).get(args.stage, (None, None))
    if cmd is None:
        print(json.dumps({"error": f"场景{ev['scene']}无阶段{args.stage}命令"},
                         ensure_ascii=False))
        conn.close()
        return
    out = run_stage_cmd(cmd)
    conn.execute(
        "INSERT OR REPLACE INTO stage_results (event_id, stage, agent, result_json, status, ts) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (args.event, args.stage, agent,
         json.dumps(out, ensure_ascii=False)[:8000],
         "ok" if out.get("ok") else "error"),
    )
    conn.commit()
    conn.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()