# 评测基建 P0/P1 改造实施计划（eval-infra-p0p1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除评测管线中导致假 FAIL/误裁定的四类基建缺陷：hermes stdout 工具噪声污染判分输入、results JSON 预览误导裁定、关键词硬门否决判官、重型题超时天花板。

**Architecture:** transport 层增加"最终回复提取"（从 `-Q` stdout 的 review-diff 噪声后截取答案），runner 只把提取后的答案送判分并在空输出时判 ERROR；报告层预览改用答案并附 transcript 路径；判分层新增 `--keywords-mode advisory|hard`（默认 advisory，forbidden 恒硬）；题集层给 15 道重型题把 timeout 提到 2000s。

**Tech Stack:** Python 3 stdlib（无新依赖）、unittest（沿用 tests/ 既有风格）、hermes CLI（`hermes chat -q ... --skills ... -Q`，不改动）。

**Spec:** 本文档"评估结论（Spec）"一节，外加 `docs/superpowers/plans/2026-09-01-eval-question-rewrite.md`（前役上下文）。

---

## 评估结论（Spec）

### 缘起

2026-09-01 ~ 09-03 完成了 133 题现象化改写（6 批全部 commit，门禁"无因改题新增 FAIL"全程通过）。收尾评估发现 FAIL 的主因已不是题目质量，而是基建缺陷。**注意：评估过程中发生过一次重要修正**——最初把 10 个 FAIL（DV1/3/5, PG3/4/23/24, EW10/21/29）归因为"transport 只截到 diff 片段、判官看不到答案"；核查 `results/transcripts/*.txt` 全文后发现**最终回复完整存在于 stdout 尾部**，判官拿到的也一直是全文。真实缺陷如下。

### 缺陷清单（按优先级）

| # | 缺陷 | 证据 | 影响 |
|---|------|------|------|
| P0-A | hermes `-Q` stdout 混入 review-diff 工具预览块，判官与关键词检查在"噪声+答案"混合文本上运行 | `transcripts/EW10.txt`：1~376 行是 diff 噪声，377 行起才是答案"**当前状态**…462.651 m"；DV3/PG3 同构 | 判官被噪声干扰（DV1 Stage3 FAIL、Stage4 同题 PASS 的非确定性）；关键词可被脚本代码误命中（假 PASS） |
| P0-B | results JSON 的 `output` 只存 stdout 前 500 字符（`report.py:19`），恰是噪声头部，且无 transcript 指针 | 10 个案例被（人工裁定者）据预览误诊为"transport 截断"；实际答案在 transcript 里 | 裁定必须逐案开 transcript，成本高且易误判（已实际发生） |
| P1-A | `expected_keywords` 为 AND 硬门（`judge.py:50,57,67`），字面措辞可一票否决判官 | EW29 rubric 3/3 pass 但关键词"未找到"未命中（答案说"不存在"）→ FAIL；EW30 同理（"缺失" vs "不存在"）；EW21（"聚合"）；F1 | 规则层与判官层结构性打架，假 FAIL |
| P1-B | 15 道重型题 1000s 超时不够：F14/16/18, PG7/16, SUP1/3/5/7, EW5-9/14 | 各 Stage 3 批次跑的 TIMEOUT 记录 | ~15 题假阴性，占全集 11% |
| P2 | 判官跨跑非确定（DV1 FAIL→PASS）；判官模型未记入结果元数据 | Stage 3 vs Stage 4 DV1 对照 | 边缘题波动，审计困难 |
| P2 | live_db 真值抽取从全文抓一堆数字（`judge.py:19` `_extract_numbers`） | F22 类 | 偶发假 PASS/FAIL（本次不改，P1 完成后视情况） |

### 判空修正（防回归语义）

现有代码已有两条正确语义，本计划不得破坏：考官返回空/非 JSON → ERROR 而非 FAIL（`judge.py:62-66`）；TIMEOUT 不重试（`run.py:120`）。新增同类语义：**transport 未超时但返回空输出 → ERROR 而非 FAIL**（infra 故障，非质量缺陷）。

---

## Global Constraints

