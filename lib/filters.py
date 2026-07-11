#!/usr/bin/env python3
"""
SmartTwinRes Skills 表过滤规则库

提供 tenant_id / deleted 自动过滤功能,确保数据隔离和软删除规则统一应用。

标准文档: docs/shared-tables.md
"""

from typing import List, Optional, Tuple

# ===========================================================================
# 表过滤规则配置
# ===========================================================================

# tenant_id 过滤规则
TENANT_ID_FILTER_TABLES = {
    'st_rsvr_r': {'filter': True, 'value': 18},
    'st_pptn_r': {'filter': True, 'value': 18},
    'srm_flood_history_base': {'filter': True, 'value': 18},
    'model_result_files': {'filter': True, 'value': 18},
    'ew_info_message': {'filter': False},  # 告警跨租户,不强制
    # 以下表无 tenant_id 列
    'f_rnfl_h': {'filter': False},
    'weather_warn': {'filter': False},
    'weather_info': {'filter': False},
    'att_res_flse_lim': {'filter': False},
}

# deleted 过滤规则
DELETED_FILTER_TABLES = {
    'st_rsvr_r': True,
    'st_pptn_r': True,
    'srm_flood_history_base': True,
    'ew_info_message': True,
    'f_rnfl_h': True,
    'weather_info': True,
    # 以下表无 deleted 列
    'model_result_files': False,
    'weather_warn': False,
    'att_res_flse_lim': False,
}

# 大表判定 (必须加时间范围)
LARGE_TABLES = {
    'st_rsvr_r': {'time_column': 'tm', 'min_rows': 100000},
    'st_pptn_r': {'time_column': 'tm', 'min_rows': 100000},
    'f_rnfl_h': {'time_column': 'ymdh', 'min_rows': 10000},
}

# ===========================================================================
# 过滤函数
# ===========================================================================

def apply_tenant_filter(
    sql: str,
    table_name: str,
    tenant_id: Optional[int] = None
) -> str:
    """
    根据表名自动添加 tenant_id 过滤条件。

    Args:
        sql: 原始 SQL (不含 WHERE 子句)
        table_name: 表名 (不含 FROM 关键字,支持带别名的表,如 'st_rsvr_r r')
        tenant_id: 强制指定的 tenant_id 值 (可选,默认从配置读)

    Returns:
        添加 tenant_id 过滤后的 SQL

    Examples:
        >>> sql = "SELECT * FROM st_rsvr_r WHERE deleted = 0"
        >>> apply_tenant_filter(sql, 'st_rsvr_r')
        "SELECT * FROM st_rsvr_r WHERE deleted = 0 AND tenant_id = 18"

        >>> sql = "SELECT * FROM f_rnfl_h WHERE deleted = 0"
        >>> apply_tenant_filter(sql, 'f_rnfl_h')
        "SELECT * FROM f_rnfl_h WHERE deleted = 0"  # 无 tenant_id 列,不加过滤
    """
    # 提取表名 (去除别名)
    base_table = table_name.split()[0].strip()

    # 检查是否需要 tenant_id 过滤
    rule = TENANT_ID_FILTER_TABLES.get(base_table, {'filter': False})
    if not rule['filter']:
        return sql

    # 获取 tenant_id 值
    tid = tenant_id if tenant_id is not None else rule.get('value', 18)

    # 判断 WHERE 子句位置
    sql_upper = sql.upper().strip()

    if 'WHERE' in sql_upper:
        # 已有 WHERE 子句 → 追加 AND
        return f"{sql} AND tenant_id = {tid}"
    else:
        # 无 WHERE 子句 → 新增 WHERE
        # 检查是否有 GROUP BY / ORDER BY / LIMIT
        for keyword in ['GROUP BY', 'ORDER BY', 'LIMIT']:
            if keyword in sql_upper:
                insert_pos = sql_upper.index(keyword)
                return f"{sql[:insert_pos]} WHERE tenant_id = {tid} {sql[insert_pos:]}"

        # 无其他关键字 → 直接在末尾添加
        return f"{sql} WHERE tenant_id = {tid}"


def apply_deleted_filter(
    sql: str,
    table_name: str
) -> str:
    """
    根据表名自动添加 deleted = 0 过滤条件。

    Args:
        sql: 原始 SQL (不含 WHERE 子句)
        table_name: 表名 (不含 FROM 关键字)

    Returns:
        添加 deleted 过滤后的 SQL

    Examples:
        >>> sql = "SELECT * FROM st_rsvr_r"
        >>> apply_deleted_filter(sql, 'st_rsvr_r')
        "SELECT * FROM st_rsvr_r WHERE deleted = 0"

        >>> sql = "SELECT * FROM model_result_files"
        >>> apply_deleted_filter(sql, 'model_result_files')
        "SELECT * FROM model_result_files"  # 无 deleted 列,不加过滤
    """
    base_table = table_name.split()[0].strip()

    # 检查是否需要 deleted 过滤
    if not DELETED_FILTER_TABLES.get(base_table, False):
        return sql

    # 判断 WHERE 子句位置
    sql_upper = sql.upper().strip()

    if 'WHERE' in sql_upper:
        return f"{sql} AND deleted = 0"
    else:
        # 无 WHERE 子句 → 新增 WHERE
        for keyword in ['GROUP BY', 'ORDER BY', 'LIMIT']:
            if keyword in sql_upper:
                insert_pos = sql_upper.index(keyword)
                return f"{sql[:insert_pos]} WHERE deleted = 0 {sql[insert_pos:]}"

        return f"{sql} WHERE deleted = 0"


