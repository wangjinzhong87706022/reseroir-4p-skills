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

    连接生命周期 = 进程生命周期（runner 是短命 CLI，退出即释放，故不提供 close）。
    若将来被长驻服务复用，须改为返回可关闭句柄或每次 connect（评审 P2 决策：暂不改造）。
    """
    conn = _connect(env)

    def _q(sql):
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    return _q
