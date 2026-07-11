#!/usr/bin/env python3
"""
预演测试数据生成脚本
功能：
1. 为现有洪水（有降雨数据但无结果）运行预演并写入结果
2. 新增多样化洪水场景
3. 补充降雨实况数据
"""

import json
import pymysql
import requests
from datetime import datetime, timedelta

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '123456aA.',
    'database': 'powerelf_srm_yml',
    'charset': 'utf8mb4'
}

XAJ_URL = "http://localhost:18081"
DISPATCH_URL = "http://localhost:18082"
ROUTING_URL = "http://localhost:18083"


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def run_simulation(rainfall, initial_wl, max_wl=462.88, min_wl=455.0,
                   scheduling_target='0', scheduling_model='0',
                   safe_cap=95.1, max_cap=191):
    """运行完整预演流程"""
    # XAJ
    xaj_resp = requests.post(f'{XAJ_URL}/api/xaj/forecast',
                             json={'rainfall': rainfall}, timeout=30)
    xaj_data = xaj_resp.json()
    inflow = xaj_data.get('flow', [])
    if not inflow:
        return None, "XAJ 返回空"

    # Dispatch
    dispatch_resp = requests.post(f'{DISPATCH_URL}/api/dispatch/optimize', json={
        'inflow': inflow,
        'initial_water_level': initial_wl,
        'max_water_level': max_wl,
        'min_water_level': min_wl,
        'max_drainage_capacity': max_cap,
        'safe_drainage_capacity': safe_cap,
        'target_water_level': initial_wl - 1,
        'scheduling_target': scheduling_target,
        'scheduling_model': scheduling_model,
    }, timeout=30)
    dispatch_data = dispatch_resp.json()
    outflow = dispatch_data.get('outflows', [])
    gate_openings = dispatch_data.get('gate_openings', [])
    if not outflow:
        return None, "Dispatch 返回空"

    # Routing
    routing_resp = requests.post(f'{ROUTING_URL}/api/routing/calculate', json={
        'inflow': inflow,
        'outflow': outflow,
        'initial_water_level': initial_wl,
        'max_water_level': max_wl,
        'min_water_level': min_wl,
    }, timeout=30)
    routing_data = routing_resp.json()
    water_levels = routing_data.get('water_levels', [])
    stats = routing_data.get('statistics', {})

    return {
        'inflow': inflow,
        'outflow': outflow,
        'gate_openings': gate_openings,
        'water_levels': water_levels,
        'statistics': stats,
    }, None


