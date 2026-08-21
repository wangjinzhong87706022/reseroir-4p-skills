#!/usr/bin/env python3
"""
flood_limit.py -- 汛限水位单一实现（评审 C2 统一）。

此前 plan-generation / simulation / forecasting 三处各自实现
"今天是否在汛期、取对应汛限"，行为细节（回退链、跨年）各异；本模块是唯一权威实现。

行为契约:
    1. att_res_flse_lim 按 MMdd 区间匹配当前汛期行（tenant 过滤，全部 %s 参数化）。
       跨年汛期（如 1101→次年0331）不支持——经 reservoir profile 确认（2026-08-06）
       桃曲坡整体 0601-1031 / 三岔无汛期分段，两库汛期均在同年内；
       接入跨年汛期水库时需补区间判断。
    2. 区间未命中 → 回退"主汛期"行（若存在；防洪更保守）。
    3. 无任何汛期行 → att_res_base.fl_low_lim_lev（deleted=0）作"非汛期"参考。
    4. 都没有 → {'status': 'missing'}；禁止硬编码水库数值。
"""
from datetime import datetime

from lib.db import execute_query_list
from lib.tenant import resolve_tenant

_TODAY_MD = datetime.now().strftime('%m%d')  # 进程内固定（CLI 短生命周期）


def current_flood_limit(tenant_id=None):
    """返回归一化汛限 dict；字段与行为契约见模块 docstring。"""
    tid = resolve_tenant(tenant_id)

    rows = execute_query_list(
        "SELECT flse_lim_stag, flood_season_name, "
        "       flood_season_start, flood_season_end "
        "FROM att_res_flse_lim "
        "WHERE tenant_id = %s "
        "ORDER BY id",
        (tid,),
    )
    today = _TODAY_MD
    in_season = next(
        (r for r in rows
         if r.get('flood_season_start') and r.get('flood_season_end')
         and r['flood_season_start'] <= today <= r['flood_season_end']),
        None,
    )
    if in_season is None:
        in_season = next(
            (r for r in rows if r.get('flood_season_name') == '主汛期'), None)

    if in_season:
        return {
            'status': 'ok',
            'flse_lim_stag': in_season.get('flse_lim_stag'),
            'flood_season_name': in_season.get('flood_season_name'),
            'flood_season_start': in_season.get('flood_season_start'),
            'flood_season_end': in_season.get('flood_season_end'),
            'source': "att_res_flse_lim({})".format(in_season.get('flood_season_name')),
        }

    base = execute_query_list(
        "SELECT fl_low_lim_lev "
        "FROM att_res_base "
        "WHERE fl_low_lim_lev IS NOT NULL AND deleted = 0 AND tenant_id = %s "
        "ORDER BY id "
        "LIMIT 1",
        (tid,),
    )
    if base:
        return {
            'status': 'fallback',
            'flse_lim_stag': base[0].get('fl_low_lim_lev'),
            'flood_season_name': '非汛期',
            'flood_season_start': None,
            'flood_season_end': None,
            'source': 'att_res_base',
        }
    return {'status': 'missing'}
