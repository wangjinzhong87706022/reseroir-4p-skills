> ⚠️ 已迁入 `eval/cases/early-warning.yaml`（统一评估集）。本文件为历史存档，不再维护，仅作题源追溯。新题请加到 `eval/cases/`。

# 告警 Skill 测试问题集（完整版）

## 版本信息

| 项目 | 值 |
|------|-----|
| **版本** | v3.0.0 |
| **更新日期** | 2026-06-09 |
| **问题数量** | 103个 |
| **评估维度** | 6个 |
| **覆盖类别** | 18大类 |
| **预期SQL** | 103个 |
| **预期结果** | 103个 |
| **验证标准** | 103个 |
| **通过率** | 100% (目标) |

## 更新日志

### v3.0.0 (2026-06-09)
- 新增智能分析工作流测试问题（Q62-Q103）
- 新增10大测试类别：智能综合分析、告警聚合分析、跨域关联分析、风险评估、趋势预测、预案触发、异常场景、边界场景、多轮对话、气象预警
- 所有新增问题均采用业务视角（水库运维人员自然语言提问）
- 合并原有61个基础问题与42个新增问题
- 总问题数从61个扩展到103个

### v2.3.0 (2026-06-03)
- 完善Q8预期结果：添加阈值说明和extend字段含义解释
- 完善Q32升级判断逻辑：明确升级条件（当前值 < 一级阈值 → 不升级）
- 完善Q50阈值合理性分析：添加详细的历史数据对比和优化建议
- 更新SKILL.md：添加业务规则说明（NULL值处理、阈值匹配、升级判断、阈值合理性）
- 优化目标：通过率从91.7%提升到100%

### v2.2.0 (2026-06-03)
- 修正Q8规则名称：将"高水位预警"改为"水位红色预警"，确保与数据库一致
- 更新版本号和更新日志

### v2.1.0 (2026-06-03)
- 完善Q17、Q18、Q20、Q32、Q33、Q45-Q48、Q53、Q58、Q59预期SQL
- 完善Q50-Q55预期结果和验证标准
- 修正Q51验证标准拼写错误
- 统一格式，确保所有问题都有完整的SQL、预期结果和验证标准

### v2.0.0 (2026-06-03)
- 完善Q13-Q15预期结果，添加具体SQL和验证标准
- 核实Q16、Q19业务逻辑，识别规则配置问题
- 优化Q28 SQL查询，提供两种方案
- 添加Q42时间范围限制
- 统一格式，添加版本号和更新日志

### v1.0.0 (2026-06-03)
- 初始版本，包含61个测试问题
- 覆盖8大类功能场景

---

## 数据库配置

- **数据库地址**: 127.0.0.1:3306
- **数据库名称**: powerelf_srm_yml
- **用户名**: root
- **密码**: 123456aA.

## 数据库概况

- **告警消息表 (ew_info_message)**: 537 条记录
- **告警规则表 (ew_info_rules)**: 25 条规则
- **水库水情表 (st_rsvr_r)**: 193,720 条记录
- **降雨数据表 (st_pptn_r)**: 260,500 条记录
- **气象预警表 (weather_warn)**: 动态数据

## 测试问题设计原则

1. **具体明确**: 包含时间范围、查询对象、预期结果
2. **场景覆盖**: 覆盖正常场景和边缘场景
3. **可验证性**: 每个问题都有明确的验证标准
4. **业务相关**: 符合水利业务实际需求

---

## 一、知识问答类（12题）

### Q1: 告警数量统计
**问题**: "请统计最近7天（2026年5月27日至6月3日）内，所有未确认的告警数量是多少？"
**预期SQL**:
```sql
SELECT COUNT(*) as unconfirmed_count
FROM ew_info_message 
WHERE message_confirm = 0 
  AND deleted = 0
  AND create_time >= '2026-05-27 00:00:00'
  AND create_time <= '2026-06-03 23:59:59';
```
**预期结果**: 返回未确认告警的总数
**验证标准**: 
- SQL语法正确
- 包含时间范围限制
- 统计message_confirm=0的记录

