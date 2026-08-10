---
name: plan-generation
description: "水库调度预案智能生成：防汛形势评估、汛情研判、水情数据分析、调度预案生成、方案对比推荐、历史预案查询、调度决策。"
version: 3.2.1
author: SmartTwinRes Team
license: MIT
platforms: [linux, windows, macos]
metadata:
  hermes:
    tags: [water-conservancy, plan, dispatch, reservoir, scheduling]
    related_skills: []
  reservoir:                  # 水库身份（多水库可插拔）：由 SRM_RESERVOIR_NAME 激活对应 profile
    default: sancha
    env: SRM_RESERVOIR_NAME
prerequisites:
  env_vars: [SRM_DB_HOST, SRM_DB_PORT, SRM_DB_NAME, SRM_DB_USER, SRM_DB_PASSWORD, SRM_TENANT_ID, SRM_RESERVOIR_NAME]
---

# 水库调度预案智能生成 Skill v3.2

## ⛔ 标准导入片段（生成查询代码时照抄，禁手写 pymysql.connect / 硬编码密码）

> ⚠️ `__file__` 在 Hermes 暂存脚本里不可靠，**必须**用 `SRM_SKILLS_ROOT` 环境变量定位共享层。

```python
# 标准导入片段（照抄）
import os, sys
sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

离线脚本（`scripts/` 下，`__file__` 可靠）：

```python
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/x.py → 根
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))
from db import execute_query, execute_query_list, unpack
from tenant import current_tenant_id
```

> 共享资源：`$SRM_SKILLS_ROOT/lib/db.py`、`$SRM_SKILLS_ROOT/shared/sql-safety-rules.md`、`$SRM_SKILLS_ROOT/shared/tenant-filtering-rules.md`。

> **⚠️ 数据源优先级（必须遵守）**：当本 skill 与 water-situation / water-warning / rainfall 等 skill 同时加载时，当前水库的所有水情、汛限、配置、历史数据**必须从本 skill 的 `scripts/query_plan_data.py` 获取**（查询调度数据库，按 `SRM_TENANT_ID` 隔离）。**禁止**使用其他 skill 的数据源——它们查询的是区域河道站数据，不适用于本水库调度决策。

> **🏛️ 水库身份感知（多水库必读）**：本 skill 通过环境变量 `SRM_RESERVOIR_NAME`（默认 `sancha`）适配不同水库。**凡涉及具体水位/汛限/特征水位/曲线/站码/下游参数前，先读 reservoir profile**：
> - profile 目录：`reservoirs/${SRM_RESERVOIR_NAME:-sancha}/`
> - 桃曲坡（`SRM_RESERVOIR_NAME=taoqupo`）：汛限 786.80m(主汛)/788.00m(次汛)、正常蓄水位 788.5m、设计洪水位 788.54m、校核洪水位 790.5m、死水位 755m、下游安全泄量 500m³/s
> - 三岔（`SRM_RESERVOIR_NAME=sancha`）：见 `reservoirs/sancha/`（或运行时从 model_config 动态读取）
> - 详见各 profile 的 `identity.md` / `characteristic-levels.md` / `curve-data.md`
> - **禁止**照抄本 skill 示例里的具体数字——那些只是某个水库的取值，必须以当前 profile 为准。

## ⛔ 输出蓝图（开始分析前先规划这3段，分析后逐段填充）

**无论什么任务，最终回答都必须包含这3段（按顺序），结尾段是回答合格的硬性标志：**

1. **【依据】**（开头）— 引出本次决策的法规/规则框架：
   `依据《防洪法》第41条和调度规则，对[本任务]分析如下：`

2. **【分析】**（中间）— 任务核心内容（见下方分类型填充表）

3. **【校验与依据】**（结尾，必填模板，**必须是回答的绝对最后内容**）：
   ```
   【安全校验】最高水位 XXm，距汛限水位 {flood_limit_level}m 还有 Ym，[未超限/超限]；最大下泄 XX m³/s，[低于/超过]下游安全泄量 {safe_drainage_capacity} m³/s。
   【法规依据】依据《防洪法》第41条，[安全要求]；依据调度规则，[合规结论]（或依据 GB 17621-1998 / SL 224-2019）。
   ```

> ⛔ **参数取值规则**：汛限水位、安全泄量等约束值**直接从你已拿到的 `full_context`/`config` 返回 JSON 里读对应字段填入**（如 `{flood_limit_level}`），不要照抄本 skill 示例里的具体数字（那些只是三岔取值）。安全校验是**纯文字填写**，**绝不为它另写 Python/execute_code**（多余代码会拖慢甚至卡死回答）。

> ⛔ **结尾段优先**：无论前面查询/计算多繁重、报告是否存盘，**【校验与依据】必须是回答最后内容**。篇幅紧张就精简分析段保结尾段——结尾段缺失=整题不合格（E2/E4 双失）。

### 各任务类型的【分析】段内容

| 任务类型 | 第2段【分析】应包含 | 第3段引用侧重 |
|---------|-------------------|--------------|
| 预案生成 | 形势研判 + 3组方案（A防洪/B综合/C兴利）+ 各方案参数 + 风险提示 | 调度规则 + 《防洪法》 |
| 预案解读 | 预案参数 + 调度过程 + 效果指标 + 风险 | 调度规则 + GB 17621-1998 |
| 形势研判 | 当前水情 + 预报 + 历史对比 + 风险等级 | 《防洪法》 + SL 224-2019 |
| 调度决策 | 方案对比 + 推荐理由 + 安全余量 | 调度规则 |
| 应急处置 | 险情描述 + 处置措施 + 资源调度 | 《防汛条例》 + 应急预案 |
| 实况/知识问答 | 直接回答（数据/规则） | 简短即可，但仍需结尾安全校验若涉及水位 |

> 💡 **工作流**：先写第1段 → 做完整分析填第2段 → **必须**写第3段。即使第2段是"无数据""数据异常""纯知识问答"，只要涉及水位/调度，第3段也不能省。

**法规/标准库（填第1/3段时复制使用）：**
- 《防洪法》第41条 — 水库调度应确保大坝安全
- 《水库大坝安全管理条例》 — 下游防护、安全泄量
- 《防汛条例》 — 防汛调度、应急处置
- GB 17621-1998 — 水库洪水调度规范
- SL 224-2019 — 洪水调度规范（升级版）
- 调度规则 — 防洪优先/综合平衡/兴利保供的选择条件（见下方"调度规则速查"）

## 第一步 — 判断场景（决策路由）

根据用户意图选择场景和查询策略：

| 用户意图 | 场景分类 | 查询策略 | 知识参考 |
|---------|---------|---------|---------|
| 当前水情怎么样 | 实况查询 | 快捷路径：full_context | 无需 |
| 生成一个调度预案 | 预案生成 | 快捷路径：full_context + 模型计算 | dispatch-rules.md |
| 解读预案 #717 | 预案解读 | 场景脚本：plan_detail --plan-id 717 | 无需 |
| 对比今年和去年预案效果 | 定制分析 | 灵活路径：自定义 SQL | sql-templates.md |
| 2024年7月那次洪水情况 | 历史回溯 | 灵活路径：按时间范围查 | table-schema.md |
| 闸门故障怎么办 | 应急处置 | 不查库，直接读知识 | emergency-response.md |
| 调度模式5是什么 | 知识问答 | 不查库，直接读知识 | dispatch-rules.md |
| 红色预警该怎么做 | 应急处置 | 快捷路径 + 知识 | emergency-response.md |
| 当前形势如何、本水库汛情 | 形势研判 | 快捷路径：full_context + historical_plans + similar_plans | knowledge-base.md + reservoir profile |
| 应选防洪优先还是综合平衡 | 调度决策 | 快捷路径：full_context + historical_plans + similar_plans + 知识参考 | dispatch-rules.md |

## 第二步 — 执行查询

> **执行前必读**：脚本依赖 `pymysql` 和 `dbutils`，环境中已预装。直接用 `python3` 运行脚本，**不要**先用 `import sys` 或 `import pymysql` 测试环境——每次会话会浪费 3-6 次 exec 调用。

### 快捷路径（强烈推荐优先）

```bash
# 强烈推荐：一次获取所有需要的数据（水位+预报+汛限+配置+历史预案+历史洪水+场景模板）
python3 scripts/query_plan_data.py --type full_context

