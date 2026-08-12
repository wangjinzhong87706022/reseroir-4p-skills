import unittest, tempfile, textwrap
from pathlib import Path
from eval.lib.schema import EvalCase, load_file, load_all, validate

YAML = textwrap.dedent("""
forbidden_keywords: [三岔]
cases:
  - id: T1
    skill: forecasting
    category: 水位
    description: d
    question: q
    env: {SRM_TENANT_ID: 20, SRM_RESERVOIR_NAME: taoqupo}
    source: old::T1
    truth_source: inline
    expected_keywords: ["4420"]
    forbidden: [桃曲坡]
""")

class TestSchema(unittest.TestCase):
    def test_load_merges_file_forbidden(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.yaml"; p.write_text(YAML, encoding="utf-8")
            cases = load_file(p)
        self.assertEqual(len(cases), 1)
        c = cases[0]
        self.assertEqual(set(c.forbidden), {"三岔", "桃曲坡"})  # 题级 + 文件级取并集

    def test_load_all_detects_duplicate_id(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"a.yaml").write_text(YAML, encoding="utf-8")
            (Path(d)/"b.yaml").write_text(YAML, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_all(d)

    def test_validate_rejects_bad_truth_source(self):
        c = EvalCase(id="X", skill="forecasting", category="c", description="d",
                     question="q", env={"SRM_TENANT_ID": 18}, source="s", truth_source="bogus")
        with self.assertRaises(ValueError):
            validate(c)

    def test_validate_requires_truth_fields(self):
        base = dict(id="X", skill="forecasting", category="c", description="d",
                    question="q", env={"SRM_TENANT_ID": 18}, source="s")
        # live_db 缺 truth_query
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="live_db"))
        # rubric 缺 rubric
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="rubric"))
        # inline 缺 keywords 与 range
        with self.assertRaises(ValueError):
            validate(EvalCase(**base, truth_source="inline"))

if __name__ == "__main__":
    unittest.main()
