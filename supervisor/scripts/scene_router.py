#!/usr/bin/env python3
"""
scene_router.py -- Supervisor 场景识别（路由）。

把用户输入/告警摘要路由到四类场景之一（A 汛期暴雨研判 / B 大坝诊断 / C 日常管控 / D 应急），
并返回对应的 DAG 名称与识别依据。

用法:
    python3 scripts/scene_router.py --trigger "当前有红色暴雨预警，水位持续上涨"
    python3 scripts/scene_router.py --trigger "渗压计数据异常，位移超限"
    python3 scripts/scene_router.py --trigger "每日例行水情汇报"
    python3 scripts/scene_router.py --trigger "闸门故障，需要应急处置"

设计原则:
    1. 关键词表驱动，便于扩展；命中多条时取优先级最高的场景。
    2. 无法识别时返回 scene=UNKNOWN，不猜测，交由上层兜底。
    3. 纯路由职责，不执行任何业务查询。
"""

import argparse
import json
import re
from dataclasses import dataclass, asdict


@dataclass
class SceneRule:
    scene: str        # A/B/C/D/UNKNOWN
    name: str
    priority: int     # 数字越大优先级越高
    keywords: list    # 命中任一即触发
    dag: str


# 优先级设计：应急(D) > 暴雨研判(A) > 大坝诊断(B) > 日常(C)
SCENE_RULES = [
    SceneRule(
        scene="D", name="应急响应", priority=100,
        keywords=["闸门故障", "险情", "溃坝", "管涌", "滑坡", "渗漏", "紧急", "Ⅰ级", "Ⅱ级",
                  "应急响应", "立即", "抢险", "人员转移", "漫坝", "超校核"],
        dag="D",
    ),
    SceneRule(
        scene="A", name="汛期暴雨研判调度", priority=80,
        keywords=["暴雨", "洪水", "超汛限", "入库流量", "水位上涨", "泄洪", "调度",
                  "雨情", "水情", "红色预警", "橙色预警", "降雨", "台风", "预报", "研判",
                  "来水", "预泄", "腾库"],
        dag="A",
    ),
    SceneRule(
        scene="B", name="大坝安全智能诊断", priority=60,
        keywords=["渗压", "渗流", "位移", "裂缝", "大坝安全", "监测异常", "变形",
                  "应力", "安全鉴定", "坝体", "浸润线", "扬压力", "沉降"],
        dag="B",
    ),
    SceneRule(
        scene="C", name="日常精细化管控", priority=40,
        keywords=["日报", "例行", "日常", "值班", "汇报", "水情汇报", "巡检", "台账",
                  "今天情况", "当前水情", "状态"],
        dag="C",
    ),
]


def route(trigger: str) -> dict:
    """识别场景，返回 {scene, name, dag, reason, matched_keywords}"""
    if not trigger or not trigger.strip():
        return {"scene": "UNKNOWN", "name": "未识别", "dag": None,
                "reason": "触发信号为空", "matched_keywords": []}

    # 强信号词：明确时间性/日常性修饰词，命中时优先归入日常管控（C）
    # 例外：应急强词（D）优先级更高（人身/大坝安全优先）
    DAILY_STRONG = ["每日", "例行", "日报", "定时", "周报", "日常"]
    EMERGENCY_STRONG = ["险情", "溃坝", "管涌", "闸门故障", "抢险", "人员转移", "漫坝"]
    # B 场景强词：大坝安全信号，命中时即使有日常修饰词也应归 B 而非 C（P1-2）
    DAM_STRONG = ["渗压", "渗流", "位移", "裂缝", "扬压力", "沉降", "变形超限"]

    if any(k in trigger for k in EMERGENCY_STRONG):
        rule = next(r for r in SCENE_RULES if r.scene == "D")
        hits = [k for k in EMERGENCY_STRONG if k in trigger]
        return {"scene": "D", "name": rule.name, "dag": rule.dag,
                "reason": f"应急强信号: {', '.join(hits[:5])}", "matched_keywords": hits}

    # P1-2 修复：DAILY_STRONG 命中时，若同时命中 DAM_STRONG 则归 B（大坝诊断），
    # 避免"每日监测渗压数据异常"被截到 C 而压制大坝安全信号。
    dam_hits = [k for k in DAM_STRONG if k in trigger]
    if dam_hits:
        rule = next(r for r in SCENE_RULES if r.scene == "B")
        return {"scene": "B", "name": rule.name, "dag": rule.dag,
                "reason": f"大坝安全强信号: {', '.join(dam_hits[:5])}",
                "matched_keywords": dam_hits}

    if any(k in trigger for k in DAILY_STRONG):
        rule = next(r for r in SCENE_RULES if r.scene == "C")
        hits = [k for k in DAILY_STRONG if k in trigger]
        return {"scene": "C", "name": rule.name, "dag": rule.dag,
                "reason": f"日常强信号: {', '.join(hits[:5])}", "matched_keywords": hits}

    best = None
    matched = []
    for rule in SCENE_RULES:
        hits = [kw for kw in rule.keywords if kw in trigger]
        if hits:
            matched.extend(hits)
            if best is None or rule.priority > best.priority:
                best = rule
    if best is None:
        return {"scene": "UNKNOWN", "name": "未识别", "dag": None,
                "reason": "未匹配到已知场景关键词", "matched_keywords": []}
    return {
        "scene": best.scene,
        "name": best.name,
        "dag": best.dag,
        "reason": f"命中关键词: {', '.join(matched[:5])}",
        "matched_keywords": matched,
    }


def main():
    parser = argparse.ArgumentParser(description="Supervisor 场景识别")
    parser.add_argument("--trigger", required=True, help="用户输入/告警摘要")
    args = parser.parse_args()
    print(json.dumps(route(args.trigger), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()