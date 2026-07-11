#!/usr/bin/env bash
# Phase 2: Run Q64-Q98 (missing) + retry timeout questions with 1200s timeout
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=300
TIMEOUT_LONG=1200

mkdir -p "$RESULTS_DIR"

echo "=== Phase 2: Q64-Q98 + Timeout Retries ==="
echo "开始: $(date)"

# Timeout questions to retry with long timeout
TIMEOUTQS="1 2 5 6 7 8 13 50 61 62"

ok=0; timeout=0; fail=0; skipped=0

while IFS=$'\t' read -r qid question; do
    output_file="$RESULTS_DIR/Q${qid}.txt"
    
    # Check if already has good result
    if [ -f "$output_file" ]; then
        size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
        if [ "$size" -gt 50 ] && ! grep -q "TIMEOUT" "$output_file"; then
            continue  # skip good results
        fi
    fi
    
    # Determine timeout: use long timeout for known timeout questions
    is_timeout_q=0
    for tq in $TIMEOUTQS; do
        [ "$qid" = "$tq" ] && is_timeout_q=1 && break
    done
    
    if [ "$is_timeout_q" = "1" ]; then
        t=$TIMEOUT_LONG
        label="LONG"
    else
        t=$TIMEOUT_SECS
        label="STD"
    fi
    
    echo -n "Q${qid} [${label}] [$(printf '%-20s' "${question:0:18}...")] "
    
    cd /opt/git/hermes-agent
    timeout $t $HERMES chat -q "$question" > "$output_file" 2>&1
    exit_code=$?
    size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
    
    if [ $exit_code -eq 124 ]; then
        echo "TIMEOUT"
        echo "TIMEOUT" > "$output_file"
        timeout=$((timeout + 1))
    elif [ $exit_code -eq 0 ] && [ "$size" -gt 50 ]; then
        echo "OK (${size}B)"
        ok=$((ok + 1))
    else
        echo "FAIL (exit=$exit_code, ${size}B)"
        fail=$((fail + 1))
    fi

done < "$QUESTIONS_FILE"

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 超时: $timeout | 失败: $fail"
