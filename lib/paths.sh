#!/usr/bin/env bash
# SmartTwinRes-skills Shell 统一路径配置
# 使用方式: source lib/paths.sh

# 项目根目录（基于当前脚本位置自动计算）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 核心目录
export SMARTTWINRES_ROOT="$PROJECT_ROOT"
export SKILLS_DIR="$PROJECT_ROOT"
export RESULTS_DIR="$PROJECT_ROOT/results"
export LOGS_DIR="$PROJECT_ROOT/logs"

# Skill 目录
export FORECASTING_DIR="$SKILLS_DIR/forecasting"
export EARLY_WARNING_DIR="$SKILLS_DIR/early-warning"
export PLAN_GENERATION_DIR="$SKILLS_DIR/plan-generation"
export SIMULATION_DIR="$SKILLS_DIR/simulation"
export DIAGNOSIS_VERIFICATION_DIR="$SKILLS_DIR/diagnosis-verification"

# Autoresearch 目录
export AUTORESEARCH_DIR="$PROJECT_ROOT/autoresearch"
export FORECASTING_AUTORESEARCH_DIR="$AUTORESEARCH_DIR/forecasting"
export EARLY_WARNING_AUTORESEARCH_DIR="$AUTORESEARCH_DIR/early-warning"
export PLAN_GENERATION_AUTORESEARCH_DIR="$AUTORESEARCH_DIR/plan-generation"
export SIMULATION_AUTORESEARCH_DIR="$AUTORESEARCH_DIR/simulation"

echo "SmartTwinRes-skills 路径已加载"
echo "  项目根目录: $PROJECT_ROOT"
echo "  Skills 目录: $SKILLS_DIR"
