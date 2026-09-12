#!/usr/bin/env python3
"""评测预检门禁:全量评测开跑前断言环境健康,不满足直接退出。

背景(2026-09-08 DV1 假超时复盘):
- 数据面: sancha roll_forward 无真实断点跳过 → tenant 18 水位冻结 145h+,
  "连续3小时未更新"前提失真 → agent 无限深挖 → 1000s 超时。陈旧度会静默漂移。
- LLM 面: iagp Qwen 端点僵死时 hermes 内部 5 连重试耗 10min 才暴露,
  烧掉一题 1000s 才发现。

本脚本三项检查:
  1. 数据陈旧度: 两个租户 st_rsvr_r MAX(tm) 距今不得超过 STALE_MAX_H 小时。
     cron 每 50min roll 一次,断点年龄 0~1h 正常;上限 48h 覆盖"数据断档诊断"
     类题的合理前提(断 1~2 天)。
  2. hermes ping: 真实调一次 hermes chat -Q,须在 HERMES_PING_TIMEOUT_S 内返回非空。
  3. 真值前提 (v2, 2026-09-11): 逐题预执行 live_db truth_query——无行/非数值直接
     FAIL;带 truth_expectation 的题比对 value±tol / min / max 断言。堵死"前提腐烂
     静默进全量 → 跑 9 小时才发现 13 FAIL"(PG7 跨租户随机行/F22 计数泄漏均属此)。
     truth_query 无 tenant_id 字样的题给 WARN 不阻断。

用法: python3 eval/preflight.py   (退出码 0=通过, 2=不通过, 详情打到 stdout)
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "lib"))
sys.path.insert(0, str(_REPO))

STALE_MAX_H = 48    # 断档类题前提的校准带上限
HERMES_PING_TIMEOUT_S = 120

# (tenant_id, stcd, 名称, 重建脚本名)
WATCHED = [(18, "3", "三岔", "generate_sancha_data.py"),
           (20, "TQP", "桃曲坡", "generate_taoqupo_data.py")]


def check_staleness():
    from db import execute_query_list
    now = datetime.now()
    failures = []
    for tenant, stcd, name, fix_script in WATCHED:
        rows = execute_query_list(
            "SELECT MAX(tm) max_tm FROM st_rsvr_r "
            "WHERE tenant_id=%s AND stcd=%s AND deleted=0", (tenant, stcd))
        max_tm = rows[0]["max_tm"] if rows else None
        if not max_tm:
            failures.append(f"{name}(tenant {tenant} stcd {stcd}): st_rsvr_r 无数据!")
            continue
        last = max_tm if isinstance(max_tm, datetime) else datetime.strptime(
            str(max_tm), "%Y-%m-%d %H:%M:%S")
        age_h = (now - last).total_seconds() / 3600
        # cron 每 50min roll 一次,断点年龄 [0,1h) 属正常 freshly-rolled
        status = "OK" if age_h <= STALE_MAX_H else "FAIL"
        print(f"  [{status}] {name}(tenant {tenant}): 断点 {max_tm}, 陈旧 {age_h:.1f}h "
              f"(上限 {STALE_MAX_H}h)")
        if status == "FAIL":
            failures.append(
                f"{name}(tenant {tenant}) 数据陈旧 {age_h:.1f}h 超出上限 {STALE_MAX_H}h"
                f" — 先跑 forecasting/data/{fix_script} --roll (无效则 --clean 重建)")
    return failures


def check_hermes():
    env = {**os.environ}
    try:
        r = subprocess.run(
            ["hermes", "chat", "-q", "只回答一个字：通", "-Q"],
            capture_output=True, text=True, timeout=HERMES_PING_TIMEOUT_S, env=env)
        answer = (r.stdout or "").strip()
        ok = r.returncode == 0 and len(answer) >= 1
        print(f"  [{'OK' if ok else 'FAIL'}] hermes ping: rc={r.returncode}, "
              f"answer={answer[:40]!r}")
        if not ok:
            return [f"hermes ping 失败 rc={r.returncode} — LLM 端点可能不可用,勿开跑评测"]
        return []
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] hermes ping 超时(>{HERMES_PING_TIMEOUT_S}s)")
        return [f"hermes ping 超时(>{HERMES_PING_TIMEOUT_S}s) — LLM 端点可能僵死"]


def check_truth_premises():
    """v2: 逐题预执行 live_db truth_query,断言真值前提未腐烂(见模块 docstring 3)。"""
    from db import execute_query_list
    from eval.lib.schema import load_all
    failures, warns = [], []
    cases = [c for c in load_all(_REPO / "eval" / "cases") if c.truth_source == "live_db"]
    for c in cases:
        try:
            rows = execute_query_list(c.truth_query)
        except Exception as e:
            failures.append(f"{c.id}: truth_query 执行失败: {e}")
            continue
        if not rows:
            failures.append(f"{c.id}: truth_query 无结果(前提腐烂,如数据被清/过滤条件失配)")
            continue
        raw = list(rows[0].values())[0]
        try:
            val = float(raw)
        except (TypeError, ValueError):
            failures.append(f"{c.id}: truth 非数值 {raw!r}(判分链会 ERROR)")
            continue
        exp = c.truth_expectation or {}
        if "value" in exp and abs(val - float(exp["value"])) > float(exp.get("tol", 0)):
            failures.append(f"{c.id}: truth={val} 偏离期望 {exp['value']}±{exp.get('tol', 0)}")
        if "min" in exp and val < float(exp["min"]):
            failures.append(f"{c.id}: truth={val} 低于下限 {exp['min']}")
        if "max" in exp and val > float(exp["max"]):
            failures.append(f"{c.id}: truth={val} 超出上限 {exp['max']}(跨租户泄漏/数据漂移?)")
        if not exp:
            warns.append(f"{c.id}: 未配 truth_expectation(仅做了非空/数值检查,建议补)")
        if "tenant_id" not in (c.truth_query or "").lower():
            warns.append(f"{c.id}: truth_query 无 tenant_id 过滤——多租户表上属泄漏隐患")
    status = "FAIL" if failures else "OK"
    print(f"  [{status}] 真值前提: {len(cases)} 道 live_db 题预执行完毕")
    for w in warns:
        print(f"  [WARN] {w}")
    return failures


def main():
    print(f"[preflight] {datetime.now().isoformat(timespec='seconds')}")
    print("[1/3] 数据陈旧度:")
    failures = check_staleness()
    print("[2/3] hermes ping:")
    failures += check_hermes()
    print("[3/3] 真值前提 (v2):")
    try:
        failures += check_truth_premises()
    except Exception as e:
        failures.append(f"真值前提检查自身异常: {e}")
    if failures:
        print("\n[preflight] ❌ 门禁未通过:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(2)
    print("\n[preflight] ✅ 通过,可开跑评测")


if __name__ == "__main__":
    main()
