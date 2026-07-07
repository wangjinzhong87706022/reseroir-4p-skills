#!/usr/bin/env bash
# Phase 4: Retry ALL timeout questions with 1200s (20min) timeout
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=1200

echo "=== Phase 4: Timeout Retries (20min) ==="
echo "开始: $(date)"
ok=0; timeout=0; fail=0

while IFS=$'\t' read -r qid question; do
    output_file="$RESULTS_DIR/Q${qid}.txt"
    
    # Only process timeout files
    if [ -f "$output_file" ] && grep -q "TIMEOUT" "$output_file"; then
        rm -f "$output_file"
        echo -n "Q${qid} [LONG] [$(printf '%-25s' "${question:0:23}...")] "
        
        cd /opt/git/hermes-agent
        timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
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
    fi
done < "$QUESTIONS_FILE"

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 超时: $timeout | 失败: $fail"
