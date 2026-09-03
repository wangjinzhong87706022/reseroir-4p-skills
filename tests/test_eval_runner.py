import pathlib
import unittest
from eval import run as runmod  # eval/run.py 是合法模块名（eval/__init__.py 已在 Task 1 建立）


def _quiet_main(*args, **kw):
    """main() 的进度 print 不排进 unittest 输出（评审 P4：CI 日志串扰）。"""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return runmod.main(*args, **kw)


class TestRunner(unittest.TestCase):

    def _cases_yaml(self, tmp):
        (pathlib.Path(tmp) / "forecasting.yaml").write_text(
            "cases:\n"
            "  - {id: F1, skill: forecasting, category: c, description: d, question: q1,\n"
            "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: inline,\n"
            "     expected_keywords: [水位]}\n"
            "  - {id: F2, skill: forecasting, category: c, description: d, question: q2,\n"
            "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: inline,\n"
            "     expected_keywords: [不存在词]}\n", encoding="utf-8")

    def test_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            rc = _quiet_main(["--list", "--cases-dir", d])
            self.assertEqual(rc, 0)

    def test_filter_and_run_with_fake_transport(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                return {"output": "当前水位 462 m", "answer": "当前水位 462 m",
                        "stderr": "", "exit_code": 0, "timed_out": False}
            rc = _quiet_main(["--skill", "forecasting", "--cases-dir", d,
                              "--report-dir", d, "--keywords-mode", "hard"],
                             transport_fn=fake_transport)
            self.assertEqual(rc, 1)  # F2 FAIL（缺"不存在词"）→ 有 FAIL → 退出码 1
            # T4 起 expected_keywords 默认 advisory（只报告不判分），本用例锁的是旧 hard 语义 → 显式传 hard

    def test_default_keywords_mode_advisory_end_to_end(self):
        """T4 端到端：默认 advisory 下关键词未命中不再 FAIL，且报告 meta 记录 keywords_mode。"""
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                return {"output": "当前水位 462 m", "answer": "当前水位 462 m",
                        "stderr": "", "exit_code": 0, "timed_out": False}
            rc = _quiet_main(["--skill", "forecasting", "--cases-dir", d,
                              "--report-dir", d], transport_fn=fake_transport)
            self.assertEqual(rc, 0)  # F2 缺"不存在词" → advisory 下不参与判分
            jp = sorted(pathlib.Path(d).glob("eval-*.json"))[-1]
            summary = json.loads(jp.read_text())["summary"]
            self.assertEqual(summary["meta"]["keywords_mode"], "advisory")

    def test_all_pass_exit_zero(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                # 让两题都过：输出含两题的关键词
                return {"output": "水位 不存在词 都在", "answer": "水位 不存在词 都在",
                        "stderr": "", "exit_code": 0, "timed_out": False}
            rc = _quiet_main(["--cases-dir", d, "--report-dir", d], transport_fn=fake_transport)
            self.assertEqual(rc, 0)

    def test_transport_exception_becomes_error_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._cases_yaml(d)
            def boom(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                raise RuntimeError("hermes exploded")
            rc = _quiet_main(["--cases-dir", d, "--report-dir", d], transport_fn=boom)
            self.assertEqual(rc, 1)  # 异常 → ERROR → 非 all-PASS → 1；run 未崩溃
            # 即便有用例异常，报告文件照常写出
            self.assertTrue(any(p.suffix == ".json" for p in pathlib.Path(d).glob("eval-*.json")))

    def test_db_connect_failure_does_not_crash(self):
        import tempfile
        from eval.lib import truth
        with tempfile.TemporaryDirectory() as d:
            # 一个 live_db 题 + 一个 inline 题
            (pathlib.Path(d) / "forecasting.yaml").write_text(
                "cases:\n"
                "  - {id: L1, skill: forecasting, category: c, description: d, question: q,\n"
                "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: live_db,\n"
                "     truth_query: 'SELECT rz FROM st_rsvr_r LIMIT 1', tolerance: 1.0}\n"
                "  - {id: I1, skill: forecasting, category: c, description: d, question: q,\n"
                "     env: {SRM_TENANT_ID: 18}, source: t, truth_source: inline,\n"
                "     expected_keywords: [水位]}\n", encoding="utf-8")
            def fake_transport(question, skill_id, env, timeout, skill_dir=None, _runner=None):
                return {"output": "水位 462 m", "answer": "水位 462 m",
                        "stderr": "", "exit_code": 0, "timed_out": False}
            orig = truth.make_db_query_fn
            truth.make_db_query_fn = lambda env: (_ for _ in ()).throw(RuntimeError("DB down"))
            try:
                rc = _quiet_main(["--cases-dir", d, "--report-dir", d], transport_fn=fake_transport)
            finally:
                truth.make_db_query_fn = orig
            self.assertEqual(rc, 1)  # live_db 题 ERROR + inline 题 PASS → 非 all-PASS → 1；未崩溃
            self.assertTrue(any(p.suffix == ".json" for p in pathlib.Path(d).glob("eval-*.json")))

if __name__ == "__main__":
    unittest.main()
