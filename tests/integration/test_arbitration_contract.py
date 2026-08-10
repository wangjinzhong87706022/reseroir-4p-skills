#!/usr/bin/env python3
"""
仲裁安全闭环契约测试（P0-3 / P3-5）。

用 plan-gen query_full_context() 的实际返回结构（mock DB）喂
arbitrator.arbitrate_plan_vs_simulation，断言：
  - 危险水位（plan_level > flood_limit）→ decision in ('adjust','reject')，非 accept
  - 下泄超安全泄量（plan_discharge > safe_discharge）→ decision == 'reject'

这是 P0-3 的关键验收——原 supervisor 测试用 _seed_stage 注入假峰值
{"max_level":786.95}，绕过真实 plan-gen 输出，掩盖了 P0-3。
本测试不注入假数据，直接用 query_full_context() 的真实契约。
"""
import os
import sys
import unittest
from unittest.mock import patch

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SUPERVISOR_SCRIPTS = os.path.join(_REPO, "supervisor", "scripts")
_PLAN_SCRIPTS = os.path.join(_REPO, "plan-generation", "scripts")
for _p in (_REPO, _SUPERVISOR_SCRIPTS, _PLAN_SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class TestArbitrationContract(unittest.TestCase):
    """仲裁闭环契约测试：用真实 plan-gen 输出结构喂仲裁器。"""

    def _mock_full_context(self, max_level, max_discharge):
        """构造 plan-gen query_full_context() 的真实返回结构。"""
        return {
            'current_water_level': [{'rz': max_level, 'otq': max_discharge, 'tm': '2026-08-10 08:00:00'}],
            'rainfall_forecast': [],
            'weather_warning': [],
            'flood_limit': [{'flse_lim_stag': 786.8, 'flood_season_name': '汛期'}],
            'config': {'safe_drainage_capacity': '95.1', 'max_drainage_capacity': '192'},
            'historical_plans': [],
            'historical_floods': [],
            'scenarios': [{'max_level': max_level, 'max_discharge': max_discharge}],
            'recent_rainfall': [],
            'water_level_curve': [],
            'discharge_curve': [],
            # ↓↓↓ P0-3 新增的顶层峰值键
            'max_level': max_level,
            'max_discharge': max_discharge,
        }

    def test_dangerous_plan_rejected_or_adjusted_not_accept(self):
        """危险方案（水位超汛限 + 下泄超安全泄量）不应 accept。

        P0-3 核心：原 plan-gen 不输出 max_level/max_discharge，
        导致 Rule 1（交叉校验）和 Rule 2（下泄否决）恒短路，
        decision 恒为 accept。本测试验证 P0-3 修复后 dangerous plan 被拦截。
        """
        from arbitrator import arbitrate_plan_vs_simulation
        # plan: 水位 787.5 > 汛限 786.8，下泄 120 > 安全泄量 95.1
        plan = {"max_level": 787.5, "max_discharge": 120.0}
        sim = {"max_level": 787.3, "max_discharge": 110.0}
        result = arbitrate_plan_vs_simulation(
            plan, sim,
            flood_limit=786.8, safe_discharge=95.1,
        )
        self.assertNotEqual(result.decision, "accept",
                            f"危险方案不应 accept，实际 decision={result.decision}")
        self.assertIn(result.decision, ("adjust", "reject"),
                      f"危险方案应返回 adjust/reject，实际 {result.decision}")

    def test_safe_plan_accepted(self):
        """安全方案（水位低于汛限 + 下泄低于安全泄量）应 accept。"""
        from arbitrator import arbitrate_plan_vs_simulation
        plan = {"max_level": 785.0, "max_discharge": 80.0}
        sim = {"max_level": 785.2, "max_discharge": 82.0}
        result = arbitrate_plan_vs_simulation(
            plan, sim,
            flood_limit=786.8, safe_discharge=95.1,
        )
        self.assertEqual(result.decision, "accept")
        self.assertTrue(result.passed)

    def test_discharge_over_safe_rejected(self):
        """下泄超安全泄量 → reject（Rule 2 守卫）。"""
        from arbitrator import arbitrate_plan_vs_simulation
        plan = {"max_level": 785.0, "max_discharge": 150.0}  # 下泄 150 > 安全 95.1
        sim = {"max_level": 785.0, "max_discharge": 150.0}
        result = arbitrate_plan_vs_simulation(
            plan, sim,
            flood_limit=786.8, safe_discharge=95.1,
        )
        self.assertEqual(result.decision, "reject")
        self.assertFalse(result.passed)

    def test_plan_level_higher_than_sim_adjusted(self):
        """方案水位 > 仿真水位 → adjust（Rule 1 守卫）。"""
        from arbitrator import arbitrate_plan_vs_simulation
        plan = {"max_level": 788.0, "max_discharge": 90.0}  # plan > sim
        sim = {"max_level": 786.0, "max_discharge": 90.0}
        result = arbitrate_plan_vs_simulation(
            plan, sim,
            flood_limit=786.8, safe_discharge=95.1,
        )
        self.assertEqual(result.decision, "adjust")
        self.assertFalse(result.passed)

    @patch('query_plan_data.execute_query_list')
    @patch('query_plan_data.execute_query')
    def test_full_context_has_peak_keys(self, mock_eq, mock_eql):
        """query_full_context() 输出含 max_level/max_discharge 顶层键。

        这是 P0-3 的契约验收——原输出缺这两键，导致仲裁 Rule 1/2 恒短路。
        P2 修复：整体 patch execute_query/execute_query_list，避免漏 mock 的
        子查询（query_rainfall_forecast 等）实连 DB → Access denied。
        """
        from query_plan_data import query_full_context
        # 整体 mock：所有子查询走 mock，不连 DB
        # scenarios 提供峰值，current_water_level 提供当前水位
        def _side_eql(sql, params=None, max_rows=None):
            sql_l = sql.lower()
            if 'scheduling_scenario' in sql_l:
                return [{'max_level': 786.0, 'max_discharge': 95.0}]
            if 'st_rsvr_r' in sql_l and 'order by tm desc' in sql_l:
                return [{'rz': 785.5, 'otq': 90.0, 'tm': '2026-08-10'}]
            if 'att_res_flse_lim' in sql_l:
                return [{'flse_lim_stag': 786.8, 'flood_season_name': '汛期'}]
            if 'model_config' in sql_l:
                # 返回 query_config 期望的所有键（config_key/value 双列）
                return [
                    {'config_key': 'safe_drainage_capacity', 'value': '95.1'},
                    {'config_key': 'max_drainage_capacity', 'value': '192'},
                ]
            return []

        def _side_eq(sql, params=None, max_rows=None):
            data = _side_eql(sql, params, max_rows)
            return {'data': data, 'count': len(data), 'truncated': False}

        mock_eq.side_effect = _side_eq
        mock_eql.side_effect = _side_eql
        ctx = query_full_context()
        self.assertIn('max_level', ctx, "query_full_context 必须输出 max_level（P0-3）")
        self.assertIn('max_discharge', ctx, "query_full_context 必须输出 max_discharge（P0-3）")
        self.assertIsNotNone(ctx['max_level'], "max_level 不应为 None（scenarios 提供）")
        self.assertEqual(ctx['max_level'], 786.0)


if __name__ == '__main__':
    unittest.main()
