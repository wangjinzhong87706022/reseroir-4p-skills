#!/usr/bin/env python3
"""
SmartTwinRes-skills 统一路径配置

使用方式:
    from lib.paths import PROJECT_ROOT, SKILLS_DIR, RESULTS_DIR

所有路径基于当前文件位置自动计算，无需硬编码绝对路径。
项目可以放在任意位置，路径自动适配。
"""

from pathlib import Path

# =============================================================================
# 项目根目录（基于当前文件位置自动计算）
# =============================================================================
# __file__ = /path/to/SmartTwinRes-skills/lib/paths.py
# parent = lib/
# parent.parent = SmartTwinRes-skills/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# =============================================================================
# 核心目录
# =============================================================================
# 注意：Skills 直接位于项目根目录下，而非 skills/ 子目录
SKILLS_DIR = PROJECT_ROOT
RESULTS_DIR = PROJECT_ROOT / "results"
LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"
DATA_DIR = PROJECT_ROOT / "data"

# =============================================================================
# 兼容旧路径（建议迁移到新名称）
# =============================================================================
BASE_DIR = PROJECT_ROOT  # 兼容 test_skills.py 中的 BASE_DIR

# =============================================================================
# Skill 特定目录（自动计算）
# =============================================================================
FORECASTING_DIR = SKILLS_DIR / "forecasting"
EARLY_WARNING_DIR = SKILLS_DIR / "early-warning"
PLAN_GENERATION_DIR = SKILLS_DIR / "plan-generation"
SIMULATION_DIR = SKILLS_DIR / "simulation"
DIAGNOSIS_VERIFICATION_DIR = SKILLS_DIR / "diagnosis-verification"

# =============================================================================
# Autoresearch 结果目录（按 Skill 组织）
# =============================================================================
AUTORESEARCH_DIR = PROJECT_ROOT / "autoresearch"
FORECASTING_AUTORESEARCH_DIR = AUTORESEARCH_DIR / "forecasting"
EARLY_WARNING_AUTORESEARCH_DIR = AUTORESEARCH_DIR / "early-warning"
PLAN_GENERATION_AUTORESEARCH_DIR = AUTORESEARCH_DIR / "plan-generation"
SIMULATION_AUTORESEARCH_DIR = AUTORESEARCH_DIR / "simulation"

# =============================================================================
# 辅助函数
# =============================================================================

def ensure_path(*paths):
    """
    把一个或多个路径规范化后加入 sys.path（去重，已存在则不重复插入）。

    解决长期运行（同进程反复 import / 测试 reload）下 sys.path 膨胀的问题：
    多个模块对同一目录各 insert 一次，路径会重复累积。

    Args:
        *paths: 任意数量的路径（str / Path）

    Returns:
        规范化后的路径列表
    """
    import sys

    added = []
    for p in paths:
        norm = str(Path(p).resolve())
        if norm not in sys.path:
            sys.path.insert(0, norm)
        added.append(norm)
    return added


def get_skill_dir(skill_name: str) -> Path:
    """
    根据 Skill 名称获取对应的 Skill 目录

    Args:
        skill_name: Skill 名称（如 'forecasting', 'simulation'）

    Returns:
        Path: Skill 目录的绝对路径
    """
    skill_map = {
        'forecasting': FORECASTING_DIR,
        'early-warning': EARLY_WARNING_DIR,
        'plan-generation': PLAN_GENERATION_DIR,
        'simulation': SIMULATION_DIR,
        'diagnosis-verification': DIAGNOSIS_VERIFICATION_DIR,
    }

    skill_dir = skill_map.get(skill_name)
    if not skill_dir:
        raise ValueError(f"未知的 Skill: {skill_name}，可选: {list(skill_map.keys())}")

    return skill_dir


def get_autoresearch_dir(skill_name: str) -> Path:
    """
    根据 Skill 名称获取对应的 Autoresearch 结果目录

    Args:
        skill_name: Skill 名称

    Returns:
        Path: Autoresearch 结果目录的绝对路径
    """
    autoresearch_map = {
        'forecasting': FORECASTING_AUTORESEARCH_DIR,
        'early-warning': EARLY_WARNING_AUTORESEARCH_DIR,
        'plan-generation': PLAN_GENERATION_AUTORESEARCH_DIR,
        'simulation': SIMULATION_AUTORESEARCH_DIR,
    }

    result_dir = autoresearch_map.get(skill_name)
    if not result_dir:
        raise ValueError(f"未知的 Skill: {skill_name}，可选: {list(autoresearch_map.keys())}")

    return result_dir


def ensure_dirs():
    """确保所有必需的目录存在"""
    dirs_to_create = [
        RESULTS_DIR,
        LOGS_DIR,
        DATA_DIR,
        AUTORESEARCH_DIR,
        FORECASTING_AUTORESEARCH_DIR,
        EARLY_WARNING_AUTORESEARCH_DIR,
        PLAN_GENERATION_AUTORESEARCH_DIR,
        SIMULATION_AUTORESEARCH_DIR,
    ]

    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)


# =============================================================================
# 导出所有公共常量
# =============================================================================
__all__ = [
    'PROJECT_ROOT',
    'BASE_DIR',  # 兼容旧代码
    'SKILLS_DIR',
    'RESULTS_DIR',
    'LOGS_DIR',
    'DOCS_DIR',
    'DATA_DIR',
    'FORECASTING_DIR',
    'EARLY_WARNING_DIR',
    'PLAN_GENERATION_DIR',
    'SIMULATION_DIR',
    'DIAGNOSIS_VERIFICATION_DIR',
    'AUTORESEARCH_DIR',
    'get_skill_dir',
    'get_autoresearch_dir',
    'ensure_dirs',
    'ensure_path',
]
