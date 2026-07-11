#!/usr/bin/env bash
# hermes-safe.sh — hermes chat 的防 Engine Busy 包装器(不改 hermes 源码)
#
# 背景: 讯飞(xf-yun) MaaS 在引擎过载时返回 code 10010 "Engine Busy",
# 流式连接在工具调用发到一半时被掐断,hermes 的策略是"部分发送后不重试"
# (防重复消息),导致工具调用丢失、回答中断、整题 0 分。
# 生产环境用专属实例/更高QPS档通常不会撞上,但留此防御:
# 检测到 Engine Busy/Stream stalled 就【退避等引擎恢复 + 重跑整题】。
#
# 用法(与 hermes chat 完全兼容,透传所有参数):
#   hermes-safe.sh chat -q "你的问题"
#   hermes-safe.sh chat -q "问题" > out.txt
#
# 环境变量(可覆盖):
#   HERMES_BIN       hermes 可执行路径(默认 /opt/git/hermes-agent/venv/bin/hermes)
#   EB_MAX_RETRY     Engine Busy 最大重试次数(默认 3)
#   EB_BACKOFF_SECS  每次退避秒数(默认 45,等讯飞引擎恢复)
#   EB_TIMEOUT_SECS  单次 hermes 超时(默认 600)

set -o pipefail

HERMES_BIN="${HERMES_BIN:-/opt/git/hermes-agent/venv/bin/hermes}"
EB_MAX_RETRY="${EB_MAX_RETRY:-3}"
EB_BACKOFF_SECS="${EB_BACKOFF_SECS:-45}"
EB_TIMEOUT_SECS="${EB_TIMEOUT_SECS:-600}"

# Engine Busy / 流中断的检测模式(命中任一即判定为可退避重试的瞬态故障)
EB_PATTERN='Engine Busy|RecvFromEngineError|10010|Stream stalled mid tool-call'

# 输出目标: 若上层用管道/重定向,hermes 的 stdout 直接透传即可;
# 但我们需要同时【检测输出内容】。用一个临时文件兜住,结束后输出到 stdout。
_out="$(mktemp -t hermes-safe.XXXXXX)"
trap 'rm -f "$_out" 2>/dev/null' EXIT

attempt=0
while [ $attempt -le $EB_MAX_RETRY ]; do
    # 透传所有参数给 hermes(支持 chat 子命令及任意 flags)
    timeout "$EB_TIMEOUT_SECS" "$HERMES_BIN" "$@" > "$_out" 2>&1
    rc=$?

    # 1) 正常结束且无 Engine Busy 标记 → 输出并退出
    if [ $rc -eq 0 ] && ! grep -qE "$EB_PATTERN" "$_out" 2>/dev/null; then
        cat "$_out"
        # 若重试过,在 stderr 留个痕迹(不污染 stdout)
        [ $attempt -gt 0 ] && echo "[hermes-safe] 第$((attempt+1))次尝试成功" >&2
        exit 0
    fi

    # 2) 命中 Engine Busy / 流中断 → 退避重试
    if grep -qE "$EB_PATTERN" "$_out" 2>/dev/null; then
        attempt=$((attempt+1))
        if [ $attempt -le $EB_MAX_RETRY ]; then
            echo "[hermes-safe] 检测到 Engine Busy/流中断,退避 ${EB_BACKOFF_SECS}s 后重试 ($attempt/$EB_MAX_RETRY)..." >&2
            sleep "$EB_BACKOFF_SECS"
            continue
        fi
        # 重试用尽: 输出最后结果(含警告),让上层自行判断
        echo "[hermes-safe] Engine Busy 重试 $EB_MAX_RETRY 次仍失败,输出最终结果" >&2
        cat "$_out"
        exit 1
    fi

    # 3) 其他错误(超时 rc=124 / 普通错误)→ 直接输出,不退避(留给上层的重试逻辑)
    cat "$_out"
    exit "$rc"
done

# 兜底
cat "$_out"
exit 0
