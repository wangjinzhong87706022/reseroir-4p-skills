# 可调参数

## 告警合并参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.merge.enabled` | true | 是否启用活跃告警合并 |
| `alarm.merge.fingerprint_fields` | st_code,eq_code,ew_rules_id | 指纹计算字段 |

## 升级参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.escalation.enabled` | true | 是否启用告警升级 |
| `alarm.escalation.L1.1` | 120 | L1 首次升级时间（分钟） |
| `alarm.escalation.L1.2` | 240 | L1 二次升级时间（分钟） |
| `alarm.escalation.L1.3` | 480 | L1 三次升级时间（分钟） |
| `alarm.escalation.L2.1` | 240 | L2 首次升级时间（分钟） |
| `alarm.escalation.L2.2` | 480 | L2 二次升级时间（分钟） |
| `alarm.escalation.L2.3` | 1440 | L2 三次升级时间（分钟） |
| `alarm.escalation.L3.1` | 480 | L3 首次升级时间（分钟） |
| `alarm.escalation.L3.2` | 1440 | L3 二次升级时间（分钟） |
| `alarm.escalation.L3.3` | 2880 | L3 三次升级时间（分钟） |
| `alarm.escalation.L4.1` | 1440 | L4 首次升级时间（分钟） |
| `alarm.escalation.L4.2` | 2880 | L4 二次升级时间（分钟） |

## 恢复检测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.recovery.enabled` | true | 是否启用恢复检测 |
| `alarm.recovery.check_interval` | 300 | 检测间隔（秒） |
| `alarm.recovery.min_duration` | 30 | 最小告警持续时间（秒），低于此值不检测恢复 |

## 风暴检测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.storm.threshold` | 50 | 风暴阈值（1分钟内告警数） |
| `alarm.storm.cooldown` | 300 | 风暴冷却期（秒），风暴结束后多久再次检测 |

## 预测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.prediction.enabled` | true | 是否启用预测性预警 |
| `alarm.prediction.forecast_hours` | 12 | 预测时间窗口（小时） |
| `alarm.prediction.confidence_threshold` | 70 | 置信度阈值（%） |

## 通知参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm.notification.storm_suppress` | true | 风暴期间是否抑制通知 |
| `alarm.notification.recovery_always` | true | 恢复通知是否总是发送 |

## Agent 行为指引

当用户问"当前的告警参数配置"时：
1. 列出所有参数及其当前值
2. 标注哪些是默认值，哪些是自定义值

当用户说"修改升级时间"时：
1. 询问要修改哪个等级和哪次升级
2. 询问新的时间值
3. 更新参数配置
4. 确认修改生效
