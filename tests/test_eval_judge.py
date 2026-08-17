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

class TestLiveDbJudge(unittest.TestCase):
    def test_pass(self):
        c = _case(truth_source="live_db", truth_query="SELECT rsvr_rz FROM st_rsvr_r LIMIT 1",
                  tolerance=1.0, expected_keywords=["水位"])
        qf = lambda sql: [{"rsvr_rz": 462.5}]
        r = judge.judge_live_db(c, "当前水位 462.4 m", qf)
        self.assertEqual(r["verdict"], "PASS")

    def test_error_when_empty(self):
        c = _case(truth_source="live_db", truth_query="SELECT x", tolerance=1.0)
        r = judge.judge_live_db(c, "out", lambda sql: [])
        self.assertEqual(r["verdict"], "ERROR")

    def test_error_when_truth_not_numeric(self):
        # truth_query 返回非数值（如 'N/A' / None）时，应返回清晰 ERROR 而非抛 ValueError
        c = _case(truth_source="live_db", truth_query="SELECT label FROM t LIMIT 1",
                  tolerance=1.0)
        for bad in ([{"label": "N/A"}], [{"label": None}], [["N/A"]]):
            r = judge.judge_live_db(c, "水位 462 m", lambda sql: bad)
            self.assertEqual(r["verdict"], "ERROR", f"bad={bad}")
            self.assertIn("真值非数值", r["detail"]["reason"], f"bad={bad}")


class TestRubricJudge(unittest.TestCase):
    def test_skip_without_llm(self):
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        r = judge.judge_rubric(c, "当前水位 462 m")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["detail"]["rubric"], "skip (no llm)")

    def test_fail_rule_layer_forbidden(self):
        c = _case(truth_source="rubric", rubric=["x"], forbidden=["桃曲坡"])
        r = judge.judge_rubric(c, "桃曲坡 结果", None)
        self.assertEqual(r["verdict"], "FAIL")

    def test_with_llm(self):
        c = _case(truth_source="rubric", rubric=["必须给数值"])
        fake = lambda out, rub: {"passed": True, "items": [{"criterion": "必须给数值", "pass": True}]}
        r = judge.judge_rubric(c, "ok", fake)
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("rubric_score", r["detail"])

    def test_rule_pass_but_llm_fail(self):
        """规则层过 + LLM 判不过 → FAIL（AND 语义回归，评审 P10）。"""
        c = _case(truth_source="rubric", rubric=["必须给数值"], expected_keywords=["水位"])
        fake = lambda out, rub: {"passed": False, "items": [{"criterion": "必须给数值", "pass": False}]}
        r = judge.judge_rubric(c, "当前水位 462 m", fake)
        self.assertEqual(r["verdict"], "FAIL")


class TestLlmJudge(unittest.TestCase):
    def test_parses_strict_json(self):
        class B:
            def __init__(self, t): self.text = t
        class R:
            def __init__(self, t): self.content = [B(t)]
        class Client:
            def __init__(self, t=None): self._t = t
            class messages:
                @staticmethod
                def create(**kw):
                    return R('{"passed": true, "items": [{"criterion": "必须给数值", "pass": true}]}')
        r = judge.llm_judge("out", ["必须给数值"], client=Client())
        self.assertTrue(r["passed"])
        self.assertEqual(len(r["items"]), 1)

    def test_build_prompt_lists_all_rubric(self):
        prompt = judge._build_prompt("输出X", ["a", "b"])
        self.assertIn("a", prompt)
        self.assertIn("b", prompt)

    def test_model_from_env_override(self):
        """EVAL_JUDGE_MODEL 覆盖默认模型（评审 P8：不硬编码）。"""
        import os
        from unittest import mock
        captured = {}

        class R:
            content = []

        class Client:
            class messages:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    return R()

        with mock.patch.dict(os.environ, {"EVAL_JUDGE_MODEL": "claude-haiku-4-5"}):
            judge.llm_judge("out", ["c"], client=Client())
        self.assertEqual(captured["model"], "claude-haiku-4-5")


if __name__ == "__main__":
    unittest.main()
