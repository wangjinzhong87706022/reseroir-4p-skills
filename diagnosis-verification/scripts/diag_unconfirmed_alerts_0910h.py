#!/usr/bin/env python3
"""三岔水库未确认告警诊断 — Phase 6/7 最终确认
诊断日期: 2026-09-10
"""
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query_list, query_one
from tenant import current_tenant_id

print(f"=== 租户: {current_tenant_id()} ===")

# A. 2026-08 告警（按月查）
print(f"\n=== A. 2026-08 告警 ===")
rows = execute_query_list("""
    SELECT id, ew_name, st_code, eq_code, value, level_r, create_time, message_confirm, deleted
    FROM ew_info_message
    WHERE tenant_id = 18 AND create_time >= '2026-08-01' AND create_time < '2026-09-01'
    ORDER BY create_time
""")
print(f"  共 {len(rows)} 条")
for r in rows:
    print(f"  id={r['id']}, 名称={r['ew_name']}, 站={r['st_code']}, 值={r['value']}, 级别={r['level_r']}, 确认={r['message_confirm']}, 删除={r['deleted']}, 时间={r['create_time']}")

# B. 主站水位跳变起始时间
print(f"\n=== B. 主站水位跳变起始时间 ===")
rows = execute_query_list("""
    SELECT tm, rz, inq, otq
    FROM st_rsvr_r
    WHERE deleted = 0 AND tenant_id = 18 AND stcd = '3' AND eq_code = 'sancha'
      AND tm >= '2026-08-25'
    ORDER BY tm ASC
    LIMIT 30
""")
prev = None
for r in rows:
    mark = ""
    if prev is not None and abs(r['rz'] - prev) > 1.0:
        mark = " <-- 跳变!"
    print(f"  {r['tm']}: rz={r['rz']}, inq={r['inq']}, otq={r['otq']}{mark}")
    prev = r['rz']

# C. 主站水位最早跳变
print(f"\n=== C. 主站水位最早跳变时间 ===")
rows = execute_query_list("""
    SELECT tm, rz
    FROM st_rsvr_r
    WHERE deleted = 0 AND tenant_id = 18 AND stcd = '3' AND eq_code = 'sancha'
    ORDER BY tm ASC
    LIMIT 5
""")
for r in rows:
    print(f"  最早: {r['tm']}: rz={r['rz']}")

# D. 主站水位值域分析（检查是否只有两个值）
print(f"\n=== D. 主站水位值域分析 ===")
rows = execute_query_list("""
    SELECT rz, COUNT(*) AS cnt, MIN(tm) AS first_tm, MAX(tm) AS last_tm
    FROM st_rsvr_r
    WHERE deleted = 0 AND tenant_id = 18 AND stcd = '3' AND eq_code = 'sancha'
    GROUP BY rz
    ORDER BY cnt DESC
    LIMIT 10
""")
for r in rows:
    print(f"  rz={r['rz']}: cnt={r['cnt']}, 首次={r['first_tm']}, 末次={r['last_tm']}")

# E. 未确认告警中 TEST_ 的完整统计
print(f"\n=== E. TEST_ 告警统计 ===")
rows = execute_query_list("""
    SELECT COUNT(*) AS total,
           SUM(CASE WHEN message_confirm = 0 THEN 1 ELSE 0 END) AS unconfirmed,
           SUM(CASE WHEN deleted = 1 THEN 1 ELSE 0 END) AS deleted_cnt
    FROM ew_info_message
    WHERE tenant_id = 18 AND ew_name LIKE 'TEST_%'
""")
for r in rows:
    print(f"  TEST_ 告警: 总={r['total']}, 未确认={r['unconfirmed']}, 已删除={r['deleted_cnt']}")

# F. 未确认告警中"设备离线"类
print(f"\n=== F. 设备离线类未确认告警 ===")
rows = execute_query_list("""
    SELECT st_code, COUNT(*) AS cnt, MIN(create_time) AS oldest, MAX(create_time) AS newest
    FROM ew_info_message
    WHERE message_confirm = 0 AND deleted = 0 AND tenant_id = 18
      AND ew_rules_type = '12'
    GROUP BY st_code
    ORDER BY cnt DESC
""")
for r in rows:
    print(f"  站={r['st_code']}, cnt={r['cnt']}, oldest={r['oldest']}, newest={r['newest']}")

# G. 606K 系列数据断更汇总
print(f"\n=== G. 606K 系列数据断更汇总 ===")
rows = execute_query_list("""
    SELECT eq_code, MAX(tm) AS latest_tm, COUNT(*) AS total
    FROM st_rsvr_r
    WHERE deleted = 0 AND tenant_id = 18 AND eq_code LIKE '606K%'
    GROUP BY eq_code
    ORDER BY eq_code
""")
for r in rows:
    print(f"  eq={r['eq_code']}, 最新={r['latest_tm']}, 总记录={r['total']}")

# H. 606K 系列降雨断更
print(f"\n=== H. 606K 系列降雨断更 ===")
rows = execute_query_list("""
    SELECT eq_code, MAX(tm) AS latest_tm, COUNT(*) AS total
    FROM st_pptn_r
    WHERE deleted = 0 AND tenant_id = 18 AND eq_code LIKE '606K%'
    GROUP BY eq_code
    ORDER BY eq_code
""")
for r in rows:
    print(f"  eq={r['eq_code']}, 最新={r['latest_tm']}, 总记录={r['total']}")

print(f"\n=== Phase 6/7 最终确认完成 ===")
