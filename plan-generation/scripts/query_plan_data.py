#!/usr/bin/env python3
"""
预案数据查询脚本 - 直连数据库获取预案生成所需数据
用法: python3 query_plan_data.py --type <查询类型> [参数]
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
from lib.tenant import current_tenant_id, resolve_tenant  # 水库身份(SRM_TENANT_ID,默认18三岔)

DEFAULT_TENANT = current_tenant_id()


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

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
    return execute_query(sql, (tid,))


def query_rainfall_forecast(hours=48, source=None):
    """查询降雨预报（取最新发布的一批数据）"""
    conditions = [
        "deleted = 0",
        "ymdh >= NOW()",
        "ymdh <= DATE_ADD(NOW(), INTERVAL %s HOUR)",
        "fymdh = (SELECT MAX(fymdh) FROM f_rnfl_h WHERE ymdh >= NOW())",
    ]
    params = [hours]

    if source:
        conditions.append("unitname = %s")
        params.append(source)

    sql = (
        "SELECT ymdh, rn, pop, text, temp, wind_dir, wind_speed, unitname"
        " FROM f_rnfl_h"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY ymdh"
    )
    return execute_query(sql, params)


def query_weather_warning(since_date=None, status='1'):
    """查询活跃气象预警"""
    conditions = []
    params = []

    if status is not None:
        conditions.append("warn_status = %s")
        params.append(str(status))

    if since_date:
        conditions.append("docpubtime >= %s")
        params.append(since_date)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (
        "SELECT docid, docabstract, docpubtime, docpuburl, warn_status, update_time"
        f" FROM weather_warn{where}"
        " ORDER BY docpubtime DESC"
        " LIMIT 10"
    )
    return execute_query(sql, params)


def query_flood_limit(tenant_id=None):
    """查询当前汛限水位"""
    tid = resolve_tenant(tenant_id)
    # 优先从 att_res_flse_lim 表查询（按当前日期匹配汛期 + tenant_id 过滤）
    sql = """
    SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
    FROM att_res_flse_lim
    WHERE tenant_id = %s
      AND flood_season_start <= DATE_FORMAT(NOW(), '%m%d')
      AND flood_season_end >= DATE_FORMAT(NOW(), '%m%d')
    ORDER BY flse_lim_stag DESC
    LIMIT 1
    """
    results = execute_query_list(sql, (tid,))
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
    results2 = execute_query_list(sql2, (tid,))
    if results2:
        return results2

    # 无兜底硬编码值——汛限必须来自数据库（model_config 的 flood_limit_main/secondary
    # 或 att_res_base）。缺失时返回空，由调用方处理（禁止编造水库特定数值）。
    return []


def query_historical_plans(limit=20, start_date=None, end_date=None,
                           min_level=None, max_level=None, keyword=None,
                           tenant_id=None):
    """查询历史预案（支持多维度筛选）"""
    tid = resolve_tenant(tenant_id)
    conditions = ["type = 2", "tenant_id = %s"]
    params = [tid]

    if start_date:
        conditions.append("create_time >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("create_time <= %s")
        params.append(end_date)
    if min_level is not None:
        conditions.append("CAST(adjusted_water_level AS DECIMAL(10,2)) >= %s")
        params.append(float(min_level))
    if max_level is not None:
        conditions.append("CAST(adjusted_water_level AS DECIMAL(10,2)) <= %s")
        params.append(float(max_level))
    if keyword:
        conditions.append("alias LIKE %s")
        params.append(f"%{keyword}%")

    params.append(limit)
    sql = (
        "SELECT id, scheme_id, alias, target_water_level, adjusted_water_level,"
        " start_time, end_time, create_time, type, extend"
        " FROM model_result_files"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY create_time DESC"
        " LIMIT %s"
    )
    return execute_query(sql, params)


def query_historical_floods(limit=20, start_date=None, end_date=None,
                            status=None, keyword=None):
    """查询历史洪水（支持多维度筛选）"""
    conditions = ["deleted = 0"]
    params = []

    if start_date:
        conditions.append("create_time >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("create_time <= %s")
        params.append(end_date)
    if status is not None:
        conditions.append("status = %s")
        params.append(int(status))
    if keyword:
        conditions.append("(name LIKE %s OR remake LIKE %s)")
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")

    params.append(limit)
    sql = (
        "SELECT id, name, start_time, end_time, adjusted_water_level,"
        " target_water_level, status, rainfall_data, remake"
        " FROM srm_flood_history_base"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY create_time DESC"
        " LIMIT %s"
    )
    return execute_query(sql, params)


def query_similar_plans(water_level=None, rainfall=None,
                        time_range_days=365, limit=5, tenant_id=None):
    """查询相似条件的历史预案（按水位接近度排序）"""
    tid = resolve_tenant(tenant_id)
    conditions = ["type = 2", "tenant_id = %s"]
    params = [tid]

    # 时间范围过滤
    conditions.append("create_time >= DATE_SUB(NOW(), INTERVAL %s DAY)")
    params.append(time_range_days)

    if water_level is not None:
        params.append(float(water_level))
        params.append(limit)
        sql = (
            "SELECT id, scheme_id, alias, target_water_level,"
            " adjusted_water_level, start_time, end_time,"
            " extend, create_time"
            " FROM model_result_files"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY ABS(CAST(adjusted_water_level AS DECIMAL(10,2)) - %s)"
            " LIMIT %s"
        )
    else:
        # 无水位参数时按时间倒序
        params.append(limit)
        sql = (
            "SELECT id, scheme_id, alias, target_water_level,"
            " adjusted_water_level, start_time, end_time,"
            " extend, create_time"
            " FROM model_result_files"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY create_time DESC"
            " LIMIT %s"
        )
    return execute_query(sql, params)


def query_recent_rainfall(hours=24, station_id=None, tenant_id=None):
    """查询最近降雨实况"""
    tid = resolve_tenant(tenant_id)
    conditions = ["deleted = 0", "tenant_id = %s", "tm >= DATE_SUB(NOW(), INTERVAL %s HOUR)"]
    params = [tid, hours]

    if station_id:
        conditions.append("stcd = %s")
        params.append(station_id)

    sql = (
        "SELECT tm, p, dr"
        " FROM st_pptn_r"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY tm DESC"
    )
    return execute_query(sql, params)


def query_scenarios(target=None, def_only=False, tenant_id=None):
    """查询调度场景模板"""
    tid = resolve_tenant(tenant_id)
    conditions = ["deleted = 0", "tenant_id = %s"]
    params = [tid]

    if target:
        conditions.append("scheduling_target = %s")
        params.append(target)
    if def_only:
        conditions.append("def_flg = 1")

    sql = (
        "SELECT id, name, scheduling_target, scheduling_model, extend, def_flg"
        " FROM srm_scheduling_scenario"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY def_flg DESC, create_time DESC"
    )
    return execute_query(sql, params)


def query_water_level_curve(min_stag=None, max_stag=None, tenant_id=None):
    """查询水位-库容曲线（按 tenant 过滤，按水位取平均值消除重复点）"""
    tid = resolve_tenant(tenant_id)
    conditions = ["tenant_id = %s"]
    params = [tid]

    if min_stag is not None:
        conditions.append("stag >= %s")
        params.append(float(min_stag))
    if max_stag is not None:
        conditions.append("stag <= %s")
        params.append(float(max_stag))

    sql = (
        "SELECT stag as water_level, AVG(cap) as capacity"
        " FROM att_res_stag_cap_disc"
        f" WHERE {' AND '.join(conditions)}"
        " GROUP BY stag"
        " ORDER BY stag"
    )
    return execute_query(sql, params)


def query_discharge_curve(min_stag=None, max_stag=None, tenant_id=None):
    """查询泄流曲线（按 tenant 过滤）"""
    tid = resolve_tenant(tenant_id)
    conditions = ["tenant_id = %s"]
    params = [tid]

    if min_stag is not None:
        conditions.append("stag >= %s")
        params.append(float(min_stag))
    if max_stag is not None:
        conditions.append("stag <= %s")
        params.append(float(max_stag))

    sql = (
        "SELECT stag as water_level, q as flow"
        " FROM att_res_discharge_curve"
        f" WHERE {' AND '.join(conditions)}"
        " ORDER BY stag"
    )
    return execute_query(sql, params)


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
        # 同 key 多行时取最新（已按 id DESC 排序，首次出现即最新）
        if row['config_key'] not in config:
            config[row['config_key']] = row['value']
    return config


# ---------------------------------------------------------------------------
# Full context
# ---------------------------------------------------------------------------

def query_full_context(hours=48):
    """获取完整上下文数据。

    契约（与 simulation M4 对齐）：除原始数据外，显式汇总 max_level /
    max_discharge 两个顶层键，供 supervisor 仲裁直接读取，避免仲裁端
    脆弱回退链（P0-3：原缺这两键导致 Rule 1/2 恒短路，decision 恒 accept）。
    """
    cwl = unpack(query_current_water_level())
    scenarios = unpack(query_scenarios())
    # 峰值提取：优先 scenarios 的 max_level/max_discharge，回退 current_water_level
    max_level = None
    max_discharge = None
    for s in scenarios:
        if not isinstance(s, dict):
            continue
        lv = s.get("max_level") or s.get("highest_level")
        ds = s.get("max_discharge") or s.get("discharge")
        if lv is not None:
            lv = float(lv)
            max_level = lv if max_level is None else max(max_level, lv)
        if ds is not None:
            ds = float(ds)
            max_discharge = ds if max_discharge is None else max(max_discharge, ds)
    # 回退：从 current_water_level 数组取峰值
    if max_level is None and isinstance(cwl, list):
        rzs = [float(x["rz"]) for x in cwl if x.get("rz") is not None]
        if rzs:
            max_level = max(rzs)
    if max_discharge is None and isinstance(cwl, list):
        otqs = [float(x["otq"]) for x in cwl if x.get("otq") is not None]
        if otqs:
            max_discharge = max(otqs)
    return {
        'current_water_level': cwl,
        'rainfall_forecast': unpack(query_rainfall_forecast(hours)),
        'weather_warning': unpack(query_weather_warning()),
        'flood_limit': query_flood_limit(),       # plain list from execute_query_list
        'config': query_config(),                  # plain dict
        'historical_plans': unpack(query_historical_plans(10)),
        'historical_floods': unpack(query_historical_floods(10)),
        'scenarios': scenarios,
        'recent_rainfall': unpack(query_recent_rainfall(24)),
        'water_level_curve': unpack(query_water_level_curve()),
        'discharge_curve': unpack(query_discharge_curve()),
        # ↓↓↓ P0-3 新增：仲裁消费的显式峰值键（与 simulation M4 契约对齐）
        'max_level': max_level,
        'max_discharge': max_discharge,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='预案数据查询脚本')
    parser.add_argument('--type', required=True,
                        choices=['current_water_level', 'rainfall_forecast',
                                 'weather_warning', 'flood_limit',
                                 'historical_plans', 'historical_floods',
                                 'scenarios', 'config', 'recent_rainfall',
                                 'similar_plans', 'full_context',
                                 'water_level_curve', 'discharge_curve'],
                        help='查询类型')
    # Existing arguments
    parser.add_argument('--hours', type=int, default=48,
                        help='时间范围（小时）')
    parser.add_argument('--limit', type=int, default=5,
                        help='返回条数')
    parser.add_argument('--rainfall', type=float,
                        help='降雨量（用于相似查询）')
    parser.add_argument('--format', choices=['json', 'table'], default='json',
                        help='输出格式')
    # New filter arguments
    parser.add_argument('--start-date', type=str, default=None,
                        help='起始日期过滤 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None,
                        help='结束日期过滤 (YYYY-MM-DD)')
    parser.add_argument('--min-level', type=float, default=None,
                        help='最低水位过滤')
    parser.add_argument('--max-level', type=float, default=None,
                        help='最高水位过滤')
    parser.add_argument('--keyword', type=str, default=None,
                        help='关键词搜索')
    parser.add_argument('--status', type=int, default=None,
                        help='状态过滤')
    parser.add_argument('--water-level', type=float, default=None,
                        help='水位（用于相似预案查询）')
    parser.add_argument('--time-range-days', type=int, default=365,
                        help='时间范围天数（用于相似预案查询）')
    parser.add_argument('--source', type=str, default=None,
                        help='数据来源过滤（unitname）')
    parser.add_argument('--tenant', type=int, default=None,
                        help='租户/水库ID（覆盖 SRM_TENANT_ID 环境变量，默认18=三岔）')

    args = parser.parse_args()

    # --tenant 覆盖环境变量，所有 resolve_tenant() 运行时统一读取
    if args.tenant is not None:
        os.environ['SRM_TENANT_ID'] = str(args.tenant)

    # Map each --type to its function with the new filter args
    query_map = {
        'current_water_level': lambda: query_current_water_level(),
        'rainfall_forecast': lambda: query_rainfall_forecast(
            hours=args.hours, source=args.source),
        'weather_warning': lambda: query_weather_warning(
            since_date=args.start_date, status=str(args.status) if args.status is not None else '1'),
        'flood_limit': lambda: query_flood_limit(),
        'historical_plans': lambda: query_historical_plans(
            limit=args.limit, start_date=args.start_date, end_date=args.end_date,
            min_level=args.min_level, max_level=args.max_level,
            keyword=args.keyword),
        'historical_floods': lambda: query_historical_floods(
            limit=args.limit, start_date=args.start_date, end_date=args.end_date,
            status=args.status, keyword=args.keyword),
        'scenarios': lambda: query_scenarios(),
        'config': lambda: query_config(),
        'recent_rainfall': lambda: query_recent_rainfall(
            hours=args.hours, station_id=args.source),
        'similar_plans': lambda: query_similar_plans(
            water_level=args.water_level, rainfall=args.rainfall,
            time_range_days=args.time_range_days, limit=args.limit),
        'full_context': lambda: query_full_context(args.hours),
        'water_level_curve': lambda: query_water_level_curve(
            min_stag=args.min_level, max_stag=args.max_level),
        'discharge_curve': lambda: query_discharge_curve(
            min_stag=args.min_level, max_stag=args.max_level),
    }

    try:
        result = query_map[args.type]()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
