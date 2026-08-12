# 统一评估集设计（eval set consolidation）

- 日期：2026-08-12
- 状态：已获批，待写实施计划
- 相关：`docs/superpowers/specs/2026-08-05-test-layer-multireservoir-design.md`（多水库测试层设计，本设计是它的泛化与落地）

## 1. 背景

项目现有"测试 / 评估"资产虽多但**碎片化、自动化参差、CI 形同虚设**：

- **~400 道 markdown 题库**（plan-gen 50+45、forecasting 45+41、simulation 98、early-warning 103、diagnosis-verification 5）几乎全是**人工参考**，没有任何 `.py` 消费它们。
- **自动 eval 脚本各自为政**：`test_skills.py` 硬编码 11 题（关键词子串判定）、`plan-generation/.../eval.py` 硬编码 5 题（活库反查）、`simulation/.../eval_runner.py` 硬编码 37 题、`simulation/.../evaluator.py` 按 `Q*.txt` 打分。判定方式、题源、报告格式各不相同。
- **判分引擎半成品**：`tests/reservoir_profile.py::verify_output` 已实现完整三判定（关键词子串 + range 任一落区间 + forbidden 任一命中即整体 FAIL），但配套的 `tests/reservoirs/*.yaml` 数据文件**从未落地**，引擎没被主 runner 使用。
- **early-warning 103 题连评分器都没有**，全靠 `eval-suite.md` 规约 + 人工打分。
- **CI 不跑任何测试**：`auto-merge.yml` 里 `python3 test_skills.py --all` 是注释掉的，连 `unittest discover` 都没有。

**结论**：不是"没有评估集"，而是"有多套解耦、互相不知道对方存在的半成品"。本设计把它们统一成一套机器可消费的评估集。

## 2. 目标与非目标

### 目标
1. 用**单一 schema + 单一 runner** 取代 6 套分散的硬编码集合与人工题库。
2. 把现有 ~400 题去重精选成 **~130 题起步集**，覆盖 6 个 skill 的正常 / 边界 / 异常档。
3. 复用并**激活**已建好的 `verify_output` 三判定引擎，顺带升级 `test_skills.py` 原本只有关键词的弱判定。
4. 把现有无 DB 的 `tests/*.py`（~85 unittest）**接进 CI**，让 PR 至少被回归测试守卫（这是独立于 eval set 的快捷项，本轮一并做）。
5. 为后续 LLM-as-judge、hermes 入 CI 预留入口（搭 adapter + 1 个 demo rubric 验证管线通即可）。

### 非目标（本轮不做）
- 不退役任何旧脚本 / 旧题库（仅标存档），迁移分文件、低优先、以后做。
- 不实现 LLM-judge 的全部 rubric 语义，只搭 adapter + 1 个 demo rubric。
- 不为 diagnosis-verification 大规模造新题（现有 5 + 少量补到 ~10）。
- 不把 eval set 本身接进 CI（hermes 不在 CI），只接 unittest。

## 3. 关键决策（已与用户确认）

| 维度 | 选定 |
|---|---|
| 路线 | 新建统一 runner，旧脚本保留，渐进迁移（方案 A） |
| 覆盖深度 | 均衡层 ~120-180 题（起步 ~130） |
| Schema | 每题声明 `truth_source`（inline / live_db / rubric） |
| 判分机制 | 规则为主（零依赖、CI 友好）+ LLM-judge 可选（手动/本地触发） |

## 4. CI 边界（重要澄清）

**评估集本身进不了 CI。** 每道题要调用 skill（`hermes chat` 子进程）→ 需 hermes 平台 + 真网 DB；CI 里没有 hermes。

- `truth_source: inline` 只让**判分**不依赖 DB，**skill 调用**仍需 hermes ⇒ inline ≠ CI 可跑。
- eval set 运行环境 = 本地 / 现网（有 hermes + DB）。
- 真正的 CI 门禁是**另一件独立的事**：把现有 `tests/*.py` 接进 CI（见 §9）。eval set 预留 `--subset smoke --no-llm` 入口，等 hermes 可入 CI 再启用。

