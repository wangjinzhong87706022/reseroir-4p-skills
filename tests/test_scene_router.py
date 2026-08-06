"""scene_router 场景识别单测：四场景路由 + 混合 trigger 优先级 + 边界输入。

重点（M1 回归保护）：EMERGENCY_STRONG（险情/溃坝/管涌/闸门故障…）必须优先于
DAILY_STRONG（每日/日报/例行…）——"每日+闸门故障"这类混合输入必须归 D（应急），
不能因词表顺序调整被误归 C（日常）。

usage: python3 -m unittest tests.test_scene_router
"""
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "supervisor" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from scene_router import route  # noqa: E402


class TestSceneRouting(unittest.TestCase):
    """四场景关键词路由。"""

    def test_emergency_keywords_route_to_D(self):
        for kw in ("闸门故障", "溃坝", "管涌", "险情", "抢险", "人员转移", "漫坝"):
            r = route(f"发生{kw}，请处置")
            self.assertEqual(r["scene"], "D", f"关键词 {kw} 应路由到 D")

    def test_storm_keywords_route_to_A(self):
        for kw in ("暴雨", "超汛限", "红色预警", "入库流量", "泄洪"):
            r = route(f"{kw}研判")
            self.assertEqual(r["scene"], "A", f"关键词 {kw} 应路由到 A")

    def test_dam_keywords_route_to_B(self):
        for kw in ("渗压异常", "渗流", "位移超限", "裂缝", "扬压力"):
            r = route(f"{kw}诊断")
            self.assertEqual(r["scene"], "B", f"关键词 {kw} 应路由到 B")

    def test_daily_keywords_route_to_C(self):
        for kw in ("日报", "例行", "值班", "巡检"):
            r = route(f"{kw}汇报")
            self.assertEqual(r["scene"], "C", f"关键词 {kw} 应路由到 C")


class TestMixedTriggerPriority(unittest.TestCase):
    """M1 回归保护：混合 trigger 的优先级（D 应急 > C 日常）。"""

    def test_daily_plus_emergency_routes_to_D(self):
        """'每日例行 + 闸门故障' → 必须归 D，不能因每日词归 C。"""
        r = route("每日例行汇报，但闸门故障需要应急处置")
        self.assertEqual(r["scene"], "D")
        self.assertIn("闸门故障", r["matched_keywords"])

    def test_daily_plus_dam_breach_routes_to_D(self):
        """'每日例行 + 溃坝' → 必须归 D。"""
        r = route("每日例行巡查发现溃坝风险")
        self.assertEqual(r["scene"], "D")

    def test_priority_order_emergency_over_storm(self):
        """应急词(D, 优先级100) > 暴雨词(A, 80)：'暴雨' 与 '闸门故障' 同时出现归 D。"""
        r = route("暴雨红色预警，闸门故障需立即处置")
        self.assertEqual(r["scene"], "D")

    def test_priority_order_storm_over_daily(self):
        """无强信号词时按普通关键词优先级：'暴雨'(A,80) > '值班'(C,40) → A。"""
        r = route("当前有暴雨，值班期间需关注")
        self.assertEqual(r["scene"], "A")

    def test_daily_strong_word_wins_over_keywords(self):
        """DAILY_STRONG 强信号词（每日/日报）优先于普通关键词——设计意图：
        '每日'命中即归 C，即使同时含普通 A 关键词（暴雨）。"""
        r = route("每日水情汇报，今日有暴雨")
        self.assertEqual(r["scene"], "C")


class TestEdgeCases(unittest.TestCase):
    """边界输入。"""

    def test_empty_returns_unknown(self):
        r = route("")
        self.assertEqual(r["scene"], "UNKNOWN")

    def test_none_returns_unknown(self):
        r = route(None)
        self.assertEqual(r["scene"], "UNKNOWN")

    def test_whitespace_returns_unknown(self):
        r = route("   ")
        self.assertEqual(r["scene"], "UNKNOWN")

    def test_unmatched_returns_unknown(self):
        r = route("今天天气不错")
        self.assertEqual(r["scene"], "UNKNOWN")
        self.assertEqual(r["dag"], None)


if __name__ == "__main__":
    unittest.main()
