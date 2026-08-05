"""arbitrator 单元测试：场景B（大坝诊断）与场景D（应急响应）专用仲裁。

覆盖评审 #11：今日 v0.4.0 新增的 arbitrate_dam_diagnosis / arbitrate_emergency
核心定级与裁决逻辑，含正常档/边界档/异常输入守卫。
"""
import os
import sys
import unittest

# 让脚本能被 import（supervisor/scripts 加入 path）
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "supervisor", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from arbitrator import (arbitrate_dam_diagnosis, arbitrate_emergency,
                        arbitrate_plan_vs_simulation, arbitrate_risk_levels)


# --------------------------------------------------------------------------
# 场景B：arbitrate_dam_diagnosis 风险定级
# --------------------------------------------------------------------------
class TestDamDiagnosis(unittest.TestCase):
    def _sim(self, rz):
        """构造 simulation full_context：current_water_level 数组。"""
        return {"current_water_level": [{"rz": rz, "otq": 10.0}]}

    def test_low_risk_when_all_normal(self):
        """数据正常 + 无缺陷 + 水位未超限 → 低"""
        diagnosis = {"st_rsvr_r": {"age_hours": 1, "null_rate": 0}}
        inspection = {"open_defects": []}
        r = arbitrate_dam_diagnosis(diagnosis, inspection, self._sim(786.0),
                                    flood_limit=786.8)
        self.assertEqual(r["risk_level"], "低")
        self.assertTrue(r["passed"])
        self.assertEqual(r["decision"], "accept")

    def test_high_risk_when_data_stale(self):
        """数据严重过期(>24h) → 高"""
        diagnosis = {"st_rsvr_r": {"age_hours": 30, "null_rate": 0}}
        r = arbitrate_dam_diagnosis(diagnosis, {}, self._sim(786.0),
                                    flood_limit=786.8)
        self.assertEqual(r["risk_level"], "高")
        self.assertFalse(r["passed"])
        self.assertEqual(r["decision"], "escalate")

    def test_high_risk_when_null_rate_over_50(self):
        """空值率>50% → 高"""
        diagnosis = {"st_rsvr_r": {"age_hours": 1, "null_rate": 60}}
        r = arbitrate_dam_diagnosis(diagnosis, {}, self._sim(786.0),
                                    flood_limit=786.8)
        self.assertEqual(r["risk_level"], "高")

    def test_high_risk_when_sim_over_flood_limit(self):
        """仿真最高水位超汛限 → 高"""
        r = arbitrate_dam_diagnosis({}, {}, self._sim(787.0),
                                    flood_limit=786.8)
        self.assertEqual(r["risk_level"], "高")
        self.assertFalse(r["passed"])
        self.assertIn("超汛限", r["issues"][0])

    def test_medium_risk_when_open_defects(self):
        """存在未处理缺陷(handle_status=0) → 中"""
        inspection = {"open_defects": [{"name": "渗漏", "handle_status": 0}]}
        r = arbitrate_dam_diagnosis({}, inspection, self._sim(786.0),
                                    flood_limit=786.8)
        self.assertEqual(r["risk_level"], "中")
        self.assertEqual(r["decision"], "review")
        self.assertEqual(r["open_defect_count"], 1)

    def test_defects_nested_in_defects_key(self):
        """缺陷清单嵌套在 defects.open_defects 路径也能取到"""
        inspection = {"defects": {"open_defects": [{"name": "裂缝", "handle_status": 0}]}}
        r = arbitrate_dam_diagnosis({}, inspection, self._sim(786.0),
                                    flood_limit=786.8)
        self.assertEqual(r["open_defect_count"], 1)

    def test_robust_to_none_inputs(self):
        """None 输入不应崩溃，回退低风险（无证据即无定级依据）"""
        r = arbitrate_dam_diagnosis(None, None, None, flood_limit=786.8)
        self.assertEqual(r["risk_level"], "低")
        self.assertTrue(r["passed"])

    def test_suggestion_present_for_all_levels(self):
        """每个风险等级都有处置建议文本"""
        for level_args in [
            ({}, {}, self._sim(786.0)),                      # 低
            ({}, {"open_defects": [{"handle_status": 0}]}, self._sim(786.0)),  # 中
            ({}, {}, self._sim(787.0)),                       # 高（超汛限）
        ]:
            r = arbitrate_dam_diagnosis(*level_args, flood_limit=786.8)
            self.assertTrue(r["suggestion"], f"缺处置建议: {r}")


