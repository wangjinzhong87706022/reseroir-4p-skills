---
name: early-warning
description: "智慧水利预警系统智能体：告警分析、诊断、预测、问答。读操作直连数据库，写操作走后端 API。"
version: 5.2.0
author: SmartTwinRes Team
license: MIT
platforms: [linux, windows, macos]
metadata:
  hermes:
    tags: [water-conservancy, early-warning, alarm, analysis, diagnosis]
    related_skills: [powerelf-data-governance, powerelf-monitor, powerelf-chatbi]
prerequisites:
  env_vars: [POWERELF_DB_HOST, POWERELF_DB_PORT, POWERELF_DB_NAME, POWERELF_DB_USER, POWERELF_DB_PASSWORD]
---

# 智能预警系统 Skill v5.2（速查卡）

## 数据库

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p123456aA. powerelf_srm_yml
```

**核心表**: ew_info_message(2021条), ew_info_rules(25条), st_rsvr_r(19万), st_pptn_r(26万)

## 快速查询

```bash
# 未确认告警
python3 scripts/query_early_warning.py --type unconfirmed --days 7

# 按级别统计
python3 scripts/query_early_warning.py --type by_level --days 30

# 最近告警
python3 scripts/query_early_warning.py --type recent --days 3

# 测站告警
python3 scripts/query_early_warning.py --type by_station --station 606K2155

# 高级别告警
python3 scripts/query_early_warning.py --type high_level --days 30

# 告警规则
python3 scripts/query_early_warning.py --type rules

# 测站排名
python3 scripts/query_early_warning.py --type station_ranking

# 设备离线
python3 scripts/query_early_warning.py --type device_offline

# 告警风暴
python3 scripts/query_early_warning.py --type alarm_storm

# 确认率
python3 scripts/query_early_warning.py --type confirmation_rate

# 气象预警
python3 scripts/query_early_warning.py --type weather_warning
```

## 智能分析

触发词（任一匹配即触发）：
- 告警情况："当前告警情况"、"告警情况如何"、"最近告警"
- 风险评估："有什么风险"、"风险大不大"、"风险评估"、"整体风险"
- 安全确认："现在安全吗"、"安全吗"、"有没有隐患"、"有没有问题"
- 告警分析："告警分析"、"分析告警"、"告警怎么这么多"
- 大坝安全："大坝安全吗"、"大坝情况"、"水位降雨渗流"
- 应急预案："需要启动预案吗"、"需要应急预案吗"、"情况严重吗"
- 未来预测："水位会涨吗"、"未来会怎样"、"会继续涨吗"
- 值班关注："今天关注什么"、"值班注意"、"重点关注"

执行流程：加载 `analysis/intelligent-analysis-workflow.md`

功能：
- 自动采集多源告警数据（告警表、水位、降雨、气象预警）
- 告警聚合与去噪（分组、去重、排序）
- 跨域关联分析（水位+降雨+渗流 → 大坝风险）
- 风险评估（高/中/低，基于5因素评分矩阵）
- 趋势预测（未来24小时水位和风险演变）
- 响应建议生成
- 高风险自动触发预案生成（需人工确认）

依赖模块：
- `analysis/risk-scoring-matrix.md` — 风险评分规则
- `analysis/correlation-analysis.md` — 跨域关联分析
- `analysis/root-cause-analysis.md` — 根因分析
- `analysis/predictive-warning.md` — 趋势预测

## 直接SQL（复杂查询）

```sql
-- 告警详情
SELECT id, ew_name, st_code, level_r, value, gather_time FROM ew_info_message WHERE id = #{id};

-- 规则阈值
SELECT name, extend FROM ew_info_rules WHERE name LIKE '%#{关键词}%';

