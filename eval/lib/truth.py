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
    """延迟导入 pymysql；连接参数读 SRM_DB_* env。可被测试替换。"""
    import pymysql  # 延迟导入：CI 无需安装
    return pymysql.connect(
        host=os.environ.get("SRM_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("SRM_DB_PORT", "3306")),
        user=os.environ.get("SRM_DB_USER", "root"),
        password=os.environ.get("SRM_DB_PASSWORD", ""),
        database=os.environ.get("SRM_DB_NAME", "powerelf_srm_yml"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def make_db_query_fn(env):
    """返回 Callable[[sql:str], list[dict]]。env 仅用于将来按租户切库；当前读全局 SRM_DB_*。"""
    conn = _connect(env)

    def _q(sql):
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    return _q
