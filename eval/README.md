# 统一评估集（eval/）

> 取代旧硬编码集合（`test_skills.py` / 各 skill 的 `eval.py` / 各 `tests/test-questions*.md`）。
> 本集是水库四预系统 6 个 skill 的统一判分入口：发现用例 → 注入 env → 跑 hermes 子进程 →
> 按真值判分（inline / live_db / rubric） → 落 JSON+Markdown 报告。

## 题集结构（cull ~130）

| skill | 文件 | 用例数 | 主要来源 |
|-------|------|--------|----------|
| forecasting | `cases/forecasting.yaml` | 25 | `forecasting/tests/test-questions*.md` + `test_skills.py::F1-F6` |
| plan-generation | `cases/plan-generation.yaml` | 25 | `plan-generation/tests/test-questions*.md` + `autoresearch-plan-skill/eval.py::TEST_INPUTS` |
| simulation | `cases/simulation.yaml` | 30 | `simulation/tests/test-questions.md`（98 题）+ `autoresearch-simulation/questions.tsv`（按 `evaluator.py::CATEGORY_MAP` 22 类） |
| early-warning | `cases/early-warning.yaml` | 33 | `early-warning/autoresearch-v3/test-inputs.md`（103 题，按 `tests/test-data-scenarios.md` 15 场景） |
| supervisor | `cases/supervisor.yaml` | 10 | `supervisor/demo-output/A|B|C|D-*.json`（四场景）+ `SKILL.md` 路由/状态 |
| diagnosis-verification | `cases/diagnosis-verification.yaml` | 10 | `diagnosis-verification/tests/test-cases.md`（5 道）+ 补 5 道 |
| **合计** |  | **133** |  |

每题 `env` 至少含 `SRM_TENANT_ID`（三岔 sancha=18 / 桃曲坡 taoqupo=20），必要时含 `SRM_RESERVOIR_NAME`。
租户隔离由 transport 层保证：case env 覆盖 `os.environ`（case 优先），每个用例显式声明自己的租户。

## 跑评估（需 hermes 平台 + 真网 DB）

```bash
python3 eval/run.py --list                       # 仅列出用例（不跑），退出码 0
python3 eval/run.py --skill forecasting          # 单 skill
python3 eval/run.py --subset smoke               # 仅 smoke 子集
python3 eval/run.py --tag live_db                # 按 tag 过滤
python3 eval/run.py --id F1                       # 单用例
python3 eval/run.py --truth live_db              # 按真值类型过滤
python3 eval/run.py --llm                         # 启用 LLM-judge（需 ANTHROPIC_API_KEY）
python3 eval/run.py                               # 全跑
```

报告输出到 `results/eval-<ts>.{json,md}`。退出码：全 PASS=0，否则=1。
过滤条件 `--subset` / `--tag` / `--skill` / `--id` / `--truth` 同时给出时为 **AND** 组合过滤。

LLM-judge 考官二选一（`--llm` 时生效）：

| 方式 | 环境变量 | 说明 |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | 模型默认 `claude-sonnet-5`，可用 `EVAL_JUDGE_MODEL` 覆盖 |
| OpenAI 兼容端点 | `EVAL_JUDGE_BASE_URL`（必）+ `EVAL_JUDGE_MODEL` + `EVAL_JUDGE_API_KEY`（可选） | 指向本地网关/vLLM 等 `/v1` 地址；未设 key 则不带鉴权头 |

例：考官用 hermes 同款自建 Qwen——
```bash
export EVAL_JUDGE_BASE_URL=https://llm.iagp.top:9080/v1 EVAL_JUDGE_MODEL=Qwen3.8-27B-Q4_K_M.gguf
python3 eval/run.py --llm ...
```

## 加题

在 `cases/<skill>.yaml` 的 `cases:` 下追加一条。**必填字段**：

- `id`：全库唯一，按 skill 前缀（F/PG/SIM/EW/SUP/DV）+ 数字
- `skill` / `category` / `description` / `question` / `source`
- `env`：至少含 `SRM_TENANT_ID`（三岔=18 / 桃曲坡=20）
- `truth_source`：三选一，按类型补字段（见 `eval/lib/schema.py::validate`）

```yaml
- id: F26
  skill: forecasting
  category: 水位查询
  description: 当前水位 inline 校验
  question: "三岔水库当前水位是多少？"
  env: {SRM_TENANT_ID: 18, SRM_RESERVOIR_NAME: sancha}
  timeout: 60
  source: 你的溯源路径
  truth_source: inline            # 或 live_db / rubric
  expected_keywords: ["水位"]       # inline 必填之一
  expected_range: {min: 450, max: 465}  # inline 必填之一（与 keywords 至少其一）
```

## truth_source 三类

| 类型 | 适用 | 必填字段 | 判分方式 |
|------|------|----------|----------|
| **inline** | 可数值/关键词校验（默认，零依赖） | `expected_keywords` 和/或 `expected_range`（可选 `forbidden`） | 规则层（复用 `tests/reservoir_profile.py::verify_output`） |
| **live_db** | 有 CONFIRMED-working SQL | `truth_query` + `tolerance`（水位建议 1.0，历史计数建议 50.0） | 真值数值在容差内（`eval/lib/truth.py`） |
| **rubric** | 报告/方案/叙述类（无单一答案） | `rubric`（2-4 条要点，抄自 SKILL.md 验收清单） | 默认规则层（keywords/forbidden）+ skip；`--llm` 才按 rubric 打分 |

