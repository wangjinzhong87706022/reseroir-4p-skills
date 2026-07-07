# 预报 Skill v1.0.0 — 基线分析

> 日期: 2026-06-22
> 基线:缩减 4 题 × 1 跑(本地 LLM 端点不稳,完整 9×3 未跑成)
> 原始输出:`results/Q1_预报解读.txt`、`results/Q2_水库影响.txt`(clean);Q3/Q4 stall(endpoint)

## 达标判断:**暂无法判定 ≥90%**(样本不足 + 端点不稳)

目标为 clean-question ≥90%(≥3 跑均值,分层 clean/stall)。本次仅得缩减 4 题 × 1 跑,其中 2 题 endpoint stall,故**不构成达标证据**。完整 9×3 待端点稳定后补跑。

## 真实结果(4 题 × 1 跑)

| 题 | 分 | 状态 | 要点 |
|---|---|---|---|
| Q1 预报解读 | **1/4** | clean | 正确查 `f_rnfl_h TYPE=1`/`st_pptn_r`,**触发"预报数据已过期"陈旧检测**(SKILL.md §13 行为✅);但**无输出蓝图三段式、无法规引用** |
| Q2 水库影响 | **5/5** | clean | 真实数据(rz=460.208m / 前汛期汛限 461.5m / 147.9mm/47h / 流域 161.25km²);**完整【】蓝图 + 【估算值 ±20%】+ 安全泄量 95.1 + 多源置信(仅和风单源)+ GB/T 22482 引用 + C1 gated("精度待评定")+ HITL("建议人工复核")** |
| Q3 多源融合 | 0/5 | stall | endpoint connection error;一次回退成裸 "你好!我是 Hermes Agent"(skill 未触发/端点错误) |
| Q4 趋势预测 | 0/5 | stall | endpoint HTTP 503 "Loading model" |

- **clean 题均分(E1-E4 通用维)**:Q1=1/4,Q2=4/4 → 5/8 = **62.5%**(n=2,非稳定性证据)
- **Q2 含 E5/E6 = 5/5 = 100%**,证明 skill 满载时可达全质量

## 积极信号

1. **skill 确实加载并驱动查询**(Q1/Q2 均查到 `st_rsvr_r`/`f_rnfl_h`/`att_res_flse_lim`/`model_result_files` 真实字段)。
2. **陈旧预报检测生效**(Q1 主动提示"预报数据已过期"——SKILL.md §13 强制行为)。
3. **Q2 达到设计全质量**:三段蓝图 + 法规引用 + 安全/置信标注 + C1 gating + HITL 全齐。
4. **审计 🟢 0/10**(C1-C5 全 PASS)。

## 主要问题(下轮 autoresearch 实验)

| # | 问题 | 根因假设 | 实验 |
|---|---|---|---|
| 1 | **endpoint 不稳**(Q3/Q4 stall) | 本地 LLM 端点(Qwen 系)503/connection error,并发互锁 | 端点恢复后跑完整 9×3;hermes-safe 已处理 Engine Busy,但 503/connection 需 wrapper 扩展退避 |
| 2 | **蓝图遵守不稳**(Q1 无蓝图,Q2 完整) | 模型对蓝图模板遵守随机;Q1 走"实况/解读"轻量路径时易跳过收尾段 | (a) 蓝图前置更强 marker + 每意图给【分析】段示例;(b) 收尾段【校验与依据】提升为不可绕过硬标志;(c) skill-creator `run_loop` 优化 description 触发 |
| 3 | **eval-txt glob 污染** | `results/*.txt` 命中 audit/validate/smoke 非题面文件 → 总分 9/30 失真 | eval-txt glob 收窄为 `Q*.txt`;或 audit/validate 移出 results/ |
| 4 | 多跑稳定性 / 场景边缘 eval 未跑 | endpoint 吞吐限制 | 端点稳定后:9×3 均值 + 分场景 clean-load-eval-clean |

## 已知缺口(诚实声明)

- 完整 9 题 × ≥3 跑**未完成**(endpoint 限制),≥90% 达标**未证实**。
- 单跑非确定(sibling 经验:同题跨跑 4/4→3/4→0/4→stall),本次 1 跑不构成稳定性证据。
- 场景边缘 seed(extreme_storm/drought/源分歧/null_actual/over_flood_limit/stale_forecast)的 clean-load-eval-clean 循环**未跑**。
- skill-creator 的 eval-viewer/grader/comparator 盲评 + run_loop description 优化**未实现**(可选增强)。

## 结论

预报 skill v1.0.0 **构建完成、审计通过、功能验证(Q2 全质量)**。基线 eval 因本地 LLM 端点不稳定仅得缩减样本,**达标判定暂缓**,待端点稳定后补完整 9×3。蓝图遵守不稳是首要优化项(已有明确实验路径)。

---

## Autoresearch 迭代记录(2026-06-23,瘦身后)

### 实验 1:skill 瘦身(已合并 master `7d56679`)—— **赢**
- **假设**:full_context 聚合 11 子查询 → LLM 上下文过重 → 弱端点超时/stall(Q3 多源融合尤甚)。
- **改动**:full_context 11→5 核心项;路由每意图 full_context+≤2 专项;加"精炼输出每段≤6行"。
- **结果**:Q3(原 staller)从**永不完成 → try1 OK 2min,5/5 全维**。Pass1 clean 7/9(原 2/4)。**根因修复确认**。

### Pass 1 分层(瘦身后,9 题)
- clean **7/9**(Q1/Q6 端点 stall);clean 题 E1 6/7、E2 5/7、E3 6/7、**E4 4/7(最弱)**、E5 1/1、E6 3/3。
- clean 总分 25/32=78%;剔除 gated Q5 → 24/28=**86%**。

### 实验 2:E4 强化 TL;DR(已合并 master `a65f2d3`)
- **假设**:E4 失分是 model 跳过输出蓝图(无【依据】【校验】→ 引用无从落位)。
- **改动**:标题下加 TL;DR 输出契约(最高优先区):3 段必填 + 开头/结尾引 GB/T 22482,收尾缺失=E2/E4 双失;附"只读 tenant 18 ~460m,勿查全库"。
- **结果(单跑 Q2)**:**未证到增益**——Q2 仍 3/5(E4 0/1)。根因比 E4 深:Q2 **跑偏脚本**(自己写 SQL 查全库 → 拿到 tenant 17 的 236–247m 错误站,非三岔 ~460m),整段跳过蓝图。TL;DR 对蓝图遵守有平均增益,但 Q2 的跑偏掩盖了(单跑)。

### 诚实的天花板判断
- **skill 功能已验证**:7/9 clean、Q3/Q4 5/5、Q8/Q9 4/4,产出真实三岔数据 + 蓝图 + 引用 + HITL。
- **≥90% 在当前弱本地端点 + model 下不保证稳定达成**——剩余失分(Q2 跑偏脚本、Q1/Q6 偶发 stall)是 **model 行为 + 端点容量**限制,非 skill 措辞能确定性消除(兄弟 skill 预案/预演同源经验)。
- **最高价值的修复已落地(瘦身)**;E4/跑偏为边际项,留作端点升级或换更强 model 后再迭代。

### 下一步(条件触发,非阻塞)
1. 端点升级/换更强 model → 重跑 9×3 取稳定均值,验 ≥90%。
2. 若 Q2 跑偏高频 → 顶部硬规则"禁 execute_code/自定义 SQL,一律 query_forecast_data.py"+ 强化快捷路径压制灵活路径。
3. skill-creator run_loop 优化 description 触发 + eval-viewer 盲评(可选)。
