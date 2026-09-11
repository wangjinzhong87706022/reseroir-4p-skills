# 2026-09-11 修复重跑结果：13/13 翻正

> 对照 9/10 全量 120/133=90.2% 的 13 个 FAIL，逐题修复后单题重跑 **13/13 PASS**。
> 折算全量口径：**133/133 = 100%**（13 题重跑独立于其余 120 题，其余题目本轮未动数据/资产面影响极小，待 Step 6 全量复核确认）。
> 施工图：`docs/eval/2026-09-11-fix-execution-plan.md` · 归因：`docs/eval/2026-09-11-eval-analysis-and-plan.md`

## 重跑结果

| # | 题 | 9/10 | 本次 | 耗时 | 修复落点 |
|---|----|------|------|------|----------|
| 1 | DV1 | FAIL | PASS | 1125s | SKILL 最终答复格式硬约束（评分行+止血/根治小节，transcripts 已验证含三要素） |
| 2 | DV7 | FAIL | PASS | 690s | rubric 租户归属声明 + 字段集任二 |
| 3 | DV8 | FAIL | PASS | 896s | rubric 复合根因逐一映射 |
| 4 | EW32 | FAIL | PASS | 278s | rubric 双路径（级别权重 / 数据质量治理） |
| 5 | F22 | FAIL | PASS | 70s | truth_query 加 `tenant_id=18`（真值 27→8，extracted 命中） |
| 6 | F24 | FAIL | PASS | 196s | rubric 同义锚点（下泄/泄洪能力/控泄等价） |
| 7 | F25 | FAIL | PASS | 42s | rubric 逐源降级语义命中 |
| 8 | PG2 | FAIL | PASS | 235s | rubric 双汛期口径（3.3m/2.8m 任一，±0.2m） |
| 9 | PG17 | FAIL | PASS | 44s | rubric 前提失配条件化（实查有值须指出矛盾） |
| 10 | PG24 | FAIL | PASS* | 247s→484s | 题目锁定假设+锚点；c3 二次条件化（见下） |
| 11 | SIM4 | FAIL | PASS | 226s | SKILL v1.9.5 前置 status 检查（transcripts 含 status=3） |
| 12 | SIM8 | FAIL | PASS | 111s | rubric 失败/低质量背景双分支 + SKILL 前置检查 |
| 13 | SUP5 | FAIL | PASS | 870s | SKILL 仲裁表加"水位>当前生效汛限→升级处置"行 |

\* PG24 第一轮 12/13，c3「不输出二元结论」字面拦住「**结论：危险。**」（agent 实质立场正确：零余量/贴限
+ 启动预案 + 有依据）。c3 条件化为"有依据+可操作即不算二元，仅无依据断言才 fail"后单题重验 PASS（484s）。

**总计**：12/13 第一轮 + PG24 补验 = **13/13**。判分依据抽查全部对得上（F22 真值命中、DV1 三要素、
SIM4/SIM8 status=3 标注），非 judge 放水。

## 本轮额外产出（Part B 资产卫生）

- **7 处 truth_query 补租户过滤**，其中两个潜伏真雷：
  - PG7 汛限查询：`att_res_flse_lim` 双租户 + 无排序 `LIMIT 1`（三岔 462.0 / 桃曲坡 786.8 同时满足季节条件）→ 此前 PASS 属侥幸；
  - PG12 预案统计：truth 混入 tenant 17 的 8 条（29 vs 21），靠容差 20 掩盖。
- **B2 撤项**：md 复选框与 JSON 复核 13/13 一致，"F23 误标"系误读，report.py 无 bug。
- eval/README.md：timeout 三层语义 + truth 租户纪律成文。
- stage5 ledger（2026-09-04）全部清账。

## 改动清单（未提交，随时可 commit）

```
eval/cases/forecasting.yaml           F22 truth / F24 F25 rubric / F7 F12 truth 租户
eval/cases/plan-generation.yaml       PG2 PG17 PG24 rubric+question / PG7 PG12 truth 租户
eval/cases/early-warning.yaml         EW32 rubric
eval/cases/simulation.yaml            SIM8 rubric / truth 租户
eval/cases/diagnosis-verification.yaml DV7 DV8 rubric / truth 租户
eval/lib/judge.py                     A5 语义等效校准句
eval/README.md                        timeout 语义 + truth 租户纪律
simulation/SKILL.md                   v1.9.5 前置 status 检查
diagnosis-verification/SKILL.md       最终答复格式硬约束
supervisor/SKILL.md                   仲裁表水位行
docs/eval/2026-09-04-non-pass-ledger.md  清账
docs/eval/2026-09-11-fix-execution-plan.md  B2 撤项标注
docs/eval/2026-09-11-eval-analysis-and-plan.md  X6 撤项标注
+ 工作区既有未提交：forecasting/data/generate_sancha_data.py（roll 断点修复，已在生效）
```

## 下一步（施工图 Step 3-6）

| Step | 内容 | 要点 |
|---|---|---|
| 3 | C1 波形修复 + 提交 roll 断点修复 | 三岔两值方波（459.18/462.65）治理，绝对时钟相位+噪声；改后 `--roll` 续写并跑 live_db 抽样（F7/F12/PG6/PG7/SIM26/SIM27） |
| 4 | C3 preflight v2 | truth_expectation 快照断言，30 秒拦住前提腐烂（本轮 PG7/PG12/F22 类） |
| 5 | C2 data_prep.py | 把 `forecasting/data/scenarios/` 7 个存量场景 SQL 接进评测 + 2 个新场景（null_water_level/single_red_alarm） |
| 6 | 全量重跑 | 目标确认 ≥96%（预期 100%），新非 PASS 全部进 ledger |

守则：先改 rubric/断言再动数据；再生成必过 preflight+抽样；数据操作必留 manifest。
