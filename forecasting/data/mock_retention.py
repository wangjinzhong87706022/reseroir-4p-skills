#!/usr/bin/env python3
"""
mock_retention.py -- mock 数据留存期清理 + 软删残留盘点(默认 dry-run,不写库)。

与 purge_mock.sql 的分工:
    purge_mock.sql    全清(WHERE creator='MOCK',无租户、无时间上界)
                      —— demo 后一键回滚用,一次删光;
    mock_retention.py 留存(带 tenant_id + tm 上界,默认 30 天)
                      —— 常驻 feeder 用,只删过期行,保住断点续写所需的近期数据。

为什么 feeder 场景必须用留存而不是全清:两个水库的 mock 每 50 分钟断点续写,
全清会把 MAX(tm) 断点一起删掉,下次续写只能从 48h 前重新灌(正是桃曲坡
8/13-8/25 断供的翻版)。留存清理删的是断点之前的老数据,不影响续写。

纪律第 3 条(AGENTS.md)在本脚本里的落实不是靠注释,而是靠断言:
删除 WHERE 必须同时含 creator(mock 标记)/ tenant_id / tm 三要素,缺一即 sys.exit。
真实行(creator IS NULL)一行不碰。

软删行(deleted=1)**不删**——那是业务自己的删除语义。本脚本只盘点报告:
软删 mock 会让断点查询读不到最后一行,须用 cleanup_tenant_pollution.py 处理。

备份:--execute 先把"即将删掉的行"原样复制到带时间戳的表。备份的是待删行本身,
      不是整表——留存删除量大,整表备份没有意义。

用法:
    export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml \
           SRM_DB_USER=root SRM_DB_PASSWORD=***
    python3 forecasting/data/mock_retention.py                       # dry-run
    python3 forecasting/data/mock_retention.py --days 30 --execute   # 备份+真删
    python3 forecasting/data/mock_retention.py --days 90             # 改留存窗口

建议的周期任务(需自行 crontab -e,本脚本不代为安装):
    23 3 * * * flock /tmp/mock_retention.lock python3 .../mock_retention.py --execute
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from lib.db import execute_query, unpack  # noqa: E402
from lib.db_write import execute_write  # noqa: E402

TABLES = ["st_rsvr_r", "st_pptn_r"]

# 删除 WHERE 的三要素:mock 标记 + 租户 + 时间上界。缺任何一个就不许删。
REQUIRED_IN_WHERE = ("creator", "tenant_id", "tm")


def rows(sql, params=None):
    return unpack(execute_query(sql, params))


def one(sql, params=None):
    r = rows(sql, params)
    return r[0] if r else {}


def discover():
    """找出哪些 (表, 租户) 真有 MOCK 行——不硬编码清单,避免对空租户空跑。"""
    found = []
    for table in TABLES:
        for r in rows(f"SELECT tenant_id, COUNT(*) AS n, MIN(tm) AS mn, MAX(tm) AS mx "
                      f"FROM {table} WHERE creator = 'MOCK' GROUP BY tenant_id "
                      f"ORDER BY tenant_id"):
            found.append({"table": table, "tenant_id": r["tenant_id"],
                          "n": int(r["n"] or 0), "mn": r["mn"], "mx": r["mx"]})
    return found


def count(table, where, params):
    return int(one(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}",
                   params).get("n") or 0)


def main():
    args = sys.argv[1:]
    execute = "--execute" in args
    days = 30
    if "--days" in args:
        i = args.index("--days")
        if i + 1 >= len(args) or not args[i + 1].isdigit():
            sys.exit("--days 需要一个正整数天数,如 --days 30")
        days = int(args[i + 1])
    cutoff = datetime.now() - timedelta(days=days)

    print("=" * 68)
    print(f"mock 留存清理 [{'EXECUTE 会真删' if execute else 'DRY-RUN 不写库'}]  "
          f"窗口:{days} 天, 截止 {cutoff:%Y-%m-%d %H:%M:%S}")
    print("=" * 68)

    targets = discover()
    if not targets:
        print("\n没有任何 creator='MOCK' 的行,无需清理。")
        return

    print("\n[盘点] 各表 mock 行现状")
    for t in targets:
        print(f"  {t['table']} tenant {t['tenant_id']}: {t['n']} 行, "
              f"{t['mn']} → {t['mx']}")

    # ---- 预检 + 统计待删 ----
    print(f"\n[预检] 待删行(creator='MOCK' 且 tm 早于 {days} 天前)")
    total_will_delete = 0
    for t in targets:
        where = "creator = %s AND tenant_id = %s AND tm < %s"
        params = ("MOCK", t["tenant_id"], cutoff)
        for must in REQUIRED_IN_WHERE:
            if must not in where:
                sys.exit(f"[SAFETY] 删除 WHERE 缺少 {must},拒绝执行——"
                         f"这是代码缺陷,不是数据问题")
        n = count(t["table"], where, params)
        t["where"], t["params"] = where, params
        t["will_delete"] = n
        total_will_delete += n
        print(f"  {t['table']} tenant {t['tenant_id']}: 删 {n} 行, "
              f"留 {t['n'] - n} 行")
    if total_will_delete == 0:
        print("\n没有超过留存窗口的 mock 行,无需清理。")
    else:
        print(f"\n  合计待删 {total_will_delete} 行")

    # ---- 软删残留:只报告,不动 ----
    print("\n[盘点] 软删 mock 残留(deleted=1,本脚本不删,仅提示)")
    for table in TABLES:
        r = one(f"SELECT COUNT(*) AS n, MIN(tm) AS mn FROM {table} "
                f"WHERE creator = 'MOCK' AND deleted = 1")
        n = int(r.get("n") or 0)
        if n:
            print(f"  [提示] {table}: {n} 行软删 mock({r.get('mn')} 起)。"
                  f"它们会让断点续写查不到最后一行——"
                  f"用 cleanup_tenant_pollution.py 处理。")
        else:
            print(f"  [OK ] {table}: 无软删 mock 残留")

    if not execute:
        print("\n[DRY-RUN] 未写库。加 --execute 才会备份并删除。")
        return

    # ---- 备份 + 删除 ----
    print("\n[执行]")
    for t in targets:
        if not t["will_delete"]:
            continue
        table, where, params = t["table"], t["where"], t["params"]
        bak = f"{table}_bak_{datetime.now():%Y%m%d_%H%M%S}"
        if not bak.replace("_", "").isalnum():
            sys.exit(f"[BACKUP] 拒绝使用异常备份表名:{bak}")
        if one("SHOW TABLES LIKE %s", (bak,)):
            sys.exit(f"[BACKUP] 备份表 {bak} 已存在——不覆盖,请重跑")
        backed = execute_write(f"CREATE TABLE {bak} AS SELECT * FROM {table} "
                               f"WHERE {where}", params)
        deleted = execute_write(f"DELETE FROM {table} WHERE {where}", params)
        left = count(table, where, params)
        status = "OK" if (deleted == t["will_delete"] and left == 0) else "CHECK"
        print(f"  [{status}] {table} tenant {t['tenant_id']}: 备份 {backed} 行 → {bak}, "
              f"删除 {deleted} 行, 残留 {left} 行")

    print("\n[回滚] 按上面打印的备份表名执行:"
          "INSERT INTO <表> SELECT * FROM <备份表>;")


if __name__ == "__main__":
    main()
