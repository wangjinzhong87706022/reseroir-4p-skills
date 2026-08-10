#!/usr/bin/env python3
"""
新安江模型（XAJ）- 简化版
功能：降雨 → 入库流量
部署：Flask API 服务，端口 18081

核心原理：
  1. 三层蒸散发模型（上层、下层、深层）
  2. 蓄满产流模型（产流计算）
  3. 水源划分（地表径流、壤中流、地下径流）
  4. 汇流计算（单位线法）

输入：逐小时降雨量(mm)、蒸发量(mm)
输出：逐小时入库流量(m³/s)
"""

import json
import numpy as np
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)


class XAJModel:
    """简化新安江模型"""

    def __init__(self, watershed_area_km2=161.25):
        """
        初始化模型参数
        :param watershed_area_km2: 流域面积(km²)，默认161.25=三岔（多水库必须显式传入，如桃曲坡1335）
        """
        self.area_km2 = watershed_area_km2
        self.area_m2 = watershed_area_km2 * 1e6  # 转换为m²

        # 模型参数（基于三岔水库流域特性率定）
        self.params = {
            # 蒸散发参数
            'K': 0.85,              # 蒸散发折算系数
            'WUM': 20.0,            # 上层土壤蓄水容量(mm)
            'WLM': 60.0,            # 下层土壤蓄水容量(mm)
            'WDM': 40.0,            # 深层土壤蓄水容量(mm)
            'C': 0.15,              # 深层蒸散发系数

            # 产流参数
            'B': 0.3,               # 蓄水容量曲线指数
            'IMP': 0.05,            # 不透水面积比例
            'WM': 120.0,            # 流域平均蓄水容量(mm) = WUM + WLM + WDM

            # 水源划分参数
            'SM': 20.0,             # 自由水蓄水容量(mm)
            'EX': 1.5,              # 自由水蓄水容量曲线指数
            'KG': 0.35,             # 地下径流出流系数
            'KSS': 0.35,            # 壤中流出流系数

            # 汇流参数
            'KKSS': 0.7,            # 壤中流消退系数
            'KKG': 0.95,            # 地下径流消退系数
            'UH': [0.15, 0.25, 0.20, 0.15, 0.10, 0.08, 0.04, 0.02, 0.01],  # 单位线（9个时段）
        }

        # 状态变量初始化
        self.WU = 15.0   # 上层土壤含水量(mm)
        self.WL = 40.0   # 下层土壤含水量(mm)
        self.WD = 30.0   # 深层土壤含水量(mm)
        self.S = 10.0    # 自由水蓄水量(mm)
        self.QSS = 0.0   # 壤中流退水流量(m³/s)
        self.QG = 0.0    # 地下径流退水流量(m³/s)

    def evapotranspiration(self, P, E0):
        """
        三层蒸散发计算
        :param P: 降雨量(mm)
        :param E0: 水面蒸发量(mm)
        :return: (EU, EL, ED, ET) 上层/下层/深层蒸散发及总蒸散发
        """
        K = self.params['K']
        WUM = self.params['WUM']
        WLM = self.params['WLM']
        C = self.params['C']

        EP = K * E0  # 流域蒸散发能力

        # 上层蒸散发
        if self.WU + P >= EP:
            EU = EP
            EL = 0
            ED = 0
        elif self.WU + P >= self.WU:
            EU = self.WU + P
            remaining = EP - EU
            # 下层蒸散发
            if self.WL >= remaining:
                EL = remaining
                ED = 0
            else:
                EL = self.WL
                ED = min(C * (EP - EU - EL), self.WD)
        else:
            EU = self.WU + P
            remaining = EP - EU
            if self.WL >= remaining * (self.WL / (self.WL + self.WD)):
                EL = remaining * (self.WL / (self.WL + self.WD))
                ED = remaining - EL
            else:
                EL = self.WL
                ED = min(remaining - EL, self.WD)

        return EU, EL, ED, EU + EL + ED

    def runoff_generation(self, P, ET):
        """
        蓄满产流计算
        :param P: 降雨量(mm)
        :param ET: 总蒸散发(mm)
        :return: 产流量R(mm)
        """
        B = self.params['B']
        IMP = self.params['IMP']
        WM = self.params['WM']

        # 扣除蒸散发后的净雨
        PE = P - ET

        if PE <= 0:
            # 无产流，更新土壤含水量
            self.WU = max(0, self.WU + P - ET)
            return 0.0

        # 计算流域蓄水容量
        W = self.WU + self.WL + self.WD
        # P2-1 修复：A 是流域蓄水容量分布曲线积分，标准定义为
        #   A = WM * (1 - (1 - W/WM)^(1/(1+B)))   (mm 量纲)
        # 原代码 A = 1 - pow(1 - W/WM, B) 缺 WM 乘数且指数错(B vs 1/(1+B))，
        # 导致 :134 的全产流判据 PE + A >= 1 量纲不符（mm + 无量纲 vs 阈值1）。
        if W < WM:
            A = WM * (1 - pow(1 - W / WM, 1.0 / (1 + B)))
        else:
            A = WM

        WMM = WM * (1 + B)  # 最大点蓄水容量（mm）

        if PE + A >= WMM:
            # 全流域产流
            R = PE - (WM - W)
        else:
            # 部分流域产流
            # P2-1 修复：原 WM * pow(1 - (PE + A), B + 1) 量纲不符，
            # 标准 XAJ 部分产流公式为
            #   R = PE - (WM - W) + WMM * pow(1 - (PE + A) / WMM, 1 + B)
            # 其中 (PE + A) / WMM 是无量纲比例，pow 后乘 WMM 回到 mm 量纲。
            R = PE - (WM - W) + WMM * pow(1 - (PE + A) / WMM, 1 + B)

        R = max(0, R) * (1 - IMP) + PE * IMP  # 考虑不透水面积

        # P2-17 修复：三层土壤含水更新缺 WU→WL→DW 级联充填
        # 标准 XAJ：上层 (WU) 超出 WUM 的多余水量补给下层 (WL)，
        # WL 超出 WLM 的多余水量补给深层 (WD)，与三层蒸散发模型闭合。
        WUM = self.params['WUM']
        WLM = self.params['WLM']
        WDM = self.params['WDM']

        # 上层：净雨补给 + 级联溢出
        new_WU = self.WU + PE - R
        if new_WU > WUM:
            excess = new_WU - WUM
            self.WU = WUM
            # 级联到下层
            new_WL = self.WL + excess
            if new_WL > WLM:
                excess2 = new_WL - WLM
                self.WL = WLM
                # 级联到深层
                self.WD = min(WDM, self.WD + excess2)
            else:
                self.WL = new_WL
        else:
            self.WU = max(0, new_WU)
            self.WL = self.WL  # 下层不变
            self.WD = self.WD  # 深层不变

        return max(0, R)

    def source_partition(self, R):
        """
        水源划分：地表径流、壤中流、地下径流
        :param R: 产流量(mm)
        :return: (RS, RSS, RG) 地表/壤中/地下径流
        """
        SM = self.params['SM']
        EX = self.params['EX']
        KG = self.params['KG']
        KSS = self.params['KSS']

        if R <= 0:
            return 0, 0, 0

        # 自由水蓄水容量曲线
        AU = SM * (1 - pow(1 - self.S / SM, EX)) if self.S < SM else SM

        if R + AU >= SM:
            # 自由水蓄满
            RS = R - (SM - self.S)
            self.S = SM
        else:
            # 部分蓄满
            SMM = SM * (1 + EX)
            RS = R - (SM - self.S) + SM * pow(1 - (R + AU) / SMM, EX + 1)
            self.S = self.S + R - RS

        RS = max(0, RS)

        # 壤中流和地下径流
        RSS = self.S * KSS
        RG = self.S * KG
        self.S = self.S - RSS - RG

        return RS, RSS, RG

    def flow_routing(self, RS, RSS, RG):
        """
        汇流计算
        :param RS: 地表径流(mm)
        :param RSS: 壤中流(mm)
        :param RG: 地下径流(mm)
        :return: 总流量(m³/s)
        """
        KSS = self.params['KKSS']
        KG = self.params['KKG']
        UH = self.params['UH']

        # 地表径流：单位线汇流
        # 简化：直接转换为流量
        RS_flow = RS * self.area_m2 / 1000 / 3600  # mm → m³/s

        # 壤中流：线性水库退水
        self.QSS = self.QSS * KSS + RSS * self.area_m2 / 1000 / 3600

        # 地下径流：线性水库退水
        self.QG = self.QG * KG + RG * self.area_m2 / 1000 / 3600

        return RS_flow + self.QSS + self.QG

    def run(self, rainfall, evaporation):
        """
        运行模型
        :param rainfall: 逐小时降雨量数组(mm)
        :param evaporation: 逐小时蒸发量数组(mm)
        :return: 逐小时入库流量数组(m³/s)
        """
        n = len(rainfall)
        flow = np.zeros(n)

        for i in range(n):
            P = rainfall[i] if i < len(rainfall) else 0
            E = evaporation[i] if i < len(evaporation) else 1.0  # 默认1mm/h

            # 1. 蒸散发计算
            EU, EL, ED, ET = self.evapotranspiration(P, E)

            # 2. 产流计算
            R = self.runoff_generation(P, ET)

            # 3. 水源划分
            RS, RSS, RG = self.source_partition(R)

            # 4. 汇流计算
            Q = self.flow_routing(RS, RSS, RG)

            flow[i] = round(Q, 2)

        return flow


