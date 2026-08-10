#!/usr/bin/env python3
"""
Hermes Agent 诊断工作流测试运行器
在 hermes 环境中运行 diagnose → verify → auto-fix 完整工作流

用法:
    python3 hermes_diagnose_runner.py                    # 运行所有测试场景
    python3 hermes_diagnose_runner.py --scenario P0-1   # 运行指定场景
    python3 hermes_diagnose_runner.py --dry-run          # 只显示场景，不执行

环境变量:
    HERMES_CMD      hermes 可执行路径（默认 hermes）
    SRM_DB_*       数据库连接配置
"""

import subprocess
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 标准导入片段（统一共享层定位）──────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from lib.db import execute_query_list, get_connection  # charset/超时/池化由 lib/db.py 统一
from lib.tenant import current_tenant_id  # 水库身份（SRM_TENANT_ID，默认18三岔）

# ============================================================
# 配置
# ============================================================
HERMES_CMD = os.getenv('HERMES_CMD', 'hermes')
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SKILL_DIR, '..', 'hermes-results')

# ============================================================
# 测试场景（基于 REAL-WORLD-PROBLEMS.md 真实数据）
# ============================================================
TEST_SCENARIOS = [
    {
        'id': 'P0-1',
        'name': '水位数据停止更新',
        'severity': 'P0',
        'description': '水位数据已停止更新 221 小时（9 天前），空值率 63%',
        'question': '''水位数据异常，连续 3 小时未更新。

数据库探查结果：
- 表：st_rsvr_r，总行数：194,111
- rz 为空：122,341（63% 空值率）
- 最新时间：2026-07-01 08:00:00（221 小时前）
- stcd=3（三岔站）数据量：仅 24 条

请执行 8 Phase 诊断，找出根因并提出修复建议。''',
        'expected_root_cause': '数据采集 pipeline 故障',
        'database_check': {
            'type': 'water_level',
            'max_age_hours': 1,  # 应 <1 小时
        }
    },
    {
        'id': 'P0-2',
        'name': '降雨预报完全过期',
        'severity': 'P0',
        'description': '降雨预报已停止更新 220 小时，无未来预报数据',
        'question': '''降雨预报数据异常。

数据库探查结果：
- 表：f_rnfl_h，总行数：7,712
- 最新预报时间：2026-07-01 09:00:00（220 小时前）
- 未来预报行数（YMDH > NOW()）：0
- 最新批次时间：2026-06-30 09:00:00（244 小时前）

请执行 8 Phase 诊断，找出根因并提出修复建议。''',
        'expected_root_cause': '数据采集 pipeline 故障',
        'database_check': {
            'type': 'rainfall_forecast',
            'max_age_hours': 6,
        }
    },
    {
        'id': 'P1-1',
        'name': '告警大量堆积',
        'severity': 'P1',
        'description': '未确认告警堆积 1,165 条（红/橙高危 463 条）',
        'question': '''告警系统异常，有大量未确认告警堆积。

数据库探查结果：
- 未确认告警总数：1,165 条
- 红色（I级）：238 条
- 橙色（II级）：225 条
- 黄色（III级）：273 条
- 蓝色（IV级）：429 条
- 最新告警时间：2026-06-09 10:49:20（30 天前）

请执行 8 Phase 诊断，分析告警堆积原因并提出处理建议。''',
        'expected_root_cause': '告警规则过敏感或误报',
        'database_check': {
            'type': 'alerts',
            'max_unconfirmed': 100,  # 应 <100
        }
    },
]

# ============================================================
# 数据库检查脚本
# ============================================================

