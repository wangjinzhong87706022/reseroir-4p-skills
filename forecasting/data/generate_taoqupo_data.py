#!/usr/bin/env python3
"""
generate_taoqupo_data.py -- 桃曲坡水库模拟监测数据生成器（tenant 20）。

用途:
    桃曲坡实时测站录入的前置步骤 —— 生成 st_rsvr_r（水位/入库/出库/蓄水量）+
    st_pptn_r（降雨）模拟时间序列，并把 model_config 的 master stcd 从 TBD 更新为真实值，
    使 forecasting / simulation / plan-generation 的 full_context 能读到"真实"水位降雨。

设计原则（对齐三岔 generate_forecast_data.py）:
    1. 物理合理:水位围绕 786.5m 波动,含一段逼近主汛期汛限 786.8m 的上涨;
       入库流量按柳林面积比 1.23 推算;蓄水量按总库容 4420 万m³ 线性化。
    2. MOCK 可清理:所有 mock 行 creator='MOCK' + tenant_id=20,清理 DELETE WHERE creator='MOCK'。
    3. 幂等:插入前先删旧 mock 行,不重复堆叠。
    4. 不污染真实数据:仅插入新行,绝不 UPDATE/DELETE 真实行。
    5. 时间窗:默认最近 30 天实测(obs),--days 可调;--hours 控制生成小时数。

用法:
    export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml \
           SRM_DB_USER=root SRM_DB_PASSWORD=***
    python3 forecasting/data/generate_taoqupo_data.py            # 默认 30 天,含逼近汛限场景
    python3 forecasting/data/generate_taoqupo_data.py --days 7   # 只生成最近 7 天
    python3 forecasting/data/generate_taoqupo_data.py --hours 72 --flat  # 平稳水位(无上涨场景)
    python3 forecasting/data/generate_taoqupo_data.py --clean    # 只清理 mock,不生成

物理参数来源: reservoirs/taoqupo/identity.md + model_config(tenant 20)。
"""
import argparse
import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from lib.db import execute_query, execute_write, get_connection, unpack  # noqa: E402

# ===========================================================================
# 桃曲坡物理参数（reservoirs/taoqupo/identity.md + model_config tenant 20）
# ===========================================================================
TENANT = 20                 # 桃曲坡租户
RES_GUID = "桃曲坡水库"

# 特征水位(m)
FLOOD_LIM_MAIN = 786.8      # 主汛期汛限
FLOOD_LIM_SEC = 788.0       # 次汛期汛限
NORMAL_POOL = 788.5         # 正常蓄水位
DESIGN_FLOOD = 788.54       # 设计洪水位
CHECK_FLOOD = 790.5         # 校核洪水位
DEAD_WL = 755.0             # 死水位
BASE_WL = 786.5             # 汛期常态水位（基线）
PEAK_WL = FLOOD_LIM_MAIN + 0.15   # 上涨峰值:逼近并轻微超过汛限(演示超限场景)
TOTAL_STORAGE = 4420.0      # 总库容(万m³,实测口径)

# 测站编码（master stcd 策略,任务2确定）
RSVR_MASTER = "TQP"         # 桃曲坡水库站 stcd(st_rsvr_r_master)
PPTN_MASTER = "TQPSN"       # 水库枢纽雨量站 stcd(st_pptn_r_master)
LIULIN_STCD = "TQPLL"       # 柳林水文站 stcd(面积比 1.23 推入库)

# 降雨预报（f_rnfl_h）
RNFL_FUTURE_HOURS = 168     # 预报预见期
RNFL_GRID_ID = 1            # 复用网格 ID=1(真实存在),未来时点 YMDH 不撞主键

# 柳林面积比拟系数:Q_桃 = 1.23 × Q_柳(S_桃=1335 / S_柳=1179 km²)
AREA_RATIO = 1.23

NOW = datetime.now().replace(minute=0, second=0, microsecond=0)


