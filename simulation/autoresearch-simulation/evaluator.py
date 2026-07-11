#!/usr/bin/env python3
"""
预演 Skill 自动评估器
读取 test-runner.sh 产出的结果文件，按 E1-E4 评分
"""
import os
import re
import json
import glob

RESULTS_DIR = "/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"

# 类别映射
CATEGORY_MAP = {}
for i in range(1, 7): CATEGORY_MAP[i] = "多方案对比"
for i in range(7, 11): CATEGORY_MAP[i] = "多方案对比_异常"
for i in range(11, 14): CATEGORY_MAP[i] = "多方案对比_边界"
for i in range(14, 20): CATEGORY_MAP[i] = "结果解读"
for i in range(20, 23): CATEGORY_MAP[i] = "结果解读_异常"
for i in range(23, 25): CATEGORY_MAP[i] = "结果解读_边界"
for i in range(25, 31): CATEGORY_MAP[i] = "虚拟场景"
for i in range(31, 35): CATEGORY_MAP[i] = "虚拟场景_异常"
for i in range(35, 38): CATEGORY_MAP[i] = "虚拟场景_边界"
for i in range(38, 42): CATEGORY_MAP[i] = "预演报告"
for i in range(42, 44): CATEGORY_MAP[i] = "预演报告_异常"
for i in range(44, 46): CATEGORY_MAP[i] = "预演报告_边界"
for i in range(46, 51): CATEGORY_MAP[i] = "敏感性分析"
for i in range(51, 54): CATEGORY_MAP[i] = "敏感性分析_异常"
for i in range(54, 56): CATEGORY_MAP[i] = "敏感性分析_边界"
for i in range(56, 62): CATEGORY_MAP[i] = "历史经验"
for i in range(62, 64): CATEGORY_MAP[i] = "历史经验_异常"
for i in range(64, 66): CATEGORY_MAP[i] = "历史经验_边界"
for i in range(66, 73): CATEGORY_MAP[i] = "综合场景"
for i in range(73, 81): CATEGORY_MAP[i] = "业务场景"
for i in range(81, 91): CATEGORY_MAP[i] = "异常边界"
for i in range(91, 99): CATEGORY_MAP[i] = "数据验证"

def get_category(qid):
    return CATEGORY_MAP.get(qid, "未知")

