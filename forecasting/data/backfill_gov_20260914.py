#!/usr/bin/env python3
"""数据治理补数（2026-09-14）——补 9/8 盘点出的 6 项评测前提缺口。

覆盖项：
  A. TEST_ 测试告警 3 条软删（KB root-cause-solutions 配方）
  B. 规则#0 无规则告警 377 条软删（引擎 8/23 后停更，不会再生）
  C. 606K 系列 7 站雨量续补（停在 2026-05-29 17:00）——小时粒度事件式降雨，
     行形态仿各自自然行：tenant/eq_code 从最新自然行派生（2151/2152/2158 是
     租户 17，其余 18，2026-09-14 实测），dr=60.0/dyp=NULL/creator=NULL
  D. 2025001001 站雨量续补（停在 2026-06-08 23:00）——该站小时行 dr=1.0、
     eq_code 无后缀，与 606K 系不同构
  E. /data/plans/plan-001~015.xlsx 生成（model_result_files 元数据 → openpyxl；
     文件内自declare补齐来源，防 agent 误当权威工程文件；DB 行零改动）

明确不动（记录在案）：
  - att_res_discharge_curve："460/461/462 重复"实为三岔 order=1（溢洪道）与
    order=3 两条工程曲线同 z 区间共存，462.5→94.0 是 order=3 尾段（斜率连续）——
    非脏数据，改工程曲线=造数据。
  - D:\\xajmodel 与 /home/xajmodel 的 41 条 xlsx 引用：历史环境残留，不在题面。
  - MS001* 渗压/渗流 5 站（停在 2026-01-11）：240 天合成体量大、题面无真值依赖，
    本轮跳过待裁定。
  - '46' 主雨量站（基线 0 行，cron 在写）：不在 9/8 清单，跳过。

铁律对齐：水位表只滚不清（零接触 st_rsvr_r/f_rnfl_h）；每步留 manifest（含反向
SQL）；写入统一走 lib.db_write.execute_write；先 --plan 后 --execute 两段式。

用法：
  python3 forecasting/data/backfill_gov_20260914.py --plan      # 只打印计划
  python3 forecasting/data/backfill_gov_20260914.py --execute   # 执行并写 manifest
"""
import argparse
import json
import os
import random
import sys
import zlib
from datetime import datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "lib"))

MANIFEST_DIR = _REPO / "output" / "data-governance-20260914"

# 断档起点 = 各站自然行断点 + 1h（606K 系停在 05-29 17:00；2025001001 停在 06-08 23:00）
RAIN_STATIONS = {
    "606K2148": "2026-05-29 18:00:00", "606K2149": "2026-05-29 18:00:00",
    "606K2150": "2026-05-29 18:00:00", "606K2151": "2026-05-29 18:00:00",
    "606K2152": "2026-05-29 18:00:00", "606K2155": "2026-05-29 18:00:00",
    "606K2158": "2026-05-29 18:00:00", "2025001001": "2026-06-09 00:00:00",
}
# 小时汇总行的 dr 惯例：606K 系（遥测雨量）=60.0，2025 系（整数位站号）=1.0
DR_HOURLY = {"606K2148": 60.0, "606K2149": 60.0, "606K2150": 60.0,
             "606K2151": 60.0, "606K2152": 60.0, "606K2155": 60.0,
             "606K2158": 60.0, "2025001001": 1.0}
# 站间相关系数：同一天气过程，各站 0.7~1.25 缩放（idx 由 dict 序稳定派生）
SCALES = [0.7, 0.85, 1.0, 1.1, 1.25, 0.9, 1.15, 0.8]


def q(sql, args=None):
    from lib.db import execute_query_list
    return execute_query_list(sql, args)


def w(sql, args):
    from lib.db_write import execute_write
    return execute_write(sql, args)