- **执行前置条件（2026-09-03 10:47 更新）**：Stage 4 全量跑 `full-095042` 已由用户下令停止（kill 于 [8/133] DV8，完成 7 题：4P/2F/1T，无 results JSON，transcripts 留档）。当前无评测跑在进行，Task 1-5 可直接执行；**执行期间（Task 1-5）禁止启动任何新评测跑**，有界验证跑仅限 Task 6。全量 133 题重跑顺延至本计划验收之后（新 Stage 4'）。
- Python 仅用标准库；不改 hermes CLI 本体；不改 `tests/reservoir_profile.py::verify_output` 的判定语义。
- `forbidden_keywords` 在任何模式下恒为硬门（租户泄漏防线）。
- 结果 JSON 顶层结构（`{"summary":…, "results":[…]}`）不破坏性变更——只加字段，不改既有字段名。
- 测试风格：unittest（沿用 `tests/test_eval_judge.py` 的 `_case(**kw)` helper 模式），运行 `python3 -m pytest tests/test_eval_judge.py -v`。
- 每个任务独立可验证、独立 commit；commit 前 `.baseline 守卫` pre-commit hook 会自动检查，勿暂存 `.baseline` 文件。

---

### Task 0: 调查 hermes `-Q` 噪声来源（可选降噪，不阻塞后续任务）

**Files:**
- 无代码产出；结论写入本文件末尾"Task 0 调查结论"一节。

**Interfaces:**
- Produces: 二选一结论——(A) 可通过 hermes 调用参数/配置消噪（记录确切参数）；(B) 无法消噪，Task 1 的提取器是唯一防线。无论结论如何，Task 1 照常实施（纵深防御）。

- [ ] **Step 1: 探测仓库级 hermes 配置/hook**

```bash
ls -la /home/scada/SmartTwinRes-skills/.hermes/ 2>/dev/null
find /home/scada/SmartTwinRes-skills/.hermes -maxdepth 2 -name "*.yaml" -o -maxdepth 2 -name "*.json" 2>/dev/null | head
grep -rn "review" ~/.hermes/config.yaml /home/scada/SmartTwinRes-skills/.hermes/ 2>/dev/null | grep -iv Binary | head
```

记录：是否存在 hooks/review 相关配置。

- [ ] **Step 2: 最小复现 + 参数对照**

```bash
cd /tmp && hermes chat -q "只回复数字 42" -Q 2>/dev/null | head -5          # 基线：是否出现 ┊ 块
cd /tmp && hermes chat -q "用 python 打印 1+1 的结果" -Q 2>/dev/null | head -20   # 触发工具调用：看 ┊ review diff 是否再现
cd /tmp && hermes chat -q "用 python 打印 1+1 的结果" -Q --ignore-user-config 2>/dev/null | head -20  # 对照
```

记录三种情况下 stdout 是否含 `┊`/`review diff`。

- [ ] **Step 3: 探测会话落盘（若可读最终回复则为最优先集成点）**

```bash
grep -rn "session_id" results/transcripts/EW10.txt | tail -1   # 取如 20260902_171513_dfbe7e
find ~/.hermes -name "*dfbe7e*" 2>/dev/null | head
find ~/.hermes -maxdepth 2 -type d -name "*session*" 2>/dev/null
```

若找到该 session 的落盘文件：检查其中是否存有最终 assistant 消息的**独立**字段（而非整段 stdout 镜像）。记录文件路径与字段名。

- [ ] **Step 4: 把结论写入本文件末尾**

格式：`## Task 0 调查结论` + 三步各自的观测 + 最终选择 (A)/(B)。**结论只能是事实观测，不得臆测 hermes 内部实现。**

---

### Task 1: transport 提取器 `extract_final_answer`

**Files:**
- Modify: `eval/lib/transport.py`
- Test: `tests/test_eval_transport.py`（新建）

**Interfaces:**
- Produces: `extract_final_answer(stdout: str) -> tuple[str, bool]`——返回 `(最终回复, 是否发生了提取)`。无 `┊` 标记或提取结果 <80 字符时原样返回 `(stdout.strip(), False)`。Task 2 的 `run_hermes` 消费此函数。

- [ ] **Step 1: 写失败测试（fixtures 取自真实 transcripts 摘录）**

新建 `tests/test_eval_transport.py`：

```python
import unittest
from eval.lib.transport import extract_final_answer


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
        self.assertFalse(extracted)   # 提取结果 <80 字符 → 原样返回
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_eval_transport.py -v`
Expected: FAIL（`ImportError: cannot import name 'extract_final_answer'`）

- [ ] **Step 3: 实现（追加到 `eval/lib/transport.py`）**