# P2-3 修复：全局可变模型实例 + Flask threaded=True 并发不安全
# 改 threading.local() per-request 实例化
import threading

_xaj_local = threading.local()


def _get_model(watershed_area):
    """获取当前线程的 XAJ 模型实例（线程安全）。

    Flask threaded=True 下不同请求可能并发调用 forecast()，
    原全局 xaj_model 实例的 WU/WL/WD 内部状态会被并发覆写，
    导致桃曲坡(1335km²)/三岔(161.25km²)并发算错。
    """
    if not hasattr(_xaj_local, 'model') or _xaj_local.model.area_km2 != watershed_area:
        _xaj_local.model = XAJModel(watershed_area_km2=watershed_area)
    return _xaj_local.model


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "model": "XAJ", "version": "1.0.0"})


@app.route('/api/xaj/forecast', methods=['POST'])
def forecast():
    """
    新安江模型预报接口

    请求体：
    {
        "rainfall": [5.0, 8.0, 15.0, ...],    // 逐小时降雨量(mm)
        "evaporation": [1.0, 1.0, 1.0, ...],  // 逐小时蒸发量(mm)，可选
        "watershed_area": 161.25               // 流域面积(km²)，可选
    }

    响应：
    {
        "flow": [12.5, 18.3, 25.6, ...],      // 逐小时入库流量(m³/s)
        "peak_flow": 25.6,                     // 洪峰流量
        "peak_time": 2,                        // 洪峰出现时段
        "total_runoff": 156.8,                 // 总径流量(万m³)
        "runoff_coefficient": 0.45             // 径流系数
    }
    """
    try:
        data = request.get_json()
        rainfall = data.get('rainfall', [])
        evaporation = data.get('evaporation', [1.0] * len(rainfall))
        watershed_area = data.get('watershed_area', 161.25)

        if not rainfall:
            return jsonify({"error": "降雨数据不能为空"}), 400

        # P2-3: 改 threading.local per-request 实例（线程安全）
        model = _get_model(watershed_area)

        # 运行模型
        flow = model.run(rainfall, evaporation)

        # 计算统计指标
        peak_flow = float(np.max(flow))
        peak_time = int(np.argmax(flow))
        total_runoff = float(np.sum(flow) * 3600 / 10000)  # m³/s → 万m³
        total_rainfall = float(np.sum(rainfall))
        runoff_coefficient = round(total_runoff * 10000 / (total_rainfall * watershed_area * 1000), 3) if total_rainfall > 0 else 0

        return jsonify({
            "flow": flow.tolist(),
            "peak_flow": round(peak_flow, 2),
            "peak_time": peak_time,
            "total_runoff": round(total_runoff, 2),
            "total_rainfall": round(total_rainfall, 2),
            "runoff_coefficient": runoff_coefficient,
            "hours": len(flow)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/xaj/reset', methods=['POST'])
def reset():
    """重置当前线程的模型状态（P2-3: 清 _xaj_local 线程本地属性，删原 global xaj_model 引用）"""
    if hasattr(_xaj_local, 'model'):
        watershed_area = _xaj_local.model.area_km2
        _xaj_local.model = XAJModel(watershed_area_km2=watershed_area)
        return jsonify({"status": "reset", "message": f"模型状态已重置（流域面积 {watershed_area} km²）"})
    return jsonify({"status": "noop", "message": "当前线程无活跃模型实例，无需重置"})


if __name__ == '__main__':
    print("新安江模型服务启动中...")
    print("API: http://0.0.0.0:18081/api/xaj/forecast")
    app.run(host='0.0.0.0', port=18081, debug=False)
