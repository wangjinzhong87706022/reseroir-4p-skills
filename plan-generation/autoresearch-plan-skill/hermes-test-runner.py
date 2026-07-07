#!/usr/bin/env python3
"""
Hermes Agent 预案 Skill 测试运行器
通过 Hermes Agent CLI 运行测试问题，收集和评估结果

用法:
  python3 hermes-test-runner.py                    # 运行所有测试
  python3 hermes-test-runner.py --question Q1      # 运行指定问题
  python3 hermes-test-runner.py --category 预案生成  # 运行指定类别
  python3 hermes-test-runner.py --eval-only        # 只评估已有结果
"""

import subprocess
import json
import os
import sys
import time
from datetime import datetime

# ============================================================
# 配置
# ============================================================
HERMES_CMD = "/opt/git/hermes-agent/venv/bin/hermes"
SKILL_DIR = "/opt/git/hermes-agent/skills/plan-generation"
RESULTS_DIR = os.path.join(SKILL_DIR, "autoresearch-plan-skill", "hermes-results")
DB_HOST = "127.0.0.1"
DB_NAME = "powerelf_srm_yml"

# ============================================================
# 测试问题集（v2 完整版）
# ============================================================
TEST_QUESTIONS = [
    # 一、预案生成类
    {"id": "Q1", "category": "预案生成", "difficulty": "Hard",
     "question": "今天是 2026年6月5日 08:00，当前水位 459.18m，气象预报未来 48 小时有暴雨（预计降雨 80-120mm），请生成一套防洪优先的调度预案。"},
    {"id": "Q2", "category": "预案生成", "difficulty": "Hard",
     "question": "今天是 2026年6月3日 10:00，当前水位 458.5m，未来 72 小时无强降雨，天气晴好。请生成一套综合平衡的调度预案。"},
    {"id": "Q3", "category": "预案生成", "difficulty": "Hard",
     "question": "今天是 2026年6月1日 08:00，当前水位 453.0m（接近死水位 451m），未来一周无有效降雨，下游灌溉需求增加。请生成一套兴利保供的调度预案。"},
    {"id": "Q4", "category": "预案生成", "difficulty": "Hard",
     "question": "今天是 2026年6月5日 08:00，当前水位 459.18m，未来 48 小时预报降雨 100mm。请生成 3 个不同策略的调度方案（防洪/综合/兴利），并对比推荐最优方案。"},

    # 二、预案解读类
    {"id": "Q9", "category": "预案解读", "difficulty": "Medium",
     "question": "预案 id=717（2026年5月20日防洪安全方案）已执行完成，请解读该预案的调度效果：起调水位 459.81m，最高允许水位 462.88m，调度时长 24 小时。这个方案效果怎么样？"},
    {"id": "Q10", "category": "预案解读", "difficulty": "Medium",
     "question": "预案 id=717 的调度数据显示，前 12 小时闸门开度逐渐增大（0.05→0.32），后 12 小时逐渐减小（0.32→0.04）。请解释这种调度曲线的含义和设计意图。"},

    # 三、形势研判类
    {"id": "Q14", "category": "形势研判", "difficulty": "Medium",
     "question": "今天是 2026年6月5日 08:00，当前水位 459.18m，未来 48 小时预报降雨 80mm，气象台发布暴雨黄色预警。请评估当前防汛形势，是否需要启动预案？"},
    {"id": "Q15", "category": "形势研判", "difficulty": "Medium",
     "question": "当前水位 462.3m，汛限水位 462.5m，未来 6 小时预报降雨 30mm。当前水位安全吗？需要采取什么措施？"},

    # 四、历史参考类
    {"id": "Q19", "category": "历史参考", "difficulty": "Medium",
     "question": "当前预报未来 24 小时降雨 80mm，起调水位约 459m。历史上有没有类似条件的洪水？当时是怎么调度的？"},
    {"id": "Q21", "category": "历史参考", "difficulty": "Medium",
     "question": "2018 年第二场次洪水（id=1）期间，入库洪峰 61.41 m³/s，出库 10.08 m³/s，削峰率 23.34%。从中可以总结什么调度经验？"},

    # 五、调度决策类
    {"id": "Q24", "category": "调度决策", "difficulty": "Hard",
     "question": "当前水位 460.0m，未来 24 小时预报降雨 50mm，下游河道水位正常。应该选择防洪优先还是综合平衡？"},
    {"id": "Q28", "category": "调度决策", "difficulty": "Hard",
     "question": "下游安全泄量为 95.1 m³/s，入库洪峰预计 200 m³/s。在这种约束下，应该如何调度？水库能拦蓄多少？"},

    # 六、预案管理类
    {"id": "Q30", "category": "预案管理", "difficulty": "Easy",
     "question": "调度人员想查看最近一个月生成的所有防洪优先预案，有哪些？它们的参数有什么变化趋势？"},
    {"id": "Q33", "category": "预案管理", "difficulty": "Easy",
     "question": "预案和预演有什么区别？什么情况下用预案，什么情况下用预演？"},

    # 七、应急响应类
    {"id": "Q35", "category": "应急响应", "difficulty": "Expert",
     "question": "今天凌晨 03:00，水位突然涨到 463.0m，超过汛限水位 462.5m。现在是凌晨 03:30，应该如何应急调度？"},
    {"id": "Q36", "category": "应急响应", "difficulty": "Expert",
     "question": "气象台发布暴雨红色预警（未来 6 小时降雨 100mm），当前水位 461.5m，现在是下午 14:00。按照应急预案，应该采取什么措施？"},

    # 八、综合场景类
    {"id": "Q40", "category": "综合场景", "difficulty": "Expert",
     "question": "今天是 2026 年 5 月 1 日，进入汛期第一天，当前水位 461.0m，气象预报未来 3 天有中到大雨（50-80mm）。作为汛期首场洪水，应该如何制定调度方案？"},
    {"id": "Q45", "category": "综合场景", "difficulty": "Expert",
     "question": "假设发生 500 年一遇洪水（入库洪峰 1000 m³/s），当前水位 462.0m，水库能拦蓄多少？会不会溃坝？"},
]

