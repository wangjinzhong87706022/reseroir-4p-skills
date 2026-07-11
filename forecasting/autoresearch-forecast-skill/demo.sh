#!/bin/bash
# 预报 skill 端到端 demo runner:逐场景(模拟器→快照→skill 解读)→ 报告
# 用法: SRM_DB_PASSWORD=<预置> bash demo.sh [--auto]
# 依赖 env: SRM_DB_HOST/PORT/NAME/USER/PASSWORD(调用方预置);hermes-safe.sh;forecasting skill 已注册 ~/.hermes/skills/forecasting
# 串行(弱本地端点禁并发)。每场景独立(造数前 --purge-mock)。
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM="$SCRIPT_DIR/../data/generate_forecast_data.py"
HERMES="bash $(realpath "$SCRIPT_DIR/hermes-safe.sh")"
RES="$SCRIPT_DIR/results"; mkdir -p "$RES"
AUTO="${1:-}"; [ "$AUTO" = "--auto" ] && AUTO=1 || AUTO=0
HERMES_TIMEOUT=1200
STALL_RE='Engine Busy|10010|Stream stalled|HTTP 503|Connection error|API call failed|RecvFromEngineError'

# 场景配置表(数据驱动:加场景只加一行)
#   idx | name | sim_cmd(传模拟器,空=默认窗口) | skill_question(空=不调 skill)
SC_NAME=( "正常水情" "暴雨来袭" "多源冲突" "预报陈旧" "复位" )
SC_SIM=(  ""  "--scenario demo_flow"  "--inject-fault source_disagree"  "--inject-fault stale_forecast"  "--purge-mock" )
SC_Q=(    "今天值班，看看三岔水库当前水情和未来24h降雨，会不会有问题？"
          "这场暴雨会不会让水位超汛限？要不要提前预泄？"
          "和风报120mm、分区报60mm，该信哪个源？按多少调度？"
          "未来24小时雨情怎么样？什么时候下得最大？"
          "" )

# --- 快照:查数据现状 → results/demo-snapshot-N.txt ---
snapshot() {  # $1=idx, $2=name
  local out="$RES/demo-snapshot-$1.txt"
  {
    echo "=== 场景$1 $2 数据快照 ($(date '+%H:%M:%S')) ==="
    mysql -h "${SRM_DB_HOST:-127.0.0.1}" -P "${SRM_DB_PORT:-3306}" -u "${SRM_DB_USER:-root}" \
      -p"${SRM_DB_PASSWORD}" "${SRM_DB_NAME:-powerelf_srm_yml}" -t 2>/dev/null <<'SQL'
SELECT '当前水位' k, (SELECT CONCAT(rz,'m') FROM st_rsvr_r WHERE creator='MOCK' ORDER BY tm DESC LIMIT 1) v
UNION ALL SELECT '水位峰值24h', (SELECT CONCAT(MAX(rz),'m') FROM st_rsvr_r WHERE creator='MOCK' AND tm>=NOW()-INTERVAL 24 HOUR)
UNION ALL SELECT '24h预报降雨总量mm', (SELECT ROUND(SUM(RN),1) FROM f_rnfl_h WHERE COMMENTS='MOCK' AND YMDH<=NOW()+INTERVAL 24 HOUR)
UNION ALL SELECT '24h实测降雨mm', (SELECT ROUND(SUM(dr),1) FROM st_pptn_r WHERE creator='MOCK' AND tm>=NOW()-INTERVAL 24 HOUR)
UNION ALL SELECT '预警', (SELECT IFNULL(GROUP_CONCAT(chnlname),'无') FROM weather_warn WHERE docabstract LIKE '%[MOCK]%')
UNION ALL SELECT '汛限水位', (SELECT CONCAT(flse_lim_stag,'m') FROM att_res_flse_lim ORDER BY id LIMIT 1);
SQL
  } > "$out"
  echo "  快照 → $out"
}

# --- 解读:hermes 调 skill(串行)→ results/demo-scenario-N.txt ---
interpret() {  # $1=idx, $2=question
  local out="$RES/demo-scenario-$1.txt"
  echo "  调 hermes 解读(timeout ${HERMES_TIMEOUT}s,串行)..."
  ( cd /opt/git/hermes-agent && timeout "$HERMES_TIMEOUT" $HERMES -z "$2" ) > "$out" 2>&1
  local rc=$? sz=$(wc -c < "$out" 2>/dev/null || echo 0)
  if [ "$rc" -ne 0 ] || [ "$sz" -lt 100 ] || grep -qE "$STALL_RE" "$out" 2>/dev/null; then
    echo -e "\n⚠️ STALL(rc=$rc, ${sz}B) — 端点未取到解读,报告将标注\n" >> "$out"
    echo "  ⚠️ stall(rc=$rc,${sz}B)"
  else
    echo "  解读 OK(${sz}B)"
  fi
}

echo "=== Demo Runner 开始 $(date '+%H:%M:%S') ===  AUTO=$AUTO"
for i in 0 1 2 3 4; do
  n=$((i+1)); name="${SC_NAME[$i]}"; sim="${SC_SIM[$i]}"; q="${SC_Q[$i]}"
  echo "--- 场景$n: $name ---"
  # 1. 清场(每场景独立,避免污染)
  python3 "$SIM" --purge-mock >/dev/null 2>&1
  # 2. 造数(复位场景 sim=--purge-mock 已清;否则按 sim_cmd;空=默认窗口)
  if [ -n "$sim" ] && [ "$sim" != "--purge-mock" ]; then
    python3 "$SIM" $sim >/dev/null 2>&1 || echo "  ⚠️ 造数失败"
  elif [ -z "$sim" ]; then
    python3 "$SIM" >/dev/null 2>&1 || echo "  ⚠️ 造数失败"
  fi
  # 3. 快照(复位场景跳过)
  [ "$name" != "复位" ] && snapshot "$n" "$name"
  # 4. 解读(无问题则跳过)
  [ -n "$q" ] && interpret "$n" "$q"
  # pause 或 --auto
  if [ "$AUTO" != 1 ] && [ "$n" -lt 5 ]; then
    read -rp "  场景$n 完成,回车进下一个(Ctrl-C 退出,先生成部分报告)..." _ || break
  fi
done
echo "=== Demo 完成 $(date '+%H:%M:%S') ==="
# 报告(Task 2 接;若 demo_report.py 存在则生成)
if [ -f "$SCRIPT_DIR/demo_report.py" ]; then
  python3 "$SCRIPT_DIR/demo_report.py" "$RES"
  echo "报告: $RES/demo-report.md"
else
  echo "(demo_report.py 未建,跳过报告生成)"
fi
