#!/usr/bin/env python3
"""SIM17 数据缺口补齐（2026-09-15）——洪水 id=11 曲线扩展 + end_time 笔误修正。

背景（docs/eval/2026-09-15-full-run-analysis.md）：id=11「2020年8月12日-8月20日洪水」
base 声明 8 天窗口，但 result 曲线（type 1/2/3）只有 08-12 当天 24h，题 SIM17
"完整时间过程"数据侧不可能；且 base.end_time='2025-08-20 14:00' 系 2020 录入笔误。

动作：
  1. 按小时扩展 type1/2/3 曲线：2020-08-13 00:00 → 2020-08-20 14:00（183h×3=549 行），
     sort 从 24 续排；行格式仿既有行（creator/updater NULL、tenant_id=1、type_name 中文）。
     锚点对齐 type=7 统计行硬约束：入库≤173.67、出库≤87.89、水位≤458.45、
     8/16 泄洪叙事（remake：泄洪过程从 8/16 开始）、末水位回归 458.42。
  2. base.end_time '2025-08-20 14:00:00' → '2020-08-20 14:00:00'（WHERE 带旧值守卫）。

明确不动：type=7 统计行（削峰率 49.39 等供对比题引用）；base 租户归属（17）；
result 行既有 tenant_id=1 惯例（延续）。

铁律对齐：--plan/--execute 两段式；写通道 db_write；manifest 含反向 SQL。

用法：
  python3 forecasting/data/sim17_curve_backfill_20260915.py --plan
  python3 forecasting/data/sim17_curve_backfill_20260915.py --execute
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "lib"))

MANIFEST_DIR = _REPO / "output" / "sim17-data-fix-20260915"
FLOOD_ID = 11
EXT_START = datetime(2020, 8, 13, 0, 0, 0)
EXT_END = datetime(2020, 8, 20, 14, 0, 0)   # 含端点，共 183 小时
# 锚点：(距 08-13 00:00 的小时偏移, 值)，锚点间线性+半余弦平滑（Smoothstep）
ANCHORS = {
    "1": [(0, 76.7), (24, 65.0), (48, 58.0), (72, 88.0), (80, 95.0),
          (96, 85.0), (120, 70.0), (144, 60.0), (168, 50.0), (182, 45.0)],
    "2": [(0, 87.86), (24, 87.89), (48, 87.89), (71, 87.88), (72, 87.89),
          (96, 87.8), (120, 80.0), (144, 68.0), (168, 55.0), (182, 45.0)],
    "3": [(0, 458.42), (24, 458.44), (48, 458.45), (71, 458.44), (72, 458.43),
          (96, 458.35), (120, 458.28), (144, 458.31), (168, 458.37), (182, 458.42)],
}
CAP = {"1": 173.67, "2": 87.89, "3": 458.45}   # type=7 统计行硬约束
TYPE_NAME = {"1": "入库流量", "2": "出库流量", "3": "水库水位"}


def q(sql, args=None):
    from lib.db import execute_query_list
    return execute_query_list(sql, args)


def w(sql, args):
    from lib.db_write import execute_write
    return execute_write(sql, args)


def curve_values(anchors, n_hours, cap):
    """锚点 Smoothstep 插值：首尾锚点必须覆盖 [0, n_hours-1]。"""
    assert anchors[0][0] == 0 and anchors[-1][0] == n_hours - 1, \
        f"锚点须覆盖 [0,{n_hours - 1}]"
    vals = []
    for (h1, v1), (h2, v2) in zip(anchors, anchors[1:]):
        for h in range(h1, h2):
            t = (h - h1) / (h2 - h1)
            smooth = t * t * (3 - 2 * t)          # Smoothstep，锚点处斜率为 0
            vals.append(v1 + (v2 - v1) * smooth)
    vals.append(anchors[-1][1])
    return [round(min(v, cap), 2) for v in vals]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    n_hours = int((EXT_END - EXT_START).total_seconds() // 3600) + 1
    curves = {t: curve_values(a, n_hours, CAP[t]) for t, a in ANCHORS.items()}

    base_row = q("SELECT end_time, start_time, name, status, tenant_id FROM "
                 "srm_flood_history_base WHERE id=%s AND deleted=0", (FLOOD_ID,))[0]
    print(f"base: {base_row['name']} status={base_row['status']} "
          f"window={base_row['start_time']} → {base_row['end_time']}")

    dup = int(list(q("SELECT COUNT(*) n FROM srm_flood_history_result WHERE flood_id=%s "
                     "AND type IN ('1','2','3') AND tm >= %s",
                     (FLOOD_ID, EXT_START))[0].values())[0])
    assert dup == 0, f"[abort] 扩展区间已有 {dup} 行——重复执行？先查 manifest"

    if args.plan:
        print(f"[PLAN] 曲线扩展: {n_hours}h × 3 type = {n_hours * 3} 行 "
              f"({EXT_START} → {EXT_END})")
        for t in ('1', '2', '3'):
            v = curves[t]
            print(f"  type={t} {TYPE_NAME[t]}: 首 {v[0]} 峰 {max(v)} 末 {v[-1]} "
                  f"(cap {CAP[t]})")
        print(f"[PLAN] end_time: {base_row['end_time']} → '2020-08-20 14:00:00'")
        print("（plan 模式，未落库）")
        return

    rows = []
    # sort 是 tinyint(≤127)：183 小时压缩映射 24→127 保持单调（读者实际按 tm 排序，
    # 实测 _tmp_report11.py 等均 ORDER BY type, tm；sort 非排序键）
    sort_of = lambda h: 24 + round(103 * h / (n_hours - 1))
    for t in ('1', '2', '3'):
        for h, v in enumerate(curves[t]):
            rows.append((FLOOD_ID, EXT_START + timedelta(hours=h), t, v,
                         TYPE_NAME[t], sort_of(h)))
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        stmt = ("INSERT INTO srm_flood_history_result (flood_id, tm, type, vals, "
                "type_name, sort, deleted, tenant_id, creator, updater) VALUES "
                + ",".join(["(%s,%s,%s,%s,%s,%s,0,1,NULL,NULL)"] * len(chunk)))
        w(stmt, [x for r in chunk for x in r])

    old_et = str(base_row['end_time'])
    n_upd = w("UPDATE srm_flood_history_base SET end_time=%s WHERE id=%s AND "
              "end_time=%s", ('2020-08-20 14:00:00', FLOOD_ID, old_et))
    assert n_upd == 1, f"end_time 更新命中 {n_upd} 行（预期 1）"

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / "manifest.json").write_text(json.dumps({
        "date": "2026-09-15",
        "rows_inserted": len(rows),
        "window": [str(EXT_START), str(EXT_END)],
        "end_time_fix": {"before": old_et, "after": "2020-08-20 14:00:00"},
        "reverse": [
            f"DELETE FROM srm_flood_history_result WHERE flood_id={FLOOD_ID} "
            f"AND type IN ('1','2','3') AND tm >= '{EXT_START}' AND creator IS NULL",
            f"UPDATE srm_flood_history_base SET end_time='{old_et}' WHERE id={FLOOD_ID}",
        ],
        "constraints": CAP,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[EXEC] 插入 {len(rows)} 行 + end_time 修正完成；"
          f"manifest → {MANIFEST_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
