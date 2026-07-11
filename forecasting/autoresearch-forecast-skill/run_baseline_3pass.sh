#!/bin/bash
# 预报 skill 完整 9×3 基线(串行,10s 间隔,无并发——本地 LLM 端点弱)
# 用法: cd /opt/git/hermes-agent && bash <本脚本>
# 每遍:清 Q*.txt → run_tests.sh(9题) → 归档到 results.runN/ → eval-txt 打分
set -u
SKILL_DIR="/home/scada/SmartTwinRes20260601/SmartTwinRes-skills/forecasting/autoresearch-forecast-skill"
export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml SRM_DB_USER=root
STALL_RE='Engine Busy|10010|Stream stalled|RecvFromEngineError|HTTP 503|Connection error|API call failed'

echo "=== 9×3 baseline start $(date '+%Y-%m-%d %H:%M:%S') ==="
for run in 1 2 3; do
  echo "----- PASS $run $(date '+%H:%M:%S') -----"
  rm -f "$SKILL_DIR/results/Q"*.txt
  bash "$SKILL_DIR/run_tests.sh" 2>&1 | tail -4
  mkdir -p "$SKILL_DIR/results.run$run"
  cp "$SKILL_DIR/results/Q"*.txt "$SKILL_DIR/results.run$run/" 2>/dev/null
  ( cd "$SKILL_DIR" && python3 eval-txt.py ) > "$SKILL_DIR/results.run$run/score.txt" 2>&1 || true
  echo "PASS $run score:"; tail -8 "$SKILL_DIR/results.run$run/score.txt"
done

echo "=== 聚合(分层 clean/stall)$(date '+%H:%M:%S') ==="
{
  echo "question|run1|run2|run3|clean_runs|stall_runs"
  for f in "$SKILL_DIR"/results.run1/Q*.txt; do
    q=$(basename "$f")
    s1=$(grep -qE "$STALL_RE" "$f" 2>/dev/null && echo STALL || echo CLEAN)
    s2=$( [ -f "$SKILL_DIR/results.run2/$q" ] && { grep -qE "$STALL_RE" "$SKILL_DIR/results.run2/$q" 2>/dev/null && echo STALL || echo CLEAN; } || echo "-")
    s3=$( [ -f "$SKILL_DIR/results.run3/$q" ] && { grep -qE "$STALL_RE" "$SKILL_DIR/results.run3/$q" 2>/dev/null && echo STALL || echo CLEAN; } || echo "-")
    clean=$(printf '%s\n%s\n%s\n' "$s1" "$s2" "$s3" | grep -c CLEAN)
    stall=$(printf '%s\n%s\n%s\n' "$s1" "$s2" "$s3" | grep -c STALL)
    echo "$q|$s1|$s2|$s3|$clean|$stall"
  done
} | column -t -s'|' > "$SKILL_DIR/results_stratified.tsv"
cat "$SKILL_DIR/results_stratified.tsv"
echo "=== done $(date '+%H:%M:%S') ==="