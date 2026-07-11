#!/usr/bin/env bash
# Run 12 selected questions through hermes with given timeout
# Usage: bash run-12.sh [timeout_secs]
HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=${1:-600}

# Pre-load questions
declare -A QUESTIONS
while IFS=$'\t' read -r qid question; do
    QUESTIONS["$qid"]="$question"
done < "$QUESTIONS_FILE"

SELECTED="14 17 24 26 38 40 44 45 50 56 62 74 1 11 46 66 42"

for qid in $SELECTED; do
    question="${QUESTIONS[$qid]}"
    output_file="$RESULTS_DIR/Q${qid}.txt"
    rm -f "$output_file"

    echo -n "Q${qid} [...] "
    cd /opt/git/hermes-agent
    timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
    exit_code=$?
    size=$(wc -c < "$output_file" 2>/dev/null || echo 0)

    if [ $exit_code -eq 124 ]; then
        echo "TIMEOUT"
    elif [ $exit_code -eq 0 ] && [ "$size" -gt 50 ]; then
        echo "OK (${size}B)"
    else
        echo "FAIL (${size}B)"
    fi
done