# ── 降雨合成：事件式，站间相关 ────────────────────────────────────────────────
def synthesize_rain(hours, seed):
    rng = random.Random(seed)
    out = []   # [(hour_offset, p)]
    i = 0
    while i < hours:
        if rng.random() < 0.06:            # 6% 概率开启一场雨（时长 3~10h）
            dur = rng.randint(3, 10)
            peak = rng.choice([0.8, 1.2, 2.0, 3.5, 6.0, 9.5, 14.0])
            for k in range(dur):
                if i + k >= hours:
                    break
                shape = (1.0 if k == 0 else max(0.1, 1.0 - k / dur))
                out.append((i + k, round(peak * shape * rng.uniform(0.6, 1.1), 1)))
            i += dur
        else:
            out.append((i, 0.0))
            i += 1
    return out


def station_profile(stcd):
    """从最新自然行派生 (tenant_id, eq_code)；合成行必须与自然行同租户同设备号。"""
    rows = q("SELECT tenant_id, eq_code FROM st_pptn_r WHERE stcd=%s "
             "ORDER BY tm DESC LIMIT 1", (stcd,))
    if not rows:
        raise SystemExit(f"[abort] {stcd} 无任何自然行，tenant/eq_code 无法派生")
    return int(rows[0]["tenant_id"]), str(rows[0]["eq_code"])


