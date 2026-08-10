#!/usr/bin/env python3
"""
预案分析专用脚本 — 一次获取预案解读/方案对比所需的全部数据
用法:
  python3 query_plan_analysis.py --type plan_detail --plan-id 717
  python3 query_plan_analysis.py --type scheme_compare --rainfall 100
  python3 query_plan_analysis.py --type full_analysis --plan-id 717
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ── 标准导入片段（统一共享层定位）──────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from lib.db import execute_query, execute_query_list, unpack  # noqa: E402
from lib.tenant import current_tenant_id  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)

TENANT = current_tenant_id()

# ============================================================
# Q4 场景：预案解读
# ============================================================

def query_plan_detail(plan_id):
    """获取预案详情（一条SQL完成）"""
    sql = """
    SELECT
        m.id, m.scheme_id, m.alias, m.target_water_level, m.adjusted_water_level,
        m.start_time, m.end_time, m.extend, m.taskid,
        d.tm, d.dispatch_opening, d.gate_opening_flow
    FROM model_result_files m
    LEFT JOIN dispatch_history d ON m.taskid = d.task_id
    WHERE m.id = %s AND m.type = 2 AND m.tenant_id = %s
    ORDER BY d.tm
    """
    return execute_query(sql, (plan_id, TENANT))

def query_plan_actual_water(plan_id):
    """获取预案时段的实测水位"""
    sql = """
    SELECT rz, inq, otq, tm
    FROM st_rsvr_r
    WHERE deleted = 0 AND rz IS NOT NULL AND tenant_id = %s
      AND tm >= (SELECT start_time FROM model_result_files WHERE id = %s)
      AND tm <= (SELECT end_time FROM model_result_files WHERE id = %s)
    ORDER BY tm
    LIMIT 1000
    """
    return execute_query(sql, (TENANT, plan_id, plan_id))

def query_plan_full(plan_id):
    """预案解读完整数据"""
    return {
        'plan_detail': unpack(query_plan_detail(plan_id)),
        'actual_water': unpack(query_plan_actual_water(plan_id)),
    }

# ============================================================
# Q5 场景：多方案对比
# ============================================================

def query_scheme_context():
    """获取方案生成所需的上下文"""
    context = {}

    # 当前水位
    context['current_water_level'] = execute_query_list(
        "SELECT rz, inq, otq, tm FROM st_rsvr_r WHERE deleted = 0 AND rz IS NOT NULL AND tenant_id = %s ORDER BY tm DESC LIMIT 1",
        (TENANT,),
    )

    # 汛限水位
    context['flood_limit'] = execute_query_list(
        """SELECT flse_lim_stag, flood_season_name FROM att_res_flse_lim
           WHERE tenant_id = %s
             AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
             AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d') LIMIT 1""",
        (TENANT,),
    )
    if not context['flood_limit']:
        context['flood_limit'] = execute_query_list(
            "SELECT fl_low_lim_lev as flse_lim_stag, '非汛期' as flood_season_name FROM att_res_base WHERE fl_low_lim_lev IS NOT NULL AND tenant_id = %s LIMIT 1",
            (TENANT,),
        )

    # 系统配置
    config_rows = execute_query_list(
        "SELECT config_key, value FROM model_config WHERE config_key IN ('max_water_level','min_water_level','max_drainage_capacity','safe_drainage_capacity') AND deleted = 0 AND tenant_id = %s",
        (TENANT,),
    )
    context['config'] = {r['config_key']: r['value'] for r in config_rows} if config_rows else {}

    # 历史预案（最近5条）
    context['historical_plans'] = execute_query_list(
        "SELECT id, alias, target_water_level, adjusted_water_level, start_time, end_time, extend FROM model_result_files WHERE type = 2 AND tenant_id = %s ORDER BY create_time DESC LIMIT 5",
        (TENANT,),
    )

    return context

def query_similar_plans(adjusted_water_level, limit=3):
    """查询水位相近的历史预案"""
    sql = """
    SELECT id, alias, target_water_level, adjusted_water_level, extend,
           ABS(adjusted_water_level - %s) as water_level_diff
    FROM model_result_files
    WHERE type = 2 AND adjusted_water_level IS NOT NULL AND tenant_id = %s
    ORDER BY water_level_diff
    LIMIT %s
    """
    return execute_query(sql, (adjusted_water_level, TENANT, limit))

# ============================================================
# 完整分析
# ============================================================

def query_full_analysis(plan_id=None):
    """完整分析数据"""
    result = {
        'current_context': query_scheme_context(),
    }

    if plan_id:
        result['plan_detail'] = query_plan_full(plan_id)

    return result

# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='预案分析专用脚本')
    parser.add_argument('--type', required=True,
                        choices=['plan_detail', 'scheme_context', 'similar_plans', 'full_analysis'],
                        help='查询类型')
    parser.add_argument('--plan-id', type=int, help='预案ID')
    parser.add_argument('--water-level', type=float, help='水位（用于相似查询）')
    parser.add_argument('--limit', type=int, default=5, help='返回条数')

    args = parser.parse_args()

    try:
        if args.type == 'plan_detail':
            if not args.plan_id:
                print(json.dumps({'error': '需要 --plan-id 参数'}))
                sys.exit(1)
            result = query_plan_full(args.plan_id)

        elif args.type == 'scheme_context':
            result = query_scheme_context()

        elif args.type == 'similar_plans':
            if not args.water_level:
                print(json.dumps({'error': '需要 --water-level 参数'}))
                sys.exit(1)
            result = query_similar_plans(args.water_level, args.limit)

        elif args.type == 'full_analysis':
            result = query_full_analysis(args.plan_id)

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

if __name__ == '__main__':
    main()