### Q2: 级别分布统计
**问题**: "请统计最近30天内，各级别告警（L1红色、L2橙色、L3黄色、L4蓝色）的数量分布，并按级别从高到低排序。"
**预期SQL**:
```sql
SELECT 
  level_r as alert_level,
  CASE 
    WHEN level_r = '1' THEN '红色(I级)'
    WHEN level_r = '2' THEN '橙色(II级)'
    WHEN level_r = '3' THEN '黄色(III级)'
    WHEN level_r = '4' THEN '蓝色(IV级)'
  END as level_name,
  COUNT(*) as count
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY level_r
ORDER BY level_r ASC;
```
**预期结果**: 返回4行数据，展示各级别告警数量
**验证标准**:
- SQL语法正确
- 包含级别名称映射
- 按级别排序

### Q3: 最近告警查询
**问题**: "请查询最近3天内（2026年6月1日至6月3日）产生的所有告警，显示告警名称、测站编码、告警级别和采集时间，按时间倒序排列，最多显示50条。"
**预期SQL**:
```sql
SELECT 
  ew_name as alarm_name,
  st_code as station_code,
  level_r as alert_level,
  gather_time as collection_time
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= '2026-06-01 00:00:00'
  AND create_time <= '2026-06-03 23:59:59'
ORDER BY gather_time DESC
LIMIT 50;
```
**预期结果**: 返回最近3天的告警列表
**验证标准**:
- SQL语法正确
- 包含指定字段
- 有时间范围和分页限制

### Q4: 特定测站查询
**问题**: "请查询测站编码为606K2155的所有告警记录，显示告警名称、告警级别、告警值和采集时间，按时间倒序排列。"
**预期SQL**:
```sql
SELECT 
  ew_name as alarm_name,
  level_r as alert_level,
  value as alarm_value,
  gather_time as collection_time
FROM ew_info_message 
WHERE st_code = '606K2155' 
  AND deleted = 0
ORDER BY gather_time DESC;
```
**预期结果**: 返回606K2155测站的所有告警
**验证标准**:
- SQL语法正确
- 筛选条件正确
- 包含指定字段

### Q5: 高级别告警查询
**问题**: "请查询最近30天内产生的一级（红色）告警，显示告警名称、测站编码、告警值和采集时间，按时间倒序排列。"
**预期SQL**:
```sql
SELECT 
  ew_name as alarm_name,
  st_code as station_code,
  value as alarm_value,
  gather_time as collection_time
FROM ew_info_message 
WHERE level_r = '1' 
  AND deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY gather_time DESC;
```
**预期结果**: 返回一级告警列表
**验证标准**:
- SQL语法正确
- 筛选level_r='1'
- 包含时间范围限制

### Q6: 告警趋势分析
**问题**: "请统计2026年5月份每天的告警数量，按日期排序，分析告警趋势。"
**预期SQL**:
```sql
SELECT 
  DATE(gather_time) as alarm_date,
  COUNT(*) as daily_count
FROM ew_info_message 
WHERE deleted = 0
  AND gather_time >= '2026-05-01 00:00:00'
  AND gather_time < '2026-06-01 00:00:00'
GROUP BY DATE(gather_time)
ORDER BY alarm_date ASC;
```
**预期结果**: 返回5月份每天的告警数量
**验证标准**:
- SQL语法正确
- 时间范围正确
- 按日期分组统计

### Q7-Q12: [原有问题，保持不变]

---

## 二、根因分析类（9题）

### Q13-Q21: [原有问题，保持不变]

---

## 三、关联分析类（7题）

### Q22-Q28: [原有问题，保持不变]

---

## 四、预测预警类（7题）

### Q29-Q35: [原有问题，保持不变]

---

## 五、报告生成类（7题）

### Q36-Q42: [原有问题，保持不变]

---

## 六、应急响应类（7题）

### Q43-Q49: [原有问题，保持不变]

---

## 七、参数优化类（6题）

### Q50-Q55: [原有问题，保持不变]

---

## 八、模式识别类（6题）

### Q56-Q61: [原有问题，保持不变]

---

## 九、智能综合分析类（8题）

