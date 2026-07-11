#!/usr/bin/env python3
"""
数据质量检查脚本 - 用于诊断 Skill 的数据探查

用法:
    python3 check_data_quality.py --type water_level
    python3 check_data_quality.py --type rainfall_forecast
    python3 check_data_quality.py --type alerts
    python3 check_data_quality.py --type all --output problems.md

共享库: SmartTwinRes-skills/lib/db.py
标准文档: docs/db-credential-config.md (见上级目录)
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 让脚本既能 `python3 scripts/check_data_quality.py` 又能被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# 从统一共享库导入 DB 查询功能
from lib.db import execute_query_list, _require_env  # noqa: E402


def check_water_level():
    """检查水位数据质量"""
    print("=" * 70)
    print("【水位数据质量检查】")
    print("=" * 70)

    sql = """
    SELECT
        COUNT(*) as 总行数,
        SUM(CASE WHEN rz IS NULL THEN 1 ELSE 0 END) as rz为空,
        MAX(tm) as 最新时间,
        TIMESTAMPDIFF(HOUR, MAX(tm), NOW()) as 距现在小时,
        SUM(CASE WHEN deleted=0 THEN 1 ELSE 0 END) as 有效数据
    FROM st_rsvr_r
    WHERE deleted=0
    """

    result = execute_query_list(sql)[0]

    print(f"\n总行数：{result['总行数']}")
    print(f"rz 为空：{result['rz为空']} ({result['rz为空']/result['总行数']*100:.1f}%)")
    print(f"最新时间：{result['最新时间']}")
    print(f"距现在：{result['距现在小时']} 小时前")
    print(f"有效数据：{result['有效数据']}")

    # 评级
    hours_ago = result['距现在小时']
    null_rate = result['rz为空'] / result['总行数']

    if hours_ago > 24:
        print(f"\n❌ 状态：数据严重过期（{hours_ago} 小时前）")
        print("建议：立即检查数据采集 pipeline")
    elif hours_ago > 6:
        print(f"\n⚠️  状态：数据过期（{hours_ago} 小时前）")
        print("建议：检查数据采集任务")
    else:
        print(f"\n✅ 状态：数据新鲜（{hours_ago} 小时前）")

    if null_rate > 0.5:
        print(f"❌ 空值率过高（{null_rate*100:.1f}%）")
    elif null_rate > 0.1:
        print(f"⚠️  空值率偏高（{null_rate*100:.1f}%）")
    else:
        print(f"✅ 空值率正常（{null_rate*100:.1f}%）")

    # 按测站统计
    sql2 = """
    SELECT stcd, COUNT(*) as 数据量, MAX(tm) as 最新时间
    FROM st_rsvr_r
    WHERE deleted=0
    GROUP BY stcd
    ORDER BY 数据量 DESC
    LIMIT 10
    """
    stations = execute_query_list(sql2)
    print(f"\n按测站统计（前 10）：")
    for s in stations:
        print(f"  {s['stcd']}: {s['数据量']} 条, 最新 {s['最新时间']}")

    return result


def check_rainfall_forecast():
    """检查降雨预报数据质量"""
    print("\n" + "=" * 70)
    print("【降雨预报数据质量检查】")
    print("=" * 70)

    sql = """
    SELECT
        COUNT(*) as 总行数,
        MAX(ymdh) as 最新预报时间,
        TIMESTAMPDIFF(HOUR, MAX(ymdh), NOW()) as 距现在小时,
        SUM(CASE WHEN ymdh > NOW() THEN 1 ELSE 0 END) as 未来预报行数,
        MAX(fymdh) as 最新批次时间,
        TIMESTAMPDIFF(HOUR, MAX(fymdh), NOW()) as 批次距现在小时
    FROM f_rnfl_h
    WHERE deleted=0
    """

    result = execute_query_list(sql)[0]

    print(f"\n总行数：{result['总行数']}")
    print(f"最新预报时间：{result['最新预报时间']}")
    print(f"距现在：{result['距现在小时']} 小时前")
    print(f"未来预报行数：{result['未来预报行数']}")
    print(f"最新批次时间：{result['最新批次时间']}")
    print(f"批次距现在：{result['批次距现在小时']} 小时前")

    # 评级
    if result['批次距现在小时'] > 12:
        print(f"\n❌ 状态：预报严重陈旧（{result['批次距现在小时']} 小时前）")
    elif result['批次距现在小时'] > 6:
        print(f"\n⚠️  状态：预报陈旧（{result['批次距现在小时']} 小时前）")
    else:
        print(f"\n✅ 状态：预报新鲜（{result['批次距现在小时']} 小时前）")

    if result['未来预报行数'] == 0:
        print("❌ 无未来预报数据")
    else:
        print(f"✅ 有未来预报数据（{result['未来预报行数']} 行）")

    return result


def check_alerts():
    """检查告警堆积情况"""
    print("\n" + "=" * 70)
    print("【告警堆积检查】")
    print("=" * 70)

    sql = """
    SELECT
        COUNT(*) as 未确认总数,
        SUM(CASE WHEN level_r='1' THEN 1 ELSE 0 END) as 红色,
        SUM(CASE WHEN level_r='2' THEN 1 ELSE 0 END) as 橙色,
        SUM(CASE WHEN level_r='3' THEN 1 ELSE 0 END) as 黄色,
        SUM(CASE WHEN level_r='4' THEN 1 ELSE 0 END) as 蓝色,
        MIN(gather_time) as 最早时间,
        MAX(gather_time) as 最新时间,
        TIMESTAMPDIFF(HOUR, MAX(gather_time), NOW()) as 距现在小时
    FROM ew_info_message
    WHERE message_confirm=0 AND deleted=0
    """

    result = execute_query_list(sql)[0]

    print(f"\n未确认总数：{result['未确认总数']}")
    print(f"  红色（I级）：{result['红色']}")
    print(f"  橙色（II级）：{result['橙色']}")
    print(f"  黄色（III级）：{result['黄色']}")
    print(f"  蓝色（IV级）：{result['蓝色']}")
    print(f"最新时间：{result['最新时间']}")
    print(f"距现在：{result['距现在小时']} 小时前")

    # 评级
    total = result['未确认总数']
    high_priority = result['红色'] + result['橙色']

    if total > 1000:
        print(f"\n❌ 告警严重堆积（{total} 条）")
    elif total > 500:
        print(f"\n⚠️  告警堆积（{total} 条）")
    else:
        print(f"\n✅ 告警数量正常（{total} 条）")

    if high_priority > 400:
        print(f"❌ 高危告警过多（红/橙 {high_priority} 条）")
    elif high_priority > 200:
        print(f"⚠️  高危告警偏多（红/橙 {high_priority} 条）")
    else:
        print(f"✅ 高危告警数量正常（红/橙 {high_priority} 条）")

    return result


def check_all(output_file=None):
    """综合检查所有数据质量"""
    results = {
        "check_time": datetime.now().isoformat(),
        "water_level": check_water_level(),
        "rainfall_forecast": check_rainfall_forecast(),
        "alerts": check_alerts()
    }

    # 生成问题集
    print("\n" + "=" * 70)
    print("【问题集汇总】")
    print("=" * 70)

    problems = []

    # 检查水位
    wl = results['water_level']
    if wl['距现在小时'] > 24:
        problems.append({
            "type": "P0",
            "category": "水位数据时效性",
            "description": f"水位数据已过期 {wl['距现在小时']} 小时",
            "data": wl
        })

    # 检查降雨预报
    rf = results['rainfall_forecast']
    if rf['批次距现在小时'] > 12:
        problems.append({
            "type": "P0",
            "category": "降雨预报时效性",
            "description": f"降雨预报已过期 {rf['批次距现在小时']} 小时",
            "data": rf
        })

    # 检查告警
    al = results['alerts']
    if al['未确认总数'] > 500:
        problems.append({
            "type": "P1",
            "category": "告警堆积",
            "description": f"未确认告警堆积 {al['未确认总数']} 条",
            "data": al
        })

    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for i, p in enumerate(problems, 1):
            print(f"\n问题 {i} [{p['type']}]：{p['category']}")
            print(f"  描述：{p['description']}")
    else:
        print("\n✅ 未发现严重问题")

    # 保存到文件
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n结果已保存到：{output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(description='数据质量检查脚本')
    parser.add_argument('--type', choices=['water_level', 'rainfall_forecast', 'alerts', 'all'],
                       default='all', help='检查类型')
    parser.add_argument('--output', help='输出文件路径（仅 type=all 时有效）')
    args = parser.parse_args()

    if args.type == 'water_level':
        check_water_level()
    elif args.type == 'rainfall_forecast':
        check_rainfall_forecast()
    elif args.type == 'alerts':
        check_alerts()
    elif args.type == 'all':
        check_all(args.output)


if __name__ == '__main__':
    main()
