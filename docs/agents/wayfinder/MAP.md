# Wayfinder Map — 水库四预多智能体协作系统参赛之路

## Destination

在 GOAI 新智基座赛道成功参赛：AgentTeams 环境可运行 + 工具网关连 MySQL + 至少一个完整场景跑通 + Demo 视频录制完成。

## Notes

- **赛道**：新智基座 (Agent Infra)，solo 参赛，目标优秀奖
- **技术栈**：AgentTeams (Matrix+Worker+Docker) + SmartTwinRes 四预 Skill + MySQL 水库数据
- **最大风险**：AgentTeams 环境问题（装了没跑通），必须在任何开发之前先解决
- **关键约束**：6 周时间，一个人，评委看视频不现场 debug
- **Skills**：每个 session 先查 /root/.claude/RTK.md（RTK token 优化）

## Decisions so far

<!-- empty — no tickets resolved yet -->

## Tickets

| # | 票名称 | 类型 | 状态 | blocked by |
|---|--------|------|------|-----------|
| 001 | AgentTeams 环境验证 | task | open | — |
| 002 | 工具网关最小接口集 | task | open | 001 |
| 003 | 四预 Worker 数量 | task | open | 001 |
| 004 | Demo 场景设计 | task | open | 001 |
| 005 | Demo 视频录制方案 | task | open | 001 |
| 006 | AgentTeams Worker 访问 MySQL 网络路径 | task | open | 002 |
| 007 | create_team_message.md 结构设计 | task | open | 001, 003, 006 |

**Frontier（可立即执行）**：Ticket 001

**Blocked（等待 001 解决）**：002, 003, 004, 005, 007

**Blocked（等待 002 解决）**：006

## Not yet specified

- **AgentTeams 调试时间**：装了没跑通，6周内能否解决？需要多少时间？
- **四预 Worker 数量**：5个还是压缩到3个（003会回答）
- **工具网关优先级**：6个工具接口先做哪些后做哪些（002会回答）
- **演示视频结构**：前中后分别展示什么（005会回答）

## Out of scope

- 多语言支持（非中文评委场景）
- 真实预报模型（深度学习替换规则+经验公式）
- RAG 向量知识库（桃曲坡文档已数字化但未向量化）
- LangGraph / LangChain 框架
- 多租户权限体系（只做桃曲坡一个水库）
- 预警推送多通道（微信/短信/邮件）
- 长历时状态记忆（SQLite Checkpoint 断点续跑）