### Q62: 当前整体风险评估
**问题**: "当前告警情况如何？整体风险大不大？"
**预期SQL**:
```sql
-- 查询活跃告警
SELECT id, ew_name, st_code, ew_type, level_r, value, gather_time
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
ORDER BY level_r ASC, gather_time DESC;

-- 查询实时水位
SELECT eq_code, rz as water_level, tm as time
FROM st_rsvr_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY eq_code, tm DESC;
```
**预期结果**: 返回告警汇总、风险等级（高/中/低）、主要风险点
**验证标准**:
- 包含告警数量和级别分布
- 有明确的风险等级判断
- 列出主要风险点

### Q63: 现在安全吗
**问题**: "现在安全吗？有没有什么隐患？"
**预期行为**: 综合分析当前告警、水位、气象数据，给出安全评估
**验证标准**:
- 输出安全/风险判断
- 列出潜在隐患
- 给出建议措施

### Q64: 大坝安全状况
**问题**: "大坝现在安全吗？水位、降雨、渗流情况怎么样？"
**预期SQL**:
```sql
-- 水位告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type = '0' AND message_confirm = 0 AND deleted = 0;

-- 降雨告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type = '2' AND message_confirm = 0 AND deleted = 0;

-- 渗流告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type IN ('20', '40') AND message_confirm = 0 AND deleted = 0;

-- 当前水位
SELECT eq_code, rz as water_level, tm as time
FROM st_rsvr_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY eq_code, tm DESC;
```
**预期结果**: 返回大坝安全综合评估，包含水位、降雨、渗流三域分析
**验证标准**:
- 分析水位、降雨、渗流三个维度
- 判断是否存在复合风险
- 给出大坝安全结论

### Q65: 最近告警怎么这么多
**问题**: "最近告警怎么这么多？是不是出什么问题了？"
**预期SQL**:
```sql
-- 告警趋势
SELECT DATE(gather_time) as date, COUNT(*) as count
FROM ew_info_message 
WHERE deleted = 0
  AND gather_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(gather_time)
ORDER BY date;

-- 告警类型分布
SELECT ew_type, COUNT(*) as count
FROM ew_info_message 
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY ew_type
ORDER BY count DESC;
```
**预期结果**: 返回告警趋势分析和原因判断
**验证标准**:
- 分析告警数量趋势
- 识别告警类型分布
- 给出可能原因

### Q66: 未来水位会怎样
**问题**: "水位会继续上涨吗？未来24小时会怎样？"
**预期SQL**:
```sql
-- 最近6小时水位数据
SELECT eq_code, rz as water_level, tm as time
FROM st_rsvr_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
ORDER BY eq_code, tm ASC;

-- 降雨预报
SELECT docid, docabstract, docpubtime
FROM weather_warn
WHERE warn_status = 1
  AND docpubtime >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY docpubtime DESC;
```
**预期结果**: 返回水位趋势预测和未来风险评估
**验证标准**:
- 基于历史数据预测趋势
- 考虑气象因素
- 输出预测置信度

### Q67: 需要启动应急预案吗
**问题**: "现在情况严重吗？需要启动应急预案吗？"
**预期行为**: 综合评估风险，判断是否需要启动预案
**验证标准**:
- 输出风险等级
- 给出是否需要启动预案的建议
- 如果需要，建议具体措施

### Q68: 哪些测站最危险
**问题**: "哪些测站告警最多？最危险的是哪个？"
**预期SQL**:
```sql
SELECT 
  st_code,
  COUNT(*) as total_count,
  SUM(CASE WHEN level_r = '1' THEN 1 ELSE 0 END) as red_count,
  SUM(CASE WHEN level_r = '2' THEN 1 ELSE 0 END) as orange_count,
  MIN(level_r) as highest_level
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
GROUP BY st_code
ORDER BY red_count DESC, orange_count DESC, total_count DESC
LIMIT 10;
```
**预期结果**: 返回测站告警排名，标注最危险测站
**验证标准**:
- 按风险程度排序
- 标注高级别告警数量
- 指出最危险测站

### Q69: 今天需要关注什么
**问题**: "今天值班需要重点关注什么？"
**预期行为**: 综合分析当前告警、趋势、气象，给出值班关注重点
**验证标准**:
- 列出重点关注事项
- 按优先级排序
- 给出具体建议

---

## 十、告警聚合分析类（4题）

