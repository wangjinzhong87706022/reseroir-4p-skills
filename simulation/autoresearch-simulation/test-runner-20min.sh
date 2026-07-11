#!/usr/bin/env bash
# 20分钟超时，从Q69开始跑所有缺失和超时题
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=1200

echo "=== 20min Timeout: Q69-Q98 ==="
echo "开始: $(date)"
ok=0; timeout=0; fail=0

while IFS=$'\t' read -r qid question; do
    [ "$qid" -lt 69 ] && continue
    
    output_file="$RESULTS_DIR/Q${qid}.txt"
    
    # Skip if already good
    if [ -f "$output_file" ]; then
        size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
        if [ "$size" -gt 50 ] && ! grep -q "TIMEOUT" "$output_file"; then
            echo "Q${qid}: SKIP"
            continue
        fi
        rm -f "$output_file"
    fi
    
    echo -n "Q${qid} [$(printf '%-25s' "${question:0:23}...")] "
    
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
done < "$QUESTIONS_FILE"

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 超时: $timeout | 失败: $fail"
