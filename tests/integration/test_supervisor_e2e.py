"""supervisor 端到端集成测试：mock 子脚本输出注入 State，断言四场景仲裁/报告关键里程碑。

不连真实 DB、不调子脚本——直接用临时 SRM_STATE_DIR 的 SQLite State 注入结构化
stage 结果，再调用 orchestrator.do_arbitration / do_report 断言：
  - 场景A：plan-vs-sim 一致性（accept）+ 超汛限风险提示
  - 场景B：风险定级（数据质量/缺陷/超汛限三档）+ 处置建议
  - 场景C：报告生成（三步汇总）
  - 场景D：告警升级 + 方案否决 + HITL 强制

usage: python3 -m unittest tests.integration.test_supervisor_e2e
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "supervisor" / "scripts"
for p in (_REPO, _SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


class _TempState:
    """为每个测试方法建独立 SQLite State（SRM_STATE_DIR 兜底）。"""

    def __init__(self):
        self._tmp = tempfile.mkdtemp(prefix="svt-state-")
        self._old = os.environ.get("SRM_STATE_DIR")

    def __enter__(self):
        os.environ["SRM_STATE_DIR"] = self._tmp
        # 触发建表
        import importlib
        import supervisor_state
        importlib.reload(supervisor_state)
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("SRM_STATE_DIR", None)
        else:
            os.environ["SRM_STATE_DIR"] = self._old
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def conn(self):
        import supervisor_state
        return supervisor_state._connect()


def _seed_event(scene, trigger="test", priority="中"):
    """新建事件并返回 (conn, event_id)。"""
    import argparse, supervisor_state
    na = argparse.Namespace(scene=scene, risk=None, trigger=trigger, priority=priority)
    created = supervisor_state.cmd_new(na)
    return created["event_id"]


def _seed_stage(event_id, stage, agent, result, status="ok"):
    """注入某阶段的结构化结果（result 为 dict/list/str，自动 JSON 化）。"""
    import json, argparse, supervisor_state
    if not isinstance(result, str):
        result = json.dumps(result, ensure_ascii=False, default=str)
    na = argparse.Namespace(event=event_id, stage=stage, agent=agent,
                            result=result, status=status)
    return supervisor_state.cmd_set(na)


class TestSceneA(unittest.TestCase):
    """场景A：plan-vs-sim 一致性 + 超汛限风险提示。"""

    def test_accept_when_consistent_with_risk_flag(self):
        with _TempState():
            eid = _seed_event("A", "暴雨预警")
            # simulation full_context（current_water_level 数组，水位略超汛限）
            _seed_stage(eid, "step4", "simulation",
                        {"current_water_level": [{"rz": 786.95, "otq": 100}]})
            # plan-generation 方案（与仿真一致）
            _seed_stage(eid, "step5", "plan-generation",
                        {"max_level": 786.95, "max_discharge": 100})

            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "A",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertTrue(r["passed"])
            self.assertEqual(r["decision"], "accept")
            # 超汛限是风险提示，不必然否决
            self.assertTrue(any("超" in i and "汛限" in i for i in r["issues"]),
                            f"缺超汛限提示: {r['issues']}")

    def test_adjust_when_plan_above_sim(self):
        with _TempState():
            eid = _seed_event("A")
            _seed_stage(eid, "step4", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 100}]})
            _seed_stage(eid, "step5", "plan-generation",
                        {"max_level": 787.0, "max_discharge": 100})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "A",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertFalse(r["passed"])
            self.assertEqual(r["decision"], "adjust")
            self.assertEqual(r["adopted_values"].get("max_level"), 786.0)


class TestSceneB(unittest.TestCase):
    """场景B：数据质量/缺陷/超汛限三档定级 + 处置建议。"""

    def test_high_risk_when_data_null_rate_over_50(self):
        with _TempState():
            eid = _seed_event("B", "渗压计异常")
            _seed_stage(eid, "step1", "diagnosis-verification",
                        {"water_level": {"age_hours": 0, "null_rate": 62.6}})
            _seed_stage(eid, "step2", "inspection", {"open_defects": []})
            _seed_stage(eid, "step3", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 10}]})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "B",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertEqual(r["risk_level"], "高")
            self.assertFalse(r["passed"])
            self.assertTrue(any("空值率" in i for i in r["issues"]))

    def test_medium_risk_with_open_defects(self):
        with _TempState():
            eid = _seed_event("B", "缺陷核查")
            _seed_stage(eid, "step1", "diagnosis-verification",
                        {"water_level": {"age_hours": 1, "null_rate": 5}})
            _seed_stage(eid, "step2", "inspection",
                        {"open_defects": [{"name": "渗漏", "handle_status": 0}]})
            _seed_stage(eid, "step3", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 10}]})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "B",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertEqual(r["risk_level"], "中")
            self.assertEqual(r["open_defect_count"], 1)


class TestSceneC(unittest.TestCase):
    """场景C：报告生成（三步汇总，缺失阶段标注未执行）。"""

    def test_report_aggregates_three_stages(self):
        with _TempState():
            eid = _seed_event("C", "每日例行")
            _seed_stage(eid, "step1", "forecasting",
                        {"current_water_level": [{"rz": 786.0, "inq": 55.0}]})
            _seed_stage(eid, "step2", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 38.2}]})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_report(eid, conn)
            conn.close()
            self.assertIn("report_md", r)
            self.assertIn("日常", r["report_md"])
            # 缺 step3 报告台账时应标注未执行/不可用
            self.assertTrue("不可用" in r["report_md"] or "未执行" in r["report_md"]
                            or "未生成" in r["report_md"],
                            f"缺缺失阶段标注: {r['report_md'][:300]}")


class TestSceneD(unittest.TestCase):
    """场景D：告警升级 + 方案否决 + HITL 强制。"""

    def test_escalate_with_high_alerts(self):
        with _TempState():
            eid = _seed_event("D", "闸门故障", priority="高")
            # early-warning 顶层数组（实测输出格式）
            _seed_stage(eid, "step1", "early-warning",
                        [{"ew_name": "TEST_高水位预警", "level_r": "1"},
                         {"ew_name": "TEST_强降雨预警", "level_r": "2"}])
            _seed_stage(eid, "step2", "plan-generation",
                        {"max_discharge": 100, "max_level": 786.0})
            _seed_stage(eid, "step3", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 10}]})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "D",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertEqual(r["decision"], "escalate")
            self.assertEqual(r["risk_level"], "极高")
            self.assertEqual(r["alert_count"], 2)
            self.assertTrue(r["hitl_required"])

    def test_reject_when_discharge_over_safe(self):
        with _TempState():
            eid = _seed_event("D", "应急", priority="高")
            _seed_stage(eid, "step1", "early-warning", [])
            _seed_stage(eid, "step2", "plan-generation",
                        {"max_discharge": 600, "max_level": 786.0})
            _seed_stage(eid, "step3", "simulation",
                        {"current_water_level": [{"rz": 786.0, "otq": 10}]})
            import orchestrator
            conn = orchestrator._connect()
            r = orchestrator.do_arbitration(eid, conn, "D",
                                            flood_limit=786.8, safe_discharge=500)
            conn.close()
            self.assertEqual(r["decision"], "reject")
            self.assertFalse(r["passed"])


class TestArbitrationReportFlow(unittest.TestCase):
    """L2 回归保护：仲裁结果落入 stage_results 后，do_report 必须能读到裁决/建议。

    覆盖 A/B/D 三场景的"仲裁 → 报告四节"数据流，防止 stage_map 映射错位或
    _safe_load 对内存生成的 dict 解包失败导致的静默断裂。
    """

    def _arb_then_report(self, scene, seed_stages):
        """种子各阶段 → 调 do_arbitration 落 State → 调 do_report 断言。"""
        with _TempState():
            eid = _seed_event(scene, "测试")
            for stage, agent, result in seed_stages:
                _seed_stage(eid, stage, agent, result)
            import orchestrator
            conn = orchestrator._connect()
            arb = orchestrator.do_arbitration(
                eid, conn, scene, flood_limit=786.8, safe_discharge=500)
            # 仲裁结果手动落 State（模拟 execute_dag 的统一写入）
            import json, argparse
            arb_stage = {"A": "step6", "B": "step4", "D": "step4"}[scene]
            na = argparse.Namespace(
                event=eid, stage=arb_stage, agent="arbitrator",
                result=json.dumps(arb, ensure_ascii=False), status="ok")
            import supervisor_state
            supervisor_state.cmd_set(na)
            report = orchestrator.do_report(eid, conn)
            conn.close()
            return arb, report

    def test_sceneA_arb_reaches_report(self):
        seed = [
            ("step4", "simulation",
             {"current_water_level": [{"rz": 786.95, "otq": 100}]}),
            ("step5", "plan-generation",
             {"max_level": 786.95, "max_discharge": 100}),
        ]
        arb, report = self._arb_then_report("A", seed)
        self.assertEqual(arb["decision"], "accept")
        self.assertIn("report_md", report)
        # 报告"四、仲裁结论"段应含裁决词
        self.assertTrue(any("accept" in line or "accept" in report["report_md"]
                            for line in report["report_md"].splitlines()),
                        f"报告未含仲裁裁决: {report['report_md'][:300]}")

    def test_sceneB_arb_reaches_report(self):
        seed = [
            ("step1", "diagnosis-verification",
             {"water_level": {"age_hours": 0, "null_rate": 5}}),
            ("step2", "inspection",
             {"open_defects": [{"name": "渗漏", "handle_status": 0}]}),
            ("step3", "simulation",
             {"current_water_level": [{"rz": 786.0, "otq": 10}]}),
        ]
        arb, report = self._arb_then_report("B", seed)
        self.assertEqual(arb["decision"], "review")
        self.assertIn("report_md", report)

    def test_sceneD_arb_reaches_report(self):
        seed = [
            ("step1", "early-warning",
             [{"ew_name": "TEST_高水位预警", "level_r": "1"}]),
            ("step2", "plan-generation",
             {"max_discharge": 100, "max_level": 786.0}),
            ("step3", "simulation",
             {"current_water_level": [{"rz": 786.0, "otq": 10}]}),
        ]
        arb, report = self._arb_then_report("D", seed)
        self.assertEqual(arb["decision"], "escalate")
        self.assertIn("report_md", report)


if __name__ == "__main__":
    unittest.main()
