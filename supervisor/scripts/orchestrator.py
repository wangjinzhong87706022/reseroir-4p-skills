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
from arbitrator import (arbitrate_plan_vs_simulation, arbitrate_dam_diagnosis,
                        arbitrate_emergency, arbitrate_risk_levels, asdict)  # noqa: E402
from supervisor_state import cmd_new  # noqa: E402

# 场景默认优先级映射（D应急=高、A暴雨/B诊断=中、C日常=低；CLI --priority 可覆盖）
_SCENE_DEFAULT_PRIORITY = {"D": "高", "A": "中", "B": "中", "C": "低"}

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
    """执行子 skill 命令，返回 (ok, stdout_text)。超时 60s。
    stdout 截断到 20000 字符：保证 full_context 核心字段（水位/降雨/汛限，位于 JSON 前部）完整可解析。"""
    if dry_run:
        return {"dry_run": True, "cmd": " ".join(str(c) for c in cmd)}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {"ok": r.returncode == 0, "stdout": r.stdout[:20000], "stderr": r.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


def load_reservoir_params() -> dict:
    """
    自动读取当前水库（SRM_TENANT_ID）的仲裁阈值，来源 model_config 表：
      - flood_limit_main      汛限水位（主汛期）
      - safe_drainage_capacity 下游安全泄量
    CLI 显式传入的 --flood-limit / --safe-discharge 优先；未传入时用本函数返回值。
    读取失败（表/行缺失、非数值）时返回空 dict，由调用方决定是否用 CLI 值或跳过。
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    from lib.tenant import current_tenant_id
    from lib.db import execute_query_list

    tenant = current_tenant_id()
    out = {}
    try:
        rows = execute_query_list(
            "SELECT config_key, value FROM model_config "
            "WHERE tenant_id=%s AND deleted=0",
            (tenant,),
        )
        for r in rows:
            key = r.get("config_key")
            val = r.get("value")
            if key in ("flood_limit_main", "safe_drainage_capacity") and val:
                try:
                    out[key] = float(val)
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass  # 读取失败不阻断编排，阈值缺失时仲裁跳过对应检查
    return out


def resolve_thresholds(flood_limit, safe_discharge):
    """合并 CLI 参数与 model_config 自动读取值：CLI 优先，缺省回退自动值。"""
    auto = load_reservoir_params()
    return {
        "flood_limit": flood_limit if flood_limit is not None
                       else auto.get("flood_limit_main"),
        "safe_discharge": safe_discharge if safe_discharge is not None
                          else auto.get("safe_drainage_capacity"),
        "auto": auto,
    }


def _unpack_stage_result(raw_result: str) -> dict:
    """把 State 中某阶段的 result_json 解包为真实数据 dict：
    兼容 {ok, stdout, stderr} 包装结构（stdout 为 JSON 字符串）。"""
    if not raw_result:
        return {}
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("stdout"), str) and data["stdout"].strip():
        try:
            inner = json.loads(data["stdout"])
            if isinstance(inner, dict):
                return inner
        except json.JSONDecodeError:
            try:
                dec = json.JSONDecoder()
                inner, _ = dec.raw_decode(data["stdout"].lstrip())
                if isinstance(inner, dict):
                    return inner
            except (json.JSONDecodeError, ValueError):
                pass
    return data


def do_arbitration(event_id, conn, scene, flood_limit, safe_discharge) -> dict:
    """按场景分派仲裁：
      - 场景A（暴雨研判）: plan-generation vs simulation 交叉校验
      - 场景B（大坝诊断）: 风险定级 + 处置建议（数据质量/缺陷/超限）
      - 场景D（应急响应）: 方案 vs 仿真 + 超限否决（复用 plan-vs-sim，HITL 由编排层控制）
    """
    stages = {
        s["stage"]: dict(s) for s in conn.execute(
            "SELECT stage, result_json FROM stage_results WHERE event_id=?",
            (event_id,),
        ).fetchall()
    }

    # 场景B：大坝诊断专用仲裁
    if scene == "B":
        diagnosis = _unpack_stage_result(stages.get("step1", {}).get("result_json"))
        inspection = _unpack_stage_result(stages.get("step2", {}).get("result_json"))
        simulation = _unpack_stage_result(stages.get("step3", {}).get("result_json"))
        return arbitrate_dam_diagnosis(
            diagnosis, inspection, simulation, flood_limit=flood_limit,
        )

    # 场景D：应急响应专用仲裁（方案否决 + 超限升级 + HITL 强制）
    if scene == "D":
        early_warning = _unpack_stage_result(stages.get("step1", {}).get("result_json"))
        sim_d = _unpack_stage_result(stages.get("step3", {}).get("result_json"))
        plan_d = _unpack_stage_result(stages.get("step2", {}).get("result_json"))
        return arbitrate_emergency(
            early_warning, plan_d, sim_d,
            flood_limit=flood_limit, safe_discharge=safe_discharge,
        )

    # 场景A/D：方案 vs 仿真交叉校验（D 的 HITL 由编排层强制）
    sim = _unpack_stage_result(stages.get("step4", {}).get("result_json"))
    plan = _unpack_stage_result(stages.get("step5", {}).get("result_json"))
    # 从 full_context 结果中提取水位/泄量（simulation 为 current_water_level 数组）
    sim_vals = {"max_level": None, "max_discharge": None}
    if isinstance(sim, dict):
        sim_cwl = sim.get("current_water_level")
        if isinstance(sim_cwl, list) and sim_cwl:
            sim_vals["max_level"] = max(
                (float(x.get("rz") or 0) for x in sim_cwl if x.get("rz")), default=None)
            sim_vals["max_discharge"] = max(
                (float(x.get("otq") or 0) for x in sim_cwl if x.get("otq")), default=None)
        sim_vals["max_level"] = sim_vals["max_level"] or sim.get("max_level") \
            or sim.get("highest_level")
        sim_vals["max_discharge"] = sim_vals["max_discharge"] or sim.get("max_discharge") \
            or sim.get("discharge")

    plan_vals = {"max_level": None, "max_discharge": None}
    if isinstance(plan, dict):
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
    """
    step7 报告生成：从 State 汇总各阶段真实结果，生成结构化研判报告（Markdown）。
    数据来源全部为 stage_results.result_json（各阶段子 skill 的真实输出），
    不做二次查询、不编造数字；缺失阶段标注"未执行"。
    """
    stages = conn.execute(
        "SELECT stage, agent, result_json, status FROM stage_results "
        "WHERE event_id=? ORDER BY stage",
        (event_id,),
    ).fetchall()
    by_stage = {s["stage"]: s for s in stages}
    ev = conn.execute("SELECT scene, status, risk_level, trigger FROM events WHERE event_id=?",
                      (event_id,)).fetchone()

    def _safe_load(stage_key):
        s = by_stage.get(stage_key)
        if not s or s["status"] != "ok":
            return None
        try:
            data = json.loads(s["result_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        # 解包子脚本包装结构: {"ok":true, "stdout":"{...}"} → 取 stdout 内的 JSON
        if isinstance(data, dict) and isinstance(data.get("stdout"), str) and data["stdout"].strip():
            # 先试完整解析; 若因 8000 字符截断失败, 用 raw_decode 取首个完整 JSON 对象
            try:
                inner = json.loads(data["stdout"])
                if isinstance(inner, dict):
                    return inner
            except json.JSONDecodeError:
                try:
                    decoder = json.JSONDecoder()
                    inner, _ = decoder.raw_decode(data["stdout"].lstrip())
                    if isinstance(inner, dict):
                        return inner
                except (json.JSONDecodeError, ValueError):
                    pass
        return data

    # 从各阶段真实结果中提取关键数值
    fc = _safe_load("step1") or {}
    sim = _safe_load("step4") or {}
    plan = _safe_load("step5") or {}
    arb = _safe_load("step6") or {}

    # 水位/入库（forecasting full_context 结构）
    wl = fc.get("current_water_level") or {}
    rz = wl.get("rz")
    inq = wl.get("inq")
    otq = wl.get("otq")
    wlv = wl.get("w")
    flood_limit = fc.get("flood_limit") or {}
    fl_val = flood_limit.get("value")

    # 降雨预报峰值（f_rnfl_h data 数组）
    rf = fc.get("rainfall_forecast") or {}
    rf_data = rf.get("data") or []
    rf_peak = None
    if rf_data:
        rf_peak = max(rf_data, key=lambda x: float(x.get("RN", 0) or 0))

    # 设备核查（step3 inspection）
    insp = _safe_load("step3") or {}
    insp_ov = insp.get("overview") or {}
    equip_total = insp_ov.get("equip_total")
    defect_open = insp_ov.get("defect_open_count")
    offline_open = insp_ov.get("offline_open_count")

    lines = []
    scene_name = {"A": "汛期暴雨研判调度", "B": "大坝安全诊断",
                  "C": "日常管控", "D": "应急响应"}.get(ev["scene"], ev["scene"])
    lines.append(f"# {scene_name}研判报告")
    lines.append("")
    lines.append(f"- **事件号**: {event_id}")
    lines.append(f"- **场景**: {ev['scene']}（{scene_name}）")
    lines.append(f"- **触发**: {ev['trigger'] or '—'}")
    lines.append(f"- **风险等级**: {ev['risk_level'] or '待评定'}")
    lines.append(f"- **状态**: {ev['status']}")
    lines.append("")

    lines.append("## 一、水情实况（step1 forecasting）")
    lines.append("")
    if rz is not None:
        fl_str = f"（汛限 {fl_val}m）" if fl_val else ""
        status = "超汛限" if (fl_val and rz > fl_val) else "未超限"
        lines.append(f"- 当前水位 **{rz}m** {fl_str} → {status}")
        lines.append(f"- 入库流量 {inq} m³/s / 出库 {otq} m³/s / 蓄水量 {wlv} 万m³")
    else:
        lines.append("- 水位数据不可用（st_rsvr_r 无有效行）")
    if rf_peak:
        lines.append(f"- 降雨预报峰值 **{rf_peak.get('RN')}mm/h** @ {rf_peak.get('YMDH')}"
                     f"（预见期 {rf.get('count')}h）")
    lines.append("")

    lines.append("## 二、工情与设备核查（step2/3）")
    lines.append("")
    if equip_total is not None:
        lines.append(f"- 设备总数 {equip_total}，待处理缺陷 {defect_open}，未恢复离线 {offline_open}")
    else:
        lines.append("- 设备核查数据不可用")
    lines.append("")

    lines.append("## 三、推演与方案（step4/5）")
    lines.append("")
    # simulation full_context 结构: current_water_level 是数组（含 rz/inq/otq），
    # 取最高水位/最大下泄；flood_limit 数组取汛限。
    sim_cwl = sim.get("current_water_level") if isinstance(sim, dict) else None
    sim_level = None
    sim_disch = None
    if isinstance(sim_cwl, list) and sim_cwl:
        sim_level = max((float(x.get("rz") or 0) for x in sim_cwl if x.get("rz")), default=None)
        sim_disch = max((float(x.get("otq") or 0) for x in sim_cwl if x.get("otq")), default=None)
    sim_level = sim_level or sim.get("max_level") or sim.get("highest_level")
    sim_disch = sim_disch or sim.get("max_discharge") or sim.get("discharge")
    if sim_level is not None:
        lines.append(f"- 仿真推演最高水位 {sim_level}m / 最大下泄 {sim_disch or '—'} m³/s")
    else:
        lines.append("- 仿真推演结果不可用")
    lines.append("")

    lines.append("## 四、仲裁结论（step6）")
    lines.append("")
    if arb:
        decision = arb.get("decision", "—")
        lines.append(f"- **裁决**: {decision}")
        for issue in arb.get("issues", [])[:5]:
            lines.append(f"  - ⚠️ {issue}")
        if arb.get("suggestion"):
            lines.append(f"- 建议: {arb['suggestion']}")
    else:
        lines.append("- 仲裁未执行（可能停在 HITL 检查点）")
    lines.append("")

    lines.append("## 五、执行链路")
    lines.append("")
    lines.append("| 步骤 | 智能体 | 状态 |")
    lines.append("|------|--------|:----:|")
    for s in stages:
        lines.append(f"| {s['stage']} | {s['agent'] or '—'} | {s['status']} |")
    lines.append("")
    lines.append("---")
    lines.append(f"*生成: supervisor orchestrator（数据源：各阶段真实结果）*")

    return {
        "report_md": "\n".join(lines),
        "water_level": rz,
        "flood_limit": fl_val,
        "rain_peak_rn": rf_peak.get("RN") if rf_peak else None,
        "arbitration": arb.get("decision") if arb else None,
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
            result = do_arbitration(event_id, conn, scene, flood_limit, safe_discharge) \
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

        # 写入 State（上限 40000，避免截断破坏合法 JSON——子脚本 stdout 转义后可能超 8000）
        conn.execute(
            "INSERT OR REPLACE INTO stage_results (event_id, stage, agent, result_json, status, ts) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (event_id, stage, agent, json.dumps(result, ensure_ascii=False)[:40000], status),
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
    # 阈值自动读取：CLI 传入优先，缺省从 model_config 读（汛限/安全泄量）
    thr = resolve_thresholds(args.flood_limit, args.safe_discharge)
    conn = _connect()
    # 优先级：CLI 显式优先，否则按场景自动映射（D=高/A·B=中/C=低）
    priority = getattr(args, "priority", None) or _SCENE_DEFAULT_PRIORITY.get(routed["scene"], "中")
    na = argparse.Namespace(scene=routed["scene"], risk=None, trigger=args.trigger,
                             priority=priority)
    created = cmd_new(na)
    event_id = created["event_id"]
    print(json.dumps({"thresholds": thr, "priority": priority}, ensure_ascii=False, indent=2))
    execute_dag(event_id, routed["scene"], conn,
                thr["flood_limit"], thr["safe_discharge"], args.dry_run, args.approve)
    conn.close()


def cmd_resume(args):
    conn = _connect()
    ev = conn.execute("SELECT scene, status FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        print(json.dumps({"error": f"事件不存在: {args.event}"}, ensure_ascii=False))
        conn.close()
        return
    thr = resolve_thresholds(args.flood_limit, args.safe_discharge)
    execute_dag(args.event, ev["scene"], conn,
                thr["flood_limit"], thr["safe_discharge"], dry_run=False, approve=args.approve)
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
         json.dumps(out, ensure_ascii=False)[:40000],
         "ok" if out.get("ok") else "error"),
    )
    conn.commit()
    conn.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()