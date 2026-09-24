#!/usr/bin/env python3
"""
audit_mock_data.py -- 只读审计:mock 数据污染、重复组、新鲜度(2026-09-24)。

本脚本**只读**,不写库。用途:
    1. 污染清单:tenant 1 跨租户 mock 行、治理插值串户行、tenant 20 软删残留,
       以及各自的时间范围与水位区间——清理前的人工确认依据;
    2. 重复组:按 (tenant_id, stcd, tm) 统计重复行,并区分 creator IS NULL
       (真实/自然行)与 creator='MOCK'。**这是加唯一约束的前置判据**:
       若重复组只出现在 mock 行,清完即可加;若真实行也有重复组,
       说明现网 ingestion 本身会写重复,加唯一约束会打断生产,须先与 DBA 确认;
    3. 新鲜度:两个水库 mock 数据的 MAX(tm) 陈旧时长,以及 tenant 17/18 真实
       雨量的陈旧时长(三岔真实雨量 2026-09-14 起停更,用于追踪是否恢复)。

用法:
    export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml \
           SRM_DB_USER=root SRM_DB_PASSWORD=***
    python3 forecasting/data/audit_mock_data.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from lib.db import execute_query, unpack  # noqa: E402

TABLES = ["st_rsvr_r", "st_pptn_r"]


def rows(sql):
    return unpack(execute_query(sql))


def one(sql):
    r = rows(sql)
    return r[0] if r else {}


def section(title):
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


def audit_pollution(post_clean=False):
    section("1. 污染清单(清理前确认用)")
    if post_clean:
        print("模式:--post-clean,预期三项均已清成 0 行(cleanup_tenant_pollution.py 之后跑)")
    checks = [
        ("tenant 1 跨租户 mock 水位", "tenant_id=1 AND eq_code='MOCK'", 1176),
        ("tenant 1 治理插值串户", "tenant_id=1 AND creator='data-governance-interpolation'", 368),
        ("tenant 20 软删 MOCK 残留", "tenant_id=20 AND deleted=1", 165),
    ]
    for label, where, expect in checks:
        # 清理后这三项的预期值就是 0;清理前是审计钉死的历史行数
        want = 0 if post_clean else expect
        agg = one(f"SELECT COUNT(*) AS n, MIN(tm) AS mn, MAX(tm) AS mx, "
                  f"MIN(rz) AS min_rz, MAX(rz) AS max_rz FROM st_rsvr_r WHERE {where}")
        n = int(agg.get("n") or 0)
        flag = "OK " if n == want else "≠预期"
        print(f"[{flag}] {label}: {n} 行(预期 {want})")
        if n:
            print(f"        tm {agg['mn']} → {agg['mx']}, 水位 {agg['min_rz']}–{agg['max_rz']}m")
            if not post_clean:
                stacked = rows(
                    f"SELECT tm, COUNT(*) AS c FROM st_rsvr_r WHERE {where} "
                    f"GROUP BY tm HAVING c > 1 ORDER BY c DESC LIMIT 3")
                if stacked:
                    print("        重复堆叠示例: " + ", ".join(
                        f"{r['tm']}×{r['c']}" for r in stacked))
        elif post_clean:
            print("        ✓ 已清空")


def audit_duplicates():
    section("2. 重复组(加唯一约束的前置判据)")
    print("口径:UNIQUE(tenant_id, stcd, tm)。MySQL 唯一索引把 NULL 视为互不相同,")
    print("     所以 stcd IS NULL 的行不受该约束管辖,必须分开统计,否则会虚报。")
    for table in TABLES:
        # A) stcd 非空:这才是唯一索引真正会拦住的人群(造数脚本都写 stcd)
        a = rows(
            f"SELECT CASE WHEN creator IS NULL THEN 'REAL' ELSE creator END AS who, "
            f"COUNT(*) AS groups_, SUM(c - 1) AS extra FROM ("
            f"  SELECT tenant_id, stcd, tm, creator, COUNT(*) AS c FROM {table} "
            f"  WHERE stcd IS NOT NULL "
            f"  GROUP BY tenant_id, stcd, tm, creator HAVING c > 1) t GROUP BY who")
        total_a = sum(int(r["extra"] or 0) for r in a)
        print(f"\n[{table}] A) stcd 非空重复: 多出 {total_a} 行"
              f"({'可加约束' if total_a == 0 else '加约束前必须清完'})")
        for r in a:
            print(f"        {r['who']}: {r['groups_']} 组, 多出 {r['extra']} 行")
        if not a:
            print("        (无重复组 → 可以直接加唯一约束)")
        else:
            # 真实行重复必须交代清楚:发生在什么时间段、拷贝是否逐字节相同。
            # 若载荷相同,去重是机械操作;若不同(如 dr 历时不一致),就是数据口径决策,
            # 必须由 DBA + 采集方拍板,脚本不能替他们决定留哪一行。
            w = rows(
                f"SELECT MIN(tm) AS mn, MAX(tm) AS mx FROM ("
                f"  SELECT tm FROM {table} WHERE stcd IS NOT NULL "
                f"  GROUP BY tenant_id, stcd, tm HAVING COUNT(*) > 1) t")
            if w:
                print(f"        重复时间窗 {w[0]['mn']} → {w[0]['mx']}"
                      f"(窗口外无重复 → 是历史事故,非进行中的采集 bug)")
        # B) stcd 为 NULL:唯一索引管不到,单独披露( tenant 1 那 1176 行正属此类)
        b = rows(
            f"SELECT COUNT(*) AS groups_, SUM(c - 1) AS extra FROM ("
            f"  SELECT tenant_id, tm, COUNT(*) AS c FROM {table} "
            f"  WHERE stcd IS NULL GROUP BY tenant_id, tm HAVING c > 1) t")
        extra_b = int(b[0]["extra"] or 0) if b else 0
        # 注:条件表达式不写进 f-string 花括号里——Python 3.11 的 f-string 扫描器
        # 对"内联条件 + 中文破折号"会误报 unmatched ')',先算好再插值。
        note_b = "——唯一索引管不到,只能靠标记清理" if extra_b else ""
        print(f"        B) stcd 为 NULL 的堆叠: 多出 {extra_b} 行({note_b})")


def audit_freshness():
    section("3. 新鲜度(mock 断供 + 真实数据停更监控)")
    for r in rows(
            "SELECT tenant_id, MAX(tm) AS last_tm, COUNT(*) AS n FROM st_rsvr_r "
            "WHERE creator='MOCK' AND tenant_id IN (20,18) GROUP BY tenant_id"):
        age = one(f"SELECT TIMESTAMPDIFF(HOUR, MAX(tm), NOW()) AS age_h FROM st_rsvr_r "
                  f"WHERE creator='MOCK' AND tenant_id={r['tenant_id']}")
        age_h = int(age.get("age_h") or 0)
        status = "OK" if age_h <= 2 else "ALERT"
        print(f"[{status}] tenant {r['tenant_id']} mock: {r['n']} 行, "
              f"最新 {r['last_tm']}, 陈旧 {age_h}h")
    print()
    for r in rows(
            "SELECT tenant_id, MAX(tm) AS last_tm FROM st_pptn_r "
            "WHERE creator IS NULL AND tenant_id IN (17,18) GROUP BY tenant_id"):
        age = one(f"SELECT TIMESTAMPDIFF(HOUR, MAX(tm), NOW()) AS age_h FROM st_pptn_r "
                  f"WHERE creator IS NULL AND tenant_id={r['tenant_id']}")
        age_h = int(age.get("age_h") or 0)
        status = "OK" if age_h <= 48 else "ALERT"
        print(f"[{status}] tenant {r['tenant_id']} 真实雨量: 最新 {r['last_tm']}, "
              f"陈旧 {age_h}h")


if __name__ == "__main__":
    # --post-clean:清理完成后跑,预期三项都是 0 行
    post_clean = "--post-clean" in sys.argv[1:]
    audit_pollution(post_clean)
    audit_duplicates()
    audit_freshness()
    print()
