#!/usr/bin/env python3
"""
水库调度优化模型
功能：入库流量 + 约束条件 → 闸门开度 + 出库流量
部署：Flask API 服务，端口 18082

核心原理：
  1. 水量平衡方程：V(t+1) = V(t) + (I(t) - O(t)) * dt
  2. 约束优化：在满足水位/流量约束条件下，优化闸门开度
  3. 调度规则：基于调度目标（防洪/兴利/综合）确定优化目标

输入：入库流量过程、水位-库容曲线、约束参数
输出：闸门开度过程、出库流量过程、水位过程
"""

import json
import numpy as np
from flask import Flask, request, jsonify

# P2-4: 删除 scipy 死 import（minimize_scalar, minimize 未使用，实为规则法调度）

app = Flask(__name__)


class DispatchModel:
    """水库调度优化模型"""

    def __init__(self, water_level_curve, discharge_curve):
        """
        初始化模型
        :param water_level_curve: 水位-库容曲线 [(水位m, 库容万m³), ...]
        :param discharge_curve: 水位-泄流曲线 [(水位m, 流量m³/s), ...]
        """
        # 水位-库容曲线（按水位排序）
        self.wl_curve = sorted(water_level_curve, key=lambda x: x[0])
        self.wl_levels = [p[0] for p in self.wl_curve]
        self.wl_caps = [p[1] for p in self.wl_curve]

        # 水位-泄流曲线（按水位排序）
        self.dc_curve = sorted(discharge_curve, key=lambda x: x[0])
        self.dc_levels = [p[0] for p in self.dc_curve]
        self.dc_flows = [p[1] for p in self.dc_curve]

    def interpolate_wl_to_cap(self, water_level):
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

    def interpolate_cap_to_wl(self, capacity):
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

    def interpolate_wl_to_flow(self, water_level):
        """水位 → 最大泄流能力（线性插值）"""
        if water_level <= self.dc_levels[0]:
            return self.dc_flows[0]
        if water_level >= self.dc_levels[-1]:
            return self.dc_flows[-1]
        for i in range(len(self.dc_levels) - 1):
            if self.dc_levels[i] <= water_level <= self.dc_levels[i + 1]:
                ratio = (water_level - self.dc_levels[i]) / (self.dc_levels[i + 1] - self.dc_levels[i])
                return self.dc_flows[i] + ratio * (self.dc_flows[i + 1] - self.dc_flows[i])
        return self.dc_flows[-1]

    def water_balance(self, capacity, inflow, outflow, dt_hours=1):
        """
        水量平衡计算
        :param capacity: 当前库容(万m³)
        :param inflow: 入库流量(m³/s)
        :param outflow: 出库流量(m³/s)
        :param dt_hours: 时间间隔(h)
        :return: 新库容(万m³)
        """
        # m³/s × 3600s / 10000 = 万m³
        delta = (inflow - outflow) * dt_hours * 3600 / 10000
        return capacity + delta

    def optimize_dispatch(self, inflow_process, initial_wl, constraints, dt_hours=1):
        """
        调度优化主方法

        :param inflow_process: 入库流量过程(m³/s)
        :param initial_wl: 初始水位(m)
        :param constraints: 约束条件字典
        :param dt_hours: 时间间隔(h)
        :return: 调度结果
        """
        n = len(inflow_process)

        # 约束参数
        max_wl = constraints.get('max_water_level', max(self.wl_levels))
        min_wl = constraints.get('min_water_level', min(self.wl_levels))
        max_capacity = constraints.get('max_drainage_capacity', 9999)
        safe_capacity = constraints.get('safe_drainage_capacity', 9999)
        target_wl = constraints.get('target_water_level', initial_wl)
        scheduling_target = constraints.get('scheduling_target', '0')  # 0=防洪, 1=兴利, 2=综合
        scheduling_model = constraints.get('scheduling_model', '0')    # 0=控制最高水位, 1=控制最低水位, 2=控制范围

        # 初始化结果数组
        water_levels = np.zeros(n)
        capacities = np.zeros(n)
        outflows = np.zeros(n)
        gate_openings = np.zeros(n)

        # 初始状态
        current_wl = initial_wl
        current_cap = self.interpolate_wl_to_cap(initial_wl)

        for i in range(n):
            inflow = inflow_process[i]
            water_levels[i] = current_wl
            capacities[i] = current_cap

            # 计算当前水位下的最大泄流能力
            max_outflow_at_wl = self.interpolate_wl_to_flow(current_wl)

            # 根据调度目标确定目标出库流量
            target_outflow = self._determine_outflow(
                current_wl, current_cap, inflow,
                max_wl, min_wl, max_capacity, safe_capacity,
                target_wl, scheduling_target, scheduling_model,
                max_outflow_at_wl, dt_hours
            )

            # 约束出库流量
            outflow = min(target_outflow, max_outflow_at_wl, max_capacity, safe_capacity)
            outflow = max(0, outflow)

            # 闸门开度（相对值 0-1）
            gate_openings[i] = outflow / max_outflow_at_wl if max_outflow_at_wl > 0 else 0
            gate_openings[i] = min(1.0, gate_openings[i])

            outflows[i] = outflow

            # 水量平衡计算
            current_cap = self.water_balance(current_cap, inflow, outflow, dt_hours)
            current_wl = self.interpolate_cap_to_wl(current_cap)

            # 水位约束检查
            if current_wl > max_wl:
                # 超过最高水位，加大泄流
                excess_cap = self.interpolate_wl_to_cap(current_wl) - self.interpolate_wl_to_cap(max_wl)
                extra_outflow = excess_cap * 10000 / 3600 / dt_hours
                outflow = min(outflow + extra_outflow, max_outflow_at_wl)
                outflows[i] = outflow
                current_cap = self.water_balance(capacities[i], inflow, outflow, dt_hours)
                current_wl = self.interpolate_cap_to_wl(current_cap)
                gate_openings[i] = outflow / max_outflow_at_wl if max_outflow_at_wl > 0 else 0
            elif current_wl < min_wl:
                # 低于死水位，削减下泄（保库，防止库容被放干危及取水/生态）
                deficit_cap = self.interpolate_wl_to_cap(min_wl) - self.interpolate_wl_to_cap(current_wl)
                cut_outflow = deficit_cap * 10000 / 3600 / dt_hours
                outflow = max(0, outflow - cut_outflow)
                outflows[i] = outflow
                current_cap = self.water_balance(capacities[i], inflow, outflow, dt_hours)
                current_wl = self.interpolate_cap_to_wl(current_cap)
                gate_openings[i] = outflow / max_outflow_at_wl if max_outflow_at_wl > 0 else 0

        # 计算统计指标
        peak_inflow = max(inflow_process)
        peak_outflow = max(outflows)
        peak_shaving = peak_inflow - peak_outflow
        peak_shaving_rate = (peak_shaving / peak_inflow * 100) if peak_inflow > 0 else 0
        max_wl_achieved = max(water_levels)
        min_wl_achieved = min(water_levels)

        total_inflow = sum(inflow_process) * dt_hours * 3600 / 10000  # 万m³
        total_outflow = sum(outflows) * dt_hours * 3600 / 10000  # 万m³
        max_regulation = total_inflow - total_outflow  # 万m³

        return {
            'water_levels': water_levels.tolist(),
            'capacities': capacities.tolist(),
            'outflows': outflows.tolist(),
            'gate_openings': gate_openings.tolist(),
            'hours': n,
            'statistics': {
                'peak_inflow': round(peak_inflow, 2),
                'peak_outflow': round(peak_outflow, 2),
                'peak_shaving': round(peak_shaving, 2),
                'peak_shaving_rate': round(peak_shaving_rate, 2),
                'max_water_level': round(max_wl_achieved, 2),
                'min_water_level': round(min_wl_achieved, 2),
                'total_inflow': round(total_inflow, 2),
                'total_outflow': round(total_outflow, 2),
                'max_regulation': round(max_regulation, 2),
                'initial_water_level': round(water_levels[0], 2),
                'final_water_level': round(water_levels[-1], 2),
            }
        }

    def _determine_outflow(self, current_wl, current_cap, inflow,
                           max_wl, min_wl, max_capacity, safe_capacity,
                           target_wl, scheduling_target, scheduling_model,
                           max_outflow_at_wl, dt_hours):
        """根据调度目标确定目标出库流量"""

        if scheduling_target == '0':
            # 防洪调度：尽量多泄，降低水位
            if scheduling_model == '0':
                # 控制最高水位：水位接近上限时加大泄流
                if current_wl > max_wl - 0.5:
                    return max_outflow_at_wl  # 全力泄洪
                elif current_wl > max_wl - 1.0:
                    return max_outflow_at_wl * 0.8
                else:
                    # 维持当前水位或缓慢下降
                    target_cap = self.interpolate_wl_to_cap(min(current_wl, target_wl))
                    delta_cap = current_cap - target_cap
                    return max(0, delta_cap * 10000 / 3600 / dt_hours)
            elif scheduling_model == '3':
                # 控制最大出库流量
                return min(safe_capacity, max_outflow_at_wl)

        elif scheduling_target == '1':
            # 兴利调度：尽量少泄，保持水位
            if scheduling_model == '1':
                # 控制最低水位
                if current_wl < min_wl + 0.5:
                    return 0  # 停止泄水
                else:
                    # 维持当前水位
                    return min(inflow * 0.5, safe_capacity)

        elif scheduling_target == '2':
            # 综合调度：平衡防洪和兴利
            if scheduling_model == '2':
                # 控制水位范围
                target_cap = self.interpolate_wl_to_cap(target_wl)
                delta_cap = current_cap - target_cap
                target_outflow = max(0, delta_cap * 10000 / 3600 / dt_hours)
                return min(target_outflow, safe_capacity)
            elif scheduling_model == '4':
                # 控制最小出库流量
                return min(safe_capacity, max_outflow_at_wl)

        # 默认：维持当前水位
        target_cap = self.interpolate_wl_to_cap(target_wl)
        delta_cap = current_cap - target_cap
        return max(0, delta_cap * 10000 / 3600 / dt_hours)


