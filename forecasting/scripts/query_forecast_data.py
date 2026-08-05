#!/usr/bin/env python3
"""
query_forecast_data.py -- 预报主取数脚本(Hermes Agent 入口)。

用法:
    python3 scripts/query_forecast_data.py --type full_context
    python3 scripts/query_forecast_data.py --type current_water_level --hours 48

12 个 --type:
    current_water_level      实时水位(st_rsvr_r 最新一行,master stcd 取自 model_config)
    rainfall_forecast        和风逐时降雨预报(f_rnfl_h,无 tenant)
    weather_warning          气象预警(weather_warn warn_status='1',无 tenant/无 deleted)
    flood_limit              汛限水位(att_res_flse_lim 当汛期行 → 回退 att_res_base.fl_low_lim_lev)
    model_forecast_result    模型预报结果(model_result_files ⟕ st_mx_preset_cal_r,CAST join)
    zonal_rainfall_forecast  分区降雨预报(st_pptn_re_forecast)
    water_level_curve        近 12h 水位过程线(st_rsvr_r,master stcd)
    historical_floods        历史洪水(srm_flood_history_base)
    forecast_accuracy_stats  预报精度统计(forecast_accuracy_record;空 → gated)
    multi_source_overview    多源降雨聚合(和风 + 分区 + weather_info + NMC fixture 标记)
    config                   model_config 关键键
    full_context             瘦身聚合核心 5 项(水位/降雨预报/汛限/气象预警/配置)+ _meta;重项按意图单独 --type

设计原则:
    1. master stcd 来自 config,绝不硬编码(st_rsvr_r_master/st_pptn_r_master)。
    2. 参数化用 %s 占位符,禁字符串拼接。
    3. tenant 策略:多数表 tenant_id=18;f_rnfl_h/weather_warn/weather_info 无 tenant。
    4. deleted 策略:st_*/srm_flood_history_base/att_res_base/model_config 加 deleted=0;
       model_result_files/weather_warn/att_res_flse_lim 无 deleted 列,不加。
    5. taskid JOIN:model_result_files.taskid(varbinary) ⟕ st_mx_preset_cal_r.taskid(varchar)
       必须 CAST(m.taskid AS CHAR) = s.taskid。
    6. 精度数据不足时返回 gated 结构,绝不编造数字。

DB 配置:环境变量 SRM_DB_HOST/PORT/NAME/USER/PASSWORD(见 query_utils.py / docs/db-config.md)。
"""
import argparse
import json
import os
import sys
from datetime import datetime

# 让脚本既能 `python3 scripts/query_forecast_data.py` 又能被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_utils import execute_query, execute_query_list, unpack  # noqa: E402
from lib.tenant import current_tenant_id  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)


DEFAULT_TENANT = current_tenant_id()
DEFAULT_HOURS = 48
DEFAULT_LIMIT = 1000


# ===========================================================================
# 辅助:从 model_config 读 master stcd(绝不硬编码)
# ===========================================================================
def get_master_stcd(key, tenant_id=DEFAULT_TENANT):
    """读 model_config 里指定 key(如 'st_rsvr_r_master')的 value。
    返回 str;若缺失返回 None(由 caller 决定回退行为)。
    """
    sql = (
        "SELECT value FROM model_config "
        "WHERE config_key=%s AND tenant_id=%s AND deleted=0 LIMIT 1"
    )
    rows = unpack(execute_query(sql, (key, tenant_id)))
    if rows and rows[0].get('value') is not None:
        return str(rows[0]['value'])
    return None


def _now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ===========================================================================
# 1. current_water_level —— 实时水位
#    源:st_rsvr_r;tenant=18;deleted=0;stcd 取自 config 'st_rsvr_r_master'。
# ===========================================================================
def query_current_water_level(tenant_id=DEFAULT_TENANT, **_):
    master = get_master_stcd('st_rsvr_r_master', tenant_id)
    if not master:
        return {"status": "missing_config",
                "message": "model_config 缺 st_rsvr_r_master,无法定位水库站"}
    sql = (
        "SELECT rz, inq, otq, w, tm, stcd "
        "FROM st_rsvr_r "
        "WHERE tenant_id=%s AND deleted=0 AND stcd=%s "
        "ORDER BY tm DESC LIMIT 1"
    )
    rows = unpack(execute_query(sql, (tenant_id, master)))
    if not rows:
        return {"status": "empty", "stcd": master,
                "message": f"st_rsvr_r 无 stcd={master} 的有效行"}
    row = rows[0]
    return {
        "status": "ok",
        "stcd": master,
        "rz": row.get('rz'),
        "inq": row.get('inq'),
        "otq": row.get('otq'),
        "w": row.get('w'),
        "tm": row.get('tm'),
    }


