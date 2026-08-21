# SPEC: 水库四预多智能体协作系统 — AgentTeams 基座

## Problem Statement

当前 SmartTwinRes 的四预智能体（forecasting / early-warning / plan-generation / simulation）是4个独立的 Hermess Skill，各自为战，无法自动串联成完整的水库事故处置闭环。现有 `supervisor/` 编排层基于 Python DAG / SQLite State，是单进程架构，无法满足 GOAI 世界人工智能开源大赛**新智基座（Agent Infra）**赛道对"可运行 Demo + 多智能体协作 + 工程验证"的要求。需要在 **AgentTeams**（Matrix 消息驱动 + Docker Worker）上重新实现四预协作体系。

---

## Solution

将 SmartTwinRes 四预能力集群从 Python Skill+DAG 架构迁移到 **AgentTeams 多智能体协作平台**，保留现有的 MySQL 水库数据库和 reservoir profile 机制，新增 HTTP 工具网关连接数据库，4个专业 Worker 通过 Matrix 消息协作，TeamLeader 负责场景路由和 DAG 编排。

---

## User Stories

1. 作为**值班人员**，在 Element Web 的 Team 房间输入"暴雨导致水库水位快速上涨"，系统自动完成预报→诊断→预演→预案→预警全链路，输出调度建议报告。

2. 作为**运维人员**，在水务局收到防洪预警后，系统查询实时水位/雨量/汛限水位，自动判断预警等级并生成应急调度预案。

3. 作为**水利工程师**，在汛期获取未来24h降雨预报+水库来水预报，系统自动进行多方案对比仿真并输出最优调度方案。

4. 作为**参赛者**，在本地 Docker 环境中一键启动 AgentTeams + 工具网关，运行"汛期暴雨"完整场景，录制可展示多智能体协作的 Demo 视频。

5. 作为**评审**，在 Matrix Team 房间观察到 TeamLeader 调度4个 Worker 依次工作，每个 Worker 通过 HTTP 网关查询 MySQL 数据库，TeamLeader 最终汇总报告。

6. 作为**后续开发者**，基于水库名/tenant_id 接入新水库（已接入桃曲坡 tenant_id=20），Skill 配置不变，系统自动适配。

7. 作为**平台管理员**，在复赛阶段展示系统在高水位/低水位/汛限等多种场景下的健壮性，触发预警阈值时系统自动生成应急预案。

---

## Implementation Decisions

### 模块划分

| 模块 | 说明 |
|------|------|
| `tools/reservoir_gateway.py` | Flask HTTP 网关 (:18089)，暴露四预工具接口，内部调用 `lib/db.py` 查询 MySQL |
| `at/create_team_message.md` | AgentTeams 创建消息，包含5个 Worker + 1个 Team 的完整定义 |
| `agents/water-forecast/` | Worker: 降雨预报解读、水库来水估算、水位趋势 |
| `agents/diagnosis/` | Worker: 数据质量检查、异常检测、跨域关联分析 |
| `agents/simulation/` | Worker: 多方案对比预演、敏感性分析 |
| `agents/dispatch-planner/` | Worker: 调度预案生成、方案对比推荐 |
| `agents/early-warning/` | Worker: 预警阈值监控、预警生成、应急响应 |
| `agents/team-leader/prompt.md` | TeamLeader 编排 prompt：场景路由、DAG 调度、结果仲裁 |
| `scenarios/summer_storm.yaml` | 比赛用场景：汛期暴雨导致水位快速上涨 |

### 工具网关接口（HTTP POST，JSON body）

```
POST /tools/{tenant_id}/reservoir.query_water_level
  body: {"reservoir_name": "桃曲坡"}
  → {"ok: true, result: {water_level, flood_limit_level, normal_level, ...}}

POST /tools/{tenant_id}/reservoir.query_forecast
  body: {"reservoir_name": "桃曲坡", "hours": 24}
  → {"ok: true, result: {rainfall_forecast, inflow_forecast, water_level_trend, ...}}

POST /tools/{tenant_id}/reservoir.check_data_quality
  body: {"reservoir_name": "桃曲坡", "data_types": ["water_level", "rainfall"]}
  → {"ok: true, result: {quality_score, anomalies: [], ...}}

POST /tools/{tenant_id}/reservoir.run_simulation
  body: {"reservoir_name": "桃曲坡", "scenario": "flood", "params": {...}}
  → {"ok: true, result: {max_water_level, overflow_risk,方案的优缺点: [...]}}

POST /tools/{tenant_id}/reservoir.query_historical_plans
  body: {"reservoir_name": "桃曲坡", "event_type": "flood"}
  → {"ok: true, result: {plans: [{id, name, date, effect, ...}]}}

POST /tools/{tenant_id}/reservoir.query_alerts
  body: {"reservoir_name": "桃曲坡", "severity": "P1"}
  → {"ok: true, result: {alerts: [{id, level, message, timestamp, ...}]}}

POST /tools/{tenant_id}/reservoir.create_dispatch_plan
  body: {"reservoir_name": "桃曲坡", "situation": "...", "plan_type": "flood_control"}
  → {"ok: true, result: {plan_id, measures: [...], approval_level: "L2"}}
```