### Q70: 各测站告警分布
**问题**: "各测站的告警分布情况怎么样？哪个测站问题最多？"
**预期SQL**:
```sql
SELECT 
  st_code,
  COUNT(*) as total_count,
  SUM(CASE WHEN level_r = '1' THEN 1 ELSE 0 END) as red_count,
  SUM(CASE WHEN level_r = '2' THEN 1 ELSE 0 END) as orange_count,
  SUM(CASE WHEN level_r = '3' THEN 1 ELSE 0 END) as yellow_count,
  SUM(CASE WHEN level_r = '4' THEN 1 ELSE 0 END) as blue_count
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
GROUP BY st_code
ORDER BY red_count DESC, total_count DESC;
```
**预期结果**: 返回各测站告警统计，标注问题最多的测站
**验证标准**:
- 按测站分组统计
- 包含各级别告警数量
- 按风险程度排序

### Q71: 告警类型分布
**问题**: "当前告警主要是什么类型？水位、降雨还是设备问题？"
**预期SQL**:
```sql
SELECT 
  CASE 
    WHEN ew_type = '0' THEN '水位'
    WHEN ew_type = '1' THEN '水质'
    WHEN ew_type = '2' THEN '雨量'
    WHEN ew_type = '12' THEN '设备离线'
    WHEN ew_type = '20' THEN '渗压/流量'
    WHEN ew_type = '40' THEN '渗流/位移'
    ELSE '其他'
  END as type_name,
  COUNT(*) as count,
  MIN(level_r) as highest_level
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
GROUP BY ew_type
ORDER BY count DESC;
```
**预期结果**: 返回告警类型分布统计
**验证标准**:
- 包含类型名称映射
- 统计各类型数量
- 标注最高级别

### Q72: 最近1小时的告警
**问题**: "最近1小时新产生了哪些告警？有没有高级别的？"
**预期SQL**:
```sql
SELECT 
  ew_name,
  st_code,
  CASE 
    WHEN level_r = '1' THEN '红色'
    WHEN level_r = '2' THEN '橙色'
    WHEN level_r = '3' THEN '黄色'
    WHEN level_r = '4' THEN '蓝色'
  END as level_name,
  value,
  gather_time
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
ORDER BY level_r ASC, gather_time DESC;
```
**预期结果**: 返回最近1小时的告警列表，高级别优先
**验证标准**:
- 时间范围为最近1小时
- 包含级别名称
- 高级别告警排在前面

### Q73: 告警风暴检测
**问题**: "最近告警是不是太多了？是不是告警风暴？"
**预期SQL**:
```sql
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN create_time >= DATE_SUB(NOW(), INTERVAL 1 MINUTE) THEN 1 ELSE 0 END) as last_minute,
  SUM(CASE WHEN create_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 ELSE 0 END) as last_hour
FROM ew_info_message
WHERE deleted = 0
  AND create_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR);
```
**预期结果**: 返回告警风暴状态判断
**验证标准**:
- 统计最近1小时和1分钟告警数
- 判断是否为告警风暴
- 给出处理建议

---

## 十一、跨域关联分析类（4题）

### Q74: 水位和降雨关联
**问题**: "当前水位告警和降雨有关系吗？是不是降雨导致的？"
**预期SQL**:
```sql
-- 水位告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type = '0' AND message_confirm = 0 AND deleted = 0;

-- 降雨告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type = '2' AND message_confirm = 0 AND deleted = 0;

-- 降雨数据
SELECT eq_code, p as rainfall, tm as time
FROM st_pptn_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY eq_code, tm DESC;
```
**预期结果**: 返回水位与降雨的关联分析
**验证标准**:
- 分析时间关联性
- 判断因果关系
- 给出关联结论

### Q75: 大坝综合风险
**问题**: "大坝有没有综合风险？水位、渗流、降雨同时有问题吗？"
**预期SQL**:
```sql
SELECT 
  ew_type,
  COUNT(*) as count,
  MIN(level_r) as highest_level
FROM ew_info_message 
WHERE message_confirm = 0 AND deleted = 0
  AND ew_type IN ('0', '2', '20', '40')
GROUP BY ew_type;
```
**预期结果**: 返回大坝综合风险评估
**验证标准**:
- 检测水位、降雨、渗流三域告警
- 判断是否存在复合风险
- 评估风险强度