# ===========================================================================
# 2. rainfall_forecast —— 和风逐时降雨预报
#    源:f_rnfl_h;无 tenant;deleted=0;窗口 NOW() → NOW()+hours。
# ===========================================================================
def query_rainfall_forecast(hours=DEFAULT_HOURS, limit=DEFAULT_LIMIT, **_):
    sql = (
        "SELECT RN, YMDH, FYMDH, UNITNAME "
        "FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "  AND deleted=0 "
        "ORDER BY YMDH"
    )
    rows = unpack(execute_query(sql, (hours,), max_rows=limit))
    return {
        "source": "f_rnfl_h (和风天气)",
        "hours": hours,
        "count": len(rows),
        "data": rows,
    }


# ===========================================================================
# 3. weather_warning —— 气象预警
#    源:weather_warn;无 tenant_id/无 deleted;warn_status='1'。
# ===========================================================================
def query_weather_warning(**_):
    sql = (
        "SELECT docid, docabstract, chnlname, docpubtime, warn_status "
        "FROM weather_warn "
        "WHERE warn_status='1' "
        "ORDER BY docpubtime DESC LIMIT 20"
    )
    rows = unpack(execute_query(sql))
    return {
        "source": "weather_warn",
        "count": len(rows),
        "data": rows,
    }


# ===========================================================================
# 4. flood_limit —— 汛限水位(字段名+值,绝不硬编码)
#    源1:att_res_flse_lim(按当前日期落在哪段汛期,取该段 flse_lim_stag;无 deleted 列)
#    回退:att_res_base.fl_low_lim_lev(tenant=18, deleted=0)
# ===========================================================================
def _pick_in_season_flse_lim(tenant_id):
    """att_res_flse_lim 按 MMdd 选中当前汛期行;无匹配 → None。"""
    sql = (
        "SELECT flse_lim_stag, flood_season_name, "
        "       flood_season_start, flood_season_end "
        "FROM att_res_flse_lim "
        "WHERE tenant_id=%s "
        "ORDER BY id"
    )
    rows = unpack(execute_query(sql, (tenant_id,)))
    if not rows:
        return None
    today_mmdd = datetime.now().strftime('%m%d')
    in_season = None
    for r in rows:
        s, e = r.get('flood_season_start'), r.get('flood_season_end')
        if not s or not e:
            continue
        # 跨年汛期(如 1101→0331)暂不支持;三岔水库汛期均在同年内,直接区间比较。
        if s <= today_mmdd <= e:
            in_season = r
            break
    # 未命中任意区间 → 回退到主汛期(若存在)
    if not in_season:
        in_season = next(
            (r for r in rows if r.get('flood_season_name') == '主汛期'), None
        )
    return in_season


def query_flood_limit(tenant_id=DEFAULT_TENANT, **_):
    season = _pick_in_season_flse_lim(tenant_id)
    if season:
        return {
            "field": "flse_lim_stag",
            "value": season.get('flse_lim_stag'),
            "source": f"att_res_flse_lim({season.get('flood_season_name')})",
            "flood_season": season.get('flood_season_name'),
            "flood_season_start": season.get('flood_season_start'),
            "flood_season_end": season.get('flood_season_end'),
        }
    # 回退:att_res_base
    sql = (
        "SELECT fl_low_lim_lev FROM att_res_base "
        "WHERE tenant_id=%s AND deleted=0 ORDER BY update_time DESC LIMIT 1"
    )
    rows = unpack(execute_query(sql, (tenant_id,)))
    if rows and rows[0].get('fl_low_lim_lev') is not None:
        return {
            "field": "fl_low_lim_lev",
            "value": rows[0]['fl_low_lim_lev'],
            "source": "att_res_base (fallback)",
        }
    return {"status": "missing", "message": "汛限水位既无 att_res_flse_lim 也无 att_res_base 行"}


