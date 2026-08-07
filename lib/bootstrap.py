#!/usr/bin/env python3
"""
SmartTwinRes-skills 三层定位器。

Priority:
  1. SRM_SKILLS_ROOT env var (deployment contract)       ← 主路径
  2. Candidate-root fallback (dev convenience)            ← 兜底
  3. RuntimeError                                          ← 找不到时

设计参考：/opt/git/water-resources-skills/skills/lib/bootstrap.py
"""

import os
from pathlib import Path

_LIB_MARKER = "db.py"

# 兜底候选根（仅当 SRM_SKILLS_ROOT 未设时遍历）
_KNOWN_ROOTS = (
    "/home/scada/SmartTwinRes-skills",        # 当前部署位置
    "/opt/git/SmartTwinRes-skills",           # 可能的部署位置
    str(Path.home() / "SmartTwinRes-skills"),
)


def locate_root() -> Path:
    """返回仓库根目录（含 lib/db.py）。"""
    r = os.environ.get("SRM_SKILLS_ROOT")
    if r and (Path(r) / "lib" / _LIB_MARKER).exists():
        return Path(r)
    for c in _KNOWN_ROOTS:
        if (Path(c) / "lib" / _LIB_MARKER).exists():
            return Path(c)
    raise RuntimeError(
        "SmartTwinRes lib/ not found. Set SRM_SKILLS_ROOT to the repo root."
    )


def locate_lib() -> Path:
    """返回 lib/ 目录绝对路径。"""
    return locate_root() / "lib"


def locate_shared() -> Path:
    """返回 shared/ 共享知识库目录。"""
    return locate_root() / "shared"


if __name__ == "__main__":
    # CLI 自检：python3 lib/bootstrap.py
    root = locate_root()
    print(f"SRM_SKILLS_ROOT resolved to: {root}")
    print(f"  lib/    : {locate_lib()} ({'存在' if locate_lib().is_dir() else '缺失'})")
    print(f"  shared/ : {locate_shared()} ({'存在' if locate_shared().is_dir() else '缺失'})")
