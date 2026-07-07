#!/bin/bash
# 预演编排服务启动脚本
# 检查依赖服务状态后启动 simulation_service.py

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=18084

echo "=========================================="
echo " 预演编排服务启动检查"
echo "=========================================="

# 检查依赖服务
check_service() {
    local name=$1
    local url=$2
    local status=$(curl -s -o /dev/null -w "%{http_code}" "$url/health" 2>/dev/null || echo "000")
    if [ "$status" = "200" ]; then
        echo "  ✅ $name ($url) — 可用"
        return 0
    else
        echo "  ❌ $name ($url) — 不可用"
        return 1
    fi
}

echo ""
echo "检查依赖服务..."
FAILED=0

check_service "XAJ 模型" "http://localhost:18081" || FAILED=$((FAILED + 1))
check_service "Dispatch 模型" "http://localhost:18082" || FAILED=$((FAILED + 1))
check_service "Routing 模型" "http://localhost:18083" || FAILED=$((FAILED + 1))

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "⚠️  $FAILED 个依赖服务不可用。"
    echo "请先启动 plan-generation 的模型服务："
    echo "  cd SmartTwinRes-skills/plan-generation/models"
    echo "  bash start_models.sh"
    echo ""
    read -p "是否仍然启动？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "启动预演编排服务 (端口 $PORT)..."
echo "=========================================="

cd "$SCRIPT_DIR"
python3 simulation_service.py