# --------------------------------------------------------------------------
# 场景D：arbitrate_emergency 应急响应仲裁
# --------------------------------------------------------------------------
class TestEmergency(unittest.TestCase):
    def _sim(self, rz, otq=10.0):
        return {"current_water_level": [{"rz": rz, "otq": otq}]}

    def test_escalate_when_high_alerts(self):
        """存在高级别告警 → escalate"""
        early_warning = {"data": [{"ew_name": "超汛限", "level": "Ⅰ"}]}
        r = arbitrate_emergency(early_warning, {}, self._sim(786.0),
                                flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r["decision"], "escalate")
        self.assertEqual(r["risk_level"], "极高")
        self.assertEqual(r["alert_count"], 1)
        self.assertFalse(r["passed"])

    def test_reject_when_discharge_over_safe(self):
        """方案下泄超安全泄量 → reject"""
        plan = {"max_discharge": 600}
        r = arbitrate_emergency({}, plan, self._sim(786.0),
                                flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r["decision"], "reject")
        self.assertEqual(r["risk_level"], "高")
        self.assertFalse(r["passed"])

    def test_escalate_when_sim_over_flood_limit(self):
        """仿真最高水位超汛限 → escalate"""
        r = arbitrate_emergency({}, {}, self._sim(787.0),
                                flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r["decision"], "escalate")
        self.assertIn("超汛限", r["issues"][0])

    def test_pending_approval_when_all_clear(self):
        """无告警/超限/超泄 → pending_approval（待人工确认）"""
        r = arbitrate_emergency({}, {"max_discharge": 100}, self._sim(786.0),
                                flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r["decision"], "pending_approval")
        self.assertTrue(r["passed"])
        self.assertEqual(r["risk_level"], "中")

    def test_hitl_always_required(self):
        """应急场景 HITL 恒强制"""
        r = arbitrate_emergency({}, {}, self._sim(786.0),
                                flood_limit=786.8, safe_discharge=500)
        self.assertTrue(r["hitl_required"])

    def test_robust_to_none_inputs(self):
        """None 输入不应崩溃"""
        r = arbitrate_emergency(None, None, None,
                                flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r["decision"], "pending_approval")
        self.assertTrue(r["hitl_required"])

    def test_reject_overrides_escalate_priority(self):
        """同时触发 reject 和 escalate 条件时，建议逻辑仍可给出对应建议（不崩溃）"""
        early_warning = {"data": [{"ew_name": "溃坝", "level": "Ⅰ"}]}
        plan = {"max_discharge": 600}
        r = arbitrate_emergency(early_warning, plan, self._sim(787.0),
                                flood_limit=786.8, safe_discharge=500)
        # reject 是后赋值的，会覆盖 escalate
        self.assertEqual(r["decision"], "reject")
        self.assertFalse(r["passed"])


# --------------------------------------------------------------------------
# 通用规则：arbitrate_risk_levels 取更高等级
# --------------------------------------------------------------------------
class TestRiskLevels(unittest.TestCase):
    def test_takes_higher(self):
        self.assertEqual(arbitrate_risk_levels(["低", "高", "中"]), "高")
        self.assertEqual(arbitrate_risk_levels(["中", "极高"]), "极高")

    def test_empty_returns_low(self):
        self.assertEqual(arbitrate_risk_levels([]), "低")

    def test_none_skipped(self):
        self.assertEqual(arbitrate_risk_levels([None, "中", None]), "中")


# --------------------------------------------------------------------------
# 通用规则：arbitrate_plan_vs_simulation 场景A
# --------------------------------------------------------------------------
class TestPlanVsSimulation(unittest.TestCase):
    def test_accept_when_consistent(self):
        plan = {"max_level": 786.0, "max_discharge": 100}
        sim = {"max_level": 786.5, "max_discharge": 100}
        r = arbitrate_plan_vs_simulation(plan, sim,
                                         flood_limit=786.8, safe_discharge=500)
        self.assertTrue(r.passed)
        self.assertEqual(r.decision, "accept")

    def test_adjust_when_plan_above_sim(self):
        """方案预估高于仿真 → 以仿真为准（保守）"""
        plan = {"max_level": 787.0, "max_discharge": 100}
        sim = {"max_level": 786.5, "max_discharge": 100}
        r = arbitrate_plan_vs_simulation(plan, sim,
                                         flood_limit=786.8, safe_discharge=500)
        self.assertFalse(r.passed)
        self.assertEqual(r.decision, "adjust")
        self.assertEqual(r.adopted_values.get("max_level"), 786.5)

    def test_reject_when_discharge_over_safe(self):
        plan = {"max_level": 786.0, "max_discharge": 600}
        sim = {"max_level": 786.0, "max_discharge": 600}
        r = arbitrate_plan_vs_simulation(plan, sim,
                                         flood_limit=786.8, safe_discharge=500)
        self.assertEqual(r.decision, "reject")
        self.assertFalse(r.passed)


if __name__ == "__main__":
    unittest.main()
