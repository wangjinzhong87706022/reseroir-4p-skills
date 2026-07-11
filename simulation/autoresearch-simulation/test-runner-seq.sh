#!/usr/bin/env bash
# 预演 Skill 顺序测试运行器
# 一次只跑一个问题，跳过已有成功结果
# 用法: bash test-runner-seq.sh

HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"
TIMEOUT_SECS=300

mkdir -p "$RESULTS_DIR"

echo "=== 预演 Skill 顺序测试 ==="
echo "开始: $(date)"
echo ""

total=0
skipped=0
ok=0
fail=0
timeout=0

while IFS=$'\t' read -r qid question; do
    total=$((total + 1))
    output_file="$RESULTS_DIR/Q${qid}.txt"

    # Skip if already has good result
    if [ -f "$output_file" ]; then
        size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
        if [ "$size" -gt 50 ] && ! grep -q "TIMEOUT" "$output_file"; then
            skipped=$((skipped + 1))
            continue
        fi
        rm -f "$output_file"
    fi

    echo -n "Q${qid} [$(printf '%-20s' "${question:0:18}...")] "

    cd /opt/git/hermes-agent
    timeout $TIMEOUT_SECS $HERMES chat -q "$question" > "$output_file" 2>&1
    exit_code=$?
    size=$(wc -c < "$output_file" 2>/dev/null || echo 0)

    if [ $exit_code -eq 124 ]; then
        echo "TIMEOUT"
        echo "TIMEOUT" > "$output_file"
        timeout=$((timeout + 1))
    elif [ $exit_code -eq 0 ] && [ "$size" -gt 50 ]; then
        dur=$(grep 'Duration:' "$output_file" | head -1 | sed 's/.*Duration:\s*//')
        echo "OK (${size}B, $dur)"
        ok=$((ok + 1))
    else
        echo "FAIL (exit=$exit_code, ${size}B)"
        fail=$((fail + 1))
    fi

done < "$QUESTIONS_FILE"

echo ""
echo "=== 完成 $(date) ==="
echo "总: $total | 成功: $ok | 跳过: $skipped | 超时: $timeout | 失败: $fail"
echo "结果目录: $RESULTS_DIR"
