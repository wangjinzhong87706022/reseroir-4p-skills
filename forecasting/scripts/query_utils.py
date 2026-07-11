#!/usr/bin/env python3
"""
query_utils.py -- 向后兼容层,从 SmartTwinRes-skills/lib/db.py 重新导出。

注意: 此文件保留用于向后兼容。
新代码应直接从 lib.db 导入:
    from lib.db import execute_query, execute_query_list, unpack

共享库: SmartTwinRes-skills/lib/db.py
标准文档: docs/db-credential-config.md
"""
import os
import sys

# 让脚本既能 `python3 scripts/query_utils.py` 又能被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# 从统一共享库导入所有功能
from lib.db import (  # noqa: E402
    DB_CONFIG,
    _require_env,
    _get_pool,
    get_connection,
    _serialize_value,
    _serialize_row,
    MAX_ROWS,
    execute_query,
    execute_query_list,
    unpack,
    query_one,
    execute_write,
)

# 重新导出所有符号,保持向后兼容
__all__ = [
    'DB_CONFIG',
    '_require_env',
    '_get_pool',
    'get_connection',
    '_serialize_value',
    '_serialize_row',
    'MAX_ROWS',
    'execute_query',
    'execute_query_list',
    'unpack',
    'query_one',
    'execute_write',
]
