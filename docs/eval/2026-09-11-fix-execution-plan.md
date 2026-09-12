# 2026-09-11 评测修复执行方案（FAIL 逐题修复 + 评测数据准备层）

> 配套分析：`docs/eval/2026-09-11-eval-analysis-and-plan.md`（13 FAIL 归因）
> 本文档是可直接执行的施工图：每处改动给出**文件、精确的 old→new、验收标准**。

---

## Part A：13 个 FAIL 逐题修复

### A1 真值 SQL（1 题，1 行改动）

**F22** `eval/cases/forecasting.yaml:262`

```yaml
# old
truth_query: "SELECT COUNT(*) AS cnt FROM srm_flood_history_base WHERE deleted = 0"
# new（答题环境 tenant 18，真值必须同租户）
truth_query: "SELECT COUNT(*) AS cnt FROM srm_flood_history_base WHERE deleted = 0 AND tenant_id = 18"
```

验收：preflight 下执行 truth_query = 8；单题重跑 PASS（agent 答"8 条"，extracted 含 8，|8-8|=0 < 2）。

### A2 rubric 条件化/同义锚点（8 题，只改 yaml）

| 题 | 条目 | old（现状） | new |
|---|---|---|---|
| **PG2** | c1 | `给出当前水位与汛限的距离（余量约 3.3m）` | `给出当前水位距当前生效汛限的余量（主汛期 462.5 计约 3.3m；后汛期 462.0 计约 2.8m；任一口径均判满足，数值 ±0.2m 容差）` |
| **PG17** | c1 | `检测当前水位数据为空/缺失状态（定位水位表，确认无有效 rz 值即可，不绑死特定列名）` | `水位数据状态核查：定位水位表核查 rz 有效性；若实查有值、与题设"数据为空"不符，明确指出该矛盾并按缺失流程给出处理策略，同样判满足` |
| **EW32** | c1 | `考虑告警级别权重，评估中等风险` | `路径一：结合告警级别权重给出风险等级（中等/较高等）与依据；路径二：识别告警数据质量问题（TEST_ 测试数据、批次自相矛盾、历史告警堆积）并给出复核/治理建议。任一路径均判满足` |
| **SIM8** | c2 | `注意 id=9 为 status=3 失败记录` | `标注 id=9 的失败/低质量背景：明确指出 status=3，或指出其结果异常（削峰率 0%/下泄 0/拦蓄时长 0）并说明不宜作为效果基准，均判满足` |
| **DV8** | c1 | `Phase 5 根因分类明确（数据/规则/模型/基础设施之一）` | `Phase 5 根因定性到枚举：主要根因归入 数据/规则/模型/基础设施 之一；复合根因须逐一映射（如"路由配置→规则类""水位伪造→数据类""flood_limit bug→模型/基础设施类"），judge 按映射判满足` |
| **F24** | c2 | `紧急状态下给出下泄/控泄方向建议，体现下游安全泄量约束（引用安全泄量概念即可，不强制 95.1 数值）` | `（同 old，追加）——提及 下泄/泄洪能力/控泄/安全泄量 任一组合并给出方向即判满足；"拉满泄洪能力"与"受安全泄量约束控泄"等价，不强制数值 95.1` |
| **F25** | c1 | `说明降级触发条件（预报降雨无未来时段行/全源缺失时触发降级，语义命中即可，不要求实查特定表）` | `（同 old，追加）——"单源缺失→置信度降级/缺一源""全源缺失→仅供参考/转实况+人工复核"均属触发条件语义命中；逐源降级列表等同覆盖` |
| **DV7** | c1+c2 | c1 `…确认无 skill 间数据混用、tenant 隔离正确`；c2 `比对预演输出与调度方案关键字段（最高水位/削峰率）…` | c1 `…比对关键字段并确认一致性；本租户无联合事件时，选择最近全局联合事件并显式声明其租户归属，同样判满足`；c2 `比对字段集为（最高水位/削峰率/出流量/下泄量/汛限水位）任两项` |

### A3 SKILL 行为修复（3 族，改被测系统）

**① SIM4 + SIM8（同族）** `simulation/SKILL.md` — 在"报告异常/边界处理（分流二）"**之前**新增入口检查节：

