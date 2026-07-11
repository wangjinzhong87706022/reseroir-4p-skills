#!/usr/bin/env bash
# 预演 Skill 全量测试运行器 v2
# 用法: bash test-runner-v2.sh [start_idx] [end_idx]

HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
MAX_PARALLEL=4
TIMEOUT_SECS=300

START_IDX=${1:-1}
END_IDX=${2:-98}

mkdir -p "$RESULTS_DIR"

# 问题文件：每行格式 "Q号\t问题文本"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"

run_one() {
    local qid=$1
    local question=$2
    local output_file="$RESULTS_DIR/Q${qid}.txt"

    cd /opt/git/hermes-agent
    timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
    local exit_code=$?
    local size=$(wc -c < "$output_file" 2>/dev/null || echo 0)

    if [ $exit_code -eq 0 ] && [ $size -gt 50 ]; then
        echo "Q${qid}: OK (${size}B)"
    elif [ $exit_code -eq 124 ]; then
        echo "TIMEOUT" > "$output_file"
        echo "Q${qid}: TIMEOUT"
    else
        echo "Q${qid}: FAIL (exit=$exit_code ${size}B)"
    fi
}

echo "=== 预演 Skill 全量测试 v2 ==="
echo "范围: Q${START_IDX} - Q${END_IDX} | 并行: ${MAX_PARALLEL}"
echo "开始: $(date)"
echo ""

running=0
while IFS=$'\t' read -r qid question; do
    # Skip if outside range
    [ "$qid" -lt "$START_IDX" ] && continue
    [ "$qid" -gt "$END_IDX" ] && break

    run_one "$qid" "$question" &
    running=$((running + 1))

    if [ $running -ge $MAX_PARALLEL ]; then
        wait -n 2>/dev/null || wait
        running=$((running - 1))
    fi
done < "$QUESTIONS_FILE"

# Wait for remaining
wait

echo ""
echo "=== 完成 $(date) ==="
echo "结果: $(ls "$RESULTS_DIR"/*.txt 2>/dev/null | wc -l) 文件"