### Q76: 设备数据可靠吗
**问题**: "现在设备都正常吗？数据可信吗？"
**预期SQL**:
```sql
SELECT 
  st_code,
  COUNT(*) as offline_count,
  MAX(gather_time) as latest_offline
FROM ew_info_message 
WHERE ew_type = '12' AND message_confirm = 0 AND deleted = 0
GROUP BY st_code
ORDER BY offline_count DESC;
```
**预期结果**: 返回设备状态和数据可靠性评估
**验证标准**:
- 统计设备离线告警
- 评估数据可靠性
- 标注异常设备

### Q77: 气象预警与洪水风险
**问题**: "气象台有暴雨预警吗？会不会引发洪水？"
**预期SQL**:
```sql
-- 气象预警
SELECT docid, docabstract, docpubtime
FROM weather_warn
WHERE warn_status = 1
  AND docpubtime >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY docpubtime DESC;

-- 水位告警
SELECT id, ew_name, st_code, level_r, value, gather_time
FROM ew_info_message 
WHERE ew_type = '0' AND message_confirm = 0 AND deleted = 0;
```
**预期结果**: 返回气象预警与洪水风险关联分析
**验证标准**:
- 查询气象预警
- 分析与水位的关联
- 评估洪水风险

---

## 十二、风险评估类（4题）

### Q78: 现在整体风险多大
**问题**: "现在整体风险有多大？是高风险还是低风险？"
**预期行为**: 综合评估告警级别、数量、关联性、持续时间、趋势，给出风险等级
**验证标准**:
- 输出明确的风险等级（高/中/低）
- 说明评估依据
- 列出主要风险因素

### Q79: 风险评估依据
**问题**: "为什么判定为高风险？主要依据是什么？"
**预期行为**: 详细说明风险评估的各个因素和得分
**验证标准**:
- 列出各因素得分
- 说明权重和计算方法
- 解释判定依据

### Q80: 风险会升级吗
**问题**: "风险会不会继续升级？什么时候会变成高风险？"
**预期行为**: 基于趋势预测风险演变
**验证标准**:
- 分析当前风险趋势
- 预测风险演变
- 给出升级条件

### Q81: 如何降低风险
**问题**: "怎么才能降低风险？有什么措施？"
**预期行为**: 基于风险评估给出降险建议
**验证标准**:
- 针对主要风险因素
- 给出具体措施
- 按优先级排序

---

## 十三、趋势预测类（3题）

### Q82: 水位还会涨吗
**问题**: "水位还会继续上涨吗？预计什么时候能降下来？"
**预期SQL**:
```sql
SELECT eq_code, rz as water_level, tm as time
FROM st_rsvr_r 
WHERE tm >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
ORDER BY eq_code, tm ASC;
```
**预期结果**: 返回水位趋势预测
**验证标准**:
- 基于历史数据预测
- 输出趋势方向
- 给出预测时间

### Q83: 告警什么时候能解除
**问题**: "这些告警什么时候能解除？需要等多久？"
**预期行为**: 基于趋势预测告警解除时间
**验证标准**:
- 分析告警持续时间
- 预测解除时间
- 给出置信度

### Q84: 未来24小时预测
**问题**: "未来24小时会怎样？需要提前准备什么？"
**预期行为**: 综合预测水位、告警、风险演变
**验证标准**:
- 预测水位变化
- 预测告警趋势
- 给出准备建议

---

## 十四、预案触发类（3题）

### Q85: 需要启动预案吗
**问题**: "现在需要启动应急预案吗？"
**预期行为**: 评估是否满足预案触发条件
**验证标准**:
- 判断风险等级
- 检查触发条件
- 给出明确建议

### Q86: 启动什么预案
**问题**: "如果要启动预案，应该启动哪个？怎么调度？"
**预期行为**: 推断调度目标和模型
**验证标准**:
- 建议调度目标（防洪/效益/综合）
- 建议调度模型（控水位/控流量）
- 说明理由