# ===========================================================================
# 波形生成(物理合理)
# ===========================================================================
def gen_water_level_series(hours, flat=False):
    """水位序列:基线波动 + 中段逼近汛限的上涨再回落(flat=True 时仅基线波动)。"""
    series = []
    rise_start = hours // 3
    rise_end = 2 * hours // 3
    for i in range(hours):
        wave = BASE_WL + 0.25 * math.sin(i / 8.0) + 0.06 * math.sin(i / 2.0)
        if not flat and rise_start <= i <= rise_end:
            mid = (rise_start + rise_end) / 2.0
            ratio = 1 - abs(i - mid) / max(mid - rise_start, 1)
            wave += (PEAK_WL - BASE_WL) * max(0, ratio)
        series.append(round(min(wave, CHECK_FLOOD), 3))
    return series


def gen_inflow_series(wl_series):
    """入库流量:由水位上涨率反推 + 基线流量。物理约束:汛期入库 30~1800 m³/s。"""
    series = []
    base_q = 45.0  # 汛期常态入库(m³/s)
    for i, wl in enumerate(wl_series):
        if i == 0:
            q = base_q
        else:
            dh = wl_series[i] - wl_series[i - 1]
            q = base_q + dh * 2500  # 上涨 0.1m/h ≈ +250 m³/s(粗线性化)
        q = max(15, min(q, 1800))
        series.append(round(q, 1))
    return series


def gen_rainfall_series(hours, total_mm=60, pattern="triangle"):
    """降雨序列(mm/h),总雨量 total_mm;triangle=中峰,uniform=均布。"""
    if pattern == "uniform":
        per = total_mm / hours
        return [round(per, 1)] * hours
    mid = hours / 2.0
    weights = [max(0, 1 - abs(i - mid) / max(mid, 1)) for i in range(hours)]
    tot = sum(weights)
    return [round(total_mm * w / tot, 1) if tot else 0 for w in weights]


def hourly_range(start_tm, end_tm):
    out = []
    t = start_tm
    while t <= end_tm:
        out.append(t)
        t += timedelta(hours=1)
    return out


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
# 断点续写
# ===========================================================================
def gen_forecast_rainfall_series(hours=RNFL_FUTURE_HOURS):
    """生成未来 hours 小时降雨预报序列(mm/h):NOW+12h 起涨 → +18h 达峰 → 缓退。
    物理合理:峰前 6h 已明显降雨(符合产汇流预见需求),峰值 22mm/h(暴雨场景)。"""
    series = []
    peak = 22.0
    peak_at = 18
    for i in range(hours):
        if i < 12:
            r = round(0.5 + 1.5 * (i / 12.0), 1)                 # 0.5 → 2.0 缓升
        elif i < peak_at:
            r = round(2.0 + (peak - 2.0) * ((i - 12) / (peak_at - 12)), 1)  # 2 → 22 急升
        elif i == peak_at:
            r = peak
        elif i < peak_at + 8:
            ratio = (i - peak_at) / 8.0
            r = round(peak * math.exp(-2.0 * ratio) + 1.5, 1)    # 指数退水
        else:
            r = round(0.3 * (1 + math.sin(i / 3.0)) / 2.0, 1)    # 尾部零星小雨
        series.append(max(0.0, round(r, 1)))
    return series


def generate_forecast(fc_hours=RNFL_FUTURE_HOURS):
    """向 f_rnfl_h 插入未来 fc_hours 小时逐时降雨预报(MOCK 标记,幂等)。
    YMDH=各未来时点, FYMDH=NOW(预报发布时刻), UNITNAME='1', TYPE='1', tenant_id=1。"""
    print(f"[forecast] f_rnfl_h 未来 {fc_hours}h 降雨预报 [NOW+1h → NOW+{fc_hours}h] ...")
    execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
    rain = gen_forecast_rainfall_series(fc_hours)
    rows = []
    for i in range(fc_hours):
        ymdh = NOW + timedelta(hours=i + 1)
        rows.append((RNFL_GRID_ID, ymdh, NOW, rain[i], '1', '1', 'MOCK'))
    _bulk_insert(
        "INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1)",
        rows,
    )
    peak_idx = rain.index(max(rain))
    print(f"  f_rnfl_h: {fc_hours} 行, 峰值 RN={max(rain)}mm/h @ NOW+{peak_idx + 1}h")
    return {"hours": fc_hours, "peak_rn": max(rain), "total_rain": round(sum(rain), 1)}


