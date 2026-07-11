# 反馈日志

## 概念

记录 Agent 在告警处理过程中的反馈和学习，用于持续优化。

## 反馈类型

| 类型 | 说明 |
|------|------|
| `diagnosis_accuracy` | 诊断准确性反馈 |
| `prediction_accuracy` | 预测准确性反馈 |
| `rule_effectiveness` | 规则有效性反馈 |
| `user_satisfaction` | 用户满意度反馈 |

## 反馈记录格式

```json
{
  "timestamp": "2026-06-02T14:30:00Z",
  "feedback_type": "diagnosis_accuracy",
  "alarm_id": 12345,
  "agent_diagnosis": "水位上涨导致超警戒",
  "actual_cause": "降雨导致水位上涨",
  "accurate": true,
  "notes": "诊断正确，但未考虑上游水库泄洪因素",
  "improvement": "增加上游水库泄洪数据的关联分析"
}
```

## 查询反馈日志（读 — 直连数据库）

### 统计诊断准确率

```sql
SELECT 
  feedback_type,
  COUNT(*) as total,
  SUM(CASE WHEN accurate = true THEN 1 ELSE 0 END) as accurate_count,
  ROUND(SUM(CASE WHEN accurate = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as accuracy_rate
FROM alarm_feedback_log 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY feedback_type
```

### 查询最近的反馈

```sql
SELECT id, feedback_type, alarm_id, agent_diagnosis, 
       actual_cause, accurate, notes, improvement, timestamp
FROM alarm_feedback_log 
ORDER BY timestamp DESC
LIMIT 20
```

### 查询需要改进的模式

```sql
SELECT improvement, COUNT(*) as count
FROM alarm_feedback_log 
WHERE accurate = false
  AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY improvement
ORDER BY count DESC
LIMIT 10
```

## Agent 行为指引

当用户说"诊断不准确"时：
1. 询问用户的实际原因
2. 记录反馈到日志
3. 分析诊断偏差的原因
4. 提出改进建议

当用户问"诊断准确率如何？"时：
1. 统计诊断准确率
2. 按反馈类型分组
3. 展示需要改进的模式
4. 给出优化建议

当用户说"这个规则不准确"时：
1. 询问具体哪个规则
2. 询问实际触发情况
3. 记录规则有效性反馈
4. 建议规则调整方案
