# Ticket 006 — AgentTeams Worker 如何访问宿主机 MySQL

## Question

Docker Worker 在容器内运行，宿主机 MySQL 在 `127.0.0.1:3306`。Worker 的工具网关也在宿主机上（`:18089`）。但 MySQL 本身也需要从 Worker 访问（部分工具可能需要直接查 MySQL）。网络路径怎么走？

## 网络拓扑

```
宿主机
├── Docker Network (172.17.0.0/16)
│   └── Worker Container (172.17.0.x)
│       └── 工具网关 (:18089) ✓ 已确认可达
│       └── ??? MySQL (:3306) ❓ 如何访问
└── MySQL (:3306) ← 通常绑定 127.0.0.1，不暴露到 Docker 网络
```

## 候选方案

### 方案A：MySQL 绑定到 0.0.0.0（推荐）
```
# my.cnf
bind-address = 0.0.0.0
# 然后从容器内用 docker network gateway 访问
# 宿主机 docker0 网关: 172.17.0.1
mysql_url = 172.17.0.1:3306
```
- 优点：最简单
- 缺点：MySQL 暴露到局域网（安全风险，但比赛内网环境可接受）

### 方案B：工具网关代理 MySQL
```
# 工具网关同时暴露 MySQL 查询接口
# Worker 只能通过工具网关查 MySQL，不能直连
POST /tools/{tenant_id}/db.query
  body: {"sql": "SELECT water_level FROM st_rsvr_r ..."}
```
- 优点：MySQL 不暴露
- 缺点：所有查询都要封装成 HTTP，增加复杂度

### 方案C：MySQL 端口映射到工具网关
```
# docker run -p 13306:3306 ...
# 容器内访问: host.docker.internal:13306
```
- 优点：简单
- 缺点：依赖 host.docker.internal 解析（AGENTTEAMS_RUNBOOK.md 提到这个在部分 Docker Desktop 环境不可用）

## 预期答案

**推荐方案B（工具网关代理 MySQL）**：
- 理由：工具网关已经是必需的（暴露 HTTP 接口），扩展它代理 MySQL 查询是自然延伸
- Worker 只需访问工具网关一个地址，不需要知道 MySQL 在哪
- 安全：MySQL 不暴露到容器网络

## 关联

- blocked by: Ticket 002
- blocking: Ticket 007（工具网关实现）
