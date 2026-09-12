#!/usr/bin/env python3
"""场景注入层：按题单物化数据前提，manifest 留痕可 --restore（施工图 C2）。

背景：forecasting/data/scenarios/ 下 7 月已建成套错误场景 SQL，但从未接入评测
流程——异常题一直跑在"正常基线"上，前提靠运气。本模块把"场景→题目"映射
（eval/data/scenarios.yaml）接进 runner：每题执行前 setup 注入、判分后 teardown
恢复，全部动作写 manifest（含 pre-image），崩溃后可 --restore 回滚。

场景形态（scenarios.yaml 每项）：
  <name>:
    handler: file | insert_rows | null_rz_latest | suppress
    cases: [题 id...]          # 或在题目 yaml 侧写 fixtures: [<name>]
    exclusive: true            # 改基线表的场景；>EXCLUSIVE_MAX_BATCH 题的批量自动跳过
    teardown: restore | delete_first | cron_refresh | none
    # file:         file: <repo-rel .sql 路径>（可含会话变量，单连接顺序执行）
    # insert_rows:  table + marker_where + rows[{列: 值}]（幂等 DELETE-before-INSERT）
    # null_rz_latest: stcd + tenant_id + rows（主站最新 N 行 rz 置 NULL，pre-image 回写）
    # suppress:     table + capture_where + scope_where（scope 必配！评审 P0#1）

安全纪律（2026-09-12 评审后固化，违反即 error 不落库）：
  - suppress/restore 的 UPDATE 必须带 scope_where（如 tenant_id = 18）。f_rnfl_h
    复合主键 (ID,YMDH,UNITNAME,TYPE) 下裸 id 不唯一——租户 1 有 6946 行 ID=1、
    租户 20 有 168 行，裸 UPDATE 会跨租户误伤/复活。
  - pre-image 捕获按 id 游标分页（execute_query 有 MAX_ROWS=1000 静默截断）。
  - manifest 文件名带时间戳（fixture_manifest-<ts>.json）——固定名会被下一次
    运行覆盖，毁掉崩溃现场唯一的恢复依据。
  - 写入统一走 lib.db_write.execute_write（显式 commit+rollback 的唯一审计写通道；
    lib.db.execute_query 不 commit，写入会静默回滚——2026-09-12 实测）。

用法（run.py 内）：
  prep = Prep(report_dir); prep.validate(已知题id集合)
  fx = prep.setup(case, n_selected); ...; prep.teardown(case)
命令行：
  python3 eval/data_prep.py --restore <fixture_manifest-*.json>
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for p in (str(_REPO / "lib"), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

SCENARIOS_YAML = Path(__file__).parent / "data" / "scenarios.yaml"
EXCLUSIVE_MAX_BATCH = 5   # exclusive 场景仅在 ≤5 题的小批量生效
CHUNK = 500               # 回写分块
CAPTURE_MAX = 20000       # pre-image 单次捕获上限，撞线即拒绝（防截断静默进 manifest）
TEARDOWN_NONE = "none"


def load_scenarios():
    import yaml
    data = yaml.safe_load(SCENARIOS_YAML.read_text(encoding="utf-8")) or {}
    return data.get("fixtures") or {}


def _write(sql, params=None):
    """写入专用：统一走 lib.db_write（commit+rollback）。注意 SQL 文本含字面 %
    （LIKE 'x\\_%'）时不得传空元组——pymysql 会对非 None args 做 % 格式化。"""
    from lib.db_write import execute_write
    return execute_write(sql, params)


def _capture_all(table, select_cols, where, cap=CAPTURE_MAX):
    """捕获 pre-image 行。绕开 execute_query 的 MAX_ROWS=1000 静默截断（评审 P0#4）：
    其 max_rows 参数被 min(max_rows, MAX_ROWS) 封死，抬不上去，故直连池连接 fetchall。
    撞 cap 即报错拒绝——截断的 pre-image 意味着 --restore 无法完整回写。
    注意不用 id 游标分页：f_rnfl_h 等复合主键表 id 不唯一（ID=1 有 695 行），
    `id > last` 会整页跳过同 id 余行（2026-09-12 实测 910 行只捕到 715）。"""
    from lib.db import get_connection, _serialize_row
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {select_cols} FROM {table} WHERE {where}")  # args=None → 不做 % 格式化
            rows = cur.fetchall()
    finally:
        conn.close()   # 只读查询无需 commit；池连接 close=归还
    if len(rows) >= cap:
        raise ValueError(f"{table} 捕获行数撞上限 {cap}——capture_where 过宽，缩小范围后重试（防 pre-image 截断）")
    return [_serialize_row(r) for r in rows]   # bytes/datetime → JSON 可序列化（manifest 依赖）


class Prep:
    def __init__(self, report_dir):
        self.scenarios = load_scenarios()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        # 评审 P0#7：带时间戳——固定名会被下次运行覆盖，毁掉崩溃现场的恢复依据
        self.manifest_path = Path(report_dir) / f"fixture_manifest-{ts}.json"
        self.manifest = {"started": datetime.now().isoformat(timespec="seconds"),
                         "entries": []}
        self._by_case = {}   # case_id -> [entry]

    # ---- 接线校验 --------------------------------------------------------
    def validate(self, known_case_ids):
        """场景 cases 引用了不存在的题 id = typo 静默失联（场景永远不触发），启动时告警。"""
        for name, spec in self.scenarios.items():
            for cid in spec.get("cases") or []:
                if cid not in known_case_ids:
                    print(f"[data_prep][WARN] 场景 {name} 引用了不存在的题 id: {cid}（typo?）",
                          flush=True)

    # ---- manifest 持久化 ---------------------------------------------------
    def _flush(self):
        """每条 entry 落盘一次——崩溃时 manifest 反映到条目级粒度。"""
        _flush_to(self.manifest_path, self.manifest)

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
        """题目判分后调用。restore/delete_first 就地恢复；cron_refresh 交给下轮 --roll/--forecast。
        run.py 在 finally 中无条件调用（setup 中途异常也要恢复已 applied 的部分）。"""
        for entry in self._by_case.get(case.id, []):
            if entry.get("status") != "applied":
                continue
            spec = self.scenarios[entry["fixture"]]
            td = spec.get("teardown", TEARDOWN_NONE)
            try:
                if td == "restore" and entry.get("pre_image") is not None:
                    matched, expected = _restore_rows(entry["pre_image"])
                    entry["teardown"] = f"restored {matched}/{expected}"
                    if matched != expected:
                        entry["teardown_anomaly"] = (f"回写 {matched}/{expected} 行——差额行已被硬删或"
                                                     "值被外部改动，见 manifest")
                elif td == "delete_first":
                    _write(f"DELETE FROM {spec['table']} WHERE {spec['marker_where']}")
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
        from lib.db import get_connection   # 与 truth.py 同一 pool 实例（勿用顶层 db，会双池）
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
                    cur.execute(stmt)   # 单参调用（args=None）→ pymysql 不做 % 格式化
                affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return {"file": spec["file"], "statements": len(stmts), "last_affected": int(affected)}

    def _do_insert_rows(self, case, spec):
        _write(f"DELETE FROM {spec['table']} WHERE {spec['marker_where']}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in spec["rows"]:
            cols = {**row}
            vals = [now if v == "NOW" else v for v in cols.values()]
            ph = ", ".join(["%s"] * len(cols))
            _write(f"INSERT INTO {spec['table']} ({', '.join(cols)}) VALUES ({ph})", vals)
        return {"table": spec["table"], "rows": len(spec["rows"])}

    def _do_null_rz_latest(self, case, spec):
        """主站最新 N 行 rz 置 NULL；pre-image（id+rz+scope）存 manifest 供 restore 回写。"""
        stcd, tenant, n = spec["stcd"], spec["tenant_id"], int(spec["rows"])
        rows = _capture_all(
            "st_rsvr_r", "id, rz",
            f"stcd='{stcd}' AND tenant_id={tenant} AND deleted=0 AND rz IS NOT NULL")[:n]
        scope = f"stcd='{stcd}' AND tenant_id={tenant}"
        pre_image = {"table": "st_rsvr_r", "scope_where": scope,
                     "rows": [{"id": r["id"], "rz": float(r["rz"])} for r in rows]}
        if rows:
            ids = [r["id"] for r in rows]
            _write(f"UPDATE st_rsvr_r SET rz=NULL WHERE id IN ({', '.join(['%s'] * len(ids))}) AND {scope}", ids)
        return {"pre_image": pre_image, "nulled": len(rows)}

    def _do_suppress(self, case, spec):
        """临时软删基线行（如 cron 新鲜预报批），pre-image 记 id+deleted 供 restore。

        scope_where 必配：回写与软删的 UPDATE 都要带它限定租户/标记边界——
        f_rnfl_h 下裸 id 不唯一（租户 1 有 6946 行 ID=1），裸 UPDATE 跨租户误伤。
        没有本 handler，陈旧场景会被 cron 每 50min 刷新的新鲜批次盖过
        （MAX(FYMDH) 仍新鲜），场景形同虚设。
        """
        if "scope_where" not in spec:
            raise ValueError("suppress 场景必配 scope_where（防跨租户误伤，评审 P0#1）")
        table = spec["table"]
        rows = _capture_all(table, "id, deleted", spec["capture_where"])
        scope = spec["scope_where"]
        pre_image = {"table": table, "scope_where": scope,
                     "rows": [{"id": r["id"], "deleted": r["deleted"]} for r in rows]}
        for i in range(0, len(rows), CHUNK):
            ids = [r["id"] for r in rows[i:i + CHUNK]]
            _write(f"UPDATE {table} SET deleted=1 WHERE id IN ({', '.join(['%s'] * len(ids))}) AND {scope}",
                   ids)
        return {"pre_image": pre_image, "suppressed": len(rows)}


def _restore_rows(pre):
    """按主键 id 批量回写 pre-image 列，附 scope_where 限定（评审 P0#1）。

    返回 (matched, expected)：matched 按 pre-image 值回查计数（f_rnfl_h 复合主键下
    id 不唯一，UPDATE rowcount 会重复/漏计——2026-09-12 实测 IN(1×500) 命中 695 行），
    matched != expected = 差额行被硬删/外部改动，调用方告警。
    兼容旧格式（无 scope_where）：按 id 裸回写并打 WARN。
    """
    from lib.db import execute_query
    from lib.db_write import execute_write
    table = pre.get("table")
    scope = pre.get("scope_where")
    rows = pre.get("rows", [])
    expected = len(rows)
    if not rows:
        return 0, 0
    if not scope:
        print(f"[data_prep][WARN] {table} pre-image 无 scope_where（旧格式）——按 id 裸回写，有跨租户风险", flush=True)
    # 按列值签名分组：同签名合并成一条 UPDATE（SET k=%s ... WHERE id IN (...)）
    groups = defaultdict(list)
    for r in rows:
        sig = tuple((k, r[k]) for k in r if k != "id")
        groups[sig].append(r["id"])
    where_scope = f" AND {scope}" if scope else ""
    matched = 0
    for sig, ids in groups.items():
        cols = [k for k, _ in sig]
        sets = ", ".join(f"{k}=%s" for k in cols)
        base_vals = [v for _, v in sig]
        uniq_ids = sorted(set(ids))   # 复合主键表同一 id 承载多行，IN 去重防重复命中
        for i in range(0, len(uniq_ids), CHUNK):
            chunk = uniq_ids[i:i + CHUNK]
            execute_write(
                f"UPDATE {table} SET {sets} WHERE id IN ({', '.join(['%s'] * len(chunk))}){where_scope}",
                base_vals + chunk)
        # 回查验证：scope + id IN + pre-image 值全匹配的行数（id 分块计数防超长 IN）
        for i in range(0, len(uniq_ids), CHUNK):
            chunk = uniq_ids[i:i + CHUNK]
            conds = " AND ".join([f"{k}=%s" for k in cols]
                                 + [f"id IN ({', '.join(['%s'] * len(chunk))})"])
            cnt = execute_query(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {conds}{where_scope}",
                base_vals + chunk)["data"][0]["n"]
            matched += int(cnt)
    return matched, expected


def _flush_to(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _restore_from_manifest(manifest_path):
    """崩溃/中断后的回滚入口：只处理 pre_image 类条目（其余场景天然幂等/自愈）。
    matched != expected 的条目如实上报并以退出码 1 收场（差额行多半被 cron 硬删，
    对 COMMENTS='MOCK' 的 cron 批会由下个 tick 自愈重写，其余需人工核对）。"""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    total_matched = total_expected = anomalies = 0
    for e in data.get("entries", []):
        if e.get("pre_image") is None:
            continue
        matched, expected = _restore_rows(e["pre_image"])
        total_matched += matched
        total_expected += expected
        tag = f"{e.get('case')}/{e.get('fixture')}"
        if matched == expected:
            print(f"  [restore] {tag}: {matched}/{expected} 行已回写")
        else:
            anomalies += 1
            print(f"  [restore][WARN] {tag}: 仅 {matched}/{expected} 行命中——差额行被硬删或已变更，需人工核对")
    print(f"[data_prep] 回写完成 {total_matched}/{total_expected} 行"
          f"（anomalies={anomalies}, manifest: {manifest_path}）")
    return anomalies


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="评测场景注入/回滚")
    ap.add_argument("--restore", help="按 fixture_manifest-<ts>.json 回写 pre-image")
    args = ap.parse_args()
    if args.restore:
        sys.exit(1 if _restore_from_manifest(args.restore) else 0)
    ap.print_help()
