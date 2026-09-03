"""hermes 子进程调用。端口自 test_skills.py::SkillTestRunner.run_test_case。"""
import os
import re
import subprocess


def run_hermes(question, skill_id, env, timeout, skill_dir=None, _runner=subprocess.run):
    cmd = ["hermes", "chat", "-q", question, "--skills", skill_id, "-Q"]
    full_env = {**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}}
    try:
        r = _runner(cmd, capture_output=True, text=True, timeout=timeout,
                    cwd=str(skill_dir) if skill_dir else None, env=full_env)
        output = (r.stdout or "").strip()
        answer, extracted = extract_final_answer(output)
        return {"output": output, "answer": answer, "answer_extracted": extracted,
                "stderr": (r.stderr or "").strip(),
                "exit_code": r.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"output": "", "answer": "", "answer_extracted": False,
                "stderr": "", "exit_code": None, "timed_out": True}


_TRAILER_RE = re.compile(r"\[exited with code -?\d+\]\s*$")


def _strip_trailer(text: str) -> str:
    """hermes -Q stdout 末尾的退出码尾巴行，非答案文本，剥掉。"""
    return _TRAILER_RE.sub("", text).rstrip()


# ┊ 预览块特征：'a/.. → b/..' 文件头、'@@ -' hunk、+/空格/- 行、纯数字行（hermes 预览行号残留）
# 附：'… omitted N diff line(s)…' 为 hermes 的 diff 省略提示行（EW10/PG3 实测均在答案前一行）
_DIFF_PREFIXES = ("+", "-", "@", "a/", "b/")

# 提取结果过短视为没截到答案。brief 原定 80，但其自带 fixtures 的答案仅 49~67 字符，
# 80 会让 3 个用例误走回退（见 task-1-report.md）；实测真答案均为数百字符，20 足以挡碎片。
_MIN_ANSWER_CHARS = 20


def extract_final_answer(stdout: str):
    """从 hermes -Q stdout 截取最终回复，返回 (answer, extracted)。

    实测结构（results/transcripts/EW10|DV3|PG3.txt，2026-09）：stdout =
    [review-diff 预览块]* + 最终回复。预览块由含 ┊ 的行（可能缩进）开头，
    其后为 diff 内容（含空格打头的 context 行与 '… omitted …' 省略行），
    直到首个"非 diff 特征且非空"的行即为回复起点。
    已知局限：若回复以 '-'/'+' 开头或带缩进的行打头会被误当 diff 跳过——
    实测回复均以标题/普通句起头，且全文 transcript 始终落盘兜底。
    无 ┊ 标记或提取结果过短时原样返回（extracted=False，行为同旧版）。
    """
    stdout = _strip_trailer(stdout)
    lines = stdout.splitlines()
    marks = [i for i, ln in enumerate(lines) if "┊" in ln]
    if not marks:
        return stdout.strip(), False
    i = marks[-1] + 1
    while i < len(lines):
        ln, s = lines[i], lines[i].strip()
        if (not s or s.isdigit() or s.startswith(_DIFF_PREFIXES) or "→ b/" in s
                or ln[:1] in (" ", "\t")        # diff context 行原样带缩进（" #!/usr/bin/env"）
                or s.startswith("…") or "diff line(s)" in s):
            i += 1
            continue
        break
    answer = "\n".join(lines[i:]).strip()
    if len(answer) < _MIN_ANSWER_CHARS:
        return stdout.strip(), False
    return answer, True