### AgentTeams Worker 运行时

- 所有业务 Worker 使用 `hermes` 运行时（Hermes 自主编码 Agent）
- Manager 运行时使用 `openclaw` 或 `qwenpow`
- Worker 在 Docker 容器中运行，工具网关地址为 Docker network gateway（`172.17.0.1:18089` 或 `172.18.0.1:18089`）

### 工具网关复用 SmartTwinRes 现有代码

`tools/reservoir_gateway.py` 内部复用：
- `lib/db.py` — MySQL 连接和查询
- `lib/tenant.py` — tenant_id 解析和多水库适配
- `lib/filters.py` — SQL 安全过滤
- `forecasting/scripts/query_forecast_data.py` — 预报数据查询
- `early-warning/scripts/query_early_warning.py` — 告警查询

### 多智能体协作 DAG（TeamLeader 调度）

```
用户 @team-leader "暴雨导致水库水位快速上涨"
    ↓
team-leader (场景路由)
    ↓
water-forecast → 降雨预报 + 水位趋势
    ↓
diagnosis → 数据质量 + 异常检测
    ↓
simulation → 多方案对比预演
    ↓
dispatch-planner → 生成调度预案
    ↓
early-warning → 预警等级判定 + 应急响应
    ↓
team-leader (结果仲裁 + 报告汇总)
    ↓
输出: 调度建议报告
```

### 风险策略（L0/L1 自动执行，L2/L3 审批）

- L0/L1 动作（查询、数据质量检查）：Worker 直接执行
- L2/L3 动作（调度预案生成、预警发布）：生成审批计划，由人工确认

---

## Testing Decisions

### 验证点

1. **HTTP 工具网关可用性**：`curl http://localhost:18089/health` 返回 `{"ok": true}`
2. **数据库查询正确性**：各 `/tools/{tenant_id}/reservoir.*` 接口返回结构化 JSON，无 MySQL 错误
3. **AgentTeams Worker 创建**：4个业务 Worker + 1个 TeamLeader 在 Matrix 中成功创建
4. **多智能体协作链路**：在 Team 房间发送"汛期暴雨"场景，TeamLeader 调度4个 Worker 依次工作，最终输出完整报告
5. **预警触发**：水位超过汛限水位时，系统自动生成预警和调度预案
6. **多水库适配**：切换 tenant_id（18=三岔 / 20=桃曲坡）后，Worker 查询对应水库数据

### 测试形态

- **单元测试**：`python3 -m unittest discover tests`（现有28个用例，无需 DB）
- **集成测试**：`tools/reservoir_gateway.py` 的 Flask 测试（需 MySQL）
- **E2E 测试**：AgentTeams 真实运行"汛期暴雨"场景，截图中展示多 Agent 协作证据

---

## Out of Scope

- 不实现 LangGraph / LangChain 等第三方多智能体框架
- 不改造现有的 Python Skill 文件（forecasting / early-warning / plan-generation / simulation 的 SKILL.md 保持不变）
- 不实现 RAG 向量知识库（桃曲坡文档数字化已完成但未向量化）
- 不实现长历时状态记忆（SQLite Checkpoint，断点续跑）
- 不实现预警推送多通道（微信/短信/邮件）
- 不实现真实预报模型（深度学习预报，保留现有规则+经验公式）

---

## Further Notes

**参赛赛道**：新智基座（Agent Infra）
**参赛队伍**：solo（一个人）
**复赛材料清单**：可执行 AgentTeams 代码包 / 可运行 Demo / Demo 视频 / 提交材料清单
**时间线**：复赛提交截止前完成全部实现和视频录制

关键技术来源：
- AgentTeams 架构：`/home/scada/opspilot-zero-demo/at/AGENTTEAMS_RUNBOOK.md`
- 水库四预能力：`/home/scada/SmartTwinRes-skills/docs/四预智能体深入分析报告.md`
- 现有数据库接入：`/home/scada/SmartTwinRes-skills/lib/db.py`
