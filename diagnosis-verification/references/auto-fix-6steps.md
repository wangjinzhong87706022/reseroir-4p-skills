# auto-fix（自动修复）— 6 步详细文档

## Step 1：解析诊断报告

### 目的
提取诊断结果中的关键信息。

### 输入
diagnose 输出的诊断报告

### 输出格式
```json
{
  "root_cause": "基础设施问题",
  "affected_files": ["query_forecast_data.py:78"],
  "fix_type": "short_term",
  "solution": "调整连接池配置 pool_size=2 → 10",
  "evidence": {
    "fact": "连接池 pool_size=2 过小",
    "reasoning": "高并发时连接耗尽",
    "conclusion": "基础设施问题"
  }
}
```

### 失败处理
- ❌ 若诊断报告不完整：停止，提示"诊断报告不完整，请重新诊断"
- ❌ 若根因分类不明确：停止，提示"根因分类不明确，请人工复核"

---

## Step 2：查询知识库

### 目的
先查是否有已知解决方案，避免重复造轮子。

### 知识库结构
```yaml
- problem_type: 水位数据超时
  root_cause: 基础设施问题
  evidence: "连接池 pool_size=2 过小"
  solution: "调整配置 pool_size=10"
  fix_time: "首次 48 分钟 → 有知识库 15 分钟"
  tags: [连接池, 超时, 基础设施]
  success_rate: 0.95
  last_used: "2026-07-09"
```

### 通过标准
- ✅ 匹配度 >80%：直接复用方案
- ⚠️ 匹配度 50-80%：参考方案，需调整
- ❌ 匹配度 <50%：无匹配，进入 Step 3

### 输出格式
```
【Step 2 完成】
- 知识库匹配：<有/无>
- 匹配度：<百分比>
- 解决方案：<方案内容>
- 历史成功率：<百分比>
- 预计修复时间：<X> 分钟（首次 <Y> 分钟）
```

### 价值
- 首次修复 48 分钟 → 有知识库后 15 分钟
- 同类问题不再从零开始

---

## Step 3：生成修复方案

### 目的
根据根因分类，生成具体修复方案。

### 6 类根因对应修复模式

#### 3.1 外部系统异常

**修复模式**：try-except + fallback + retry

```python
# 修复前
result = mcp_tool.call()

# 修复后
try:
    result = mcp_tool.call()
except Exception as e:
    logger.warning(f"MCP 调用失败：{e}，使用 fallback")
    result = fallback_strategy()
```

**检查清单**：
- [ ] 是否加了 try-except
- [ ] 是否有 fallback 策略
- [ ] 是否加了 retry 机制（最多 3 次）
- [ ] 是否记录了降级日志

---

#### 3.2 内部代码缺陷

**修复模式**：精确修改 file:line

```python
# 修复前
sql = "SELECT rz FROM st_rsvr_r WHERE stcd=240"  # ❌ 硬编码

# 修复后
master = get_master_stcd('st_rsvr_r_master')  # ✅ 从 config 读取
sql = f"SELECT rz FROM st_rsvr_r WHERE stcd={master}"
```

**检查清单**：
- [ ] 是否精确定位到 file:line
- [ ] 是否最小化改动
- [ ] 是否向后兼容
- [ ] 是否加了注释说明

---

#### 3.3 数据问题

**修复模式**：不修，转工单给 Owner

```markdown
# 修复方案
数据问题（用户数据异常、表不存在）不由本 Skill 修复。

## 工单内容
- 问题描述：<描述>
- 影响范围：<涉及的表/字段>
- 建议处理：<人工处理建议>
- 紧急程度：<P0/P1/P2>
```

---

#### 3.4 基础设施问题

**修复模式**：配置调整

```yaml
# 修复前
pool_size: 2

# 修复后
pool_size: 10
```

**常见配置修复**：
| 问题 | 修复方案 |
|------|---------|
| 连接池超时 | `pool_size: 2 → 10` |
| 查询慢 | 增加索引或加缓存 |
| 内存不足 | 调整 JVM 堆大小 |

---

#### 3.5 LLM/模型异常

**修复模式**：Prompt 约束 + schema 校验

```markdown
Prompt: """
查询水位数据，必须使用 query_forecast_data.py 脚本，
表名为 st_rsvr_r（水位表），tenant_id=18
禁止查询 st_pptn_r（河道站数据）
"""
```

---

#### 3.6 预期行为（误报）

**修复模式**：降级处理（合理降级，非掩盖故障）

