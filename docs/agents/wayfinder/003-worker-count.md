# Ticket 003 — 四预 Worker 数量：5个还是3个

## Question

四预原始有5个环节（预报/诊断/预演/预案/预警），但5个 Worker 意味着5次创建+5次调试+5次可能的失败。是否应该压缩到3个以节省时间？

## 候选方案

### 方案A：5个 Worker（原始设计）
```
water-forecast → diagnosis → simulation → dispatch-planner → early-warning
```
- 优点：与现有 Skill 一一对应，专业性最强
- 缺点：调试工作量大，一个人6周可能不够

### 方案B：3个 Worker（压缩版）
```
forecast-and-warning → simulation → dispatch-planner
```
- `forecast-and-warning`：合并预报+预警
- 优点：减少调试节点，加快迭代
- 缺点：专业性下降，单个 Worker 职责过重

### 方案C：4个 Worker（折中）
```
water-forecast → simulation → dispatch-planner → early-warning
（跳过 diagnosis，数据质量检查合并到 forecast）
```

## 评估标准

| 维度 | 方案A | 方案B | 方案C |
|------|-------|-------|-------|
| 专业性 | ★★★★★ | ★★☆☆☆ | ★★★★☆ |
| 调试难度 | ★★★★★ | ★★☆☆☆ | ★★★☆☆ |
| 评委感知价值 | ★★★★★ | ★★★☆☆ | ★★★★☆ |

## 预期答案

**推荐方案C（4个 Worker）**：
- 去掉 diagnosis（数据质量检查合并到 forecast）
- 保留核心4个：forecast / simulation / dispatch-planner / early-warning
- 理由：既保持专业性，又减少25%调试工作量

## 关联

- blocked by: Ticket 001
- blocking: Ticket 004（create_team_message.md）
