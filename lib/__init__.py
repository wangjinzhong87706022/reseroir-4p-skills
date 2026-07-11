"""
SmartTwinRes Skills 共享库

提供统一的数据库连接、查询、序列化、过滤规则等功能。
所有 SmartTwinRes Skill 都应从此库导入 DB 相关功能,避免重复实现。

标准文档: docs/db-credential-config.md
"""

from .db import (
    DB_CONFIG,
    get_connection,
    execute_query,
    execute_query_list,
    unpack,
    _require_env,
    MAX_ROWS,
    query_one,
    execute_write,
)

from .filters import (
    TENANT_ID_FILTER_TABLES,
    DELETED_FILTER_TABLES,
    LARGE_TABLES,
    apply_tenant_filter,
    apply_deleted_filter,
    apply_table_filters,
    validate_table_filter,
    generate_where_clause,
)

__all__ = [
    # DB 连接和查询
    'DB_CONFIG',
    'get_connection',
    'execute_query',
    'execute_query_list',
    'unpack',
    '_require_env',
    'MAX_ROWS',
    'query_one',
    'execute_write',
    # 表过滤规则
    'TENANT_ID_FILTER_TABLES',
    'DELETED_FILTER_TABLES',
    'LARGE_TABLES',
    'apply_tenant_filter',
    'apply_deleted_filter',
    'apply_table_filters',
    'validate_table_filter',
    'generate_where_clause',
]

