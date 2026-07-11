#!/bin/bash
# 启动三个物理模型服务
# 用法: bash start_models.sh [start|stop|status|restart]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$SCRIPT_DIR/pids"

mkdir -p "$PID_DIR"

start_service() {
    local name=$1
    local script=$2
    local port=$3
    local pidfile="$PID_DIR/${name}.pid"

    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "[$name] 已在运行 (PID: $(cat "$pidfile"))"
        return
    fi

    echo "[$name] 启动中... (端口: $port)"
    cd "$SCRIPT_DIR"
    nohup python3 "$script" > "$SCRIPT_DIR/logs/${name}.log" 2>&1 &
    echo $! > "$pidfile"
    sleep 1

    if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "[$name] 启动成功 (PID: $(cat "$pidfile"))"
    else
        echo "[$name] 启动失败，查看日志: $SCRIPT_DIR/logs/${name}.log"
    fi
}

stop_service() {
    local name=$1
    local pidfile="$PID_DIR/${name}.pid"

    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "[$name] 已停止 (PID: $pid)"
        else
            echo "[$name] 进程不存在"
        fi
        rm -f "$pidfile"
    else
        echo "[$name] 未运行"
    fi
}

status_service() {
    local name=$1
    local port=$2
    local pidfile="$PID_DIR/${name}.pid"

    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "[$name] 运行中 (PID: $(cat "$pidfile"), 端口: $port)"
    else
        echo "[$name] 未运行"
    fi
}

mkdir -p "$SCRIPT_DIR/logs"

case "${1:-start}" in
    start)
        echo "=== 启动物理模型服务 ==="
        start_service "xaj" "xaj_model.py" "18081"
        start_service "dispatch" "dispatch_model.py" "18082"
        start_service "routing" "flood_routing.py" "18083"
        echo ""
        echo "=== 服务状态 ==="
        status_service "xaj" "18081"
        status_service "dispatch" "18082"
        status_service "routing" "18083"
        echo ""
        echo "API 端点："
        echo "  新安江模型: http://localhost:18081/api/xaj/forecast"
        echo "  调度优化:   http://localhost:18082/api/dispatch/optimize"
        echo "  调洪演算:   http://localhost:18083/api/routing/calculate"
        ;;
    stop)
        echo "=== 停止物理模型服务 ==="
        stop_service "xaj"
        stop_service "dispatch"
        stop_service "routing"
        ;;
    status)
        echo "=== 物理模型服务状态 ==="
        status_service "xaj" "18081"
        status_service "dispatch" "18082"
        status_service "routing" "18083"
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    *)
        echo "用法: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