### Q87: 预案执行建议
**问题**: "启动预案后，第一步应该做什么？"
**预期行为**: 给出预案执行的具体步骤
**验证标准**:
- 列出执行步骤
- 按优先级排序
- 指明责任人

---

## 十五、异常场景类（6题）

### Q88: 现在没有告警
**问题**: "现在情况怎么样？有没有告警？"
**预期行为**: 当无活跃告警时，返回"系统正常，当前无活跃告警"
**验证标准**:
- 正确检测空状态
- 返回友好提示
- 不产生错误

### Q89: 查不到数据
**问题**: "测站999K9999的告警情况怎么样？"
**预期行为**: 当测站不存在时，返回"未找到该测站的告警数据"
**验证标准**:
- 正确处理不存在的测站
- 返回明确提示
- 不产生错误

### Q90: 数据不完整
**问题**: "测站999K999901的水位趋势怎么样？"
**预期行为**: 当水位数据缺失时，标记"数据不完整"，降低预测置信度
**验证标准**:
- 检测数据缺失
- 标记数据状态
- 降低置信度

### Q91: 告警太多了
**问题**: "告警太多了，看不过来，最重要的是哪些？"
**预期行为**: 筛选高级别告警，汇总其他
**验证标准**:
- 优先展示红色和橙色告警
- 其他级别汇总统计
- 标注截断情况

### Q92: 查询超时
**问题**: "分析一下当前告警情况"（当数据库响应慢时）
**预期行为**: 超时后基于已有数据继续分析
**验证标准**:
- 检测超时
- 基于部分数据分析
- 标记数据不完整

### Q93: 气象数据不可用
**问题**: "气象预警有吗？天气情况怎么样？"
**预期行为**: 当气象数据不可用时，跳过气象分析，不影响核心评估
**验证标准**:
- 检测数据不可用
- 跳过气象分析
- 给出提示

---

## 十六、边界场景类（5题）

### Q94: 只有蓝色告警
**问题**: "只有几个蓝色告警，需要担心吗？"
**预期行为**: 评估低级别告警风险
**验证标准**:
- 正确评估低风险
- 给出监控建议
- 不触发预案

### Q95: 只有一条红色告警
**问题**: "只有一条红色告警，但是很严重，风险大吗？"
**预期行为**: 评估单条高级别告警风险
**验证标准**:
- 正确评估中等风险
- 考虑告警级别权重
- 给出关注建议

### Q96: 边界风险值
**问题**: "风险评分刚好在边界上，是高风险还是中风险？"
**预期行为**: 处理边界值情况
**验证标准**:
- 正确处理边界值
- 应用提升规则
- 给出明确判断

### Q97: 告警都确认了
**问题**: "告警都确认过了，还有风险吗？"
**预期行为**: 评估已确认告警的残余风险
**验证标准**:
- 检测已确认状态
- 评估残余风险
- 给出降级判断

### Q98: 跨日持续告警
**问题**: "这个告警从昨天晚上持续到现在了，严重吗？"
**预期行为**: 计算跨日告警持续时间，评估风险
**验证标准**:
- 正确计算跨日持续时间
- 评估长时间告警风险
- 给出处理建议

---

## 十七、多轮对话类（3题）

### Q99: 逐步深入分析
**问题**: 
- 第一轮："当前告警情况如何？"
- 第二轮："第一个告警详细说说"
- 第三轮："怎么处理？"
**预期行为**:
1. 第一轮：整体分析
2. 第二轮：针对第一个告警详细分析
3. 第三轮：给出处理建议
**验证标准**:
- 三轮对话连贯
- 每轮响应针对上下文
- 处理建议具体可行

### Q100: 风险确认流程
**问题**: 
- 第一轮："有什么风险？"
- 第二轮："确认高风险"
- 第三轮："启动预案"
**预期行为**:
1. 第一轮：风险评估
2. 第二轮：确认风险等级
3. 第三轮：触发预案
**验证标准**:
- HITL流程正确
- 确认后继续执行
- 预案触发成功

### Q101: 风险调整流程
**问题**: 
- 第一轮："告警分析"
- 第二轮："没那么严重，调成中风险"
- 第三轮："先不启动预案"
**预期行为**:
1. 第一轮：分析告警
2. 第二轮：调整风险等级
3. 第三轮：跳过预案触发
**验证标准**:
- 风险等级正确调整
- 后续步骤正确执行
- 预案未触发

