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
LLM-judge 模型默认 `claude-sonnet-5`，可用 `EVAL_JUDGE_MODEL` 覆盖（如换更便宜的模型）。

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

## 守卫测试

`tests/test_eval_cases.py` 校验：所有用例加载且 id 唯一；每 skill 用例数在 band 内
（forecasting/plan-generation 20-30，simulation/early-warning 25-35，supervisor/diagnosis-verification 8-15）；
总数 100-180。CI 通过 `python3 -m unittest discover tests` 执行。

## 与旧资产的关系（方案 A 渐进迁移）

本集取代旧硬编码集合（`test_skills.py` / 各 `eval.py`）与人工 markdown 题库（已标存档）。
旧脚本暂不删，后续逐文件退役。每题 `source` 字段保留溯源路径（如
`forecasting/tests/test-questions.md::Q3`、`test_skills.py::FORECASTING_TESTS::F1`、
`supervisor/demo-output/A-20260805-192723.json`），便于回归比对。