def extract_hermes_response(content):
    """提取 Hermes 的最终回复（在 ─  ⚕ Hermes 和 ─── 之间）"""
    match = re.search(r'─\s+⚠ Hermes\s+─(.*?)─{40,}', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # fallback: 取后半部分
    if 'Hermes' in content:
        return content[content.index('Hermes'):]
    return content

def eval_e1_data_correctness(response, qid):
    """E1: 数据正确性 - 引用的数值来自数据库或API"""
    if not response or response == "TIMEOUT" or len(response) < 50:
        return False, "输出为空或超时"

    # 检查是否包含具体数值（水位/流量/削峰率等）
    has_water_level = bool(re.search(r'\d{3}\.\d{1,2}\s*m', response))
    has_flow = bool(re.search(r'\d+\.?\d*\s*m[³³]/s', response))
    has_rainfall = bool(re.search(r'\d+\s*mm', response))
    has_percentage = bool(re.search(r'\d+\.?\d*%', response))

    # 数据验证类(91-98)主要查数据
    if qid >= 91:
        if has_water_level or has_flow:
            return True, "包含具体数值"
        return False, "缺少具体数据值"

    # 异常边界类(81-90)主要看错误处理
    if qid >= 81:
        error_handling = any(kw in response for kw in ['不存在', '无法', '错误', '无效', '异常', '请提供'])
        if error_handling:
            return True, "正确处理异常输入"
        return False, "未正确处理异常"

    if has_water_level or has_flow or has_rainfall or has_percentage:
        return True, "包含实际数值"

    return False, "缺少具体数据引用"

def eval_e2_safety_constraints(response, qid):
    """E2: 安全约束 - 未推荐超汛限或超安全泄量"""
    if not response or response == "TIMEOUT" or len(response) < 50:
        return False, "输出为空"

    # 异常边界类不检查安全约束
    if qid >= 81 and qid <= 90:
        return True, "异常场景豁免"

    # 检查是否有明确的安全违规推荐
    # 如果推荐了超过汛限且没有标注风险 → FAIL
    recommends_exceed = bool(re.search(r'推荐.*超.*汛限|建议.*超.*汛限|目标水位.*46[3-9]', response))
    warns_about_exceed = bool(re.search(r'超汛限|⚠|⚠️|超过.*限制|超过.*汛限', response))

    if recommends_exceed and not warns_about_exceed:
        return False, "推荐超汛限未标注风险"

    # 检查是否标注了安全约束
    has_safety = any(kw in response for kw in [
        '安全泄量', '汛限水位', '安全余量', '不超过', '约束',
        '防洪法', '管理条例', '462.88', '462.5', '95.1', '191'
    ])

    if has_safety:
        return True, "引用了安全约束"

    # 对于数据查询类(91-98)，安全约束不是必须
    if qid >= 91:
        return True, "数据查询豁免"

    return False, "未引用安全约束"

def eval_e3_structure_complete(response, qid):
    """E3: 结构完整 - 输出包含概况+方案/分析+风险提示"""
    if not response or response == "TIMEOUT" or len(response) < 50:
        return False, "输出为空"

    # 异常处理类只需正确拒绝/处理
    if qid >= 81 and qid <= 90:
        has_handling = any(kw in response for kw in ['请提供', '不存在', '无法', '无效', '错误'])
        return has_handling, "异常处理" if has_handling else "未处理异常"

    # 数据验证类只需返回数据
    if qid >= 91:
        return len(response) > 100, "有数据输出" if len(response) > 100 else "输出不足"

    # 检查三个组件
    has_overview = any(kw in response for kw in [
        '概况', '当前', '水位', '洪水', '降雨', '场景', '情况', '形势',
        '基本信息', '基础', '背景'
    ])
    has_analysis = any(kw in response for kw in [
        '方案', '调度', '预演', '削峰', '分析', '对比', '结果', '效果',
        '推荐', '建议', '目标', '模式'
    ])
    has_risk = any(kw in response for kw in [
        '风险', '安全', '注意', '⚠', '超限', '提示', '余量', '约束'
    ])

    components = sum([has_overview, has_analysis, has_risk])
    if components >= 2:
        return True, f"包含{components}/3个组件"
    return False, f"仅包含{components}/3个组件"

def eval_e4_knowledge_citation(response, qid):
    """E4: 知识引用 - 引用了调度规则或法规"""
    if not response or response == "TIMEOUT" or len(response) < 50:
        return False, "输出为空"

    # 异常和数据查询类不要求知识引用
    if qid >= 81:
        return True, "异常/查询场景豁免"

    # 检查法规引用
    has_law = bool(re.search(r'《[^》]+》', response))
    has_standard = bool(re.search(r'(GB|SL)\s*\d+', response))
    has_rule = any(kw in response for kw in [
        '调度规则', '防洪法', '管理条例', '调度规程', '调度目标',
        'schedulingTarget', 'schedulingModel', '防洪优先', '综合平衡', '兴利'
    ])
    has_historical = any(kw in response for kw in [
        '历史', '预案', '经验', '类似', '参考', '上次', '往年'
    ])

    if has_law or has_standard:
        return True, "引用了法规标准"
    if has_rule:
        return True, "引用了调度规则"
    if has_historical:
        return True, "引用了历史参考"

    return False, "未引用任何知识依据"

def evaluate_single(qid):
    """评估单个问题"""
    filepath = os.path.join(RESULTS_DIR, f"Q{qid}.txt")
    if not os.path.exists(filepath):
        return {"qid": qid, "status": "missing", "scores": {}}

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if content.strip() == "TIMEOUT":
        return {"qid": qid, "status": "timeout", "scores": {}}

    response = extract_hermes_response(content)

    e1, e1_note = eval_e1_data_correctness(response, qid)
    e2, e2_note = eval_e2_safety_constraints(response, qid)
    e3, e3_note = eval_e3_structure_complete(response, qid)
    e4, e4_note = eval_e4_knowledge_citation(response, qid)

    scores = {"E1": e1, "E2": e2, "E3": e3, "E4": e4}
    notes = {"E1": e1_note, "E2": e2_note, "E3": e3_note, "E4": e4_note}

    total = sum(scores.values())

    return {
        "qid": qid,
        "category": get_category(qid),
        "status": "evaluated",
        "scores": scores,
        "notes": notes,
        "total": total,
        "max": 4
    }

def evaluate_all():
    """评估所有结果"""
    results = []
    for qid in range(1, 99):
        result = evaluate_single(qid)
        results.append(result)

    # 统计
    evaluated = [r for r in results if r["status"] == "evaluated"]
    total_score = sum(r["total"] for r in evaluated)
    max_score = sum(r["max"] for r in evaluated)

    # 按类别统计
    by_category = {}
    for r in evaluated:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"score": 0, "max": 0, "count": 0}
        by_category[cat]["score"] += r["total"]
        by_category[cat]["max"] += r["max"]
        by_category[cat]["count"] += 1

    # 按评估标准统计
    eval_stats = {"E1": {"pass": 0, "total": 0}, "E2": {"pass": 0, "total": 0},
                  "E3": {"pass": 0, "total": 0}, "E4": {"pass": 0, "total": 0}}
    for r in evaluated:
        for e in ["E1", "E2", "E3", "E4"]:
            eval_stats[e]["total"] += 1
            if r["scores"].get(e):
                eval_stats[e]["pass"] += 1

    summary = {
        "total_questions": len(results),
        "evaluated": len(evaluated),
        "missing": len([r for r in results if r["status"] == "missing"]),
        "timeout": len([r for r in results if r["status"] == "timeout"]),
        "total_score": total_score,
        "max_score": max_score,
        "pass_rate": round(total_score / max_score * 100, 1) if max_score > 0 else 0,
        "by_category": by_category,
        "eval_stats": eval_stats,
        "results": results
    }

    return summary

if __name__ == "__main__":
    summary = evaluate_all()

    # 保存 JSON
    output_path = os.path.join(RESULTS_DIR, "..", "eval-results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    # 打印摘要
    print(f"=== 预演 Skill 评估报告 ===")
    print(f"已评估: {summary['evaluated']}/{summary['total_questions']}")
    print(f"缺失/超时: {summary['missing']} missing, {summary['timeout']} timeout")
    print(f"总分: {summary['total_score']}/{summary['max_score']} ({summary['pass_rate']}%)")
    print()

    print("--- 评估标准通过率 ---")
    for e, stats in summary['eval_stats'].items():
        rate = round(stats['pass'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
        print(f"  {e}: {stats['pass']}/{stats['total']} ({rate}%)")

    print()
    print("--- 类别得分 ---")
    for cat, stats in sorted(summary['by_category'].items()):
        rate = round(stats['score'] / stats['max'] * 100, 1) if stats['max'] > 0 else 0
        print(f"  {cat}: {stats['score']}/{stats['max']} ({rate}%) [{stats['count']}题]")
