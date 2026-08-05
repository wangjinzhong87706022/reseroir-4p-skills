#!/usr/bin/env python3
"""
inspection_check.py -- 设备可调度性核查（step3）。

Supervisor 场景 A step3 的真实数据源：查询调度库中的设备清单/异常/缺陷/离线/闸门状态，
输出设备可调度性核查摘要（用于 DAG 中"设备约束"校验）。

用法:
    python3 scripts/inspection_check.py --type overview      # 设备全貌摘要（默认）
    python3 scripts/inspection_check.py --type offline       # 未恢复离线设备
    python3 scripts/inspection_check.py --type defects       # 未处理缺陷
    python3 scripts/inspection_check.py --type gates         # 闸门最新状态
    python3 scripts/inspection_check.py --type all           # 全部

设计原则:
    1. 按 SRM_TENANT_ID 过滤（桃曲坡=20 / 三岔=18），tenant 缺失列的表全量统计并标注。
    2. 只读查询，不触发任何写入。
    3. 输出 JSON，供 orchestrator 写入 State 与仲裁使用。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from lib.db import execute_query_list, _require_env  # noqa: E402
from lib.tenant import current_tenant_id  # noqa: E402


TENANT = current_tenant_id()


def overview() -> dict:
    """设备全貌摘要：总数/类型分布/异常/缺陷/离线/闸门"""
    equip_total = execute_query_list(
        "SELECT COUNT(*) AS cnt FROM eq_equip_base WHERE deleted=0"
    )[0]["cnt"]

    # 类型分布（type_flag: 1闸门 7水位计 8雨量计 20渗压计 等）
    type_rows = execute_query_list(
        "SELECT type_flag, COUNT(*) AS cnt FROM eq_equip_base "
        "WHERE deleted=0 GROUP BY type_flag ORDER BY cnt DESC"
    )

    # 异常记录（tenant 18/20；tenant=1 为测试数据）
    anomaly = execute_query_list(
        "SELECT COUNT(*) AS cnt FROM eq_equip_anomaly_record WHERE tenant_id=%s",
        (TENANT,),
    )[0]["cnt"]

    # 未恢复离线（offline_end_time IS NULL）
    offline_open = execute_query_list(
        "SELECT COUNT(*) AS cnt FROM eq_equip_offline_record "
        "WHERE tenant_id=%s AND offline_end_time IS NULL",
        (TENANT,),
    )[0]["cnt"]

    # 未处理缺陷（handle_status=0 待处理）
    defect_open = execute_query_list(
        "SELECT COUNT(*) AS cnt FROM eq_equip_defect "
        "WHERE tenant_id=%s AND deleted=0 AND handle_status=0",
        (TENANT,),
    )[0]["cnt"]

    # 闸门最新状态
    gate_rows = execute_query_list(
        "SELECT eq_code, gtq, gtophgt, gtopnum, status, tm "
        "FROM rei_gate_r WHERE tenant_id=%s AND deleted=0 "
        "ORDER BY tm DESC LIMIT 20",
        (TENANT,),
    )

    return {
        "tenant_id": TENANT,
        "equip_total": equip_total,
        "type_distribution": [{"type_flag": r["type_flag"], "count": r["cnt"]} for r in type_rows],
        "anomaly_count": anomaly,
        "offline_open_count": offline_open,
        "defect_open_count": defect_open,
        "gates_latest": [dict(r) for r in gate_rows],
    }


def offline() -> dict:
    rows = execute_query_list(
        "SELECT equipment_code, offline_start_date, offline_start_time, offline_end_time, "
        "total_offline_duration FROM eq_equip_offline_record "
        "WHERE tenant_id=%s AND offline_end_time IS NULL ORDER BY offline_start_time DESC LIMIT 20",
        (TENANT,),
    )
    return {"tenant_id": TENANT, "open_offline": [dict(r) for r in rows]}


def defects() -> dict:
    rows = execute_query_list(
        "SELECT id, equip_id, name, description, type, discovery_time, handle_status, handler "
        "FROM eq_equip_defect WHERE tenant_id=%s AND deleted=0 AND handle_status=0 "
        "ORDER BY discovery_time DESC LIMIT 20",
        (TENANT,),
    )
    return {"tenant_id": TENANT, "open_defects": [dict(r) for r in rows]}


def gates() -> dict:
    rows = execute_query_list(
        "SELECT eq_code, gtq, gtophgt, gtopnum, status, tm FROM rei_gate_r "
        "WHERE tenant_id=%s AND deleted=0 ORDER BY tm DESC LIMIT 30",
        (TENANT,),
    )
    return {"tenant_id": TENANT, "gates": [dict(r) for r in rows]}


def main():
    parser = argparse.ArgumentParser(description="设备可调度性核查")
    parser.add_argument("--type", default="overview",
                        choices=["overview", "offline", "defects", "gates", "all"])
    args = parser.parse_args()

    _ = TENANT  # 确保 tenant 解析在查询前完成（缺环境变量时提前报错）
    result = {}
    if args.type in ("overview", "all"):
        result["overview"] = overview()
    if args.type in ("offline", "all"):
        result["offline"] = offline()
    if args.type in ("defects", "all"):
        result["defects"] = defects()
    if args.type in ("gates", "all"):
        result["gates"] = gates()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()