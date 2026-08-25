#!/usr/bin/env python3
"""
SmartTwinRes Skills 统一数据库连接库

所有 SmartTwinRes Skill 共享此库,避免重复实现 DB_CONFIG。
支持双命名空间:
  - SRM_DB_* (SmartTwinRes 家族,主命名空间)
  - POWERELF_DB_* (powerelf 家族,fallback)

标准文档: shared/db-connection.md

版本: 1.0
维护: SmartTwinRes Team
"""

import os
import sys
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal

import pymysql
import pymysql.cursors

__all__ = [
    'DB_CONFIG', 'get_connection', 'execute_query', 'execute_query_list',
    'unpack', 'require_env', 'MAX_ROWS'
]


def _require_env(name):
    """敏感凭据强制从环境变量读取,无值则报错退出(杜绝硬编码口令)。"""
    val = os.getenv(name)
    if not val:
        sys.exit(
            f"[DB] 环境变量 {name} 未设置。请配置 SRM_DB_* 环境变量后重试"
            f"（见 shared/db-connection.md）。"
        )
    return val


# P3-3: 公开别名（无下划线），供 __all__ 导出
require_env = _require_env


# ---------------------------------------------------------------------------
# DB config lazy build (P2: 延迟到首连解析，import 无 sys.exit)
# 命名空间优先级: SRM_DB_* → POWERELF_DB_* → 默认值
# ---------------------------------------------------------------------------
DB_CONFIG = None  # 模块加载时不解析凭据，首连时由 _ensure_db_config() 构造


def _ensure_db_config():
    """首连时构造 DB_CONFIG（凭据延迟解析，生产仍 fail-loud）。

    import 期不触发 _require_env→sys.exit，使无 DB 环境的单测可 import；
    生产首连仍缺凭据即 sys.exit，保持 fail-loud 安全。
    """
    global DB_CONFIG
    if DB_CONFIG is not None:
        return DB_CONFIG
    DB_CONFIG = {
        'host': os.getenv('SRM_DB_HOST') or os.getenv('POWERELF_DB_HOST', '127.0.0.1'),
        'port': int(os.getenv('SRM_DB_PORT') or os.getenv('POWERELF_DB_PORT', '3306')),
        'user': os.getenv('SRM_DB_USER') or os.getenv('POWERELF_DB_USER') or _require_env('SRM_DB_USER'),
        'password': os.getenv('SRM_DB_PASSWORD') or os.getenv('POWERELF_DB_PASSWORD') or _require_env('SRM_DB_PASSWORD'),
        'database': os.getenv('SRM_DB_NAME') or os.getenv('POWERELF_DB_NAME', 'powerelf_srm_yml'),
        'charset': 'utf8mb4',
        'connect_timeout': 10,  # 连接超时: 10 秒
        'read_timeout': 30,     # 读取超时: 30 秒
    }
    return DB_CONFIG

# ---------------------------------------------------------------------------
# Connection pool (graceful fallback if dbutils not installed)
# ---------------------------------------------------------------------------
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """Return (or lazily create) the connection pool (thread-safe)."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:  # 双重检查锁定，防并发首调创建多个 PooledDB
        if _pool is not None:
            return _pool
        config = _ensure_db_config()  # P2: 凭据延迟解析，首连时 fail-loud
        try:
            from dbutils.pooled_db import PooledDB
            _pool = PooledDB(
                creator=pymysql,
                maxconnections=10,  # 2026-08-25: 5→10，修复高并发连接耗尽问题
                **config,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except ImportError:
            # dbutils not available -- fall back to single-connection mode
            _pool = 'single'
        return _pool


def get_connection():
    """Get a database connection (from pool or freshly created)."""
    pool = _get_pool()
    config = _ensure_db_config()
    if pool == 'single':
        return pymysql.connect(
            **config,
            cursorclass=pymysql.cursors.DictCursor,
        )
    return pool.connection()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialize_value(value):
    """Convert a single value to a JSON-safe type."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        # For bitwise values, return integer; otherwise decode as utf-8
        try:
            return int.from_bytes(value, 'big')
        except Exception:
            return value.decode('utf-8', errors='replace')
    # Handle objects with __float__ (e.g. numpy scalars) but skip strings
    if not isinstance(value, (str, int, float, bool)) and hasattr(value, '__float__'):
        try:
            return float(value)
        except Exception:
            pass
    return value


def _serialize_row(row):
    """Apply JSON-safe serialization to every field in a dict row."""
    return {k: _serialize_value(v) for k, v in row.items()}


# ---------------------------------------------------------------------------
# Max rows hard limit
# ---------------------------------------------------------------------------

def _load_max_rows() -> int:
    """全局行数上限：优先读 SRM_DB_MAX_ROWS 环境变量（运维可调），非法值回退 1000。"""
    raw = os.getenv('SRM_DB_MAX_ROWS')
    if not raw:
        return 1000
    try:
        return max(1, int(raw.strip()))
    except (TypeError, ValueError):
        return 1000


MAX_ROWS = _load_max_rows()


# ---------------------------------------------------------------------------
# Core query functions
# ---------------------------------------------------------------------------

def execute_query(sql, params=None, max_rows=None):
    """
    Execute a query and return a result dict with metadata.

    Args:
        sql: SQL query string with %s placeholders
        params: Query parameters (tuple or dict)
        max_rows: Maximum rows to return (capped at MAX_ROWS; None → MAX_ROWS)
    """
    # P3-2: 延迟读 MAX_ROWS，避免 import 时绑定导致 SRM_DB_MAX_ROWS 不生效
    effective_max = MAX_ROWS if max_rows is None else min(max_rows, MAX_ROWS)
    cap = effective_max
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchmany(cap + 1)
            truncated = len(rows) > cap
            if truncated:
                rows = rows[:cap]
            data = [_serialize_row(r) for r in rows]
            return {
                'data': data,
                'count': len(data),
                'truncated': truncated,
            }
    finally:
        conn.close()


def execute_query_list(sql, params=None, max_rows=None):
    """
    Execute a query and return a plain list[dict].

    This is the backward-compatible mode used by existing callers that expect a bare list.

    Args:
        sql: SQL query string with %s placeholders
        params: Query parameters (tuple or dict)
        max_rows: Maximum rows to return (capped at MAX_ROWS)

    Returns:
        list[dict]  -- serialised rows
    """
    result = execute_query(sql, params, max_rows)
    return result['data']


def unpack(result):
    """
    Extract the 'data' list from a dict result returned by execute_query().

    If *result* is already a list, return it unchanged (idempotent convenience).

    Args:
        result: Result from execute_query() or a plain list

    Returns:
        list[dict] -- the data list
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and 'data' in result:
        return result['data']
    return result


# ---------------------------------------------------------------------------
# Utility: Query single value
# ---------------------------------------------------------------------------

def query_one(sql, params=None):
    """
    Execute a query and return a single value (first row, first column).

    Useful for scalar queries like COUNT(*), MAX(), etc.

    Args:
        sql: SQL query string
        params: Query parameters

    Returns:
        Single value or None
    """
    result = execute_query(sql, params, max_rows=1)
    data = unpack(result)
    if data:
        return list(data[0].values())[0]
    return None
