# 统一路径配置使用指南

## 📋 概述

SmartTwinRes-skills 使用统一的路径配置系统，所有路径基于项目位置自动计算，无需硬编码绝对路径。项目可以放在任意位置，路径自动适配。

## 🐍 Python 使用方式

### 基本用法

```python
#!/usr/bin/env python3
"""示例脚本"""

import sys
from pathlib import Path

# 方法1: 直接导入 paths 模块
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from paths import PROJECT_ROOT, SKILLS_DIR, RESULTS_DIR

print(f"项目根目录: {PROJECT_ROOT}")
print(f"Skills 目录: {SKILLS_DIR}")

# 方法2: 使用辅助函数
from paths import get_skill_dir, get_autoresearch_dir

forecasting_dir = get_skill_dir("forecasting")
simulation_dir = get_skill_dir("simulation")

print(f"预报 Skill 目录: {forecasting_dir}")
print(f"预演 Skill 目录: {simulation_dir}")

# 方法3: 使用自动创建目录功能
from paths import ensure_dirs

# 确保所有必需的目录存在
ensure_dirs()
```

### 可用常量

```python
from paths import (
    PROJECT_ROOT,           # 项目根目录
    BASE_DIR,               # 兼容旧代码（等同于 PROJECT_ROOT）
    SKILLS_DIR,             # Skills 根目录
    RESULTS_DIR,            # 测试结果目录
    LOGS_DIR,               # 日志目录
    DOCS_DIR,               # 文档目录
    DATA_DIR,               # 数据目录
    FORECASTING_DIR,        # 预报 Skill 目录
    EARLY_WARNING_DIR,      # 预警 Skill 目录
    PLAN_GENERATION_DIR,    # 预案 Skill 目录
    SIMULATION_DIR,         # 预演 Skill 目录
    DIAGNOSIS_VERIFICATION_DIR,  # 诊断验证 Skill 目录
    AUTORESEARCH_DIR,       # Autoresearch 根目录
    FORECASTING_AUTORESEARCH_DIR,  # 预报 Autoresearch 目录
    EARLY_WARNING_AUTORESEARCH_DIR,  # 预警 Autoresearch 目录
    # ... 更多常量
)

# 辅助函数
from paths import get_skill_dir, get_autoresearch_dir, ensure_dirs
```

## 🐚 Shell/Bash 使用方式

### 基本用法

```bash
#!/usr/bin/env bash
# 示例脚本

# 方法1: 加载路径配置
source "$(dirname "$0")/../lib/paths.sh"

echo "项目根目录: $SMARTTWINRES_ROOT"
echo "预报 Skill 目录: $FORECASTING_DIR"
echo "结果目录: $RESULTS_DIR"

# 方法2: 在 Autoresearch 脚本中使用
source "$(dirname "$0")/../../../lib/paths.sh"

RESULTS_DIR="$SIMULATION_AUTORESEARCH_DIR/results"
LOG_DIR="$SIMULATION_AUTORESEARCH_DIR/logs"

mkdir -p "$RESULTS_DIR" "$LOG_DIR"
```

### 可用环境变量

```bash
# 核心目录
export SMARTTWINRES_ROOT          # 项目根目录
export SKILLS_DIR                 # Skills 根目录
export RESULTS_DIR                # 测试结果目录
export LOGS_DIR                   # 日志目录

# Skill 目录
export FORECASTING_DIR            # 预报 Skill
export EARLY_WARNING_DIR          # 预警 Skill
export PLAN_GENERATION_DIR        # 预案 Skill
export SIMULATION_DIR             # 预演 Skill
export DIAGNOSIS_VERIFICATION_DIR # 诊断验证 Skill

# Autoresearch 目录
export AUTORESEARCH_DIR           # Autoresearch 根目录
export FORECASTING_AUTORESEARCH_DIR
export EARLY_WARNING_AUTORESEARCH_DIR
export PLAN_GENERATION_AUTORESEARCH_DIR
export SIMULATION_AUTORESEARCH_DIR
```

## 📂 目录结构

```
SmartTwinRes-skills/
├── lib/
│   ├── __init__.py           # 库入口
│   ├── db.py                 # 数据库连接
│   ├── filters.py            # 数据过滤器
│   ├── paths.py              # Python 路径配置 ⭐
│   └── paths.sh              # Shell 路径配置 ⭐
├── forecasting/
├── early-warning/
├── plan-generation/
├── simulation/
├── results/                  # 自动创建的目录
├── logs/                     # 自动创建的目录
└── test_skills.py           # 测试框架（已更新使用 paths.py）
```

## ✨ 优势

1. **可移植性**: 项目可以放在任意位置，无需修改任何路径
2. **一致性**: 所有脚本使用统一的路径管理方式
3. **易维护**: 只需修改 `lib/paths.py` 一个文件即可调整所有路径
4. **自动创建**: `ensure_dirs()` 函数自动创建必需的目录
5. **类型安全**: Python 版本使用 `pathlib.Path`，避免字符串拼接错误

## 🔄 迁移指南

### 从旧路径迁移

**旧代码:**
```python
BASE_DIR = Path("/home/scada/SmartTwinRes20260601")
SKILLS_DIR = BASE_DIR / "SmartTwinRes-skills"
```

**新代码:**
```python
from paths import PROJECT_ROOT, SKILLS_DIR
# 或直接使用
from paths import get_skill_dir
skill_dir = get_skill_dir("forecasting")
```

**旧 Shell 脚本:**
```bash
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
```

**新 Shell 脚本:**
```bash
source "$(dirname "$0")/../../../lib/paths.sh"
RESULTS_DIR="$SIMULATION_AUTORESEARCH_DIR/results"
```

## 📝 注意事项

1. **Python 脚本**: 使用 `from paths import ...`
2. **Shell 脚本**: 使用 `source lib/paths.sh`
3. **路径计算**: 所有路径基于 `__file__` 或 `${BASH_SOURCE[0]}` 自动计算
4. **向后兼容**: `BASE_DIR` 常量保留，但建议使用 `PROJECT_ROOT`
5. **目录创建**: 首次运行时调用 `ensure_dirs()` 自动创建目录
