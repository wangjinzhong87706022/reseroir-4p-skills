#!/usr/bin/env bash
# 鲁棒版17题运行器：请求间隔+错误自动重试+跳过已成功
# v1.9.3+: 通过 hermes-safe.sh 调用,自动处理讯飞 Engine Busy(code 10010)退避重试
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES="bash ${SCRIPT_DIR}/hermes-safe.sh"   # 包装器: Engine Busy 退避重试
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=1200
INTERVAL=10   # 每题间隔10秒，避免限流
MAX_RETRY=2   # 错误自动重试次数(Engine Busy 由 hermes-safe 内部处理)

declare -A QUESTIONS
while IFS=$'\t' read -r qid question; do
    QUESTIONS["$qid"]="$question"
done < "$QUESTIONS_FILE"

SELECTED="14 17 24 26 38 40 44 45 50 56 62 74 1 11 46 66 42"

echo "=== 鲁棒版17题 (v1.7, 间隔${INTERVAL}s, 重试${MAX_RETRY}) ==="
echo "开始: $(date)"
ok=0; err=0; skip=0

run_one() {
    local qid=$1
    local question="${QUESTIONS[$qid]}"
    local output_file="$RESULTS_DIR/Q${qid}.txt"
    
    # 跳过已成功
    if [ -f "$output_file" ] && [ "$(wc -c < "$output_file")" -gt 50 ] && \
       ! grep -q "Stream stalled\|429\|quota\|Max retries" "$output_file" 2>/dev/null; then
        echo "Q${qid}: SKIP"
        skip=$((skip+1))
        return 0
    fi
    rm -f "$output_file"
    
    local attempt=0
    while [ $attempt -le $MAX_RETRY ]; do
        echo -n "Q${qid} [try$((attempt+1))] "
        cd /opt/git/hermes-agent
        timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
        local code=$?
        local size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
        
        # 检查是否成功（无错误标记，size>50）
        if [ $code -eq 0 ] && [ "$size" -gt 50 ] && \
           ! grep -q "Stream stalled\|429\|quota\|Max retries" "$output_file" 2>/dev/null; then
            echo "OK (${size}B)"
            ok=$((ok+1))
            return 0
        elif [ $code -eq 124 ]; then
            echo "TIMEOUT"
        else
            echo "ERR(${size}B)"
        fi
        attempt=$((attempt+1))
        sleep 5
    done
    echo "Q${qid}: 最终失败"
    err=$((err+1))
}

for qid in $SELECTED; do
    run_one "$qid"
    sleep $INTERVAL
done

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 跳过: $skip | 失败: $err"
