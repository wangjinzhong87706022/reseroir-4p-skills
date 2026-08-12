import unittest
from eval.lib import transport


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

if __name__ == "__main__":
    unittest.main()