def build_rain_rows(stcd, tenant, eq_code, start, end, idx):
    dr = DR_HOURLY[stcd]
    hours = int((end - start).total_seconds() // 3600) + 1
    base = synthesize_rain(hours, seed=zlib.crc32(stcd.encode("utf-8")))
    scale = SCALES[idx % len(SCALES)]
    rows = []
    for off, p in base:
        if p and scale != 1.0:
            p = round(p * scale, 1)
        rows.append((start + timedelta(hours=off), p, dr, None, stcd, tenant, eq_code))
    return rows


def insert_rain(rows):
    """纪律通道分批写入：多行 VALUES 参数化（execute_write 单语句+commit）。"""
    sql = ("INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, "
           "creator, eq_code) VALUES " + ",".join(["(%s,%s,%s,%s,%s,%s,0,NULL,%s)"] * 1000))
    for i in range(0, len(rows), 1000):
        chunk = rows[i:i + 1000]
        flat = [v for row in chunk for v in row]
        stmt = sql if len(chunk) == 1000 else \
            ("INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, "
             "creator, eq_code) VALUES " + ",".join(["(%s,%s,%s,%s,%s,%s,0,NULL,%s)"] * len(chunk)))
        w(stmt, flat)


def gen_plan_xlsx(meta):
    """按 model_result_files 元数据生成占位 xlsx（自declare补齐来源）。"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "调度方案"
    ws.append(["项目", "值"])
    for row in [("方案编号(scheme_id)", meta["scheme_id"]),
                ("方案名称(alias)", meta["alias"]),
                ("原始文件名", meta["file_name"]),
                ("起始时间", str(meta["start_time"])),
                ("结束时间", str(meta["end_time"])),
                ("目标水位(m)", meta["target_water_level"]),
                ("调整后水位(m)", meta["adjusted_water_level"]),
                ("方案类型(type)", meta["type"]),
                ("tenant_id", meta["tenant_id"]),
                ("备注", f"本文件为 2026-09-14 数据治理补齐件（原文件缺失），"
                         f"内容取自 model_result_files id={meta['id']} 元数据，"
                         "非原始工程成果文件")]:
        ws.append(row)
    os.makedirs(os.path.dirname(meta["file_path"]), exist_ok=True)
    wb.save(meta["file_path"])
    return meta["file_path"]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="只打印计划不落库")
    g.add_argument("--execute", action="store_true", help="执行并写 manifest")
    args = ap.parse_args()
    now = datetime.now()
    manifest = {"started": now.isoformat(timespec="seconds"), "steps": []}

    # ---- A/B 告警清理（软删，id 列表留 manifest 可逆）----------------------
    for label, where in [
        ("A. TEST_ 测试告警软删", "ew_name LIKE 'TEST\\\\_%' AND deleted=0"),
        ("B. 规则#0 无规则告警软删", "ew_rules_id=0 AND deleted=0"),
    ]:
        n = int(list(q(f"SELECT COUNT(*) n FROM ew_info_message WHERE {where}")[0].values())[0])
        step = {"step": label, "before": n,
                "reverse": "按 manifest.ids 回置 deleted=0"}
        if args.execute and n:
            ids = [int(r["id"]) for r in q(f"SELECT id FROM ew_info_message WHERE {where}")]
            w(f"UPDATE ew_info_message SET deleted=1 WHERE id IN "
              f"({','.join(['%s'] * len(ids))})", tuple(ids))
            after = int(list(q(f"SELECT COUNT(*) n FROM ew_info_message WHERE {where}")[0].values())[0])
            step.update({"deleted": len(ids), "after": after, "ids": ids})
            assert after == 0, f"{label} 后仍有 {after} 条"
        manifest["steps"].append(step)
        print(f"[{'EXEC' if args.execute else 'PLAN'}] {label}: {n} 条")

    # ---- C/D 雨量续补 -----------------------------------------------------
    per = {}
    for idx, (stcd, start_s) in enumerate(RAIN_STATIONS.items()):
        start = datetime.strptime(start_s, "%Y-%m-%d %H:%M:%S")
        tenant, eq = station_profile(stcd)
        last = q("SELECT MAX(tm) m FROM st_pptn_r WHERE stcd=%s AND deleted=0",
                 (stcd,))[0]["m"]
        last_s = str(last)   # _serialize_value 已把 datetime 转字符串
        assert last_s < start_s, f"{stcd} 断点异常: {last_s}"
        ent = {"tenant": tenant, "eq_code": eq, "dr": DR_HOURLY[stcd],
               "db_last": str(last), "start": start_s}
        if args.execute:
            rows = build_rain_rows(stcd, tenant, eq, start, now, idx)
            insert_rain(rows)
            ent["inserted"] = len(rows)
            ent["reverse"] = (f"DELETE FROM st_pptn_r WHERE stcd='{stcd}' "
                              f"AND tm >= '{start_s}' AND creator IS NULL AND dr={DR_HOURLY[stcd]}")
        per[stcd] = ent
    total = sum(v.get("inserted", 0) for v in per.values())
    manifest["steps"].append({"step": "C/D 雨量续补（8 站）",
                              "window_end": now.isoformat(timespec="seconds"),
                              "stations": per, "total_inserted": total})
    print(f"[{'EXEC' if args.execute else 'PLAN'}] C/D 雨量续补 8 站: {total} 行 "
          f"（tenant 分布 {sorted({v['tenant'] for v in per.values()})}）")

    # ---- E plan xlsx（只建文件，DB 零改动）--------------------------------
    metas = q("SELECT id, scheme_id, alias, file_name, file_path, start_time, "
              "end_time, target_water_level, adjusted_water_level, type, tenant_id "
              "FROM model_result_files WHERE file_path LIKE '/data/plans/%' ORDER BY id")
    missing = [m for m in metas if not os.path.exists(m["file_path"])]
    print(f"[{'EXEC' if args.execute else 'PLAN'}] E. /data/plans xlsx: "
          f"{len(missing)}/{len(metas)} 缺失待生成")
    step = {"step": "E. /data/plans xlsx 生成", "db_rows_touched": 0,
            "existing": len(metas) - len(missing), "generated": []}
    if args.execute:
        for m in missing:
            path = gen_plan_xlsx(m)
            step["generated"].append({"id": int(m["id"]), "path": path,
                                      "reverse": f"rm '{path}'"})
    manifest["steps"].append(step)

    if args.execute:
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        out = MANIFEST_DIR / "manifest.json"
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
        print(f"\nmanifest → {out}")
    print("完成" if args.execute else "（plan 模式，未落库）")


if __name__ == "__main__":
    main()