# ===========================================================================
# 5. model_forecast_result —— 模型预报结果
#    源:model_result_files(无 deleted)⟕ st_mx_preset_cal_r (CAST join);
#    type IN ('21' 流量,'22' 水位);取 create_time<=NOW() 的最新 run。
# ===========================================================================
def query_model_forecast_result(tenant_id=DEFAULT_TENANT, **_):
    sql = (
        "SELECT m.taskid, m.target_water_level, m.adjusted_water_level, "
        "       m.create_time, m.type AS file_type, "
        "       s.tm, s.type AS series_type, s.vals, s.step "
        "FROM model_result_files m "
        "JOIN st_mx_preset_cal_r s ON s.taskid = CAST(m.taskid AS CHAR) "
        "WHERE m.tenant_id=%s "
        "  AND m.create_time <= NOW() "
        "  AND m.create_time = ("
        "        SELECT MAX(create_time) FROM model_result_files "
        "        WHERE tenant_id=%s AND create_time<=NOW()) "
        "  AND s.type IN ('21','22') "
        "ORDER BY s.tm"
    )
    rows = unpack(execute_query(sql, (tenant_id, tenant_id)))
    if not rows:
        return {"status": "empty", "message": "无 create_time<=NOW() 的模型预报 run"}
    # 拆分水位/流量两条曲线
    flow_curve = [{"tm": r['tm'], "vals": r['vals']}
                  for r in rows if r.get('series_type') == '21']
    level_curve = [{"tm": r['tm'], "vals": r['vals']}
                   for r in rows if r.get('series_type') == '22']
    head = rows[0]
    return {
        "status": "ok",
        "taskid": str(head.get('taskid')),
        "create_time": head.get('create_time'),
        "target_water_level": head.get('target_water_level'),
        "adjusted_water_level": head.get('adjusted_water_level'),
        "flow_curve_count": len(flow_curve),
        "level_curve_count": len(level_curve),
        "flow_curve": flow_curve,
        "level_curve": level_curve,
    }


# ===========================================================================
# 6. zonal_rainfall_forecast —— 分区降雨预报
#    源:st_pptn_re_forecast(tenant=18,deleted=0,按 re_id 关联无 stcd);
#    窗口 NOW()-48h → NOW()+168h。
# ===========================================================================
def query_zonal_rainfall_forecast(tenant_id=DEFAULT_TENANT, limit=DEFAULT_LIMIT, **_):
    sql = (
        "SELECT drp, dyp, intv, wth, tm, re_id "
        "FROM st_pptn_re_forecast "
        "WHERE tenant_id=%s AND deleted=0 "
        "  AND tm BETWEEN NOW()-INTERVAL 48 HOUR AND NOW()+INTERVAL 168 HOUR "
        "ORDER BY tm"
    )
    rows = unpack(execute_query(sql, (tenant_id,), max_rows=limit))
    return {
        "source": "st_pptn_re_forecast",
        "count": len(rows),
        "data": rows,
    }


# ===========================================================================
# 7. water_level_curve —— 近 12h 水位过程线
#    源:st_rsvr_r;tenant=18;deleted=0;stcd 取自 config 'st_rsvr_r_master'。
# ===========================================================================
def query_water_level_curve(tenant_id=DEFAULT_TENANT, **_):
    master = get_master_stcd('st_rsvr_r_master', tenant_id)
    if not master:
        return {"status": "missing_config",
                "message": "model_config 缺 st_rsvr_r_master"}
    sql = (
        "SELECT rz, tm "
        "FROM st_rsvr_r "
        "WHERE tenant_id=%s AND deleted=0 AND stcd=%s "
        "  AND tm >= NOW()-INTERVAL 12 HOUR "
        "ORDER BY tm"
    )
    rows = unpack(execute_query(sql, (tenant_id, master)))
    return {
        "stcd": master,
        "window_hours": 12,
        "count": len(rows),
        "data": rows,
    }


