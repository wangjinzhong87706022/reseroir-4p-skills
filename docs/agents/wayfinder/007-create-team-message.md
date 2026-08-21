# Ticket 007 — create_team_message.md 结构设计

## Question

参考 opspilot-zero-demo 的 `at/create_agents_messages.md`，SmartTwinRes 水库四预系统的 AgentTeams 创建消息应该包含什么内容？如何保证 Worker 能正确调用工具网关？

## 关键要素

### Worker 定义（每个 Worker）
- `name`：worker 名称
- `mission`：一句话使命
- `skills`：对应的 SmartTwinRes skill 名称（forecasting / simulation / plan-generation / early-warning）
- `tool contracts`：HTTP POST 到工具网关的接口列表

### Team 定义
- `team_name`：团队名称（如 `reservoir-four-forecast`）
- `leader_name`：TeamLeader worker 名称（如 `reservoir-leader`）
- `workers`：纳入团队的 worker 列表

### 场景消息格式
用户发给 TeamLeader 的消息格式：
```
@reservoir-leader 桃曲坡水库，当前水位783.50m，气象台发布暴雨橙色预警，预计24h降雨量150mm，请给出调度建议
```

## 候选结构

### 方案A：完全参照 opspilot-zero-demo（推荐）
- Worker 创建消息格式 1:1 参照
- 工具网关地址用 `http://172.17.0.1:18089`
- team_name = `reservoir-four-forecast`
- 4个 Worker + 1个 TeamLeader

### 方案B：精简版
- 只创建 Team，不预先创建 Worker
- TeamLeader 按需动态创建 Worker
- 优点：减少初始创建工作量
- 缺点：第一次协作延迟更高

## 预期答案

**推荐方案A**：
- 完全参照 opspilot-zero-demo 格式，减少格式错误风险
- 4个 Worker：water-forecast / simulation / dispatch-planner / early-warning
- TeamLeader 名称：`reservoir-leader`
- 团队名称：`reservoir-four-forecast`

## 关联

- blocked by: Ticket 001, Ticket 003, Ticket 006
- blocking: 无（实现阶段）