> **full_context 优先原则**：除非用户需求明确需要自定义 SQL（如跨年对比、趋势分析），否则一律使用 `full_context` 一次取全，避免多次查询。

# 灵活参数示例：
python3 scripts/query_plan_data.py --type historical_plans --limit 10 --start-date 2024-06-01 --end-date 2024-09-01
python3 scripts/query_plan_data.py --type similar_plans --water-level 459.18 --limit 3
python3 scripts/query_plan_data.py --type historical_floods --status 2 --keyword "暴雨"
```

### 场景脚本（高效单任务）

```bash
python3 scripts/query_plan_analysis.py --type plan_detail --plan-id 717
python3 scripts/query_plan_analysis.py --type scheme_context
python3 scripts/query_plan_analysis.py --type similar_plans --water-level 459.18
python3 scripts/query_plan_analysis.py --type full_analysis --plan-id 717
```

### 灵活路径（自定义 SQL）

三步流程：

1. 先读 `${HERMES_SKILL_DIR}/references/table-schema.md` 了解表结构
2. 参考 `${HERMES_SKILL_DIR}/references/sql-templates.md` 选择参数化模板
3. 替换 `{参数}` 为实际值后执行

## 第三步 — SQL 安全规则（灵活路径必须遵守）

1. 数据提取查询（SELECT 返回多行）必须加 `LIMIT`，最大不超过 1000
2. 大表的数据提取查询必须加时间范围。具体每张表的量级参考 `table-schema.md` 的数据量级列（⚠️ 标记的为大表）
3. 统计/聚合查询（COUNT, SUM, AVG, MAX, MIN）按意图区分：
   - 用户意图明确是"全量统计"（如"水位为NULL的记录总共有多少"）→ 不加时间范围，直接执行
   - 用户提到时间范围（如"今年的"、"最近一个月的"）→ 按用户指定的范围过滤
   - 意图不明确 → 先确认："您要统计全量数据还是某个时间段？"
4. 所有表必须加 `deleted = 0`（如果表有此字段）
5. 禁止 `SELECT *`，明确列出需要的字段
6. 禁止 `UPDATE / DELETE / INSERT`，只读查询
7. 不确定是否为大表时，默认加时间范围（保守策略）

## 查询策略指引（按场景细化）

| 场景 | 数据范围 | 时间窗口 | 推荐路径 |
|------|---------|---------|---------|
| 预案生成 | 当前水位 + 未来48h预报 + 汛限 + 配置 + 最近5条历史预案 | 不需要历史数据 | 快捷路径：full_context |
| 预案解读 | 指定预案详情 + 该时段实测水位 | 预案的 start_time ~ end_time | 场景脚本：plan_detail |
| 历史对比分析 | 用户指定时间段内的预案/洪水/水位数据 | 由用户问题决定（可能跨年） | 灵活路径 |
| 趋势分析 | 水位/降雨的时间序列 | 通常 24h~7d | 灵活路径 |
| 应急处置 | 当前实况 + 活跃预警 | 只看当前 | 快捷路径 + 知识文件 |
| 形势研判 | full_context + 历史预案 + 相似预案 | 最近365天 | 快捷路径：full_context + 追加查询 |
| 调度决策 | full_context + 知识参考 + 历史预案 | 不限 | 快捷路径：full_context + 知识文件 |

### 水库范围限定（重要）

> 所有查询默认针对**三岔水库**，不要查询全区域数据。

- 水位数据：`st_rsvr_r` 主测站从 `model_config` 的 `st_rsvr_r_master` 键获取
- 配置数据：优先过滤 `tenant_id = 18`（三岔水库所在租户）
- 雨量数据：`st_pptn_r` 主测站从 `model_config` 的 `st_pptn_r_master` 键获取
- 历史预案/洪水：已由脚本按 tenant_id 过滤，灵活路径自定义 SQL **必须**补 `tenant_id=%s`

## 数据库

```bash
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME"
```

**核心表**: st_rsvr_r(水情), att_res_flse_lim(汛限), model_config(配置), model_result_files(历史预案), srm_flood_history_base(历史洪水)

---

## 调度规则（速查）

> 📖 **详细规则**：`${HERMES_SKILL_DIR}/references/dispatch-rules.md`

### 调度目标选择

| 条件 | 调度目标 | schedulingTarget |
|------|---------|-----------------|
| 当前水位 > 汛限水位 - 2m | 防洪优先 | 0 |
| 当前水位 < 死水位 + 3m | 兴利保供 | 1 |
| 水位适中 | 综合平衡 | 2 |

### 调度模式选择

| 调度目标 | 推荐模式 | schedulingModel | 说明 |
|---------|---------|-----------------|------|
| 防洪优先 | 控制最高水位 | 0 | 确保水位不超过上限 |
| 防洪优先 | 控制最大出库 | 3 | 当下游有防洪要求时 |
| 兴利保供 | 控制最低水位 | 1 | 确保水位不低于下限 |
| 兴利保供 | 控制最小出库 | 4 | 当需要保证供水时 |
| 综合平衡 | 控制水位范围 | 2 | 水位在指定范围内波动 |
| 综合平衡 | 控制出库流量范围 | 5 | 流量在指定范围内 |

### 目标水位确定

| 场景 | 目标水位 | 说明 |
|------|---------|------|
| 防洪优先 | 汛限水位 - 安全余量 | 黄色预警-0.5m，橙色-1.0m，红色-2.0m |
| 兴利保供 | min(正常蓄水位, 当前水位+需求) | 根据供水需求确定 |
| 综合平衡 | (汛限+死水位)/2 或 当前水位 | 维持中间水位 |

### 调度时长选择

| 降雨条件 | 调度时长 |
|---------|---------|
| 短时强降雨（<6h） | 6h |
| 一般降雨（6-24h） | 24h |
| 持续降雨（24-48h） | 48h |
| 长历时降雨（>48h） | 72h |

---

## 安全约束（不可违反）

> 📖 **法规依据**：`${HERMES_SKILL_DIR}/references/knowledge-base.md`

- 最高允许水位 ≤ 汛限水位（《防洪法》第41条）
- 下泄流量 ≤ 下游安全泄量（《水库大坝安全管理条例》）
- 起调水位 > 目标水位（水量平衡约束）
- 推荐参数必须来自实际查询数据，不能编造

## 引用规范

回答涉及法规、标准、技术要求时，**必须**注明出处：

| 引用类型 | 格式 | 示例 |
|---------|------|------|
| 法律法规 | 《名称》第X条 | "依据《防洪法》第41条" |
| 国家标准 | 标准号 | "依据 GB 17621-1998" |
| 行业标准 | 标准号 | "依据 SL 224-2019" |
| 调度规则 | "根据调度规则" | "根据调度规则，当前水位超汛限-2m应选防洪优先" |

**禁止**：做出技术判断时不引用任何依据。

---

## 应急响应规则（速查）

> 📖 **完整流程**：`${HERMES_SKILL_DIR}/references/emergency-response.md`

### 水位超汛限
- 立即加大泄洪，全力降低水位
- 通知防汛值班人员
- 加密水位监测频率（每15分钟一次）

### 暴雨红色预警
- 提前预泄，降低水位至汛限以下2m
- 加密监测频率（每30分钟）
- 通知所有防汛责任人到岗

### 设备故障
- 确认故障设备数量和位置
- 评估剩余泄洪能力
- 调整调度方案，使用可用设备

### 下游险情（管涌/漫堤）
- 立即减少下泄流量
- 下泄流量 ≤ min(安全泄量×50%, 入库流量×50%)
- 密切关注水库水位变化

---

## 多方案生成

每次生成预案时，**必须生成 3 组方案**：

- **方案A：防洪优先**（schedulingTarget=0）— 适合暴雨、高水位
- **方案B：综合平衡**（schedulingTarget=2）— 适合常规条件
- **方案C：兴利保供**（schedulingTarget=1）— 适合干旱、低水位

每组方案包含：调度目标、调度模式、最高/最低允许水位、最大下泄、安全泄量、调度时长。

**每个方案必须包含风险提示**：水位安全余量、是否超汛限、主要风险。

---

## 预案解读（高效查询）

当用户要求解读某个预案时，使用以下 SQL 一次性获取所有需要的数据：

```sql
-- 获取预案参数 + 调度数据（一条 SQL）
SELECT 
  m.alias, m.target_water_level, m.adjusted_water_level, m.start_time, m.end_time, m.extend,
  d.tm, d.dispatch_opening, d.gate_opening_flow