def check_database(scenario):
    """执行场景对应的数据库检查"""
    check_type = scenario['database_check']['type']

    tid = current_tenant_id()
    params = ()
    if check_type == 'water_level':
        sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN rz IS NULL THEN 1 ELSE 0 END) as null_count,
            MAX(tm) as latest_time,
            TIMESTAMPDIFF(HOUR, MAX(tm), NOW()) as hours_ago
        FROM st_rsvr_r WHERE deleted=0 AND tenant_id=%s
        """
        params = (tid,)
    elif check_type == 'rainfall_forecast':
        sql = """
        SELECT
            COUNT(*) as total,
            MAX(fymdh) as latest_batch,
            TIMESTAMPDIFF(HOUR, MAX(fymdh), NOW()) as hours_ago,
            SUM(CASE WHEN ymdh > NOW() THEN 1 ELSE 0 END) as future_count
        FROM f_rnfl_h WHERE deleted=0 AND tenant_id=%s
        """
        params = (tid,)
    elif check_type == 'alerts':
        sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN level_r='1' THEN 1 ELSE 0 END) as red,
            SUM(CASE WHEN level_r='2' THEN 1 ELSE 0 END) as orange
        FROM ew_info_message WHERE message_confirm=0 AND deleted=0
        """
        # ew_info_message 跨租户广播，不加 tenant 过滤（见 lib/filters.py）
    else:
        return None

    # 执行查询
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        return {'error': str(e)}


def check_scenario_condition(scenario, db_result):
    """检查场景是否满足触发条件"""
    if not db_result or 'error' in db_result:
        return False, f"数据库查询失败：{db_result.get('error', 'Unknown')}"

    check = scenario['database_check']
    check_type = check['type']

    if check_type == 'water_level':
        hours_ago = db_result.get('hours_ago', 0)
        if hours_ago > check['max_age_hours']:
            return True, f"水位数据过期 {hours_ago} 小时（阈值 {check['max_age_hours']} 小时）"
        else:
            return False, f"水位数据新鲜（{hours_ago} 小时前）"

    elif check_type == 'rainfall_forecast':
        hours_ago = db_result.get('hours_ago', 0)
        if hours_ago > check['max_age_hours']:
            return True, f"降雨预报过期 {hours_ago} 小时（阈值 {check['max_age_hours']} 小时）"
        else:
            return False, f"降雨预报新鲜（{hours_ago} 小时前）"

    elif check_type == 'alerts':
        total = db_result.get('total', 0)
        if total > check['max_unconfirmed']:
            return True, f"未确认告警堆积 {total} 条（阈值 {check['max_unconfirmed']} 条）"
        else:
            return False, f"未确认告警数量正常（{total} 条）"

    return False, "未知检查类型"


# ============================================================
# Hermes 测试运行器
# ============================================================

