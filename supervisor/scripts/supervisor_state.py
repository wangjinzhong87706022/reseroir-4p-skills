#!/usr/bin/env python3
"""
supervisor_state.py -- Supervisor 全局 State 持久化（SQLite，支持断点续跑）。

用法:
    # 新建事件
    python3 scripts/supervisor_state.py new --scene A --trigger "暴雨预警" [--risk 高]
    # 写入某阶段结果
    python3 scripts/supervisor_state.py set --event A-20260805-001 --stage step4 \
        --agent simulation --result '{"max_level": 787.1}' [--status ok]
    # 读事件全貌
    python3 scripts/supervisor_state.py get --event A-20260805-001
    # 列出未完成阶段（断点续跑）
    python3 scripts/supervisor_state.py resume --event A-20260805-001
    # 更新事件状态/风险
    python3 scripts/supervisor_state.py status --event A-20260805-001 --status awaiting_approval [--risk 高]
    # 列出事件
    python3 scripts/supervisor_state.py list [--scene A] [--limit 10]

表结构:
    events        事件主表 (event_id, scene, status, risk_level, trigger, created_at, updated_at)
    stage_results 阶段结果表 (event_id, stage, agent, result_json, status, ts)

设计原则:
    1. event_id 格式: {scene}-{YYYYMMDD}-{3位序号}，如 A-20260805-001。
    2. stage 命名: step1..stepN（对齐 DAG 步骤），或 stage_ 前缀自由命名。
    3. 所有阶段结果以 JSON 存 result_json，读取方自行解析，不在此做业务判断。
    4. status 取值: running | awaiting_approval | done | aborted（事件级）；
       pending | ok | skipped | error（阶段级）。
    5. SQLite 文件位置: supervisor/state/supervisor_state.db（可由 SRM_STATE_DIR 覆盖）。
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ===========================================================================
# 配置
# ===========================================================================

DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def _state_dir() -> Path:
    """State 目录（环境变量 SRM_STATE_DIR 可覆盖，便于多水库隔离）"""
    env = os.getenv("SRM_STATE_DIR")
    if env:
        return Path(env)
    return DEFAULT_STATE_DIR


def _db_path() -> Path:
    d = _state_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "supervisor_state.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id    TEXT PRIMARY KEY,
            scene       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'running',
            risk_level  TEXT,
            trigger     TEXT,
            priority    TEXT NOT NULL DEFAULT '中',   -- 高/中/低（优先级队列排序依据）
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stage_results (
            event_id    TEXT NOT NULL,
            stage       TEXT NOT NULL,
            agent       TEXT,
            result_json TEXT,
            status      TEXT NOT NULL DEFAULT 'ok',
            ts          TEXT NOT NULL,
            PRIMARY KEY (event_id, stage)
        );
        CREATE INDEX IF NOT EXISTS idx_stage_event ON stage_results(event_id);
        CREATE INDEX IF NOT EXISTS idx_events_scene ON events(scene);
        """
    )
    # 兼容旧库：events 表已存在但缺 priority 列时补列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "priority" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN priority TEXT NOT NULL DEFAULT '中'")
    conn.commit()


# ===========================================================================
# 事件号生成
# ===========================================================================

