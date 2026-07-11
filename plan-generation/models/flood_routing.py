#!/usr/bin/env python3
"""
调洪演算模型（Flood Routing）
功能：入库流量 + 出库流量 → 水位过程
部署：Flask API 服务，端口 18083

核心原理：
  水量平衡方程：S(t+1) = S(t) + (I(t) - O(t)) × Δt
  其中 S=蓄水量, I=入库流量, O=出库流量, Δt=时间间隔

输入：入库流量过程、出库流量过程（或闸门开度过程）、初始水位、水位-库容曲线
输出：水位过程、库容过程、水量平衡统计

可独立使用，也可配合新安江模型和调度优化模型串联使用。
"""

import json
import numpy as np
from flask import Flask, request, jsonify

app = Flask(__name__)


class FloodRoutingModel:
    """调洪演算模型"""

    def __init__(self, water_level_curve, discharge_curve=None):
        """
        初始化模型
        :param water_level_curve: 水位-库容曲线 [(水位m, 库容万m³), ...]
        :param discharge_curve: 水位-泄流曲线 [(水位m, 流量m³/s), ...]，可选
        """
        self.wl_curve = sorted(water_level_curve, key=lambda x: x[0])
        self.wl_levels = [p[0] for p in self.wl_curve]
        self.wl_caps = [p[1] for p in self.wl_curve]

        if discharge_curve:
            self.dc_curve = sorted(discharge_curve, key=lambda x: x[0])
            self.dc_levels = [p[0] for p in self.dc_curve]
            self.dc_flows = [p[1] for p in self.dc_curve]
        else:
            self.dc_curve = None

    def wl_to_cap(self, water_level):
        """水位 → 库容（线性插值）"""
        if water_level <= self.wl_levels[0]:
            return self.wl_caps[0]
        if water_level >= self.wl_levels[-1]:
            return self.wl_caps[-1]
        for i in range(len(self.wl_levels) - 1):
            if self.wl_levels[i] <= water_level <= self.wl_levels[i + 1]:
                ratio = (water_level - self.wl_levels[i]) / (self.wl_levels[i + 1] - self.wl_levels[i])
                return self.wl_caps[i] + ratio * (self.wl_caps[i + 1] - self.wl_caps[i])
        return self.wl_caps[-1]

    def cap_to_wl(self, capacity):
        """库容 → 水位（线性插值）"""
        if capacity <= self.wl_caps[0]:
            return self.wl_levels[0]
        if capacity >= self.wl_caps[-1]:
            return self.wl_levels[-1]
        for i in range(len(self.wl_caps) - 1):
            if self.wl_caps[i] <= capacity <= self.wl_caps[i + 1]:
                ratio = (capacity - self.wl_caps[i]) / (self.wl_caps[i + 1] - self.wl_caps[i])
                return self.wl_levels[i] + ratio * (self.wl_levels[i + 1] - self.wl_levels[i])
        return self.wl_levels[-1]

    def wl_to_max_outflow(self, water_level):
        """水位 → 最大泄流能力"""
        if not self.dc_curve:
            return 9999  # 无泄流曲线时不限制
        if water_level <= self.dc_levels[0]:
            return self.dc_flows[0]
        if water_level >= self.dc_levels[-1]:
            return self.dc_flows[-1]
        for i in range(len(self.dc_levels) - 1):
            if self.dc_levels[i] <= water_level <= self.dc_levels[i + 1]:
                ratio = (water_level - self.dc_levels[i]) / (self.dc_levels[i + 1] - self.dc_levels[i])
                return self.dc_flows[i] + ratio * (self.dc_flows[i + 1] - self.dc_flows[i])
        return self.dc_flows[-1]

    def route(self, inflow, outflow=None, gate_openings=None,
              initial_wl=459.18, dt_hours=1, max_wl=462.88, min_wl=451.0):
        """
        调洪演算主方法

        :param inflow: 入库流量过程(m³/s)
        :param outflow: 出库流量过程(m³/s)，与 gate_openings 二选一
        :param gate_openings: 闸门开度过程(0-1)，与 outflow 二选一
        :param initial_wl: 初始水位(m)
        :param dt_hours: 时间间隔(h)
        :param max_wl: 最高允许水位(m)
        :param min_wl: 最低允许水位(m)
        :return: 演算结果
        """
        n = len(inflow)

        # 如果提供了闸门开度，转换为出库流量
        if outflow is None and gate_openings is not None:
            outflow = []
            current_wl = initial_wl
            for i in range(n):
                max_out = self.wl_to_max_outflow(current_wl)
                out = gate_openings[i] * max_out
                outflow.append(out)
                # 更新水位（用于下一时段的泄流能力计算）
                cap = self.wl_to_cap(current_wl)
                cap = cap + (inflow[i] - out) * dt_hours * 3600 / 10000
                current_wl = self.cap_to_wl(cap)
        elif outflow is None:
            outflow = [0] * n

        # 初始化结果数组
        water_levels = np.zeros(n)
        capacities = np.zeros(n)
        cumulative_inflow = np.zeros(n)
        cumulative_outflow = np.zeros(n)

        # 初始状态
        current_cap = self.wl_to_cap(initial_wl)

        for i in range(n):
            # 水量平衡：S(t+1) = S(t) + (I(t) - O(t)) × Δt
            delta = (inflow[i] - outflow[i]) * dt_hours * 3600 / 10000  # 万m³
            current_cap = current_cap + delta

            # 库容不能为负
            current_cap = max(0, current_cap)

            # 库容转水位
            current_wl = self.cap_to_wl(current_cap)

            # 水位约束（软约束，记录但不阻断）
            if current_wl > max_wl:
                current_wl = max_wl
                current_cap = self.wl_to_cap(max_wl)
            elif current_wl < min_wl:
                current_wl = min_wl
                current_cap = self.wl_to_cap(min_wl)

            water_levels[i] = current_wl
            capacities[i] = current_cap
            cumulative_inflow[i] = sum(inflow[:i + 1]) * dt_hours * 3600 / 10000
            cumulative_outflow[i] = sum(outflow[:i + 1]) * dt_hours * 3600 / 10000

        # 计算统计指标
        peak_inflow = max(inflow)
        peak_outflow = max(outflow)
        peak_inflow_time = int(np.argmax(inflow))
        peak_outflow_time = int(np.argmax(outflow))
        max_wl_achieved = max(water_levels)
        max_wl_time = int(np.argmax(water_levels))
        min_wl_achieved = min(water_levels)

        total_inflow = sum(inflow) * dt_hours * 3600 / 10000  # 万m³
        total_outflow = sum(outflow) * dt_hours * 3600 / 10000  # 万m³
        storage_change = total_inflow - total_outflow  # 万m³

        peak_shaving = peak_inflow - peak_outflow
        peak_shaving_rate = (peak_shaving / peak_inflow * 100) if peak_inflow > 0 else 0

        return {
            'water_levels': water_levels.tolist(),
            'capacities': capacities.tolist(),
            'inflows': inflow if isinstance(inflow, list) else inflow.tolist(),
            'outflows': outflow if isinstance(outflow, list) else outflow.tolist(),
            'cumulative_inflow': cumulative_inflow.tolist(),
            'cumulative_outflow': cumulative_outflow.tolist(),
            'hours': n,
            'statistics': {
                'initial_water_level': round(water_levels[0], 2),
                'final_water_level': round(water_levels[-1], 2),
                'max_water_level': round(max_wl_achieved, 2),
                'max_water_level_time': max_wl_time,
                'min_water_level': round(min_wl_achieved, 2),
                'peak_inflow': round(peak_inflow, 2),
                'peak_inflow_time': peak_inflow_time,
                'peak_outflow': round(peak_outflow, 2),
                'peak_outflow_time': peak_outflow_time,
                'peak_shaving': round(peak_shaving, 2),
                'peak_shaving_rate': round(peak_shaving_rate, 2),
                'total_inflow': round(total_inflow, 2),
                'total_outflow': round(total_outflow, 2),
                'storage_change': round(storage_change, 2),
                'initial_capacity': round(self.wl_to_cap(water_levels[0]), 2),
                'final_capacity': round(capacities[-1], 2),
            }
        }


