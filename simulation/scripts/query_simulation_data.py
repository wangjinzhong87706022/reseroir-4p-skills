#!/usr/bin/env python3
"""
模拟数据查询脚本 - 直连数据库获取模拟推演所需数据
用法: python3 query_simulation_data.py --type <查询类型> [参数]

共享库: SmartTwinRes-skills/lib/db.py
标准文档: docs/db-credential-config.md
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# ── 标准导入片段（统一共享层定位）──────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from lib.db import execute_query_list, DB_CONFIG  # noqa: E402
from lib.db import execute_query, unpack  # noqa: E402 (用于需要元数据的场景)
from lib.tenant import current_tenant_id, resolve_tenant  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)

DEFAULT_TENANT = current_tenant_id()


def query_current_water_level(tenant_id=None):
    """查询当前水位"""
    tid = resolve_tenant(tenant_id)
    sql = """
    SELECT rz, inq, otq, w, tm
    FROM st_rsvr_r
    WHERE deleted = 0 AND rz IS NOT NULL AND tenant_id = %s
    ORDER BY tm DESC
    LIMIT 1
    """
    return execute_query_list(sql, (tid,))


def query_flood_limit(tenant_id=None):
    """查询当前汛限水位"""
    tid = resolve_tenant(tenant_id)
    # 优先从 att_res_flse_lim 表查询（按当前日期匹配汛期 + tenant_id 过滤）
    # 注：DATE_FORMAT 的 %m/%d 需在 Python 端先格式化，避免与 pymysql 的 %s 占位符冲突
    today_md = datetime.now().strftime("%m%d")
    sql = """
    SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
    FROM att_res_flse_lim
    WHERE tenant_id = %s
      AND flood_season_start <= %s
      AND flood_season_end >= %s
    ORDER BY flse_lim_stag DESC
    LIMIT 1
    """
    results = execute_query_list(sql, (tid, today_md, today_md))
    if results:
        return results

    # 非汛期：从 att_res_base 查询正常蓄水位作为参考
    sql2 = """
    SELECT fl_low_lim_lev as flse_lim_stag,
           '非汛期' as flood_season_name,
           NULL as flood_season_start,
           NULL as flood_season_end
    FROM att_res_base
    WHERE fl_low_lim_lev IS NOT NULL AND deleted = 0 AND tenant_id = %s
    ORDER BY id
    LIMIT 1
    """
    results2 = execute_query(sql2, (tid,))
    if results2:
        return results2

    # 无兜底硬编码值——汛限必须来自数据库。缺失返回空，禁止编造水库特定数值。
    return []


def query_config(tenant_id=None):
    """查询系统配置（取当前租户的一组配置）"""
    tid = resolve_tenant(tenant_id)
    sql = """
    SELECT config_key, value, tenant_id
    FROM model_config
    WHERE config_key IN ('max_water_level', 'min_water_level',
                         'max_drainage_capacity', 'safe_drainage_capacity',
                         'st_rsvr_r_master', 'st_pptn_r_master', 'res_guid',
                         'watershed_area_km2', 'flood_limit_main', 'flood_limit_secondary',
                         'normal_pool_level', 'design_flood_level', 'check_flood_level',
                         'dead_water_level', 'total_storage')
      AND deleted = 0 AND tenant_id = %s
    ORDER BY id DESC
    """
    results = execute_query_list(sql, (tid,))
    config = {}
    for row in results:
        if row['config_key'] not in config:
            config[row['config_key']] = row['value']
    return config


def query_water_level_curve(tenant_id=None):
    """查询水位-库容曲线（按 tenant 过滤，按水位取平均值消除重复点）"""
    tid = resolve_tenant(tenant_id)
    sql = """
    SELECT stag as water_level, AVG(cap) as capacity
    FROM att_res_stag_cap_disc
    WHERE tenant_id = %s
    GROUP BY stag
    ORDER BY stag
    """
    return execute_query_list(sql, (tid,))


def query_discharge_curve(tenant_id=None):
    """查询泄流曲线（按 tenant 过滤）"""
    tid = resolve_tenant(tenant_id)
    sql = """
    SELECT stag as water_level, q as flow
    FROM att_res_discharge_curve
    WHERE tenant_id = %s
    ORDER BY stag
    """
    return execute_query_list(sql, (tid,))


def query_historical_floods(limit=10, tenant_id=None):
    """查询历史洪水（已完成状态）"""
    tid = resolve_tenant(tenant_id)
    sql = """
    SELECT id, name, start_time, end_time, adjusted_water_level,
           target_water_level, status, rainfall_data, remake
    FROM srm_flood_history_base
    WHERE deleted = 0 AND status = 2 AND tenant_id = %s
    ORDER BY create_time DESC
    LIMIT %s
    """
    return execute_query_list(sql, (tid, limit))


def query_flood_detail(flood_id):
    """查询洪水详情"""
    sql = """
    SELECT id, name, start_time, end_time, adjusted_water_level,
           target_water_level, status, rainfall_data, remake,
           rsvr_remake, river_remake, pptn_remake
    FROM srm_flood_history_base
    WHERE id = %s AND deleted = 0
    """
    return execute_query_list(sql, (flood_id,))


def query_flood_result(flood_id):
    """查询洪水结果（统计摘要 type=7）"""
    sql = """
    SELECT type_name, vals, sort
    FROM srm_flood_history_result
    WHERE flood_id = %s AND type = 7 AND deleted = 0
    ORDER BY sort
    """
    return execute_query_list(sql, (flood_id,))


def query_flood_result_curve(flood_id):
    """查询洪水结果曲线（入库/出库/水位过程 type IN 1,2,3,6）"""
    sql = """
    SELECT type, type_name, vals, tm, sort
    FROM srm_flood_history_result
    WHERE flood_id = %s AND type IN (1, 2, 3, 6) AND deleted = 0
    ORDER BY type, tm
    """
    return execute_query_list(sql, (flood_id,))


def query_flood_inflow(flood_id):
    """查询洪水入库流量过程"""
    sql = """
    SELECT vals, tm, sort
    FROM srm_flood_history_result
    WHERE flood_id = %s AND type = 1 AND deleted = 0
    ORDER BY tm
    """
    return execute_query_list(sql, (flood_id,))


def query_flood_statistics(flood_id):
    """查询洪水统计结果"""
    sql = """
    SELECT type_name, vals, sort
    FROM srm_flood_history_result
    WHERE flood_id = %s AND type = 7 AND deleted = 0
    ORDER BY sort
    """
    return execute_query_list(sql, (flood_id,))


def query_similar_floods(rainfall, tolerance=0.2, limit=10):
    """查询相似降雨条件的历史洪水"""
    sql = """
    SELECT id, name, start_time, end_time, adjusted_water_level,
           target_water_level, status, rainfall_data, remake
    FROM srm_flood_history_base
    WHERE deleted = 0 AND status = 2 AND rainfall_data IS NOT NULL
    ORDER BY create_time DESC
    """
    all_floods = execute_query_list(sql)
    # 在 Python 中按降雨量容差过滤
    similar = []
    for flood in all_floods:
        rd = flood.get('rainfall_data')
        if rd is None:
            continue
        try:
            if isinstance(rd, str):
                rd_data = json.loads(rd)
            else:
                rd_data = rd
            # rainfall_data 可能是 dict 或 list
            if isinstance(rd_data, dict):
                total_rain = rd_data.get('total', 0)
            elif isinstance(rd_data, list) and len(rd_data) > 0:
                # 支持多种降雨数据格式: RN/rn/P/p
                total_rain = sum(
                    item.get('RN', item.get('rn', item.get('P', item.get('p', 0))))
                    for item in rd_data if isinstance(item, dict)
                )
            else:
                continue
            if total_rain > 0 and abs(total_rain - rainfall) / rainfall <= tolerance:
                similar.append(flood)
        except (json.JSONDecodeError, TypeError, ZeroDivisionError):
            continue
        if len(similar) >= limit:
            break
    return similar


def query_scenarios():
    """查询调度场景模板"""
    sql = """
    SELECT id, name, scheduling_target, scheduling_model, extend, def_flg
    FROM srm_scheduling_scenario
    WHERE deleted = 0
    ORDER BY def_flg DESC, create_time DESC
    """
    return execute_query_list(sql)


def query_recent_rainfall(hours=48):
    """查询最近降雨实况"""
    sql = """
    SELECT tm, p, dr
    FROM st_pptn_r
    WHERE deleted = 0
      AND tm >= DATE_SUB(NOW(), INTERVAL %s HOUR)
    ORDER BY tm DESC
    """
    return execute_query_list(sql, (hours,))


def query_full_context(hours=48):
    """获取完整上下文数据。

    契约（M4）：除原始数据外，显式汇总 max_level / max_discharge 两个键，
    供仲裁/报告消费端直接读取，避免消费端自行解析数组 + 脆弱回退链。
    """
    cwl = query_current_water_level()
    max_level = None
    max_discharge = None
    if isinstance(cwl, list):
        rzs = [float(x["rz"]) for x in cwl if x.get("rz") is not None]
        otqs = [float(x["otq"]) for x in cwl if x.get("otq") is not None]
        if rzs:
            max_level = max(rzs)
        if otqs:
            max_discharge = max(otqs)
    return {
        'current_water_level': cwl,
        'max_level': max_level,
        'max_discharge': max_discharge,
        'flood_limit': query_flood_limit(),
        'config': query_config(),
        'water_level_curve': query_water_level_curve(),
        'discharge_curve': query_discharge_curve(),
        'historical_floods': query_historical_floods(10),
        'scenarios': query_scenarios(),
        'recent_rainfall': query_recent_rainfall(hours),
    }


def main():
    parser = argparse.ArgumentParser(description='模拟数据查询脚本')
    parser.add_argument('--type', required=True,
                        choices=['current_water_level', 'flood_limit', 'config',
                                 'water_level_curve', 'discharge_curve',
                                 'historical_floods', 'flood_detail',
                                 'flood_result', 'flood_result_curve',
                                 'flood_inflow', 'flood_statistics',
                                 'similar_floods', 'scenarios',
                                 'recent_rainfall', 'full_context'],
                        help='查询类型')
    parser.add_argument('--flood-id', type=int, help='洪水ID（flood_detail等查询必需）')
    parser.add_argument('--rainfall', type=float, help='降雨量（similar_floods查询必需）')
    parser.add_argument('--tolerance', type=float, default=0.2, help='降雨量容差（默认0.2=20%%）')
    parser.add_argument('--hours', type=int, default=48, help='时间范围（小时）')
    parser.add_argument('--limit', type=int, default=10, help='返回条数')
    parser.add_argument('--format', choices=['json', 'table'], default='json',
                        help='输出格式')
    parser.add_argument('--tenant', type=int, default=None,
                        help='租户/水库ID（覆盖 SRM_TENANT_ID 环境变量，默认18=三岔）')

    args = parser.parse_args()

    # --tenant 覆盖环境变量，所有 resolve_tenant() 运行时统一读取
    if args.tenant is not None:
        os.environ['SRM_TENANT_ID'] = str(args.tenant)

    # 参数校验：需要 --flood-id 的查询类型
    flood_id_types = ['flood_detail', 'flood_result', 'flood_result_curve',
                      'flood_inflow', 'flood_statistics']
    if args.type in flood_id_types and args.flood_id is None:
        print(json.dumps({'error': f'查询类型 {args.type} 需要 --flood-id 参数'},
                         ensure_ascii=False))
        sys.exit(1)

    # 参数校验：需要 --rainfall 的查询类型
    if args.type == 'similar_floods' and args.rainfall is None:
        print(json.dumps({'error': '查询类型 similar_floods 需要 --rainfall 参数'},
                         ensure_ascii=False))
        sys.exit(1)

    # 执行查询
    query_map = {
        'current_water_level': lambda: query_current_water_level(),
        'flood_limit': lambda: query_flood_limit(),
        'config': lambda: query_config(),
        'water_level_curve': lambda: query_water_level_curve(),
        'discharge_curve': lambda: query_discharge_curve(),
        'historical_floods': lambda: query_historical_floods(args.limit),
        'flood_detail': lambda: query_flood_detail(args.flood_id),
        'flood_result': lambda: query_flood_result(args.flood_id),
        'flood_result_curve': lambda: query_flood_result_curve(args.flood_id),
        'flood_inflow': lambda: query_flood_inflow(args.flood_id),
        'flood_statistics': lambda: query_flood_statistics(args.flood_id),
        'similar_floods': lambda: query_similar_floods(args.rainfall, args.tolerance, args.limit),
        'scenarios': lambda: query_scenarios(),
        'recent_rainfall': lambda: query_recent_rainfall(args.hours),
        'full_context': lambda: query_full_context(args.hours),
    }

    try:
        result = query_map[args.type]()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
