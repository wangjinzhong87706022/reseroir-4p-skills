import json, unittest
from pathlib import Path
from eval.lib.schema import EvalCase
from eval.lib import report


def _c(i, skill, cat):
    return EvalCase(id=i, skill=skill, category=cat, description="d", question="q",
                    env={"SRM_TENANT_ID": 18}, source="s", truth_source="inline")


class TestReport(unittest.TestCase):
    def test_build_result_truncates(self):
        r = report.build_result(_c("1", "f", "c"), "PASS", 1.234, "x" * 600, {})
        self.assertTrue(r["output"].endswith("..."))
        self.assertEqual(r["elapsed_seconds"], 1.23)

    def test_summarize_skill_category(self):
        results = [
            report.build_result(_c("1", "f", "水位"), "PASS", 1, "o", {}),
            report.build_result(_c("2", "f", "水位"), "FAIL", 1, "o", {}),
            report.build_result(_c("3", "f", "降雨"), "PASS", 1, "o", {}),
        ]
        s = report.summarize(results)
        self.assertEqual(s["overall"], {"pass": 2, "total": 3, "rate": 0.667})
        self.assertEqual(s["by_skill"]["f"]["水位"], {"pass": 1, "total": 2, "rate": 0.5})

    def test_write_json_and_markdown(self):
        import tempfile
        results = [report.build_result(_c("1", "f", "c"), "PASS", 1, "o", {})]
        s = report.summarize(results)
        with tempfile.TemporaryDirectory() as d:
            jp, mp = Path(d) / "r.json", Path(d) / "r.md"
            report.write_json(results, s, jp)
            report.write_markdown(results, s, mp)
            self.assertEqual(json.loads(jp.read_text())["summary"]["overall"]["pass"], 1)
            self.assertIn("# 评估报告", mp.read_text())

if __name__ == "__main__":
    unittest.main()