def insert_flood_results(conn, flood_id, result, base_time='2024-01-01 00:00:00'):
    """将预演结果写入 srm_flood_history_result"""
    with conn.cursor() as cur:
        # 先删除旧结果
        cur.execute('DELETE FROM srm_flood_history_result WHERE flood_id = %s', (flood_id,))

        inflow = result['inflow']
        outflow = result['outflow']
        water_levels = result['water_levels']
        stats = result['statistics']

        base_dt = datetime.strptime(base_time, '%Y-%m-%d %H:%M:%S')

        # type=1: 入库流量
        for i, v in enumerate(inflow):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (1, v, flood_id, tm, '入库流量', i))

        # type=2: 出库流量
        for i, v in enumerate(outflow):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (2, v, flood_id, tm, '出库流量', i))

        # type=3: 水位
        for i, v in enumerate(water_levels):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (3, v, flood_id, tm, '水库水位', i))

        # type=7: 统计指标
        stat_map = {
            'peak_inflow': '入库洪峰',
            'peak_outflow': '出库洪峰',
            'peak_shaving_rate': '削峰率',
            'max_water_level': '最高水位',
            'min_water_level': '最低水位',
            'total_inflow': '总入库水量',
            'total_outflow': '总出库水量',
            'storage_change': '调蓄量',
            'initial_water_level': '起调水位',
            'final_water_level': '末水位',
        }
        for i, (key, name) in enumerate(stat_map.items()):
            val = stats.get(key)
            if val is not None:
                cur.execute(
                    'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                    (7, val, flood_id, base_time, name, i))

    conn.commit()
    print(f'  ✅ 已写入 {len(inflow)} 条入库 + {len(outflow)} 条出库 + {len(water_levels)} 条水位 + 统计指标')


def insert_new_flood(conn, name, start_time, end_time, adjusted_wl, target_wl,
                     rainfall_data, remake='', status=2):
    """插入新洪水记录"""
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO srm_flood_history_base
            (name, start_time, end_time, adjusted_water_level, target_water_level,
             status, rainfall_data, remake, deleted, data_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 1)''',
                    (name, start_time, end_time, adjusted_wl, target_wl,
                     status, json.dumps(rainfall_data), remake))
    conn.commit()
    flood_id = cur.lastrowid
    print(f'  ✅ 新增洪水 id={flood_id}: {name}')
    return flood_id


def generate_rainfall(total_mm, hours, pattern='uniform'):
    """生成降雨序列"""
    if pattern == 'uniform':
        hourly = total_mm / hours
        return [round(hourly, 2)] * hours
    elif pattern == 'triangle':
        n = hours
        mid = n / 2.0
        weights = []
        for i in range(n):
            if i < mid:
                weights.append(i + 1)
            else:
                weights.append(n - i)
        total_weight = sum(weights)
        return [round(total_mm * w / total_weight, 2) for w in weights]
    elif pattern == 'front_peak':
        # 前峰型：前期集中降雨
        n = hours
        first_third = n // 3
        rainfall = []
        for i in range(n):
            if i < first_third:
                rainfall.append(total_mm * 2 / first_third / 3)
            else:
                rainfall.append(total_mm / (n - first_third) / 3)
        # 归一化
        current = sum(rainfall)
        if current > 0:
            rainfall = [round(r * total_mm / current, 2) for r in rainfall]
        return rainfall
    elif pattern == 'rear_peak':
        # 后峰型：后期集中降雨
        n = hours
        last_third = n * 2 // 3
        rainfall = []
        for i in range(n):
            if i >= last_third:
                rainfall.append(total_mm * 2 / (n - last_third) / 3)
            else:
                rainfall.append(total_mm / last_third / 3)
        current = sum(rainfall)
        if current > 0:
            rainfall = [round(r * total_mm / current, 2) for r in rainfall]
        return rainfall
    return [round(total_mm / hours, 2)] * hours


def main():
    conn = get_conn()

    # ========================================
    # Part 1: 为现有洪水补充结果数据
    # ========================================
    print("=" * 60)
    print("Part 1: 为现有洪水运行预演并写入结果")
    print("=" * 60)

    floods_to_simulate = [
        (17, 458.5, '0', '0'),   # 2023年7月典型暴雨, 防洪优先
        (18, 457.0, '0', '0'),   # 2022年8月长历时, 防洪优先
        (19, 459.8, '0', '0'),   # 2019年8月短时特大暴雨, 防洪优先
        (20, 456.5, '0', '0'),   # 2024年6月常规汛期, 防洪优先
        (21, 458.0, '0', '0'),   # 2021年7月复式洪水, 防洪优先
    ]

    for flood_id, initial_wl, st, sm in floods_to_simulate:
        with conn.cursor() as cur:
            cur.execute('SELECT name, rainfall_data FROM srm_flood_history_base WHERE id=%s', (flood_id,))
            row = cur.fetchone()
            if not row:
                print(f'  ⚠️ 洪水 id={flood_id} 不存在')
                continue

            # 检查是否已有结果
            cur.execute('SELECT COUNT(*) FROM srm_flood_history_result WHERE flood_id=%s', (flood_id,))
            cnt = cur.fetchone()[0]
            if cnt > 0:
                print(f'  ⏭️ 洪水 id={flood_id} ({row[0]}) 已有 {cnt} 条结果，跳过')
                continue

        name = row[0]
        rd = json.loads(row[1]) if row[1] else []
        rainfall = [item['RN'] for item in rd if isinstance(item, dict) and 'RN' in item]
        if not rainfall:
            print(f'  ⚠️ 洪水 id={flood_id} ({name}) 无降雨数据')
            continue

        print(f'  🔄 洪水 id={flood_id} ({name}): {len(rainfall)}h, 总雨量={sum(rainfall):.0f}mm')
        result, err = run_simulation(rainfall, initial_wl, scheduling_target=st, scheduling_model=sm)
        if err:
            print(f'  ❌ 失败: {err}')
            continue

        insert_flood_results(conn, flood_id, result)
        stats = result['statistics']
        print(f'     最高水位={stats.get("max_water_level"):.2f}m, 削峰率={stats.get("peak_shaving_rate"):.1f}%')

    # ========================================
    # Part 2: 新增多样化洪水场景
    # ========================================
    print("\n" + "=" * 60)
    print("Part 2: 新增多样化洪水场景")
    print("=" * 60)

    new_floods = [
        {
            'name': '2017年7月短时强降雨洪水',
            'start_time': '2017-07-15 08:00:00',
            'end_time': '2017-07-16 08:00:00',
            'adjusted_wl': 457.5,
            'target_wl': 458.0,
            'total_mm': 180,
            'hours': 24,
            'pattern': 'front_peak',
            'remake': '短时强降雨，前峰型，24h 180mm',
        },
        {
            'name': '2016年8月持续降雨洪水',
            'start_time': '2016-08-10 00:00:00',
            'end_time': '2016-08-14 00:00:00',
            'adjusted_wl': 456.0,
            'target_wl': 457.5,
            'total_mm': 320,
            'hours': 96,
            'pattern': 'uniform',
            'remake': '持续降雨，96h 320mm，长历时中等强度',
        },
        {
            'name': '2015年6月后峰型暴雨洪水',
            'start_time': '2015-06-20 12:00:00',
            'end_time': '2015-06-22 12:00:00',
            'adjusted_wl': 458.2,
            'target_wl': 459.0,
            'total_mm': 250,
            'hours': 48,
            'pattern': 'rear_peak',
            'remake': '后峰型暴雨，48h 250mm，后期集中',
        },
        {
            'name': '2014年9月低水位大洪水',
            'start_time': '2014-09-05 00:00:00',
            'end_time': '2014-09-07 00:00:00',
            'adjusted_wl': 454.0,
            'target_wl': 457.0,
            'total_mm': 350,
            'hours': 48,
            'pattern': 'triangle',
            'remake': '低水位大洪水，起调水位454m，48h 350mm',
        },
        {
            'name': '2013年7月接近汛限洪水',
            'start_time': '2013-07-25 06:00:00',
            'end_time': '2013-07-27 06:00:00',
            'adjusted_wl': 461.5,
            'target_wl': 462.0,
            'total_mm': 150,
            'hours': 48,
            'pattern': 'uniform',
            'remake': '接近汛限水位，起调461.5m，48h 150mm',
        },
        {
            'name': '2012年8月三角分布大洪水',
            'start_time': '2012-08-03 00:00:00',
            'end_time': '2012-08-05 00:00:00',
            'adjusted_wl': 457.8,
            'target_wl': 459.0,
            'total_mm': 400,
            'hours': 48,
            'pattern': 'triangle',
            'remake': '三角分布大洪水，48h 400mm',
        },
        {
            'name': '2011年7月小洪水',
            'start_time': '2011-07-10 10:00:00',
            'end_time': '2011-07-11 10:00:00',
            'adjusted_wl': 456.5,
            'target_wl': 456.8,
            'total_mm': 80,
            'hours': 24,
            'pattern': 'uniform',
            'remake': '小洪水，24h 80mm，测试低雨量场景',
        },
        {
            'name': '2010年8月极端洪水',
            'start_time': '2010-08-08 00:00:00',
            'end_time': '2010-08-10 00:00:00',
            'adjusted_wl': 459.0,
            'target_wl': 461.0,
            'total_mm': 480,
            'hours': 48,
            'pattern': 'front_peak',
            'remake': '极端洪水，48h 480mm，前峰型，接近模型上限',
        },
    ]

    for flood in new_floods:
        # 检查是否已存在
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM srm_flood_history_base WHERE name=%s', (flood['name'],))
            if cur.fetchone():
                print(f'  ⏭️ {flood["name"]} 已存在，跳过')
                continue

        rainfall = generate_rainfall(flood['total_mm'], flood['hours'], flood['pattern'])
        rainfall_data = [{'RN': round(r, 2), 'YMDH': 0} for r in rainfall]

        flood_id = insert_new_flood(
            conn, flood['name'], flood['start_time'], flood['end_time'],
            flood['adjusted_wl'], flood['target_wl'], rainfall_data, flood['remake']
        )

        # 运行预演
        print(f'  🔄 运行预演...')
        result, err = run_simulation(rainfall, flood['adjusted_wl'])
        if err:
            print(f'  ❌ 预演失败: {err}')
            continue

        insert_flood_results(conn, flood_id, result)
        stats = result['statistics']
        print(f'     最高水位={stats.get("max_water_level"):.2f}m, 削峰率={stats.get("peak_shaving_rate"):.1f}%')

    # ========================================
    # Part 3: 验证最终数据
    # ========================================
    print("\n" + "=" * 60)
    print("Part 3: 验证最终数据")
    print("=" * 60)

    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM srm_flood_history_base WHERE deleted=0 AND status=2')
        total = cur.fetchone()[0]

        cur.execute('''SELECT COUNT(DISTINCT b.id) FROM srm_flood_history_base b
                       INNER JOIN srm_flood_history_result r ON b.id = r.flood_id
                       WHERE b.deleted=0 AND b.status=2''')
        with_results = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM srm_flood_history_result')
        result_rows = cur.fetchone()[0]

        print(f'  历史洪水（status=2）: {total} 条')
        print(f'  有预演结果的洪水: {with_results} 条')
        print(f'  结果数据总行数: {result_rows} 条')

        # 列出所有洪水
        cur.execute('''SELECT b.id, b.name, b.adjusted_water_level,
                       (SELECT COUNT(*) FROM srm_flood_history_result WHERE flood_id=b.id) as result_cnt
                       FROM srm_flood_history_base b WHERE b.deleted=0 AND b.status=2
                       ORDER BY b.id''')
        rows = cur.fetchall()
        print(f'\n  洪水列表:')
        for r in rows:
            print(f'    id={r[0]}: {r[1]} | 起调={r[2]}m | 结果={r[3]}条')

    conn.close()
    print("\n✅ 数据生成完成")


if __name__ == '__main__':
    main()