FROM model_result_files m
LEFT JOIN dispatch_history d ON m.taskid = d.task_id
WHERE m.id = {预案ID} AND m.type = 2
ORDER BY d.tm;
```

基于查询结果，分析：
- 起调水位 vs 目标水位
- 闸门开度变化趋势
- 下泄流量变化
- 是否符合调度目标

## 数据缺失处理

| 数据缺失 | 处理方式 |
|---------|---------|
| 水位为 NULL | 提示"当前水位数据不可用" |
| 降雨预报为空 | 使用历史平均降雨量参考 |
| 历史预案为空 | 跳过历史参考，用配置中心参数 |
| 汛限水位为空 | 使用 att_res_base 的 fl_low_lim_lev |

---

## API 模式（可选）

如需调用后端 REST API 触发实际计算：

```bash
export API_BASE=http://127.0.0.1:48080/admin-api

# 执行调度计算
curl -X POST "$API_BASE/model/dispatch/cal" \
  -H "Content-Type: application/json" \
  -d '{
    "startTime": "2026-06-05 08:00:00",
    "tmSpan": 48,
    "adjustedWaterLevel": 338.5,
    "save": false,
    "dispatchRequestExtendVO": {
      "schedulingTarget": "0",
      "schedulingModel": "0",
      "maxWaterLevel": 462.88,
      "minWaterLevel": 451.0,
      "maxDrainageCapacity": 192,
      "safeDrainageCapacity": 95.1
    }
  }'
```

---

## 知识库文件索引

当需要深入分析时，请读取对应文件：

| 文件路径 | 内容 | 何时读取 |
|---------|------|---------|
| `${HERMES_SKILL_DIR}/references/table-schema.md` | 14张表的字段、量级、索引、安全规则 | 自己写 SQL 前、不确定字段名时 |
| `${HERMES_SKILL_DIR}/references/sql-templates.md` | 19个参数化 SQL 查询模板 | 需要灵活查询、模板查询时 |
| `${HERMES_SKILL_DIR}/references/dispatch-rules.md` | 完整调度规则、参数选择逻辑 | 用户问"调度模式5是什么" |
| `${HERMES_SKILL_DIR}/references/emergency-response.md` | 完整应急响应措施 | 用户问"闸门故障怎么办" |
| `${HERMES_SKILL_DIR}/references/knowledge-base.md` | 国标(GB)、行标(SL)、法律法规 | 用户问"SL 224 具体条款" |
| `${HERMES_SKILL_DIR}/references/INDEX.md` | 知识库索引表 | 不确定读哪个文件时 |
| `${HERMES_SKILL_DIR}/references/sql-queries.md` | ⚠️ 已废弃，用 sql-templates.md | 不推荐 |
