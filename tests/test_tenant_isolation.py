#!/usr/bin/env python3
"""
租户隔离回归测试（P3-5）。

验证 P0-1 修复的查询函数在 mock 双 tenant（18/20）数据下只回本租户行，
杜绝三岔(18)/桃曲坡(20)数据串库——历史 bug 同形复发。

mock 策略：patch 被测脚本模块自身绑定的 execute_query_list / execute_query
引用（各脚本用 `from lib.db import ...`，需 patch 模块级名字）。
无需真实 DB。
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 各 skill scripts 加入 path
_PLAN_SCRIPTS = os.path.join(_REPO_ROOT, "plan-generation", "scripts")
_SIM_SCRIPTS = os.path.join(_REPO_ROOT, "simulation", "scripts")
_EW_SCRIPTS = os.path.join(_REPO_ROOT, "early-warning", "scripts")
_FC_SCRIPTS = os.path.join(_REPO_ROOT, "forecasting", "scripts")
for _p in (_PLAN_SCRIPTS, _SIM_SCRIPTS, _EW_SCRIPTS, _FC_SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ===========================================================================
# plan-generation/scripts/query_plan_data.py
# ===========================================================================
class TestPlanDataTenantIsolation(unittest.TestCase):

    @patch('query_plan_data.execute_query_list')
    def test_query_flood_limit_filters_by_tenant(self, mock_eql):
        """query_flood_limit 应在 WHERE 含 tenant_id。"""
        from query_plan_data import query_flood_limit
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = [{'flse_lim_stag': 786.8}]
        query_flood_limit()
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(20, params)

    @patch('query_plan_data.execute_query')
    def test_query_historical_plans_filters_by_tenant(self, mock_eq):
        """query_historical_plans 应含 tenant_id 过滤。"""
        from query_plan_data import query_historical_plans
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eq.return_value = {'data': [], 'count': 0, 'truncated': False}
        query_historical_plans(limit=5)
        sql, params = mock_eq.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)

    @patch('query_plan_data.execute_query')
    def test_query_similar_plans_filters_by_tenant(self, mock_eq):
        """query_similar_plans 应含 tenant_id 过滤。"""
        from query_plan_data import query_similar_plans
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eq.return_value = {'data': [], 'count': 0, 'truncated': False}
        query_similar_plans(water_level=786.0, limit=3)
        sql, params = mock_eq.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(20, params)

    @patch('query_plan_data.execute_query')
    def test_query_recent_rainfall_filters_by_tenant(self, mock_eq):
        """query_recent_rainfall (plan-gen) 应含 tenant_id 过滤。"""
        from query_plan_data import query_recent_rainfall
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eq.return_value = {'data': [], 'count': 0, 'truncated': False}
        query_recent_rainfall(hours=24)
        sql, params = mock_eq.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)


# ===========================================================================
# simulation/scripts/query_simulation_data.py
# ===========================================================================
class TestSimulationDataTenantIsolation(unittest.TestCase):

    @patch('query_simulation_data.execute_query_list')
    def test_query_recent_rainfall_filters_by_tenant(self, mock_eql):
        """query_recent_rainfall (simulation) 应含 tenant_id 过滤。"""
        from query_simulation_data import query_recent_rainfall
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = []
        query_recent_rainfall(hours=48)
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(20, params)

    @patch('query_simulation_data.execute_query_list')
    def test_query_similar_floods_filters_by_tenant(self, mock_eql):
        """query_similar_floods 应含 tenant_id 过滤。"""
        from query_simulation_data import query_similar_floods
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eql.return_value = []
        query_similar_floods(rainfall=100, tolerance=0.2, limit=10)
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)

    @patch('query_simulation_data.execute_query_list')
    def test_query_scenarios_filters_by_tenant(self, mock_eql):
        """query_scenarios (simulation) 应含 tenant_id 过滤。"""
        from query_simulation_data import query_scenarios
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = []
        query_scenarios()
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(20, params)

    @patch('query_simulation_data.execute_query_list')
    def test_query_flood_detail_filters_by_tenant(self, mock_eql):
        """query_flood_detail 应含 tenant_id 过滤。"""
        from query_simulation_data import query_flood_detail
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eql.return_value = []
        query_flood_detail(flood_id=1)
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)


# ===========================================================================
# early-warning/scripts/query_early_warning.py
# ===========================================================================
class TestEarlyWarningTenantIsolation(unittest.TestCase):

    @patch('query_early_warning.execute_query_list')
    def test_query_water_level_filters_by_tenant(self, mock_eql):
        """query_water_level (st_rsvr_r) 应含 tenant_id 过滤。"""
        from query_early_warning import query_water_level
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eql.return_value = []
        query_water_level(station_code='3')
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)

    @patch('query_early_warning.execute_query_list')
    def test_query_rainfall_filters_by_tenant(self, mock_eql):
        """query_rainfall (st_pptn_r) 应含 tenant_id 过滤。"""
        from query_early_warning import query_rainfall
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eql.return_value = []
        query_rainfall(station_code='3')
        sql, params = mock_eql.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(20, params)


# ===========================================================================
# lib/filters.py 规则表正确性（P0-2 回归守卫）
# ===========================================================================
class TestFiltersRuleTable(unittest.TestCase):
    """验证 P0-2 修复：att_res_flse_lim 应标 filter:True。"""

    def test_att_res_flse_lim_filter_is_true(self):
        sys.path.insert(0, os.path.join(_REPO_ROOT, 'lib'))
        import filters
        rule = filters.TENANT_ID_FILTER_TABLES.get('att_res_flse_lim')
        self.assertIsNotNone(rule, "att_res_flse_lim 未在 TENANT_ID_FILTER_TABLES 注册")
        self.assertTrue(rule['filter'], "att_res_flse_lim 必须标 filter:True（P0-2）")

    def test_st_rsvr_r_filter_is_true(self):
        sys.path.insert(0, os.path.join(_REPO_ROOT, 'lib'))
        import filters
        rule = filters.TENANT_ID_FILTER_TABLES.get('st_rsvr_r')
        self.assertTrue(rule['filter'])

    def test_ew_info_message_filter_is_false(self):
        sys.path.insert(0, os.path.join(_REPO_ROOT, 'lib'))
        import filters
        rule = filters.TENANT_ID_FILTER_TABLES.get('ew_info_message')
        self.assertFalse(rule['filter'])


# ===========================================================================
# forecasting/scripts/query_forecast_data.py —— S4：f_rnfl_h 补 tenant
# ===========================================================================
class TestForecastingTenantIsolation(unittest.TestCase):

    @patch('query_forecast_data.execute_query')
    def test_query_rainfall_forecast_filters_by_tenant(self, mock_eq):
        """query_rainfall_forecast (f_rnfl_h) 应含 tenant_id 过滤（S4）。"""
        from query_forecast_data import query_rainfall_forecast
        os.environ['SRM_TENANT_ID'] = '18'
        mock_eq.return_value = {'data': [], 'count': 0, 'truncated': False}
        query_rainfall_forecast(hours=48)
        sql, params = mock_eq.call_args[0]
        self.assertIn('tenant_id', sql)
        self.assertIn(18, params)

    @patch('query_forecast_data.execute_query')
    def test_multi_source_overview_hewind_filters_by_tenant(self, mock_eq):
        """multi_source_overview 的 f_rnfl_h 168h 聚合应含 tenant_id 过滤（S4 勘误第二处）。"""
        from query_forecast_data import query_multi_source_overview
        os.environ['SRM_TENANT_ID'] = '20'
        mock_eq.return_value = {'data': [{}], 'count': 1, 'truncated': False}
        query_multi_source_overview()
        seen = []
        for c in mock_eq.call_args_list:
            sql = c[0][0]
            if 'f_rnfl_h' in sql:
                params = c[0][1] if len(c[0]) > 1 else c[1].get('params', ())
                seen.append((sql, params))
        self.assertTrue(seen, "f_rnfl_h 查询未被调用")
        for sql, params in seen:
            self.assertIn('tenant_id', sql)
            self.assertIn(20, params)


if __name__ == '__main__':
    unittest.main()