```markdown
### 预演/解读/对比前置检查（刚性，v1.9.5）

凡任务涉及历史洪水 ID（预演、多方案对比、结果解读、报告），**第一步**必须查该洪水状态：

    SELECT id, status FROM srm_flood_history_base WHERE id = ? AND tenant_id = ? AND deleted = 0

- `status = 3`（失败）→ 后续所有输出必须包含一句：
  "该洪水标记为失败（status=3），预演结果可能低质量"
- 记录不存在 → 如实说明，禁止用其他洪水的数据拼凑
- 分流逻辑之后仍按"报告异常/边界处理"执行（本检查是前置，不替代分流）
```

验收：单题重跑 SIM4，rubric c1 过 + kw `失败`/`status` 命中；SIM8 c2 直接过。

**② DV1** `diagnosis-verification/SKILL.md` — 在 Phase 8 校验清单（:284-289）后追加最终答复格式硬约束：

```markdown
**最终答复格式（判分依赖，不可省略）**：

- 必须包含一行时效性/完整性评分结论：`时效性/完整性评分：差 / 中 / 好`（Phase 2 结论复述）
- 必须包含「短期止血」与「长期根治」两个小节标题（Phase 7 内容拆分写入答复正文；
  写入知识库 YAML 的 fix.immediate/fix.long_term 字段**不能替代**答复正文）
```

验收：单题重跑 DV1，answer 中含评分行与两小节，c2/c4 过。

**③ SUP5** `supervisor/SKILL.md:98` 通用仲裁规则表追加一行：

```markdown
| 水位 > 当前生效汛限 | 升级处置：报告必须标注"已超汛限，HITL 待确认"，不得作为纯日常报告交卷（场景C 同样适用） |
```

验收：单题重跑 SUP5，c3 过（升级路径被触发并标注 HITL）。

### A4 题目改写（1 题）

**PG24** `eval/cases/plan-generation.yaml`

```yaml
# question old: 如果当前水位恰好等于汛限水位 462.500m，是安全还是危险？
question: "假设当前水位恰好等于汛限水位 462.500m（不考虑实况数据），是安全还是危险？应采取什么措施？"
# rubric c1 加同义锚点
- 判定为临界状态（临界/安全边界/零余量/贴限 任一表述均判满足）
# c2 微调
- 建议启动防洪预案（或等效的预泄/控泄等防御动作）
```

### A5 判官校准（横切，1 行）

`eval/lib/judge.py:_build_prompt` 注意段追加一句：

```python
"判定标准：语义等效即 PASS——只要答复满足条目要点的含义，措辞/结构/详略差异不扣分；"
"仅在要点内容实质缺失时判 fail。\n"
```

---

## Part B：横切资产卫生（防复发）

| # | 动作 | 落点 |
|---|---|---|
| B1 | truth_query 租户纪律全量扫描：`grep -L tenant_id` 全部 truth_query，逐条人工确认 | `eval/cases/*.yaml` |
| B2 | ~~md 逐题列表复选框与 JSON status 对齐~~ **已核实为误报**（2026-09-11 复查：md 13 个 `[ ]` 与 JSON 13 个 non-PASS 完全一致，`report.py` 的 mark 逻辑正确）——无需修复，仅更正前文档 X6 表述 | 无改动 |
| B3 | README 写明 timeout 语义：`--timeout-set` 与 yaml 单题值取 max、传参时 yaml 值被吞 | `eval/README.md` |
| B4 | stage5 ledger 清账：补"2026-09-11 处置"列（F22/PG2 本次补修、SIM 双分支已落、timeout 已落） | `docs/eval/2026-09-04-non-pass-ledger.md` |

---

## Part C：评测数据准备层（回答"评测前是否先跑模拟生成工具"）

**结论：要，且分两层——基线新鲜度 + 错误场景注入。** 现状是"半成品"：

| 资产 | 状态 |
|---|---|
| `forecasting/data/generate_sancha_data.py`（--roll/--clean/--forecast） | 断点 bug 已修**未提交**；roll 波形有方波缺陷（见 C1） |
| `forecasting/data/generate_taoqupo_data.py`（--roll 按 MAX(tm)） | 正常 |
| `forecasting/data/scenarios/*.sql`（7 个场景：drought/extreme_storm/null_actual/over_flood_limit/source_disagreement/stale_forecast + 汛限备份） | **7 月建成，未接入评测流程**，9 月两轮全量都没跑 |
| `eval/preflight.py`（陈旧度 + hermes ping） | 只查"数据新不新"，不查"题目前提在不在" |