def apply_table_filters(
    sql: str,
    table_name: str,
    tenant_id: Optional[int] = None,
    apply_tenant: bool = True,
    apply_deleted: bool = True
) -> str:
    """
    根据表名自动添加 tenant_id 和 deleted 过滤条件 (一站式过滤)。

    Args:
        sql: 原始 SQL
        table_name: 表名 (支持带别名,如 'st_rsvr_r r')
        tenant_id: 强制指定的 tenant_id 值 (可选)
        apply_tenant: 是否应用 tenant_id 过滤 (默认 True)
        apply_deleted: 是否应用 deleted 过滤 (默认 True)

    Returns:
        添加过滤后的 SQL

    Examples:
        >>> sql = "SELECT rz, inq, otq, w, tm FROM st_rsvr_r ORDER BY tm DESC LIMIT 1"
        >>> apply_table_filters(sql, 'st_rsvr_r')
        "SELECT rz, inq, otq, w, tm FROM st_rsvr_r WHERE tenant_id = 18 AND deleted = 0 ORDER BY tm DESC LIMIT 1"
    """
    if apply_tenant:
        sql = apply_tenant_filter(sql, table_name, tenant_id)
    if apply_deleted:
        sql = apply_deleted_filter(sql, table_name)
    return sql


def validate_table_filter(
    table_name: str
) -> Tuple[bool, bool, str]:
    """
    验证表名的过滤规则,返回 (need_tenant_filter, need_deleted_filter, message)。

    Args:
        table_name: 表名

    Returns:
        (是否需 tenant 过滤, 是否需 deleted 过滤, 说明信息)

    Examples:
        >>> validate_table_filter('st_rsvr_r')
        (True, True, 'tenant_id=18, deleted=0')

        >>> validate_table_filter('model_result_files')
        (True, False, 'tenant_id=18, 无 deleted 列')
    """
    base_table = table_name.split()[0].strip()

    need_tenant = TENANT_ID_FILTER_TABLES.get(base_table, {}).get('filter', False)
    need_deleted = DELETED_FILTER_TABLES.get(base_table, False)

    messages = []
    if need_tenant:
        tid = TENANT_ID_FILTER_TABLES[base_table].get('value', 18)
        messages.append(f"tenant_id={tid}")
    else:
        messages.append("无 tenant_id 列,不过滤")

    if need_deleted:
        messages.append("deleted=0")
    else:
        messages.append("无 deleted 列,不过滤")

    return (need_tenant, need_deleted, ', '.join(messages))


# ===========================================================================
# 快捷工具: 根据表名生成 WHERE 子句
# ===========================================================================

def generate_where_clause(
    table_name: str,
    extra_conditions: Optional[List[str]] = None,
    tenant_id: Optional[int] = None
) -> str:
    """
    根据表名自动生成完整的 WHERE 子句 (tenant_id + deleted + 额外条件)。

    Args:
        table_name: 表名
        extra_conditions: 额外的 WHERE 条件列表 (可选)
        tenant_id: 强制指定的 tenant_id 值 (可选)

    Returns:
        生成的 WHERE 子句 (含 'WHERE' 关键字)

    Examples:
        >>> generate_where_clause('st_rsvr_r', extra_conditions=['tm >= NOW() - INTERVAL 24 HOUR'])
        'WHERE tenant_id = 18 AND deleted = 0 AND tm >= NOW() - INTERVAL 24 HOUR'
    """
    base_table = table_name.split()[0].strip()

    conditions = []

    # tenant_id 过滤
    rule = TENANT_ID_FILTER_TABLES.get(base_table, {})
    if rule.get('filter', False):
        tid = tenant_id if tenant_id is not None else rule.get('value', 18)
        conditions.append(f"tenant_id = {tid}")

    # deleted 过滤
    if DELETED_FILTER_TABLES.get(base_table, False):
        conditions.append("deleted = 0")

    # 额外条件
    if extra_conditions:
        conditions.extend(extra_conditions)

    if not conditions:
        return ""

    return "WHERE " + " AND ".join(conditions)


# ===========================================================================
# 导出
# ===========================================================================

__all__ = [
    'TENANT_ID_FILTER_TABLES',
    'DELETED_FILTER_TABLES',
    'LARGE_TABLES',
    'apply_tenant_filter',
    'apply_deleted_filter',
    'apply_table_filters',
    'validate_table_filter',
    'generate_where_clause',
]
