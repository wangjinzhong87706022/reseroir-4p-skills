# Autoresearch Changelog — plan-generation

## Experiment #0 — baseline

**Score:** 24/30 (80.0%)
**Change:** 无（原始 SKILL.md v2.1）
**Reasoning:** 建立基线
**Result:** Q1-Q3,Q5 通过 (6/6)，Q4 超时
**Failing outputs:** Q4（预案解读）因 Agent 执行时间过长超时

## Experiment #1 — discard

**Score:** 23/30 (76.7%)
**Change:** 增加"预案解读高效查询"SQL 指导
**Reasoning:** 指导 Agent 使用 JOIN 查询一次性获取预案+调度数据，减少查询次数
**Result:** Q4 通过 (5/6)，但 Q5 超时。总分下降
**Failing outputs:** Q5（多方案对比）超时，说明超时问题是随机的

## Experiment #2 — discard

**Score:** 23/30 (76.7%)
**Change:** 移除"直接SQL查询"示例，精简 SKILL.md
**Reasoning:** 减少 Agent 上下文大小，鼓励使用 Python 脚本
**Result:** Q5 仍然超时。总分下降
**Failing outputs:** Q5 超时，说明精简内容对超时无帮助

---

## 总结

**基线：** 24/30 (80.0%)
**最终：** 24/30 (80.0%)（回退到基线）
**实验次数：** 3（1 基线 + 2 实验）
**保留数：** 0（所有实验均回退）

**根因分析：**
- 失败原因不是 SKILL.md 内容问题，而是 Agent 执行时间不可预测
- Q4/Q5 需要多次 SQL 查询，执行时间 20-240 秒不等
- 240 秒超时对简单问题足够，对复杂问题不稳定

**优化建议：**
1. 增加超时时间到 360-480 秒
2. 优化 Agent 的查询策略（减少 DESCRIBE 命令）
3. 使用 `full_context` 脚本预取数据，减少实时查询
