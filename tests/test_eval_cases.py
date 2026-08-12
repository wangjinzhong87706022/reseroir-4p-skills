import unittest
from pathlib import Path
from eval.lib.schema import load_all

CASES_DIR = Path(__file__).resolve().parents[1] / "eval" / "cases"
TARGETS = {  # skill -> (min, max)
    "forecasting": (20, 30), "plan-generation": (20, 30), "simulation": (25, 35),
    "early-warning": (25, 35), "supervisor": (8, 15), "diagnosis-verification": (8, 15),
}


class TestCases(unittest.TestCase):
    def test_all_load_and_unique(self):
        cases = load_all(CASES_DIR)
        self.assertGreater(len(cases), 0)

    def test_per_skill_counts_in_target(self):
        cases = load_all(CASES_DIR)
        from collections import Counter
        cnt = Counter(c.skill for c in cases)
        for skill, (lo, hi) in TARGETS.items():
            self.assertIn(skill, cnt, f"缺 skill: {skill}")
            self.assertGreaterEqual(cnt[skill], lo, f"{skill} 题太少 {cnt[skill]}")
            self.assertLessEqual(cnt[skill], hi, f"{skill} 题太多 {cnt[skill]}")

    def test_total_in_balanced_band(self):
        cases = load_all(CASES_DIR)
        self.assertGreaterEqual(len(cases), 100)
        self.assertLessEqual(len(cases), 180)

if __name__ == "__main__":
    unittest.main()
