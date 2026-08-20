#!/usr/bin/env python3
"""
db_write.py -- 显式受控的 DB 写通道（INSERT/UPDATE/DELETE）。

本模块是全仓唯一的写能力出口，仅供 forecasting/data/ 造数脚本
（generate_sancha_data.py / generate_taoqupo_data.py）在测试环境灌/清 mock 数据使用。

纪律（与 docs/统一共享层设计-20260807.md 一致）:
    1. 只读 skill 脚本（*/scripts/ 下任何文件）禁止 import 本模块；
       lib.db 保持纯只读（SELECT/SHOW/DESCRIBE）。
    2. 写 SQL 同样必须参数化 %s，禁止 f-string/format 拼接值。
    3. DELETE/UPDATE 的 WHERE 必须同时带 mock 标记与 tenant_id，
       防止误删他库生产行（评审 S1 + 勘误：原 lib.db.execute_write
       由 forecasting/data 两脚本共 9 处调用，2026-08-20 剥离至此）。
"""
from lib.db import get_connection  # 连接层复用：env 解析/池化/超时与只读通道一致

__all__ = ['execute_write']


def execute_write(sql, params=None):
    """
    Execute an INSERT/UPDATE/DELETE statement and return affected rows.

    Args:
        sql: SQL statement（%s 参数化）
        params: Query parameters

    Returns:
        int -- number of affected rows
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            rows = cursor.execute(sql, params)
            conn.commit()
            return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