def _next_event_seq(conn: sqlite3.Connection, scene: str, today: str) -> str:
    """生成 event_id: {scene}-{YYYYMMDD}-{3位序号}"""
    prefix = f"{scene}-{today}-"
    rows = conn.execute(
        "SELECT event_id FROM events WHERE event_id LIKE ?", (prefix + "%",)
    ).fetchall()
    max_seq = 0
    for r in rows:
        try:
            seq = int(r["event_id"].rsplit("-", 1)[1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ===========================================================================
# 命令实现
# ===========================================================================

def cmd_new(args) -> dict:
    conn = _connect()
    today = datetime.now().strftime("%Y%m%d")
    event_id = _next_event_seq(conn, args.scene, today)
    now = datetime.now().isoformat(timespec="seconds")
    priority = getattr(args, "priority", None) or "中"
    conn.execute(
        "INSERT INTO events (event_id, scene, status, risk_level, trigger, priority, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?, ?, ?, ?)",
        (event_id, args.scene, args.risk, args.trigger, priority, now, now),
    )
    conn.commit()
    conn.close()
    return {"event_id": event_id, "scene": args.scene, "status": "running",
            "priority": priority}


def cmd_queue(args) -> dict:
    """优先级队列：列出未结束事件（running/awaiting_approval），按 优先级(高>中>低) + 创建时间 排序。
    这是"多事件并行"的调度视图——调用方可据此决定先处理哪个事件。"""
    conn = _connect()
    order = {"高": 0, "中": 1, "低": 2}
    rows = conn.execute(
        "SELECT event_id, scene, status, risk_level, trigger, priority, created_at "
        "FROM events WHERE status IN ('running','awaiting_approval') "
        "ORDER BY CASE priority WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, created_at"
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        d["order"] = order.get(d.get("priority"), 1)
        items.append(d)
    return {"queue_size": len(items), "events": items}


def cmd_set(args) -> dict:
    conn = _connect()
    # 校验事件存在
    ev = conn.execute("SELECT event_id FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        conn.close()
        raise SystemExit(f"事件不存在: {args.event}（先用 new 创建）")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR REPLACE INTO stage_results (event_id, stage, agent, result_json, status, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (args.event, args.stage, args.agent, args.result, args.status, now),
    )
    conn.execute("UPDATE events SET updated_at=? WHERE event_id=?", (now, args.event))
    conn.commit()
    conn.close()
    return {"event_id": args.event, "stage": args.stage, "status": args.status}


def cmd_get(args) -> dict:
    conn = _connect()
    ev = conn.execute("SELECT * FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        conn.close()
        raise SystemExit(f"事件不存在: {args.event}")
    stages = conn.execute(
        "SELECT stage, agent, result_json, status, ts FROM stage_results "
        "WHERE event_id=? ORDER BY stage",
        (args.event,),
    ).fetchall()
    conn.close()
    return {
        "event": dict(ev),
        "stages": [dict(s) for s in stages],
    }


def cmd_resume(args) -> dict:
    """列出未完成阶段（断点续跑入口）"""
    conn = _connect()
    ev = conn.execute("SELECT * FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        conn.close()
        raise SystemExit(f"事件不存在: {args.event}")
    if ev["status"] in ("done", "aborted"):
        conn.close()
        return {"event_id": args.event, "status": ev["status"], "pending_stages": [],
                "note": "事件已结束，无需续跑"}
    stages = conn.execute(
        "SELECT stage, agent, status FROM stage_results WHERE event_id=? ORDER BY stage",
        (args.event,),
    ).fetchall()
    # 已完成的 stage 集合
    done_stages = {s["stage"] for s in stages if s["status"] in ("ok", "skipped")}
    # 按 DAG 顺序找第一个未完成的 stage
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from references.dag_order import DAG_ORDER  # 延迟导入，避免循环依赖
    dag = DAG_ORDER.get(ev["scene"], [])
    pending = [s for s in dag if s not in done_stages]
    conn.close()
    return {
        "event_id": args.event,
        "scene": ev["scene"],
        "status": ev["status"],
        "done_stages": sorted(done_stages),
        "pending_stages": pending,
        "next_stage": pending[0] if pending else None,
    }


def cmd_status(args) -> dict:
    conn = _connect()
    ev = conn.execute("SELECT event_id FROM events WHERE event_id=?", (args.event,)).fetchone()
    if not ev:
        conn.close()
        raise SystemExit(f"事件不存在: {args.event}")
    now = datetime.now().isoformat(timespec="seconds")
    if args.risk:
        conn.execute("UPDATE events SET risk_level=? WHERE event_id=?", (args.risk, args.event))
    conn.execute("UPDATE events SET status=?, updated_at=? WHERE event_id=?",
                 (args.status, now, args.event))
    conn.commit()
    conn.close()
    return {"event_id": args.event, "status": args.status, "risk": args.risk}


def cmd_list(args) -> dict:
    conn = _connect()
    sql = "SELECT event_id, scene, status, risk_level, trigger, updated_at FROM events"
    params = []
    if args.scene:
        sql += " WHERE scene=?"
        params.append(args.scene)
    sql += " ORDER BY event_id DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


# ===========================================================================
# main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Supervisor 全局 State 持久化")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="新建事件")
    p_new.add_argument("--scene", required=True, help="场景 A/B/C/D")
    p_new.add_argument("--trigger", default="", help="触发信号")
    p_new.add_argument("--risk", default=None, help="初始风险等级 高/中/低")
    p_new.add_argument("--priority", default="中", choices=["高", "中", "低"],
                       help="事件优先级（高/中/低，队列排序依据）")
    p_new.set_defaults(func=cmd_new)

    p_queue = sub.add_parser("queue", help="优先级队列：未结束事件按优先级排序")
    p_queue.set_defaults(func=cmd_queue)

    p_set = sub.add_parser("set", help="写入阶段结果")
    p_set.add_argument("--event", required=True)
    p_set.add_argument("--stage", required=True, help="如 step1")
    p_set.add_argument("--agent", default="", help="如 forecasting")
    p_set.add_argument("--result", default="{}", help="阶段结果 JSON")
    p_set.add_argument("--status", default="ok", choices=["ok", "skipped", "error"])
    p_set.set_defaults(func=cmd_set)

    p_get = sub.add_parser("get", help="读事件全貌")
    p_get.add_argument("--event", required=True)
    p_get.set_defaults(func=cmd_get)

    p_resume = sub.add_parser("resume", help="列出未完成阶段")
    p_resume.add_argument("--event", required=True)
    p_resume.set_defaults(func=cmd_resume)

    p_status = sub.add_parser("status", help="更新事件状态")
    p_status.add_argument("--event", required=True)
    p_status.add_argument("--status", required=True,
                          choices=["running", "awaiting_approval", "done", "aborted"])
    p_status.add_argument("--risk", default=None, help="风险等级 高/中/低")
    p_status.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="列出事件")
    p_list.add_argument("--scene", default=None)
    p_list.add_argument("--limit", type=int, default=10)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()