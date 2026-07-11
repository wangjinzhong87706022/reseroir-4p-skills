#!/usr/bin/env bash
# 通用顺序测试运行器（预加载数组，无管道断裂问题）
# 用法: bash test-runner.sh [start_qid] [end_qid] [timeout_secs]
# 示例: bash test-runner.sh              # 跑全部，600s超时
#       bash test-runner.sh 69 98 1200   # 跑Q69-Q98，20分钟超时
#       bash test-runner.sh 1 98 600     # 跑全部，10分钟超时

HERMES="/opt/git/hermes-agent/venv/bin/hermes"
RESULTS_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/results"
QUESTIONS_FILE="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/simulation/autoresearch-simulation/questions.tsv"

START_QID=${1:-1}
END_QID=${2:-98}
TIMEOUT_SECS=${3:-600}

mkdir -p "$RESULTS_DIR"

# 预加载所有问题到关联数组（避免 while-read 管道断裂）
declare -A QUESTIONS
while IFS=$'\t' read -r qid question; do
    QUESTIONS["$qid"]="$question"
done < "$QUESTIONS_FILE"

echo "=== 预演 Skill 测试 (Q${START_QID}-Q${END_QID}, ${TIMEOUT_SECS}s) ==="
echo "开始: $(date)"
ok=0; skip=0; timeout=0; fail=0

for qid in $(seq $START_QID $END_QID); do
    question="${QUESTIONS[$qid]}"
    [ -z "$question" ] && continue
    
    output_file="$RESULTS_DIR/Q${qid}.txt"
    
    # 跳过已有成功结果
    if [ -f "$output_file" ]; then
        size=$(wc -c < "$output_file" 2>/dev/null || echo 0)
        if [ "$size" -gt 50 ] && ! grep -q "TIMEOUT" "$output_file"; then
            echo "Q${qid}: SKIP"
            skip=$((skip + 1))
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
        echo "OK (${size}B)"
        ok=$((ok + 1))
    else
        echo "FAIL (exit=$exit_code, ${size}B)"
        fail=$((fail + 1))
    fi
done

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 跳过: $skip | 超时: $timeout | 失败: $fail"
echo "结果目录: $RESULTS_DIR"
