import unittest
from eval.lib.truth import extract_numbers, compare_with_tolerance


class TestTruth(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_numbers("水位 462.5m，降 12.3"), [462.5, 12.3])

    def test_compare_pass(self):
        r = compare_with_tolerance([462.4, 500.0], 462.5, 1.0)
        self.assertTrue(r["passed"])  # 462.4 在容差内

    def test_compare_fail(self):
        r = compare_with_tolerance([500.0], 462.5, 1.0)
        self.assertFalse(r["passed"])

    def test_make_query_fn_uses_injected_port(self):
        # make_db_query_fn 返回的闭包应执行给定 SQL；这里只验证它可调用且延迟导入
        from eval.lib import truth
        called = {}
        def fake_connect(*a, **k):
            class Cur:
                def execute(self, sql): called["sql"] = sql
                def fetchall(self): return [{"v": 7}]
                def __enter__(self): return self
                def __exit__(self, *a): pass
            class Conn:
                def cursor(self): return Cur()
            return Conn()
        orig = truth._connect
        truth._connect = fake_connect
        try:
            q = truth.make_db_query_fn({})
            rows = q("SELECT 1")
        finally:
            truth._connect = orig
        self.assertEqual(rows, [{"v": 7}])
        self.assertEqual(called["sql"], "SELECT 1")

    def test_connect_delegates_to_lib_db(self):
        # C1：_connect 应复用 lib.db 连接（同 env 解析/超时/fail-loud），
        # 而非自带 root/空密码弱默认。CI 无 pymysql 时跳过。
        try:
            import pymysql  # noqa: F401
        except ImportError:
            self.skipTest("pymysql 未安装（CI 环境）")
        from unittest.mock import patch
        from eval.lib import truth
        sentinel = object()
        with patch('lib.db.get_connection', return_value=sentinel) as m:
            self.assertIs(truth._connect({}), sentinel)
        m.assert_called_once_with()

if __name__ == "__main__":
    unittest.main()
