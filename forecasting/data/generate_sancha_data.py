#!/usr/bin/env python3
"""
三岔水库模拟实时数据生成器（mock）。

为 tenant 18 的 st_rsvr_r（水位/入库/出库/蓄水量）+ f_rnfl_h（降雨预报）续写/重建
MOCK 数据，配合 supervisor 闭环形成"数据→研判→方案"全链路可演示。

物理参数来源: reservoirs/sancha/identity.md + characteristic-levels.md + model_config(tenant 18)。
桃曲坡见 generate_taoqupo_data.py；本脚本为三岔专属（基面 ~460m，汛限 462.5m）。
"""
import argparse
import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from lib.db import execute_query, execute_query_list, get_connection, unpack  # noqa: E402
from lib.db_write import execute_write  # noqa: E402 -- 显式写通道（仅造数）


def _bulk_insert(sql, rows):
    """批量插入（executemany），幂等依赖调用前的 DELETE。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ===========================================================================
# 三岔物理参数（reservoirs/sancha/identity.md + characteristic-levels.md）
# ===========================================================================
TENANT = 18                 # 三岔租户
RES_GUID = "三岔水库"

# 特征水位(m)（characteristic-levels.md：基面 ~460m）
FLOOD_LIM = 462.5           # 汛限/正常蓄水位（三岔无主汛/次汛分段）
DESIGN_FLOOD = 461.96       # 设计洪水位（百年一遇）
CHECK_FLOOD = 462.88        # 校核洪水位（千年一遇）
DEAD_WL = 451.0             # 死水位
BASE_WL = 459.18            # 常态水位（test-questions.md 测试样本）
PEAK_WL = FLOOD_LIM + 0.15  # 上涨峰值:逼近并轻微超过汛限(演示超限场景)
TOTAL_STORAGE = 22870.0     # 总库容(万m³, identity.md)

# 测站编码（identity.md master stcd）
RSVR_MASTER = "3"           # 三岔水库站 stcd(st_rsvr_r_master)
PPTN_MASTER = "46"          # 三岔雨量主站 stcd(st_pptn_r_master)

# 降雨预报（f_rnfl_h）
RNFL_FUTURE_HOURS = 168     # 预报预见期
RNFL_GRID_ID = 2            # 三岔网格 ID(与桃曲坡 ID=1 区隔)

NOW = datetime.now().replace(minute=0, second=0, microsecond=0)

# 波形相位基准（确定性：同 tm 同值，roll 分段续写幂等可复算）
_EPOCH = datetime(2026, 8, 1)


# ===========================================================================
# st_rsvr_r: 水位/入库/出库/蓄水量
# ===========================================================================

def _storage_from_wl(wl):
    """简化水位→库容（线性插值 characteristic-levels.md 关键节点）。"""
    nodes = [(451.0, 3900), (455.0, 5200), (458.0, 6455), (462.0, 8723),
             (462.5, 9064), (465.0, 10819), (468.0, 14500)]
    if wl <= nodes[0][0]:
        return nodes[0][1]
    if wl >= nodes[-1][0]:
        return nodes[-1][1]
    for i in range(len(nodes) - 1):
        w0, s0 = nodes[i]
        w1, s1 = nodes[i + 1]
        if w0 <= wl <= w1:
            return s0 + (s1 - s0) * (wl - w0) / (w1 - w0)
    return 9064


def _discharge_from_wl(wl):
    """简化水位→泄量（characteristic-levels.md 泄流曲线）。"""
    nodes = [(451.0, 0), (453.0, 20), (455.0, 80), (458.0, 87),
             (462.0, 99), (462.5, 94), (468.0, 500)]
    if wl <= nodes[0][0]:
        return nodes[0][1]
    if wl >= nodes[-1][0]:
        return nodes[-1][1]
    for i in range(len(nodes) - 1):
        w0, q0 = nodes[i]
        w1, q1 = nodes[i + 1]
        if w0 <= wl <= w1:
            return q0 + (q1 - q0) * (wl - w0) / (w1 - w0)
    return 95.1  # 安全泄量兜底


def gen_observation_series(start, end, stcd=RSVR_MASTER):
    """生成 [start, end] 逐时观测数据（st_rsvr_r），返回摘要 dict。
    水位在 BASE_WL → PEAK_WL 间正弦波动，入库随降雨变化，出库按泄流曲线。"""
    rows = []
    total_h = int((end - start).total_seconds() // 3600)
    for i in range(total_h + 1):
        tm = start + timedelta(hours=i)
        # 水位：绝对时钟相位（72h 主周期 + 24h 日周期 + 确定性伪噪声）。
        # 旧实现相位相对本次调用起点（i/total_h），每次 roll 都从正弦起点走两个点
        # → 时序上退化为 BASE/PEAK 两值方波（2026-09-02 起）。改绝对相位后续写无缝。
        hours = (tm - _EPOCH).total_seconds() / 3600.0
        phase72 = hours / 72.0 * 2 * math.pi
        phase24 = hours / 24.0 * 2 * math.pi
        wl = (BASE_WL
              + (PEAK_WL - BASE_WL) * 0.5 * (1 + math.sin(phase72))
              + 0.05 * math.sin(phase24)
              + 0.03 * math.sin(hours * 2.7))
        # 入库：基流 + 随主周期的汛期脉冲
        inq = 15.0 + 40.0 * max(0, math.sin(phase72 - math.pi / 4))
        # 出库：按泄流曲线 + 人工调控（超汛限加大泄）
        otq = _discharge_from_wl(wl)
        if wl > FLOOD_LIM:
            otq = min(otq + 30, 192)  # 不超最大泄流能力
        w = _storage_from_wl(wl)
        rows.append((tm, round(wl, 3), round(inq, 1), round(otq, 1),
                     round(w, 0), stcd, TENANT, 0, 'MOCK', 'sancha'))
    _bulk_insert(
        "INSERT INTO st_rsvr_r (tm, rz, inq, otq, w, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    return {"rows": len(rows), "stcd": stcd,
            "wl_range": (round(min(r[1] for r in rows), 3),
                         round(max(r[1] for r in rows), 3)),
            "max_tm": rows[-1][0].strftime("%Y-%m-%d %H:%M:%S")}


# ===========================================================================
# f_rnfl_h: 降雨预报
# ===========================================================================

def generate_forecast(fc_hours=RNFL_FUTURE_HOURS):
    """向 f_rnfl_h 插入未来 fc_hours 小时逐时降雨预报(MOCK 标记,幂等)。
    三岔汛期暴雨场景:峰值 18mm/h(比桃曲坡 22mm/h 弱,流域面积小)。"""
    print(f"[forecast] f_rnfl_h 未来 {fc_hours}h 降雨预报 [NOW+1h → NOW+{fc_hours}h] ...")
    execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK' AND tenant_id=%s", (TENANT,))

    rain = []
    for i in range(1, fc_hours + 1):
        # 双峰暴雨:主峰 @ NOW+18h(18mm/h),次峰 @ NOW+48h(12mm/h)
        t = i
        main = 18 * math.exp(-((t - 18) ** 2) / (2 * 9 ** 2))
        sec = 12 * math.exp(-((t - 48) ** 2) / (2 * 12 ** 2))
        r = max(0, round(main + sec, 2))
        rain.append(r)

    rows = []
    for i, r in enumerate(rain):
        ymdh = NOW + timedelta(hours=i + 1)
        fymdh = NOW
        rows.append((RNFL_GRID_ID, ymdh, fymdh, r, 'mm', '预报', 'MOCK', 0, TENANT))
    _bulk_insert(
        "INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    peak = max(rain)
    peak_idx = rain.index(peak)
    print(f"  f_rnfl_h: {fc_hours} 行, 峰值 RN={peak}mm/h @ NOW+{peak_idx + 1}h")
    return {"rows": len(rows), "peak_rn": peak, "peak_hour": peak_idx + 1}


# ===========================================================================
# 断点续写
# ===========================================================================

def roll_forward(stcd=RSVR_MASTER):
    """读 st_rsvr_r 断点,从断点+1h 续写到 NOW。
    数据已最新(断点 >= NOW-1h)则跳过(幂等)。
    断点取全表 MAX(tm):本库模拟数据 creator 均为 'MOCK',按 creator<>'MOCK'
    找断点会永远查不到 → 每次跳过 → 数据冻结陈旧(2026-09-02 起 145h+,DV1 假超时根因)。
    桃曲坡(generate_taoqupo_data.py)即按含 MOCK 的 MAX(tm) 续写,此处对齐其口径。"""
    r = execute_query_list(
        "SELECT MAX(tm) as max_tm FROM st_rsvr_r "
        "WHERE deleted=0 AND stcd=%s AND tenant_id=%s",
        (stcd, TENANT)
    )[0]
    last = r["max_tm"]
    if not last:
        print("[roll] 无任何断点,跳过续写(用 --clean + --days 初始重建)")
        return {"skipped": True, "reason": "no_breakpoint"}
    last_dt = last if isinstance(last, datetime) else datetime.strptime(str(last), "%Y-%m-%d %H:%M:%S")
    gap_h = int((NOW - last_dt).total_seconds() // 3600)
    if gap_h <= 1:
        print(f"[roll] 数据已最新(断点 {last}, age={gap_h}h),跳过续写")
        return {"skipped": True, "reason": "already_fresh", "gap_h": gap_h}
    print(f"[roll] 断点 {last}, gap={gap_h}h, 续写 {gap_h}h ...")
    summary = gen_observation_series(last_dt + timedelta(hours=1), NOW, stcd)
    print(f"  st_rsvr_r: +{summary['rows']} 行, max_tm={summary['max_tm']}")
    return summary


# ===========================================================================
# 主入口
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="三岔水库模拟数据生成器")
    parser.add_argument("--days", type=int, default=30, help="重建天数(仅 --clean 模式)")
    parser.add_argument("--forecast", action="store_true", help="生成/重建未来168h降雨预报")
    parser.add_argument("--roll", action="store_true", help="断点续写(真实断点+1h → NOW)")
    parser.add_argument("--clean", action="store_true",
                        help="按 creator='MOCK' 清三岔模拟数据后重建")
    args = parser.parse_args()

    if not any([args.forecast, args.roll, args.clean]):
        parser.print_help()
        return

    if args.clean:
        print(f"[clean] 清三岔 tenant={TENANT} MOCK 数据...")
        execute_write("DELETE FROM st_rsvr_r WHERE creator='MOCK' AND tenant_id=%s", (TENANT,))
        execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK' AND tenant_id=%s", (TENANT,))
        start = NOW - timedelta(days=args.days)
        print(f"[clean] 重建 {args.days} 天观测数据 [{start} → {NOW}] ...")
        summary = gen_observation_series(start, NOW)
        print(f"  st_rsvr_r: {summary['rows']} 行, wl_range={summary['wl_range']}, max_tm={summary['max_tm']}")

    if args.roll:
        roll_forward()

    if args.forecast:
        generate_forecast()

    print("✅ 三岔 mock 数据生成完成")


if __name__ == "__main__":
    main()