# ============================================================
# 评估标准
# ============================================================
EVAL_CRITERIA = [
    {"id": "E1", "name": "数据查询正确", "description": "输出中引用的水位/降雨/配置值与数据库实际值一致"},
    {"id": "E2", "name": "参数合理", "description": "推荐的调度参数在配置约束范围内"},
    {"id": "E3", "name": "知识引用", "description": "回答中引用了知识库中的规则或标准"},
    {"id": "E4", "name": "安全约束", "description": "不推荐超过汛限水位或安全泄量的参数"},
    {"id": "E5", "name": "历史参考", "description": "提及了历史预案或历史洪水的参考"},
    {"id": "E6", "name": "输出完整", "description": "包含形势判断+方案推荐+风险提示"},
]

# ============================================================
# 核心函数
# ============================================================

def run_question(question_obj):
    """通过 Hermes Agent 运行单个问题"""
    qid = question_obj['id']
    question = question_obj['question']

    print(f"\n{'='*60}")
    print(f"运行 {qid}: {question_obj['category']} ({question_obj['difficulty']})")
    print(f"问题: {question[:80]}...")
    print(f"{'='*60}")

    # 构建完整 prompt
    prompt = f"""请使用 plan-generation skill 回答以下问题。
请先查询数据库获取实际数据，然后基于实际数据回答。

{question}"""

    # 运行 hermes CLI
    try:
        result = subprocess.run(
            [HERMES_CMD, "chat", "-q", prompt],
            capture_output=True,
            text=True,
            timeout=180,  # 3 分钟超长
            cwd="/opt/git/hermes-agent"
        )

        output = result.stdout + result.stderr

        # 保存结果
        result_obj = {
            "id": qid,
            "category": question_obj['category'],
            "difficulty": question_obj['difficulty'],
            "question": question,
            "output": output,
            "timestamp": datetime.now().isoformat(),
            "success": result.returncode == 0 and "API call failed" not in output
        }

        # 保存到文件
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(os.path.join(RESULTS_DIR, f"{qid}.json"), 'w', encoding='utf-8') as f:
            json.dump(result_obj, f, ensure_ascii=False, indent=2)

        if result_obj['success']:
            print(f"  ✅ 成功 ({len(output)} 字符)")
        else:
            print(f"  ❌ 失败")
            if "API call failed" in output:
                print(f"     原因: 模型 API 不可用")
            else:
                print(f"     原因: {output[:100]}...")

        return result_obj

    except subprocess.TimeoutExpired:
        print(f"  ❌ 超时")
        return {"id": qid, "success": False, "output": "timeout"}
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return {"id": qid, "success": False, "output": str(e)}

def evaluate_result(result_obj):
    """评估单个结果"""
    if not result_obj.get('success', False):
        return {eid: False for eid in ['E1', 'E2', 'E3', 'E4', 'E5', 'E6']}

    output = result_obj.get('output', '').lower()

    return {
        'E1': any(kw in output for kw in ['459', '460', '462', '水位', 'm']),
        'E2': '调度' in output or '方案' in output or '参数' in output,
        'E3': '规程' in output or '标准' in output or '规范' in output or '知识' in output,
        'E4': not ('463' in output and '推荐' in output),  # 不推荐超汛限
        'E5': '历史' in output or '预案' in output or '参考' in output,
        'E6': '方案' in output and ('风险' in output or '建议' in output),
    }

def run_all_tests():
    """运行所有测试"""
    print(f"=== 开始运行 {len(TEST_QUESTIONS)} 个测试问题 ===")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for q in TEST_QUESTIONS:
        result = run_question(q)
        results.append(result)
        time.sleep(2)  # 间隔 2 秒避免限流

    # 汇总
    successful = sum(1 for r in results if r.get('success', False))
    print(f"\n{'='*60}")
    print(f"测试完成: {successful}/{len(results)} 成功")
    print(f"{'='*60}")

    # 保存汇总
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "successful": successful,
        "results": results
    }
    with open(os.path.join(RESULTS_DIR, "summary.json"), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return results

# ============================================================
# 主函数
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--question', help='运行指定问题 (如 Q1)')
    parser.add_argument('--category', help='运行指定类别')
    parser.add_argument('--eval-only', action='store_true', help='只评估已有结果')
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    if args.eval_only:
        # 只评估已有结果
        print("评估已有结果...")
        # TODO: 实现评估逻辑
    elif args.question:
        # 运行指定问题
        q = next((q for q in TEST_QUESTIONS if q['id'] == args.question), None)
        if q:
            run_question(q)
        else:
            print(f"未找到问题: {args.question}")
    elif args.category:
        # 运行指定类别
        questions = [q for q in TEST_QUESTIONS if q['category'] == args.category]
        print(f"运行 {len(questions)} 个 {args.category} 问题...")
        for q in questions:
            run_question(q)
    else:
        # 运行所有
        run_all_tests()