-- 设备当前值
SELECT rz, tm FROM st_rsvr_r WHERE eq_code = '#{eqCode}' ORDER BY tm DESC LIMIT 1;
```

## 查询优化

### 性能原则

1. **一次查询获取所有数据**: 尽量用一条SQL获取所需数据，避免多次查询
2. **使用时间范围限制**: 所有查询都应包含时间范围，避免全表扫描
3. **使用LIMIT分页**: 查询告警列表时使用LIMIT限制返回数量
4. **避免SELECT ***: 只查询需要的字段

### 预置查询（推荐使用）

#### 一次性获取告警概况
```sql
-- 获取告警统计（级别分布、类型分布、确认状态）- 一条SQL搞定
SELECT 
  level_r,
  ew_type,
  COUNT(*) as total,
  SUM(CASE WHEN message_confirm = 0 THEN 1 ELSE 0 END) as unconfirmed,
  MIN(gather_time) as earliest,
  MAX(gather_time) as latest
FROM ew_info_message 
WHERE deleted = 0 AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY level_r, ew_type
ORDER BY level_r, total DESC;
```

#### 一次性获取水位+降雨+渗流
```sql
-- 获取所有监测数据（水位、降雨、渗压）- 一条SQL搞定
SELECT 
  'water_level' as data_type,
  st_code,
  rz as value,
  tm as time
FROM st_rsvr_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
UNION ALL
SELECT 
  'rainfall' as data_type,
  st_code,
  p as value,
  tm as time
FROM st_pptn_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY data_type, time DESC;
```

#### 一次性获取告警+规则
```sql
-- 获取告警及其规则配置 - 一条SQL搞定
SELECT 
  im.id, im.ew_name, im.st_code, im.ew_type, im.level_r, 
  im.value, im.gather_time, im.message_confirm,
  er.name as rule_name, er.extend as rule_config
FROM ew_info_message im
LEFT JOIN ew_info_rules er ON im.ew_rules_id = er.id
WHERE im.deleted = 0 AND im.message_confirm = 0
ORDER BY im.level_r ASC, im.gather_time DESC
LIMIT 50;
```

### 查询策略

| 场景 | 推荐策略 | 避免 |
|------|---------|------|
| 告警概况 | 用GROUP BY一次性统计 | 逐条查询告警 |
| 水位趋势 | 查询最近6小时数据 | 查询所有历史数据 |
| 跨域关联 | 用UNION ALL合并查询 | 分别查询再合并 |
| 告警详情 | 查询top 5-10条 | 查询所有告警 |
| 规则配置 | 查询启用的规则 | 查询所有规则 |

### 性能要求（必须遵守）

**所有查询必须包含以下两项：**

1. **时间范围限制**: 使用 `WHERE tm >= DATE_SUB(NOW(), INTERVAL X HOUR/DAY)`
2. **分页限制**: 使用 `LIMIT N`（告警列表LIMIT 50，统计类可省略）

**示例:**
```sql
-- ✅ 正确：有时间范围和分页
SELECT * FROM ew_info_message 
WHERE deleted = 0 AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY gather_time DESC LIMIT 50;

