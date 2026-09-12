"""live_db 真值：纯比较逻辑 + DB query_fn 工厂（端口自 plan-gen eval.py::get_ground_truth）。"""
import os
import re

_NUM_RE = re.compile(r"-?\d+\.?\d*")


def extract_numbers(text):
    return [float(m) for m in _NUM_RE.findall(text or "")]


def compare_with_tolerance(numbers, truth, tolerance):
    passed = any(abs(n - truth) <= tolerance for n in numbers)
    return {"truth": truth, "tolerance": tolerance, "extracted": list(numbers), "passed": passed}


def _connect(env):
    """复用 lib.db 连接：env 解析(SRM_DB_*→POWERELF_DB_*→fail-loud)、
    连接/读取超时、DictCursor 与只读通道完全一致（评审 C1：消除双份连接
    逻辑与 root/空密码弱默认）。保留本函数作为测试接缝。"""
    from lib.db import get_connection  # 延迟导入：CI 无 DB/未装 pymysql 时不必引入
    return get_connection()


def make_db_query_fn(env):
    """返回 Callable[[sql:str], list[dict]]。env 仅用于将来按租户切库；当前读全局 SRM_DB_*。

    连接策略（评审 P0#5, 2026-09-12）：每次查询从池 checkout → 读完 commit → 归还。
    旧实现整跑持有同一连接且从不 commit——InnoDB REPEATABLE READ 下读视图冻结在
    T0，长跑期间数据再生成（cron 每 50min roll）对真值查询不可见 → 漂移假 FAIL；
    且单连接撞上 wait_timeout(8h) 直接断连无自愈。checkout/归还经池的 ping 自愈。
    """
    def _q(sql):
        conn = _connect(env)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            conn.commit()   # 释放读视图+行锁，下一查询取新快照
            return rows
        finally:
            conn.close()    # DBUtils 池连接的 close() = 归还而非断开

    return _q
