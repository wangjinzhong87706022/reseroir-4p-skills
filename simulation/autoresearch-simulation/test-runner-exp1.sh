#!/usr/bin/env bash
# Exp 1 retest: 28 E2+E4 failure questions with v1.1 SKILL.md
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results-exp1"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=600

mkdir -p "$RESULTS_DIR"

# Questions to retest
FAILQS="2 9 11 14 15 16 17 18 19 23 24 26 40 41 43 44 45 50 52 54 62 63 64 65 72 74 78 79"

echo "=== Exp 1 Retest (v1.1 SKILL.md) ==="
echo "Questions: $FAILQS"
echo "开始: $(date)"
ok=0; timeout=0; fail=0

while IFS=$'\t' read -r qid question; do
    # Only process target questions
    match=0
    for tq in $FAILQS; do
        [ "$qid" = "$tq" ] && match=1 && break
    done
    [ "$match" = "0" ] && continue
    
    output_file="$RESULTS_DIR/Q${qid}.txt"
    
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