# ⚠️ 三岔水库专属兜底曲线（仅供三岔部署实例向后兼容）。
# 多水库部署（如桃曲坡）必须由调用方从 att_res_stag_cap_disc / att_res_discharge_curve
# 按 tenant_id 取曲线后显式传入，禁止走此 fallback（否则会误用三岔曲线）。
DEFAULT_WL_CURVE = [
    (451.0, 3900), (452.0, 4200), (453.0, 4500), (454.0, 4836),
    (455.0, 5200), (456.0, 5600), (457.0, 6100), (458.0, 6455),
    (459.0, 6960), (460.0, 7450), (461.0, 8086), (462.0, 8723),
    (462.5, 9064), (463.0, 9405), (464.0, 9900), (465.0, 10819),
    (466.0, 11800), (467.0, 13000), (468.0, 14500),
]

# ⚠️ 三岔水库专属兜底泄流曲线（同上警告）。
DEFAULT_DC_CURVE = [
    (451.0, 0), (453.0, 20), (455.0, 80), (456.0, 83),
    (457.0, 85), (458.0, 87), (459.0, 89), (460.0, 91),
    (461.0, 93), (462.0, 99), (462.5, 94), (463.0, 100),
    (464.0, 120), (465.0, 150), (466.0, 200), (467.0, 300),
    (468.0, 500),
]