# 默认水位-库容曲线（三岔水库）
DEFAULT_WL_CURVE = [
    (451.0, 3900), (452.0, 4200), (453.0, 4500), (454.0, 4836),
    (455.0, 5200), (456.0, 5600), (457.0, 6100), (458.0, 6455),
    (459.0, 6960), (460.0, 7450), (461.0, 8086), (462.0, 8723),
    (462.5, 9064), (463.0, 9405), (464.0, 9900), (465.0, 10819),
    (466.0, 11800), (467.0, 13000), (468.0, 14500),
]

DEFAULT_DC_CURVE = [
    (451.0, 0), (453.0, 20), (455.0, 80), (456.0, 83),
    (457.0, 85), (458.0, 87), (459.0, 89), (460.0, 91),
    (461.0, 93), (462.0, 99), (462.5, 94), (463.0, 100),
    (464.0, 120), (465.0, 150), (466.0, 200), (467.0, 300),
    (468.0, 500),
]


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "model": "FloodRouting", "version": "1.0.0"})


@app.route('/api/routing/calculate', methods=['POST'])
def calculate():
    """
    调洪演算接口

    请求体：
    {
        "inflow": [50, 80, 120, ...],        // 入库流量过程(m³/s)
        "outflow": [30, 50, 80, ...],        // 出库流量过程(m³/s)，可选
        "gate_openings": [0.3, 0.5, 0.8, ...], // 闸门开度(0-1)，可选
        "initial_water_level": 459.18,        // 初始水位(m)
        "dt_hours": 1,                        // 时间间隔(h)
        "max_water_level": 462.88,            // 最高允许水位(m)
        "min_water_level": 451.0,             // 最低允许水位(m)
        "water_level_curve": [[451, 3900], ...], // 可选
        "discharge_curve": [[451, 0], ...]       // 可选
    }
    """
    try:
        data = request.get_json()

        inflow = data.get('inflow', [])
        outflow = data.get('outflow')
        gate_openings = data.get('gate_openings')
        initial_wl = data.get('initial_water_level', 459.18)
        dt_hours = data.get('dt_hours', 1)
        max_wl = data.get('max_water_level', 462.88)
        min_wl = data.get('min_water_level', 451.0)

        wl_curve = data.get('water_level_curve', DEFAULT_WL_CURVE)
        dc_curve = data.get('discharge_curve', DEFAULT_DC_CURVE)

        if not inflow:
            return jsonify({"error": "入库流量数据不能为空"}), 400

        model = FloodRoutingModel(
            water_level_curve=[tuple(p) for p in wl_curve],
            discharge_curve=[tuple(p) for p in dc_curve]
        )

        result = model.route(
            inflow=inflow,
            outflow=outflow,
            gate_openings=gate_openings,
            initial_wl=initial_wl,
            dt_hours=dt_hours,
            max_wl=max_wl,
            min_wl=min_wl
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/routing/water-balance', methods=['POST'])
def water_balance():
    """
    简化水量平衡计算

    请求体：
    {
        "initial_water_level": 459.18,
        "inflow_volume": 500,     // 入库水量(万m³)
        "outflow_volume": 300,    // 出库水量(万m³)
        "water_level_curve": [[451, 3900], ...]  // 可选
    }
    """
    try:
        data = request.get_json()
        initial_wl = data.get('initial_water_level', 459.18)
        inflow_vol = data.get('inflow_volume', 0)
        outflow_vol = data.get('outflow_volume', 0)

        wl_curve = data.get('water_level_curve', DEFAULT_WL_CURVE)
        model = FloodRoutingModel(water_level_curve=[tuple(p) for p in wl_curve])

        initial_cap = model.wl_to_cap(initial_wl)
        final_cap = initial_cap + inflow_vol - outflow_vol
        final_wl = model.cap_to_wl(final_cap)

        return jsonify({
            'initial_water_level': round(initial_wl, 2),
            'initial_capacity': round(initial_cap, 2),
            'inflow_volume': round(inflow_vol, 2),
            'outflow_volume': round(outflow_vol, 2),
            'final_capacity': round(final_cap, 2),
            'final_water_level': round(final_wl, 2),
            'water_level_change': round(final_wl - initial_wl, 2),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("调洪演算模型服务启动中...")
    print("API: http://0.0.0.0:18083/api/routing/calculate")
    app.run(host='0.0.0.0', port=18083, debug=False)
