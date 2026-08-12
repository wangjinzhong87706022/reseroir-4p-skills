import unittest
from eval.lib.schema import EvalCase
from eval.lib import judge


def _case(**kw):
    base = dict(id="X", skill="forecasting", category="c", description="d", question="q",
                env={"SRM_TENANT_ID": 18}, source="s", truth_source="inline")
    base.update(kw)
    return EvalCase(**base)


class TestInlineJudge(unittest.TestCase):
    def test_pass_on_keywords_and_range(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        out = "当前水位 462.5 m"
        r = judge.judge_inline(c, out)
        self.assertEqual(r["verdict"], "PASS")

    def test_fail_when_range_misses(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        r = judge.judge_inline(c, "当前水位 500 m")
        self.assertEqual(r["verdict"], "FAIL")

    def test_fail_on_forbidden(self):
        c = _case(expected_keywords=["水位"], forbidden=["桃曲坡"])
        r = judge.judge_inline(c, "桃曲坡 当前水位 462 m")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("桃曲坡", r["detail"]["forbidden_hits"])

if __name__ == "__main__":
    unittest.main()