```python
# ┊ 预览块特征：'a/.. → b/..' 文件头、'@@ -' hunk、+/空格/- 行、纯数字行（hermes 预览行号残留）
_DIFF_PREFIXES = ("+", "-", "@", "a/", "b/")


def extract_final_answer(stdout: str):
    """从 hermes -Q stdout 截取最终回复，返回 (answer, extracted)。

    实测结构（results/transcripts/EW10|DV3|PG3.txt，2026-09）：stdout =
    [review-diff 预览块]* + 最终回复。预览块由含 ┊ 的行（可能缩进）开头，
    其后为 diff 内容，直到首个"非 diff 特征且非空"的行即为回复起点。
    已知局限：若回复以 '-'/'+' 开头的行打头会被误当 diff 跳过一行——
    实测回复均以标题/普通句起头，且全文 transcript 始终落盘兜底。
    无 ┊ 标记或提取结果 <80 字符时原样返回（extracted=False，行为同旧版）。
    """
    lines = stdout.splitlines()
    marks = [i for i, ln in enumerate(lines) if "┊" in ln]
    if not marks:
        return stdout.strip(), False
    i = marks[-1] + 1
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.isdigit() or s.startswith(_DIFF_PREFIXES) or "→ b/" in s:
            i += 1
            continue
        break
    answer = "\n".join(lines[i:]).strip()
    if len(answer) < 80:
        return stdout.strip(), False
    return answer, True
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_eval_transport.py -v`
Expected: 5 PASS

- [ ] **Step 5: 用真实 transcripts 回放验证**

```bash
python3 -c "
from eval.lib.transport import extract_final_answer
for cid in ('EW10','DV3','PG3'):
    raw = open(f'results/transcripts/{cid}.txt').read().split('===== STDERR')[0]
    ans, ex = extract_final_answer(raw)
    print(cid, 'extracted=', ex, 'chars=', len(ans))
    print('  head:', ans[:60].replace(chr(10),' / '))
"
```

Expected: 三个案例 `extracted=True`，head 均为答案起始（EW10 含"当前状态"、PG3 含预测表/效果评估附近），而非 diff。

- [ ] **Step 6: Commit**

```bash
git add eval/lib/transport.py tests/test_eval_transport.py
git commit -m "feat(eval): extract final answer from hermes -Q stdout (P0-A)"
```

---

### Task 2: run_hermes 返回 answer + run.py 改送答案给判分 + 空输出判 ERROR

**Files:**
- Modify: `eval/lib/transport.py:6-15`（`run_hermes`）
- Modify: `eval/run.py:131-146`（主循环判分输入与 transcript 写入）
- Test: `tests/test_eval_transport.py`（追加）、`tests/test_eval_runner.py`（追加）

**Interfaces:**
- Consumes: `extract_final_answer(stdout) -> (answer, extracted)`（Task 1）。
- Produces: `run_hermes(...)` 返回 dict 新增键 `"answer": str`、`"answer_extracted": bool`（既有 `"output"/"stderr"/"exit_code"/"timed_out"` 不变）。`run.main` 判分输入改为 `r["answer"]`；`report.build_result` 调用新增 `transcript=` 关键字参数（Task 3 定义）。TimeoutExpired 分支同样带 `"answer": ""`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_eval_transport.py`：

```python
from eval.lib.transport import run_hermes


class TestRunHermesAnswer(unittest.TestCase):
    def _fake_runner(self, stdout):
        def fake(cmd, capture_output, text, timeout, cwd, env):
            class R:
                stdout = stdout
                stderr = ""
                returncode = 0
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
```

（文件顶部需 `import subprocess`。）

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_eval_transport.py -v`
Expected: 新增 3 例 FAIL（`KeyError: 'answer'`）

- [ ] **Step 3: 实现 run_hermes**

替换 `eval/lib/transport.py` 中 `run_hermes` 为：

```python
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
```

- [ ] **Step 4: run.py 主循环改判分输入**

修改 `eval/run.py:131-145` 的 `if r is not None:` 分支为：

```python
        if r is not None:
            elapsed = time.time() - t0
            if r.get("timed_out"):
                v = {"verdict": "TIMEOUT", "detail": {"reason": f"超时 {eff_timeout}s"}}
            elif not (r.get("answer") or "").strip():
                # 未超时但无最终回复 = infra 故障（hermes 崩溃/空 stdout），判 ERROR 防假 FAIL
                v = {"verdict": "ERROR", "detail": {"reason": "transport 未超时但返回空输出"}}
            else:
                v = _dispatch(c, r["answer"], query_fn, llm_on)
            out_preview = r.get("answer", "")
            transcript_path = transcripts_dir / f"{c.id}.txt"
            meta = (f"[answer_extracted={r.get('answer_extracted')}] "
                    f"[answer_chars={len(r.get('answer') or '')}]\n")
            report.write_transcript(transcript_path, meta + r.get("output", ""), r.get("stderr", ""))
```

（`else` 分支与后续 `status = ...` 行保持不变；`results.append(...)` 行在 Task 3 改为带 `transcript=` 参数——本任务先只改判分输入与 transcript meta。）

- [ ] **Step 5: 跑既有 runner/judge 测试确认无回归**