-- ❌ 错误：无时间范围和分页
SELECT * FROM ew_info_message WHERE deleted = 0;
```

## 告警类型

| 值 | 含义 | 值 | 含义 |
|----|------|----|------|
| 0 | 水位 | 12 | 设备离线 |
| 1 | 水质 | 20 | 渗压/流量 |
| 2 | 雨量 | 40 | 渗流/位移 |

## 告警级别

| 级别 | 含义 | 颜色 | 升级时限 |
|------|------|------|----------|
| 1 | 特别严重 | 红色 | 2h→L2, 4h→L3 |
| 2 | 严重 | 橙色 | 4h→L3, 8h→L4 |
| 3 | 较重 | 黄色 | 8h→L4, 24h→L5 |
| 4 | 一般 | 蓝色 | 24h→L5 |

## 字段规范

| 字段 | 说明 | 格式 | 示例 |
|------|------|------|------|
| id | 告警ID | bigint | 14898 |
| ew_name | 告警名称 | varchar(255) | 低水位预警 |
| st_code | 测站编码 | varchar(255) | 606K2155 |
| eq_code | 设备编码 | varchar(255) | 606K215502 |
| ew_type | 告警类型 | char(2) | 0=水位, 2=雨量 |
| level_r | 告警级别 | char(2) | 1=红, 2=橙, 3=黄, 4=蓝 |
| value | 告警值 | varchar(255) | 456.5 |
| gather_time | 采集时间 | datetime | 2026-05-28 16:37:04 |
| message_confirm | 确认状态 | bit(1) | 0=未确认, 1=已确认 |
| ew_rules_id | 规则ID | bigint | 230 |
| create_time | 创建时间 | datetime | 2026-05-28 16:37:04 |
| deleted | 删除标记 | bit(1) | 0=正常, 1=已删除 |
| tenant_id | 租户ID | bigint | 18 |

## 气象预警表

| 字段 | 说明 | 格式 | 示例 |
|------|------|------|------|
| docid | 预警ID | varchar | 12345 |
| docabstract | 预警摘要 | text | 暴雨蓝色预警 |
| chnlname | 频道名称 | varchar | 气象预警 |
| model_type | 预警类型 | varchar | 暴雨 |
| docpubtime | 发布时间 | datetime | 2026-06-09 10:00:00 |
| docpuburl | 原文链接 | varchar | http://... |
| warn_status | 状态 | int | 1=有效, 0=无效 |

## 业务规则

### NULL值处理
- 告警值为NULL表示：设备故障、数据传输异常、或非数值型告警（如断面预警）
- 断面预警（ew_type=5）通常无具体值，基于多点综合判断
- **查询时说明**：当查询结果包含NULL值时，需要解释NULL的含义
- **断面预警说明**：断面预警是大坝安全监测的一部分，监测的是断面变形或位移，通常无单一数值，基于多点综合判断

### 阈值匹配
- 告警值与阈值不匹配时，可能是：规则配置错误、数据单位不一致、或数据采集异常
- 需要对比历史数据和规则配置进行分析
- **查询时说明**：当告警值与阈值不匹配时，需要分析可能原因
- **常见原因**：
  - 规则配置错误：阈值设置不合理
  - 数据单位不一致：如0.9可能是m³/s，阈值80可能是L/s
  - 数据采集异常：传感器故障或数据传输问题

### 升级判断
- 升级条件：告警持续时间超过阈值 + 告警值仍在预警范围
- 不升级条件：告警已恢复、告警已确认处理、告警值已回落
- **判断逻辑**：当前值 < 一级阈值 → 不会升级
- **查询时说明**：需要查询当前值和一级阈值进行对比

### 阈值合理性
- 分析方法：对比历史数据的最小值、最大值、平均值
- 合理范围：阈值应在历史数据的95%分位数附近
- **查询时说明**：需要查询历史数据进行对比分析
- **渗流预警说明**：渗流预警分为一级（>=30）和二级（15-30），当前值在二级范围内不会升级

## 告警处理检查清单

### 处理前
- [ ] 确认告警真实性
- [ ] 检查告警级别
- [ ] 查看告警详情
- [ ] 检查关联告警
- [ ] 查看历史案例

### 处理中
- [ ] 按照处理流程执行
- [ ] 记录处理过程
- [ ] 通知相关人员
- [ ] 更新告警状态
- [ ] 保存处理证据

### 处理后
- [ ] 确认告警恢复
- [ ] 记录处理结果
- [ ] 生成复盘报告
- [ ] 更新知识库
- [ ] 归档处理记录

## 告警报告模板

### 日报模板

```markdown
# 告警日报

## 一、报告摘要
- 报告时间：YYYY-MM-DD
- 告警总数：X条
- 主要告警：XXX
- 处理情况：已处理X条，未处理X条

## 二、告警统计
| 级别 | 数量 | 占比 |
|------|------|------|
| L1(红色) | X | X% |
| L2(橙色) | X | X% |
| L3(黄色) | X | X% |
| L4(蓝色) | X | X% |

