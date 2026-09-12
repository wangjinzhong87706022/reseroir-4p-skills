#!/usr/bin/env python3
"""场景注入层：按题单物化数据前提，manifest 留痕可 --restore（施工图 C2）。

背景：forecasting/data/scenarios/ 下 7 月已建成套错误场景 SQL，但从未接入评测
流程——异常题一直跑在"正常基线"上，前提靠运气。本模块把"场景→题目"映射
（eval/data/scenarios.yaml）接进 runner：每题执行前 setup 注入、判分后 teardown
恢复，全部动作写 manifest（含 pre-image），崩溃后可 --restore 回滚。

场景形态（scenarios.yaml 每项）：
  <name>:
    handler: file | insert_rows | null_rz_latest
    cases: [题 id...]          # 或在题目 yaml 侧写 fixtures: [<name>]
    exclusive: true            # 改基线表的场景；>EXCLUSIVE_MAX_BATCH 题的批量自动跳过
    teardown: restore | delete_first | cron_refresh | none
    # file:         file: <repo-rel .sql 路径>（可含会话变量，单连接顺序执行）
    # insert_rows:  table + marker_where + rows[{列: 值}]（幂等 DELETE-before-INSERT）
    # null_rz_latest: stcd + tenant_id + rows（主站最新 N 行 rz 置 NULL，pre-image 回写）

用法（run.py 内）：
  prep = Prep(report_dir); fx = prep.setup(case, n_selected); ...; prep.teardown(case)
命令行：
  python3 eval/data_prep.py --restore <fixture_manifest.json>
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for p in (str(_REPO / "lib"), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

SCENARIOS_YAML = Path(__file__).parent / "data" / "scenarios.yaml"
EXCLUSIVE_MAX_BATCH = 5   # exclusive 场景仅在 ≤5 题的小批量生效
TEARDOWN_NONE = "none"


def load_scenarios():
    import yaml
    data = yaml.safe_load(SCENARIOS_YAML.read_text(encoding="utf-8")) or {}
    return data.get("fixtures") or {}


def _execute_write(sql, params=None):
    """写入专用。lib.db.execute_query 不 commit（读导向），pymysql 池化连接 close 即回滚——
    2026-09-11 实测：经它 UPDATE rz=NULL 后 NULL 行数为 0（静默丢失）。写必须显式提交。"""
    from db import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 无参数时必须传 None：传 () 会让 pymysql 对 SQL 做 % 格式化，
            # LIKE '...\_%' 里的 % 通配符会炸（"not enough arguments"）。
            affected = cur.execute(sql, params) if params else cur.execute(sql)
        conn.commit()
        return affected
    finally:
        conn.close()


class Prep:
    def __init__(self, report_dir):
        self.scenarios = load_scenarios()
        self.manifest_path = Path(report_dir) / "fixture_manifest.json"
        self.manifest = {"started": datetime.now().isoformat(timespec="seconds"),
                         "entries": []}
        self._by_case = {}   # case_id -> [entry]

    # ---- 题目 → 场景解析 -------------------------------------------------
    def _specs_for(self, case, n_selected):
        out = []
        for name, spec in self.scenarios.items():
            wanted = case.id in (spec.get("cases") or []) or name in (case.fixtures or [])
            if not wanted:
                continue
            if spec.get("exclusive") and n_selected > EXCLUSIVE_MAX_BATCH:
                out.append({"fixture": name, "status": "skipped",
                            "reason": f"exclusive 场景仅小批量(≤{EXCLUSIVE_MAX_BATCH}题)生效,本次 {n_selected} 题"})
                continue
            out.append({"fixture": name, "status": "applied", "spec": spec})
        return out

    # ---- 注入 / 恢复 -----------------------------------------------------
    def setup(self, case, n_selected):
        """题目执行前调用。返回 [{fixture, status}] 供写进结果 detail。"""
        summary = []
        for item in self._specs_for(case, n_selected):
            if item["status"] == "skipped":
                summary.append({k: item[k] for k in ("fixture", "status", "reason")})
                print(f"   [fixture] {item['fixture']} SKIP: {item['reason']}", flush=True)
                continue
            name, spec = item["fixture"], item["spec"]
            entry = {"case": case.id, "fixture": name, "at": datetime.now().isoformat(timespec="seconds")}
            try:
                handler = getattr(self, f"_do_{spec['handler']}")
                pre = handler(case, spec)
                entry.update(status="applied", **(pre or {}))
                print(f"   [fixture] {name} 注入完成", flush=True)
            except Exception as e:
                entry.update(status="error", error=str(e)[:300])
                print(f"   [fixture] {name} 注入失败: {e}", flush=True)
            self.manifest["entries"].append(entry)
            self._by_case.setdefault(case.id, []).append(entry)
            self._flush()
            summary.append({"fixture": name, "status": entry["status"],
                            **({"error": entry["error"]} if entry.get("error") else {})})
        return summary

    def teardown(self, case):
        """题目判分后调用。restore/delete_first 就地恢复；cron_refresh 交给下轮 --roll/--forecast。"""
        for entry in self._by_case.get(case.id, []):
            if entry.get("status") != "applied":
                continue
            spec = self.scenarios[entry["fixture"]]
            td = spec.get("teardown", TEARDOWN_NONE)
            try:
                if td == "restore" and entry.get("pre_image") is not None:
                    self._restore_rows(entry["pre_image"])
                    entry["teardown"] = "restored"
                elif td == "delete_first":
                    _execute_write(f"DELETE FROM {spec['table']} WHERE {spec['marker_where']}")
                    entry["teardown"] = "deleted"
                elif td == "cron_refresh":
                    entry["teardown"] = "cron_refresh_pending"
                print(f"   [fixture] {entry['fixture']} teardown: {entry.get('teardown', td)}", flush=True)
            except Exception as e:
                entry["teardown"] = f"error: {e}"
                print(f"   [fixture] {entry['fixture']} teardown 失败: {e}", flush=True)
            self._flush()

    # ---- handlers --------------------------------------------------------
    def _do_file(self, case, spec):
        """执行场景 SQL 文件：剥离注释后按分号拆语句，单连接顺序执行（保会话变量）。"""
        from db import get_connection
        path = _REPO / spec["file"]
        sql_text = path.read_text(encoding="utf-8")
        stmts = []
        for raw in sql_text.split(";"):
            lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
            stmt = "\n".join(lines).strip()
            if stmt:
                stmts.append(stmt)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for stmt in stmts:
                    cur.execute(stmt)
                affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return {"file": spec["file"], "statements": len(stmts), "last_affected": int(affected)}

    def _do_insert_rows(self, case, spec):
        _execute_write(f"DELETE FROM {spec['table']} WHERE {spec['marker_where']}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in spec["rows"]:
            cols = {**row}
            vals = []
            for k, v in cols.items():
                vals.append(now if v == "NOW" else v)
            ph = ", ".join(["%s"] * len(cols))
            _execute_write(
                f"INSERT INTO {spec['table']} ({', '.join(cols)}) VALUES ({ph})", vals)
        return {"table": spec["table"], "rows": len(spec["rows"])}

    def _do_null_rz_latest(self, case, spec):
        """主站最新 N 行 rz 置 NULL；pre-image（id+rz）存 manifest 供 restore 回写。"""
        from db import execute_query
        stcd, tenant, n = spec["stcd"], spec["tenant_id"], int(spec["rows"])
        rows = execute_query(
            "SELECT id, rz FROM st_rsvr_r WHERE stcd=%s AND tenant_id=%s AND deleted=0 "
            "AND rz IS NOT NULL ORDER BY tm DESC LIMIT %s", (stcd, tenant, n))["data"]
        pre_image = {"table": "st_rsvr_r",
                     "rows": [{"id": r["id"], "rz": float(r["rz"])} for r in rows]}
        if rows:
            ids = [r["id"] for r in rows]
            _execute_write("UPDATE st_rsvr_r SET rz=NULL WHERE id IN (%s)"
                           % ", ".join(["%s"] * len(ids)), ids)
        return {"pre_image": pre_image, "nulled": len(rows)}

    def _do_suppress(self, case, spec):
        """临时软删基线行（如 cron 新鲜预报批），pre-image 记 id+deleted 供 restore。

        没有这一步，陈旧场景会被 cron 每小时刷新的新鲜批次盖过（MAX(FYMDH) 仍新鲜），
        场景形同虚设——2026-09-11 接线时实测 f_rnfl_h 租户18 最新批次当天 19:00。
        """
        from db import execute_query
        table, where = spec["table"], spec["capture_where"]
        rows = execute_query(f"SELECT id, deleted FROM {table} WHERE {where}")["data"]
        pre_image = {"table": table,
                     "rows": [{"id": r["id"], "deleted": r["deleted"]} for r in rows]}
        if rows:
            ids = [r["id"] for r in rows]
            _execute_write(f"UPDATE {table} SET deleted=1 WHERE id IN (%s)"
                           % ", ".join(["%s"] * len(ids)), ids)
        return {"pre_image": pre_image, "suppressed": len(rows)}

    def _restore_rows(self, pre):
        _restore_rows(pre)

    def _flush(self):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2),
                                      encoding="utf-8")


def _restore_rows(pre):
    """按主键 id 回写 pre-image 列（通用：rz / deleted / 任意列）。模块级供 --restore 复用。"""
    table = pre.get("table")
    for r in pre.get("rows", []):
        cols = [k for k in r if k != "id"]
        sets = ", ".join(f"{k}=%s" for k in cols)
        vals = [r[k] for k in cols] + [r["id"]]
        _execute_write(f"UPDATE {table} SET {sets} WHERE id=%s", vals)


def _restore_from_manifest(manifest_path):
    """崩溃/中断后的回滚入口：只处理 pre_image 类条目（其余场景天然幂等/自愈）。"""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    n = 0
    for e in data.get("entries", []):
        if e.get("pre_image") is not None:
            _restore_rows(e["pre_image"])
            n += len(e["pre_image"].get("rows", []))
    print(f"[data_prep] 已回写 {n} 行 pre-image（manifest: {manifest_path}）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="评测场景注入/回滚")
    ap.add_argument("--restore", help="按 fixture_manifest.json 回写 pre-image")
    args = ap.parse_args()
    if args.restore:
        _restore_from_manifest(args.restore)
    else:
        ap.print_help()
