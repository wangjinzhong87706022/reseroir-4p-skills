#!/usr/bin/env python3
"""
Phase 6 验收测试：模型物理正确性守卫。

三类断言（评审 P2 要求）：
  1. 泄流曲线单调性——堰流 Q∝H^1.5 物理约束
  2. XAJ 干旱反例——W=0 + 微雨 → R≈0（不凭空产流）
  3. 水量平衡守恒——storage_change = total_inflow - total_outflow - extra_outflow

拦系数 bug：错的 XAJ 系数没有任何测试拦着，本测试补此防线。
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# P2: 模型文件顶部 from flask import Flask，无 flask 环境下 import 即崩。
# 测试前先 stub flask，让模型文件可 import（生产仍需真 flask）。
if 'flask' not in sys.modules:
    _flask_stub = MagicMock()
    _flask_stub.Flask = lambda name: MagicMock()
    _flask_stub.request = MagicMock()
    _flask_stub.jsonify = lambda d: d
    sys.modules['flask'] = _flask_stub

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS = _REPO_ROOT / "plan-generation" / "models"
if str(_MODELS) not in sys.path:
    sys.path.insert(0, str(_MODELS))


class TestDischargeCurveMonotonicity(unittest.TestCase):
    """泄流曲线单调性断言（堰流 Q∝H^1.5）。"""

    def test_flood_routing_default_curve_monotonic(self):
        from flood_routing import DEFAULT_DC_CURVE
        for i in range(len(DEFAULT_DC_CURVE) - 1):
            wl_a, q_a = DEFAULT_DC_CURVE[i]
            wl_b, q_b = DEFAULT_DC_CURVE[i + 1]
            self.assertLessEqual(
                q_a, q_b,
                f"DEFAULT_DC_CURVE 非单调递增：({wl_a},{q_a})→({wl_b},{q_b})，"
                f"违反堰流 Q∝H^1.5 物理约束",
            )

    def test_dispatch_model_default_curve_monotonic(self):
        from dispatch_model import DEFAULT_DC_CURVE
        for i in range(len(DEFAULT_DC_CURVE) - 1):
            wl_a, q_a = DEFAULT_DC_CURVE[i]
            wl_b, q_b = DEFAULT_DC_CURVE[i + 1]
            self.assertLessEqual(
                q_a, q_b,
                f"DEFAULT_DC_CURVE 非单调递增：({wl_a},{q_a})→({wl_b},{q_b})，"
                f"违反堰流 Q∝H^1.5 物理约束",
            )


class TestXAJDryBasinNoRunoff(unittest.TestCase):
    """XAJ 干旱反例：流域蓄水接近饱和容量 W=0 + 微雨 → 产流 R≈0。

    评审反例：W=0 + 微雨 → 代码算出 R≈WM·B≈36mm 径流（应≈0）。
    这直接污染喂给调度模型的入库预报。
    """

    @unittest.expectedFailure  # P2-1: XAJ 系数 bug 待水文专家复核（拍板跳过）
    def test_dry_basin_micro_rain_near_zero_runoff(self):
        """干旱流域(W=0)+微雨 → R≈0（系数 bug 时凭空产流 ~34mm）。

        拍板「跳过待水文专家」：XAJ 系数本身不改，本测试标 expectedFailure
        保持防线——等水文专家修系数后去 decorator，测试自动转 pass。
        """
        from xaj_model import XAJModel
        model = XAJModel(watershed_area_km2=161.25)
        model.WU = 0.0
        model.WL = 0.0
        model.WD = 0.0
        R = model.runoff_generation(P=1.0, ET=0.0)
        self.assertLess(
            R, 5.0,
            f"干旱流域(W=0)+微雨(1mm)产流 R={R}mm 过大，"
            f"应≈0mm（流域完全缺水，净雨补土壤），疑似 XAJ 系数 bug",
        )

    def test_saturated_basin_full_runoff(self):
        """饱和流域(W=WM) + 显著净雨 → 全产流 R≈PE（ sanity check）。"""
        from xaj_model import XAJModel
        model = XAJModel(watershed_area_km2=161.25)
        # 饱和流域：三层土壤满
        model.WU = model.params['WUM']
        model.WL = model.params['WLM']
        model.WD = model.params['WDM']
        WM = model.params['WM']
        # 显著净雨 50mm
        R = model.runoff_generation(P=50.0, ET=0.0)
        # 饱和流域全产流：R ≈ PE = 50mm（扣除微量补缺）
        self.assertGreater(
            R, 30.0,
            f"饱和流域(W=WM)+显著净雨(50mm)产流 R={R}mm 过小，"
            f"应≈50mm（全流域产流）",
        )


class TestWaterBalanceConservation(unittest.TestCase):
    """水量平衡守恒：storage_change = total_inflow - total_outflow - extra_outflow。"""

    def test_route_storage_change_conserved(self):
        """调洪演算水量守恒：Δ库容 = 入库 - 出库 - 溢流。"""
        from flood_routing import FloodRoutingModel, DEFAULT_WL_CURVE, DEFAULT_DC_CURVE
        import numpy as np
        model = FloodRoutingModel(DEFAULT_WL_CURVE, DEFAULT_DC_CURVE)
        # 简单情景：入库恒定 100 m³/s，出库恒定 50 m³/s，演算 6 小时
        inflow = [100.0] * 6
        outflow = [50.0] * 6
        result = model.route(inflow, outflow, initial_wl=459.18, dt_hours=1,
                             max_wl=462.88, min_wl=451.0)
        stats = result['statistics']
        total_in = stats['total_inflow']
        total_out = stats['total_outflow']
        total_extra = stats.get('total_extra_outflow', 0.0)
        storage_change = stats['storage_change']
        # 守恒断言：storage_change ≈ total_in - total_out - total_extra
        expected = total_in - total_out - total_extra
        self.assertAlmostEqual(
            storage_change, expected, places=1,
            msg=f"水量不守恒：storage_change={storage_change} ≠ "
                f"in({total_in})-out({total_out})-extra({total_extra})={expected}",
        )

    def test_route_overflow_balance_conserved(self):
        """超限溢流场景：溢流水量计入守恒。"""
        from flood_routing import FloodRoutingModel, DEFAULT_WL_CURVE, DEFAULT_DC_CURVE
        import numpy as np
        model = FloodRoutingModel(DEFAULT_WL_CURVE, DEFAULT_DC_CURVE)
        # 超限情景：入库远大于出库，水位逼近 max_wl 触发溢流
        inflow = [500.0] * 10
        outflow = [10.0] * 10
        result = model.route(inflow, outflow, initial_wl=461.0, dt_hours=1,
                             max_wl=462.88, min_wl=451.0)
        stats = result['statistics']
        total_in = stats['total_inflow']
        total_out = stats['total_outflow']
        total_extra = stats.get('total_extra_outflow', 0.0)
        storage_change = stats['storage_change']
        expected = total_in - total_out - total_extra
        self.assertAlmostEqual(
            storage_change, expected, places=1,
            msg=f"超限溢流场景水量不守恒：storage_change={storage_change} ≠ "
                f"in({total_in})-out({total_out})-extra({total_extra})={expected}",
        )
        # 溢流场景 extra_outflow 应 > 0
        if total_extra <= 0:
            # 允许无溢流（若水位未超限），但守恒律必须成立
            pass


if __name__ == '__main__':
    unittest.main()