def run_scenario(scenario, dry_run=False):
    """运行单个诊断场景"""
    sid = scenario['id']
    print(f"\n{'='*70}")
    print(f"场景 {sid}：{scenario['name']}（{scenario['severity']}）")
    print(f"{'='*70}")
    print(f"描述：{scenario['description']}")

    # 步骤 1：检查数据库条件是否满足
    print(f"\n>>> 步骤 1：检查数据库条件...")
    db_result = check_database(scenario)
    if db_result:
        print(f"  数据库查询结果：")
        for k, v in db_result.items():
            print(f"    {k}: {v}")

    should_run, reason = check_scenario_condition(scenario, db_result)
    print(f"  是否满足触发条件：{'✅ 是' if should_run else '❌ 否'}（{reason}）")

    if not should_run and not dry_run:
        print(f"  ⚠️  场景条件未满足，跳过")
        return {'id': sid, 'status': 'skipped', 'reason': reason}

    if dry_run:
        print(f"\n[DRY-RUN] 将在 hermes 中执行以下问题：")
        print(f"{scenario['question']}")
        return {'id': sid, 'status': 'dry-run'}

    # 步骤 2：通过 hermes 运行诊断
    print(f"\n>>> 步骤 2：在 hermes 中运行诊断...")
    print(f"  命令：{HERMES_CMD} chat -q \"<问题>\"")

    try:
        # 构建 hermes 命令
        prompt = f"""请使用 diagnosis-verification Skill 的 diagnose 功能。

{scenario['question']}

请严格按照 8 Phase 执行，并在每 Phase 完成后标注【Phase X 完成】。"""

        result = subprocess.run(
            [HERMES_CMD, 'chat', '-q', prompt],
            capture_output=True,
            text=True,
            timeout=600,  # 10 分钟超时
            cwd=SKILL_DIR
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0 and 'error' not in output.lower()

        # 步骤 3：评估结果
        print(f"\n>>> 步骤 3：评估结果...")
        evaluation = evaluate_diagnosis_output(output, scenario)

        print(f"  评估结果：")
        for criterion, passed in evaluation.items():
            status = '✅' if passed else '❌'
            print(f"    {status} {criterion}")

        all_passed = all(evaluation.values())
        print(f"  总评：{'✅ 通过' if all_passed else '❌ 失败'}")

        # 保存结果
        result_obj = {
            'id': sid,
            'name': scenario['name'],
            'severity': scenario['severity'],
            'timestamp': datetime.now().isoformat(),
            'success': success,
            'output': output,
            'evaluation': evaluation,
            'all_passed': all_passed,
        }

        os.makedirs(RESULTS_DIR, exist_ok=True)
        result_file = os.path.join(RESULTS_DIR, f"{sid}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_obj, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n  结果已保存：{result_file}")

        return result_obj

    except subprocess.TimeoutExpired:
        print(f"  ❌ 超时（>10 分钟）")
        return {'id': sid, 'status': 'timeout', 'error': 'Timeout'}
    except Exception as e:
        print(f"  ❌ 错误：{e}")
        return {'id': sid, 'status': 'error', 'error': str(e)}


def evaluate_diagnosis_output(output, scenario):
    """评估诊断输出质量"""
    output_lower = output.lower()

    return {
        'has_phase0': 'phase 0' in output_lower or '澄清确认' in output,
        'has_phase1': 'phase 1' in output_lower or '全景扫描' in output,
        'has_phase5': 'phase 5' in output_lower or '根因分析' in output,
        'has_evidence_chain': '[事实]' in output or '[推理]' in output or '[结论]' in output,
        'has_root_cause': scenario['expected_root_cause'].lower() in output_lower,
        'has_fix_suggestion': '修复建议' in output or '短期止血' in output or '长期根治' in output,
    }


def run_all_scenarios(dry_run=False):
    """运行所有测试场景"""
    print(f"{'='*70}")
    print(f"水库四预诊断工作流测试")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"场景数：{len(TEST_SCENARIOS)}")
    print(f"{'='*70}")

    results = []
    for scenario in TEST_SCENARIOS:
        result = run_scenario(scenario, dry_run=dry_run)
        results.append(result)

        if not dry_run:
            time.sleep(5)  # 间隔 5 秒，避免限流

    # 汇总
    print(f"\n{'='*70}")
    print(f"测试汇总")
    print(f"{'='*70}")

    if dry_run:
        print(f"模式：dry-run（仅检查场景条件）")
        for r in results:
            print(f"  {r['id']}: {r['status']}")
    else:
        total = len(results)
        completed = sum(1 for r in results if r.get('success', False))
        passed = sum(1 for r in results if r.get('all_passed', False))

        print(f"总场景数：{total}")
        print(f"成功完成：{completed}")
        print(f"评估通过：{passed}")
        print(f"失败：{total - completed}")

        # 保存汇总
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total': total,
            'completed': completed,
            'passed': passed,
            'results': results,
        }
        summary_file = os.path.join(RESULTS_DIR, 'summary.json')
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n汇总已保存：{summary_file}")

    return results


# ============================================================
# 主函数
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Hermes 诊断工作流测试运行器')
    parser.add_argument('--scenario', help='运行指定场景（如 P0-1）')
    parser.add_argument('--dry-run', action='store_true', help='只检查场景条件，不执行')
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    if args.scenario:
        # 运行指定场景
        scenario = next((s for s in TEST_SCENARIOS if s['id'] == args.scenario), None)
        if scenario:
            run_scenario(scenario, dry_run=args.dry_run)
        else:
            print(f"未找到场景：{args.scenario}")
            print(f"可用场景：{[s['id'] for s in TEST_SCENARIOS]}")
    else:
        # 运行所有
        run_all_scenarios(dry_run=args.dry_run)
