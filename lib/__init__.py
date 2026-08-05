"""
SmartTwinRes-skills 共享库

提供：
- tenant.py: 水库身份（租户）解析，全仓库唯一身份来源
- db.py: 统一数据库连接
- filters.py: 数据过滤器
- paths.py: 统一路径管理（自动适配项目位置）
"""

from . import tenant
from . import db
from . import filters
from . import paths

__all__ = [
    # 水库身份（租户）解析
    'tenant',
    # DB 连接和查询
    'db',
    # 表过滤规则
    'filters',
    # 路径管理
    'paths',
]

