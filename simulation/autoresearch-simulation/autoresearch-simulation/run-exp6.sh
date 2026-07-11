#!/usr/bin/env bash
# Exp 6: 只跑 Q40, Q46, Q56 三题
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=1200
INTERVAL=10

declare -A QUESTIONS
while IFS=$'\t' read -r qid question; do
    QUESTIONS["$qid"]="$question"
done < "$QUESTIONS_FILE"

SELECTED="40 46 56"

echo "=== Exp 6 (v1.9): Q40,46,56 ==="
echo "开始: $(date)"

for qid in $SELECTED; do
    question="${QUESTIONS[$qid]}"
    output_file="$RESULTS_DIR/Q${qid}.txt"
    rm -f "$output_file"
    
    echo -n "Q${qid} [...] "
    cd /opt/git/hermes-agent
    timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
    code=$?
    size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
    
    if [ $code -eq 124 ]; then
        echo "TIMEOUT"
    elif [ $code -eq 0 ] && [ "$size" -gt 50 ]; then
        echo "OK (${size}B)"
    else
        echo "FAIL (${size}B)"
    fi
    sleep $INTERVAL
done
echo "=== 完成 $(date) ==="