```python
# ❌ 掩盖故障
logger.error("水位数据异常") → logger.warning("水位数据异常")

# ✅ 合理降级
try:
    data = query_realtime()
except TimeoutError:
    logger.warning(f"实时数据超时，降级使用历史数据")
    data = query_historical()
    log_degradation(source="realtime", fallback="historical")
```

**区分"掩盖"和"降级"**：
| 行为 | 类型 | 判断标准 |
|------|------|---------|
| 改日志级别，错误未解决 | ❌ 掩盖 | 错误还在但不再上报 |
| 降级 + 记录日志 | ✅ 合理降级 | 有 fallback，错误可追溯 |

---

## Step 4：生成修复补丁

### 目的
将修复方案转化为可执行的代码/配置变更。

### 输出格式
```diff
--- a/query_forecast_data.py
+++ b/query_forecast_data.py
@@ -75,7 +75,7 @@
 def query_current_water_level(tenant_id=DEFAULT_TENANT, **_):
-    master = get_master_stcd('st_rsvr_r_master', tenant_id)
+    master = get_master_stcd('st_rsvr_r_master', tenant_id) or '3'  # fallback
```

### 检查清单
- [ ] 补丁是否最小化
- [ ] 是否标注了改动原因
- [ ] 是否向后兼容
- [ ] 是否通过 lint（零 warning）

---

## Step 5：执行测试

### 目的
验证修复方案是否有效，不引入新问题。

### 测试层次

#### 5.1 单元测试
```bash
pytest tests/test_forecast_data.py -v
```
**通过标准**：所有测试通过

#### 5.2 集成测试
```bash
python3 scripts/query_forecast_data.py --type full_context
```
**通过标准**：数据返回正常（status=ok）

#### 5.3 回归测试
```bash
python3 scripts/query_forecast_data.py --type current_water_level
python3 scripts/query_forecast_data.py --type rainfall_forecast
```
**通过标准**：未影响其他功能

#### 5.4 性能检查
```bash
time python3 scripts/query_forecast_data.py --type full_context
```
**通过标准**：查询时间 < 5 秒

### 重试机制（最多 3 轮）

```
第 1 轮：执行修复 → 测试 → 通过 ✅
第 2 轮：测试失败 → 分析原因 → 调整方案 → 重测 → 通过 ✅
第 3 轮：测试失败 → 分析原因 → 调整方案 → 重测 → 通过 ✅
第 4 轮：测试失败 → 停止 → 升级人工 ❌
```

**触发停止的条件**：
- 连续 3 轮测试失败
- 改动范围超出预期
- 性能严重退化（> 10 秒）
- 引入新的 P0 问题

**停止后处理**：
1. 输出失败原因和已尝试方案
2. 推送钉钉工单给 Owner
3. 等待人工介入

---

## Step 6：提交并部署

### 目的
将修复方案提交到代码库，并部署到预发环境。

### 执行步骤

#### 6.1 创建分支
```bash
git checkout -b fix/<问题描述>_<日期>_<序号>
# 示例：fix/connection-pool-timeout_20260710_01
```

#### 6.2 提交代码
```bash
git add <改动文件>
git commit -m "fix: 修复连接池超时问题

- 调整 pool_size=2 → 10
- 增加连接池健康检查
- 关联问题：水位数据连续 3 小时未更新

Co-Authored-By: Claude <noreply@anthropic.com>"
```

#### 6.3 推送分支 + 创建 PR
```bash
git push origin fix/<问题描述>_<日期>_<序号>
gh pr create --title "fix: ..." --body "..." --base develop
```

#### 6.4 触发预发部署
```bash
gh workflow run pre-deploy.yml --ref <分支名>
```

#### 6.5 集成测试（预发环境）
```bash
python3 scripts/query_forecast_data.py --type full_context --env=staging
```

### 通过标准
- ✅ 预发环境数据返回正常
- ✅ 无新增 ERROR 日志
- ✅ Langfuse Trace 验证通过（ERROR observations=0）

---

## 修复方案模板库

### 模板 1：外部系统异常
详见 SKILL.md 第三节 3.1

### 模板 2：内部代码缺陷
详见 SKILL.md 第三节 3.2

### 模板 3：基础设施问题
详见 SKILL.md 第三节 3.4

### 模板 4：LLM/模型异常
详见 SKILL.md 第三节 3.5

### 模板 5：预期行为（误报）
详见 SKILL.md 第三节 3.6

### 模板 6：告警规则过敏感
详见 SKILL.md 第三节修复模板