### C1 基线新鲜度：修 roll 波形

方波根因：`gen_observation_series` 的相位是**相对本次调用 start** 的短正弦（`phase = i/total_h*π`），每次 roll 只走正弦起点两个点（BASE 459.18 → PEAK 462.65），下次 roll 再从头走 → 时序上呈两值交替。修复：相位改**绝对时钟**，并加噪声：

```python
# old: phase = i / max(total_h, 1) * math.pi
#      wl  = BASE_WL + (PEAK_WL - BASE_WL) * (1 - math.cos(phase)) / 2
# new: 相位基于绝对时刻（72h 主周期 + 24h 日周期 + 确定性伪噪声）
phase72 = (tm - _EPOCH).total_seconds() / 3600 / 72 * 2 * math.pi
phase24 = (tm - _EPOCH).total_seconds() / 3600 / 24 * 2 * math.pi
wl = (BASE_WL
      + (PEAK_WL - BASE_WL) * 0.5 * (1 + math.sin(phase72))
      + 0.05 * math.sin(phase24)
      + 0.03 * math.sin(i * 2.7))          # 确定性伪噪声（可复现，非随机）
```

要点：确定性（同 tm 同值，roll 幂等可复算）、不再有相邻两小时同值跳变、保留"逼近并轻微超汛限"的演示场景。`inq/otq/w` 由 wl 推导，自然连续。改完 `--roll` 续写补齐历史，再跑 live_db 抽样验证。

### C2 错误场景注入：把 scenarios/ 接进评测（data_prep.py）

新建 `eval/data_prep.py`，职责单一：**按本轮题单，物化各题需要的数据前提，产出 manifest**。

```yaml
# eval/data/scenarios.yaml（新增，场景→题映射 + 前提断言）
fixtures:
  stale_forecast:                     # 已有 scenarios/stale_forecast.sql
    sql: forecasting/data/scenarios/stale_forecast.sql
    cases: [F5, F10, F25]
  null_actual:                        # 已有（实测缺失）
    sql: forecasting/data/scenarios/null_actual.sql
    cases: []
  null_water_level:                   # 新增（PG17/PG6 前提）
    sql: forecasting/data/scenarios/null_water_level.sql   # 待写
    cases: [PG17]
    teardown: restore                 # 跑完恢复 pre-image
  single_red_alarm:                   # 新增（EW32 前提）
    sql: forecasting/data/scenarios/single_red_alarm.sql   # 待写
    cases: [EW32]
```

需要新写的 2 个场景 SQL（沿用库内既有约定：幂等 DELETE-before-INSERT、`creator='MOCK'` 标记、NOW 相对时间）：

- **null_water_level.sql**（PG17）：备份主站最新 3 行的 rz → UPDATE 置 NULL；`teardown: restore` 由 manifest 记录 pre-image，data_prep `--restore` 恢复。注意与 PG2/F12 等 live 题互斥 → 只允许在 PG17 单题前后注入（见执行顺序）。
- **single_red_alarm.sql**（EW32）：注入 1 条 `tm=NOW` 的红色告警（stcd 主站，告警名不带 TEST_）；配合数据治理清洗既有 `TEST_%` 历史告警。

**runner 接线（改 run.py ~15 行）**：`EvalCase` 增加可选字段 `fixtures: list`（schema.py 加 `fixtures: list = field(default_factory=list)`）；main 循环里 dispatch 前 `data_prep.setup(case)`、之后 `data_prep.teardown(case)`；所有动作写 `manifest`。全量跑时互斥场景（改基线表的）自动跳过并在报告中标注 `fixture_skipped`，单题/小批量重跑时才启用。

### C3 preflight v2：真值快照断言（守门员，最重要）

`eval/preflight.py` 新增 `check_truth_premises()`：对每个 `truth_source: live_db` 的题**预执行 truth_query**，与 yaml 新增字段 `truth_expectation` 比对，不符则 FATAL 拒绝开跑：

