#!/usr/bin/env python3
"""
SmartTwinRes Skills 水库身份（租户）解析

本模块是全仓库唯一的"当前水库是谁"判断入口。
所有 tenant_id 的取值都应经由此处，禁止在业务代码里硬编码 18。

身份来源（按优先级）：
  1. 显式传入的参数（函数调用时传 tenant_id=...）
  2. 环境变量 SRM_TENANT_ID（部署实例级配置，每水库一套）
  3. 默认回退 18（三岔水库，保证现网不设 env 时行为不变）

独立部署形态下，每个水库一套独立数据库 + 独立服务实例，
通过 SRM_RESERVOIR_NAME / SRM_TENANT_ID 两个环境变量激活对应水库 profile。
"""

import os
from typing import Optional

# ===========================================================================
# 默认值（三岔水库，保证现网不破）
# ===========================================================================

DEFAULT_TENANT_ID = 18
DEFAULT_RESERVOIR_NAME = "sancha"


# ===========================================================================
# 解析函数
# ===========================================================================

def current_tenant_id() -> int:
    """
    当前租户 ID（水库身份）。

    读 SRM_TENANT_ID 环境变量，缺失回退 18（三岔）。
    非法值（非整数）回退默认值并保持健壮。
    """
    raw = os.getenv("SRM_TENANT_ID")
    if raw is None or raw.strip() == "":
        return DEFAULT_TENANT_ID
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return DEFAULT_TENANT_ID


def current_reservoir_name() -> Optional[str]:
    """
    当前水库 profile 名（如 "sancha" / "taoqupo"）。

    读 SRM_RESERVOIR_NAME 环境变量，缺失返回 None。
    用于知识层 references/reservoirs/{name}/ 路由。
    返回值统一小写、去首尾空白。
    """
    raw = os.getenv("SRM_RESERVOIR_NAME")
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower()


def resolve_reservoir_name(explicit: Optional[str] = None) -> str:
    """显式传入优先，否则环境变量，否则默认 sancha。"""
    if explicit:
        return explicit.strip().lower()
    return current_reservoir_name() or DEFAULT_RESERVOIR_NAME


def resolve_tenant(explicit: Optional[int] = None) -> int:
    """
    统一的 tenant_id 兜底：显式参数 > 环境变量 > 默认 18。

    供所有"函数可显式传 tenant"的场景使用：
        def query_xxx(tenant_id=None):
            tid = resolve_tenant(tenant_id)
    """
    if explicit is not None:
        return explicit
    return current_tenant_id()


# ===========================================================================
# 导出
# ===========================================================================

__all__ = [
    'DEFAULT_TENANT_ID',
    'DEFAULT_RESERVOIR_NAME',
    'current_tenant_id',
    'current_reservoir_name',
    'resolve_reservoir_name',
    'resolve_tenant',
]
