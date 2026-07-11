#!/usr/bin/env python3
"""
预报模拟数据生成器:断点接续 + NOW 滚动 + mock 源/精度。
读各表 MAX(tm) 真实断点,续写到 NOW;不污染真实数据(MOCK 标记)。
对标 simulation/tests/generate_test_data_v2.py。

设计原则:
  1. 断点接续:从各表 MAX(tm)+1h 续写到 NOW(每小时 1 行),保持时序连续。
  2. 物理合理:水位围绕 459~461 波动,含一段逼近汛限 462.5 的上涨;流量/降雨物理量级正确。
  3. MOCK 可清理:每条 mock 行可识别 —— alias='MOCK' 或 taskid LIKE 'MOCK%'。
  4. 幂等:重跑前先删旧 mock 行(基于 MOCK 标记),再插入;不重复堆叠。
  5. 不污染真实数据:仅插入新行,绝不 UPDATE/DELETE 真实行。

用法:
  export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml SRM_DB_USER=root SRM_DB_PASSWORD=...
  python3 data/generate_forecast_data.py --extend-all          # 跑全部 extender
  python3 data/generate_forecast_data.py --extend-all --via-mysql-cli   # 生成 SQL 文件后用 mysql 客户端执行
"""
import sys
import os
import json
import math
import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from query_utils import execute_query, execute_query_list, unpack  # noqa: E402

NOW = datetime.now().replace(minute=0, second=0, microsecond=0)
MOCK_TENANT = 18  # 三岔;mock 行用 alias='MOCK' 或 taskid LIKE 'MOCK%'

# ---------------------------------------------------------------------------
# 物理常量(三岔水库实测/设计值,来自 baseline_seed.sql)
# ---------------------------------------------------------------------------
MAX_WL = 462.88       # 设计洪水位 (model_config max_water_level)
MIN_WL = 451.0        # 死水位 (model_config min_water_level)
FLOOD_LIM = 462.5     # 主汛期汛限 (att_res_flse_lim)
BASE_WL = 459.5       # 续写基线水位(汛期常态)
RSVR_MASTER = '3'     # model_config st_rsvr_r_master (水库 master stcd)
PPTN_MASTER = '46'    # model_config st_pptn_r_master (降雨 master stcd)


# ===========================================================================
# Window 模型:把"实测窗口"与"预报窗口"显式参数化,取代硬编码 NOW±N。
#   - default (no mode flag): obs [NOW-30d, NOW], fc [NOW, NOW+168h]  ← 标准 demo 窗口
#   - --start/--end         : obs [s, min(e,NOW)], fc [max(s,NOW), e] ← 自定义时间窗
#   - --roll                : obs_start=None(哨兵,由 extender 内 read_breakpoint 决定),
#                             fc [NOW, NOW+168h] ← 断点续到 NOW(cron 用)
# obs_start=None 是 --roll 的哨兵:extend_observed 见此值即改用 read_breakpoint。
# ===========================================================================
DEFAULT_OBS_DAYS = 30
FC_HOURS = 168


@dataclass
class Window:
    """obs_* = 实测窗口;fc_* = 预报窗口。obs_start 可为 None(--roll 哨兵)。"""
    obs_start: datetime   # 可为 None(--roll:由 read_breakpoint 决定)
    obs_end: datetime
    fc_start: datetime
    fc_end: datetime


def resolve_window(args, now):
    """默认=标准 demo 窗口(实测-30d→NOW,预报 NOW→+168h);
    --start/--end=自定义;--roll=断点续到 NOW(obs_start=None 哨兵)。

    args 需含 start/end/roll 字段(argparse.Namespace 即可)。
    now  为"当前时刻"(测试可注入固定值;生产用模块级 NOW)。
    """
    if getattr(args, 'start', None) or getattr(args, 'end', None):
        s = args.start or (now - timedelta(days=DEFAULT_OBS_DAYS))
        e = args.end or (now + timedelta(hours=FC_HOURS))
        return Window(s, min(e, now), max(s, now), e)
    if getattr(args, 'roll', False):
        # 断点续写:obs 由各 extender 内部 read_breakpoint 决定;这里给哨兵
        return Window(None, now, now, now + timedelta(hours=FC_HOURS))
    # 默认 demo 窗口
    return Window(
        now - timedelta(days=DEFAULT_OBS_DAYS), now,
        now, now + timedelta(hours=FC_HOURS),
    )


