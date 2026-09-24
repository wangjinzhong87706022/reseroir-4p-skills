#!/usr/bin/env python3
"""
cleanup_tenant_pollution.py -- 清理审计发现的三处污染行(默认 dry-run,不写库)。

2026-09-24 审计(audit_mock_data.py)确认的三处污染:
    T1  tenant 1  跨租户 mock 水位    1176 行  eq_code='MOCK' AND creator IS NULL
                                        tm 2026-08-16 13:00 → 08-23 12:00, 水位 461.4m
                                        (同一小时堆 7 行 = 168h × 7 次重跑)
    T2  tenant 1  治理插值串户         368 行  creator='data-governance-interpolation'
                                        tm 2026-08-06 11:00 → 08-21 18:00, 水位 461.7–471.62m
                                        (471.62m 超过三岔汛限 462.5m → 误报预警)
    T3  tenant 20 软删 MOCK 残留        165 行  deleted=1
                                        tm 2026-08-06 04:00 → 08-13 00:00, 水位 786.95m
                                        (桃曲坡 8/13-8/25 断供 12 天的根因)

为什么 T3 要硬删:这些行已处于软删状态,对业务不可见,但
generate_taoqupo_data.py 的断点查询带 deleted=0,永远查不到"最后一行 mock"
→ 回退"初始生成 48h" → 本表无 (tenant_id,stcd,tm) 唯一约束 → 反复重灌堆重复行。
详见该脚本 2026-09-24 的注释。

安全设计(缺一不可):
    1. 默认 dry-run,只打印将删的范围,不碰库;--execute 才真删;
    2. 每条目标带 expect 行数,不符即中止——口径漂移时宁可停手也不多删;
    3. T3 额外要求该租户的 deleted=1 行**全部**带 MOCK 标记,
       否则说明还有别人软删的行,停手人工看;
    4. --execute 先备份到带时间戳的表(含待清理租户的全部行)再删,可回滚;
    5. 只走 lib.db_write.execute_write(全仓唯一受控写入口),WHERE 一律 %s 参数化。

用法:
    export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml \
           SRM_DB_USER=root SRM_DB_PASSWORD=***
    python3 forecasting/data/cleanup_tenant_pollution.py                 # dry-run
    python3 forecasting/data/cleanup_tenant_pollution.py --execute       # 备份+真删
    python3 forecasting/data/cleanup_tenant_pollution.py --execute --only T3
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from lib.db import execute_query, unpack  # noqa: E402
from lib.db_write import execute_write  # noqa: E402
from lib.tenant import resolve_tenant  # noqa: E402

TABLE = "st_rsvr_r"

# WHERE 是每条目标的唯一事实来源:预检、快照、删除三条路径复用同一串,
# 不会出现"查的是一批、删的是另一批"。纪律第 3 条要求 WHERE 同时带 tenant_id
# 与 mock/污染标记——下面每条都满足。
# tenant_id 经 resolve_tenant(显式传参) 取得,不在 SQL 里写字面量(AGENTS.md 第 2 条)。
TARGETS = [
    {
        "key": "T1",
        "label": "tenant 1 跨租户 mock 水位",
        "expect": 1176,
        "where": "tenant_id = %s AND eq_code = %s AND creator IS NULL",
        "params": (resolve_tenant(1), "MOCK"),
    },
    {
        "key": "T2",
        "label": "tenant 1 治理插值串户",
        "expect": 368,
        "where": "tenant_id = %s AND creator = %s",
        "params": (resolve_tenant(1), "data-governance-interpolation"),
    },
    {
        "key": "T3",
        "label": "tenant 20 软删 MOCK 残留(桃曲坡断供根因)",
        "expect": 165,
        "where": "tenant_id = %s AND deleted = 1 AND creator = %s",
        "params": (resolve_tenant(20), "MOCK"),
        # 删前确认:tenant 20 的 deleted=1 行必须全部带 MOCK 标记。
        # 若宽松口径(deleted=1)数出更多行,说明还有别的来源软删的行,停手。
        "require_all_flagged": {
            "where": "tenant_id = %s AND deleted = 1",
            "params": (resolve_tenant(20),),
        },
    },
]


def one(sql, params=None):
    r = unpack(execute_query(sql, params))
    return r[0] if r else {}


def count(where, params=None):
    return int(one(f"SELECT COUNT(*) AS n FROM {TABLE} WHERE {where}", params).get("n") or 0)


def snapshot(tenant_id):
    """删前/删后各打一次:该租户在表里的整体轮廓,便于核对爆炸半径。"""
    return one(
        f"SELECT COUNT(*) AS n, MIN(tm) AS mn, MAX(tm) AS mx, "
        f"MIN(rz) AS min_rz, MAX(rz) AS max_rz, SUM(deleted) AS soft_del "
        f"FROM {TABLE} WHERE tenant_id = %s", (tenant_id,))


def show_snapshot(tag, snap):
    print(f"    {tag}: {snap.get('n')} 行, tm {snap.get('mn')} → {snap.get('mx')}, "
          f"水位 {snap.get('min_rz')}–{snap.get('max_rz')}m, "
          f"软删 {snap.get('soft_del') or 0} 行")


def do_backup(tenant_ids):
    """把待清理租户的全部行复制到带时间戳的表。表名由内部常量拼出、无法 %s 参数化
    (MySQL 标识符不能做占位符),故显式校验只含安全字符,且已存在即中止不覆盖。"""
    name = f"{TABLE}_bak_{datetime.now():%Y%m%d_%H%M%S}"
    if not name.replace("_", "").isalnum():
        sys.exit(f"[BACKUP] 拒绝使用异常备份表名:{name}")
    if one("SHOW TABLES LIKE %s", (name,)):
        sys.exit(f"[BACKUP] 备份表 {name} 已存在——不覆盖,请换个时间点重跑")
    ph = ", ".join(["%s"] * len(tenant_ids))
    n = execute_write(f"CREATE TABLE {name} AS SELECT * FROM {TABLE} "
                      f"WHERE tenant_id IN ({ph})", tuple(tenant_ids))
    print(f"[BACKUP] 已备份 tenant {list(tenant_ids)} → {name}({n} 行)")
    return name


def main():
    args = sys.argv[1:]
    execute = "--execute" in args
    only = None
    if "--only" in args:
        i = args.index("--only")
        if i + 1 >= len(args):
            sys.exit("--only 需要一个目标 key,如 --only T3")
        only = args[i + 1].upper()
    targets = [t for t in TARGETS if only in (None, t["key"])]
    if not targets:
        sys.exit(f"没有匹配的目标:{only}(可选 {', '.join(t['key'] for t in TARGETS)})")

    print("=" * 68)
    print(f"污染清理 [{'EXECUTE 会真删' if execute else 'DRY-RUN 不写库'}]"
          f"  目标:{', '.join(t['key'] for t in targets)}")
    print("=" * 68)

    total_before = count("1 = 1")
    print(f"\n[全局] {TABLE} 清理前 {total_before} 行")

    # ---- 预检:行数口径必须与审计一致,否则一条都不删 ----
    print("\n[预检] 行数口径核对(不符即中止)")
    for t in targets:
        n = count(t["where"], t["params"])
        ok = n == t["expect"]
        print(f"  [{'OK ' if ok else 'STOP'}] {t['key']} {t['label']}: "
              f"{n} 行(审计预期 {t['expect']})")
        if not ok:
            sys.exit(f"[预检] {t['key']} 行数 {n} ≠ 预期 {t['expect']},"
                     f"口径已漂移——请重跑 audit_mock_data.py 确认后再来。")
        guard = t.get("require_all_flagged")
        if guard:
            broad = count(guard["where"], guard["params"])
            if broad != n:
                sys.exit(f"[预检] {t['key']} 宽松口径(deleted=1)有 {broad} 行,"
                         f"比带 MOCK 标记的 {n} 行多——该租户还有别的软删行,停手人工确认。")
            print(f"        ✓ 该租户 {broad} 行软删数据全部带 MOCK 标记")

    # ---- 删前哨兵 ----
    print("\n[哨兵] 删前快照")
    tenants = []
    for t in targets:
        if t["params"][0] not in tenants:
            tenants.append(t["params"][0])
    before = {tenant: snapshot(tenant) for tenant in tenants}
    for tenant, snap in before.items():
        show_snapshot(f"tenant {tenant}", snap)

    if not execute:
        print("\n[DRY-RUN] 未写库。加 --execute 才会备份并删除。")
        return

    # ---- 备份 ----
    do_backup(sorted({t["params"][0] for t in targets}))

    # ---- 删除 ----
    print("\n[删除]")
    for t in targets:
        affected = execute_write(f"DELETE FROM {TABLE} WHERE {t['where']}", t["params"])
        left = count(t["where"], t["params"])
        status = "OK" if (affected == t["expect"] and left == 0) else "CHECK"
        print(f"  [{status}] {t['key']}: 删除 {affected} 行, 残留 {left} 行")

    # ---- 删后复核 ----
    print("\n[哨兵] 删后快照")
    for tenant in tenants:
        snap = snapshot(tenant)
        show_snapshot(f"tenant {tenant}", snap)
        delta = (before[tenant].get("n") or 0) - (snap.get("n") or 0)
        print(f"        净减 {delta} 行")
    total_after = count("1 = 1")
    print(f"\n[全局] {TABLE} 清理后 {total_after} 行(净减 {total_before - total_after} 行)")
    print("[回滚] 需要时按上面 [BACKUP] 打印的表名执行:"
          f"INSERT INTO {TABLE} SELECT * FROM <备份表>;")


if __name__ == "__main__":
    main()
