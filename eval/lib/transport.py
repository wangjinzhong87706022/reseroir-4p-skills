"""hermes 子进程调用。端口自 test_skills.py::SkillTestRunner.run_test_case。"""
import os
import subprocess


def run_hermes(question, skill_id, env, timeout, skill_dir=None, _runner=subprocess.run):
    cmd = ["hermes", "chat", "-q", question, "--skills", skill_id, "-Q"]
    full_env = {**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}}
    try:
        r = _runner(cmd, capture_output=True, text=True, timeout=timeout,
                    cwd=str(skill_dir) if skill_dir else None, env=full_env)
        return {"output": (r.stdout or "").strip(), "stderr": (r.stderr or "").strip(),
                "exit_code": r.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"output": "", "stderr": "", "exit_code": None, "timed_out": True}