# ===========================================================================
# 8. historical_floods —— 历史洪水
#    源:srm_flood_history_base;tenant=18(数据层隔离);deleted=0;最近 10 条。
# ===========================================================================
def query_historical_floods(tenant_id=DEFAULT_TENANT, **_):
    sql = (
        "SELECT id, name, start_time, end_time, target_water_level, "
        "       adjusted_water_level, rainfall_data, status, data_source "
        "FROM srm_flood_history_base "
        "WHERE tenant_id=%s AND deleted=0 "
        "ORDER BY start_time DESC LIMIT 10"
    )
    rows = unpack(execute_query(sql, (tenant_id,)))
    return {
        "source": "srm_flood_history_base",
        "count": len(rows),
        "data": rows,
    }


# ===========================================================================
# 9. forecast_accuracy_stats —— 预报精度统计(gated,绝不编造)
#    源:forecast_accuracy_record(Task 2 mock 表);空/不存在 → gated 结构。
# ===========================================================================
def query_forecast_accuracy_stats(tenant_id=DEFAULT_TENANT, **_):
    # 先确认表存在且非空
    try:
        probe = unpack(execute_query(
            "SELECT COUNT(*) AS c FROM forecast_accuracy_record WHERE tenant_id=%s",
            (tenant_id,)))
    except Exception as e:
        return {
            "status": "insufficient",
            "message": "精度数据不足/暂不可信(C1 缺陷未修)",
            "detail": f"forecast_accuracy_record 查询失败: {e}",
        }
    if not probe or not probe[0].get('c'):
        return {
            "status": "insufficient",
            "message": "精度数据不足/暂不可信(C1 缺陷未修)",
            "detail": "forecast_accuracy_record 为空",
        }

    sql = (
        "SELECT COUNT(*) AS sample_count, "
        "       ROUND(AVG(mape),3) AS avg_mape, "
        "       ROUND(MAX(mape),3) AS max_mape, "
        "       ROUND(MIN(mape),3) AS min_mape, "
        "       MAX(issued_tm) AS latest_issued, "
        "       MIN(issued_tm) AS earliest_issued "
        "FROM forecast_accuracy_record WHERE tenant_id=%s"
    )
    rows = unpack(execute_query(sql, (tenant_id,)))
    stat = rows[0] if rows else {}
    # 按来源拆分(若有 source 列)
    by_source = unpack(execute_query(
        "SELECT source, COUNT(*) AS n, ROUND(AVG(mape),3) AS avg_mape "
        "FROM forecast_accuracy_record WHERE tenant_id=%s "
        "GROUP BY source", (tenant_id,)))
    return {
        "status": "ok",
        "stats": stat,
        "by_source": by_source,
    }


# ===========================================================================
# 10. multi_source_overview —— 多源降雨聚合
#     和风 f_rnfl_h(168h) + 分区 st_pptn_re_forecast + weather_info(30d) + NMC fixture 标记
# ===========================================================================
def query_multi_source_overview(tenant_id=DEFAULT_TENANT, hours=DEFAULT_HOURS, **_):
    # 和风 168h 总量
    he = unpack(execute_query(
        "SELECT COUNT(*) AS n, ROUND(SUM(RN),2) AS total_mm, MAX(YMDH) AS latest "
        "FROM f_rnfl_h WHERE YMDH BETWEEN NOW() AND NOW()+INTERVAL 168 HOUR AND deleted=0"))
    he_row = he[0] if he else {}

    # 分区 st_pptn_re_forecast(未来 168h)
    zo = unpack(execute_query(
        "SELECT COUNT(*) AS n, ROUND(SUM(drp),2) AS total_mm, MAX(tm) AS latest "
        "FROM st_pptn_re_forecast WHERE tenant_id=%s AND deleted=0 "
        "  AND tm BETWEEN NOW() AND NOW()+INTERVAL 168 HOUR", (tenant_id,)))
    zo_row = zo[0] if zo else {}

    # weather_info 近 30d
    wi = unpack(execute_query(
        "SELECT COUNT(*) AS n, MAX(fx_date) AS latest_fx, MIN(fx_date) AS earliest_fx "
        "FROM weather_info WHERE fx_date >= CURDATE()-INTERVAL 30 DAY"))
    wi_row = wi[0] if wi else {}

    # NMC fixture 标记(文件存在性,不解析)
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'scenarios', 'nmc_rainfall_24.json')
    nmc = {
        "available": os.path.exists(fixture_path),
        "source": "NMC-MOCK" if os.path.exists(fixture_path) else "NMC(缺失)",
        "lead_hours": 24,
    }

    return {
        "hefeng_168h": he_row,
        "zonal_168h": zo_row,
        "weather_info_30d": wi_row,
        "nmc_fixture": nmc,
        "confidence": {
            "hefeng": "high" if (he_row.get('n') or 0) > 0 else "none",
            "zonal": "medium" if (zo_row.get('n') or 0) > 0 else "none",
            "nmc": "fixture" if nmc["available"] else "none",
        },
    }