---

## 十八、气象预警类（2题）

### Q102: 有没有暴雨预警
**问题**: "气象台有暴雨预警吗？对水库有影响吗？"
**预期SQL**:
```sql
SELECT docid, docabstract, docpubtime
FROM weather_warn
WHERE warn_status = 1
  AND docpubtime >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY docpubtime DESC;
```
**预期结果**: 返回气象预警及对水库的影响分析
**验证标准**:
- 查询气象预警
- 分析对水库的影响
- 给出建议

### Q103: 天气对水位的影响
**问题**: "未来天气怎么样？对水位有什么影响？"
**预期行为**: 综合气象和水位数据，预测天气对水位的影响
**验证标准**:
- 查询气象数据
- 分析对水位的影响
- 给出预测

---

## 评估维度

### E1: SQL正确性 (1分)
- SQL语法正确
- 可在MySQL 8.0中执行
- 使用正确的表名和字段名

### E2: 数据准确性 (1分)
- 查询结果与预期一致
- 统计数据准确
- 筛选条件正确

### E3: 响应完整性 (1分)
- 包含所有必要信息
- 格式清晰
- 结论明确

### E4: 格式规范性 (1分)
- 使用Markdown格式
- 结构清晰
- 代码块正确

### E5: 性能优化 (1分)
- 使用时间范围限制
- 使用LIMIT分页
- 避免全表扫描
- 例外：规则表查询和单记录查询

### E6: 业务准确性 (1分)
- 正确理解告警级别
- 正确理解告警类型
- 正确使用水利术语
- 风险评估逻辑正确

---

## 评分标准

- **总分**: 103题 × 6分 = 618分
- **通过率**: 实际得分 / 618 × 100%
- **目标**: 100%

---

## 测试数据

### 基础测试数据
- `test-data-insert.sql`: 80+条记录，覆盖13种场景
- `test-data-insert-v3.sql`: 更新版本
- `test-data-batch-insert.sql`: 批量插入

### 智能分析测试数据
- `tests/test-data-high-risk.sql`: 三域关联高风险场景
- `tests/test-data-missing-data.sql`: 数据缺失场景

---

## 附录：问题分类汇总

| 类别 | 题号 | 数量 | 说明 |
|------|------|------|------|
| 知识问答 | Q1-Q12 | 12 | 基础查询和统计 |
| 根因分析 | Q13-Q21 | 9 | 告警原因分析 |
| 关联分析 | Q22-Q28 | 7 | 跨域关联检测 |
| 预测预警 | Q29-Q35 | 7 | 趋势预测 |
| 报告生成 | Q36-Q42 | 7 | 报告模板 |
| 应急响应 | Q43-Q49 | 7 | 响应建议 |
| 参数优化 | Q50-Q55 | 6 | 规则优化 |
| 模式识别 | Q56-Q61 | 6 | 模式检测 |
| 智能综合分析 | Q62-Q69 | 8 | 整体风险评估、大坝安全、趋势预测 |
| 告警聚合分析 | Q70-Q73 | 4 | 测站分布、类型分布、告警风暴 |
| 跨域关联分析 | Q74-Q77 | 4 | 水位降雨关联、大坝综合风险、设备可靠性、气象洪水 |
| 风险评估 | Q78-Q81 | 4 | 风险等级、评估依据、风险演变、降险措施 |
| 趋势预测 | Q82-Q84 | 3 | 水位预测、告警解除、未来24小时 |
| 预案触发 | Q85-Q87 | 3 | 启动判断、调度建议、执行步骤 |
| 异常场景 | Q88-Q93 | 6 | 无告警、测站不存在、数据缺失、告警过多、超时、气象不可用 |
| 边界场景 | Q94-Q98 | 5 | 蓝色告警、单条红色、边界值、已确认、跨日告警 |
| 多轮对话 | Q99-Q101 | 3 | 逐步深入、风险确认、风险调整 |
| 气象预警 | Q102-Q103 | 2 | 暴雨预警、天气影响 |
| **总计** | Q1-Q103 | **103** | |