```yaml
# yaml 示例
F22: { truth_expectation: { value: 8, tol: 2 } }          # 防跨租户/数据再生成
PG2: { truth_expectation: { flood_limit_in: [462.0, 462.5] } }
PG17: { truth_expectation: { rz_null: true } }            # 仅当启用 null_water_level fixture
SIM4: { truth_expectation: { result_rows_gt: 0, or_absent: true } }  # 双分支均可
```

这直接堵死本轮的失效模式："前提腐烂静默进全量 → 跑 9 小时后才发现 13 FAIL"。预检 30 秒，省 9 小时。

### C4 run.sh 集成顺序

```bash
# 1. 基线 roll 到 NOW（两租户）
python3 forecasting/data/generate_sancha_data.py --roll
python3 forecasting/data/generate_taoqupo_data.py --roll
# 2. preflight v2（陈旧度 + hermes + 真值前提断言）
python3 eval/preflight.py || exit 3
# 3. 全量
python3 eval/run.py --timeout-set 2000 --llm --mode report --report-dir "$DIR"
```

---

## Part D：执行顺序与验收门

```
Step 1  Part A1/A2（yaml + truth）+ A5（judge 校准）+ Part B
        → 单题重跑 13 题 → 预期翻正 8~9 题（F22/PG2/PG17/EW32/SIM8/DV8/F24/F25/DV7）
Step 2  Part A3（3 处 SKILL 修复）+ A4（PG24）
        → 单题重跑 SIM4/SIM8/DV1/SUP5/PG24 → 预期再 +3~5 题
Step 3  C1 波形修复 + 提交工作区未提交改动（roll 断点修复）
        → --roll 续写 → live_db 抽样（F7/F12/PG6/PG7/SIM26/SIM27）确认前提未破坏
Step 4  C3 preflight v2 → 手工试跑 preflight（应能抓住本轮回归的 5 个前提失配）
Step 5  C2 data_prep + 2 个新场景 SQL → 异常题抽样（F10/PG17/EW32）
Step 6  全量重跑 → 目标 ≥96%（128/133），零 TIMEOUT；新非 PASS 全部进 ledger 归因
```

**执行进度（2026-09-12 更新）**：
- Step 4 ✅ preflight v2 三检查（陈旧度/hermes ping/真值前提断言）落地，破坏性测试
  exit 2 验证通过；9 道 live_db 题配 truth_expectation。
- Step 5 ✅ data_prep.py + scenarios.yaml + run.py 接线落地。实际接入 3 个场景
  （null_water_level→PG17、single_red_alarm→EW32、stale_forecast 对→F5/F10；F25 题面
  假设式不注入），未新写场景 SQL——存量 7 月 SQL 修复后直接复用（stale_forecast.sql
  修了 tenant_id 1→18、标记撞车 'MOCK'→'MOCK-STALE'、ID 1→20001 三个潜伏 bug）。
  验收：handler 级三场景全 PASS + 真跑 4 题（PG17/EW32/F5/F10）4/4 PASS，
  转写证实 agent 看到场景数据（F10 答出"8 小时"陈旧），teardown 后 DB 零残留
  （output/2026-09-11/step5-acceptance/）。
- Step 6 ⏸ **用户裁定暂缓**（2026-09-12："不要进行整体评测集的评测任务"）。
  全量重跑的前置条件（13/13 单题翻正 + preflight v2 + 场景层）均已就绪，
  待用户放行即可执行 `--timeout-set 2000 --llm --mode report` 全量。

**守则（数据再生的三条铁律）**：
1. **先改 rubric/断言，再动数据**——9/2 的教训：数据重建重置了所有 live 真值，rubric 没跟上就是一轮假回归。
2. **每次再生成都必须过 preflight v2 + live_db 抽样**，才允许全量。
3. **数据操作必须留 manifest**（场景名、影响表/行、pre-image 位置），可一键 `--restore`。

## 预期收益汇总

| 阶段 | 措施 | 预期分数 |
|---|---|---|
| 当前 | — | 120/133 = 90.2% |
| Step 1 后 | 资产修复 9 项 | ~128/133 = 96% |
| Step 2 后 | 行为修复 4 项 | ~131/133 = 98.5% |
| Step 3-5 后 | 数据准备层 | 分数不再受数据漂移扰动，方差收窄 |
