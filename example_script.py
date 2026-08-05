#!/usr/bin/env python3
"""
示例脚本：演示如何使用统一路径配置

此脚本展示如何在新的 Python 脚本中使用 lib/paths.py
替代硬编码的绝对路径。
"""

import sys
from pathlib import Path

# 添加 lib/ 到 Python 路径
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from paths import (
    PROJECT_ROOT,
    SKILLS_DIR,
    RESULTS_DIR,
    LOGS_DIR,
    get_skill_dir,
    get_autoresearch_dir,
    ensure_dirs,
)


def main():
    print("=" * 60)
    print("SmartTwinRes-skills 统一路径配置示例")
    print("=" * 60)

    # 1. 基础路径
    print("\n📁 基础路径:")
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  Skills 目录: {SKILLS_DIR}")
    print(f"  结果目录: {RESULTS_DIR}")
    print(f"  日志目录: {LOGS_DIR}")

    # 2. Skill 目录
    print("\n🎯 Skill 目录:")
    skills = ["forecasting", "early-warning", "plan-generation", "simulation"]
    for skill_name in skills:
        skill_dir = get_skill_dir(skill_name)
        exists = "✓" if skill_dir.exists() else "✗"
        print(f"  {exists} {skill_name}: {skill_dir}")

    # 3. Autoresearch 目录
    print("\n🔬 Autoresearch 目录:")
    autoresearch_dirs = ["forecasting", "early-warning", "simulation"]
    for skill_name in autoresearch_dirs:
        ar_dir = get_autoresearch_dir(skill_name)
        print(f"  📂 {skill_name}: {ar_dir}")

    # 4. 自动创建目录
    print("\n✨ 自动创建目录:")
    ensure_dirs()
    print(f"  ✓ 已确保所有目录存在")

    # 5. 验证目录
    print("\n✅ 验证结果:")
    print(f"  PROJECT_ROOT 存在: {PROJECT_ROOT.exists()}")
    print(f"  RESULTS_DIR 存在: {RESULTS_DIR.exists()}")
    print(f"  LOGS_DIR 存在: {LOGS_DIR.exists()}")

    print("\n" + "=" * 60)
    print("示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
