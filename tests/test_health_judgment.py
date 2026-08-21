#!/usr/bin/env python3
"""evaluate_health 纯函数健康判定测试（T1）——无 DB、无 lib 依赖。"""
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_REPO_ROOT, "supervisor", "scripts")
for _p in (_REPO_ROOT, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from supervisor_state import evaluate_health


def _wl(age_h):
    return {"age_h": age_h, "max_tm": "2026-08-20 08:00:00", "cnt": 5}


def _rf(cnt):
    return {"cnt": cnt, "max_ymdh": "2026-08-27 08:00:00"}


def _al(total, high=0):
    return {"total": total, "high": high}


class TestEvaluateHealth(unittest.TestCase):

    def test_all_ok(self):
        checks, overall, d = evaluate_health("TQP", _wl(1.0), _rf(200), _al(3))
        self.assertEqual(overall, "ok")
        self.assertEqual(len(checks), 3)

    def test_stale_water_warns(self):
        checks, overall, _ = evaluate_health("TQP", _wl(9.0), _rf(200), _al(3))
        self.assertEqual(overall, "warn")
        self.assertTrue(any(c["item"] == "st_rsvr_r" and c["status"] == "warn"
                            for c in checks))

    def test_no_water_is_error(self):
        _, overall, _ = evaluate_health("TQP", _wl(None), _rf(0), _al(0))
        self.assertEqual(overall, "error")

    def test_low_forecast_coverage_warns(self):
        checks, overall, _ = evaluate_health("TQP", _wl(1.0), _rf(100), _al(3))
        self.assertEqual(overall, "warn")
        self.assertTrue(any(c["item"] == "f_rnfl_h" and c["status"] == "warn"
                            for c in checks))

    def test_alarm_pile_warns(self):
        checks, overall, d = evaluate_health("TQP", _wl(1.0), _rf(200), _al(1500, 12))
        self.assertEqual(overall, "warn")
        self.assertEqual(d["al_total"], 1500)
        self.assertEqual(d["al_high"], 12)

    def test_forecast_ok_msg_clean(self):
        """钉住 H3：ok 文案不得再出现 U+FFFD 替换字符。"""
        checks, _, _ = evaluate_health("TQP", _wl(1.0), _rf(200), _al(3))
        rf_ok = next(c for c in checks if c["item"] == "f_rnfl_h")
        self.assertEqual(rf_ok["msg"], "未来预报 200h 覆盖完整")


if __name__ == '__main__':
    unittest.main()
