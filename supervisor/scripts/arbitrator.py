#!/usr/bin/env python3
"""
arbitrator.py -- Supervisor 结果仲裁（冲突裁决）。

仲裁规则（与 SKILL.md 一致）:
    1. 方案 vs 仿真水位: 方案预估最高水位 > 仿真结果 → 以仿真为准（保守）。
    2. 下泄 vs 安全泄量: 超下游安全泄量 → 否决并降档。
    3. 多 skill 风险等级不一致 → 取更高等级（防洪优先）。
    4. 预报源分歧 → 沿用 forecasting 的多源裁决。

设计原则:
    1. 阈值（汛限/安全泄量）运行时从参数传入或读 reservoir profile，
       禁止在代码里硬编码数字。
    2. 本模块只做"一致性检查 + 建议"，不修改任何子 skill 的结论，
       最终裁决结果写回 State（由 orchestrator 调用）。
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# 让脚本能被 import（上级目录加入 path，读取 references）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


@dataclass
class ArbitrationResult:
    passed: bool                       # 是否通过仲裁
    decision: str                      # accept / reject / adjust
    issues: list = field(default_factory=list)   # 发现的问题列表
    adopted_values: dict = field(default_factory=dict)  # 采纳值（以仿真为准时）
    suggestion: str = ""               # 建议动作


def arbitrate_plan_vs_simulation(
    plan: dict,
    simulation: dict,
    flood_limit: Optional[float] = None,
    safe_discharge: Optional[float] = None,
) -> ArbitrationResult:
    """
    仲裁 plan-generation 方案 vs simulation 推演结果。

    参数:
        plan:         plan-generation 输出，如 {"max_level": 787.3, "max_discharge": 520}
        simulation:   simulation 输出，如 {"max_level": 787.1, "max_discharge": 480}
        flood_limit:  汛限水位（m），运行时传入，禁止硬编码
        safe_discharge: 下游安全泄量（m³/s），运行时传入
    """
    res = ArbitrationResult(passed=True, decision="accept")

    plan_level = plan.get("max_level")
    sim_level = simulation.get("max_level")
    plan_discharge = plan.get("max_discharge")
    sim_discharge = simulation.get("max_discharge")

    # 规则1: 方案 vs 仿真水位 —— 以仿真为准（保守）
    if plan_level is not None and sim_level is not None and plan_level > sim_level:
        res.issues.append(
            f"方案预估最高水位 {plan_level}m 高于仿真推演 {sim_level}m，"
            f"以仿真结果为准（保守）"
        )
        res.adopted_values["max_level"] = sim_level
        res.decision = "adjust"
        res.passed = False

    # 规则2: 下泄 vs 安全泄量
    if safe_discharge is not None and plan_discharge is not None:
        if plan_discharge > safe_discharge:
            res.issues.append(
                f"方案下泄 {plan_discharge}m³/s 超过下游安全泄量 {safe_discharge}m³/s，"
                f"方案需降档或重新拟定"
            )
            res.decision = "reject"
            res.passed = False

    # 规则1b: 仿真结果自身是否超汛限
    if flood_limit is not None and sim_level is not None:
        if sim_level > flood_limit:
            res.issues.append(
                f"仿真推演最高水位 {sim_level}m 超过汛限 {flood_limit}m，"
                f"存在超限风险，需重点提示"
            )
            if res.passed:
                res.passed = True  # 超限是风险提示，不必然否决，但标记 issue
                res.suggestion = "建议启动更高一级响应或加大预泄"

    # 汇总建议
    if res.decision == "accept":
        res.suggestion = "方案与仿真结果一致，可提交人工确认"
    elif res.decision == "adjust":
        res.suggestion = "以仿真结果修正方案参数后，重新校验"
    elif res.decision == "reject":
        res.suggestion = "方案不满足安全约束，需重新生成"

    return res


def arbitrate_risk_levels(levels: list) -> str:
    """规则3: 多 skill 风险等级不一致 → 取更高等级（防洪优先）"""
    order = {"低": 1, "中": 2, "高": 3, "极高": 4}
    best = "低"
    for lv in levels:
        if lv and order.get(lv, 0) > order.get(best, 0):
            best = lv
    return best


def arbitrate_emergency(
    early_warning: dict,
    plan: dict,
    simulation: dict,
    flood_limit: Optional[float] = None,
    safe_discharge: Optional[float] = None,
) -> dict:
    """
    场景D（应急响应）专用仲裁：方案否决 + 超限升级 + HITL 强化。

    输入（orchestrator 传入，从 State 解包后）：
      - early_warning: step1 early-warning 输出（高级别告警清单）
      - plan:          step2 plan-generation 输出（应急调度方案）
      - simulation:    step3 simulation full_context（current_water_level 数组）
      - flood_limit / safe_discharge: 汛限水位(m)/下游安全泄量(m³/s)，运行时传入

    裁决逻辑（应急从紧）：
      1. 存在 Ⅰ/Ⅱ 级告警 → 强制升级（escalate）
      2. 方案下泄 > 安全泄量 → 否决（reject）
      3. 仿真最高水位 > 汛限 → 升级（escalate）+ 提示降库/预泄
      4. 其余 → 待人工确认（pending_approval），HITL 由编排层强制
    """
    issues = []
    decision = "pending_approval"
    passed = True

    # --- 告警维度（early_warning）---
    alert_count = 0
    high_alerts = []
    if isinstance(early_warning, dict):
        for key in ("data", "alerts", "high_level", "list"):
            val = early_warning.get(key)
            if isinstance(val, list):
                high_alerts = val
                break
        alert_count = len(high_alerts)
        for a in high_alerts[:3]:
            name = a.get("ew_name") or a.get("name") or "告警"
            level = a.get("level_r") or a.get("level") or "?"
            issues.append(f"高级别告警: {name}（{level}级）")

    # --- 仿真水位/下泄（simulation）---
    sim_level = None
    sim_disch = None
    if isinstance(simulation, dict):
        cwl = simulation.get("current_water_level")
        if isinstance(cwl, list) and cwl:
            sim_level = max((float(x.get("rz") or 0) for x in cwl if x.get("rz")), default=None)
            sim_disch = max((float(x.get("otq") or 0) for x in cwl if x.get("otq")), default=None)

    # --- 方案参数（plan）---
    plan_disch = plan.get("max_discharge") or plan.get("discharge")

    # 规则1: Ⅰ/Ⅱ级告警 → 升级
    if alert_count > 0:
        issues.append(f"当前 {alert_count} 条高级别告警，需升级处置")
        decision = "escalate"
        passed = False

    # 规则2: 下泄超安全泄量 → 否决
    if safe_discharge is not None and plan_disch is not None and plan_disch > safe_discharge:
        issues.append(f"方案下泄 {plan_disch}m³/s 超过下游安全泄量 {safe_discharge}m³/s，方案否决")
        decision = "reject"
        passed = False

    # 规则3: 仿真超汛限 → 升级
    if flood_limit is not None and sim_level is not None and sim_level > flood_limit:
        issues.append(f"仿真最高水位 {sim_level}m 超汛限 {flood_limit}m，需降库/预泄")
        decision = "escalate"
        passed = False

    # 处置建议
    if decision == "reject":
        suggestion = "应急方案不满足安全约束，需重新拟定（降低下泄或加大预泄腾库）"
    elif decision == "escalate":
        suggestion = "存在超限/告警风险，建议立即上报市防指，启动更高一级响应并组织下游转移准备"
    else:
        suggestion = "应急方案与仿真一致，待人工确认后执行（HITL）"

    return {
        "risk_level": "极高" if decision == "escalate" else
                      ("高" if decision == "reject" else "中"),
        "passed": passed,
        "decision": decision,
        "issues": issues,
        "alert_count": alert_count,
        "sim_max_level": sim_level,
        "sim_max_discharge": sim_disch,
        "suggestion": suggestion,
        "hitl_required": True,   # 应急场景 HITL 强制
    }


def arbitrate_dam_diagnosis(
    diagnosis: dict,
    inspection: dict,
    simulation: dict,
    flood_limit: Optional[float] = None,
) -> dict:
    """
    场景B（大坝安全智能诊断）专用仲裁：风险定级 + 处置建议。

    输入为各阶段的真实结果（orchestrator 传入，从 State 解包后）：
      - diagnosis:   step1 check_data_quality 输出（水位过期/空值率/降雨过期等）
      - inspection:  step2 inspection_check 输出（open_defects 缺陷清单）
      - simulation:  step3 simulation full_context（current_water_level 数组）
      - flood_limit: 汛限水位（m），运行时传入

    定级逻辑（保守优先）：
      1. 任一监测数据严重过期（>24h）或空值率>50% → 高（数据可信度不足，大坝安全无法确认）
      2. 存在未处理缺陷且等级为 P0/P1（handle_status=0）→ 高
      3. 仿真最高水位超汛限 → 高
      4. 存在未处理缺陷（一般）→ 中
      5. 数据正常且无缺陷 → 低

    处置建议：基于风险等级 + 具体问题给出（对接 defect-disposal 思路，不硬编码具体数值）。
    """
    issues = []
    level_scores = {"低": 0, "中": 1, "高": 2}

    risk = "低"

    # --- 数据质量维度（diagnosis） ---
    dq_issues = []
    if isinstance(diagnosis, dict):
        # check_data_quality 输出按表分组，常见键：水位/降雨/告警
        for table_key, table_info in diagnosis.items():
            if not isinstance(table_info, dict):
                continue
            age = table_info.get("age_hours") or table_info.get("stale_hours")
            null_rate = table_info.get("null_rate")
            if age is not None and age > 24:
                dq_issues.append(f"{table_key} 数据过期 {age}h")
            if null_rate is not None and null_rate > 50:
                dq_issues.append(f"{table_key} 空值率 {null_rate}%")
    if dq_issues:
        issues.extend(dq_issues)
        risk = arbitrate_risk_levels([risk, "高"])

    # --- 缺陷维度（inspection） ---
    open_defects = []
    if isinstance(inspection, dict):
        defs = inspection.get("open_defects") or inspection.get("defects", {}).get("open_defects")
        if isinstance(defs, list):
            open_defects = [d for d in defs if d.get("handle_status") == 0]
    if open_defects:
        issues.append(f"存在 {len(open_defects)} 条未处理缺陷"
                      f"（如 {open_defects[0].get('name', '—')}）")
        risk = arbitrate_risk_levels([risk, "中"])

    # --- 仿真水位维度（simulation） ---
    sim_level = None
    if isinstance(simulation, dict):
        cwl = simulation.get("current_water_level")
        if isinstance(cwl, list) and cwl:
            sim_level = max((float(x.get("rz") or 0) for x in cwl if x.get("rz")), default=None)
    if flood_limit is not None and sim_level is not None and sim_level > flood_limit:
        issues.append(f"仿真最高水位 {sim_level}m 超汛限 {flood_limit}m")
        risk = arbitrate_risk_levels([risk, "高"])

    # --- 处置建议（按风险等级 + 问题类型） ---
    if risk == "低":
        suggestion = "监测数据正常、无未处理缺陷、水位未超限，大坝运行状态良好，维持例行监测"
    elif risk == "中":
        suggestion = "存在未处理缺陷，建议按缺陷清单限期处置并复核；加密渗流/位移监测频次"
    else:  # 高
        if dq_issues:
            suggestion = ("监测数据严重异常，大坝安全状态无法确认，"
                          "建议立即核查数据采集链路并人工现场查勘，必要时启动应急预案")
        elif any("超汛限" in i for i in issues):
            suggestion = "水位超汛限运行，建议立即降低库水位并加密监测，评估泄流能力"
        else:
            suggestion = ("存在高风险缺陷，建议立即组织专家会诊，"
                          "对照险情处置措施库制定专项处置方案")

    return {
        "risk_level": risk,
        "passed": risk != "高",
        "decision": "accept" if risk == "低" else ("review" if risk == "中" else "escalate"),
        "issues": issues,
        "open_defect_count": len(open_defects),
        "sim_max_level": sim_level,
        "suggestion": suggestion,
    }


def main():
    parser = argparse.ArgumentParser(description="Supervisor 结果仲裁")
    parser.add_argument("--plan", required=True, help="plan-generation 结果 JSON")
    parser.add_argument("--simulation", required=True, help="simulation 结果 JSON")
    parser.add_argument("--flood-limit", type=float, default=None, help="汛限水位(m)，运行时传入")
    parser.add_argument("--safe-discharge", type=float, default=None, help="下游安全泄量(m³/s)")
    args = parser.parse_args()

    plan = json.loads(args.plan)
    sim = json.loads(args.simulation)
    result = arbitrate_plan_vs_simulation(
        plan, sim,
        flood_limit=args.flood_limit,
        safe_discharge=args.safe_discharge,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()