def _warn_default_curve(reservoir_hint="三岔"):
    """兜底曲线被使用时发出警告（多水库场景的防串库提醒）。"""
    import warnings
    warnings.warn(
        f"使用了 {reservoir_hint} 默认曲线 fallback。多水库部署必须由调用方"
        f"从 DB 按 tenant_id 取曲线显式传入，禁止依赖此兜底。",
        stacklevel=3,
    )


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "model": "Dispatch", "version": "1.0.0"})


@app.route('/api/dispatch/optimize', methods=['POST'])
def optimize():
    """
    调度优化接口

    请求体：
    {
        "inflow": [50, 80, 120, ...],         // 入库流量过程(m³/s)
        "initial_water_level": 459.18,         // 初始水位(m)
        "max_water_level": 462.88,             // 最高允许水位(m)
        "min_water_level": 451.0,              // 最低允许水位(m)
        "max_drainage_capacity": 192,          // 最大泄流能力(m³/s)
        "safe_drainage_capacity": 95.1,        // 下游安全泄量(m³/s)
        "target_water_level": 460.0,           // 目标水位(m)
        "scheduling_target": "0",              // 调度目标：0=防洪, 1=兴利, 2=综合
        "scheduling_model": "0",               // 调度模式：0=控制最高, 1=控制最低, 2=控制范围
        "dt_hours": 1,                         // 时间间隔(h)
        "water_level_curve": [[451, 3900], ...], // 水位-库容曲线，可选
        "discharge_curve": [[451, 0], ...]       // 水位-泄流曲线，可选
    }

    响应：
    {
        "water_levels": [...],                 // 逐时水位过程(m)
        "outflows": [...],                     // 逐时出库流量(m³/s)
        "gate_openings": [...],                // 逐时闸门开度(0-1)
        "statistics": { ... }                  // 统计指标
    }
    """
    try:
        data = request.get_json()

        inflow = data.get('inflow', [])
        initial_wl = data.get('initial_water_level', 459.18)
        dt_hours = data.get('dt_hours', 1)

        # 约束参数
        constraints = {
            'max_water_level': data.get('max_water_level', 462.88),
            'min_water_level': data.get('min_water_level', 451.0),
            'max_drainage_capacity': data.get('max_drainage_capacity', 192),
            'safe_drainage_capacity': data.get('safe_drainage_capacity', 95.1),
            'target_water_level': data.get('target_water_level', initial_wl - 1),
            'scheduling_target': data.get('scheduling_target', '0'),
            'scheduling_model': data.get('scheduling_model', '0'),
        }

        # 曲线数据（多水库部署必须由调用方传入，否则走三岔兜底并告警）
        wl_curve = data.get('water_level_curve')
        dc_curve = data.get('discharge_curve')
        if wl_curve is None or dc_curve is None:
            _warn_default_curve()
            wl_curve = wl_curve or DEFAULT_WL_CURVE
            dc_curve = dc_curve or DEFAULT_DC_CURVE

        if not inflow:
            return jsonify({"error": "入库流量数据不能为空"}), 400

        # 创建模型实例
        model = DispatchModel(
            water_level_curve=[tuple(p) for p in wl_curve],
            discharge_curve=[tuple(p) for p in dc_curve]
        )

        # 运行优化
        result = model.optimize_dispatch(
            inflow_process=inflow,
            initial_wl=initial_wl,
            constraints=constraints,
            dt_hours=dt_hours
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/dispatch/verify', methods=['POST'])
def verify():
    """
    方案验证接口：检查参数是否满足约束

    请求体：
    {
        "water_level": 462.5,
        "outflow": 100,
        "max_water_level": 462.88,
        "safe_drainage_capacity": 95.1
    }

    响应：
    {
        "valid": false,
        "violations": ["水位超过最高允许水位", "下泄流量超过下游安全泄量"]
    }
    """
    try:
        data = request.get_json()
        violations = []

        wl = data.get('water_level', 0)
        outflow = data.get('outflow', 0)
        max_wl = data.get('max_water_level', 999)
        min_wl = data.get('min_water_level', 0)
        safe_cap = data.get('safe_drainage_capacity', 999)

        if wl > max_wl:
            violations.append(f"水位 {wl}m 超过最高允许水位 {max_wl}m")
        if wl < min_wl:
            violations.append(f"水位 {wl}m 低于最低允许水位 {min_wl}m")
        if outflow > safe_cap:
            violations.append(f"下泄流量 {outflow}m³/s 超过下游安全泄量 {safe_cap}m³/s")

        return jsonify({
            "valid": len(violations) == 0,
            "violations": violations
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("调度优化模型服务启动中...")
    print("API: http://0.0.0.0:18082/api/dispatch/optimize")
    app.run(host='0.0.0.0', port=18082, debug=False)
