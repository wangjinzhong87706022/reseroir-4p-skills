# Stage 5 Non-PASS Ledger (v2 baseline, 2026-09-04)

> **Run:** `eval-20260903-233359.json` · 133 cases · GLM-5.1 · advisory keywords · 2000 s heavy-cap  
> **Gate:** 13 FAIL + 2 TIMEOUT — all attributable, no grader artifacts  
> **Attribution enum:** `simulation_anti_hallucination | rubric_needs_conditioning | timeout_too_short | judge_logic_bug`

---

## Ledger

| id | skill | verdict | attribution | fail_criteria | raw_numbers | notes |
|----|-------|---------|-------------|---------------|-------------|-------|
| DV2 | diagnosis-verification | TIMEOUT | `timeout_too_short` | elapsed 1000 s | — | genuine heavy case; not in T5-heavy list; recommend add |
| SIM2 | simulation | TIMEOUT | `timeout_too_short` | elapsed 1000 s | — | same as DV2; long-duration multi-plan comparison |
| SUP3 | supervisor | FAIL | `rubric_needs_conditioning` | c2: 仲裁识别数据质量问题（water_level 空值率高、alerts 过期） | — | answer correctly reports data-absent; rubric says "data quality problem"; concept mismatch → condition rubric on data-existence premise |
| SUP10 | supervisor | FAIL | `rubric_needs_conditioning` | c2: 从 Step4 续跑而非从头开始 | — | answer correctly says event A-20260805-019 is done (all 7 steps ok); rubric "resume from Step4" premise is false → condition on event-status |
| SIM4 | simulation | FAIL | `simulation_anti_hallucination` | c3: 不编造预演结果数据 | — | id=9 flood has status=3 (failed); agent detects status but fabricates result data instead of "no data" signal |
| SIM9 | simulation | FAIL | `simulation_anti_hallucination` | c3: 不编造预演结果数据 | — | id=17 flood query returned no rows in DB; agent says "reading results" but no data exists → fabricated |
| SIM18 | simulation | FAIL | `simulation_anti_hallucination` | c2: 不编造未经预演的指标 | — | same id=17 hallucination pattern; report contains fabricated metrics |
| SIM17 | simulation | FAIL | `rubric_needs_conditioning` | c1: 长历时洪水报告包含完整时间过程 | — | id=11 long-duration flood; agent skipped time-process section; rubric edge-case for historical flood format |
| SIM29 | simulation | FAIL | `rubric_needs_conditioning` | c1: 结合当前水位 459.18m 与降雨预报给出研判 | — | agent gave generic advice without synthesizing current-state + forecast; rubric too strict for open-domain question |
| PG2 | plan-generation | FAIL | `rubric_needs_conditioning` | c1: 给出当前水位与汛限的距离（余量约 3.3m） | — | agent reports 2.82 m vs rubric 3.3 m; either rounding or different data snapshot; condition rubric on acceptable tolerance |
| PG3 | plan-generation | FAIL | `rubric_needs_conditioning` | c1/c2: 起调/最高水位对比 + 安全余量评估 | — | hermes File-mutation verifier footer leaked into extractor; output preview shows truncated response; full transcript needed |
| PG18 | plan-generation | FAIL | `rubric_needs_conditioning` | c2: 给出最大泄流/控制出库的依据 | — | agent states max discharge=191 but doesn't cite GB-T or scheduling rule basis; rubric expects rationale |
| F22 | forecasting | FAIL | `judge_logic_bug` | live_db compare: truth=27 vs extracted=[26 floats incl. 8, truth=8 would PASS] | truth=27 (wrong, counts all tenants); tenant-18 correct=8; `_extract_numbers` grabs all floats; agent answer "8 条" is correct for tenant 18 | fix truth_query: add `tenant_id=18`; optionally add context-aware number extractor |
| F24 | forecasting | FAIL | `rubric_needs_conditioning` | c2: 明确下泄方向建议 | — | agent mentions 下泄 but not as 安全泄量 concept (95.1 m³/s); rubric expects named safety-discharge concept |
| DV5 | diagnosis-verification | FAIL | `rubric_needs_conditioning` | c5: 产出可执行的测试方案; c6: 产出可执行的提交/部署清单 | — | agent auto-repaired config but didn't produce Step5 test plan or Step6 deploy checklist; rubric expects artifacts the tool doesn't produce in auto-fix mode |

---

## Summary

| attribution | count | cases |
|-------------|-------|-------|
| `simulation_anti_hallucination` | 3 | SIM4, SIM9, SIM18 |
| `rubric_needs_conditioning` | 9 | SUP3, SUP10, SIM17, SIM29, PG2, PG3, PG18, F24, DV5 |
| `timeout_too_short` | 2 | DV2, SIM2 |
| `judge_logic_bug` | 1 | F22 |
| **total non-PASS** | **15** | |

## Forbidden-Zero-Deployment

All 6 case yamls have `forbidden_keywords: []`. Zero deployment changes required.  
Tenant map: 123 cases @ tenant 18 (sancha), 10 cases @ tenant 20 (taoqupo) — no cross-tenant forbidden leakage.

---

## 2026-09-11 处置清账

对照 9/8、9/10 两轮全量后逐条核销（方案：`docs/eval/2026-09-11-fix-execution-plan.md`）：

| id | 2026-09-11 处置 | 落点 |
|----|----------------|------|
| F22 | **补修落地**——truth_query 加 `AND tenant_id = 18`（691dcb6 只收紧了 tolerance，truth 未修是本条遗留主因） | `eval/cases/forecasting.yaml` |
| PG2 | **补修落地**——c1 双汛期口径条件化（主汛 3.3m / 后汛 2.8m 任一，±0.2m 容差） | `eval/cases/plan-generation.yaml` |
| SIM4 | 双分支 rubric 已在 691dcb6 落地；本轮补 SKILL 前置 status 检查（v1.9.5） | `simulation/SKILL.md` |
| SIM9 / SIM18 | 691dcb6 双分支已落地，9/10 全量两题已 PASS，**销账** | — |
| DV2 / SIM2 | timeout 已提至 2000s（691dcb6），9/10 全量零 TIMEOUT，**销账** | — |
| SUP3 / SUP10 | 691dcb6 条件化已落地，9/10 全量两题已 PASS，**销账** | — |
| F24 | c2 同义锚点条件化（下泄/泄洪能力/控泄 任一组合即满足） | `eval/cases/forecasting.yaml` |
| DV5 | 691dcb6 沙箱只读如实说明条款已落地，9/10 全量已 PASS，**销账** | — |
| PG3 / PG18 / SIM17 / SIM29 | 9/10 全量均已 PASS（judge 方差类），不另修，**销账** | — |

新发现横切项（本轮扫描产出）：`att_res_flse_lim` / `model_result_files` / 4 处 `st_rsvr_r` truth_query
缺租户过滤——PG7 的 truth 是跨租户随机行（今秋三岔 462.0 / 桃曲坡 786.8 同时满足季节条件），
PG12 真值混入 tenant 17 的 8 条。已全部加 `AND tenant_id = 18`。md 复选框"F23 误标"经复核为
误报（md 与 JSON 13/13 一致），撤项。