## 三、告警分析
- 主要告警类型：XXX
- 告警趋势：XXX
- 关联分析：XXX

## 四、处理建议
| 告警 | 建议 | 负责人 |
|------|------|--------|
| XXX | XXX | XXX |

## 五、待确认事项
- XXX

## 六、风险提示
- XXX
```

### 周报模板

```markdown
# 告警周报

## 一、报告摘要
- 报告周期：YYYY-MM-DD ~ YYYY-MM-DD
- 告警总数：X条
- 与上周对比：+/-X%
- 主要变化：XXX

## 二、告警趋势
| 日期 | 告警数 | 环比 |
|------|--------|------|
| 周一 | X | +/-X% |
| 周二 | X | +/-X% |
| ... | ... | ... |

## 三、测站排名
| 测站 | 告警数 | 主要类型 |
|------|--------|----------|
| XXX | X | XXX |
| XXX | X | XXX |

## 四、处理效率
- 平均确认时间：X分钟
- 平均处理时间：X小时
- 确认率：X%
- 处理率：X%

## 五、问题与建议
- XXX
```

## 告警复盘模板

```markdown
# 告警复盘报告

## 一、告警概况
- 告警ID：XXX
- 告警名称：XXX
- 告警级别：XXX
- 触发时间：XXX
- 恢复时间：XXX

## 二、处理过程
| 时间 | 操作 | 操作人 | 结果 |
|------|------|--------|------|
| XXX | XXX | XXX | XXX |

## 三、原因分析
- 直接原因：XXX
- 根本原因：XXX
- 关联因素：XXX

## 四、经验教训
- 做得好的：XXX
- 需要改进的：XXX
- 避免再次发生：XXX

## 五、改进措施
| 措施 | 负责人 | 截止时间 | 验证方式 |
|------|--------|----------|----------|
| XXX | XXX | XXX | XXX |

## 六、知识沉淀
- 更新知识库：XXX
- 优化规则：XXX
- 完善流程：XXX
```

## 多轮对话处理

### 上下文保持
- 记住用户之前提到的告警、测站、时间范围
- 在后续回答中引用之前的分析结果
- 支持"第一个告警"、"那个测站"等指代词

### HITL检查点交互
- **风险确认**：展示风险等级和依据，等待用户确认或调整
- **预案触发**：展示触发条件和建议，等待用户确认或取消
- 用户说"确认"→继续执行；说"调整为X"→修改后继续；说"暂不"→跳过

### 典型对话流程
```
用户：当前告警情况如何？
Agent：[执行智能分析] 当前有X条告警，风险等级为[高/中/低]...

用户：第一个告警详细说说
Agent：[针对第一个告警进行根因分析]

用户：怎么处理？
Agent：[给出处理建议]

用户：确认高风险
Agent：[继续执行，展示HITL检查点2]

用户：启动预案
Agent：[触发预案生成]
```

## 异常场景处理

### 无告警场景
- 返回"系统正常，当前无活跃告警"
- 不执行后续分析步骤
- 给出监控建议

### 数据缺失场景
- 标记"数据不完整"
- 降低预测置信度
- 基于已有数据继续分析

### 告警过多场景（>100条）
- 仅分析红色和橙色告警详情
- 其他级别汇总统计
- 在输出中说明截断情况

### 查询超时场景
- 跳过超时的查询
- 基于已有数据继续分析
- 在输出中标记超时

### 气象数据不可用
- 跳过气象预警查询
- 不影响核心分析
- 在输出中标记气象数据不可用

## 按需加载

详细内容请加载对应文件：

- 规则配置: `references/rule-config.md`
- 根因分析: `references/root-cause.md`
- 关联分析: `references/correlation.md`
- 预测预警: `references/prediction.md`
- 报告生成: `references/report.md`
- 应急响应: `references/emergency.md`
- 参数优化: `references/optimization.md`
- 模式识别: `references/pattern.md`