## 5. 目录布局

```
eval/
  README.md            # 加题 / 跑评估指南
  run.py               # 统一 runner：发现题 → 分发 truth_source → 判分 → 报告
  cases/
    forecasting.yaml
    plan-generation.yaml
    simulation.yaml
    early-warning.yaml
    diagnosis-verification.yaml
    supervisor.yaml
  lib/
    judge.py            # 规则判分（复用 tests/reservoir_profile.verify_output）+ LLM-judge 适配
    transport.py        # hermes 子进程调用（抽自 SkillTestRunner，含 env 注入 / 超时 / 退避）
    truth.py            # live_db 反查真值（抽自 plan-gen eval.py 的 get_ground_truth）
    report.py           # md + json 报告（沿用现有 results.json 习惯）
  results/              # 成绩单（保留基线版本）
```

`tests/reservoir_profile.py` **保留为规则判分核心**，`eval/lib/judge.py` 直接 import 复用——这同时补完了"引擎建好、YAML 没落地"的半成品，并把它从水库专用泛化到全 skill。

## 6. 题目 YAML schema

每个 `cases/<skill>.yaml` 是一个 dict：可选顶层 `forbidden_keywords`（该 skill 全库共享的禁词，如 taoqupo 文件可顶层禁 `三岔`，任一题命中即整体 FAIL——防串库）+ 必填 `cases` 列表。这与现有 `tests/reservoir_profile.py` 的 `ReservoirProfile` 约定一致。题级 `forbidden` 与顶层 `forbidden_keywords` **取并集**生效。

```yaml
# 顶层（可选）
forbidden_keywords: []        # 该 skill 共享禁词；题级 forbidden 与之取并集

# 必填：题目列表
cases:
  - id: F1                       # 必填，全库唯一，建议 <skill 首字母><序号>
    skill: forecasting           # 必填，对应 SKILLS 之一的 id
    category: 水位查询            # 必填，分组报告用；精选时每类留 正常 + 边界 + 异常
    description: 查询当前水位     # 必填，人类可读
    question: "查询三岔水库当前水位（只返回数值）"   # 必填，喂给 hermes 的原文
    env:                         # 必填，注入子进程（防"永远 tenant 18" bug）
      SRM_TENANT_ID: 18
      SRM_RESERVOIR_NAME: sancha
    timeout: 60                  # 可选，默认 300
    tags: [smoke]                # 可选，smoke = 冒烟子集；可自定义
    source: test_skills.py::F1   # 必填，溯源旧集合（迁移期对照）
    truth_source: inline         # 必填，inline | live_db | rubric
    # —— 以下字段随 truth_source 而定 ——
    expected_keywords: ["462", "水位", "m"]   # inline / 可选
    expected_range: {min: 459, max: 463}      # inline / 可选
    forbidden: []                            # inline / rubric / 可选；与顶层取并集
```

### 三种 `truth_source` 的题体

- **inline**：`expected_keywords` / `expected_range` / `forbidden`，走规则三判定。
- **live_db**：
  ```yaml
  truth_source: live_db
  truth_query: "SELECT rsvr_rz FROM st_rsvr_r WHERE stcd='...' ORDER BY ... LIMIT 1"
  tolerance: 1.0              # 输出提取数值与真值之差 ≤ tolerance 即过
  expected_keywords: [...]    # 可选，额外关键词兜底
  ```
- **rubric**：
  ```yaml
  truth_source: rubric
  rubric:                     # 评分要点，LLM-judge 逐条 0/1（启用 --llm 时）
    - 必须引用 GB/T 22482
    - 必须给出当前水位数值
  expected_keywords: [...]    # 可选，规则层先过
  forbidden: [...]            # 可选，规则层硬约束
  ```

### Schema 校验（runner 加载时强校验，失败即清晰报错退出）
- 必填：`id`（全库唯一）/ `skill`（在已知 skill 集合内）/ `category` / `description` / `question` / `env` / `source` / `truth_source`。
- `truth_source` 取值合法，且其对应字段齐全（inline 至少有 `expected_keywords` 或 `expected_range`；live_db 必有 `truth_query`；rubric 必有 `rubric`）。
- `env` 至少含 `SRM_TENANT_ID`。

