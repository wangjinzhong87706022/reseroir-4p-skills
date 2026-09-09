# 2026-09-08 夜间全量评测深入分析与优化方案

- **运行**: `output/2026-09-08/full-20260908-201456/`（GLM-5.1，`--timeout-set 1000 --llm --mode report`，2026-09-08 20:16 → 2026-09-09 06:55，共 10.6h）
- **结果**: **115/133 = 86.5%**（PASS 115 / FAIL 15 / TIMEOUT 3）
- **对比基线**: v2 基线（eval-20260903-233359.json）118/133 = 88.7% → **净回撤 -2.2pp**
- **前置**: preflight 通过（三岔断点陈旧 1.3h、桃曲坡 0.3h，hermes ping OK）

## 1. 总体结论

本轮 18 个非 PASS 中，**没有一例是"能力真退化"**。逐题核对 transcript + live DB 真值后，归因分布如下：

| 归因桶 | 数量 | 案例 | 性质 |
|---|---|---|---|
| B-rubric 与 live DB 前提失配 | 7 | EW6, EW8, EW21, F13, SUP1, SUP3, SUP10 | 评测资产问题，agent 答案反而更符合真实数据 |
| C-truth 前提腐烂（mock 再生副作用） | 3 | SIM4, SIM9, SIM18 | DB 里已存在预演结果，rubric 的"无结果"前提失效 |
| A-超时 | 5 | DV2, DV3, DV5, DV8, PG25 | heavy 任务超 1000s；B4 修复（stage5 backlog）未落地 |
| D-答案抽取截断 | 1 | PG8 | 只抽到 98 字收尾语，数字/关键词全丢 |
| E-判分过严（单条 rubric 卡死） | 2 | DV1, SIM28 | 5 条中 4 条过，仅 1 条措辞性失败 |

**核心判断**：-2.2pp 回撤几乎全部来自 stage5 验收时已识别但**未落地**的 Priority B 修复（B1/B2/B3/B4），加上一次 mock 数据再生引入的 SIM 前提腐烂。这是**评测资产维护债**，不是被测系统的回归。

## 2. 18 个非 PASS 逐题归因

### 2.1 回归项（11，基线 PASS → 本轮非 PASS）

| # | 案例 | 归因 | 证据 |
|---|---|---|---|
| 1 | EW6 渗流异常根因 | B | agent 正确发现 `st_perpercolation` 数据 2026-08-23 后停止更新 → 判"无法联合渗压+渗流交叉判断"是**正确结论**；rubric c1 仍要求交叉判断 |
| 2 | EW8 水位降雨关联 | B | agent 正确指出降雨为 MOCK 数据、无法做时滞判断；rubric c2 要求时滞结论 |
| 3 | EW21 告警风暴检测 | B | 当前 DB 无暴雨、引擎 7 天未产出 → agent 正确报"无风暴"；rubric 期望风暴判定+聚合建议。B1 条件化未做 |
| 4 | F13 死水位逼近 | B | 真值：当前 462.65m vs 死水位 451m，余量 **11.65m**，根本不接近死水位；agent 正确反驳用户前提；rubric 仍要求"识别低水位风险+保供建议" |
| 5 | PG25 tmSpan=0 校验 | A | 1002s 超时，transcript `answer_extracted=False answer_chars=0`，hermes 无可抽取输出 |
| 6 | SIM28 综合场景 | E | 仅 c3"报告含明确推荐方案"失败；7 步链路+一致性均过 |
| 7 | SUP1 场景A 七步研判 | B | 仲裁实际写"仿真 max_level=790.5m vs 方案 790.5m 一致"；rubric 硬编码"仿真最高水位 786.95m 超汛限 786.8m"与真实仿真输出不符 |
| 8 | SUP3 场景B 诊断链 | B | c1 链路新失败 + c2 数据质量识别；B3 条件化未做 |
| 9 | DV2 告警堆积诊断 | A | 1000s 整点超时；DV heavy 任务（对照 DV1 899s 勉强完成、DV7 772s） |
| 10 | DV3 输出验证 | A | 1000s 整点超时，transcript 停在临时脚本 diff 中途 |
| 11 | DV8 根因诊断 | A | 1000s 整点超时 |

### 2.2 持续失败项（7，基线也非 PASS）

| # | 案例 | 归因 | 证据 |
|---|---|---|---|
| 12 | DV5 自动修复 | A | 1000s 超时；transcript 停在更新知识库 RC-10（连接池根因）中途——**注意：这次写入污染了仓库状态**（见 §4） |
| 13 | SIM4 失败洪水多方案预演 | C | DB 已有 flood_id=9 预演结果 **154 行**（`srm_flood_history_result`，2026-09-09 实查），rubric"检测无预演结果"前提失效；agent 跑了真结果并如实标注低质量 |
| 14 | SIM9 解读无结果洪水 | C | flood_id=17 有 **82 行**结果且 base.status='2'，"id=17 无预演"前提已腐烂 |
| 15 | SIM18 无结果洪水报告 | C | 同上 |
| 16 | SUP10 断点续跑 | B | 事件 A-20260805-019 实际 7 步全部完成，"从 Step4 续跑"物理不可能；B2 条件化未做 |
| 17 | DV1 数据时效性诊断 | E | 仅 c1"Phase 0 = P0"失败（agent 写 P1），其余 4 条全过；899s 完成 |
| 18 | PG8 配置查询 | D | 只抽到 98 字收尾语"已查询完毕，临时脚本可手动删除…"；transcript 显示 agent 已正确查 `model_config`（先查错列 config_value 后纠正），数字 [445,465] 未进被判文本 |