# ===========================================================================
# 11. config —— model_config 关键键
# ===========================================================================
def query_config(tenant_id=DEFAULT_TENANT, **_):
    keys = ('max_water_level', 'min_water_level',
            'st_rsvr_r_master', 'st_pptn_r_master', 'Forecast_Q')
    placeholders = ','.join(['%s'] * len(keys))
    sql = (
        f"SELECT config_key, value FROM model_config "
        f"WHERE tenant_id=%s AND deleted=0 AND config_key IN ({placeholders})"
    )
    rows = unpack(execute_query(sql, (tenant_id, *keys)))
    # Python 内转 dict(同名键多行时取最后一条;tenant 18 优选已在 SQL 里保证)
    cfg = {}
    for r in rows:
        cfg[r['config_key']] = r['value']
    return {
        "source": "model_config",
        "config": cfg,
    }


# ===========================================================================
# 12. full_context —— 瘦身聚合(仅核心 5 项,降 LLM 上下文重量)
#    重项(model_forecast_result/zonal/water_level_curve/historical/accuracy/
#    multi_source)由 SKILL.md 路由按意图单独 --type 取,不再默认全打包。
# ===========================================================================
def query_full_context(tenant_id=DEFAULT_TENANT, hours=DEFAULT_HOURS, limit=DEFAULT_LIMIT):
    return {
        "current_water_level": query_current_water_level(tenant_id=tenant_id),
        "rainfall_forecast": query_rainfall_forecast(hours=hours, limit=limit),
        "flood_limit": query_flood_limit(tenant_id=tenant_id),
        "weather_warning": query_weather_warning(),
        "config": query_config(tenant_id=tenant_id),
        "_meta": {
            "as_of": _now_iso(), "tenant": tenant_id, "hours": hours,
            "note": "瘦身核心 5 项;按意图另取 --type: "
                    "model_forecast_result/water_level_curve/multi_source_overview/"
                    "forecast_accuracy_stats/historical_floods/zonal_rainfall_forecast",
        },
    }


# ===========================================================================
# 分发表 + main
# ===========================================================================
QUERY_FUNCS = {
    "current_water_level": query_current_water_level,
    "rainfall_forecast": query_rainfall_forecast,
    "weather_warning": query_weather_warning,
    "flood_limit": query_flood_limit,
    "model_forecast_result": query_model_forecast_result,
    "zonal_rainfall_forecast": query_zonal_rainfall_forecast,
    "water_level_curve": query_water_level_curve,
    "historical_floods": query_historical_floods,
    "forecast_accuracy_stats": query_forecast_accuracy_stats,
    "multi_source_overview": query_multi_source_overview,
    "config": query_config,
    "full_context": query_full_context,
}


def main():
    ap = argparse.ArgumentParser(description='预报主取数(12 个 --type)')
    ap.add_argument('--type', required=True, choices=list(QUERY_FUNCS.keys()),
                    help='查询类型')
    ap.add_argument('--hours', type=int, default=DEFAULT_HOURS,
                    help='降雨预报窗口(默认 48)')
    ap.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                    help='返回行数上限(默认 1000)')
    ap.add_argument('--source', default=None, help='(预留)预报来源过滤')
    ap.add_argument('--water-level', dest='water_level', default=None,
                    help='(预留)目标水位过滤')
    ap.add_argument('--tenant', type=int, default=DEFAULT_TENANT,
                    help='租户 ID(默认 18)')
    args = ap.parse_args()

    kwargs = {
        'hours': args.hours,
        'limit': args.limit,
        'source': args.source,
        'water_level': args.water_level,
        'tenant_id': args.tenant,
    }
    fn = QUERY_FUNCS[args.type]
    try:
        result = fn(**kwargs)
    except TypeError:
        # 该函数不接受全部 kwargs(如 query_weather_warning)——退化为只传它支持的
        result = fn()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