## 7. Runner（`eval/run.py`）

职责：
1. **发现**：`eval/cases/*.yaml` → 扁平题列表；加载时 schema 校验。
2. **过滤**：`--skill` / `--subset smoke|full` / `--tag` / `--id` / `--truth inline|live_db|rubric`。
3. **传输**：每题用 `lib/transport.py` 跑 `hermes chat -q <question> --skills <skill> -Q`（cwd=skill_dir、注入 env、超时 / 异常 / 2s 限流退避）——抽自现有 `SkillTestRunner`。
4. **判分**：按 `truth_source` 分发：
   - inline → `verify_output(case, output, forbidden)`（复用 `tests/reservoir_profile.py`）
   - live_db → `lib/truth.py` 跑 `truth_query` 取真值 → 数值容差比对 + 关键词
   - rubric → 规则层（forbidden / 关键词）+ 可选 LLM-judge（`--llm` 且 `ANTHROPIC_API_KEY` 存在才启用；否则 rubric 部分标 `skip`，不假装通过）
5. **报告**：逐题 result dict（沿用现有字段：id / skill / status / elapsed / output 预览 / 判分明细）+ 按 `skill × category` 两级通过率 → `results/eval-<timestamp>.json` + `.md`。
6. **退出码**：全 PASS = 0；有 FAIL = 1（便于现网脚本，也为将来 hermes 入 CI 铺路）。

### 复用映射（避免重写）
| 新组件 | 复用来源 |
|---|---|
| `lib/judge.py` 规则层 | `tests/reservoir_profile.py::verify_output` |
| `lib/transport.py` | `test_skills.py::SkillTestRunner.run_test_case`（hermes 子进程 + 超时 + 退避） |
| `lib/truth.py` | `plan-generation/autoresearch-plan-skill/eval.py::get_ground_truth` |
| `lib/report.py` | 现有 `results.json` 字段约定 |
| 路径 / skill 注册 | `lib/paths.py`（PROJECT_ROOT / get_skill_dir / RESULTS_DIR） |

## 8. 判分细则

- **规则层（零依赖）**：复用 `verify_output`（关键词子串，大小写不敏感 + range 任一数值落区间 + forbidden 任一命中即整体 FAIL）。相对 `test_skills.py` 现状，新增了 range 与 forbidden 两道防线。
- **live_db 层**：truth_query 结果与输出提取数值做容差比对；truth_query 失败（DB 不可达）→ 该题标 `ERROR` 并记录，**不**回退为通过。
- **LLM-judge（可选）**：`lib/judge.py::llm_judge(output, rubric)` 调 Anthropic API（Claude），按 rubric 逐条 0/1 打分，返回得分与证据引用。仅 `--llm` 且 key 存在时启用；否则 rubric 题规则层照跑，rubric 部分标 `skip`。

## 9. CI 集成（独立于 eval set）

- 在 `.github/workflows/` 新增（或扩展 `auto-merge.yml`）加一步：`python3 -m unittest discover tests`（无 DB，~85 用例，分钟级）。PR 必须全绿才允许 auto-merge。
- eval set 本轮**不接 CI**；预留：等 hermes 可入 CI 时，加 `python3 eval/run.py --subset smoke --no-llm`。

## 10. 400 → ~130 精选规则（去重 cull）

按 skill 从现有题库精选，统一规则：
1. **v1 / v2 合并**：技术向（v1）与业务 / 口语向（v2）各留覆盖该 category 的代表题，语义重复去重。
2. **优先留有 ground truth 的**：forecasting 带 `Expected 数据点` 的题全留并转 `live_db` 或 `inline + range`；plan-gen 现 5 道（已 100%）原样迁入。
3. **每 category 留 1 正常 + 1 边界 + 1 异常**（异常题源自 simulation 的 `_异常/_边界` 分类、early-warning 的 missing-data / high-risk SQL 场景）。
4. **目标存量**：
   | skill | 题量 | 说明 |
   |---|---:|---|
   | forecasting | ~25 | 含 `Expected 数据点` 转 live_db |
   | plan-generation | ~25 | 含现有 5 道原样迁入 |
   | simulation | ~30 | 多方案 / 解读 / 虚拟场景 / 报告 / 敏感性 / 历史 / 综合 |
   | early-warning | ~30 | 覆盖 15 场景矩阵的代表题 |
   | supervisor | ~10 | 由 `demo-output` A/B/C/D 四场景转题 |
   | diagnosis-verification | ~10 | 现有 5 + 少量补 |
   | **合计** | **~130** | 后续可随时扩 |
