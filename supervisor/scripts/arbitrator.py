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