# ===========================================================================
# 1. 断点读取
# ===========================================================================
def read_breakpoint(table, tm_col='tm', extra_where='', via_cli_buf=None):
    """返回 (max_tm, gap_hours)。
    max_tm: 该表最新真实断点(datetime 或 None);gap_hours: 断点到 NOW 的小时数(无断点则 None)。
    via_cli_buf: 若非 None,则不查库而是把 SQL 追加到该列表(mysql-cli 模式)。
    """
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT MAX({tm_col}) AS max_tm FROM {table} {where}"
    if via_cli_buf is not None:
        # mysql-cli 模式下无法回读,退化为 None(由 caller 决定是否从头生成)
        return None, None
    row = unpack(execute_query(sql))
    max_tm = row[0]['max_tm'] if row and row[0].get('max_tm') else None
    # query_utils 把 datetime 序列化成字符串 'YYYY-MM-DD HH:MM:SS'
    if isinstance(max_tm, str):
        try:
            max_tm = datetime.strptime(max_tm, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            max_tm = None
    gap = int((NOW - max_tm).total_seconds() // 3600) if max_tm else None
    return max_tm, gap


def hourly_range(start_tm, end_tm):
    """生成 [start_tm, end_tm] 每小时 datetime 列表(闭区间,步长 1h)。"""
    out = []
    t = start_tm
    while t <= end_tm:
        out.append(t)
        t += timedelta(hours=1)
    return out


# ===========================================================================
# 2. 水位/流量波形生成(物理合理)
# ===========================================================================
def gen_water_level_wave(hours, base=BASE_WL, peak=FLOOD_LIM - 0.3):
    """生成 hours 小时水位序列:基线波动 + 一段逼近汛限的上涨再回落。
    返回 list[float],值域 [base-0.8, peak]。
    """
    series = []
    # 上涨发生在中段 1/3 ~ 2/3
    rise_start = hours // 3
    rise_end = 2 * hours // 3
    for i in range(hours):
        # 基线小幅波动(正弦 + 微噪声)
        wave = base + 0.4 * math.sin(i / 6.0) + 0.1 * math.sin(i / 2.0)
        if rise_start <= i <= rise_end:
            # 三角上涨:从基线爬到 peak 再回落
            mid = (rise_start + rise_end) / 2.0
            ratio = 1 - abs(i - mid) / max(mid - rise_start, 1)
            wave += (peak - base) * max(0, ratio)
        series.append(round(min(wave, MAX_WL), 3))
    return series


def gen_inflow_series(wl_series, base_q=120.0):
    """根据水位序列反推入库流量(简化:水位上涨率 → 入库增量)。
    物理约束:汛期入库 50~800 m³/s。
    """
    series = []
    for i, wl in enumerate(wl_series):
        if i == 0:
            q = base_q
        else:
            # 水位上涨 0.1m/h ≈ +50 m³/s(粗略线性化)
            dh = wl_series[i] - wl_series[i - 1]
            q = base_q + dh * 500
        q = max(30, min(q, 800))
        series.append(round(q, 1))
    return series


def gen_rainfall_series(hours, total_mm=80, pattern='triangle'):
    """生成 hours 小时降雨序列(mm),总雨量 total_mm。"""
    if pattern == 'uniform':
        per = total_mm / hours
        return [round(per, 1)] * hours
    # triangle(默认):中峰
    mid = hours / 2.0
    weights = [max(0, 1 - abs(i - mid) / max(mid, 1)) for i in range(hours)]
    tot = sum(weights)
    return [round(total_mm * w / tot, 1) if tot else 0 for w in weights]


# ---------------------------------------------------------------------------
# 跨源物理一致性:一个降雨事件驱动 forecast/observed/water_level/inflow,
# 使 f_rnfl_h(预报雨)↔ st_pptn_r(实测雨,滞后+偏差)↔ st_rsvr_r(水位响应)
# ↔ st_mx_preset_cal_r(模型预报水位,同趋势) 同源一致 —— demo 才能讲一条故事线。
# 物理简化(非水文模型):obs 滞后 2h + ±15% 偏差;水位 lag 4h,径流系数 0.6,
#   1mm 降雨 ≈ +0.012m;水位钳制 [MIN_WL, MAX_WL]。
# ---------------------------------------------------------------------------
OBS_LAG_HOURS = 2      # 实测雨滞后预报 2h(预报先到、实测随后)
WL_LAG_HOURS = 4       # 水位响应滞后降雨 4h(汇流时间)
RUNOFF_COEFF = 0.6     # 径流系数(产流比例)
WL_GAIN_PER_MM = 0.02  # 水位上涨系数:lag_rain × 0.6 × 0.02 = 0.012m/mm(经验线性化)
OBS_BIAS = 0.85        # 实测 = 预报 × 0.85(精度演示:预报偏高 15%)


def gen_coherent_event(window, total_mm=120, peak_mmh=22):
    """一个降雨事件 → 驱动四源同源序列(forecast雨 / observed雨 / water_level / inflow)。

    把整场暴雨锚定到 [obs_start, fc_end] 时间轴上:暴雨 onset 落在 obs 末段(最近实测"刚开始下雨"),
    暴雨 peak 落在 fc 前段(预报"未来 X 小时达峰"),暴雨 tail 在 fc 中后段。这样一个连续雨型被
    obs/fc 两窗口共同覆盖,实测雨是预报雨"过去那一截"的现场重现,二者天然同源且时序连贯。

    forecast_rain[]: fc 窗口段雨型(暴雨峰在 fc 前段;total_mm≥80 走 storm 否则 triangle)。
    observed_rain[]: obs 窗口段雨型 + ×OBS_BIAS(±15% 偏差,精度演示素材);末段衔接 storm onset。
    water_level[]: 由 observed_rain 累积驱动(径流系数 RUNOFF_COEFF,汇流滞后 WL_LAG_HOURS),
        1mm → +0.012m;从 BASE_WL 起算,钳制 [MIN_WL, MAX_WL]。
    inflow[]: 由 water_level 经 gen_inflow_series 反推。

    时序保证:fc_rain peak(最早,未来)→ obs_rain peak(实测,滞后 + 在 obs 窗口末段)→
        wl peak(再滞后 WL_LAG_HOURS)→ model_wl(同趋势,见 _model_forecast_water_level)。
    返回 dict: {forecast, observed, water_level, inflow},各为 list[float]。
    """
    fc_hours = max(1, int((window.fc_end - window.fc_start).total_seconds() // 3600))
    # obs_start 可为 None(--roll 哨兵:实测起点由 read_breakpoint 动态决定)。
    # 此时无法做跨源锚定,退化为 obs_hours=1(仅占位,axis 主体走 fc 段),
    # 与 extend_observed/_model_forecast_water_level 的 --roll 回退路径一致。
    if window.obs_start is None:
        obs_hours = 1
    else:
        obs_hours = max(1, int((window.obs_end - window.obs_start).total_seconds() // 3600) + 1)

    # 1) 生成一条覆盖整轴 [obs_start, fc_end] 的连续暴雨序列(每小时 1 点)。
    total_hours = obs_hours + fc_hours
    if total_mm >= 80:
        full = gen_forecast_rainfall_storm(total_hours)
        # storm 默认峰 22mm/h 在 idx 18;按 peak_mmh 缩放
        storm_peak = max(full) if full else peak_mmh
        if peak_mmh and storm_peak > 0:
            scale = peak_mmh / storm_peak
            full = [round(r * scale, 1) for r in full]
    else:
        full = gen_rainfall_series(total_hours, total_mm, pattern='triangle')

    # 2) 锚定:把 storm 峰(idx=PEAK_OFFSET)对齐到 fc 窗口前段 ——
    #    即把整条 full 向后平移,使 full[PEAK_OFFSET] 落在 fc_start + NOW_OFFSET_STORM_PEAK。
    #    obs 窗口(轴前段 obs_hours 点)取 onset/tail;fc 窗口(后段 fc_hours 点)含主峰。
    PEAK_OFFSET = 18                 # storm 雨峰在 full 中的相对位置(同 gen_forecast_rainfall_storm)
    NOW_OFFSET_STORM_PEAK = 7        # 雨峰锚定到 fc_start + 7h(预报"未来 7h 达峰")
    shift = (obs_hours + NOW_OFFSET_STORM_PEAK) - PEAK_OFFSET  # full 实际起始相对轴 0 的偏移
    axis = [0.0] * total_hours
    for k, r in enumerate(full):
        pos = k + shift
        if 0 <= pos < total_hours:
            axis[pos] = r

    # 3) 切片:obs 段 / fc 段
    forecast = axis[obs_hours:obs_hours + fc_hours]
    if len(forecast) < fc_hours:
        forecast = forecast + [0.0] * (fc_hours - len(forecast))
    observed_base = axis[:obs_hours]

    # 4) 实测 = 锚定雨型 × OBS_BIAS(精度偏差);保证 obs 末段(接近 NOW)已见 onset 上升
    observed = [round(max(0.0, r * OBS_BIAS), 1) for r in observed_base]

    # 5) 水位响应:累积 observed 雨量 → 水位上涨(汇流滞后 WL_LAG_HOURS,径流 RUNOFF_COEFF)
    #    1mm 降雨 → +0.012m(RUNOFF_COEFF × WL_GAIN_PER_MM = 0.6 × 0.02 = 0.012)
    wl = []
    level = BASE_WL
    for i in range(obs_hours):
        lag_rain = observed[i - WL_LAG_HOURS] if i >= WL_LAG_HOURS else 0.0
        level += lag_rain * RUNOFF_COEFF * WL_GAIN_PER_MM
        level = max(MIN_WL, min(level, MAX_WL))
        wl.append(round(level, 3))
    inflow = gen_inflow_series(wl)
    return {'forecast': forecast, 'observed': observed,
            'water_level': wl, 'inflow': inflow}


def _model_forecast_water_level(window, fc_horizon):
    """模型预报水位(fc 段,未来):与实测同源同一降雨事件,趋势延续。

    取 gen_coherent_event(window) 的实测水位末值为起点,用 forecast 雨(同事件)继续累积
    (RUNOFF_COEFF × WL_GAIN_PER_MM,汇流滞后 WL_LAG_HOURS),钳制 [MIN_WL, MAX_WL]。
    obs 段不可用(--roll 动态断点)或 fc_horizon 极小时,回退独立 gen_water_level_wave。
    这样实测水位峰(obs)与模型预报水位峰(fc)由同一雨型驱动,呈现"实测已涨→模型预报继续涨"
    的连贯故事(实测峰早于模型预报峰,因 fc 在 obs 之后)。
    """
    if window.obs_start is None or fc_horizon <= 0:
        return gen_water_level_wave(fc_horizon, base=BASE_WL, peak=FLOOD_LIM - 0.1)
    event = gen_coherent_event(window)
    obs_wl = event['water_level']
    fc_rain = event['forecast']
    start_level = obs_wl[-1] if obs_wl else BASE_WL
    wl = []
    level = start_level
    for i in range(fc_horizon):
        # 汇流滞后:fc 时点 i 的水位响应对应 fc 时点 i-WL_LAG_HOURS 的预报雨。
        # 前 WL_LAG_HOURS 个 fc 时点的滞后源仍在 obs 段(obs 水位已含其响应),此处不重复计入,
        # 故该段水位保持 start_level 平滑过渡,从 i==WL_LAG_HOURS 起开始响应 fc 预报雨。
        if i >= WL_LAG_HOURS:
            j = i - WL_LAG_HOURS
            lag_rain = fc_rain[j] if j < len(fc_rain) else 0.0
        else:
            lag_rain = 0.0
        level += lag_rain * RUNOFF_COEFF * WL_GAIN_PER_MM
        level = max(MIN_WL, min(level, MAX_WL))
        wl.append(round(level, 3))
    # 若累积为零(fc 全为滞后期/无雨),用 obs 末水位 + 轻微衰减趋势兜底,保证非完全平直
    if wl and max(wl) - min(wl) < 1e-3:
        wl = [round(max(MIN_WL, min(start_level - 0.001 * i, MAX_WL)), 3) for i in range(fc_horizon)]
    return wl


# ===========================================================================
# 3. extender: st_rsvr_r + st_pptn_r (实测表接续)
# ===========================================================================
def extend_observed(conn_or_buf, via_cli=False, window=None):
    """对 st_rsvr_r / st_pptn_r 按 window.obs_* 窗口逐时插入,每小时 1 行,tenant_id=18,deleted=0。
    st_rsvr_r.stcd = RSVR_MASTER ('3');st_pptn_r.stcd = PPTN_MASTER ('46')。
    MOCK 标记:这两表无 alias/taskid 列,故 mock 行用 stcd 取 model_config master 值 +
      creator='MOCK' 标记(若表有 creator 列),清理靠 DELETE WHERE creator='MOCK' AND tenant_id=18。
    window 为 None 时回退到默认 demo 窗口。window.obs_start=None(--roll 哨兵)时
      st_rsvr_r/st_pptn_r 改用 read_breakpoint 决定起点(断点+1h,无断点则 obs_end-47h)。
    幂等:先按 creator='MOCK' + tenant_id 删旧行(整表范围,与窗口无关 —— mock 段始终唯一)。

    跨源一致性(T7):默认/暴雨 demo 路径(obs_start 已知)下,水位与实测雨同源自
      gen_coherent_event —— 实测雨是预报事件的滞后+偏差重现,水位由实测雨累积驱动。
      --roll(obs_start=None,断点续写 cron 边缘路径)回退到独立波形。
    """
    w = window or resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
    print(f"[extend_observed] st_rsvr_r / st_pptn_r window "
          f"obs[{w.obs_start}→{w.obs_end}] ...")
    buf = conn_or_buf if via_cli else None

    # --- st_rsvr_r ---
    # 先清旧 mock(基于 creator='MOCK' 标记,幂等)
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_rsvr_r WHERE creator='MOCK' AND tenant_id=%s", (MOCK_TENANT,))
    if w.obs_start is None and not via_cli:
        # --roll 直连模式:从真实断点+1h 续
        max_tm, _ = read_breakpoint(
            'st_rsvr_r',
            extra_where="tenant_id=%s AND stcd=%s AND deleted=0 AND creator!='MOCK'" % (MOCK_TENANT, "'%s'" % RSVR_MASTER),
            via_cli_buf=buf,
        )
        start = (max_tm + timedelta(hours=1)) if max_tm else (w.obs_end - timedelta(hours=47))
    elif w.obs_start is None and via_cli:
        # --roll mysql-cli 模式:无法回读,退化为 obs_end-47h
        start = w.obs_end - timedelta(hours=47)
    else:
        start = w.obs_start
    end = w.obs_end
    hours = max(1, int((end - start).total_seconds() // 3600) + 1)

    # 跨源一致:默认/暴雨路径(obs_start 已知)用水位来自 gen_coherent_event;
    # --roll(动态断点)回退独立波形。
    coherent = None
    if w.obs_start is not None:
        # 用一个对齐到 [start,end] 的临时 window 取 coherent 水位序列,
        # 保证 obs 窗口与 fc 窗口同源(预报/水位/实测雨联动)。
        cw = Window(start, end, w.fc_start, w.fc_end)
        coherent = gen_coherent_event(cw)
        # gen_coherent_event 按 cw.obs_* 算 hours,与上面 hours 对齐
        wl_series = coherent['water_level']
        # 对齐长度(极端窗口长度不一致时裁/补)
        if len(wl_series) < hours:
            wl_series = wl_series + [wl_series[-1]] * (hours - len(wl_series))
        wl_series = wl_series[:hours]
    else:
        wl_series = gen_water_level_wave(hours)
    inq_series = gen_inflow_series(wl_series)
    print(f"  st_rsvr_r: 续写 {hours}h [{start} → {end}], stcd={RSVR_MASTER}"
          f"{' (coherent)' if coherent else ' (independent)'}")

    rows = []
    rsvr_series_start = start  # 记录 obs 系列零点,供 pptn 对齐
    for i, tm in enumerate(hourly_range(start, end)):
        rz = wl_series[i]
        inq = inq_series[i]
        otq = round(max(30, inq * 0.85), 1)  # 出库 ≈ 入库 85%(削峰)
        wv = round(1000 + (rz - MIN_WL) * 200, 1)  # 蓄水量粗略线性化(万m³)
        rows.append((
            tm, rz, inq, otq, wv, RSVR_MASTER, MOCK_TENANT,
        ))
    sql_rsvr = (
        "INSERT INTO st_rsvr_r "
        "(tm, rz, inq, otq, w, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'MOCK', 'MOCK')"
    )
    _bulk_insert(conn_or_buf, via_cli, sql_rsvr, rows)

    # --- st_pptn_r ---
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_pptn_r WHERE creator='MOCK' AND tenant_id=%s", (MOCK_TENANT,))
    if w.obs_start is None and not via_cli:
        max_tm2, _ = read_breakpoint(
            'st_pptn_r',
            extra_where="tenant_id=%s AND stcd=%s AND deleted=0 AND creator!='MOCK'" % (MOCK_TENANT, "'%s'" % PPTN_MASTER),
            via_cli_buf=buf,
        )
        start2 = (max_tm2 + timedelta(hours=1)) if max_tm2 else (w.obs_end - timedelta(hours=47))
    elif w.obs_start is None and via_cli:
        start2 = w.obs_end - timedelta(hours=47)
    else:
        start2 = w.obs_start
    end2 = w.obs_end
    hours2 = max(1, int((end2 - start2).total_seconds() // 3600) + 1)

    # 跨源一致:从同一 coherent 事件取 observed 雨系列,按小时对齐 pptn 窗口;
    # --roll 回退独立三角雨型。
    if coherent is not None:
        # coherent['observed'] 以 cw.obs_start=rsvr_series_start 为零点;
        # 按 pptn 窗口起点相对偏移取小时值,越界补 0。
        full_obs = coherent['observed']
        rain = []
        for i in range(hours2):
            tm = start2 + timedelta(hours=i)
            off = int((tm - rsvr_series_start).total_seconds() // 3600)
            rain.append(full_obs[off] if 0 <= off < len(full_obs) else 0.0)
    else:
        rain = gen_rainfall_series(hours2, total_mm=60, pattern='triangle')
    print(f"  st_pptn_r: 续写 {hours2}h [{start2} → {end2}], stcd={PPTN_MASTER}"
          f"{' (coherent)' if coherent else ' (independent)'}")
    rows2 = []
    for i, tm in enumerate(hourly_range(start2, end2)):
        rows2.append((tm, rain[i], 1.0, rain[i], PPTN_MASTER, MOCK_TENANT))
    sql_pptn = (
        "INSERT INTO st_pptn_r "
        "(tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, %s, %s, %s, %s, %s, 0, 'MOCK', 'MOCK')"
    )
    _bulk_insert(conn_or_buf, via_cli, sql_pptn, rows2)


# ===========================================================================
# 4. extender: model_result_files + st_mx_preset_cal_r (模型预报接续)
# ===========================================================================
def extend_model_forecast(conn_or_buf, via_cli=False, window=None):
    """对 model_result_files + st_mx_preset_cal_r 按 window.fc_* 窗口续写 mock 预报。
    - model_result_files: 一行(type=1, tenant_id=18, alias='MOCK', taskid LIKE 'MOCK%')
    - st_mx_preset_cal_r: fc 窗口时序(type 22 水位 + type 21 流量,vals 物理合理)
    issued = fc_start;预报时点 = fc_start+1h ... fc_end。fc_start==fc_end 时退化为 1h。
    过滤 create_time <= NOW() 避免 anchor 到 2026-09-15 未来垃圾行。
    window 为 None 时回退到默认 demo 窗口(NOW→NOW+168h)。
    """
    w = window or resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
    print(f"[extend_model_forecast] model_result_files + st_mx_preset_cal_r "
          f"fc[{w.fc_start}→{w.fc_end}] ...")
    # 幂等:清旧 mock(基于 taskid LIKE 'MOCK%')
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_mx_preset_cal_r WHERE taskid LIKE 'MOCK%%'", ())
    _exec(conn_or_buf, via_cli,
          "DELETE FROM model_result_files WHERE alias='MOCK' OR taskid LIKE 'MOCK%%'", ())

    taskid = "MOCK" + datetime.now().strftime("%Y%m%d%H%M%S")
    issued = w.fc_start
    # 预报时点 = issued+1h ... fc_end,至少 1 个时点
    fc_horizon = max(1, int((w.fc_end - w.fc_start).total_seconds() // 3600))

    # 跨源一致(T7):模型预报水位取自 gen_coherent_event(w) 同一降雨事件 ——
    # 实测水位(obs 段)已对该事件响应;模型预报(fc 段,未来)水位继续沿同一趋势:
    # 以 obs 末水位为起点,按预报雨继续累积(同 RUNOFF_COEFF/WL_LAG_HOURS 物理参数),
    # 使"预报雨→水位上涨"在实测与模型预报两侧同趋势。drought/极端窗口长度为 1 时回退独立波形。
    model_wl = _model_forecast_water_level(w, fc_horizon)
    inq_series = gen_inflow_series(model_wl)
    wl_series = model_wl

    # model_result_files 一行
    _exec(conn_or_buf, via_cli,
          "INSERT INTO model_result_files "
          "(taskid, scheme_id, file_name, file_path, file_size, start_time, end_time, "
          " create_time, type, tenant_id, alias, target_water_level, adjusted_water_level) "
          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, 'MOCK', %s, %s)",
          (taskid, 'MOCK_SCHEME', f'{taskid}.json', f'/mock/{taskid}.json', 1024,
           issued, w.fc_end, issued, MOCK_TENANT,
           str(FLOOD_LIM), str(BASE_WL)))
    print(f"  model_result_files: taskid={taskid}")

    # st_mx_preset_cal_r: type 22 水位 + type 21 流量,每预报时点一行
    cal_rows = []
    for i in range(fc_horizon):
        tm = issued + timedelta(hours=i + 1)  # 预报未来时点
        cal_rows.append((taskid, RSVR_MASTER, '三岔', tm, '22', wl_series[i], '1h', MOCK_TENANT))
        cal_rows.append((taskid, RSVR_MASTER, '三岔', tm, '21', inq_series[i], '1h', MOCK_TENANT))
    sql_cal = (
        "INSERT INTO st_mx_preset_cal_r "
        "(taskid, stcd, stnm, tm, type, vals, step, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )
    _bulk_insert(conn_or_buf, via_cli, sql_cal, cal_rows)
    print(f"  st_mx_preset_cal_r: {fc_horizon}h × 2 类型 = {len(cal_rows)} 行 (taskid={taskid}, "
          f"issued={issued})")


# ===========================================================================
# 4.5 extender: f_rnfl_h (和风逐时降雨预报 —— 未来 168h)
# ===========================================================================
# f_rnfl_h 复合主键 (ID, YMDH, UNITNAME, TYPE);ID 是"网格代码"(int, 非 auto_inc)。
# 生产 f_rnfl_h 大部分 tenant_id=1(6946 行),仅 742 行 tenant_id=18;且
# query_forecast_data.py 的 rainfall_forecast / multi_source_overview 查询均无 tenant 过滤,
# 故 mock 行用 tenant_id=1 与真实主体一致,确保被查询命中。
# MOCK 标记靠 COMMENTS='MOCK' 列(该表自带 COMMENTS varchar(255)),清理靠
#   DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'。
RNFL_FUTURE_HOURS = 168
RNFL_GRID_ID = 1  # 复用网格 ID=1(真实存在),未来时点 YMDH 不撞主键


def gen_forecast_rainfall_storm(hours=RNFL_FUTURE_HOURS):
    """生成 hours 小时未来降雨预报序列(mm/h),含一场清晰暴雨:
    NOW+0~12h 微雨起涨 → NOW+15~21h 达峰 15~25mm/h → NOW+24h 后缓退趋零。
    物理合理(峰前 6h 已开始明显降雨,符合产汇流预见需求)。
    """
    series = []
    peak = 22.0          # 峰值 mm/h
    peak_at = 18         # 峰位偏移(NOW+18h)
    for i in range(hours):
        if i < 12:
            r = round(0.5 + 1.5 * (i / 12.0), 1)          # 0.5 → 2.0 mm/h 缓升
        elif i < peak_at:
            r = round(2.0 + (peak - 2.0) * ((i - 12) / (peak_at - 12)), 1)  # 2 → 22 急升
        elif i == peak_at:
            r = peak
        elif i < peak_at + 8:
            # 退水:8h 内从峰退到 ~2mm/h(指数衰减感)
            ratio = (i - peak_at) / 8.0
            r = round(peak * math.exp(-2.0 * ratio) + 1.5, 1)
        else:
            # 尾部零星小雨/无雨(夜间偶发 0~1mm)
            r = round(0.3 * (1 + math.sin(i / 3.0)) / 2.0, 1)
        series.append(max(0.0, round(r, 1)))
    return series


def extend_f_rnfl_h(conn_or_buf, via_cli=False, window=None, hours=RNFL_FUTURE_HOURS):
    """向 f_rnfl_h 插入 [fc_start, fc_end] 的未来逐时降雨预报行。
    UNITNAME='1', TYPE='1', RN 来自暴雨波形, FYMDH=fc_start(预报发布时刻),
    YMDH=各未来时点(fc_start+1h ... fc_end), deleted=0, tenant_id=1, COMMENTS='MOCK'。
    幂等:先 DELETE WHERE COMMENTS='MOCK'。
    window 为 None 时回退到默认 demo 窗口(NOW→NOW+168h);hours 仅在无 window 时作
      兼容回退(旧行为 NOW→NOW+hours)。
    """
    if window is None:
        w = resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
        fc_start = NOW
        fc_hours = hours
    else:
        w = window
        fc_start = w.fc_start
        fc_hours = max(1, int((w.fc_end - w.fc_start).total_seconds() // 3600))
    print(f"[extend_f_rnfl_h] f_rnfl_h 未来 {fc_hours}h 降雨预报 "
          f"fc[{fc_start}→{fc_start + timedelta(hours=fc_hours)}] ...")
    _exec(conn_or_buf, via_cli,
          "DELETE FROM f_rnfl_h WHERE COMMENTS=%s", ('MOCK',))
    # 跨源一致(T7):window 显式时,预报雨取自 gen_coherent_event(window) 的 forecast 序列,
    # 与实测雨/水位同源;window=None(旧兼容路径)回退独立 storm 波形。
    if window is not None:
        rain = gen_coherent_event(w)['forecast']
        if len(rain) < fc_hours:
            rain = rain + [0.0] * (fc_hours - len(rain))
        rain = rain[:fc_hours]
    else:
        rain = gen_forecast_rainfall_storm(fc_hours)
    rows = []
    for i in range(fc_hours):
        ymdh = fc_start + timedelta(hours=i + 1)   # fc_start+1h ... fc_start+fc_hours
        rows.append((RNFL_GRID_ID, ymdh, fc_start, rain[i], '1', '1', 'MOCK'))
    sql = (
        "INSERT INTO f_rnfl_h "
        "(ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1)"
    )
    _bulk_insert(conn_or_buf, via_cli, sql, rows)
    peak_idx = rain.index(max(rain))
    print(f"  f_rnfl_h: {fc_hours} 行 [{rows[0][1]} → {rows[-1][1]}], "
          f"峰值 RN={max(rain)} mm/h @ fc_start+{peak_idx+1}h")


# ===========================================================================
# 5. extender: weather_info + st_pptn_re_forecast (长期断档表重建)
# ===========================================================================
def rebuild_long_stale(conn_or_buf, via_cli=False, window=None):
    """weather_info(断 2025-07)按 obs 窗口最近 7d 重建;st_pptn_re_forecast(断 2025-12)
    重建近期分区预报(过去 24h 回看锚定 obs_end + 未来 fc 窗口预报)。
    window 为 None 时回退到默认 demo 窗口。
    weather_info 用 obs_end 往前推 7d(fx_date 是 date 且 UNIQUE,固定 8d 窗);
    st_pptn_re_forecast 过去 24h 锚定 obs_end(覆盖 zonal 查询 NOW-48h 回看),
    未来预报段用 fc 窗口 [fc_start+1h, fc_end]。
    """
    w = window or resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
    obs_end = w.obs_end
    print(f"[rebuild_long_stale] weather_info + st_pptn_re_forecast "
          f"obs_end={obs_end} fc[{w.fc_start}→{w.fc_end}] ...")
    # 幂等清旧 mock:weather_info 的 fx_date 是 UNIQUE,我们owns obs_end-7d→obs_end 窗口,
    # 故按 fx_date 范围删(mock 行的 icon_day 也标 'MOCK' 作辅助标记)。
    _exec(conn_or_buf, via_cli,
          "DELETE FROM weather_info WHERE icon_day='MOCK'", ())

    # --- weather_info: fx_date 是 date 且 UNIQUE,覆盖 obs_end-7d → obs_end(8d) ---
    w_start = (obs_end - timedelta(days=7)).date()
    days = 8
    w_rows = []
    texts = ['晴', '多云', '阴', '小雨', '中雨', '大雨', '暴雨', '晴']
    for d in range(days):
        fx = w_start + timedelta(days=d)
        idx = min(d, len(texts) - 1)
        w_rows.append((
            fx.strftime('%Y-%m-%d'), str(28 + d % 5), str(20 + d % 4),
            texts[idx], texts[(idx + 1) % len(texts)],
            '东南风', '1-3', '13', '东南风', '1-3', '13',
            str(round(2 + d * 0.5, 1)), '70', '500', '999', 'MOCK',
        ))
    sql_w = (
        "INSERT INTO weather_info "
        "(fx_date, temp_max, temp_min, text_day, text_night, "
        " wind_dir_day, wind_scale_day, wind_speed_day, "
        " wind_dir_night, wind_scale_night, wind_speed_night, "
        " precip, humidity, pressure, vis, icon_day) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE icon_day='MOCK'"
    )
    _bulk_insert(conn_or_buf, via_cli, sql_w, w_rows)
    print(f"  weather_info: {days}d [{w_start} → {w_start + timedelta(days=days-1)}]")

    # --- st_pptn_re_forecast: 重建近期分区预报(tenant 18) ---
    # 该表用 re_id 关联,无 alias/creator 列;mock 行用 drp 标记困难,
    # 故采用:删除 re_id >= 9000 (mock 区段) 后重插。
    # zonal_rainfall_forecast 查询窗口含过去 24h 回看 + 未来预报;过去段锚定 obs_end。
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_pptn_re_forecast WHERE re_id >= 9000", ())
    sql_fc = (
        "INSERT INTO st_pptn_re_forecast "
        "(re_id, tm, drp, intv, dyp, tenant_id, deleted) "
        "VALUES (%s, %s, %s, %s, %s, %s, 0)"
    )
    fc_rows = []
    # (1) 过去 24h 回看场(re_id 9xxx 区段,锚定 obs_end,三角分布总雨量 45mm)
    re_id_past = 9000 + int(datetime.now().strftime('%H%M')) % 100
    lookback_start = obs_end - timedelta(hours=23)
    rain_past = gen_rainfall_series(24, total_mm=45, pattern='triangle')
    for i in range(24):
        tm = lookback_start + timedelta(hours=i)
        fc_rows.append((re_id_past, tm, rain_past[i], 1.0, rain_past[i], MOCK_TENANT))
    # (2) 未来预报场(re_id 9100 区段,覆盖 fc 窗口 [fc_start+1h, fc_end])
    re_id_future = 9100 + int(datetime.now().strftime('%H%M')) % 100
    fc_hours = max(1, int((w.fc_end - w.fc_start).total_seconds() // 3600))
    rain_future = gen_forecast_rainfall_storm(fc_hours)
    for i in range(fc_hours):
        tm = w.fc_start + timedelta(hours=i + 1)
        fc_rows.append((re_id_future, tm, rain_future[i], 1.0, rain_future[i], MOCK_TENANT))
    _bulk_insert(conn_or_buf, via_cli, sql_fc, fc_rows)
    print(f"  st_pptn_re_forecast: 过去 24h (re_id={re_id_past}) + 未来 {fc_hours}h "
          f"(re_id={re_id_future}) = {len(fc_rows)} 行")


# ===========================================================================
# 6. extender: forecast_accuracy_record (mock 精度表)
# ===========================================================================
def create_mock_accuracy(conn_or_buf, via_cli=False, window=None):
    """CREATE TABLE IF NOT EXISTS forecast_accuracy_record;
    插 60d 合成预报-实测对(物理正确,标注 MOCK),issued 区间锚定 obs_end-60d → obs_end。
    window 为 None 时回退到默认 demo 窗口(obs_end=NOW,与旧行为等价)。
    """
    w = window or resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
    print(f"[create_mock_accuracy] forecast_accuracy_record 60d 合成对 "
          f"(issued锚定 {w.obs_end - timedelta(days=60)} → {w.obs_end}) ...")
    # DDL
    ddl = """
    CREATE TABLE IF NOT EXISTS forecast_accuracy_record (
        id            BIGINT       NOT NULL AUTO_INCREMENT,
        taskid        VARCHAR(64)  NOT NULL,
        source        VARCHAR(32)  DEFAULT NULL  COMMENT '预报来源(XAJ/NMC/MOCK)',
        forecast_val  DOUBLE       DEFAULT NULL  COMMENT '预报值(水位m或流量m3/s)',
        actual_val    DOUBLE       DEFAULT NULL  COMMENT '实测值',
        mape          DOUBLE       DEFAULT NULL  COMMENT '平均绝对百分比误差(%)',
        issued_tm     DATETIME     DEFAULT NULL  COMMENT '预报发布时间',
        lead_horizon  INT          DEFAULT NULL  COMMENT '预见期(h)',
        remark        VARCHAR(32)  DEFAULT NULL,
        tenant_id     BIGINT       NOT NULL DEFAULT 18,
        PRIMARY KEY (id),
        KEY idx_far_taskid (taskid),
        KEY idx_far_issued (issued_tm)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='预报精度记录(mock)'
    """
    _exec(conn_or_buf, via_cli, ddl, ())

    # 幂等清旧 mock
    _exec(conn_or_buf, via_cli,
          "DELETE FROM forecast_accuracy_record WHERE remark='MOCK'", ())

    # 60d 合成对:每天 1 条 24h 预报 vs 实测,水位误差 0.1~0.5m,锚定 obs_end
    rows = []
    base_issued = w.obs_end - timedelta(days=60)
    wl_series = gen_water_level_wave(60, base=BASE_WL, peak=FLOOD_LIM - 0.2)
    for d in range(60):
        issued = base_issued + timedelta(days=d)
        actual = wl_series[d]
        # 模拟预报误差:±0.3m 内随机(用确定性公式避免随机种子问题)
        err = 0.3 * math.sin(d / 5.0)
        forecast = round(actual + err, 3)
        mape = round(abs(err) / max(actual, 1) * 100, 3)
        rows.append((
            f"MOCK{issued.strftime('%Y%m%d')}", 'MOCK',
            forecast, actual, mape, issued, 24, 'MOCK', MOCK_TENANT,
        ))
    sql_acc = (
        "INSERT INTO forecast_accuracy_record "
        "(taskid, source, forecast_val, actual_val, mape, issued_tm, lead_horizon, remark, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    _bulk_insert(conn_or_buf, via_cli, sql_acc, rows)
    print(f"  forecast_accuracy_record: {len(rows)} 条,issued_tm MAX={rows[-1][5]}")


# ===========================================================================
# 6.5 extender: weather_warn + dispatch_history (凑齐 10 表)
# ===========================================================================
def extend_warn_dispatch(conn_or_buf, via_cli=False, window=None):
    """weather_warn(气象预警,无 tenant/无 deleted)+ dispatch_history(闸门时序,task_id 下划线)。
    - weather_warn: 当前/预报预警,用 fc_* 窗口或 NOW(预警本就是当前/未来发布)。
      docid PK,无 tenant_id/无 deleted;MOCK 标记 docabstract LIKE '%[MOCK]%'。
    - dispatch_history: 闸门开度时序(关联 model_result_files 的 MOCK taskid),
      用 obs_* 窗口(闸门系列为实测/历史);task_id 列(下划线),有 tenant_id/deleted。
      MOCK 标记 dispatch_opening LIKE '%[MOCK]%'。
    window 为 None 时回退到默认 demo 窗口。幂等:两表均先按 MOCK 标记 DELETE 再 INSERT。
    """
    w = window or resolve_window(argparse.Namespace(start=None, end=None, roll=False), NOW)
    print("[extend_warn_dispatch] weather_warn + dispatch_history "
          f"fc[{w.fc_start}→{w.fc_end}] obs[{w.obs_start}→{w.obs_end}] ...")

    # --- weather_warn: 当前/预报预警(fc 窗口或 NOW) ---
    # 幂等:先按 MOCK 标记清旧
    _exec(conn_or_buf, via_cli,
          "DELETE FROM weather_warn WHERE docabstract LIKE '%%[MOCK]%%'", ())
    warns = [
        # (docid, docabstract, chnlname, model_type, docpubtime, warn_status)
        (f"MOCK-W{NOW.strftime('%Y%m%d%H')}",
         "[MOCK] 暴雨橙色预警:三岔流域未来24h降雨50~100mm",
         "暴雨预警", "11B09", NOW.strftime('%Y-%m-%d %H:%M:%S'), "1"),
    ]
    for r in warns:
        _exec(conn_or_buf, via_cli,
              "INSERT INTO weather_warn (docid, docabstract, chnlname, model_type, docpubtime, warn_status) "
              "VALUES (%s,%s,%s,%s,%s,%s)", r)

    # --- dispatch_history: 闸门开度时序(obs 窗口,实测/历史) ---
    # 幂等:先按 MOCK 标记清旧
    _exec(conn_or_buf, via_cli,
          "DELETE FROM dispatch_history WHERE dispatch_opening LIKE '%%[MOCK]%%'", ())
    taskid = "MOCK" + NOW.strftime("%Y%m%d%H%M%S")
    dh_rows = []
    start = w.obs_start or (NOW - timedelta(hours=47))
    end = w.obs_end
    hours = max(1, int((end - start).total_seconds() // 3600) + 1)
    for i, tm in enumerate(hourly_range(start, end)):
        opening = round(0.3 + 0.4 * math.sin(i / 8.0), 2)   # 闸门开度波动
        flow = round(80 + 40 * math.sin(i / 8.0), 1)         # 下泄流量
        dh_rows.append((tm, f"[MOCK]{opening}", str(flow), taskid, MOCK_TENANT))
    _bulk_insert(conn_or_buf, via_cli,
                 "INSERT INTO dispatch_history (tm, dispatch_opening, gate_opening_flow, task_id, tenant_id) "
                 "VALUES (%s,%s,%s,%s,%s)", dh_rows)
    print(f"  weather_warn: {len(warns)} 条; dispatch_history: {len(dh_rows)} 行")


# ===========================================================================
# 7. NMC HTTP fixture
# ===========================================================================
def write_nmc_fixture():
    """写 data/scenarios/nmc_rainfall_24.json:合法 JSONP diamond14_rainfall_24_json({...})。
    合成等值线 + ≥1 场强降雨。生产 rainfallController.getRainfallForecast 实时拉取此格式,
    mock 时把 typhoon.nmc.cn 指向本文件(或 skill 直接读 fixture 解析)。
    """
    out_dir = os.path.join(os.path.dirname(__file__), 'scenarios')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'nmc_rainfall_24.json')

    payload = {
        "contours": [
            # 24h 降雨等值线(单位 mm),从 10mm 到 100mm+ 强降雨带
            {"value": 10,  "points": [[105.5, 26.0], [106.0, 26.0], [106.0, 26.5], [105.5, 26.5]]},
            {"value": 25,  "points": [[105.7, 26.1], [106.0, 26.1], [106.0, 26.4], [105.7, 26.4]]},
            {"value": 50,  "points": [[105.8, 26.2], [105.95, 26.2], [105.95, 26.35], [105.8, 26.35]]},
            # ≥1 场强降雨(>100mm,暴雨-大暴雨量级)
            {"value": 100, "points": [[105.85, 26.25], [105.92, 26.25], [105.92, 26.32], [105.85, 26.32]]},
            {"value": 250, "points": [[105.87, 26.27], [105.90, 26.27], [105.90, 26.30], [105.87, 26.30]]},
        ],
        "legend": [
            {"min": 0,   "max": 10,  "color": "#A6F28F", "label": "0~10mm"},
            {"min": 10,  "max": 25,  "color": "#3DBA3D", "label": "10~25mm"},
            {"min": 25,  "max": 50,  "color": "#61B8FF", "label": "25~50mm"},
            {"min": 50,  "max": 100, "color": "#0000FF", "label": "50~100mm"},
            {"min": 100, "max": 250, "color": "#FF00F0", "label": "100~250mm"},
            {"min": 250, "max": 999, "color": "#9B0064", "label": "≥250mm"},
        ],
        "issue_time": NOW.strftime('%Y-%m-%d %H:00:00'),
        "lead_hours": 24,
        "source": "NMC-MOCK",
        "remark": "MOCK fixture;生产代码 rainfallController 实时拉取 typhoon.nmc.cn 此格式",
    }
    # JSONP wrapper(生产代码 strips 外层 diamond14_rainfall_24_json(...))
    jsonp = "diamond14_rainfall_24_json(" + json.dumps(payload, ensure_ascii=False, indent=2) + ")"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(jsonp)
    print(f"[write_nmc_fixture] 写入 {out_path} ({len(payload['contours'])} 等值线, 含 ≥1 强降雨)")


# ===========================================================================
# 执行适配层:direct pymysql / via-mysql-cli
# ===========================================================================
def _exec(conn_or_buf, via_cli, sql, params):
    """执行单条 SQL。direct 模式用 conn;mysql-cli 模式渲染成 SQL 文本追加到 buf。
    注意:DDL/含字面量 % 的 SQL 必须传 params=() 且 sql 中不含 %s 占位符,
    此时直接 execute(sql) 不做参数替换(避免 pymysql 把 COMMENT='...' 里的 % 当占位符)。
    """
    if via_cli:
        conn_or_buf.append(_render_sql(sql, params))
        return
    with conn_or_buf.cursor() as cur:  # conn_or_buf 实为 conn
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
    conn_or_buf.commit()


def _bulk_insert(conn_or_buf, via_cli, sql, rows):
    """批量插入。direct 模式 executemany;mysql-cli 模式渲染多条 INSERT 文本。"""
    if via_cli:
        for r in rows:
            conn_or_buf.append(_render_sql(sql, r))
        return
    with conn_or_buf.cursor() as cur:
        cur.executemany(sql, rows)
    conn_or_buf.commit()


def _render_sql(sql, params):
    """把参数化 SQL + params 渲染成 mysql-cli 可执行的文本(字符串加引号转义,datetime 格式化)。"""
    rendered = sql
    if params:
        # 逐个 %s 占位符替换
        out = []
        idx = 0
        parts = rendered.split('%s')
        for i, part in enumerate(parts):
            out.append(part)
            if i < len(params):
                p = params[i]
                if p is None:
                    out.append('NULL')
                elif isinstance(p, (datetime,)):
                    out.append("'" + p.strftime('%Y-%m-%d %H:%M:%S') + "'")
                elif isinstance(p, bool):
                    out.append('1' if p else '0')
                elif isinstance(p, (int, float)):
                    out.append(str(p))
                else:
                    s = str(p).replace("\\", "\\\\").replace("'", "\\'")
                    out.append("'" + s + "'")
                idx += 1
        rendered = ''.join(out)
    # 处理 LIKE 'MOCK%%' 的双百分号转义(在 executemany 里 %s 会冲突,这里直接用单 %)
    rendered = rendered.replace('%%', '%')
    return rendered + ';'


# ===========================================================================
# 连接 + 执行调度(T1 引入;T3-T6 故障注入器复用 _get_conn)
# ===========================================================================
def _get_conn(args):
    """直连模式:返回一条 live pymysql 连接(从 query_utils.get_connection())。
    args 仅用于将来扩展(读 args.via_mysql_cli 等);当前恒走 direct。
    T3-T6 的故障注入器直接复用本函数取连接。
    """
    from query_utils import get_connection
    return get_connection()


def _run_extenders(extenders, window, args):
    """按 args 选择执行路径跑 extenders 列表:
      - --dry-run        : 把每个 extender 渲染成 SQL 打印到 stdout,不 exec
      - --via-mysql-cli  : 渲染 SQL 到 /tmp 文件后用 mysql 客户端执行
      - 默认(direct)     : 开一条连接逐个执行
    每个 extender 签名: fn(conn_or_buf, via_cli, window)。
    """
    if args.dry_run:
        buf = []
        buf.append("-- dry-run: generated SQL (NOT executed)")
        buf.append("SET NAMES utf8mb4;")
        buf.append("SET FOREIGN_KEY_CHECKS=0;")
        for fn in extenders:
            fn(buf, via_cli=True, window=window)
        sql_text = "\n".join(buf)
        print(sql_text)
        print(f"\n[dry-run] {len(buf)} 语句(未执行)。去掉 --dry-run 以实际写入。", file=sys.stderr)
        return

    if args.via_mysql_cli:
        _run_via_mysql_cli(extenders, window)
        return

    # direct pymysql
    conn = _get_conn(args)
    try:
        for fn in extenders:
            fn(conn, via_cli=False, window=window)
    finally:
        conn.close()


def _run_via_mysql_cli(extender_funcs, window):
    """生成 SQL 文件到 /tmp,然后用 mysql 客户端执行。"""
    buf = []
    buf.append("SET NAMES utf8mb4;")
    buf.append("SET FOREIGN_KEY_CHECKS=0;")
    for fn in extender_funcs:
        # mysql-cli 模式:read_breakpoint 退化为 None,extender 用窗口 obs_end-47h 兜底
        fn(buf, via_cli=True, window=window)
    sql_text = "\n".join(buf)
    out_file = '/tmp/forecast_mock_extend.sql'
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(sql_text)
    print(f"\n[via-mysql-cli] SQL 文件已写: {out_file} ({len(buf)} 语句)")
    # 用 mysql 客户端执行
    env = os.environ.copy()
    cmd = [
        'mysql', '-h', env.get('SRM_DB_HOST', '127.0.0.1'),
        '-P', env.get('SRM_DB_PORT', '3306'),
        '-u', env.get('SRM_DB_USER', 'root'),
        f"-p{env.get('SRM_DB_PASSWORD', '')}",
        env.get('SRM_DB_NAME', 'powerelf_srm_yml'),
    ]
    res = subprocess.run(cmd, input=sql_text, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        sys.exit(f"[via-mysql-cli] mysql 执行失败 (exit {res.returncode}):\n{res.stderr}")
    # 过滤 password 警告
    err = '\n'.join(l for l in res.stderr.splitlines() if 'Warning' not in l and 'password' not in l.lower())
    if err.strip():
        print(f"[via-mysql-cli] stderr: {err}")
    print("[via-mysql-cli] 执行完成")


# ===========================================================================
# 故障注入(T3):在已生成的 mock 数据上 OVERLAY 故障条件(删/插特定 mock 子集),
# 模拟预报 skill 应能检出的异常(stale/缺失)。
#   - 每个 inject_* 先 DELETE 其负责的 mock 子集(幂等),再按需插入"问题"数据。
#   - 签名: fn(conn, via_cli, at)  —— at 为故障注入时刻(默认 NOW)。
#   - 不触碰真实行(只动 MOCK 标记/tenant 子集)。
# ===========================================================================
def inject_stale_forecast(conn_or_buf, via_cli, at):
    """f_rnfl_h 最新 FYMDH = at-7天(发布极旧的预报:发布时刻停在 7 天前)。
    幂等:先 DELETE COMMENTS='MOCK',再插入 168 行,YMDH 各时点而 FYMDH 统一锁在 old。
    """
    old = at - timedelta(days=7)
    _exec(conn_or_buf, via_cli,
          "DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
    rows = []
    for i in range(RNFL_FUTURE_HOURS):  # 168
        ymdh = old + timedelta(hours=i + 1)   # 历史时点
        rn = round(1 + 2 * math.sin(i / 5.0), 1)
        rows.append((RNFL_GRID_ID, ymdh, old, rn, '1', '1', 'MOCK'))
    sql = (
        "INSERT INTO f_rnfl_h "
        "(ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1)"
    )
    _bulk_insert(conn_or_buf, via_cli, sql, rows)
    print(f"  [inject_stale_forecast] f_rnfl_h 168 行,FYMDH 锁在 {old} (= at-7d)")


def inject_stale_observed(conn_or_buf, via_cli, at):
    """st_rsvr_r / st_pptn_r mock 停在 at-11天:删除 cutoff 之后(更新)的 mock 行,
    只留更早的 → 实测数据在 11 天前就停了。幂等:基于 creator='MOCK' 范围删。
    """
    cutoff = at - timedelta(days=11)
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_rsvr_r WHERE creator='MOCK' AND tm > %s", (cutoff,))
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_pptn_r WHERE creator='MOCK' AND tm > %s", (cutoff,))
    print(f"  [inject_stale_observed] st_rsvr_r/st_pptn_r mock 截断至 {cutoff} (= at-11d)")


def inject_null_observed(conn_or_buf, via_cli, at):
    """f_rnfl_h 有预报,但对应时段(at-24h → 至今)st_pptn_r mock 清空:
    预报存在而实测缺测(空)。幂等:删 [at-24h, ∞) 的 pptn mock。
    """
    start = at - timedelta(hours=24)
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_pptn_r WHERE creator='MOCK' AND tm >= %s", (start,))
    print(f"  [inject_null_observed] st_pptn_r mock 清空 [{start} → ∞) (= at-24h)")


def inject_empty_model(conn_or_buf, via_cli, at):
    """st_mx_preset_cal_r / model_result_files mock 清空 → model_forecast_result 查询返回空。
    幂等:基于 taskid LIKE 'MOCK%' / alias='MOCK'。
    """
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_mx_preset_cal_r WHERE taskid LIKE 'MOCK%%'", ())
    _exec(conn_or_buf, via_cli,
          "DELETE FROM model_result_files WHERE alias='MOCK' OR taskid LIKE 'MOCK%%'", ())
    print(f"  [inject_empty_model] st_mx_preset_cal_r + model_result_files mock 已清空")


def inject_gated_accuracy(conn_or_buf, via_cli, at):
    """forecast_accuracy_record mock 清空 → 预报精度被 gated(无可评分对)。
    幂等:基于 remark='MOCK'。
    """
    _exec(conn_or_buf, via_cli,
          "DELETE FROM forecast_accuracy_record WHERE remark='MOCK'", ())
    print(f"  [inject_gated_accuracy] forecast_accuracy_record mock 已清空")


# ===========================================================================
# 故障注入(T4):冲突 + 越限类 5 种。
#   - source_disagree / single_source : 多源降雨预报分歧 / 单源缺失
#   - over_flood_limit / extreme_storm / drought : 越限 / 极端暴雨 / 干旱
#   每个 inject_* 先 DELETE 其负责的 mock 子集(幂等),再插入"问题"数据。
#   签名同 T3: fn(conn, via_cli, at);at 默认 NOW,未来时点 YMDH 不撞真实主键。
# ===========================================================================
def inject_source_disagree(conn_or_buf, via_cli, at):
    """和风 f_rnfl_h ≈120mm/24h vs 分区 st_pptn_re_forecast ≈60mm/24h(>20mm 分歧)。
    幂等:delete f_rnfl_h(COMMENTS='MOCK') + st_pptn_re_forecast(re_id>=9000),重插分歧行。
    f_rnfl_h: 5mm/h × 24 = 120mm/24h(和风);分区 2.5mm/h × 24 = 60mm/24h。
    """
    _exec(conn_or_buf, via_cli, "DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
    for i in range(24):
        _exec(conn_or_buf, via_cli,
            "INSERT INTO f_rnfl_h (ID,YMDH,FYMDH,RN,UNITNAME,TYPE,COMMENTS,deleted,tenant_id) "
            "VALUES (1,%s,%s,5.0,'1','1','MOCK',0,1)",
            (at + timedelta(hours=i + 1), at))  # 和风:120mm/24h
    _exec(conn_or_buf, via_cli, "DELETE FROM st_pptn_re_forecast WHERE re_id>=9000", ())
    for i in range(24):
        _exec(conn_or_buf, via_cli,
            "INSERT INTO st_pptn_re_forecast (re_id,tm,drp,intv,dyp,tenant_id,deleted) "
            "VALUES (9200,%s,2.5,1.0,2.5,%s,0)",
            (at + timedelta(hours=i + 1), MOCK_TENANT))  # 分区:60mm/24h
    print(f"  [inject_source_disagree] 和风 120mm/24h vs 分区 60mm/24h (分歧 60mm) @ {at}")


def inject_single_source(conn_or_buf, via_cli, at):
    """仅留和风 f_rnfl_h,删分区 st_pptn_re_forecast(re_id>=9000)+ weather_info(icon_day='MOCK')。
    幂等:按各表标记 DELETE;不插新行(单源=缺源)。
    """
    _exec(conn_or_buf, via_cli, "DELETE FROM st_pptn_re_forecast WHERE re_id>=9000", ())
    _exec(conn_or_buf, via_cli, "DELETE FROM weather_info WHERE icon_day='MOCK'", ())
    print(f"  [inject_single_source] 仅留和风 f_rnfl_h;分区预报 + weather_info mock 已清空 @ {at}")


def inject_over_flood_limit(conn_or_buf, via_cli, at):
    """st_rsvr_r mock 水位 462.0→462.9 逐时越过汛限 462.5。
    幂等:delete st_rsvr_r(creator='MOCK'),重插上涨 24h。
    """
    _exec(conn_or_buf, via_cli, "DELETE FROM st_rsvr_r WHERE creator='MOCK'", ())
    for i in range(24):
        rz = round(462.0 + 0.04 * i, 3)  # 462.0→462.92,越过汛限 462.5
        _exec(conn_or_buf, via_cli,
            "INSERT INTO st_rsvr_r (tm,rz,inq,otq,w,stcd,tenant_id,deleted,creator,eq_code) "
            "VALUES (%s,%s,300,200,22000,%s,%s,0,'MOCK','MOCK')",
            (at + timedelta(hours=i), rz, RSVR_MASTER, MOCK_TENANT))
    print(f"  [inject_over_flood_limit] st_rsvr_r 24h 水位 462.0→462.92 越过汛限 {FLOOD_LIM} @ {at}")


def inject_extreme_storm(conn_or_buf, via_cli, at):
    """f_rnfl_h >100mm/24h(6mm/h × 24 = 144mm)+ weather_warn 红色。
    幂等:delete f_rnfl_h(COMMENTS='MOCK') + weather_warn(docabstract LIKE '%[MOCK]%'),重插。
    """
    _exec(conn_or_buf, via_cli, "DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK'", ())
    for i in range(24):
        _exec(conn_or_buf, via_cli,
            "INSERT INTO f_rnfl_h (ID,YMDH,FYMDH,RN,UNITNAME,TYPE,COMMENTS,deleted,tenant_id) "
            "VALUES (1,%s,%s,6.0,'1','1','MOCK',0,1)",
            (at + timedelta(hours=i + 1), at))  # 144mm/24h
    _exec(conn_or_buf, via_cli,
          "DELETE FROM weather_warn WHERE docabstract LIKE '%%[MOCK]%%'", ())
    _exec(conn_or_buf, via_cli,
        "INSERT INTO weather_warn (docid,docabstract,chnlname,model_type,docpubtime,warn_status) "
        "VALUES (%s,%s,'暴雨红色预警','11B09',%s,'1')",
        (f"MOCK-RED{at.strftime('%Y%m%d%H')}",
         "[MOCK] 暴雨红色预警:三岔流域24h降雨>100mm",
         at.strftime('%Y-%m-%d %H:%M:%S')))
    print(f"  [inject_extreme_storm] f_rnfl_h 144mm/24h + weather_warn 红色 @ {at}")


def inject_drought(conn_or_buf, via_cli, at):
    """长期(7 天)st_pptn_r≈0 + st_rsvr_r 低水位 451.5→逼近死水位 451。
    幂等:delete st_pptn_r(creator='MOCK') + st_rsvr_r(creator='MOCK'),重插 7d 低水。
    时序:从 at-7d 逐时到 at,水位 451.5 缓降到 449.82(逼近死水位 MIN_WL=451)。
    """
    _exec(conn_or_buf, via_cli, "DELETE FROM st_pptn_r WHERE creator='MOCK'", ())
    _exec(conn_or_buf, via_cli, "DELETE FROM st_rsvr_r WHERE creator='MOCK'", ())
    for i in range(24 * 7):  # 7 天 = 168h
        tm = at - timedelta(hours=24 * 7 - 1 - i)  # at-7d → at
        _exec(conn_or_buf, via_cli,
            "INSERT INTO st_pptn_r (tm,p,dr,dyp,stcd,tenant_id,deleted,creator,eq_code) "
            "VALUES (%s,0,0,0,%s,%s,0,'MOCK','MOCK')",
            (tm, PPTN_MASTER, MOCK_TENANT))
        rz = round(451.5 - 0.01 * i, 3)  # 451.5 → 449.83,逼近/破死水位 451
        _exec(conn_or_buf, via_cli,
            "INSERT INTO st_rsvr_r (tm,rz,inq,otq,w,stcd,tenant_id,deleted,creator,eq_code) "
            "VALUES (%s,%s,20,15,4000,%s,%s,0,'MOCK','MOCK')",
            (tm, rz, RSVR_MASTER, MOCK_TENANT))
    print(f"  [inject_drought] 7d st_pptn_r≈0 + st_rsvr_r 451.5→449.83 逼近死水位 {MIN_WL} @ {at}")


# ===========================================================================
# 故障注入(T5):脏数据 + 配置类 5 种(E+F)。
#   - future_junk / negative_rain / taskid_orphan : 脏数据(可清 mock 行)
#   - missing_flood_limit / bad_master_stcd       : 真实 seed/config 表,必须可还原
#   ⚠️ missing_flood_limit 清空真实 seed 表 att_res_flse_lim(3 行汛期),
#      bad_master_stcd UPDATE 真实配置 model_config(tenant 18 st_rsvr_r_master)。
#      两者改前先 _backup_for_fault() dump,--clear-faults(T6)调 _restore_config() 还原。
#   backup/restore 只走 direct 连接(需读库回写文件);via_cli 模式不适用。
#   签名同 T3/T4: fn(conn, via_cli, at)。
# ===========================================================================
SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), 'scenarios')
BACKUP_FLSE_LIM_PATH = os.path.join(SCENARIOS_DIR, 'backup_flse_lim.sql')
BACKUP_MASTER_STCD_PATH = os.path.join(SCENARIOS_DIR, 'backup_master_stcd.txt')
MASTER_CFG_KEY = 'st_rsvr_r_master'


def _backup_for_fault(name, conn):
    """对改动真实 seed/config 表的故障,先 dump 当前值到 scenarios/ 备份文件。
    - missing_flood_limit: att_res_flse_lim 全表 → backup_flse_lim.sql(INSERT 文本)
    - bad_master_stcd     : model_config[st_rsvr_r_master,tenant=18].value → backup_master_stcd.txt
    备份文件随 repo 提交,是 demo 还原脚本的一部分(demo 后用 --clear-faults 还原)。
    幂等:每次重写(覆盖)备份文件,确保反映当前真实状态。仅 direct 模式调用。
    """
    os.makedirs(SCENARIOS_DIR, exist_ok=True)
    cur = conn.cursor()
    try:
        if name == 'missing_flood_limit':
            cur.execute(
                "SELECT id, flse_lim_stag, flood_season_name, flood_season_start, "
                "flood_season_end, res_guid, create_time, update_time, collect_time, "
                "creator, updater, tenant_id FROM att_res_flse_lim ORDER BY id")
            rows = cur.fetchall()
            lines = [
                "-- backup of att_res_flse_lim (real seed; --clear-faults restores from here)",
                "-- generated by inject_missing_flood_limit; demo restore script.",
                "SET NAMES utf8mb4;",
            ]
            for r in rows:
                def q(v):
                    if v is None:
                        return 'NULL'
                    if hasattr(v, 'strftime'):
                        return "'" + v.strftime('%Y-%m-%d %H:%M:%S.%f') + "'"
                    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
                    return "'" + s + "'"
                cols = ['id', 'flse_lim_stag', 'flood_season_name', 'flood_season_start',
                        'flood_season_end', 'res_guid', 'create_time', 'update_time',
                        'collect_time', 'creator', 'updater', 'tenant_id']
                vals = ', '.join(q(r[c]) for c in cols)
                lines.append(
                    f"INSERT INTO att_res_flse_lim ({', '.join(cols)}) VALUES ({vals});")
            with open(BACKUP_FLSE_LIM_PATH, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")
            print(f"  [_backup_for_fault] att_res_flse_lim {len(rows)} 行 → {BACKUP_FLSE_LIM_PATH}")
        elif name == 'bad_master_stcd':
            cur.execute(
                "SELECT value FROM model_config WHERE config_key=%s AND tenant_id=%s",
                (MASTER_CFG_KEY, MOCK_TENANT))
            row = cur.fetchone()
            val = row['value'] if row else RSVR_MASTER  # 无则回退常量 RSVR_MASTER='3'
            with open(BACKUP_MASTER_STCD_PATH, 'w', encoding='utf-8') as f:
                f.write(str(val) + "\n")
            print(f"  [_backup_for_fault] model_config.{MASTER_CFG_KEY}="
                  f"{val} → {BACKUP_MASTER_STCD_PATH}")
    finally:
        cur.close()


def inject_future_junk(conn_or_buf, via_cli, at):
    """model_result_files 插一行 create_time = at+90天(未来脏行)。
    幂等:先 DELETE taskid LIKE 'JUNK%',再插(alias='JUNK', taskid LIKE 'JUNK%')。
    marker: alias='JUNK' + taskid LIKE 'JUNK%'(可清)。
    注:model_result_files 有 UNIQUE(scheme_id,version);mock 用 version=NOW 时间戳避免撞键。
    """
    future = at + timedelta(days=90)
    _exec(conn_or_buf, via_cli,
          "DELETE FROM model_result_files WHERE taskid LIKE 'JUNK%%'", ())
    version = datetime.now().strftime('%Y%m%d%H%M%S')
    _exec(conn_or_buf, via_cli,
        "INSERT INTO model_result_files (taskid, scheme_id, version, file_name, file_path, "
        "file_size, start_time, end_time, create_time, type, tenant_id, alias) "
        "VALUES (%s, 'JUNK', %s, 'j.json', '/j.json', 1, %s, %s, %s, 1, %s, 'JUNK')",
        (f'JUNK{future.strftime("%Y%m%d")}', version, future,
         future + timedelta(hours=72), future, MOCK_TENANT))
    print(f"  [inject_future_junk] model_result_files 未来脏行 create_time={future} (alias='JUNK')")


def inject_negative_rain(conn_or_buf, via_cli, at):
    """st_pptn_r 插一行 dr=-1.0(负值,脏数据)。marker: creator='MOCK'。
    幂等:先 DELETE creator='MOCK' AND dr<0,再插。
    """
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_pptn_r WHERE creator='MOCK' AND dr < 0", ())
    _exec(conn_or_buf, via_cli,
        "INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) "
        "VALUES (%s, 0, -1.0, -1.0, %s, %s, 0, 'MOCK', 'MOCK')",
        (at, PPTN_MASTER, MOCK_TENANT))
    print(f"  [inject_negative_rain] st_pptn_r 负值行 dr=-1.0 (creator='MOCK') @ {at}")


def inject_taskid_orphan(conn_or_buf, via_cli, at):
    """model_result_files 有 taskid='MOCK-ORPHAN',但 st_mx_preset_cal_r 无对应 → JOIN 空集。
    幂等:先 DELETE taskid='MOCK-ORPHAN'(两表),再插 model_result_files 一行。
    marker: taskid='MOCK-ORPHAN'。
    """
    _exec(conn_or_buf, via_cli,
          "DELETE FROM st_mx_preset_cal_r WHERE taskid='MOCK-ORPHAN'", ())
    _exec(conn_or_buf, via_cli,
          "DELETE FROM model_result_files WHERE taskid='MOCK-ORPHAN'", ())
    version = datetime.now().strftime('%Y%m%d%H%M%S')
    _exec(conn_or_buf, via_cli,
        "INSERT INTO model_result_files (taskid, scheme_id, version, file_name, file_path, "
        "file_size, start_time, end_time, create_time, type, tenant_id, alias) "
        "VALUES ('MOCK-ORPHAN', 'MOCK-ORPHAN', %s, 'o.json', '/o.json', 1, %s, %s, %s, 1, %s, 'MOCK')",
        (version, at, at + timedelta(hours=24), at, MOCK_TENANT))
    print(f"  [inject_taskid_orphan] model_result_files taskid='MOCK-ORPHAN' (st_mx_preset_cal_r 无对应)")


def inject_missing_flood_limit(conn_or_buf, via_cli, at):
    """清空真实 seed 表 att_res_flse_lim(3 行汛期)→ 演示汛限回退 att_res_base。
    ⚠️ 改真实 seed 表:先 _backup_for_fault dump 全表到 backup_flse_lim.sql,
       再 DELETE FROM att_res_flse_lim(全表)。--clear-faults(T6)从备份还原。
    via_cli 模式无法回读备份 → 仅 direct 模式生效(cli 模式打印警告跳过备份)。
    """
    if via_cli:
        print("  [inject_missing_flood_limit] ⚠️ via_cli 模式跳过备份(seed 表改动需 direct);仅渲染 DELETE")
        _exec(conn_or_buf, True, "DELETE FROM att_res_flse_lim", ())
        return
    # direct: 先备份(conn_or_buf 即 conn)
    _backup_for_fault('missing_flood_limit', conn_or_buf)
    _exec(conn_or_buf, via_cli, "DELETE FROM att_res_flse_lim", ())
    print(f"  [inject_missing_flood_limit] att_res_flse_lim 已清空(演示汛限回退);备份见 {BACKUP_FLSE_LIM_PATH}")


def inject_bad_master_stcd(conn_or_buf, via_cli, at):
    """UPDATE 真实配置 model_config.st_rsvr_r_master(tenant 18) → '999999'(不存在站)。
    ⚠️ 改真实配置:先 _backup_for_fault 把当前 value 存 backup_master_stcd.txt,再 UPDATE。
       --clear-faults(T6)调 _restore_config('bad_master_stcd') 还原。
    via_cli 模式无法回读 → 仅 direct 模式生效。
    """
    if via_cli:
        print("  [inject_bad_master_stcd] ⚠️ via_cli 模式跳过备份(配置改动需 direct);仅渲染 UPDATE")
        _exec(conn_or_buf, True,
              "UPDATE model_config SET value='999999' WHERE config_key='st_rsvr_r_master' AND tenant_id=18", ())
        return
    _backup_for_fault('bad_master_stcd', conn_or_buf)
    _exec(conn_or_buf, via_cli,
          "UPDATE model_config SET value='999999' WHERE config_key=%s AND tenant_id=%s",
          (MASTER_CFG_KEY, MOCK_TENANT))
    print(f"  [inject_bad_master_stcd] model_config.{MASTER_CFG_KEY}='999999' (tenant {MOCK_TENANT});"
          f" 备份见 {BACKUP_MASTER_STCD_PATH}")


# 故障名 → 注入函数(T4-T6 将补 FAULTS_CD / FAULTS_EF;当前仅 A+B 5 种)
FAULTS_AB = {
    'stale_forecast': inject_stale_forecast,
    'stale_observed': inject_stale_observed,
    'null_observed': inject_null_observed,
    'empty_model': inject_empty_model,
    'gated_accuracy': inject_gated_accuracy,
}
# T4:冲突/越限类 5 种(source_disagree / single_source / over_flood_limit /
# extreme_storm / drought)。T5/T6 将补 FAULTS_EF。
FAULTS_CD = {
    'source_disagree': inject_source_disagree,
    'single_source': inject_single_source,
    'over_flood_limit': inject_over_flood_limit,
    'extreme_storm': inject_extreme_storm,
    'drought': inject_drought,
}
# T5:脏数据 + 配置类 5 种(future_junk / negative_rain / taskid_orphan /
# missing_flood_limit / bad_master_stcd)。共 15 种(A+B / C+D / E+F)。
FAULTS_EF = {
    'future_junk': inject_future_junk,
    'negative_rain': inject_negative_rain,
    'taskid_orphan': inject_taskid_orphan,
    'missing_flood_limit': inject_missing_flood_limit,
    'bad_master_stcd': inject_bad_master_stcd,
}


def _restore_config(name, args):
    """还原改过真实 seed/config 表的故障(T6 的 --clear-faults 调用)。
    - missing_flood_limit: 从 backup_flse_lim.sql 重插 att_res_flse_lim 全表。
      (TRUNCATE 防止 mock 残留撞主键,再 source 备份的 INSERT。)
    - bad_master_stcd: 从 backup_master_stcd.txt 读原值,UPDATE model_config 回原值。
    仅 direct 模式;备份文件缺失 → 报错退出(不可静默丢配置)。
    """
    if name == 'missing_flood_limit':
        if not os.path.exists(BACKUP_FLSE_LIM_PATH):
            sys.exit(f"[restore] 备份缺失: {BACKUP_FLSE_LIM_PATH};无法还原 att_res_flse_lim。")
        conn = _get_conn(args)
        try:
            with open(BACKUP_FLSE_LIM_PATH, 'r', encoding='utf-8') as f:
                sql_text = f.read()
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE att_res_flse_lim")
                # 备份文件内是多条 INSERT;逐句执行(跳过注释/SET 行)
                for line in sql_text.splitlines():
                    line = line.strip()
                    if line.startswith('--') or line.startswith('SET ') or not line:
                        continue
                    cur.execute(line)
            conn.commit()
        finally:
            conn.close()
        print(f"  [_restore_config] att_res_flse_lim 已从 {BACKUP_FLSE_LIM_PATH} 还原")
    elif name == 'bad_master_stcd':
        if not os.path.exists(BACKUP_MASTER_STCD_PATH):
            sys.exit(f"[restore] 备份缺失: {BACKUP_MASTER_STCD_PATH};无法还原 master stcd。")
        with open(BACKUP_MASTER_STCD_PATH, 'r', encoding='utf-8') as f:
            val = f.read().strip()
        conn = _get_conn(args)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE model_config SET value=%s WHERE config_key=%s AND tenant_id=%s",
                    (val, MASTER_CFG_KEY, MOCK_TENANT))
            conn.commit()
        finally:
            conn.close()
        print(f"  [_restore_config] model_config.{MASTER_CFG_KEY} 已还原为 '{val}' (tenant {MOCK_TENANT})")
    else:
        sys.exit(f"[restore] 未知还原目标: {name}(仅 missing_flood_limit / bad_master_stcd 改真实表)")


def _run_fault(name, at, args):
    """按名分发到对应故障注入器;conn 取自 _get_conn(args),调用 fn(conn, via_cli, at)。
    未知名 → sys.exit 报错。via_cli 时不开连接(渲染到 buf? 故障注入只走 direct,
    因为它需针对已生成数据就地删/改,与 extender 的 dry-run/cli 批量模式语义不符)。
    """
    fn = FAULTS_AB.get(name) or FAULTS_CD.get(name) or FAULTS_EF.get(name)
    if not fn:
        sys.exit(f"未知故障: {name}(已知 15 种 — A+B: stale_forecast/stale_observed/"
                 f"null_observed/empty_model/gated_accuracy; C+D: source_disagree/single_source/"
                 f"over_flood_limit/extreme_storm/drought; E+F: future_junk/negative_rain/"
                 f"taskid_orphan/missing_flood_limit/bad_master_stcd)")
    via_cli = getattr(args, 'via_mysql_cli', False)
    if via_cli:
        # mysql-cli 模式:故障注入也渲染 SQL 到 /tmp 并用 mysql 客户端执行
        buf = ["SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS=0;"]
        fn(buf, via_cli=True, at=at)
        _run_fault_via_cli(buf)
        return
    conn = _get_conn(args)
    try:
        fn(conn, via_cli=False, at=at)
    finally:
        conn.close()


def _run_fault_via_cli(buf):
    """故障注入的 mysql-cli 执行路径(复用 _run_via_mysql_cli 的连接参数)。"""
    sql_text = "\n".join(buf)
    out_file = '/tmp/forecast_mock_fault.sql'
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(sql_text)
    print(f"\n[via-mysql-cli] 故障 SQL 文件已写: {out_file} ({len(buf)} 语句)")
    env = os.environ.copy()
    cmd = [
        'mysql', '-h', env.get('SRM_DB_HOST', '127.0.0.1'),
        '-P', env.get('SRM_DB_PORT', '3306'),
        '-u', env.get('SRM_DB_USER', 'root'),
        f"-p{env.get('SRM_DB_PASSWORD', '')}",
        env.get('SRM_DB_NAME', 'powerelf_srm_yml'),
    ]
    res = subprocess.run(cmd, input=sql_text, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        sys.exit(f"[via-mysql-cli] mysql 执行故障注入失败 (exit {res.returncode}):\n{res.stderr}")
    err = '\n'.join(l for l in res.stderr.splitlines()
                    if 'Warning' not in l and 'password' not in l.lower())
    if err.strip():
        print(f"[via-mysql-cli] stderr: {err}")
    print("[via-mysql-cli] 故障注入执行完成")


# ===========================================================================
# 场景触发 + 清理(T6):SCENARIOS / run_scenario / _purge_mock / _clear_faults。
#   - SCENARIOS 定义场景序列:[(kind, fault, at), ...];kind ∈ {'win','fault'}。
#   - run_scenario 按序执行:win → 正常生成窗口数据;fault → _run_fault(fault, at, args)。
#   - _purge_mock  : 跑 purge_mock.sql 清全部 MOCK 行(各表 marker)。
#   - _clear_faults: purge → 重跑正常生成 → _restore_config 还原真实 seed/config 表。
# ⚠️ _clear_faults 必须调 _restore_config('missing_flood_limit'|'bad_master_stcd'),
#    否则 inject_missing_flood_limit / inject_bad_master_stcd 改过的真实表会留在故障态。
# ===========================================================================
SCENARIOS = {
    'demo_flow': [  # 平静→暴雨→超汛限→退水(live demo 完整故事)
        ('win', None, None),                       # 先正常生成窗口数据
        ('fault', 'extreme_storm', None),          # 红色暴雨预警
        ('fault', 'over_flood_limit', None),       # 水位越汛限
    ],
    'extreme': [  # 仅极端组合(无前置正常生成)
        ('fault', 'extreme_storm', None),
        ('fault', 'over_flood_limit', None),
    ],
}


def run_scenario(name, args):
    """按 SCENARIOS[name] 序列执行场景:win 步走正常生成,fault 步注入故障。
    at 默认 NOW;每个 fault 在上一歩产生的数据上 OVERLAY。"""
    steps = SCENARIOS.get(name)
    if not steps:
        sys.exit(f"[scenario] 未知场景: {name}(已知: {', '.join(SCENARIOS)})")
    print(f"\n[scenario] 运行场景 '{name}' ({len(steps)} 步) ...")
    window = resolve_window(args, NOW)
    for i, step in enumerate(steps, 1):
        kind, fault, at = step
        if kind == 'win':
            print(f"  [step {i}] win: 正常生成窗口数据 obs[{window.obs_start}→{window.obs_end}] "
                  f"fc[{window.fc_start}→{window.fc_end}]")
            _run_extenders(_ALL_EXTENDERS, window, args)
        elif kind == 'fault':
            t = at or (args.at or NOW)
            print(f"  [step {i}] fault: {fault} @ {t}")
            _run_fault(fault, t, args)
        else:
            sys.exit(f"[scenario] 未知步骤类型: {kind}(仅 'win'/'fault')")
    print(f"[scenario] {name} 完成")


def _purge_mock(args):
    """跑 purge_mock.sql 清全部 MOCK 行(各表 marker)+ 脏故障行(JUNK/ORPHAN)。
    用 mysql 客户端执行(DB 凭据从 env,默认与 _run_via_mysql_cli 一致)。"""
    sql_path = os.path.join(os.path.dirname(__file__), 'purge_mock.sql')
    if not os.path.exists(sql_path):
        sys.exit(f"[purge-mock] {sql_path} 不存在")
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_text = f.read()
    env = os.environ.copy()
    cmd = [
        'mysql', '-h', env.get('SRM_DB_HOST', '127.0.0.1'),
        '-P', env.get('SRM_DB_PORT', '3306'),
        '-u', env.get('SRM_DB_USER', 'root'),
        f"-p{env.get('SRM_DB_PASSWORD', '')}",
        env.get('SRM_DB_NAME', 'powerelf_srm_yml'),
    ]
    res = subprocess.run(cmd, input=sql_text, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        sys.exit(f"[purge-mock] mysql 执行失败 (exit {res.returncode}):\n{res.stderr}")
    err = '\n'.join(l for l in res.stderr.splitlines()
                    if 'Warning' not in l and 'password' not in l.lower())
    if err.strip():
        print(f"[purge-mock] stderr: {err}")
    print("[purge-mock] 全 MOCK 已清(含 JUNK/ORPHAN 脏行)")


def _clear_faults(args):
    """清除已注入故障,把数据重置为正常 demo 状态:
      (a) _purge_mock          —— 清全部 MOCK + 脏故障行
      (b) 重跑正常窗口生成      —— 重新填充 mock 数据(平静态)
      (c) _restore_config × 2  —— 还原 inject_missing_flood_limit / inject_bad_master_stcd
                                  改过的真实 seed/config 表(att_res_flse_lim / model_config)
    ⚠️ 没有 (c),真实表会停在故障态(att_res_flse_lim 空 / master='999999'),demo 后无法恢复。
    """
    print("\n[clear-faults] (a) 清全部 MOCK ...")
    _purge_mock(args)
    print("[clear-faults] (b) 重跑正常窗口生成 ...")
    window = resolve_window(args, NOW)
    print(f"NOW = {NOW}  window = obs[{window.obs_start}→{window.obs_end}] "
          f"fc[{window.fc_start}→{window.fc_end}]")
    _run_extenders(_ALL_EXTENDERS, window, args)
    print("[clear-faults] (c) 还原真实 seed/config 表 ...")
    for restore in ('missing_flood_limit', 'bad_master_stcd'):
        _restore_config(restore, args)
    print("[clear-faults] 故障已清,数据已重置为正常")


# ===========================================================================
# main
# ===========================================================================
def _parse_date(s):
    return datetime.strptime(s, '%Y-%m-%d')


def _parse_datetime(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M')


# 旧 --extend-* 标志 → extender 子集映射(向后兼容,forecasting skill 的 run_tests/eval 仍用)
_EXTEND_MAP = {
    'extend_observed': extend_observed,
    'extend_model': extend_model_forecast,
    'extend_rainfall': extend_f_rnfl_h,
    'rebuild_stale': rebuild_long_stale,
    'mock_accuracy': create_mock_accuracy,
    'warn_dispatch': extend_warn_dispatch,
}
_ALL_EXTENDERS = [extend_observed, extend_model_forecast, extend_f_rnfl_h,
                  rebuild_long_stale, create_mock_accuracy, extend_warn_dispatch]


def main():
    ap = argparse.ArgumentParser(
        description='预报 demo 数据模拟器(默认=生成标准 demo 窗口数据)')
    # 窗口模式
    ap.add_argument('--start', type=_parse_date, default=None,
                    help='实测/预报窗口起始(YYYY-MM-DD);默认 NOW-30d')
    ap.add_argument('--end', type=_parse_date, default=None,
                    help='实测/预报窗口结束(YYYY-MM-DD);默认 NOW+168h')
    ap.add_argument('--roll', action='store_true',
                    help='断点续到 NOW(cron 用;实测起点由 read_breakpoint 决定)')
    # 故障/场景(T3-T6 实现;此处占位不崩)
    ap.add_argument('--at', type=_parse_datetime, default=None,
                    help='故障注入时刻(YYYY-MM-DD HH:MM);默认 NOW')
    ap.add_argument('--inject-fault', default=None,
                    help='故障名,逗号分隔(T3-T5 实现)')
    ap.add_argument('--scenario', default=None, help='场景序列名(T6 实现)')
    ap.add_argument('--clear-faults', action='store_true', help='清除已注入故障(T6 实现)')
    ap.add_argument('--purge-mock', action='store_true', help='清除全部 MOCK 行(T6 实现)')
    # 执行控制
    ap.add_argument('--dry-run', action='store_true', help='只打印 SQL,不执行')
    ap.add_argument('--via-mysql-cli', action='store_true',
                    help='生成 SQL 文件后用 mysql 客户端执行(不用 dbutils/pymysql 直写)')
    ap.add_argument('--nmc-fixture', action='store_true', help='仅写 NMC HTTP fixture(不需 DB)')
    # 向后兼容:旧 --extend-* 标志(映射到 extender 子集)
    ap.add_argument('--extend-all', action='store_true',
                    help='[兼容] 跑全部 extender(=默认 demo 窗口行为)')
    for flag in _EXTEND_MAP:
        ap.add_argument(f'--{flag.replace("_", "-")}', action='store_true',
                        help=f'[兼容] 仅跑 {flag}')
    args = ap.parse_args()

    # 单独的清理类动作(T6 实现):短路 —— 执行后直接 return,不走正常生成。
    if args.purge_mock:
        _purge_mock(args)
        return
    if args.clear_faults:
        _clear_faults(args)
        return

    # NMC fixture 不需要 DB,可单独触发(或随 --extend-all / 默认一并写)
    explicit_extend = any(getattr(args, f) for f in _EXTEND_MAP)
    write_fixture = args.nmc_fixture or args.extend_all

    # 默认行为(无任何模式标志)= 生成标准 demo 窗口数据 + NMC fixture
    if no_mode_explicit_only_fixture(args):
        write_nmc_fixture()
        return

    window = resolve_window(args, NOW)
    print(f"NOW = {NOW}  MOCK_TENANT = {MOCK_TENANT}")
    print(f"window = obs[{window.obs_start}→{window.obs_end}]  "
          f"fc[{window.fc_start}→{window.fc_end}]")

    # 选 extenders:旧 --extend-* 子集;否则全量
    if args.extend_all or explicit_extend:
        extenders = [fn for flag, fn in _EXTEND_MAP.items() if getattr(args, flag)]
        if args.extend_all:
            extenders = list(_ALL_EXTENDERS)
    else:
        extenders = list(_ALL_EXTENDERS)

    if write_fixture:
        write_nmc_fixture()

    _run_extenders(extenders, window, args)

    # 故障注入(T3 实现):逗号分隔的故障名,逐个分发注入。
    # at 默认 NOW;每个故障在已生成的 mock 数据上 OVERLAY 问题条件。
    if args.inject_fault:
        at = args.at or NOW
        faults = [f.strip() for f in args.inject_fault.split(',') if f.strip()]
        print(f"\n[inject-fault] 注入 {len(faults)} 种故障 @ {at}: {', '.join(faults)}")
        for name in faults:
            print(f"  → 注入 {name}")
            _run_fault(name, at, args)
    if args.scenario:
        run_scenario(args.scenario, args)

    print("\n✅ 生成完成。")


def no_mode_explicit_only_fixture(args):
    """仅 --nmc-fixture 被显式指定(不带其他模式标志)→ 只写 fixture 后退出。"""
    return (args.nmc_fixture and not any([args.start, args.end, args.roll,
            args.extend_all] + [getattr(args, f) for f in _EXTEND_MAP]
            + [args.inject_fault, args.scenario]))


if __name__ == '__main__':
    main()