5. **旧文件零删除**：旧 markdown 题库顶部加 `> 已迁入 eval/cases/<skill>.yaml，本文件为历史存档`；旧 `.py` eval 脚本不动。

## 11. 迁移路线图（方案 A，渐进）

- **本轮（本 spec → 实施计划 → 实施）**：
  - 建 `eval/` 骨架 + `run.py` + `lib/{judge,transport,truth,report}.py`
  - 6 个 `cases/<skill>.yaml` 起步集（~130 题，按 §10 规则精选）
  - CI 接 `python3 -m unittest discover tests`
  - LLM-judge adapter + 1 个 demo rubric（验证管线通）
  - 旧脚本 / 旧题库全保留，仅 markdown 标存档
- **后续（低优先，逐文件）**：
  - `test_skills.py` 改为薄封装调 `eval/run.py`，退役 `FORECASTING_TESTS` 等硬编码
  - plan-gen / simulation 的 `eval.py` 同理
  - 旧 markdown 存档或删
  - hermes 入 CI 后启用 eval set 的 smoke 子集

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 迁移期旧硬编码 + 新 YAML 临时重复 | `source` 字段溯源 + 后续逐文件退役 |
| live_db 真值漂移（活库数据变 → 基线不可比） | 用已有场景种子 SQL 固化 + `results/` 留版本 |
| rubric 规则层弱（LLM 未启用时信号弱） | 明确标 `skip`，不假装通过；CI 不依赖 rubric |
| hermes / DB 不可用导致大面积 ERROR | runner 按 skill 分组、逐题容错；报告里区分 FAIL / ERROR / SKIP |
| 精选误删有价值题 | 旧 markdown 仅标存档不删；`source` 字段可双向追溯 |

## 13. 成功标准（验收）

1. `python3 eval/run.py --list` 列出 ~130 题，无 schema 校验错误。
2. `python3 eval/run.py --subset smoke` 能在现网（hermes + DB）跑通，产出 `results/eval-<ts>.{json,md}`，逐题有 status（PASS/FAIL/TIMEOUT/ERROR/SKIP）与判分明细。
3. 规则判分**复用** `tests/reservoir_profile.py::verify_output`（由单测证明 import 关系与三判定行为）。
4. live_db 题用 `truth_query` 取真值并按 `tolerance` 比对（单测用 mock DB 证明）。
5. LLM-judge adapter 有 demo rubric + 单测（mock LLM，不打真实 API）。
6. CI 工作流跑 `python3 -m unittest discover tests` 在 main 上退出码 0（无 DB 时个别 health 用例走 `skipTest`，skip 不计为失败）。
7. 6 个 `cases/<skill>.yaml` 题量符合 §10 目标；旧 markdown 题库顶部已标存档。
8. 旧脚本（`test_skills.py` / 各 `eval.py` / `eval_runner.py`）未被修改，仍可独立运行。

## 14. 范围界定总结

| 本轮做 | 本轮不做 |
|---|---|
| eval/ 骨架 + run.py + 4 个 lib | 退役旧脚本 / 旧题库 |
| 6 个 YAML 起步集（~130 题） | test_skills.py 改薄封装 |
| 复用 verify_output + 升级判定 | 大规模造 diagnosis-verif 新题 |
| CI 接 unittest | eval set 接 CI |
| LLM-judge adapter + 1 demo rubric | LLM-judge 全量 rubric 语义 |
| 旧 markdown 标存档 | 删任何旧文件 |
