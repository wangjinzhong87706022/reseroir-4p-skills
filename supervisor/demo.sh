#!/usr/bin/env bash
# supervisor/demo.sh — 一键四场景演示（5 分钟跑完 A/B/C/D 闭环）
#
# 用法：
#   bash supervisor/demo.sh                 # 桃曲坡（tenant 20，默认）
#   SRM_RESERVOIR_NAME=sancha bash supervisor/demo.sh   # 三岔（tenant 18）
#
# 输出：每场景的编排摘要落到 supervisor/demo-output/<场景>-<时间>.json，
#       控制台只打印关键里程碑（场景识别 / 仲裁结论 / 报告状态）。
#
# 前置：supervisor/scripts/orchestrator.py 各场景已实测可跑（v0.4.0+）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH="$REPO_ROOT/supervisor/scripts/orchestrator.py"
OUT_DIR="$REPO_ROOT/supervisor/demo-output"
mkdir -p "$OUT_DIR"

# 环境变量缺省时给桃曲坡默认值（不覆盖已设值）
: "${SRM_DB_HOST:=127.0.0.1}"
: "${SRM_DB_PORT:=3306}"
: "${SRM_DB_NAME:=powerelf_srm_yml}"
: "${SRM_DB_USER:=root}"
: "${SRM_DB_PASSWORD:=123456aA.}"
: "${SRM_TENANT_ID:=20}"
: "${SRM_RESERVOIR_NAME:=taoqupo}"
export SRM_DB_HOST SRM_DB_PORT SRM_DB_NAME SRM_DB_USER SRM_DB_PASSWORD \
       SRM_TENANT_ID SRM_RESERVOIR_NAME

TS="$(date +%Y%m%d-%H%M%S)"
PASS=0
FAIL=0

run_scene() {
    local scene="$1" trigger="$2"
    local out="$OUT_DIR/${scene}-${TS}.json"
    echo ""
    echo "=========================================================="
    echo "▶ 场景 $scene：$trigger"
    echo "=========================================================="
    # --approve 跳过 HITL 检查点，自动续跑到报告生成
    if timeout 480 python3 "$ORCH" run --trigger "$trigger" --approve \
            > "$out" 2>&1; then
        # 提取关键里程碑：场景/优先级/仲裁结论/最终状态
        python3 - "$out" <<'PY'
import json, sys
lines = open(sys.argv[1], encoding="utf-8").read()
# 提取 priority 行 + 最后的 status + 仲裁行
import re
pri = re.search(r'"priority":\s*"(\w+)"', lines)
arb = re.search(r'\[step\d\]\s+arbitrator\s+→\s+(\{.*?\})', lines)
sts = re.search(r'"status":\s*"(\w+)"', lines)
print(f"  优先级: {pri.group(1) if pri else '?'}")
if arb:
    try:
        d = json.loads(arb.group(1))
        print(f"  仲裁: risk={d.get('risk_level','?')} decision={d.get('decision','?')} passed={d.get('passed')}")
    except json.JSONDecodeError:
        pass
print(f"  最终状态: {sts.group(1) if sts else '?'}")
print(f"  完整输出: {sys.argv[1]}")
PY
        PASS=$((PASS + 1))
    else
        echo "  ❌ 场景 $scene 执行失败（见 $out）"
        tail -5 "$out"
        FAIL=$((FAIL + 1))
    fi
}

echo "四预智能体 Supervisor 演示（水库=$SRM_RESERVOIR_NAME tenant=$SRM_TENANT_ID 时间=$TS）"

# 四场景触发信号（覆盖 A暴雨/B诊断/C日常/D应急）
run_scene A "暴雨预警，水位超汛限，需研判调度"
run_scene B "渗压计数据异常，位移超限，需要大坝安全诊断"
run_scene C "每日例行水情汇报"
run_scene D "闸门故障，需要紧急抢险"

echo ""
echo "=========================================================="
echo "演示完成：$PASS 场景通过，$FAIL 场景失败"
echo "输出目录：$OUT_DIR"
echo "=========================================================="
exit $FAIL
