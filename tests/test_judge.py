"""reservoir_profile 判定逻辑单元测试（unittest，无需 pytest）。"""
import unittest
from pathlib import Path

from tests.reservoir_profile import (
    verify_output, _extract_numbers, load_reservoir, TestCase,
)


class TestExtractNumbers(unittest.TestCase):
    def test_int_and_float(self):
        self.assertEqual(_extract_numbers("水位 786.8m，约 786"), [786.8, 786.0])

    def test_none_when_no_number(self):
        self.assertEqual(_extract_numbers("无数据"), [])

    def test_negative(self):
        self.assertEqual(_extract_numbers("蒸发 -15.7"), [-15.7])


class TestVerifyOutput(unittest.TestCase):
    def _case(self, **kw):
        base = dict(id="X", skill="s", description="d", question="q",
                    expected_keywords=["786.8", "汛限"])
        base.update(kw)
        return TestCase(**base)

    def test_keywords_pass(self):
        c = self._case()
        r = verify_output(c, "主汛限水位 786.8m", forbidden=[])
        self.assertTrue(r["all_passed"])
        self.assertEqual(r["forbidden_hits"], [])

    def test_keywords_miss_fails(self):
        c = self._case()
        r = verify_output(c, "正常蓄水位 788.5m", forbidden=[])
        self.assertFalse(r["all_passed"])

    def test_range_pass_when_any_in_range(self):
        c = self._case(expected_range={"min": 786.5, "max": 787.0})
        r = verify_output(c, "约 786.8 到 790 之间", forbidden=[])
        self.assertTrue(r["range_passed"])

    def test_range_fail_when_none_in_range(self):
        c = self._case(expected_range={"min": 786.5, "max": 787.0})
        r = verify_output(c, "水位 790.5m", forbidden=[])
        self.assertFalse(r["range_passed"])
        self.assertFalse(r["all_passed"])

    def test_forbidden_hit_overrides_to_fail(self):
        c = self._case()
        r = verify_output(c, "汛限 786.8 参考 三岔 水库", forbidden=["三岔", "462.5"])
        self.assertEqual(r["forbidden_hits"], ["三岔"])
        self.assertFalse(r["all_passed"])

    def test_no_range_skips_range_check(self):
        c = self._case()  # 无 expected_range
        r = verify_output(c, "汛限 786.8", forbidden=[])
        self.assertNotIn("range_passed", r)  # 无该字段视为不检查


class TestLoadReservoir(unittest.TestCase):
    def test_load_minimal_yaml(self):
        import tempfile
        yml = """
name: taoqupo
tenant_id: 20
display_name: 桃曲坡水库
forbidden_keywords: [三岔, 462.5]
cases:
  - id: TQ-PG1
    skill: plan-generation
    description: 汛限
    question: 主汛限水位？
    expected_keywords: [786.8, 汛限]
    expected_range: {min: 786.5, max: 787.0}
    timeout: 120
"""
        d = tempfile.mkdtemp()
        p = Path(d) / "taoqupo.yaml"
        p.write_text(yml, encoding="utf-8")
        prof = load_reservoir(p)
        self.assertEqual(prof.name, "taoqupo")
        self.assertEqual(prof.tenant_id, 20)
        self.assertEqual(prof.forbidden_keywords, ["三岔", "462.5"])
        self.assertEqual(len(prof.cases), 1)
        self.assertEqual(prof.cases[0].id, "TQ-PG1")
        self.assertEqual(prof.cases[0].expected_range, {"min": 786.5, "max": 787.0})


if __name__ == "__main__":
    unittest.main()
