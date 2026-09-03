import subprocess
import unittest
from eval.lib import transport
from eval.lib.transport import extract_final_answer
from eval.lib.transport import run_hermes


class FakeCompleted:
    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


class TestTransport(unittest.TestCase):
    def test_cmd_and_env_injection(self):
        seen = {}
        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            seen["env"] = kw["env"]
            seen["cwd"] = kw.get("cwd")
            return FakeCompleted(stdout="水位 462 m")
        r = transport.run_hermes("Q?", "forecasting", {"SRM_TENANT_ID": 20}, 60,
                                 skill_dir="/tmp/skill", _runner=fake_run)
        self.assertEqual(seen["cmd"], ["hermes", "chat", "-q", "Q?", "--skills", "forecasting", "-Q"])
        self.assertEqual(seen["env"]["SRM_TENANT_ID"], "20")
        self.assertIn("PATH", seen["env"])  # 合并了 os.environ
        self.assertEqual(seen["cwd"], "/tmp/skill")
        self.assertEqual(r["output"], "水位 462 m")
        self.assertFalse(r["timed_out"])

    def test_timeout(self):
        import subprocess
        def boom(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)
        r = transport.run_hermes("Q", "s", {}, 1, _runner=boom)
        self.assertTrue(r["timed_out"])
        self.assertIsNone(r["exit_code"])


class TestExtractFinalAnswer(unittest.TestCase):
    def test_plain_output_untouched(self):
        out = "当前水位 462.5 m，无告警。"
        ans, extracted = extract_final_answer(out)
        self.assertFalse(extracted)
        self.assertEqual(ans, out)

    def test_skips_review_diff_block(self):
        # 结构复刻 results/transcripts/EW10.txt：┊ 头 + diff 头 + hunk + 空行 + 答案
        out = (
            "┊ review diff\n"
            "3\n"
            "15\n"
            "a/scripts/_tmp_6h_predict.py → b/scripts/_tmp_6h_predict.py\n"
            "@@ -0,0 +1,118 @@\n"
            "+#!/usr/bin/env python3\n"
            "+from db import execute_query\n"
            " \n"
            " context line\n"
            "\n"
            "**当前状态**\n"
            "- 测站 3 最新水位：462.650 m（09-02 11:00 采集）\n"
            "  462.650 + 0.0002 × 6 ≈ **462.651 m**（17:00）\n"
            "\n"
            "结论：水位基本持平，预计未来 6 小时维持在 462.65 m 附近，涨幅不超过 0.01 m。"
        )
        ans, extracted = extract_final_answer(out)
        self.assertTrue(extracted)
        self.assertTrue(ans.startswith("**当前状态**"))
        self.assertIn("462.651", ans)
        self.assertNotIn("@@", ans)

    def test_answer_with_arrow_table_lines_kept(self):
        # PG3 实测：答案含 "16:00 → 460.421m" 表格行（→ 但非 diff 头），不得被当噪声截掉
        out = (
            "┊ review diff\n"
            "a/scripts/x.py → b/scripts/x.py\n"
            "@@ -1 +1 @@\n"
            "+print(1)\n"
            "\n"
            "16:00 → 460.421m\n"
            "18:00 → 460.408m\n"
            "\n"
            "效果评估：水位控制有效，安全余量充足，调度目标达成，结论为通过。"
        )
        ans, extracted = extract_final_answer(out)
        self.assertTrue(extracted)
        self.assertTrue(ans.startswith("16:00"))

    def test_too_short_extraction_falls_back(self):
        out = "┊ review diff\na/x.py → b/x.py\n@@ -1 +1 @@\n+print(1)\n\n好的。"
        ans, extracted = extract_final_answer(out)
        self.assertFalse(extracted)   # 提取结果过短（_MIN_ANSWER_CHARS=20）→ 原样返回
        self.assertEqual(ans, out)

    def test_indented_marker_found(self):
        # EW10 实测中 ┊ 块存在缩进形态（"  ┊ review diff"），须同样识别
        out = (
            "┊ review diff\n"
            "a/one.py → b/one.py\n"
            "@@ -1 +1 @@\n"
            "+one\n"
            "\n"
            "  ┊ review diff\n"
            "a/two.py → b/two.py\n"
            "@@ -1 +1 @@\n"
            "+two\n"
            "\n"
            "**最终结论**\n"
            "全部校验通过，水位 462.65 m，处于汛限以下，无需干预，建议继续保持观测。"
        )
        ans, extracted = extract_final_answer(out)
        self.assertTrue(extracted)
        self.assertTrue(ans.startswith("**最终结论**"))
        self.assertNotIn("one.py", ans)

    def test_trailing_exited_line_stripped(self):
        out = ("┊ review diff\na/x.py → b/x.py\n@@ -1 +1 @@\n+print(1)\n\n"
               "**当前状态**\n水位 462.65 m，未来 6 小时维持平稳，涨幅不超过 0.01 m，无需干预。\n"
               "[exited with code 0]")
        ans, extracted = extract_final_answer(out)
        self.assertTrue(extracted)
        self.assertNotIn("[exited with code", ans)
        self.assertTrue(ans.rstrip().endswith("无需干预。"))

    def test_trailer_negative_exit_code_stripped(self):
        out = ("┊ review diff\na/x.py → b/x.py\n@@ -1 +1 @@\n+print(1)\n\n"
               "**当前状态**\n水位 462.65 m，未来 6 小时维持平稳，涨幅不超过 0.01 m，无需干预。\n"
               "[exited with code -9]")
        ans, extracted = extract_final_answer(out)
        self.assertTrue(extracted)
        self.assertNotIn("[exited with code", ans)


class TestRunHermesAnswer(unittest.TestCase):
    def _fake_runner(self, stdout):
        def fake(cmd, capture_output, text, timeout, cwd, env):
            class R:
                stderr = ""
                returncode = 0
            R.stdout = stdout   # 类体里写 "stdout = stdout" 会 NameError（RHS 解析到类体局部名）
            return R()
        return fake

    def test_answer_key_present_when_clean(self):
        r = run_hermes("q", "s", {}, 60, _runner=self._fake_runner("当前水位 462.5 m，运行正常无告警。" * 2))
        self.assertEqual(r["answer"], r["output"])
        self.assertFalse(r["answer_extracted"])

    def test_answer_key_present_when_noisy(self):
        noisy = ("┊ review diff\na/x.py → b/x.py\n@@ -1 +1 @@\n+print(1)\n\n"
                 "**当前状态**\n" + "水位 462.65 m，未来 6 小时维持平稳，涨幅不超过 0.01 m，无需干预。\n" * 2)
        r = run_hermes("q", "s", {}, 60, _runner=self._fake_runner(noisy))
        self.assertTrue(r["answer_extracted"])
        self.assertTrue(r["answer"].startswith("**当前状态**"))
        self.assertEqual(r["output"], noisy.strip())   # output 恒为全文

    def test_timeout_has_empty_answer(self):
        def fake(cmd, capture_output, text, timeout, cwd, env):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        r = run_hermes("q", "s", {}, 60, _runner=fake)
        self.assertTrue(r["timed_out"])
        self.assertEqual(r["answer"], "")


if __name__ == "__main__":
    unittest.main()
