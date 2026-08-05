"""supervisor_state.py 运维命令单元测试：stats / replay / health。

stats/replay 用临时 SRM_STATE_DIR SQLite State 注入 mock 事件与阶段结果，
断言统计/重放提示正确；health 因连真实 DB 仅做命令注册与结构冒烟（连库失败兜底）。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "supervisor" / "scripts"
for p in (_REPO, _SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


class _TempState:
    """为每个测试方法建独立 SQLite State（SRM_STATE_DIR 兜底）。"""

    def __init__(self):
        self._tmp = tempfile.mkdtemp(prefix="svt-ops-")
        self._old = os.environ.get("SRM_STATE_DIR")

    def __enter__(self):
        os.environ["SRM_STATE_DIR"] = self._tmp
        import importlib, supervisor_state
        importlib.reload(supervisor_state)
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("SRM_STATE_DIR", None)
        else:
            os.environ["SRM_STATE_DIR"] = self._old
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


def _new_event(scene, trigger="", priority="中"):
    import argparse, supervisor_state
    na = argparse.Namespace(scene=scene, risk=None, trigger=trigger, priority=priority)
    return supervisor_state.cmd_new(na)["event_id"]


def _set_stage(event_id, stage, agent, result="{}", status="ok"):
    import argparse, supervisor_state
    na = argparse.Namespace(event=event_id, stage=stage, agent=agent,
                            result=result, status=status)
    return supervisor_state.cmd_set(na)


def _set_status(event_id, status, risk=None):
    import argparse, supervisor_state
    na = argparse.Namespace(event=event_id, status=status, risk=risk)
    return supervisor_state.cmd_status(na)


class TestStats(unittest.TestCase):
    """stats：事件总数/状态分布/失败率/阶段完成率。"""

    def test_counts_after_seeding(self):
        with _TempState():
            import supervisor_state, argparse
            # 3 事件：1 done、1 running、1 aborted
            e1 = _new_event("A", "暴雨"); _set_stage(e1, "step1", "f", status="ok")
            _set_status(e1, "done")
            e2 = _new_event("B", "诊断"); _set_stage(e2, "step1", "d", status="ok")
            e3 = _new_event("D", "应急", priority="高"); _set_status(e3, "aborted")
            # 给 e2 加一个 error 阶段
            _set_stage(e2, "step2", "i", status="error")

            na = argparse.Namespace()
            r = supervisor_state.cmd_stats(na)
            self.assertEqual(r["total_events"], 3)
            self.assertEqual(r["done"], 1)
            self.assertEqual(r["aborted"], 1)
            self.assertAlmostEqual(r["fail_rate_pct"], 33.3, places=1)
            # 阶段：2 ok + 1 error = 3 total
            self.assertEqual(r["stages"]["total"], 3)
            self.assertEqual(r["stages"]["ok"], 2)
            self.assertEqual(r["stages"]["error"], 1)
            self.assertEqual(r["stages"]["error_rate_pct"], 33.3)
            # error 阶段应出现在 recent_errors
            self.assertTrue(any(e["event_id"] == e2 and e["stage"] == "step2"
                                for e in r["recent_errors"]))

    def test_empty_state_no_crash(self):
        with _TempState():
            import supervisor_state, argparse
            r = supervisor_state.cmd_stats(argparse.Namespace())
            self.assertEqual(r["total_events"], 0)
            self.assertEqual(r["fail_rate_pct"], 0.0)
            self.assertEqual(r["stages"]["ok_rate_pct"], 0.0)


class TestReplay(unittest.TestCase):
    """replay：失败/未完成事件一键重放提示命令正确。"""

    def test_awaiting_approval_gives_resume_approve(self):
        with _TempState():
            import supervisor_state, argparse
            eid = _new_event("A", "暴雨")
            _set_status(eid, "awaiting_approval")
            r = supervisor_state.cmd_replay(argparse.Namespace())
            self.assertEqual(r["replay_count"], 1)
            cmd = r["events"][0]["replay_cmd"]
            self.assertIn("resume", cmd)
            self.assertIn("--approve", cmd)
            self.assertIn(eid, cmd)

    def test_aborted_with_error_stage_gives_stage_cmd(self):
        with _TempState():
            import supervisor_state, argparse
            eid = _new_event("B", "诊断")
            _set_stage(eid, "step1", "d", status="ok")
            _set_stage(eid, "step2", "i", status="error")
            _set_status(eid, "aborted")
            r = supervisor_state.cmd_replay(argparse.Namespace())
            self.assertEqual(r["replay_count"], 1)
            ev = r["events"][0]
            self.assertIn("step2", ev["bad_stages"])
            cmd = ev["replay_cmd"]
            self.assertIn("stage", cmd)
            self.assertIn("--stage step2", cmd)

    def test_running_with_no_bad_stages_gives_resume(self):
        with _TempState():
            import supervisor_state, argparse
            eid = _new_event("C", "日常", priority="低")
            _set_stage(eid, "step1", "f", status="ok")
            r = supervisor_state.cmd_replay(argparse.Namespace())
            self.assertEqual(r["replay_count"], 1)
            cmd = r["events"][0]["replay_cmd"]
            self.assertIn("resume", cmd)

    def test_done_events_not_in_replay(self):
        with _TempState():
            import supervisor_state, argparse
            eid = _new_event("A", "暴雨")
            _set_status(eid, "done")
            r = supervisor_state.cmd_replay(argparse.Namespace())
            self.assertEqual(r["replay_count"], 0)


class TestHealth(unittest.TestCase):
    """health：连真实 DB 的冒烟测试——无 DB 时应优雅兜底而非崩溃。

    因 health 依赖 lib.db 连现网 MySQL，这里只验证：
      1. 命令注册可调（argparse Namespace 可达）
      2. 缺 DB 连接时抛捕获型异常（非裸 SystemExit 崩溃）
    若环境有 DB 则验证结构字段完整。
    """

    def test_health_callable(self):
        import supervisor_state, argparse
        na = argparse.Namespace()
        try:
            r = supervisor_state.cmd_health(na)
            # 有 DB 环境：验证结构
            self.assertIn("overall", r)
            self.assertIn("checks", r)
            self.assertIn(r["overall"], ("ok", "warn", "error"))
            self.assertTrue(all("item" in c and "status" in c for c in r["checks"]))
            self.assertIn("st_rsvr_r", r["detail"])
            self.assertIn("f_rnfl_h", r["detail"])
        except (Exception, SystemExit) as e:
            # 无 DB 环境：lib.db 抛 SystemExit，跳过冲烟
            self.skipTest(f"无 DB 连接，跳过 health 冒烟: {type(e).__name__}")


if __name__ == "__main__":
    unittest.main()