Run: `python3 -m pytest tests/test_eval_runner.py tests/test_eval_judge.py tests/test_eval_transport.py -v`
Expected: 全 PASS（runner 测试用注入 transport_fn，若其 fake 返回 dict 缺 `answer` 键则补 `"answer": <同 output>`——这是唯一允许的既有测试改动）

- [ ] **Step 6: Commit**

```bash
git add eval/lib/transport.py eval/run.py tests/test_eval_transport.py tests/test_eval_runner.py
git commit -m "feat(eval): judge on extracted answer; empty output -> ERROR (P0-A/B)"
```

---

### Task 3: 报告层——预览用答案 + transcript 指针 + 运行元数据

**Files:**
- Modify: `eval/lib/report.py:17-23`（`build_result`）
- Modify: `eval/run.py`（`results.append` 与 summary meta）
- Test: `tests/test_eval_report.py`（追加）

**Interfaces:**
- Consumes: `run.main` 侧 `transcript_path`（Task 2）。
- Produces: `build_result(case, status, elapsed, output, verdict_detail, transcript=None)`；结果记录新增键 `"transcript": str|None`（`output` 键语义变为"最终回复预览（≤500 字符）"）。summary 新增 `"meta": {"judge_model": str, "keywords_mode": str}`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_eval_report.py`：

```python
class TestTranscriptPointer(unittest.TestCase):
    def test_result_carries_transcript_path(self):
        from eval.lib.report import build_result
        c = _case()   # 复用本文件既有 _case helper；若无则照 test_eval_judge.py 的造
        r = build_result(c, "FAIL", 1.0, "预览", {"reason": "x"},
                         transcript="results/transcripts/X1.txt")
        self.assertEqual(r["transcript"], "results/transcripts/X1.txt")
        self.assertLessEqual(len(r["output"]), 504)   # 500 + "..."

    def test_transcript_optional(self):
        from eval.lib.report import build_result
        c = _case()
        r = build_result(c, "PASS", 1.0, "ok", {})
        self.assertIsNone(r["transcript"])
```

（若 `tests/test_eval_report.py` 无 `_case` helper，从 `tests/test_eval_judge.py` 复制同款。）

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_eval_report.py -v`
Expected: 新增 2 例 FAIL（`build_result() got an unexpected keyword argument 'transcript'`）

- [ ] **Step 3: 实现 build_result**

替换 `eval/lib/report.py` 的 `build_result`：

```python
def build_result(case, status, elapsed, output, verdict_detail, transcript=None):
    out = output or ""
    out = (out[:500] + "...") if len(out) > 500 else out
    return {"id": case.id, "skill": case.skill, "category": case.category,
            "description": case.description, "question": case.question,
            "status": status, "elapsed_seconds": round(elapsed, 2),
            "output": out, "transcript": transcript, "verdict": verdict_detail}
```

- [ ] **Step 4: run.py 接线**

`results.append(...)` 行改为：

```python
        results.append(report.build_result(c, status, elapsed, out_preview, v["detail"],
                                           transcript=str(transcript_path)
                                           if r is not None else None))
```

`summary = report.summarize(results)` 之后加：

```python
    summary["meta"] = {"judge_model": os.environ.get("EVAL_JUDGE_MODEL", "default"),
                       "keywords_mode": getattr(args, "keywords_mode", "advisory")}
```

（`transcript_path` 变量：在 Task 2 已于 `if r is not None:` 分支定义；`else` 分支需补 `transcript_path = transcripts_dir / f"{c.id}.txt"` 以保 NameError 安全。）

- [ ] **Step 5: 跑全部 eval 测试**

Run: `python3 -m pytest tests/test_eval_report.py tests/test_eval_runner.py tests/test_eval_judge.py tests/test_eval_transport.py -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add eval/lib/report.py eval/run.py tests/test_eval_report.py
git commit -m "feat(eval): preview final answer, transcript pointer, run metadata (P0-B)"
```

---

### Task 4: `--keywords-mode advisory|hard`（默认 advisory，forbidden 恒硬）

**Files:**
- Modify: `eval/lib/judge.py:29-69`（三个 judge 函数签名与 passed 合成）
- Modify: `eval/run.py:29-51`（argparse）、`eval/run.py:70-81`（`_dispatch`）
- Test: `tests/test_eval_judge.py`（追加 + 修正依赖旧默认的用例）