### 2.3 修复确认（8，基线 FAIL → 本轮 PASS）

F22（A1 真值修复生效）、F24、PG18、PG2、PG3、SIM17、SIM2、SIM29 —— stage5 的 A1 + 部分 rubric 措辞调整已兑现。

## 3. 关键发现

1. **Priority B backlog 全部未执行**。stage5 验收（2026-09-04）列出的 B1(EW21)/B2(SUP10)/B3(SUP3)/B4(DV 超时) 四项，本轮逐一复现为 FAIL/TIMEOUT，贡献 7 个非 PASS。
2. **mock 数据再生导致 SIM truth 前提腐烂**（新缺陷类）。20b4351 的 mock 幂等工作或历史预演运行在 `srm_flood_history_result` 留下了真实结果行，SIM4/9/18 三个"无结果"反编造题的考题前提整体失效。DB 实查：flood 9→154 行、flood 17→82 行、id=17 status='2'。
3. **DV heavy 任务系统性超时**。1000s 对 DV2/3/5/8 不够（同类 DV1 899s、DV7 772s 勉强过）。B4 提出的 1500s 提升未落地。
4. **答案抽取仍是单点脆弱性**。53/133 题 `answer_extracted=False`；PG8 直接因此丢分（抽取只取最后一个 `┊` 块之后的文本，本例为收尾寒暄）。
5. **评测运行会污染仓库**。DV5 超时前向 `state/knowledge-base/root-cause-solutions.yaml` 写入 RC-10，留下未提交改动；git status 中多个 eval 期间产生的未跟踪文件。评测必须在隔离副本/沙箱中跑。

## 4. 优化方案（按优先级）

### P0 — 本周内，修完即可预期回到 ≥90%

| 任务 | 内容 | 涉及 | 预期收益 |
|---|---|---|---|
| P0-1 | **落地 B1/B2/B3 rubric 条件化**：EW21 c2 按"检出风暴/未检出风暴"双分支；SUP10 c2 按"事件已完成/事件中断"双分支；SUP3 c2 按"数据缺失/数据降质"双分支 | `eval/cases/early-warning.yaml`、`supervisor.yaml` | +3 |
| P0-2 | **落地 B4**：DV2/DV3/DV5/DV8 timeout 提至 2000s（与 EW heavy 同级），或拆分 DV heavy 任务 | `eval/cases/diagnosis-verification.yaml` | +4（至少 +3） |
| P0-3 | **修 SIM4/9/18 truth 前提**：二选一——(a) 评测前置清场：preflight 增加第 3 步，检查并清理 tenant 18 的 `srm_flood_history_result` 残留行（记录到 run.status）；(b) 重写 rubric 为"评价 agent 对已有(低质量)结果的标注与解释能力" | `eval/preflight.py` 或 3 条 case | +3 |
| P0-4 | **F13/EW6/EW8/SUP1 rubric 对齐真实数据**：F13 改为校验"反驳错误前提 + 给出真实余量 11.65m"；EW6/EW8 改为校验"正确识别数据源失效/MOCK 并降级"；SUP1 数字改为动态真值或去掉硬编码水位 | 4 条 case | +4 |

P0 合计可修复 ≤14 项 → 预期 **129/133 ≈ 97%**（上限受 DV5/SIM28 等残余项影响）。

### P1 — 两周内

1. **PG8**：抽取器对 `answer_chars < 200` 时回退取 transcript 末 2000 字符重判；同时把 model_config 查询路径（config_key/config_value 列名）写进 case 提示或 SKILL。
2. **DV1/SIM28 单条卡死**：DV1 c1 放宽为"Phase 编号正确或给出等价优先级论证"；SIM28 c3 放宽为"给出推荐或说明不可推荐原因"。
3. **评测隔离**：run.py 启动前 `git stash`/worktree 快照 + 结束后 diff 报告仓库变更；DV 类 SKILL 增加"临时脚本写到 eval 临时目录、不写 state/"约束。
4. **SUP1/SUP3 等 supervisor 长链路**（2000s 已过但 c1 新失败）：单题重跑 3 次确认是否为抖动，再决定是否进 rubric 条件化。

### P2 — 持续改进

1. 上下文感知数字抽取器（stage5 C1）。
2. hermes verifier footer 防误抽（stage5 C3）。
3. `answer_extracted=False` 率（53/133=40%）作为质量指标纳入 preflight 报告；连续两轮上升则触发 transport 重构。
4. 真值 freshness：为含 DB 前提的 case 增加 `truth_freshness` 字段，preflight 按它逐题校验，避免 SIM 类前提再次腐烂。

## 5. 建议执行顺序

1. P0-1 + P0-2（纯 yaml/timeout，半小时）→ 单题重跑 EW21/SUP10/SUP3/DV2/DV3/DV5/DV8 验证。
2. P0-3（preflight 清场，需要动 preflight.py）→ SIM4/9/18 重跑。
3. P0-4（4 条 rubric 改写，需逐题对照 transcript 真值）→ 重跑验证。
4. 全量重跑确认 ≥90%，更新 v3 基线与 ledger。
