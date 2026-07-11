#!/usr/bin/env bash
# 鲁棒版预报 Skill 9 题运行器(分层 8 基线 + 1 极端)
# 经 hermes-safe.sh wrapper 调用,自动处理讯飞 Engine Busy(code 10010)退避重试
# 用法: bash run_tests.sh [question_index 1-9]   # 不带参=跑全部9题
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
SKILL_PATH="${REPO_ROOT}/SmartTwinRes-skills/forecasting"   # 供 --skills 加载(本 skill 未装为 builtin)
HERMES="bash $(realpath ${SCRIPT_DIR}/hermes-safe.sh)"   # 软链 → simulation 的 wrapper
OUTPUT_DIR="${SCRIPT_DIR}/results"
TIMEOUT_SECS=1200   # 单题超时(wrapper内部还会退避重试 Engine Busy)
INTERVAL=10         # 题间节流,避免限流
MAX_RETRY=2         # 错误自动重试次数(Engine Busy 由 hermes-safe 内部处理)
mkdir -p "$OUTPUT_DIR"

# 必需环境变量(调用前导出): SRM_DB_HOST/PORT/NAME/USER/PASSWORD
# 本 skill 须在 ~/.hermes/skills/ 注册(软链到本目录, 仿 plan-generation/simulation),
# 否则 hermes 的 skill_view 只在 SKILLS_DIR 内按名解析、不接受 abs 路径(实测 --skills <abs_path>
# 会被静默忽略、跑成裸模型)。注册: ln -sfn "$SKILL_PATH" ~/.hermes/skills/forecasting
SKILL_NAME="forecasting"
if [ ! -e "${HOME}/.hermes/skills/${SKILL_NAME}" ]; then
    echo "FATAL: forecasting 未注册为 hermes builtin — 请先: ln -sfn \"$SKILL_PATH\" ~/.hermes/skills/forecasting" >&2
    exit 2
fi

# 分层 8 基线题(每类一题) + 1 极端题(取自 tests/test-questions-v2.md, 业务向口语化)
declare -a QUESTIONS=(
  "今天值班，帮我看看未来24小时雨情怎么样？什么时候下得最大？这场雨会不会到暴雨级别？"                                  # 预报解读
  "这场雨下完，我们水库水位会涨多少？会不会超汛限462.5？现在入库和出库流量分别是多少？"                                    # 水库影响
  "和风的预报和气象台的分区预报不一样，一个说120mm一个说60mm，信哪个？到底按多少来调度？"                                   # 多源融合
  "未来12小时水位怎么变？会涨会落？涨多少？按这个雨情洪峰大概什么时候来？"                                                # 趋势预测
  "我们用的这个和风预报，历史上准不准？平均误差多少？几个源里哪个最准？"                                                  # 预报精度
  "这次预报的雨情24h 100mm起调459m，历史上有没有类似的洪水？当时怎么处理的？削峰率多少？"                                  # 历史相似洪水
  "最近系统跑过哪些预报任务？最新一次是什么时候？结果存哪了？预报数据多久更新一次？"                                       # 预报管理
  "气象台发红色预警未来24h 130mm，现在水位459m，怎么办？要不要提前泄洪？气象局预报跟实际下的雨对得上吗？"                # 综合场景
  "水位已经462.8了，超汛限462.5了，马上要超校核462.88了！现在立刻怎么办？要泄多少？"                                       # 极端暴雨
)

declare -a NAMES=(
  "Q1_预报解读"
  "Q2_水库影响"
  "Q3_多源融合"
  "Q4_趋势预测"
  "Q5_预报精度"
  "Q6_历史相似洪水"
  "Q7_预报管理"
  "Q8_综合场景"
  "Q9_极端暴雨"
)

echo "=== 预报 Skill 鲁棒版 9 题 (间隔${INTERVAL}s, 重试${MAX_RETRY}, 超时${TIMEOUT_SECS}s) ==="
echo "开始: $(date)"
ok=0; err=0; skip=0

run_one() {
    local idx=$1
    local question="${QUESTIONS[$idx]}"
    local name="${NAMES[$idx]}"
    local output_file="$OUTPUT_DIR/${name}.txt"

    # 跳过已成功
    if [ -f "$output_file" ] && [ "$(wc -c < "$output_file")" -gt 50 ] && \
       ! grep -q "Stream stalled\|429\|quota\|Max retries" "$output_file" 2>/dev/null; then
        echo "${name}: SKIP"
        skip=$((skip+1))
        return 0
    fi
    rm -f "$output_file"

    local attempt=0
    while [ $attempt -le $MAX_RETRY ]; do
        echo -n "${name} [try$((attempt+1))] "
        cd /opt/git/hermes-agent
        timeout $TIMEOUT_SECS $HERMES -z "$question" --skills "$SKILL_NAME" > "$output_file" 2>&1
        local code=$?
        local size=$(wc -c < "$output_file" 2>/dev/null || echo 0)

        if [ $code -eq 0 ] && [ "$size" -gt 50 ] && \
           ! grep -q "Stream stalled\|429\|quota\|Max retries" "$output_file" 2>/dev/null; then
            echo "OK (${size}B)"
            ok=$((ok+1))
            return 0
        elif [ $code -eq 124 ]; then
            echo "TIMEOUT"
        else
            echo "ERR(${size}B)"
        fi
        attempt=$((attempt+1))
        sleep 5
    done
    echo "${name}: 最终失败"
    err=$((err+1))
}

# 主逻辑
if [ -n "$1" ]; then
    run_one $(( $1 - 1 ))
else
    for i in "${!QUESTIONS[@]}"; do
        run_one $i
        sleep $INTERVAL
    done
fi

echo ""
echo "=== 完成 $(date) ==="
echo "成功: $ok | 跳过: $skip | 失败: $err"
