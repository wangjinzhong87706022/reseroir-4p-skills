#!/usr/bin/env python3
"""
query_utils.py -- shared database query infrastructure for plan-generation scripts.

Provides:
  - Connection pooling (dbutils.PooledDB) with graceful fallback to single connections
  - Timeout protection (connect_timeout=10s, read_timeout=30s)
  - Result truncation with MAX_ROWS=1000 hard limit
  - Datetime / Decimal / bytes serialization to JSON-safe types
  - Two return modes: execute_query() (dict with metadata) and execute_query_list()
  - unpack() helper to extract data from dict results

DB config comes from environment variables:
  SRM_DB_HOST     (default 127.0.0.1)
  SRM_DB_PORT     (default 3306)
  SRM_DB_NAME     (default powerelf_srm_yml)
  SRM_DB_USER     (REQUIRED — no default; exits if unset)
  SRM_DB_PASSWORD (REQUIRED — no default; exits if unset)
Configure via shell env / systemd; see docs/db-credential-config.md.
"""

import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import pymysql
import pymysql.cursors


def _require_env(name):
    """敏感凭据强制从环境变量读取,无值则报错退出(杜绝硬编码口令)。"""
    val = os.getenv(name)
    if not val:
        sys.exit(
            f"[DB] 环境变量 {name} 未设置。请配置 SRM_DB_* 环境变量后重试"
            f"（见 docs/db-credential-config.md）。"
        )
    return val


# ---------------------------------------------------------------------------
# DB config from environment (host/port/name 留默认; user/password 强制要求)
# ---------------------------------------------------------------------------
DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': _require_env('SRM_DB_USER'),
    'password': _require_env('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 30,
}

# ---------------------------------------------------------------------------
# Connection pool (graceful fallback if dbutils not installed)
# ---------------------------------------------------------------------------
_pool = None


def _get_pool():
    """Return (or lazily create) the connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    try:
        from dbutils.pooled_db import PooledDB
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            **DB_CONFIG,
            cursorclass=pymysql.cursors.DictCursor,
        )
        return _pool
    except ImportError:
        # dbutils not available -- fall back to single-connection mode
        _pool = 'single'
        return _pool


def get_connection():
    """Get a database connection (from pool or freshly created)."""
    pool = _get_pool()
    if pool == 'single':
        return pymysql.connect(
            **DB_CONFIG,
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
MAX_ROWS = 1000


# ---------------------------------------------------------------------------
# Core query functions
# ---------------------------------------------------------------------------

def execute_query(sql, params=None, max_rows=MAX_ROWS):
    """
    Execute a query and return a result dict with metadata.

    Returns:
        {
            'data': list[dict],   # serialised rows
            'count': int,         # number of rows returned
            'truncated': bool,    # True if max_rows limit was hit
        }
    """
    cap = min(max_rows, MAX_ROWS)
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


def execute_query_list(sql, params=None, max_rows=MAX_ROWS):
    """
    Execute a query and return a plain list[dict].

    This is the backward-compatible mode used by existing query_plan_data.py
    and query_plan_analysis.py callers that expect a bare list.

    Returns:
        list[dict]  -- serialised rows
    """
    result = execute_query(sql, params, max_rows)
    return result['data']


def unpack(result):
    """
    Extract the 'data' list from a dict result returned by execute_query().

    If *result* is already a list, return it unchanged (idempotent convenience).
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and 'data' in result:
        return result['data']
    return result
