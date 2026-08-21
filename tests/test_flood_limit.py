#!/usr/bin/env python3
"""lib/flood_limit 汛限单一实现测试（C2）——mock DB 层，无真实 DB。"""
import os
import sys
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _season_row(name='主汛期', s='0601', e='1031', stag=786.0):
    return {'flse_lim_stag': stag, 'flood_season_name': name,
            'flood_season_start': s, 'flood_season_end': e}


class TestCurrentFloodLimit(unittest.TestCase):

    @patch('lib.flood_limit.execute_query_list')
    def test_in_season_match(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[_season_row()], []]
        r = fl.current_flood_limit(18)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['flse_lim_stag'], 786.0)
        # tenant 必须参数化传入
        sql, params = mock_eql.call_args_list[0][0]
        self.assertIn('tenant_id = %s', sql)
        self.assertIn(18, params)

    @patch('lib.flood_limit.execute_query_list')
    def test_out_of_season_falls_back_to_main_season(self, mock_eql):
        """区间未命中 → 回退主汛期行（forecasting 语义，防洪更保守）。"""
        import lib.flood_limit as fl
        mock_eql.side_effect = [[_season_row('次汛期', '0601', '0630'),
                                 _season_row('主汛期', '0701', '0930', stag=785.0)], []]
        r = fl.current_flood_limit(20)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['flood_season_name'], '主汛期')
        self.assertEqual(r['flse_lim_stag'], 785.0)

    @patch('lib.flood_limit.execute_query_list')
    def test_no_season_rows_falls_back_to_base(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[], [{'fl_low_lim_lev': 790.0}]]
        r = fl.current_flood_limit(18)
        self.assertEqual(r['status'], 'fallback')
        self.assertEqual(r['flse_lim_stag'], 790.0)
        self.assertEqual(r['flood_season_name'], '非汛期')

    @patch('lib.flood_limit.execute_query_list')
    def test_missing(self, mock_eql):
        import lib.flood_limit as fl
        mock_eql.side_effect = [[], []]
        self.assertEqual(fl.current_flood_limit(18), {'status': 'missing'})

    def test_cross_year_documented_unsupported(self):
        """跨年汛期不支持——契约写进 docstring，本测试钉住源码里的说明。"""
        import lib.flood_limit as fl
        self.assertIn('跨年', fl.__doc__)


if __name__ == '__main__':
    unittest.main()
