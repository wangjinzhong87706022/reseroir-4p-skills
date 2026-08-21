# Ticket 002 — 工具网关最小接口集

## Question

工具网关有7个接口，6周时间不可能全部实现。先做哪些接口能最快跑通"汛期暴雨"完整场景？

## 候选接口

| 接口 | 说明 | 场景必需性 |
|------|------|-----------|
| `reservoir.query_water_level` | 查询当前水位/汛限/正常水位 | 场景必需 |
| `reservoir.query_forecast` | 降雨预报/来水预报 | 场景必需 |
| `reservoir.check_data_quality` | 数据质量检查 | 可选（简化版可跳过） |
| `reservoir.run_simulation` | 多方案对比仿真 | 场景核心（预演环节） |
| `reservoir.query_historical_plans` | 历史调度方案查询 | 可选（简化版可跳过） |
| `reservoir.query_alerts` | 告警查询 | 场景必需（预警环节） |
| `reservoir.create_dispatch_plan` | 生成调度预案 | 场景核心（预案环节） |

## 约束

- 必须复用 `lib/db.py` 现有 SQL 查询
- HTTP 端口用 18089（与 opspilot-zero-demo 一致）
- JSON 响应格式：`{ok: true, result: {...}}`

## 预期答案

最小接口集（4个）：
1. `query_water_level` — 水位实时查询
2. `query_forecast` — 降雨预报
3. `run_simulation` — 多方案仿真
4. `query_alerts` — 告警查询

（`create_dispatch_plan` 初期可由 dispatch-planner Worker 直接生成，不走网关）

## 关联

- blocked by: Ticket 001（AgentTeams 环境）
- blocking: Ticket 003（四预 Worker 数量）
