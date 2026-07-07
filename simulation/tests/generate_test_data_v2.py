#!/usr/bin/env python3
"""
预演测试数据补充脚本 v2
补充缺失场景：
1. 为老洪水（id=1,11,12）补充结果数据
2. 超大洪水（500mm+）
3. 极端短时暴雨（6h）
4. 超长历时洪水（120h）
5. 超高水位起调（462m+）
6. 多峰型洪水
7. 刚好不超限 / 刚好超限的边界洪水
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
    xaj_resp = requests.post(f'{XAJ_URL}/api/xaj/forecast',
                             json={'rainfall': rainfall}, timeout=30)
    xaj_data = xaj_resp.json()
    inflow = xaj_data.get('flow', [])
    if not inflow:
        return None, "XAJ 返回空"

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
        cur.execute('DELETE FROM srm_flood_history_result WHERE flood_id = %s', (flood_id,))

        inflow = result['inflow']
        outflow = result['outflow']
        water_levels = result['water_levels']
        stats = result['statistics']
        base_dt = datetime.strptime(base_time, '%Y-%m-%d %H:%M:%S')

        for i, v in enumerate(inflow):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (1, v, flood_id, tm, '入库流量', i))

        for i, v in enumerate(outflow):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (2, v, flood_id, tm, '出库流量', i))

        for i, v in enumerate(water_levels):
            tm = (base_dt + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute(
                'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                (3, v, flood_id, tm, '水库水位', i))

        stat_map = {
            'peak_inflow': '入库洪峰', 'peak_outflow': '出库洪峰',
            'peak_shaving_rate': '削峰率', 'max_water_level': '最高水位',
            'min_water_level': '最低水位', 'total_inflow': '总入库水量',
            'total_outflow': '总出库水量', 'storage_change': '调蓄量',
            'initial_water_level': '起调水位', 'final_water_level': '末水位',
        }
        for i, (key, name) in enumerate(stat_map.items()):
            val = stats.get(key)
            if val is not None:
                cur.execute(
                    'INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted) VALUES (%s,%s,%s,%s,%s,%s,0)',
                    (7, val, flood_id, base_time, name, i))

    conn.commit()
    print(f'  ✅ 写入 {len(inflow)} 条入库 + {len(outflow)} 条出库 + {len(water_levels)} 条水位 + 统计')


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
        n = hours
        first_third = n // 3
        rainfall = []
        for i in range(n):
            if i < first_third:
                rainfall.append(total_mm * 2 / first_third / 3)
            else:
                rainfall.append(total_mm / (n - first_third) / 3)
        current = sum(rainfall)
        if current > 0:
            rainfall = [round(r * total_mm / current, 2) for r in rainfall]
        return rainfall
    elif pattern == 'rear_peak':
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
    elif pattern == 'double_peak':
        # 双峰型：两个降雨峰值
        n = hours
        rainfall = []
        for i in range(n):
            # 第一个峰在 1/4 处，第二个峰在 3/4 处
            peak1 = n // 4
            peak2 = n * 3 // 4
            dist1 = abs(i - peak1)
            dist2 = abs(i - peak2)
            weight = max(0, 1 - dist1 / (n // 4)) + max(0, 1 - dist2 / (n // 4))
            rainfall.append(weight)
        total_weight = sum(rainfall)
        if total_weight > 0:
            rainfall = [round(total_mm * w / total_weight, 2) for w in rainfall]
        return rainfall
    return [round(total_mm / hours, 2)] * hours


def main():
    conn = get_conn()

    # ========================================
    # Part 1: 为老洪水补充结果
    # ========================================
    print("=" * 60)
    print("Part 1: 为老洪水补充结果数据")
    print("=" * 60)

    old_floods = [
        (1, 458.06, '2018-07-15 00:00:00'),   # 2018年第二场次洪水
        (11, 457.96, '2020-08-12 00:00:00'),   # 2020年8月长历时洪水
        (12, 456.20, '1981-07-10 00:00:00'),   # 1981年7月洪水
    ]

    for flood_id, initial_wl, base_time in old_floods:
        with conn.cursor() as cur:
            cur.execute('SELECT name, rainfall_data FROM srm_flood_history_base WHERE id=%s', (flood_id,))
            row = cur.fetchone()
            if not row:
                continue

            cur.execute('SELECT COUNT(*) FROM srm_flood_history_result WHERE flood_id=%s', (flood_id,))
            cnt = cur.fetchone()[0]
            if cnt > 0:
                print(f'  ⏭️ id={flood_id} ({row[0]}) 已有 {cnt} 条结果，跳过')
                continue

        name = row[0]
        rd = json.loads(row[1]) if row[1] else []
        rainfall = [item.get('RN', item.get('rn', 0)) for item in rd if isinstance(item, dict)]
        if not rainfall:
            print(f'  ⚠️ id={flood_id} ({name}) 无降雨数据')
            continue

        print(f'  🔄 id={flood_id} ({name}): {len(rainfall)}h, 总雨量={sum(rainfall):.0f}mm')
        result, err = run_simulation(rainfall, initial_wl)
        if err:
            print(f'  ❌ 失败: {err}')
            continue

        insert_flood_results(conn, flood_id, result, base_time)
        stats = result['statistics']
        print(f'     最高水位={stats.get("max_water_level"):.2f}m, 削峰率={stats.get("peak_shaving_rate"):.1f}%')

    # ========================================
    # Part 2: 补充缺失场景
    # ========================================
    print("\n" + "=" * 60)
    print("Part 2: 补充缺失场景")
    print("=" * 60)

    new_floods = [
        # 超大洪水
        {
            'name': '2009年7月超大洪水',
            'start_time': '2009-07-20 00:00:00',
            'end_time': '2009-07-22 00:00:00',
            'adjusted_wl': 458.0,
            'target_wl': 461.0,
            'total_mm': 550,
            'hours': 48,
            'pattern': 'triangle',
            'remake': '超大洪水，48h 550mm，三角分布，超过常规降雨量级',
        },
        # 极端短时暴雨（6h）
        {
            'name': '2008年8月极端短时暴雨',
            'start_time': '2008-08-15 14:00:00',
            'end_time': '2008-08-15 20:00:00',
            'adjusted_wl': 459.0,
            'target_wl': 461.0,
            'total_mm': 200,
            'hours': 6,
            'pattern': 'front_peak',
            'remake': '极端短时暴雨，6h 200mm，前峰型',
        },
        # 超长历时洪水（120h）
        {
            'name': '2007年9月超长历时洪水',
            'start_time': '2007-09-01 00:00:00',
            'end_time': '2007-09-06 00:00:00',
            'adjusted_wl': 456.5,
            'target_wl': 458.5,
            'total_mm': 400,
            'hours': 120,
            'pattern': 'uniform',
            'remake': '超长历时洪水，120h 400mm，持续均匀降雨',
        },
        # 超高水位起调
        {
            'name': '2006年7月超高水位洪水',
            'start_time': '2006-07-25 00:00:00',
            'end_time': '2006-07-27 00:00:00',
            'adjusted_wl': 462.0,
            'target_wl': 462.5,
            'total_mm': 150,
            'hours': 48,
            'pattern': 'uniform',
            'remake': '超高水位起调，起调462.0m接近汛限，48h 150mm',
        },
        # 双峰型洪水
        {
            'name': '2005年8月双峰型洪水',
            'start_time': '2005-08-10 00:00:00',
            'end_time': '2005-08-13 00:00:00',
            'adjusted_wl': 457.5,
            'target_wl': 459.0,
            'total_mm': 350,
            'hours': 72,
            'pattern': 'double_peak',
            'remake': '双峰型洪水，72h 350mm，两个降雨峰值',
        },
        # 刚好不超限的边界洪水
        {
            'name': '2004年7月边界安全洪水',
            'start_time': '2004-07-18 00:00:00',
            'end_time': '2004-07-20 00:00:00',
            'adjusted_wl': 460.0,
            'target_wl': 462.5,
            'total_mm': 120,
            'hours': 48,
            'pattern': 'uniform',
            'remake': '边界安全洪水，起调460m，48h 120mm，刚好不超限',
        },
        # 低水位小洪水
        {
            'name': '2003年6月低水位小洪水',
            'start_time': '2003-06-15 00:00:00',
            'end_time': '2003-06-16 00:00:00',
            'adjusted_wl': 453.0,
            'target_wl': 454.0,
            'total_mm': 50,
            'hours': 24,
            'pattern': 'uniform',
            'remake': '低水位小洪水，起调453m（接近死水位），24h 50mm',
        },
        # 中等洪水 - 综合平衡方案
        {
            'name': '2002年8月中等洪水综合调度',
            'start_time': '2002-08-05 00:00:00',
            'end_time': '2002-08-07 00:00:00',
            'adjusted_wl': 457.0,
            'target_wl': 458.5,
            'total_mm': 200,
            'hours': 48,
            'pattern': 'triangle',
            'remake': '中等洪水，48h 200mm，综合平衡调度',
            'scheduling_target': '2',
            'scheduling_model': '2',
        },
    ]

    for flood in new_floods:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM srm_flood_history_base WHERE name=%s', (flood['name'],))
            if cur.fetchone():
                print(f'  ⏭️ {flood["name"]} 已存在，跳过')
                continue

        rainfall = generate_rainfall(flood['total_mm'], flood['hours'], flood['pattern'])
        rainfall_data = [{'RN': round(r, 2), 'YMDH': 0} for r in rainfall]

        with conn.cursor() as cur:
            cur.execute('''INSERT INTO srm_flood_history_base
                (name, start_time, end_time, adjusted_water_level, target_water_level,
                 status, rainfall_data, remake, deleted, data_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 1)''',
                        (flood['name'], flood['start_time'], flood['end_time'],
                         flood['adjusted_wl'], flood['target_wl'],
                         2, json.dumps(rainfall_data), flood['remake']))
        conn.commit()
        flood_id = cur.lastrowid
        print(f'  ✅ 新增 id={flood_id}: {flood["name"]}')

        st = flood.get('scheduling_target', '0')
        sm = flood.get('scheduling_model', '0')
        print(f'  🔄 运行预演 (target={st}, model={sm})...')
        result, err = run_simulation(rainfall, flood['adjusted_wl'],
                                     scheduling_target=st, scheduling_model=sm)
        if err:
            print(f'  ❌ 预演失败: {err}')
            continue

        insert_flood_results(conn, flood_id, result, flood['start_time'])
        stats = result['statistics']
        print(f'     最高水位={stats.get("max_water_level"):.2f}m, 削峰率={stats.get("peak_shaving_rate"):.1f}%')

    # ========================================
    # Part 3: 最终验证
    # ========================================
    print("\n" + "=" * 60)
    print("Part 3: 最终验证")
    print("=" * 60)

    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM srm_flood_history_base WHERE deleted=0 AND status=2')
        total = cur.fetchone()[0]

        cur.execute('''SELECT COUNT(DISTINCT b.id) FROM srm_flood_history_base b
                       INNER JOIN srm_flood_history_result r ON b.id=r.flood_id
                       WHERE b.deleted=0 AND b.status=2''')
        with_results = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM srm_flood_history_result')
        result_rows = cur.fetchone()[0]

        print(f'  历史洪水: {total} 条')
        print(f'  有预演结果: {with_results} 条')
        print(f'  结果数据: {result_rows} 条')

        # 覆盖范围分析
        cur.execute('''
            SELECT MIN(b.adjusted_water_level), MAX(b.adjusted_water_level)
            FROM srm_flood_history_base b WHERE b.deleted=0 AND b.status=2 AND b.adjusted_water_level IS NOT NULL
        ''')
        wl_range = cur.fetchone()
        print(f'  起调水位范围: {wl_range[0]} ~ {wl_range[1]}m')

        # 相似洪水覆盖
        print(f'\n  相似洪水搜索覆盖:')
        for target in [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550]:
            cur.execute('''SELECT rainfall_data FROM srm_flood_history_base
                           WHERE deleted=0 AND status=2 AND rainfall_data IS NOT NULL''')
            rows = cur.fetchall()
            similar = []
            for row in rows:
                rd = json.loads(row[0])
                total_rain = sum(item.get('RN', item.get('rn', 0)) for item in rd if isinstance(item, dict))
                if total_rain > 0 and abs(total_rain - target) / target <= 0.3:
                    similar.append(total_rain)
            print(f'    {target}mm±30%: {len(similar)} 条')

    conn.close()
    print("\n✅ 数据补充完成")


if __name__ == '__main__':
    main()
