#!/usr/bin/env python3
"""
预演编排服务 (Simulation Orchestration Service)
功能：编排调用调度模型、演进模型，支持多方案对比、报告生成
部署：Flask API 服务，端口 18084，绑定 127.0.0.1

职责：
  1. 多方案对比：对同一洪水事件运行不同调度方案，对比分析
  2. 报告生成：从数据库查询历史洪水数据，组装报告结构
  3. 虚拟情景（Phase 2）、敏感性分析（Phase 3）、批量运行（Phase 3）
"""

import hashlib
import json
import sys
import os
import threading
import time
from datetime import datetime

import numpy as np
import requests
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Import query helpers from scripts directory
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from query_simulation_data import (
    query_flood_detail,
    query_flood_result,
    query_flood_result_curve,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# P1-8 修复：reservoir profile 常量统一（原 30+ 处硬编码三岔常量）
# 部署桃曲坡时改 SANCHA_PROFILE → TAOQUPO_PROFILE，或读 env SRM_RESERVOIR_NAME
# ---------------------------------------------------------------------------
SANCHA_PROFILE = {
    'initial_water_level': 459.18,
    'flood_limit_level': 462.88,
    'safe_drainage_capacity': 95.1,
    'max_drainage_capacity': 192,
    'wl_score_base': 455,  # wl_score = max(0, 100 - (wl - PROFILE['wl_score_base']) * 10)
}
TAOQUPO_PROFILE = {
    'initial_water_level': 785.0,
    'flood_limit_level': 786.8,
    'safe_drainage_capacity': 95.1,
    'max_drainage_capacity': 192,
    'wl_score_base': 780,
}
_RESERVOIR_NAME = os.getenv('SRM_RESERVOIR_NAME', 'sancha').lower()
PROFILE = TAOQUPO_PROFILE if _RESERVOIR_NAME == 'taoqupo' else SANCHA_PROFILE

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
XAJ_URL = "http://localhost:18081"
DISPATCH_URL = "http://localhost:18082"
ROUTING_URL = "http://localhost:18083"
MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Concurrency control
# ---------------------------------------------------------------------------
semaphore = threading.Semaphore(MAX_CONCURRENT)

# ---------------------------------------------------------------------------
# Idempotency cache
# ---------------------------------------------------------------------------
REQUEST_CACHE = {}  # {request_hash: {result, time}}
CACHE_TTL = 300     # 5 minutes


def get_request_hash(data):
    """Compute a stable hash of the request body for idempotency checks."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def check_idempotency(request_id, data):
    """
    Check whether an identical request was recently served.
    Returns the cached result dict if found, otherwise None.
    """
    cache_key = request_id or get_request_hash(data)
    entry = REQUEST_CACHE.get(cache_key)
    if entry:
        if time.time() - entry['time'] < CACHE_TTL:
            return entry['result']
        else:
            # Expired
            del REQUEST_CACHE[cache_key]
    return None


def cache_result(request_id, data, result):
    """Store a result in the idempotency cache."""
    cache_key = request_id or get_request_hash(data)
    REQUEST_CACHE[cache_key] = {
        'result': result,
        'time': time.time(),
    }
    # Evict stale entries (simple housekeeping)
    now = time.time()
    expired = [k for k, v in REQUEST_CACHE.items() if now - v['time'] > CACHE_TTL]
    for k in expired:
        del REQUEST_CACHE[k]


# ---------------------------------------------------------------------------
# Model service helpers
# ---------------------------------------------------------------------------

def call_model_service(url, data, timeout=REQUEST_TIMEOUT):
    """
    Call an upstream model service (POST JSON).
    Returns:
      {"data": <response_json>, "status": "ok"}          on success
      {"error": "...", "status": "timeout"}               on timeout
      {"error": "...", "status": "unavailable"}           on connection error
      {"error": "...", "status": "error"}                 on other errors
    """
    try:
        resp = requests.post(url, json=data, timeout=timeout)
        resp.raise_for_status()
        return {"data": resp.json(), "status": "ok"}
    except requests.exceptions.Timeout:
        return {"error": f"服务 {url} 超时", "status": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"error": f"服务 {url} 不可用", "status": "unavailable"}
    except requests.exceptions.RequestException as e:
        return {"error": f"服务 {url} 错误: {str(e)}", "status": "error"}


def check_service_health(url):
    """
    GET <url>/health and return status:
      'ok'          – 200 response
      'error'       – non-200 response or request error
      'unavailable' – connection refused / timeout
    """
    try:
        resp = requests.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            return 'ok'
        return 'error'
    except requests.exceptions.ConnectionError:
        return 'unavailable'
    except requests.exceptions.Timeout:
        return 'unavailable'
    except Exception:
        return 'error'


# ---------------------------------------------------------------------------
# Rainfall builder
# ---------------------------------------------------------------------------

def build_rainfall(total_rainfall, duration_hours, pattern="uniform"):
    """
    Build an hourly rainfall sequence.

    :param total_rainfall: Total rainfall in mm
    :param duration_hours: Number of hours
    :param pattern: 'uniform' or 'triangle'
    :return: list of hourly rainfall values (mm)
    """
    if duration_hours <= 0:
        return []

    if pattern == "uniform":
        hourly = total_rainfall / duration_hours
        return [round(hourly, 2)] * duration_hours

    elif pattern == "triangle":
        # Triangular distribution: peaks at the middle hour
        n = duration_hours
        mid = n / 2.0
        # Generate weights: linear rise then fall
        weights = []
        for i in range(n):
            if i < mid:
                weights.append(i + 1)
            else:
                weights.append(n - i)
        total_weight = sum(weights)
        rainfall_seq = [round(total_rainfall * w / total_weight, 2) for w in weights]
        return rainfall_seq

    else:
        # Default to uniform
        hourly = total_rainfall / duration_hours
        return [round(hourly, 2)] * duration_hours


# ---------------------------------------------------------------------------
# Multi-scheme comparison
# ---------------------------------------------------------------------------

def run_multi_scheme(inflow, initial_wl, flood_limit_level, schemes,
                     safe_drainage_capacity=PROFILE['safe_drainage_capacity'], max_drainage_capacity=PROFILE['max_drainage_capacity']):
    """
    Run multiple dispatch + routing scenarios and compare.

    :param inflow: inflow hydrograph (list of m3/s)
    :param initial_wl: initial water level (m)
    :param flood_limit_level: flood limit water level (m)
    :param schemes: list of scheme dicts with keys:
        name, scheduling_target, scheduling_model, max_water_level, min_water_level
    :param safe_drainage_capacity: downstream safe capacity (m3/s)
    :param max_drainage_capacity: max discharge capacity (m3/s)
    :return: dict with 'schemes' results and 'comparison' analysis
    """
    scheme_results = []

    for scheme in schemes:
        scheme_name = scheme.get('name', 'unnamed')

        # 1. Call Dispatch model
        dispatch_payload = {
            "inflow": inflow,
            "initial_water_level": initial_wl,
            "max_water_level": scheme.get('max_water_level', flood_limit_level),
            "min_water_level": scheme.get('min_water_level', initial_wl - 5),
            "max_drainage_capacity": max_drainage_capacity,
            "safe_drainage_capacity": safe_drainage_capacity,
            "target_water_level": scheme.get('target_water_level', initial_wl),
            "scheduling_target": scheme.get('scheduling_target', '0'),
            "scheduling_model": scheme.get('scheduling_model', '0'),
        }
        dispatch_result = call_model_service(
            f"{DISPATCH_URL}/api/dispatch/optimize", dispatch_payload
        )

        if dispatch_result['status'] != 'ok':
            scheme_results.append({
                "name": scheme_name,
                "error": dispatch_result.get('error', '调度模型调用失败'),
                "status": dispatch_result['status'],
            })
            continue

        dispatch_data = dispatch_result['data']

        # 2. Call Routing model with dispatch outputs
        routing_payload = {
            "inflow": inflow,
            "outflow": dispatch_data.get('outflows', []),
            "initial_water_level": initial_wl,
            "max_water_level": scheme.get('max_water_level', flood_limit_level),
            "min_water_level": scheme.get('min_water_level', initial_wl - 5),
        }
        routing_result = call_model_service(
            f"{ROUTING_URL}/api/routing/calculate", routing_payload
        )

        if routing_result['status'] != 'ok':
            scheme_results.append({
                "name": scheme_name,
                "dispatch": dispatch_data,
                "error": routing_result.get('error', '演进模型调用失败'),
                "status": routing_result['status'],
            })
            continue

        routing_data = routing_result['data']

        # Merge statistics
        dispatch_stats = dispatch_data.get('statistics', {})
        routing_stats = routing_data.get('statistics', {})

        scheme_results.append({
            "name": scheme_name,
            "params": scheme,
            "result": {
                "water_levels": routing_data.get('water_levels', []),
                "outflows": dispatch_data.get('outflows', []),
                "gate_openings": dispatch_data.get('gate_openings', []),
                "statistics": {
                    "peak_inflow": routing_stats.get('peak_inflow'),
                    "peak_outflow": routing_stats.get('peak_outflow'),
                    "peak_shaving_rate": routing_stats.get('peak_shaving_rate'),
                    "max_water_level": routing_stats.get('max_water_level'),
                    "min_water_level": routing_stats.get('min_water_level'),
                    "total_inflow": routing_stats.get('total_inflow'),
                    "total_outflow": routing_stats.get('total_outflow'),
                    "max_regulation": routing_stats.get('storage_change'),
                    "initial_water_level": routing_stats.get('initial_water_level'),
                    "final_water_level": routing_stats.get('final_water_level'),
                },
            },
            "status": "ok",
        })

    # Build comparison
    comparison = _build_comparison(scheme_results, safe_drainage_capacity, flood_limit_level)

    return {
        "schemes": scheme_results,
        "comparison": comparison,
    }


def _build_comparison(scheme_results, safe_drainage_capacity, flood_limit_level=None):
    """
    Analyse completed scheme results and produce comparison insights.
    """
    ok_schemes = [s for s in scheme_results if s.get('status') == 'ok']
    if not ok_schemes:
        return {
            "best_peak_shaving": None,
            "safest_water_level": None,
            "recommended": None,
            "recommendation_reason": "所有方案均未成功完成",
        }

    def _get_stats(s):
        return s.get('result', {}).get('statistics', s.get('statistics', {}))

    # Best peak shaving: highest peak_shaving_rate
    best_shaving = max(
        ok_schemes,
        key=lambda s: _get_stats(s).get('peak_shaving_rate', 0)
    )

    # Safest water level: lowest max_water_level
    safest_wl = min(
        ok_schemes,
        key=lambda s: _get_stats(s).get('max_water_level', 9999)
    )

    # Recommended scheme: balance between peak shaving and safety
    max_shaving = max(_get_stats(s).get('peak_shaving_rate', 0) for s in ok_schemes)
    for s in ok_schemes:
        stats = _get_stats(s)
        wl = stats.get('max_water_level', 9999)
        shaving = stats.get('peak_shaving_rate', 0)
        wl_score = max(0, 100 - (wl - PROFILE['wl_score_base']) * 10)
        s['_score'] = (shaving / max(max_shaving, 1) * 60) + (wl_score * 0.4) if max_shaving > 0 else 0

    recommended = max(ok_schemes, key=lambda s: s.get('_score', 0))
    for s in ok_schemes:
        s.pop('_score', None)

    # Build reason
    rec_stats = _get_stats(recommended)
    rec_wl = rec_stats.get('max_water_level', 0)
    rec_shaving = rec_stats.get('peak_shaving_rate', 0)
    reason_parts = [
        f"方案 [{recommended['name']}] 综合评分最高",
        f"洪峰削减率 {rec_shaving}%",
        f"最高水位 {rec_wl}m",
    ]
    # Add safety margin info if flood_limit_level is known
    if flood_limit_level and rec_wl:
        margin = flood_limit_level - rec_wl
        if margin > 0:
            reason_parts.append(f"距汛限水位 {margin:.1f}m，安全余量充足")
        else:
            reason_parts.append(f"⚠️ 超过汛限水位 {abs(margin):.1f}m")

    return {
        "best_peak_shaving": best_shaving['name'],
        "safest_water_level": safest_wl['name'],
        "recommended": recommended['name'],
        "recommendation_reason": "；".join(reason_parts),
    }


# ---------------------------------------------------------------------------
# Virtual scenario
# ---------------------------------------------------------------------------

def run_virtual_scenario(total_rainfall, duration_hours, pattern, initial_wl,
                         flood_limit_level, scheduling_target, scheduling_model,
                         safe_drainage_capacity, max_drainage_capacity):
    """
    Run a virtual scenario: build rainfall -> XAJ -> Dispatch -> Routing.
    Returns full result with partial failure handling.
    """
    result = {
        "scenario": {
            "total_rainfall": total_rainfall,
            "duration_hours": duration_hours,
            "pattern": pattern,
            "initial_water_level": initial_wl,
        },
        "completed_steps": [],
        "partial": False,
    }

    # Step 1: Build rainfall
    rainfall = build_rainfall(total_rainfall, duration_hours, pattern)
    result["scenario"]["rainfall"] = rainfall

    # Step 2: XAJ — rainfall -> inflow
    xaj_result = call_model_service(
        f"{XAJ_URL}/api/xaj/forecast",
        {"rainfall": rainfall, "duration_hours": duration_hours}
    )
    if xaj_result["status"] != "ok":
        result["error"] = "XAJ模型调用失败"
        result["detail"] = xaj_result.get("error", "")
        result["partial"] = True
        return result

    # XAJ model returns "flow" key, not "inflow"
    inflow = xaj_result["data"].get("flow", xaj_result["data"].get("inflow", []))
    result["inflow"] = inflow
    result["completed_steps"].append("xaj")

    # Step 3: Dispatch — inflow -> outflow + gate openings
    dispatch_payload = {
        "inflow": inflow,
        "initial_water_level": initial_wl,
        "max_water_level": flood_limit_level,
        "min_water_level": initial_wl - 5,
        "max_drainage_capacity": max_drainage_capacity,
        "safe_drainage_capacity": safe_drainage_capacity,
        "target_water_level": initial_wl - 1,
        "scheduling_target": scheduling_target,
        "scheduling_model": scheduling_model,
    }
    dispatch_result = call_model_service(
        f"{DISPATCH_URL}/api/dispatch/optimize", dispatch_payload
    )
    if dispatch_result["status"] != "ok":
        result["error"] = "调度模型调用失败"
        result["detail"] = dispatch_result.get("error", "")
        result["partial"] = True
        return result

    dispatch_data = dispatch_result["data"]
    result["outflow"] = dispatch_data.get("outflows", [])
    result["gate_openings"] = dispatch_data.get("gate_openings", [])
    result["completed_steps"].append("dispatch")

    # Step 4: Routing — inflow + outflow -> water levels
    routing_payload = {
        "inflow": inflow,
        "outflow": result["outflow"],
        "initial_water_level": initial_wl,
        "max_water_level": flood_limit_level,
        "min_water_level": initial_wl - 5,
    }
    routing_result = call_model_service(
        f"{ROUTING_URL}/api/routing/calculate", routing_payload
    )
    if routing_result["status"] != "ok":
        result["error"] = "演算模型调用失败"
        result["detail"] = routing_result.get("error", "")
        result["partial"] = True
        return result

    routing_data = routing_result["data"]
    result["water_levels"] = routing_data.get("water_levels", [])
    result["statistics"] = routing_data.get("statistics", {})
    result["completed_steps"].append("routing")

    # Check exceeds_limit
    if result["statistics"].get("max_water_level", 0) > flood_limit_level:
        result["statistics"]["exceeds_limit"] = True
    else:
        result["statistics"]["exceeds_limit"] = False

    result["status"] = "ok"
    result["degraded"] = False
    return result


# ---------------------------------------------------------------------------
# Sensitivity analysis (Phase 3)
# ---------------------------------------------------------------------------

def run_sensitivity(base_scenario, param_name, param_values, flood_limit_level,
                    safe_drainage_capacity=PROFILE['safe_drainage_capacity'], max_drainage_capacity=PROFILE['max_drainage_capacity']):
    """
    Run sensitivity analysis: vary one parameter and observe results.

    :param base_scenario: dict with base parameters (total_rainfall, duration_hours, pattern, initial_water_level, scheduling_target, scheduling_model)
    :param param_name: parameter to vary (e.g., 'total_rainfall')
    :param param_values: list of values to test
    :param flood_limit_level: flood limit water level
    :return: dict with results, safety_threshold, trend
    """
    results = []

    for val in param_values:
        # Build scenario with varied parameter
        scenario = base_scenario.copy()
        scenario[param_name] = val

        total_rainfall = scenario.get('total_rainfall', 460)
        duration_hours = scenario.get('duration_hours', 48)
        pattern = scenario.get('pattern', 'uniform')
        initial_wl = scenario.get('initial_water_level', PROFILE['initial_water_level'])
        scheduling_target = scenario.get('scheduling_target', '0')
        scheduling_model = scenario.get('scheduling_model', '0')

        # Run virtual scenario
        result = run_virtual_scenario(
            total_rainfall=total_rainfall,
            duration_hours=duration_hours,
            pattern=pattern,
            initial_wl=initial_wl,
            flood_limit_level=flood_limit_level,
            scheduling_target=scheduling_target,
            scheduling_model=scheduling_model,
            safe_drainage_capacity=safe_drainage_capacity,
            max_drainage_capacity=max_drainage_capacity,
        )

        if result.get('status') == 'ok' and result.get('statistics'):
            stats = result['statistics']
            results.append({
                "param_value": val,
                "max_water_level": stats.get('max_water_level', 0),
                "peak_shaving_rate": stats.get('peak_shaving_rate', 0),
                "peak_inflow": stats.get('peak_inflow', 0),
                "peak_outflow": stats.get('peak_outflow', 0),
                "exceeds_limit": stats.get('exceeds_limit', False),
                "status": "ok",
            })
        else:
            results.append({
                "param_value": val,
                "error": result.get('error', '计算失败'),
                "status": result.get('status', 'error'),
            })

    # Find safety threshold: largest param_value that doesn't exceed limit
    ok_results = [r for r in results if r.get('status') == 'ok']
    safe_results = [r for r in ok_results if not r.get('exceeds_limit', True)]
    unsafe_results = [r for r in ok_results if r.get('exceeds_limit', False)]

    safety_threshold = None
    if safe_results:
        safety_threshold = max(r['param_value'] for r in safe_results)
    elif ok_results:
        safety_threshold = min(r['param_value'] for r in ok_results)

    # Trend analysis using linear regression
    trend = None
    if len(ok_results) >= 2:
        x = np.array([r['param_value'] for r in ok_results])
        y = np.array([r['max_water_level'] for r in ok_results])

        # Linear regression: y = slope * x + intercept
        if len(x) >= 2:
            coeffs = np.polyfit(x, y, 1)
            slope = coeffs[0]
            intercept = coeffs[1]

            # R-squared
            y_pred = slope * x + intercept
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            trend = {
                "method": "linear_regression",
                "slope": round(float(slope), 6),
                "intercept": round(float(intercept), 4),
                "r_squared": round(float(r_squared), 4),
                "description": f"{param_name}每变化1个单位，最高水位变化{round(slope, 4)}m",
            }

    return {
        "param_name": param_name,
        "base_value": base_scenario.get(param_name),
        "results": results,
        "flood_limit_level": flood_limit_level,
        "safety_threshold": safety_threshold,
        "safety_threshold_unit": _get_param_unit(param_name),
        "trend": trend,
    }


def _get_param_unit(param_name):
    """Get unit for parameter name."""
    units = {
        'total_rainfall': 'mm',
        'duration_hours': 'h',
        'initial_water_level': 'm',
    }
    return units.get(param_name, '')


# ---------------------------------------------------------------------------
# Batch run (Phase 3)
# ---------------------------------------------------------------------------

def run_batch_run(scenarios, flood_limit_level,
                  safe_drainage_capacity=PROFILE['safe_drainage_capacity'], max_drainage_capacity=PROFILE['max_drainage_capacity']):
    """
    Run multiple virtual scenarios in batch.

    :param scenarios: list of scenario dicts, each with same params as virtual-scenario API
    :param flood_limit_level: flood limit water level
    :return: list of results
    """
    results = []

    for i, scenario in enumerate(scenarios):
        total_rainfall = scenario.get('total_rainfall', 100)
        duration_hours = scenario.get('duration_hours', 48)
        pattern = scenario.get('pattern', 'uniform')
        initial_wl = scenario.get('initial_water_level', PROFILE['initial_water_level'])
        scheduling_target = scenario.get('scheduling_target', '0')
        scheduling_model = scenario.get('scheduling_model', '0')

        result = run_virtual_scenario(
            total_rainfall=total_rainfall,
            duration_hours=duration_hours,
            pattern=pattern,
            initial_wl=initial_wl,
            flood_limit_level=flood_limit_level,
            scheduling_target=scheduling_target,
            scheduling_model=scheduling_model,
            safe_drainage_capacity=safe_drainage_capacity,
            max_drainage_capacity=max_drainage_capacity,
        )

        result['scenario_index'] = i
        result['scenario_name'] = scenario.get('name', f'Scenario {i+1}')
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(flood_id, flood_detail, flood_result, flood_result_curve):
    """
    Assemble a report data structure from DB query results.

    :param flood_id: int
    :param flood_detail: list of detail rows (from query_flood_detail)
    :param flood_result: list of result summary rows (from query_flood_result)
    :param flood_result_curve: list of curve rows (from query_flood_result_curve)
    :return: dict – report data structure
    """
    detail = flood_detail[0] if flood_detail else {}

    # Parse result summary (type=7 rows)
    statistics = {}
    for row in (flood_result or []):
        key = row.get('type_name', '')
        val = row.get('vals', '')
        try:
            val = float(val)
        except (ValueError, TypeError):
            pass
        statistics[key] = val

    # Parse curves
    inflow_curve = []
    outflow_curve = []
    water_level_curve = []
    gate_curve = []
    for row in (flood_result_curve or []):
        curve_type = row.get('type')
        tm = row.get('tm', '')
        try:
            val = float(row.get('vals', 0))
        except (ValueError, TypeError):
            val = 0
        point = {"time": str(tm), "value": val}
        if curve_type == 1:
            inflow_curve.append(point)
        elif curve_type == 2:
            outflow_curve.append(point)
        elif curve_type == 3:
            water_level_curve.append(point)
        elif curve_type == 6:
            gate_curve.append(point)

    return {
        "flood_id": flood_id,
        "basic_info": {
            "name": detail.get('name', ''),
            "start_time": detail.get('start_time', ''),
            "end_time": detail.get('end_time', ''),
            "adjusted_water_level": detail.get('adjusted_water_level'),
            "target_water_level": detail.get('target_water_level'),
            "status": detail.get('status'),
            "remake": detail.get('remake', ''),
            "rsvr_remake": detail.get('rsvr_remake', ''),
            "river_remake": detail.get('river_remake', ''),
            "pptn_remake": detail.get('pptn_remake', ''),
        },
        "statistics": statistics,
        "curves": {
            "inflow": inflow_curve,
            "outflow": outflow_curve,
            "water_level": water_level_curve,
            "gate_opening": gate_curve,
        },
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


# ===========================================================================
# API Endpoints
# ===========================================================================

@app.route('/health', methods=['GET'])
def health():
    """Service health check including dependency status."""
    xaj_status = check_service_health(XAJ_URL)
    dispatch_status = check_service_health(DISPATCH_URL)
    routing_status = check_service_health(ROUTING_URL)

    overall = 'ok'
    for s in (xaj_status, dispatch_status, routing_status):
        if s != 'ok':
            overall = 'degraded'
            break

    return jsonify({
        "status": overall,
        "service": "simulation_service",
        "version": "1.0.0",
        "dependencies": {
            "xaj_model": xaj_status,
            "dispatch_model": dispatch_status,
            "routing_model": routing_status,
        },
    })


@app.route('/api/simulation/multi-scheme', methods=['POST'])
def api_multi_scheme():
    """
    Multi-scheme comparison endpoint.

    Request body:
    {
        "inflow": [50, 80, 120, ...],
        "initial_water_level": 459.18,
        "flood_limit_level": 462.88,
        "safe_drainage_capacity": 95.1,
        "max_drainage_capacity": 192,
        "request_id": "optional-idempotency-key",
        "schemes": [...]  // optional; defaults generated if omitted
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    # Idempotency check
    request_id = data.get('request_id')
    cached = check_idempotency(request_id, data)
    if cached:
        return jsonify(cached)

    # Extract parameters
    inflow = data.get('inflow', [])
    if not inflow:
        return jsonify({"error": "入库流量数据不能为空"}), 400

    initial_wl = data.get('initial_water_level', PROFILE['initial_water_level'])
    flood_limit = data.get('flood_limit_level', PROFILE['flood_limit_level'])
    safe_cap = data.get('safe_drainage_capacity', PROFILE['safe_drainage_capacity'])
    max_cap = data.get('max_drainage_capacity', PROFILE['max_drainage_capacity'])

    # Schemes: use provided or generate defaults
    schemes = data.get('schemes')
    if not schemes:
        schemes = [
            {
                "name": "防洪优先",
                "scheduling_target": "0",
                "scheduling_model": "0",
                "max_water_level": flood_limit,
                "min_water_level": initial_wl - 5,
            },
            {
                "name": "综合平衡",
                "scheduling_target": "2",
                "scheduling_model": "2",
                "max_water_level": flood_limit - 1,
                "min_water_level": initial_wl - 3,
            },
            {
                "name": "兴利优先",
                "scheduling_target": "1",
                "scheduling_model": "1",
                "max_water_level": flood_limit,
                "min_water_level": initial_wl - 2,
            },
        ]

    # Concurrency control
    acquired = semaphore.acquire(timeout=60)
    if not acquired:
        return jsonify({
            "error": "系统繁忙，请稍后重试",
            "status": "busy",
        }), 429

    try:
        result = run_multi_scheme(
            inflow=inflow,
            initial_wl=initial_wl,
            flood_limit_level=flood_limit,
            schemes=schemes,
            safe_drainage_capacity=safe_cap,
            max_drainage_capacity=max_cap,
        )
        # Cache result
        cache_result(request_id, data, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"多方案对比执行失败: {str(e)}"}), 500
    finally:
        semaphore.release()


@app.route('/api/simulation/report', methods=['POST'])
def api_report():
    """
    Generate a simulation report from historical flood data.

    Request body: {"flood_id": 123}
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    flood_id = data.get('flood_id')
    if not flood_id:
        return jsonify({"error": "flood_id 参数不能为空"}), 400

    try:
        flood_detail = query_flood_detail(flood_id)
        if not flood_detail:
            return jsonify({"error": f"未找到洪水记录: flood_id={flood_id}"}), 404

        flood_result = query_flood_result(flood_id)
        flood_result_curve = query_flood_result_curve(flood_id)

        report = generate_report(flood_id, flood_detail, flood_result, flood_result_curve)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": f"报告生成失败: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Phase 2 / Phase 3 stubs
# ---------------------------------------------------------------------------

@app.route('/api/simulation/virtual-scenario', methods=['POST'])
def api_virtual_scenario():
    """
    Virtual scenario simulation.

    Request body:
    {
        "total_rainfall": 460,
        "duration_hours": 48,
        "pattern": "uniform",
        "initial_water_level": 459.18,
        "scheduling_target": "0",
        "scheduling_model": "0",
        "max_water_level": 462.88,
        "safe_drainage_capacity": 95.1,
        "max_drainage_capacity": 192,
        "flood_limit_level": 462.88,
        "request_id": "req-xxx"
    }
    """
    try:
        data = request.get_json()

        # Idempotency check
        cached = check_idempotency(data.get('request_id'), data)
        if cached:
            return jsonify(cached)

        total_rainfall = data.get('total_rainfall', 100)
        duration_hours = data.get('duration_hours', 48)
        pattern = data.get('pattern', 'uniform')
        initial_wl = data.get('initial_water_level', PROFILE['initial_water_level'])
        flood_limit = data.get('flood_limit_level', data.get('max_water_level', PROFILE['flood_limit_level']))
        scheduling_target = data.get('scheduling_target', '0')
        scheduling_model = data.get('scheduling_model', '0')
        safe_cap = data.get('safe_drainage_capacity', PROFILE['safe_drainage_capacity'])
        max_cap = data.get('max_drainage_capacity', PROFILE['max_drainage_capacity'])

        # Validate rainfall range
        if total_rainfall <= 0 or total_rainfall > 500:
            return jsonify({"error": "降雨量必须在 0-500mm 范围内"}), 400
        if duration_hours <= 0 or duration_hours > 168:
            return jsonify({"error": "时长必须在 0-168h 范围内"}), 400

        # Concurrency control
        if not semaphore.acquire(timeout=60):
            return jsonify({"error": "系统繁忙，请稍后重试", "status": "busy"}), 429

        try:
            result = run_virtual_scenario(
                total_rainfall=total_rainfall,
                duration_hours=duration_hours,
                pattern=pattern,
                initial_wl=initial_wl,
                flood_limit_level=flood_limit,
                scheduling_target=scheduling_target,
                scheduling_model=scheduling_model,
                safe_drainage_capacity=safe_cap,
                max_drainage_capacity=max_cap,
            )

            cache_result(data.get('request_id'), data, result)
            return jsonify(result)
        finally:
            semaphore.release()

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/simulation/sensitivity', methods=['POST'])
def api_sensitivity():
    """
    Sensitivity analysis: vary one parameter and observe results.

    Request body:
    {
        "base_scenario": {
            "total_rainfall": 460,
            "duration_hours": 48,
            "pattern": "uniform",
            "initial_water_level": 459.18,
            "scheduling_target": "0",
            "scheduling_model": "0"
        },
        "param_name": "total_rainfall",
        "param_values": [370, 460, 550, 690],
        "flood_limit_level": 462.88,
        "safe_drainage_capacity": 95.1,
        "max_drainage_capacity": 192,
        "request_id": "req-sens-001"
    }
    """
    try:
        data = request.get_json()

        # Idempotency check
        cached = check_idempotency(data.get('request_id'), data)
        if cached:
            return jsonify(cached)

        base_scenario = data.get('base_scenario', {})
        param_name = data.get('param_name', 'total_rainfall')
        param_values = data.get('param_values', [])
        flood_limit = data.get('flood_limit_level', PROFILE['flood_limit_level'])
        safe_cap = data.get('safe_drainage_capacity', PROFILE['safe_drainage_capacity'])
        max_cap = data.get('max_drainage_capacity', PROFILE['max_drainage_capacity'])

        if not param_values:
            return jsonify({"error": "param_values 不能为空"}), 400

        if len(param_values) > 8:
            return jsonify({"error": "单次敏感性分析最多 8 个参数值"}), 400

        # Concurrency control
        if not semaphore.acquire(timeout=60):
            return jsonify({"error": "系统繁忙，请稍后重试", "status": "busy"}), 429

        try:
            result = run_sensitivity(
                base_scenario=base_scenario,
                param_name=param_name,
                param_values=param_values,
                flood_limit_level=flood_limit,
                safe_drainage_capacity=safe_cap,
                max_drainage_capacity=max_cap,
            )

            cache_result(data.get('request_id'), data, result)
            return jsonify(result)
        finally:
            semaphore.release()

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/simulation/batch-run', methods=['POST'])
def api_batch_run():
    """
    Batch run multiple virtual scenarios.

    Request body:
    {
        "scenarios": [
            {"name": "Scenario 1", "total_rainfall": 460, "duration_hours": 48, ...},
            {"name": "Scenario 2", "total_rainfall": 550, "duration_hours": 48, ...}
        ],
        "flood_limit_level": 462.88,
        "safe_drainage_capacity": 95.1,
        "max_drainage_capacity": 192,
        "request_id": "req-batch-001"
    }
    """
    try:
        data = request.get_json()

        # Idempotency check
        cached = check_idempotency(data.get('request_id'), data)
        if cached:
            return jsonify(cached)

        scenarios = data.get('scenarios', [])
        flood_limit = data.get('flood_limit_level', PROFILE['flood_limit_level'])
        safe_cap = data.get('safe_drainage_capacity', PROFILE['safe_drainage_capacity'])
        max_cap = data.get('max_drainage_capacity', PROFILE['max_drainage_capacity'])

        if not scenarios:
            return jsonify({"error": "scenarios 不能为空"}), 400

        # Concurrency control
        if not semaphore.acquire(timeout=60):
            return jsonify({"error": "系统繁忙，请稍后重试", "status": "busy"}), 429

        try:
            results = run_batch_run(
                scenarios=scenarios,
                flood_limit_level=flood_limit,
                safe_drainage_capacity=safe_cap,
                max_drainage_capacity=max_cap,
            )

            cache_result(data.get('request_id'), data, results)
            return jsonify({"results": results})
        finally:
            semaphore.release()

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===========================================================================
# Main
# ===========================================================================

if __name__ == '__main__':
    print("预演编排服务启动中...")
    print("API: http://127.0.0.1:18084/api/simulation/multi-scheme")
    print("依赖服务: XAJ(18081), Dispatch(18082), Routing(18083)")
    app.run(host='127.0.0.1', port=18084, threaded=True, debug=False)
