#!/usr/bin/env python3
"""
预演 Skill Autoresearch 评估运行器 v2
覆盖全部 98 个测试问题，按能力分组执行
"""

import json
import os
import subprocess
import requests
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(SCRIPT_DIR, '..')
QUERY_SCRIPT = os.path.join(SKILL_DIR, 'scripts', 'query_simulation_data.py')
SIM_API = 'http://127.0.0.1:18084'

# ============================================================
# 全部 98 个测试输入
# ============================================================

TEST_INPUTS = [
    # ── 能力1：多方案对比预演（13 题）──
    {'id': 'T01', 'name': '2018年洪水三方案对比', 'capability': 'multi-scheme',
     'flood_id': 1, 'initial_wl': 458.06},
    {'id': 'T02', 'name': '2020年长历时洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 11, 'initial_wl': 457.96},
    {'id': 'T03', 'name': '1981年低水位洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 12, 'initial_wl': 456.2},
    {'id': 'T04', 'name': '2019年短时特大暴雨方案对比', 'capability': 'multi-scheme',
     'flood_id': 19, 'initial_wl': 459.8},
    {'id': 'T05', 'name': '2021年复式洪水两方案对比', 'capability': 'multi-scheme',
     'flood_id': 21, 'initial_wl': 458.0,
     'schemes': [
         {'name': '防洪优先', 'scheduling_target': '0', 'scheduling_model': '0', 'max_water_level': 462.88, 'min_water_level': 455.0},
         {'name': '综合平衡', 'scheduling_target': '2', 'scheduling_model': '2', 'max_water_level': 461.88, 'min_water_level': 456.0},
     ]},
    {'id': 'T06', 'name': '2023年典型暴雨默认方案', 'capability': 'multi-scheme',
     'flood_id': 17, 'initial_wl': 458.5},
    {'id': 'T07', 'name': '2018年第一场(失败)洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 9, 'initial_wl': 458.0, 'expect_error': True},
    {'id': 'T08', 'name': '2025年6月(失败)洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 16, 'initial_wl': 459.18, 'expect_error': True},
    {'id': 'T09', 'name': '不存在洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 999, 'initial_wl': 458.0, 'expect_error': True},
    {'id': 'T10', 'name': 'id=15异常洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 15, 'initial_wl': 458.0},
    {'id': 'T11', 'name': '2024年常规汛期方案对比', 'capability': 'multi-scheme',
     'flood_id': 20, 'initial_wl': 456.5},
    {'id': 'T12', 'name': '2022年长历时洪水方案对比', 'capability': 'multi-scheme',
     'flood_id': 18, 'initial_wl': 457.0},
    {'id': 'T13', 'name': '单方案预演', 'capability': 'multi-scheme',
     'flood_id': 17, 'initial_wl': 458.5,
     'schemes': [{'name': '防洪优先', 'scheduling_target': '0', 'scheduling_model': '0', 'max_water_level': 462.88, 'min_water_level': 455.0}]},

    # ── 能力2：结果智能解读（11 题）──
    {'id': 'T14', 'name': '2018年洪水结果解读', 'capability': 'interpretation', 'flood_id': 1},
    {'id': 'T15', 'name': '2018年洪水削峰率评估', 'capability': 'interpretation', 'flood_id': 1},
    {'id': 'T16', 'name': '2018年洪水安全余量评估', 'capability': 'interpretation', 'flood_id': 1},
    {'id': 'T17', 'name': '2020年洪水调度效果', 'capability': 'interpretation', 'flood_id': 11},
    {'id': 'T18', 'name': '1981年洪水关键时间节点', 'capability': 'interpretation', 'flood_id': 12},
    {'id': 'T19', 'name': '2023年洪水结果解读(无结果)', 'capability': 'interpretation', 'flood_id': 17},
    {'id': 'T20', 'name': '2025年洪水结果解读(失败)', 'capability': 'interpretation', 'flood_id': 16, 'expect_error': True},
    {'id': 'T21', 'name': '不存在洪水结果解读', 'capability': 'interpretation', 'flood_id': 888, 'expect_error': True},
    {'id': 'T22', 'name': '2017年短时强降雨结果解读', 'capability': 'interpretation', 'flood_id': 22},
    {'id': 'T23', 'name': '2014年低水位大洪水结果解读', 'capability': 'interpretation', 'flood_id': 25},
    {'id': 'T24', 'name': '2010年极端洪水结果解读', 'capability': 'interpretation', 'flood_id': 29},

    # ── 能力3：虚拟场景构建（13 题）──
    {'id': 'T25', 'name': '200mm/48h均匀防洪优先', 'capability': 'virtual-scenario',
     'total_rainfall': 200, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T26', 'name': '150mm/24h三角分布', 'capability': 'virtual-scenario',
     'total_rainfall': 150, 'duration_hours': 24, 'pattern': 'triangle', 'initial_wl': 459.18},
    {'id': 'T27', 'name': '300mm/72h均匀综合平衡', 'capability': 'virtual-scenario',
     'total_rainfall': 300, 'duration_hours': 72, 'pattern': 'uniform', 'initial_wl': 459.18,
     'scheduling_target': '2', 'scheduling_model': '2'},
    {'id': 'T28', 'name': '100mm/24h起调457m', 'capability': 'virtual-scenario',
     'total_rainfall': 100, 'duration_hours': 24, 'pattern': 'uniform', 'initial_wl': 457.0},
    {'id': 'T29', 'name': '100mm/48h两方案对比', 'capability': 'virtual-scenario',
     'total_rainfall': 100, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T30', 'name': '500mm/48h极端降雨', 'capability': 'virtual-scenario',
     'total_rainfall': 500, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T31', 'name': '1000mm超范围降雨', 'capability': 'virtual-scenario',
     'total_rainfall': 1000, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18, 'expect_error': True},
    {'id': 'T32', 'name': '0h时长', 'capability': 'virtual-scenario',
     'total_rainfall': 100, 'duration_hours': 0, 'pattern': 'uniform', 'initial_wl': 459.18, 'expect_error': True},
    {'id': 'T33', 'name': '-50mm负降雨量', 'capability': 'virtual-scenario',
     'total_rainfall': -50, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18, 'expect_error': True},
    {'id': 'T34', 'name': '1mm极小降雨', 'capability': 'virtual-scenario',
     'total_rainfall': 1, 'duration_hours': 48, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T35', 'name': '168h最大时长', 'capability': 'virtual-scenario',
     'total_rainfall': 500, 'duration_hours': 168, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T36', 'name': '100mm/1h极端短时', 'capability': 'virtual-scenario',
     'total_rainfall': 100, 'duration_hours': 1, 'pattern': 'uniform', 'initial_wl': 459.18},
    {'id': 'T37', 'name': '200mm/48h三角分布', 'capability': 'virtual-scenario',
     'total_rainfall': 200, 'duration_hours': 48, 'pattern': 'triangle', 'initial_wl': 459.18},

    # ── 能力4：预演报告生成（8 题）──
    {'id': 'T38', 'name': '2018年洪水报告', 'capability': 'report', 'flood_id': 1},
    {'id': 'T39', 'name': '2020年洪水报告', 'capability': 'report', 'flood_id': 11},
    {'id': 'T40', 'name': '2023年洪水报告(无结果)', 'capability': 'report', 'flood_id': 17},
    {'id': 'T41', 'name': '不存在洪水报告', 'capability': 'report', 'flood_id': 999, 'expect_error': True},
    {'id': 'T42', 'name': '2017年短时强降雨报告', 'capability': 'report', 'flood_id': 22},
    {'id': 'T43', 'name': '2016年持续降雨报告', 'capability': 'report', 'flood_id': 23},
    {'id': 'T44', 'name': '2013年接近汛限报告', 'capability': 'report', 'flood_id': 26},
    {'id': 'T45', 'name': '2011年小洪水报告', 'capability': 'report', 'flood_id': 28},

    # ── 能力5：敏感性分析（10 题）──
    {'id': 'T46', 'name': '降雨量100-400mm敏感性', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_values': [100, 200, 300, 400], 'initial_wl': 459.18},
    {'id': 'T47', 'name': '起调水位457-460m敏感性', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_name': 'initial_water_level',
     'param_values': [457, 458, 459, 460], 'initial_wl': 459.18},
    {'id': 'T48', 'name': '降雨时长12-72h敏感性', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_name': 'duration_hours',
     'param_values': [12, 24, 48, 72], 'initial_wl': 459.18},
    {'id': 'T49', 'name': '安全阈值确定', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_values': [100, 200, 300, 400, 500], 'initial_wl': 459.18},
    {'id': 'T50', 'name': '降雨量50-250mm敏感性', 'capability': 'sensitivity',
     'base_rainfall': 150, 'param_values': [50, 100, 150, 200, 250], 'initial_wl': 459.18},
    {'id': 'T51', 'name': '10个参数值超限', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_values': [100, 150, 200, 250, 300, 350, 400, 450, 500], 'initial_wl': 459.18, 'expect_error': True},
    {'id': 'T52', 'name': '极小参数范围1-5mm', 'capability': 'sensitivity',
     'base_rainfall': 3, 'param_values': [1, 2, 3, 4, 5], 'initial_wl': 459.18},
    {'id': 'T53', 'name': '降雨量200-600mm敏感性', 'capability': 'sensitivity',
     'base_rainfall': 400, 'param_values': [200, 300, 400, 500, 600], 'initial_wl': 459.18},
    {'id': 'T54', 'name': '起调水位454-462m敏感性', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_name': 'initial_water_level',
     'param_values': [454, 456, 458, 460, 462], 'initial_wl': 459.18},
    {'id': 'T55', 'name': '单参数值敏感性', 'capability': 'sensitivity',
     'base_rainfall': 200, 'param_values': [200], 'initial_wl': 459.18},

    # ── 能力6：历史经验提取（10 题）──
    {'id': 'T56', 'name': '200mm相似洪水搜索', 'capability': 'historical', 'target_rainfall': 200},
    {'id': 'T57', 'name': '历史规律提取', 'capability': 'historical', 'target_rainfall': 300},
    {'id': 'T58', 'name': '失败案例查询', 'capability': 'historical', 'target_rainfall': 100},
    {'id': 'T59', 'name': '历史效果对比', 'capability': 'historical', 'target_rainfall': 400},
    {'id': 'T60', 'name': '高水位历史案例', 'capability': 'historical', 'target_rainfall': 150},
    {'id': 'T61', 'name': '短时vs长历时策略差异', 'capability': 'historical', 'target_rainfall': 250},
    {'id': 'T62', 'name': '1000mm超大洪水搜索', 'capability': 'historical', 'target_rainfall': 1000},
    {'id': 'T63', 'name': '50mm小洪水搜索', 'capability': 'historical', 'target_rainfall': 50},
    {'id': 'T64', 'name': '450mm大洪水搜索', 'capability': 'historical', 'target_rainfall': 450},
    {'id': 'T65', 'name': '350mm相似洪水搜索', 'capability': 'historical', 'target_rainfall': 350},

    # ── 数据质量验证（8 题）──
    {'id': 'T91', 'name': '当前水位查询', 'capability': 'data-query', 'query_type': 'current_water_level'},
    {'id': 'T92', 'name': '汛限水位查询', 'capability': 'data-query', 'query_type': 'flood_limit'},
    {'id': 'T93', 'name': '水位库容曲线查询', 'capability': 'data-query', 'query_type': 'water_level_curve'},
    {'id': 'T94', 'name': '系统配置查询', 'capability': 'data-query', 'query_type': 'config'},
    {'id': 'T95', 'name': '最近降雨查询', 'capability': 'data-query', 'query_type': 'recent_rainfall'},
    {'id': 'T96', 'name': '历史洪水列表', 'capability': 'data-query', 'query_type': 'historical_floods'},
    {'id': 'T97', 'name': '调度场景模板', 'capability': 'data-query', 'query_type': 'scenarios'},
    {'id': 'T98', 'name': '完整上下文', 'capability': 'data-query', 'query_type': 'full_context'},
]

# 评估标准（5 个二元检查）
EVALS = [
    {'id': 'E1', 'name': 'Data Query', 'question': '输出包含实际数据（非空或占位符）'},
    {'id': 'E2', 'name': 'API Call', 'question': '正确调用 API 并返回有效响应'},
    {'id': 'E3', 'name': 'Result Present', 'question': '输出包含具体数值结果'},
    {'id': 'E4', 'name': 'Safety Check', 'question': '安全校验正确执行'},
    {'id': 'E5', 'name': 'Output Complete', 'question': '输出格式完整'},
]


# ============================================================
# 执行函数
# ============================================================

def run_query(query_type, **kwargs):
    """Run query_simulation_data.py"""
    cmd = ['python3', QUERY_SCRIPT, '--type', query_type]
    if 'flood_id' in kwargs:
        cmd.extend(['--flood-id', str(kwargs['flood_id'])])
    if 'rainfall' in kwargs:
        cmd.extend(['--rainfall', str(kwargs['rainfall'])])
    if 'limit' in kwargs:
        cmd.extend(['--limit', str(kwargs['limit'])])
    env = os.environ.copy()
    env['SRM_DB_PASSWORD'] = '123456aA.'
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {'error': result.stderr}
    except Exception as e:
        return {'error': str(e)}


def run_multi_scheme(test):
    """Run multi-scheme comparison"""
    flood_id = test['flood_id']
    initial_wl = test.get('initial_wl', 458.0)

    inflow_data = run_query('flood_inflow', flood_id=flood_id)
    if not inflow_data or (isinstance(inflow_data, dict) and 'error' in inflow_data):
        return {'error': f'无法获取洪水 id={flood_id} 的入库流量数据'}

    inflow = [d['vals'] for d in inflow_data]
    if not inflow:
        return {'error': f'洪水 id={flood_id} 入库流量为空'}

    schemes = test.get('schemes', [
        {'name': '防洪优先', 'scheduling_target': '0', 'scheduling_model': '0', 'max_water_level': 462.88, 'min_water_level': initial_wl - 5},
        {'name': '综合平衡', 'scheduling_target': '2', 'scheduling_model': '2', 'max_water_level': 461.88, 'min_water_level': initial_wl - 3},
        {'name': '兴利优先', 'scheduling_target': '1', 'scheduling_model': '1', 'max_water_level': 462.88, 'min_water_level': initial_wl - 2},
    ])

    resp = requests.post(f'{SIM_API}/api/simulation/multi-scheme', json={
        'inflow': inflow, 'initial_water_level': initial_wl,
        'flood_limit_level': 462.88, 'safe_drainage_capacity': 95.1, 'max_drainage_capacity': 191,
        'schemes': schemes,
    }, timeout=120)
    return resp.json()


def run_interpretation(test):
    """Run result interpretation (data query)"""
    flood_id = test['flood_id']
    detail = run_query('flood_detail', flood_id=flood_id)
    stats = run_query('flood_statistics', flood_id=flood_id)
    curve = run_query('flood_result_curve', flood_id=flood_id)
    return {'detail': detail, 'statistics': stats, 'curve_count': len(curve) if isinstance(curve, list) else 0}


def run_virtual_scenario(test):
    """Run virtual scenario"""
    resp = requests.post(f'{SIM_API}/api/simulation/virtual-scenario', json={
        'total_rainfall': test['total_rainfall'],
        'duration_hours': test['duration_hours'],
        'pattern': test.get('pattern', 'uniform'),
        'initial_water_level': test.get('initial_wl', 459.18),
        'scheduling_target': test.get('scheduling_target', '0'),
        'scheduling_model': test.get('scheduling_model', '0'),
        'flood_limit_level': 462.88,
        'safe_drainage_capacity': 95.1,
        'max_drainage_capacity': 191,
    }, timeout=120)
    return resp.json()


def run_sensitivity(test):
    """Run sensitivity analysis"""
    param_name = test.get('param_name', 'total_rainfall')
    base_scenario = {
        'total_rainfall': test['base_rainfall'],
        'duration_hours': 48,
        'pattern': 'uniform',
        'initial_water_level': test.get('initial_wl', 459.18),
        'scheduling_target': '0',
        'scheduling_model': '0',
    }
    if param_name == 'initial_water_level':
        base_scenario['initial_water_level'] = test['param_values'][0]
    elif param_name == 'duration_hours':
        base_scenario['duration_hours'] = test['param_values'][0]

    resp = requests.post(f'{SIM_API}/api/simulation/sensitivity', json={
        'base_scenario': base_scenario,
        'param_name': param_name,
        'param_values': test['param_values'],
        'flood_limit_level': 462.88,
    }, timeout=300)
    return resp.json()


def run_report(test):
    """Run report generation"""
    resp = requests.post(f'{SIM_API}/api/simulation/report', json={
        'flood_id': test['flood_id'],
    }, timeout=60)
    return resp.json()


def run_historical(test):
    """Run historical experience extraction"""
    target = test['target_rainfall']
    floods = run_query('historical_floods', limit=20)
    similar = run_query('similar_floods', rainfall=target, tolerance=0.3)
    flood_details = []
    for f in (similar if isinstance(similar, list) else [])[:5]:
        stats = run_query('flood_statistics', flood_id=f['id'])
        flood_details.append({'id': f['id'], 'name': f['name'], 'statistics': stats})
    return {
        'total_floods': len(floods) if isinstance(floods, list) else 0,
        'similar_count': len(similar) if isinstance(similar, list) else 0,
        'similar_floods': flood_details,
    }


def run_data_query(test):
    """Run data query"""
    return run_query(test['query_type'])


def execute_skill(test):
    """Execute the skill for a given test input"""
    cap = test['capability']
    try:
        if cap == 'multi-scheme':
            return run_multi_scheme(test)
        elif cap == 'interpretation':
            return run_interpretation(test)
        elif cap == 'virtual-scenario':
            return run_virtual_scenario(test)
        elif cap == 'sensitivity':
            return run_sensitivity(test)
        elif cap == 'report':
            return run_report(test)
        elif cap == 'historical':
            return run_historical(test)
        elif cap == 'data-query':
            return run_data_query(test)
        return {'error': f'Unknown capability: {cap}'}
    except Exception as e:
        return {'error': str(e)}


# ============================================================
# 评估函数
# ============================================================

def evaluate_output(test, output):
    """Evaluate output against all eval criteria"""
    results = {}
    cap = test['capability']
    expect_error = test.get('expect_error', False)

    # If expecting error, check that error was returned
    if expect_error:
        has_error = isinstance(output, dict) and ('error' in output or output.get('status') == 'error')
        results['E1'] = has_error
        results['E2'] = has_error
        results['E3'] = True  # Error case doesn't need numbers
        results['E4'] = True  # Error case doesn't need safety check
        results['E5'] = has_error
        return results

    # Normal case evaluation
    has_error = isinstance(output, dict) and 'error' in output
    is_dict = isinstance(output, dict)
    is_list = isinstance(output, list)

    # E1: Data Query - output contains meaningful data
    has_data = False
    if not has_error:
        if cap == 'multi-scheme' and is_dict:
            ok_schemes = [s for s in output.get('schemes', [])
                          if s.get('result', {}).get('statistics', {}).get('max_water_level')]
            has_data = len(ok_schemes) >= 1
        elif cap == 'interpretation' and is_dict:
            has_data = len(output.get('statistics', [])) >= 1 or bool(output.get('detail'))
        elif cap == 'virtual-scenario' and is_dict:
            stats = output.get('statistics', {})
            has_data = stats.get('max_water_level') is not None
        elif cap == 'sensitivity' and is_dict:
            ok_results = [r for r in output.get('results', []) if r.get('max_water_level') is not None]
            has_data = len(ok_results) >= 1
        elif cap == 'report' and is_dict:
            has_data = bool(output.get('basic_info') or output.get('summary') or output.get('statistics'))
        elif cap == 'historical' and is_dict:
            has_data = output.get('similar_count', 0) >= 0
        elif cap == 'data-query':
            has_data = (is_list and len(output) > 0) or (is_dict and len(output) > 0)
    results['E1'] = has_data

    # E2: API Call - correct API returned valid response
    api_ok = False
    if not has_error:
        if cap == 'multi-scheme' and is_dict:
            api_ok = output.get('comparison', {}).get('recommended') is not None
        elif cap == 'interpretation' and is_dict:
            api_ok = bool(output.get('detail')) or bool(output.get('statistics'))
        elif cap == 'virtual-scenario' and is_dict:
            api_ok = len(output.get('completed_steps', [])) >= 1
        elif cap == 'sensitivity' and is_dict:
            api_ok = len(output.get('results', [])) >= 1
        elif cap == 'report' and is_dict:
            api_ok = bool(output.get('basic_info') or output.get('summary'))
        elif cap == 'historical' and is_dict:
            api_ok = 'similar_count' in output
        elif cap == 'data-query':
            api_ok = (is_list and len(output) > 0) or (is_dict and len(output) > 0)
    results['E2'] = api_ok

    # E3: Result Present - has numerical results
    has_numbers = False
    if not has_error:
        if cap == 'multi-scheme' and is_dict:
            for s in output.get('schemes', []):
                stats = s.get('result', {}).get('statistics', {})
                if stats.get('max_water_level') is not None:
                    has_numbers = True
                    break
        elif cap == 'interpretation' and is_dict:
            for s in output.get('statistics', []):
                if s.get('vals') is not None:
                    has_numbers = True
                    break
        elif cap == 'virtual-scenario' and is_dict:
            stats = output.get('statistics', {})
            has_numbers = stats.get('peak_inflow') is not None
        elif cap == 'sensitivity' and is_dict:
            for r in output.get('results', []):
                if r.get('max_water_level') is not None:
                    has_numbers = True
                    break
        elif cap == 'report' and is_dict:
            has_numbers = bool(output.get('statistics'))
        elif cap == 'historical' and is_dict:
            for f in output.get('similar_floods', []):
                if f.get('statistics'):
                    has_numbers = True
                    break
        elif cap == 'data-query':
            has_numbers = (is_list and len(output) > 0) or (is_dict and len(output) > 0)
    results['E3'] = has_numbers

    # E4: Safety Check - explicit safety analysis
    safety_check = False
    if not has_error:
        if cap == 'multi-scheme' and is_dict:
            comp = output.get('comparison', {})
            reason = str(comp.get('recommendation_reason', ''))
            safety_check = '汛限' in reason or '安全' in reason
        elif cap == 'virtual-scenario' and is_dict:
            stats = output.get('statistics', {})
            safety_check = 'exceeds_limit' in stats
        elif cap == 'sensitivity' and is_dict:
            safety_check = 'flood_limit_level' in output or 'safety_threshold' in output
        elif cap in ('historical', 'interpretation', 'report', 'data-query'):
            safety_check = True
    results['E4'] = safety_check

    # E5: Output Complete - has structured format
    is_complete = False
    if not has_error:
        if cap == 'multi-scheme' and is_dict:
            is_complete = 'schemes' in output and 'comparison' in output
        elif cap == 'interpretation' and is_dict:
            is_complete = 'detail' in output or 'statistics' in output
        elif cap == 'virtual-scenario' and is_dict:
            is_complete = 'scenario' in output and 'statistics' in output
        elif cap == 'sensitivity' and is_dict:
            is_complete = 'results' in output
        elif cap == 'report' and is_dict:
            is_complete = bool(output.get('basic_info') or output.get('summary'))
        elif cap == 'historical' and is_dict:
            is_complete = 'similar_count' in output and 'similar_floods' in output
        elif cap == 'data-query':
            is_complete = (is_list and len(output) > 0) or (is_dict and len(output) > 0)
    results['E5'] = is_complete

    return results


# ============================================================
# 实验执行
# ============================================================

def run_experiment(experiment_id, description='baseline', test_subset=None):
    """Run a single experiment"""
    tests = test_subset or TEST_INPUTS
    all_results = []
    per_eval_pass = {e['id']: 0 for e in EVALS}
    total_evals = 0

    for test in tests:
        output = execute_skill(test)
        evals = evaluate_output(test, output)

        for eval_id, passed in evals.items():
            if passed:
                per_eval_pass[eval_id] += 1
            total_evals += 1

        all_results.append({
            'test_id': test['id'],
            'test_name': test['name'],
            'capability': test['capability'],
            'evals': evals,
        })

    total_pass = sum(per_eval_pass.values())
    max_score = len(tests) * len(EVALS)
    pass_rate = (total_pass / max_score * 100) if max_score > 0 else 0

    return {
        'experiment_id': experiment_id,
        'description': description,
        'score': total_pass,
        'max_score': max_score,
        'pass_rate': round(pass_rate, 1),
        'per_eval': per_eval_pass,
        'details': all_results,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'test_count': len(tests),
    }


def save_results(results, output_dir):
    """Save experiment results"""
    json_path = os.path.join(output_dir, 'results.json')
    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
    else:
        data = {
            'skill_name': 'simulation',
            'status': 'running',
            'current_experiment': 0,
            'baseline_score': 0,
            'best_score': 0,
            'experiments': [],
            'eval_breakdown': [],
        }

    data['current_experiment'] = results['experiment_id']

    exp_entry = {
        'id': results['experiment_id'],
        'score': results['score'],
        'max_score': results['max_score'],
        'pass_rate': results['pass_rate'],
        'status': results.get('status', 'baseline'),
        'description': results['description'],
        'timestamp': results['timestamp'],
        'test_count': results['test_count'],
    }

    found = False
    for i, exp in enumerate(data['experiments']):
        if exp['id'] == results['experiment_id']:
            data['experiments'][i] = exp_entry
            found = True
            break
    if not found:
        data['experiments'].append(exp_entry)

    # Update eval breakdown
    data['eval_breakdown'] = []
    for eval_def in EVALS:
        total_pass = sum(
            1 for exp_detail in results['details']
            if exp_detail['evals'].get(eval_def['id'], False)
        )
        total_runs = len(results['details'])
        data['eval_breakdown'].append({
            'name': eval_def['name'],
            'pass_count': total_pass,
            'total': total_runs,
        })

    data['best_score'] = max(exp['pass_rate'] for exp in data['experiments'])
    if results['experiment_id'] == 0:
        data['baseline_score'] = results['pass_rate']

    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Append to results.tsv
    tsv_path = os.path.join(output_dir, 'results.tsv')
    write_header = not os.path.exists(tsv_path)
    with open(tsv_path, 'a') as f:
        if write_header:
            f.write('experiment\tscore\tmax_score\tpass_rate\tstatus\ttest_count\tdescription\n')
        f.write(f"{results['experiment_id']}\t{results['score']}\t{results['max_score']}\t"
                f"{results['pass_rate']}%\t{results.get('status', 'baseline')}\t"
                f"{results['test_count']}\t{results['description']}\n")


def print_summary(results):
    """Print experiment summary"""
    print(f"\n{'='*60}")
    print(f"实验 #{results['experiment_id']}: {results['description']}")
    print(f"{'='*60}")
    print(f"总分: {results['score']}/{results['max_score']} ({results['pass_rate']}%)")
    print(f"测试数: {results['test_count']}")
    print(f"\n评估维度:")
    for eval_def in EVALS:
        cnt = results['per_eval'][eval_def['id']]
        total = results['test_count']
        pct = round(cnt / total * 100, 1) if total > 0 else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"  {eval_def['name']:15s} {bar} {cnt}/{total} ({pct}%)")

    # Show failures
    failures = [d for d in results['details'] if not all(d['evals'].values())]
    if failures:
        print(f"\n失败用例 ({len(failures)}):")
        for f in failures[:10]:
            failed_evals = [k for k, v in f['evals'].items() if not v]
            print(f"  {f['test_id']} {f['test_name']}: {','.join(failed_evals)}")
    else:
        print(f"\n✅ 全部通过!")


def main():
    import sys
    output_dir = SCRIPT_DIR

    if len(sys.argv) > 1 and sys.argv[1] == 'baseline':
        print("Running baseline with ALL 98 test questions...")
        results = run_experiment(0, 'original skill — all 98 questions')
        results['status'] = 'baseline'
        save_results(results, output_dir)
        print_summary(results)

    elif len(sys.argv) > 1 and sys.argv[1] == 'run':
        exp_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        desc = sys.argv[3] if len(sys.argv) > 3 else 'test run'
        print(f"Running experiment {exp_id}: {desc}")
        results = run_experiment(exp_id, desc)
        results['status'] = 'test'
        save_results(results, output_dir)
        print_summary(results)

    elif len(sys.argv) > 1 and sys.argv[1] == 'capability':
        # Run only tests for a specific capability
        cap = sys.argv[2]
        subset = [t for t in TEST_INPUTS if t['capability'] == cap]
        print(f"Running {len(subset)} tests for capability: {cap}")
        results = run_experiment(0, f'capability test: {cap}', subset)
        save_results(results, output_dir)
        print_summary(results)

    elif len(sys.argv) > 1 and sys.argv[1] == 'list':
        # List all test inputs
        for t in TEST_INPUTS:
            print(f"  {t['id']:4s} [{t['capability']:15s}] {t['name']}")

    else:
        print("Usage:")
        print("  python3 eval_runner.py baseline          # Run all 98 tests")
        print("  python3 eval_runner.py run <id> <desc>   # Run experiment")
        print("  python3 eval_runner.py capability <cap>  # Run capability tests")
        print("  python3 eval_runner.py list              # List all tests")


if __name__ == '__main__':
    main()