**Interfaces:**
- Produces: `judge_inline(case, output, keywords_mode="advisory")`、`judge_live_db(case, output, query_fn, keywords_mode="advisory")`、`judge_rubric(case, output, llm_fn=None, keywords_mode="advisory")`。语义：advisory 下 expected_keywords 只记入 detail（键 `keywords_advisory`/`all_found_advisory`），不参与 passed；hard 下行为与旧版完全一致且 detail 记 `"keywords_mode": "hard"`。forbidden 两模式恒硬。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_eval_judge.py`：

```python
class TestKeywordsAdvisory(unittest.TestCase):
    def test_rubric_keyword_miss_still_passes_when_advisory(self):
        # EW29 实例：rubric 全过、答案说"不存在"而非"未找到" → advisory 下应 PASS
        c = _case(truth_source="rubric", rubric=["正确处理不存在测站"],
                  expected_keywords=["未找到", "测站"])
        llm = lambda o, r: {"passed": True, "items": [{"criterion": r[0], "pass": True}]}
        r = judge.judge_rubric(c, "该测站不存在，已查询 6 张表均无记录，" * 3, llm)
        self.assertEqual(r["verdict"], "PASS")
        self.assertFalse(r["detail"]["all_found_advisory"])
        self.assertEqual(r["detail"]["keywords_mode"], "advisory")

    def test_rubric_keyword_miss_fails_when_hard(self):
        c = _case(truth_source="rubric", rubric=["正确处理不存在测站"],
                  expected_keywords=["未找到", "测站"])
        llm = lambda o, r: {"passed": True, "items": [{"criterion": r[0], "pass": True}]}
        r = judge.judge_rubric(c, "该测站不存在。" * 10, llm, keywords_mode="hard")
        self.assertEqual(r["verdict"], "FAIL")

    def test_forbidden_hard_in_advisory(self):
        c = _case(truth_source="rubric", rubric=["正常作答"], expected_keywords=["水位"],
                  forbidden=["桃曲坡"])
        llm = lambda o, r: {"passed": True, "items": [{"criterion": r[0], "pass": True}]}
        r = judge.judge_rubric(c, "桃曲坡水位正常。" * 10, llm, keywords_mode="advisory")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("桃曲坡", r["detail"]["forbidden_hits"])

    def test_live_db_advisory_ignores_keyword(self):
        c = _case(truth_source="live_db", truth_query="SELECT rz FROM st_rsvr_r LIMIT 1",
                  tolerance=1.0, expected_keywords=["水位"])
        r = judge.judge_live_db(c, "462.4 m", lambda sql: [{"rz": 462.5}])
        self.assertEqual(r["verdict"], "PASS")
        self.assertFalse(r["detail"]["all_found_advisory"])

    def test_inline_advisory_ignores_keyword(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        r = judge.judge_inline(c, "当前 462.5 m")   # 无"水位"字样
        self.assertEqual(r["verdict"], "PASS")
        self.assertFalse(r["detail"]["all_found_advisory"])

    def test_inline_hard_still_fails_on_keyword(self):
        c = _case(expected_keywords=["水位"], expected_range={"min": 459, "max": 463})
        r = judge.judge_inline(c, "当前 462.5 m", keywords_mode="hard")
        self.assertEqual(r["verdict"], "FAIL")
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_eval_judge.py -v`
Expected: 新增 6 例 FAIL（TypeError/unexpected keyword 或断言失败）

- [ ] **Step 3: 实现三个 judge**

`judge_inline` 改为：

```python
def judge_inline(case, output: str, keywords_mode: str = "advisory") -> dict:
    """规则三判定：range + forbidden 硬门；keywords 按 keywords_mode。
    advisory 下 verify_output 收空 keywords，真实关键词命中另记 keywords_advisory。"""
    kws = case.expected_keywords if keywords_mode == "hard" else []
    rp = RPCase(id=case.id, skill=case.skill, description=case.description,
                question=case.question, expected_keywords=kws,
                expected_range=case.expected_range, timeout=case.timeout)
    v = verify_output(rp, output, case.forbidden)
    kw = _keyword_check(output, case.expected_keywords)
    detail = {**v, "keywords_mode": keywords_mode}
    if keywords_mode == "advisory":
        detail["keywords_advisory"] = kw["keyword_checks"]
        detail["all_found_advisory"] = kw["all_found"]
    return {"verdict": "PASS" if v["all_passed"] else "FAIL", "detail": detail}
```

`judge_live_db` 的尾部两行改为：

```python
    cmp = compare_with_tolerance(_extract_numbers(output), truth, case.tolerance)
    kw = _keyword_check(output, case.expected_keywords)
    kw_hard = kw["all_found"] if keywords_mode == "hard" else True
    passed = cmp["passed"] and kw_hard
    detail = {"truth": truth, **cmp, "keywords_mode": keywords_mode,
              "keywords_advisory": kw["keyword_checks"], "all_found_advisory": kw["all_found"]}
    if keywords_mode == "hard":
        detail.update(kw)
    return {"verdict": "PASS" if passed else "FAIL", "detail": detail}
```

（函数签名加 `keywords_mode: str = "advisory"`。）

`judge_rubric` 改为：

```python
def judge_rubric(case, output: str, llm_fn=None, keywords_mode: str = "advisory") -> dict:
    forb = [w for w in case.forbidden if str(w).lower() in (output or "").lower()]
    kw = _keyword_check(output, case.expected_keywords)
    kw_hard = kw["all_found"] if keywords_mode == "hard" else True
    rule_pass = kw_hard and not forb
    detail = {"keywords_mode": keywords_mode,
              "keywords_advisory": kw["keyword_checks"], "all_found_advisory": kw["all_found"],
              "forbidden_hits": forb}
    if keywords_mode == "hard":
        detail.update(kw)
    if llm_fn is None:
        return {"verdict": "PASS" if rule_pass else "FAIL",
                "detail": {**detail, "rubric": "skip (no llm)"}}
    score = llm_fn(output, case.rubric)
    if score.get("error"):
        return {"verdict": "ERROR", "detail": {**detail, "rubric_score": score,
                                               "reason": f"考官故障: {score['error']}"}}
    passed = rule_pass and score["passed"]
    return {"verdict": "PASS" if passed else "FAIL", "detail": {**detail, "rubric_score": score}}
```

- [ ] **Step 4: run.py 加旗标并透传**

`parse_args` 加：

```python
    p.add_argument("--keywords-mode", choices=["hard", "advisory"], default="advisory",
                   help="expected_keywords 语义：advisory=只报告不判分（默认）；hard=一票否决（旧版）。"
                        "forbidden_keywords 恒为硬门")
```

`_dispatch` 与调用点改为：

```python
def _dispatch(case, out, query_fn, llm_on, keywords_mode="advisory"):
    if case.truth_source == "inline":
        return judge.judge_inline(case, out, keywords_mode)
    if case.truth_source == "live_db":
        if query_fn is None:
            return {"verdict": "ERROR", "detail": {"reason": "无 DB 连接"}}
        return judge.judge_live_db(case, out, query_fn, keywords_mode)
    llm_fn = None
    if llm_on and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EVAL_JUDGE_BASE_URL")):
        llm_fn = lambda o, r: judge.llm_judge(o, r)
    return judge.judge_rubric(case, out, llm_fn, keywords_mode)
```

主循环调用点：`v = _dispatch(c, r["answer"], query_fn, llm_on, args.keywords_mode)`。

- [ ] **Step 5: 全量 eval 测试 + 修正依赖旧默认的既有用例**

Run: `python3 -m pytest tests/test_eval_judge.py tests/test_eval_runner.py tests/test_eval_report.py tests/test_eval_transport.py -v`

若有既有用例因默认 advisory 而 FAIL（例如关键词缺失类断言），给该用例显式传 `keywords_mode="hard"`——逐个修，不得删除断言。记录改了哪几个。

- [ ] **Step 6: Commit**

```bash
git add eval/lib/judge.py eval/run.py tests/test_eval_judge.py
git commit -m "feat(eval): --keywords-mode advisory default, forbidden stays hard (P1-A)"
```

---

### Task 5: 15 道重型题 timeout 提至 2000s

**Files:**
- Modify: `eval/cases/forecasting.yaml`（F14, F16, F18）
- Modify: `eval/cases/plan-generation.yaml`（PG7, PG16）
- Modify: `eval/cases/supervisor.yaml`（SUP1, SUP3, SUP5, SUP7）
- Modify: `eval/cases/early-warning.yaml`（EW5, EW6, EW7, EW8, EW9, EW14）

**Interfaces:**
- Produces: 上述题 `timeout: 2000`。与 `--timeout-set` 的既有交互不变（`max(case, set)`，只抬不压）。

- [ ] **Step 1: 逐文件把 15 题的 `timeout:` 行改为 `timeout: 2000`**

用 Edit 逐处修改（每题只动 `timeout:` 一行，勿碰其他字段）。定位：

```bash
grep -n "id: F14\|id: F16\|id: F18" eval/cases/forecasting.yaml
grep -n "id: PG7\|id: PG16" eval/cases/plan-generation.yaml
grep -n "id: SUP1\|id: SUP3\|id: SUP5\|id: SUP7" eval/cases/supervisor.yaml
grep -n "id: EW5\|id: EW6\|id: EW7\|id: EW8\|id: EW9\|id: EW14" eval/cases/early-warning.yaml
```

- [ ] **Step 2: 校验题集完整性与生效值**

```bash
python3 eval/run.py --list | wc -l        # 必须 133
python3 -c "
from eval.lib.schema import load_all
cases = {c.id: c for c in load_all('eval/cases')}
ids = ['F14','F16','F18','PG7','PG16','SUP1','SUP3','SUP5','SUP7','EW5','EW6','EW7','EW8','EW9','EW14']
assert all(cids in cases and cases[cids].timeout == 2000 for cids in ids), [ (i, cases.get(i).timeout if i in cases else 'MISSING') for i in ids ]
print('15 题均已 2000s')
"
```

Expected: `133` 与 `15 题均已 2000s`

- [ ] **Step 3: Commit**

```bash
git add eval/cases/forecasting.yaml eval/cases/plan-generation.yaml eval/cases/supervisor.yaml eval/cases/early-warning.yaml
git commit -m "chore(eval): raise timeout to 2000s for 15 heavy cases (P1-B)"
```

---

### Task 6: 修复后验证跑（有界：仅历史受害题）

**Files:**
- 无代码；产出验证结论，追加到本文件"Task 0 调查结论"之后。

- [ ] **Step 1: 确认前置（无评测跑在进行、Task 1-5 已 commit）**

```bash
ps -p 189624 --no-headers 2>/dev/null; echo "---"   # 须无输出（full-095042 已停）
ps aux | grep -c "[e]val/run.py"                    # 须为 0（无其他评测在跑）
git log --oneline -5                                 # 须见 Task 1-5 的 5 个 commit
```

- [ ] **Step 2: 有界重跑历史受害题（detached）**

```bash
bash logs/run-eval-detached.sh --id EW10,EW21,EW29,EW30,DV1,DV3,DV5,PG3,PG4,PG23,PG24 \
  --timeout-set 1000 --llm --mode report
```

- [ ] **Step 3: 裁定验收标准**

加载新 `results/eval-*.json`，按题对照：

| 题 | 修复前 | 验收预期 |
|----|--------|----------|
| EW21/29/30 | 关键词假 FAIL | advisory 下转 **PASS**（答案实质正确） |
| EW10 | rubric item1"置信度"严格 FAIL | 干净答案上重判；PASS 或维持 FAIL 但 detail 里 `answer_chars` 为真实答案长度（可归因） |
| DV1/DV3/DV5, PG3/4/23/24 | 噪声干扰判官，跨跑波动 | 判分输入已是干净答案；PASS 或 FAIL 均可归因（看 rubric items 对干净文本的判定） |

任一题若 `answer_extracted=false` 且 output 仍以 `┊` 开头 → 提取器对该形态失效，回 Task 1 补 fixture 再修。

- [ ] **Step 4: 结论写回本文件 + 更新断点 memory**

记录通过率变化、`answer_extracted` 比例、剩余波动题清单。

---

## Self-Review 结论

- 覆盖检查：评估表中 P0-A→Task 1/2，P0-B→Task 3，P1-A→Task 4，P1-B→Task 5，验证→Task 6，P2 两项（判官非确定/live_db 抽取）明确不在本计划范围（已在评估表中标注"本次不改"）。
- 类型一致性：`extract_final_answer` 返回 tuple 在 Task 1 定义、Task 2 消费；`build_result(..., transcript=)` 在 Task 3 定义、Task 2 Step 4 预留调用点并在 Task 3 Step 4 落地；`keywords_mode` 默认值三处一致（`"advisory"`）。
- 语义红线：`passed` 合成中 forbidden 恒硬（Task 4 Step 3 三个实现均保留）；ERROR-not-FAIL 语义沿用并扩展（Task 2 Step 4 空输出分支）。

---

## Task 0 调查结论

调查时间 2026-09-03。环境：Hermes Agent v0.20.3 (2026.8.16.2)，`/root/.local/bin/hermes`，安装目录 `/opt/git/hermes-agent`。全部为实际执行的观测记录。

### Step 1 观测：仓库级 hermes 配置 / hook

- `ls -la /home/scada/SmartTwinRes-skills/.hermes/` → 只有一个 `skills/` 子目录（另加 `.` `..`）。
- `find .hermes -maxdepth 2 -name "*.yaml" -o -maxdepth 2 -name "*.json"` → **0 命中**（仓库级 `.hermes/` 无任何配置文件）。
- `grep -rn "review" ~/.hermes/config.yaml` → 命中的全是无关项：`user_message_preview:`(L287)、`tool_preview_length: 0`(L292)、TTS 模型名、3 个 skill 名（`flood-season-review` L456 / `github-code-review` L460 / `requesting-code-review` L502）。仓库 `.hermes/` 中命中的只是技能脚本里的变量名 `rain_preview`。
- 补充 `grep -n "hook" ~/.hermes/config.yaml` → `hooks:`(L596) 下 5 条命令全部指向 `/home/scada/powerelf-skills/_shared/hooks/block_raw_pymysql.py` / `block_repo_writes.py`（拦截类），无任何渲染/preview 相关 hook。
- 小结：**仓库级与用户级配置中都不存在 review-diff/preview 开关。**

### Step 2 观测：最小复现 + 参数对照（均在 /tmp 执行）

| 命令 | stdout 实际内容 | 含 `┊`/`review diff`？ |
|---|---|---|
| `hermes chat -q "只回复数字 42" -Q` | 1 行：`42` | 否（无工具调用即干净） |
| `hermes chat -q "用 python 打印 1+1 的结果" -Q` | `  ┊ review diff` → `a/calc.py → b/calc.py` → `@@ -0,0 +1 @@` → `+print(1 + 1)` → 答案 `1+1 = 2 啦~ (◕‿◕)★` → 说明行 → `[exited with code 0]` | **是**，位于最终答案之前 |
| 同上 + `--ignore-user-config` | `┌─ Reasoning ─…┐` 框 + 两段重复的中间文本 → 同样的 `  ┊ review diff` / `a/sum_test.py → b/sum_test.py` / `@@ -0,0 +1 @@` / `+print(1 + 1)` → 答案 → `[exited with code 0]` | **是**，且额外泄漏 reasoning 框 |

- `--ignore-user-config` 还换了模型：该 session `20260903_110433_d9af72` 在 state.db 中 model=`claude-fable-5`，而带用户配置的两条（`20260903_110129_eb2b68`、`20260903_110245_3db71f`）model=`Qwen3.8-27B-Q4_K_M.gguf`。即它不是"仅关配置"的降噪开关。
- 用户配置里 `display.tool_preview_length: 0` 与 `tool_progress_command: false` **已经**是 0/false，review diff 块仍输出 → 该块不受 `display.tool_preview_length` 管辖（该键只作用于 spinner 工具预览，见 `/opt/git/hermes-agent/agent/display.py:1553`）。
- 附加观测：`-Q` 输出末尾还有 `[exited with code 0]` 尾巴行，同属非答案文本。
- `-Q` 的 help 文案是 "suppress banner, spinner, and tool previews. Only output the final response and session info."，与实际输出不符（edit diff 未被抑制）；`hermes chat --help` 全部选项中没有任何 diff/review/preview 相关 flag。
- 源码观测（直接读到，非臆测）：噪声出自 `/opt/git/hermes-agent/agent/display.py:950` `print_fn("  ┊ review diff")`；唯一 CLI 调用点是 `/opt/git/hermes-agent/cli.py:13775 _on_tool_complete()`，它在 L13793-13798 **无条件**调用 `render_edit_diff_with_delta(...)`，外层没有 quiet/config 判断；触发工具为 `write_file` / `patch` / `skill_manage`（`display.py:933`）。

### Step 3 观测：会话落盘

- `grep -rn "session_id" results/transcripts/EW10.txt | tail -1` → `EW10.txt:405: session_id: 20260902_171513_dfbe7e`
- `find ~/.hermes -name "*dfbe7e*"` → **0 命中**；`~/.hermes/sessions/` 实际只有 1957 个 `request_dump_*.json`（另有 1 个 2026-08-19 的 `session_20260819_095727_912f42.json`），不存在按 session id 落盘的会话文件。
- 会话真正落在 `/root/.hermes/state.db`（sqlite）：`sessions` 表 1 行命中该 id，`messages` 表 26 行。最后一条 assistant 消息是**独立字段** `messages.content`（row id=78101，length=458，之前各条 assistant 行 content 长度均为 0），内容即 EW10 的最终答案；逐项检查 `┊` / `review diff` / `@@ -` / `a/calc.py` / `[exited with code` → **全部 False（干净）**。
- schema 关键列：`messages(session_id, role, content, tool_name, timestamp, display_kind, …)`，可直接 `role='assistant'` + 该 session 的最大 rowid 取最终回复。

### 最终选择

**(B) 无法消噪，Task 1 提取器是唯一防线。**

依据：`-Q`、`-Q --ignore-user-config`、以及已带 `display.tool_preview_length: 0` 的用户配置三种形态下 review diff 块均照常输出；`hermes chat` 无相关 flag，仓库/用户配置无相关键，源码调用点无任何 quiet/config 条件。

补充（不改变结论）：Step 3 观测到 `/root/.hermes/state.db` 的 `messages.content`（role='assistant' 最后一条）是**不含任何噪声标记的独立最终回复字段**，可作为 Task 1 之外更优先的备选集成点；Task 1 提取器按计划照常实施（纵深防御）。