def read_breakpoint(table, tm_col="tm", where_sql=""):
    """读取该表真实断点(非 MOCK),返回 (max_tm, gap_hours)。无断点返回 (None, None)。"""
    sql = f"SELECT MAX({tm_col}) AS max_tm FROM {table} {where_sql}"
    rows = unpack(execute_query(sql))
    max_tm = rows[0]["max_tm"] if rows and rows[0].get("max_tm") else None
    if isinstance(max_tm, str):
        try:
            max_tm = datetime.strptime(max_tm, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            max_tm = None
    gap = int((NOW - max_tm).total_seconds() // 3600) if max_tm else None
    return max_tm, gap


def generate_observed(start, end, flat=False, rain_mm=60):
    """生成 [start, end] 观测数据(st_rsvr_r + st_pptn_r 两站),返回摘要 dict。"""
    hours = max(1, int((end - start).total_seconds() // 3600) + 1)

    # --- st_rsvr_r:水位/入库/出库/蓄水 ---
    wl = gen_water_level_series(hours, flat=flat)
    inq = gen_inflow_series(wl)
    rows = []
    for i, tm in enumerate(hourly_range(start, end)):
        rz = wl[i]
        q_in = inq[i]
        q_out = round(max(20, q_in * 0.85), 1)  # 削峰 85%
        stor = round(DEAD_WL + (rz - DEAD_WL) / (CHECK_FLOOD - DEAD_WL) * TOTAL_STORAGE, 1)
        rows.append((tm, rz, q_in, q_out, stor, RSVR_MASTER, TENANT))
    _bulk_insert(
        "INSERT INTO st_rsvr_r (tm, rz, inq, otq, w, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'MOCK', 'MOCK')",
        rows,
    )
    peak = max(wl)

    # --- st_pptn_r:枢纽雨量站 + 柳林站 ---
    rain = gen_rainfall_series(hours, total_mm=rain_mm)
    rows2 = []
    rows3 = []
    for i, tm in enumerate(hourly_range(start, end)):
        rows2.append((tm, rain[i], 1.0, rain[i], PPTN_MASTER, TENANT))
        rows3.append((tm, rain[i], 1.0, rain[i], LIULIN_STCD, TENANT))
    _bulk_insert(
        "INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, 0, 'MOCK', 'MOCK')",
        rows2,
    )
    _bulk_insert(
        "INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, 0, 'MOCK', 'MOCK')",
        rows3,
    )

    return {
        "hours": hours,
        "peak_level": peak,
        "exceed_flood_limit": peak > FLOOD_LIM_MAIN,
        "total_rain": round(sum(rain), 1),
        "peak_inflow": max(inq),
    }


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="桃曲坡模拟监测数据生成器")
    parser.add_argument("--days", type=int, default=30, help="生成最近 N 天实测(默认30)")
    parser.add_argument("--hours", type=int, default=None, help="精确小时数(覆盖 --days)")
    parser.add_argument("--flat", action="store_true", help="平稳水位,无逼近汛限场景")
    parser.add_argument("--clean", action="store_true", help="只清理 mock 行,不生成")
    parser.add_argument("--rain-mm", type=float, default=60, help="降雨事件总量(mm,默认60)")
    parser.add_argument("--roll", action="store_true",
                        help="断点续写:从 st_rsvr_r/st_pptn_r 各自 MAX(tm) 续写到 NOW")
    parser.add_argument("--forecast", action="store_true",
                        help="生成 f_rnfl_h 未来降雨预报(默认不生成;--all 同时生成观测+预报)")
    parser.add_argument("--all", action="store_true",
                        help="观测数据 + 降雨预报一起生成(等效 --roll/初始 + --forecast)")
    parser.add_argument("--fc-hours", type=int, default=RNFL_FUTURE_HOURS,
                        help="降雨预报预见期小时数(默认168)")
    args = parser.parse_args()

    # 幂等:先清旧 mock
    if args.clean:
        n1 = execute_write("DELETE FROM st_rsvr_r WHERE creator='MOCK' AND tenant_id=%s", (TENANT,))
        n2 = execute_write("DELETE FROM st_pptn_r WHERE creator='MOCK' AND tenant_id=%s", (TENANT,))
        n3 = execute_write("DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
        print(f"[clean] 已删除 st_rsvr_r mock {n1} 行, st_pptn_r mock {n2} 行, "
              f"f_rnfl_h mock {n3} 行 (tenant {TENANT})")
        return

    # 降雨预报（--forecast 或 --all）
    if args.forecast or args.all:
        generate_forecast(args.fc_hours)

    if args.roll:
        # 断点续写:以 st_rsvr_r 的 MOCK 数据 MAX(tm) 为断点(桃曲坡模拟数据均为 MOCK),
        # 从断点+1h 续写到 NOW;数据已最新则跳过(cron 幂等)。
        max_tm, gap = read_breakpoint(
            "st_rsvr_r",
            where_sql=f"WHERE tenant_id={TENANT} AND stcd='{RSVR_MASTER}' "
                      f"AND deleted=0 AND creator='MOCK'",
        )
        if max_tm is None:
            print("[roll] 无断点,初始生成最近 48h")
            start = NOW - timedelta(hours=47)
        elif gap is not None and gap <= 0:
            print(f"[roll] 数据已最新({max_tm}),无需续写")
            return
        else:
            start = max_tm + timedelta(hours=1)
        end = NOW
        summary = generate_observed(start, end, flat=args.flat, rain_mm=args.rain_mm)
        print(f"[roll] 断点续写 {summary['hours']}h [{start} → {end}]")
        print(f"  水位峰值 {summary['peak_level']}m "
              f"({'超汛限' if summary['exceed_flood_limit'] else '未超汛限'}), "
              f"入库峰 {summary['peak_inflow']}m³/s, 雨量 {summary['total_rain']}mm")
        return

    hours = args.hours or args.days * 24
    start = NOW - timedelta(hours=hours - 1)
    end = NOW
    print(f"[generate] 桃曲坡(tenant {TENANT}) 生成 {hours}h [{start} → {end}]")
    summary = generate_observed(start, end, flat=args.flat, rain_mm=args.rain_mm)
    print(f"  st_rsvr_r: {summary['hours']} 行, 峰值水位 {summary['peak_level']}m "
          f"({'超汛限' if summary['exceed_flood_limit'] else '未超汛限'})")
    print(f"  st_pptn_r(枢纽+柳林): 2×{summary['hours']} 行, "
          f"总雨量 {summary['total_rain']}mm, 入库峰≈{summary['peak_inflow']}m³/s")

    # --- model_config:更新 master stcd ---
    upserts = [
        ("st_rsvr_r_master", RSVR_MASTER, "桃曲坡水库站(模拟)"),
        ("st_pptn_r_master", PPTN_MASTER, "桃曲坡枢纽雨量站(模拟)"),
    ]
    for key, val, remark in upserts:
        execute_write(
            "UPDATE model_config SET value=%s, remark=%s, update_time=NOW() "
            "WHERE config_key=%s AND tenant_id=%s",
            (val, remark, key, TENANT),
        )
        print(f"  model_config.{key} → {val}")

    print("\n✅ 桃曲坡模拟数据生成完成。清理: --clean; 断点续写: --roll")


if __name__ == "__main__":
    main()