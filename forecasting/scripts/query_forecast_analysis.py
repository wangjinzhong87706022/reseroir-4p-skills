#!/usr/bin/env python3
"""
query_forecast_analysis.py -- 预报场景分析脚本(Hermes 场景入口)。

用法:
    python3 scripts/query_forecast_analysis.py --type fusion_detail
    python3 scripts/query_forecast_analysis.py --type accuracy_report
    python3 scripts/query_forecast_analysis.py --type similar_floods --water-level 460
    python3 scripts/query_forecast_analysis.py --type forecast_timeline --hours 48

4 个 --type(分析密集型,减少 round-trip):
    fusion_detail       多源降雨逐时对齐(和风 168h + 分区 + 30d + NMC),分歧标注
    accuracy_report     预报精度聚合(按源 MAPE + 置信分级 + gated_flag)
    similar_floods      相似洪水(按 |峰值水位 - X| 排序)
    forecast_timeline   预报 vs 实测降雨对照时间轴(f_rnfl_h ⟕ st_pptn_r)

设计原则(与 query_forecast_data.py 一致):
    1. master stcd 从 model_config 读,绝不硬编码(复用 get_master_stcd)。
    2. 参数化用 %s 占位符,禁字符串拼接。
    3. tenant 策略:st_*/srm_flood_history_base/forecast_accuracy_record = 18;
       f_rnfl_h/weather_info 无 tenant。
    4. deleted 策略:st_*/srm_flood_history_base/forecast_accuracy_record 加 deleted=0;
       f_rnfl_h 无 deleted 列(与 query_forecast_data 同源,但 103 现网有 deleted,本地 mock 无 → 不依赖)。
    5. 精度/历史数据不足时返回 gated 结构,绝不编造数字。
    6. NMC fixture 读取+解析 JSONP 外壳。

DB 配置:环境变量 SRM_DB_HOST/PORT/NAME/USER/PASSWORD(见 query_utils.py / docs/db-config.md)。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 标准导入片段（统一共享层定位）──────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 复用同目录 query_forecast_data
from lib.db import execute_query, execute_query_list, unpack  # noqa: E402
# 复用 query_forecast_data 的 master-stcd 读取器(绝不硬编码站点)
from query_forecast_data import get_master_stcd  # noqa: E402
from lib.tenant import current_tenant_id  # noqa: E402 -- 水库身份(SRM_TENANT_ID,默认18三岔)


DEFAULT_TENANT = current_tenant_id()
DEFAULT_HOURS = 48
DEFAULT_LIMIT = 1000

# similar_floods 使用的"峰值水位"列:实测数据里 srm_flood_history_base 没有显式
# peak_water_level 字段;adjusted_water_level(起调水位,即泄洪开始时刻库水位)是
# 该表中最接近"峰值水位"语义的列(样本行 458.06m,与 text 描述一致)。
PEAK_WATER_LEVEL_COL = "adjusted_water_level"


def _now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _nmc_fixture_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'scenarios', 'nmc_rainfall_24.json')


# ===========================================================================
# 1. fusion_detail —— 多源降雨逐时对齐
#    源:和风 f_rnfl_h(168h,future) + 分区 st_pptn_re_forecast + weather_info(30d)
#        + NMC fixture(JSONP,解析取等值面 max 值代表该源 RN 强度)
#    每源置信度:NMC=高 / 和风 30d=中 / 模型(分区)=高 / 168h=中。
#    分歧标注:逐小时 max-min RN > 20mm → disagreement=true。
# ===========================================================================
def _parse_nmc_fixture():
    """读 NMC JSONP fixture,剥掉 diamond14_rainfall_24_json(...) 外壳。
    返回 dict(可能含 contours/legend/issue_time 等);缺失/解析失败 → None。
    """
    path = _nmc_fixture_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read().strip()
        m = re.match(r'^\s*\w+\((.*)\)\s*$', raw, re.DOTALL)
        payload = m.group(1) if m else raw
        return json.loads(payload)
    except Exception:
        return None


def query_fusion_detail(tenant_id=DEFAULT_TENANT, hours=DEFAULT_HOURS,
                        limit=DEFAULT_LIMIT, **_):
    # --- 源 1:和风 168h 逐时 ---
    hefeng = unpack(execute_query(
        "SELECT YMDH, RN FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "ORDER BY YMDH",
        (hours,), max_rows=limit))
    hefeng_map = {}
    for r in hefeng:
        ymdh = str(r.get('YMDH'))
        try:
            hefeng_map[ymdh] = float(r.get('RN') or 0)
        except (TypeError, ValueError):
            continue

    # --- 源 2:分区预报(st_pptn_re_forecast, re_id 聚合到小时) ---
    zonal_raw = unpack(execute_query(
        "SELECT tm, drp, re_id FROM st_pptn_re_forecast "
        "WHERE tenant_id=%s AND deleted=0 "
        "  AND tm BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "ORDER BY tm",
        (tenant_id, hours), max_rows=limit))
    # 同一小时多 re_id 取平均(分区面积加权简化为均值)
    zonal_hourly = {}
    zonal_count_by_hour = {}
    for r in zonal_raw:
        tm = str(r.get('tm'))
        try:
            v = float(r.get('drp') or 0)
        except (TypeError, ValueError):
            continue
        zonal_hourly[tm] = zonal_hourly.get(tm, 0.0) + v
        zonal_count_by_hour[tm] = zonal_count_by_hour.get(tm, 0) + 1
    zonal_map = {tm: round(zonal_hourly[tm] / n, 3)
                 for tm, n in zonal_count_by_hour.items()} if zonal_count_by_hour else {}

    # --- 源 3:weather_info 30d(按 fx_date 聚合,precip 是日总量,展平到"日"轴) ---
    weather = unpack(execute_query(
        "SELECT fx_date, precip FROM weather_info "
        "WHERE fx_date >= CURDATE() - INTERVAL 30 DAY "
        "ORDER BY fx_date"))
    weather_map = {}
    for r in weather:
        d = str(r.get('fx_date'))
        try:
            weather_map[d] = float(r.get('precip') or 0)
        except (TypeError, ValueError):
            continue

    # --- 源 4:NMC fixture(等值面最大值代表该源强度,标量) ---
    nmc = _parse_nmc_fixture()
    nmc_max_mm = None
    if nmc and isinstance(nmc.get('contours'), list):
        vals = [c.get('value') for c in nmc['contours']
                if isinstance(c.get('value'), (int, float))]
        if vals:
            nmc_max_mm = max(vals)
    nmc_issue = nmc.get('issue_time') if isinstance(nmc, dict) else None

    # --- 对齐到小时时间轴(和风 + 分区共有) ---
    all_hours = sorted(set(list(hefeng_map.keys()) + list(zonal_map.keys())))
    timeline = []
    disagreement_hours = 0
    for h in all_hours:
        he = hefeng_map.get(h)
        zo = zonal_map.get(h)
        present = [v for v in (he, zo) if v is not None]
        if len(present) >= 2 and (max(present) - min(present)) > 20:
            disagree = True
            disagreement_hours += 1
        else:
            disagree = False
        timeline.append({
            "ymdh": h,
            "hefeng_168h_mm": he,
            "zonal_model_mm": zo,
            "disagreement": disagree,
        })

    return {
        "status": "ok",
        "window_hours": hours,
        "sources": {
            "hefeng_168h": {
                "confidence": "中",
                "rows": len(hefeng),
                "note": "f_rnfl_h 逐时,无 tenant",
            },
            "zonal_model": {
                "confidence": "高",
                "rows": len(zonal_raw),
                "note": "st_pptn_re_forecast 分区,同小时多 re_id 取均值",
            },
            "weather_info_30d": {
                "confidence": "中",
                "rows": len(weather),
                "note": "和风 30d 日总量(precip)",
                "daily_mm": weather_map,
            },
            "nmc_24h": {
                "confidence": "高" if nmc_max_mm is not None else "缺失",
                "issue_time": nmc_issue,
                "max_contour_mm": nmc_max_mm,
                "note": "NMC JSONP fixture,等值面 max 值",
            },
        },
        "timeline_aligned": timeline,
        "disagreement_hours": disagreement_hours,
        "disagreement_threshold_mm": 20,
        "_meta": {"as_of": _now_iso(), "tenant": tenant_id},
    }


# ===========================================================================
# 2. accuracy_report —— 预报精度聚合
#    源:forecast_accuracy_record(Task 2 mock 表);按 source 聚合 MAPE。
#    置信分级:MAPE<15%=高 / 15-30%=中 / >30%=低。
#    gated_flag:C1 缺陷未修 → 恒 true(精度数据不足/不可全信)。
# ===========================================================================
def _classify_confidence(mape):
    if mape is None:
        return "未知"
    if mape < 15:
        return "高"
    if mape <= 30:
        return "中"
    return "低"


def query_accuracy_report(tenant_id=DEFAULT_TENANT, **_):
    # 先探测表存在且非空 → 否则 gated
    try:
        probe = unpack(execute_query(
            "SELECT COUNT(*) AS c FROM forecast_accuracy_record "
            "WHERE tenant_id=%s", (tenant_id,)))
    except Exception as e:
        return {
            "status": "insufficient",
            "gated_flag": True,
            "gated_reason": "C1 缺陷未修;forecast_accuracy_record 查询失败",
            "detail": str(e)[:200],
        }
    if not probe or not probe[0].get('c'):
        return {
            "status": "insufficient",
            "gated_flag": True,
            "gated_reason": "C1 缺陷未修;forecast_accuracy_record 为空",
            "message": "精度数据不足/暂不可信",
        }

    # 总体统计
    overall = unpack(execute_query(
        "SELECT COUNT(*) AS sample_count, "
        "       ROUND(AVG(mape),3) AS avg_mape, "
        "       ROUND(MAX(mape),3) AS max_mape, "
        "       ROUND(MIN(mape),3) AS min_mape, "
        "       MAX(issued_tm) AS latest_issued, "
        "       MIN(issued_tm) AS earliest_issued "
        "FROM forecast_accuracy_record WHERE tenant_id=%s",
        (tenant_id,)))
    overall_row = overall[0] if overall else {}

    # 按来源拆分
    by_source_rows = unpack(execute_query(
        "SELECT source, COUNT(*) AS sample_count, "
        "       ROUND(AVG(mape),3) AS avg_mape, "
        "       ROUND(MAX(mape),3) AS max_mape, "
        "       ROUND(MIN(mape),3) AS min_mape "
        "FROM forecast_accuracy_record WHERE tenant_id=%s "
        "GROUP BY source ORDER BY avg_mape",
        (tenant_id,)))
    by_source = []
    for r in by_source_rows:
        mape = r.get('avg_mape')
        by_source.append({
            "source": r.get('source'),
            "sample_count": r.get('sample_count'),
            "avg_mape": mape,
            "max_mape": r.get('max_mape'),
            "min_mape": r.get('min_mape'),
            "confidence": _classify_confidence(mape),
        })

    overall_mape = overall_row.get('avg_mape')
    return {
        "status": "ok",
        "overall": {
            "sample_count": overall_row.get('sample_count'),
            "avg_mape": overall_mape,
            "max_mape": overall_row.get('max_mape'),
            "min_mape": overall_row.get('min_mape'),
            "confidence": _classify_confidence(overall_mape),
            "latest_issued": overall_row.get('latest_issued'),
            "earliest_issued": overall_row.get('earliest_issued'),
        },
        "by_source": by_source,
        # gated_flag:C1(精度回灌链路)缺陷未修复 → 即使有数据也标记不可全信。
        "gated_flag": True,
        "gated_reason": "C1 缺陷未修(精度回灌链路待修复);数据可信但需人工复核",
        "_meta": {"as_of": _now_iso(), "tenant": tenant_id},
    }


# ===========================================================================
# 3. similar_floods —— 相似洪水(按 |峰值水位 - X| 排序)
#    源:srm_flood_history_base;峰值水位列 = adjusted_water_level(见模块常量说明)。
# ===========================================================================
def query_similar_floods(water_level=None, limit=10, tenant_id=DEFAULT_TENANT, **_):
    if water_level is None:
        return {"status": "missing_param",
                "message": "需要 --water-level X 指定参考峰值水位"}
    try:
        target = float(water_level)
    except (TypeError, ValueError):
        return {"status": "bad_param",
                "message": f"--water-level 非数值: {water_level!r}"}

    sql = (
        f"SELECT id, name, start_time, end_time, "
        f"       {PEAK_WATER_LEVEL_COL} AS peak_water_level, "
        f"       target_water_level, status, data_source, remake "
        f"FROM srm_flood_history_base "
        f"WHERE tenant_id=%s AND deleted=0 "
        f"  AND {PEAK_WATER_LEVEL_COL} IS NOT NULL "
        f"ORDER BY ABS({PEAK_WATER_LEVEL_COL} - %s) "
        f"LIMIT %s"
    )
    rows = unpack(execute_query(sql, (tenant_id, target, limit), max_rows=limit))
    for r in rows:
        peak = r.get('peak_water_level')
        if peak is not None:
            try:
                r["delta_m"] = round(float(peak) - target, 3)
            except (TypeError, ValueError):
                r["delta_m"] = None
    return {
        "status": "ok",
        "target_water_level_m": target,
        "peak_column_used": PEAK_WATER_LEVEL_COL,
        "count": len(rows),
        "data": rows,
        "_meta": {"as_of": _now_iso(), "tenant": tenant_id},
    }


# ===========================================================================
# 4. forecast_timeline —— 预报 vs 实测降雨对照时间轴
#    源:f_rnfl_h(预报 RN/YMDH)⟕ st_pptn_r(实测 drp/ymdh);按小时对齐。
#    observed 取自 st_pptn_r(stcd='46' master,从 config 读);缺失 → null。
# ===========================================================================
def query_forecast_timeline(tenant_id=DEFAULT_TENANT, hours=DEFAULT_HOURS,
                            limit=DEFAULT_LIMIT, **_):
    master = get_master_stcd('st_pptn_r_master', tenant_id)
    if not master:
        return {"status": "missing_config",
                "message": "model_config 缺 st_pptn_r_master,无法定位雨量站"}

    # 预报:f_rnfl_h,future 窗口
    fc = unpack(execute_query(
        "SELECT YMDH, RN, FYMDH FROM f_rnfl_h "
        "WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s HOUR) "
        "ORDER BY YMDH",
        (hours,), max_rows=limit))
    # 实测:st_pptn_r,master stcd,过去同长度窗口 + 覆盖 now(便于对照)
    obs = unpack(execute_query(
        "SELECT tm, dr FROM st_pptn_r "
        "WHERE tenant_id=%s AND deleted=0 AND stcd=%s "
        "  AND tm >= NOW() - INTERVAL %s HOUR "
        "ORDER BY tm",
        (tenant_id, master, hours), max_rows=limit))

    # 对齐:以小时(YYYY-MM-DD HH:00:00)为 key
    def _hour_key(s):
        if not s:
            return None
        return str(s)[:13] + ":00:00"

    fc_map = {}
    for r in fc:
        k = _hour_key(r.get('YMDH'))
        if k is None:
            continue
        try:
            fc_map[k] = float(r.get('RN') or 0)
        except (TypeError, ValueError):
            continue
    obs_map = {}
    for r in obs:
        k = _hour_key(r.get('tm'))
        if k is None:
            continue
        try:
            obs_map[k] = float(r.get('dr') or 0)
        except (TypeError, ValueError):
            continue

    all_hours = sorted(set(list(fc_map.keys()) + list(obs_map.keys())))
    timeline = []
    for h in all_hours:
        timeline.append({
            "ymdh": h,
            "forecast_mm": fc_map.get(h),       # None = 该小时无预报
            "observed_mm": obs_map.get(h),      # None = 该小时无实测
        })

    # 简单误差统计(仅对同时有预报+实测的小时)
    pairs = [(h, fc_map[h], obs_map[h]) for h in all_hours
             if h in fc_map and h in obs_map]
    bias_list = [f - o for _, f, o in pairs]
    if bias_list:
        bias = round(sum(bias_list) / len(bias_list), 3)
        mae = round(sum(abs(b) for b in bias_list) / len(bias_list), 3)
    else:
        bias = None
        mae = None

    return {
        "status": "ok",
        "stcd_observed": master,
        "window_hours": hours,
        "forecast_rows": len(fc),
        "observed_rows": len(obs),
        "aligned_hours": len(timeline),
        "overlap_hours": len(pairs),
        "bias_mm": bias,        # 预报 - 实测 均值(正=预报偏高)
        "mae_mm": mae,
        "timeline": timeline,
        "_meta": {"as_of": _now_iso(), "tenant": tenant_id},
    }


# ===========================================================================
# 分发表 + main
# ===========================================================================
QUERY_FUNCS = {
    "fusion_detail": query_fusion_detail,
    "accuracy_report": query_accuracy_report,
    "similar_floods": query_similar_floods,
    "forecast_timeline": query_forecast_timeline,
}


def main():
    ap = argparse.ArgumentParser(description='预报场景分析(4 个 --type)')
    ap.add_argument('--type', required=True, choices=list(QUERY_FUNCS.keys()),
                    help='查询类型')
    ap.add_argument('--hours', type=int, default=DEFAULT_HOURS,
                    help='时间窗口(默认 48)')
    ap.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                    help='返回行数上限(默认 1000)')
    ap.add_argument('--water-level', dest='water_level', default=None,
                    help='similar_floods 参考峰值水位(m)')
    ap.add_argument('--tenant', type=int, default=DEFAULT_TENANT,
                    help='租户 ID(默认 18)')
    args = ap.parse_args()

    kwargs = {
        'hours': args.hours,
        'limit': args.limit,
        'water_level': args.water_level,
        'tenant_id': args.tenant,
    }
    fn = QUERY_FUNCS[args.type]
    try:
        result = fn(**kwargs)
    except TypeError:
        result = fn()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