**live_db 真值 SQL 的唯一可信来源**：`plan-generation/autoresearch-plan-skill/eval.py::get_ground_truth`
（已验证：`st_rsvr_r.rz`、`att_res_flse_lim.flse_lim_stag`、`model_config`、`model_result_files`、
`srm_flood_history_base`）。**不要**照抄 schema markdown 文档的列名（已证实不可靠）。

**truth_query 租户纪律（2026-09-11 起）**：除基础设施全局表外，truth_query 必须带 `AND tenant_id = ?`
（与题目 env 的 `SRM_TENANT_ID` 一致）。`att_res_flse_lim` / `model_result_files` / `srm_flood_history_base`
等都是多租户表——无过滤的 `LIMIT 1` 会随机取到其他水库的行，无过滤的 `COUNT(*)` 会把其他租户
数据算进真值。新增 live_db 题时自查一条：真值 SQL 在 tenant 20 下执行结果是否不同？

## 超时（timeout）语义

三层口径（`eval/run.py:112` 附近）：

1. **默认**：用 yaml 单题 `timeout` 字段。
2. **`--timeout-set N`**：`eff = max(yaml值, N)`——**只抬不压**。传了它，yaml 里 60/120/240 的
   单题值全部被抬到 N 起（yaml 内单题 timeout 实际失效，只有原生长超时题如 DV2 的 2000 保留意义）。
   全量跑统一用 `--timeout-set 2000`。
3. **`--timeout-cap N`**：`eff = min(eff, N)` 封顶，与 `--timeout-set` 互斥（后者优先）。

判 TIMEOUT 的题判 ERROR 不判 FAIL；单题超时历史值：DV8 ≈981s、DV2 ≈1500s，
长题不要低于 2000s 跑。
水位真值统一用：
```sql
SELECT rz FROM st_rsvr_r WHERE rz IS NOT NULL AND deleted = 0 ORDER BY tm DESC LIMIT 1
```

## 判分实现

- `eval/lib/judge.py::judge_inline` — 关键词包含 + 区间 + 禁词，零依赖
- `eval/lib/truth.py::compare_with_tolerance` — live_db 数值容差比较
- `eval/lib/judge.py::judge_rubric` — 规则层先行；`--llm` 时叠加 `llm_judge`
- `eval/lib/transport.py` — hermes 子进程 + env 注入 + 超时（case env 覆盖 ambient）
- `eval/run.py` — CLI 发现/过滤/分发/报告，单题异常转 ERROR 不中断整跑

## 场景注入（data_prep，2026-09-12 起）

异常题此前一直跑在"正常基线"上——`forecasting/data/scenarios/` 的 7 月场景 SQL 从未
接入评测。`eval/data_prep.py` + `eval/data/scenarios.yaml` 把"场景→题目"接进 runner：
每题 **transport 前 setup 注入、判分后 teardown 恢复**，动作全量写
`<report_dir>/fixture_manifest.json`（含 pre-image），崩溃后可
`python3 eval/data_prep.py --restore <manifest>` 回写。

- handler 三种：`file`（场景 SQL，剥注释按分号拆语句、单连接保会话变量）、
  `insert_rows`（幂等 DELETE-before-INSERT）、`null_rz_latest` / `suppress`
  （软改基线，pre-image 记主键+列值按 id 回写）。
- `exclusive: true` 的场景（改基线可见性）只在 ≤5 题的小批量生效（EXCLUSIVE_MAX_BATCH），
  全量跑自动跳过——场景保真与大批次隔离二选一，当前选隔离。
- teardown 型：`restore`（按 pre-image 回写）/ `delete_first`（按 marker 删注入行）。
- fixtures 状态写进每题结果 `verdict.fixtures`，报告可见"该题是否真的跑了场景"。

**写库纪律（踩过的坑）**：
- `lib.db.execute_query` 不 commit（读导向），写入必须走 `data_prep._execute_write`
  （显式提交），否则静默回滚——2026-09-12 实测 UPDATE 后 NULL 行数为 0。
- SQL 文本含 `%`（如 `LIKE 'EVALFIX\_%'`、`DATE_FORMAT('%Y..')`）时，无参执行必须传
  `None` 不传 `()`，否则 pymysql 做 % 格式化直接炸。
- 场景标记/主键要与在写方隔离：cron 的 `--forecast` 批用 `COMMENTS='MOCK'`、
  f_rnfl_h 复合主键 (ID,YMDH,UNITNAME,TYPE) 且软删不释放 PK——所以 stale_forecast
  场景用 `COMMENTS='MOCK-STALE'` + `ID=20001`，与存量（1/2/10001-10047）无交集。
- `ew_info_message.creator` 是 INT 列不是字符串。
- 已接线场景：null_water_level→PG17、single_red_alarm→EW32、stale_forecast 对→F5/F10
  （F25 题面是假设式，前提不匹配，不注入）。其余场景 SQL（drought/extreme_storm/
  over_flood_limit/source_disagreement/null_actual）按需在 scenarios.yaml 登记。


## 守卫测试

`tests/test_eval_cases.py` 校验：所有用例加载且 id 唯一；每 skill 用例数在 band 内
（forecasting/plan-generation 20-30，simulation/early-warning 25-35，supervisor/diagnosis-verification 8-15）；
总数 100-180。CI 通过 `python3 -m unittest discover tests` 执行。

## 与旧资产的关系（方案 A 渐进迁移）

本集取代旧硬编码集合（`test_skills.py` / 各 `eval.py`）与人工 markdown 题库（已标存档）。
旧脚本暂不删，后续逐文件退役。每题 `source` 字段保留溯源路径（如
`forecasting/tests/test-questions.md::Q3`、`test_skills.py::FORECASTING_TESTS::F1`、
`supervisor/demo-output/A-20260805-192723.json`），便于回归比对。
