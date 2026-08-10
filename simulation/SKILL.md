---
name: simulation
description: "水库预演AI增强：多方案对比预演、结果智能解读、虚拟场景构建、预演报告生成。支持SQL直连和Flask编排服务两种模式。"
version: 1.9.3
author: SmartTwinRes Team
license: MIT
platforms: [linux, windows, macos]
metadata:
  hermes:
    tags: [water-conservancy, simulation, rehearsal, flood, dispatch, analysis]
    related_skills: [plan-generation, early-warning]
  reservoir:
    default: sancha
    env: SRM_RESERVOIR_NAME
prerequisites:
  env_vars: [SRM_DB_HOST, SRM_DB_PORT, SRM_DB_NAME, SRM_DB_USER, SRM_DB_PASSWORD, SRM_TENANT_ID, SRM_RESERVOIR_NAME]
  services: [xaj-model:18081, dispatch-model:18082, routing-model:18083, orchestrator:18084]
---

# 水库预演 AI 增强 Skill v1.9.3（速查卡）

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

> **🏛️ 水库身份感知（多水库必读）**：本 skill 通过 `SRM_RESERVOIR_NAME`（默认 sancha）适配多水库。预演涉及的水位/汛限/曲线/泄量/调度参数**必须以当前 reservoir profile 为准**：`reservoirs/${SRM_RESERVOIR_NAME:-sancha}/`（characteristic-levels.md / curve-data.md）。模型计算所需水位-库容/泄流曲线应从该水库读取，禁止使用其他水库的兜底曲线（三岔 ~460m、桃曲坡 ~788m，基准不同）。

## ⛔ 输出蓝图（开始分析前先规划这3段，分析后逐段填充）

**无论什么问题，最终回答都必须包含这3段（按顺序）：**

1. **【依据】**（开头）— 引出分析的法规框架：
   `依据《防洪法》第41条和《${reservoir_profile}调度规程》，对[解读本任务]如下：`

2. **【分析】**（中间）— 任务核心内容（数据、解读、报告、对比等）

3. **【校验与依据】**（结尾，必填模板，**必须是回答的绝对最后内容**）：
   ```
   【安全校验】最高水位 XXm，距汛限水位 {flood_limit_level}m 还有 Ym，[未超限/超限]；最大下泄 XX m³/s，[低于/超过]下游安全泄量 {safe_drainage_capacity} m³/s。
   【法规依据】依据《防洪法》第41条，[安全要求]；依据GB 50201-2014《防洪标准》，[合规结论]。
   ```

> ⚠️ **顺序铁律**：如果回答里要提及"报告已保存到 /xxx.md"这类文件路径，**文件路径必须放在【校验与依据】段之前**，绝不能作为结尾。正确顺序：分析内容 → 文件路径（可选）→ **【校验与依据】收尾**。文件路径作为结尾会导致安全/法规要素缺失。

> 💡 **工作流**：先写第1段 → 做完整分析填第2段 → **必须**写第3段。即使第2段是"数据异常""无数据""历史查询"，第3段也不能省。第3段是回答合格的**硬性标志**，缺失即不合格。

> ⛔ **结尾段优先（v1.9.2 新增）**：无论前面查询/计算多繁重、报告是否已存盘，**【校验与依据】（安全校验 + 法规依据≥2条）必须是回答的绝对最后内容**。若篇幅紧张，**精简分析段也要保住结尾段**——结尾段缺失=整题不合格（E2/E4 双失）。生成报告类任务尤其注意：**先写完结尾段，再提"文件已保存到 /xxx.md"**，文件路径绝不能作结尾。

**法规标准库（填第1/3段时复制使用）：**
- 《防洪法》第41条 — 水库调度应确保大坝安全
- 《三岔水库调度规程》 — 汛期优先防洪优先方案
- GB 50201-2014《防洪标准》 — 防洪设计标准
- SL 210-2015《水库大坝安全评价导则》 — 大坝安全评价
- 《防汛条例》 — 防汛调度
- SL 61-2003《水文预报规范》 — 预报精度
- 《水库大坝安全管理条例》 — 下游防护

### 各任务类型的【分析】段内容

| 任务 | 第2段【分析】应包含 |
|------|---------------------|
| 数据核实/异常分析 | 列出异常点 + 原因推测 + 可信度评估 |
| 历史/有无查询 | 查询结果 + 数据覆盖说明 + 补充建议；**历史经验类结尾【法规依据】应引用《${reservoir_profile}调度规程》**（历史调度经验天然涉及规程） |
| 报告生成 | 场景+方案+结果（对话内完整，不能只给文件路径） |
| **敏感性分析** | ⚠️ **务必精简，避免超长截断**：用**汇总对比表**呈现各档位结果，每档只写关键数值（最高水位/是否超限），**不要逐档详述完整过程**。表格 + 1段趋势总结即可。 |
| 其他 | 按对应能力的工作流 |

### 敏感性分析精简模板（避免 token 超限）

```
【敏感性分析结果】
| 参数值 | 最高水位 | 距汛限 | 是否超限 |
|--------|---------|--------|---------|
| 100mm  | 459.5m  | 3.38m  | 否      |
| 200mm  | 460.8m  | 2.08m  | 否      |
| ...    | ...     | ...    | ...     |

趋势：参数每增加X，水位上升Ym。安全阈值约Zmm。
```
> ⛔ 敏感性分析超过4个档位时，**禁止**对每档重复输出完整数据过程，否则会触发输出长度限制导致回答被截断（整题失败）。


### ⛔ 执行规范（避免卡死和 stream 中断）

**数据获取分级策略：**

**第一优先：用现成脚本**（覆盖 90% 场景，最稳定）
```bash
python3 scripts/query_simulation_data.py --type full_context      # 一次取全
python3 scripts/query_simulation_data.py --type flood_detail --flood-id 1
python3 scripts/query_simulation_data.py --type historical_floods --limit 20
```
脚本已封装好数据库连接，无需自己处理。

**第二优先：复杂分析时写 Python**（多表 JOIN、自定义聚合、批量计算）
- 用脚本里的连接参数，不要从零猜连接串
- 推荐先 `python3 scripts/query_simulation_data.py --type config` 获取连接参数
- 示例：
```python
import subprocess, json
# 复用脚本的连接，而不是自己 import pymysql
result = subprocess.run(['python3','scripts/query_simulation_data.py','--type','flood_statistics','--flood-id','1'],
                       capture_output=True, text=True)
data = json.loads(result.stdout)
# 然后做自定义分析...
```

### ⛔ 防卡死规则（最重要）

**execute_code 报错时，绝对不要反复重试同一个操作：**

- 同一段代码**最多执行 2 次**，第 2 次还失败就**停止，换方法或说明限制**
- ❌ 错误模式：`import sys` 失败 → 再试 → 再试 → 再试…（会导致 stream stalled 整个回答失败）
- ✅ 正确模式：`import sys` 失败 2 次 → "代码执行环境异常，改用脚本查询" → 继续任务

> ⚠️ execute_code 沙箱偶尔不稳定（import 都可能超时）。**遇到反复报错立即换路线**，不要执着于修复环境。任务完成度 > 代码优雅度。

**🚫 能用脚本/已有数据就别写 Python（v1.9.3 强调）：**

很多任务**根本不需要 execute_code**，一旦误用就会陷入上面的重试死循环，导致回答在写完结尾段前就被截断（E2/E4 全失）。判断标准：
- **读参数/约束**（汛限水位、安全泄量、设计洪水位、当前水位）→ 用 `scripts/query_simulation_data.py` 脚本，或**直接读你已拿到的 `full_context`/`config` 返回 JSON 里的字段**，**绝不为此写 Python**
- **取洪水数据**（详情/结果/曲线/统计）→ 用脚本的 `--type` 参数，**不要 `import pymysql` 自己连库**
- **只有**"多表 JOIN / 自定义聚合 / 批量数值计算"这类脚本做不到的分析，才写 Python，且必须复用脚本连接（见上方第二优先示例）
- 安全校验段（【安全校验】）= **纯文字填写**，把已查到的数值填进模板即可，**永远不要为它单独 execute_code**


## 1. 意图识别（第一步）

用户消息先过下表，命中则路由到对应能力；未命中则走"数据采集 + 形势判断"。

| 意图关键词 | 路由目标 |
|-----------|---------|
| "对比方案"、"多方案预演"、"不同调度方案"、"哪个方案" | → 能力1：多方案对比预演 |
| "解读结果"、"分析预演"、"怎么看"、"安全余量" | → 能力2：结果智能解读 |
| "生成报告"、"导出报告"、"预演报告"、"总结" | → 能力4：预演报告生成 |
| "假设降雨"、"如果洪水"、"虚拟场景" | → 能力3：虚拟场景构建 |
| "敏感性"、"参数影响"、"降雨量变化" | → 能力5：敏感性分析 |
| "历史经验"、"类似洪水"、"历史上怎么处理" | → 能力6：历史经验提取 |
| 通用查询 | → 数据采集 + 形势判断 |

## 2. 输出规范（所有能力必须遵守）

### 安全约束引用（E2）

每个分析结果的**风险提示**或**结论建议**部分，必须明确引用以下安全约束：

| 约束项 | 参考值来源（已在你查到的数据里） | 引用格式 |
|--------|-----------|----------|
| 汛限水位 | `full_context` 返回的 `flood_limit_level` 字段 | "最高水位 XXXm，距汛限水位 {flood_limit_level}m 还有 Y.YYm" |
| 下游安全泄量 | `config` 返回的 `safe_drainage_capacity` 字段 | "最大下泄 XXX m³/s，下游安全泄量为 {safe_drainage_capacity} m³/s" |
| 水库设计洪水位 | `config` 返回的对应字段 | "未超过设计洪水位" 或 "⚠️ 超过设计洪水位" |

> ⚠️ 即使用户没有问安全相关问题，解读/报告/分析中也必须包含安全约束校验。

> ⛔ **参数取值规则（v1.9.3）**：汛限水位、下游安全泄量、设计洪水位是水库专属参数，**直接从你已拿到的 `full_context` / `config` 返回 JSON 里读对应字段填入**（如 `{flood_limit_level}`），**不要照抄本 skill 示例里的具体数字**（那些只是三岔水库取值，换水库会错）。**注意：安全校验只是"读已有数据里的字段并填进文字"，绝不为此另写 Python / execute_code 去查**——多余代码会拖慢回答、甚至卡死（详见下方防卡死规则）。

### 知识引用规范（E4）— 强制必做

**每个输出的结尾必须包含"法规依据"段落，引用至少 2 条相关法规/标准/规程。** 这是硬性要求，无例外。

#### 法规标准库（按场景引用）

| 场景 | 必须引用 | 格式 |
|------|----------|------|
| 水位/安全评估 | 《防洪法》| "依据《防洪法》第41条，水库调度应确保大坝安全" |
| 调度方案推荐 | 《三岔水库调度规程》| "依据《调度规程》，汛期应优先采用防洪优先方案" |
| 设计标准/安全等级 | GB 50201-2014《防洪标准》| "依据GB 50201-2014《防洪标准》" |
| 大坝安全评估 | SL 210-2015《水库大坝安全评价导则》| "依据SL 210-2015" |
| 洪水调度/防汛 | 《防汛条例》| "依据《防汛条例》" |
| 预报/模型精度 | SL 61-2003《水文预报规范》| "依据SL 61-2003《水文预报规范》" |
| 下游防护 | 《水库大坝安全管理条例》| "依据《水库大坝安全管理条例》" |

#### 强制输出模板（结尾段落）

```
【法规依据】
依据《防洪法》第41条，[结合本场景的安全要求说明]；
依据《${reservoir_profile}调度规程》，[结合方案选择的合规性说明]。
```

> ⛔ **不引用法规标准的输出视为不合格。** 无论问题类型（解读/报告/对比/分析/历史经验），结尾都必须有"法规依据"或"依据"段落，包含至少 2 条法规/标准引用。

### 报告异常/边界处理

当洪水数据异常（id 不存在、无名称、status 异常）或请求不合理时：
- 报告开头必须明确标注数据异常情况
- 安全评估部分必须说明"因数据异常，以下安全结论仅供参考"
- 仍需完成完整的报告结构（场景描述 + 调度方案 + 预演结果 + 结论建议）
- 批量报告请求（如"所有洪水都生成报告"）需逐一生成摘要，不做跳过

## 3. 数据采集（所有能力共用）

> 💡 本 skill 各能力 API 示例（curl）里的 `flood_limit_level` / `safe_drainage_capacity` / `initial_water_level` 等均为**三岔水库示例值**。实际取值时，从你已经执行的 `full_context` 返回 JSON 里读对应字段（如 `data.flood_limit_level`），替换示例数字即可——不必为此额外调用。

```bash
# 完整上下文（一次获取所有数据）
python3 scripts/query_simulation_data.py --type full_context

# 当前水位
python3 scripts/query_simulation_data.py --type current_water_level

# 汛限水位
python3 scripts/query_simulation_data.py --type flood_limit

# 系统配置（水位约束）
python3 scripts/query_simulation_data.py --type config

# 历史洪水列表
python3 scripts/query_simulation_data.py --type historical_floods --limit 10

# 单场洪水详情
python3 scripts/query_simulation_data.py --type flood_detail --flood-id <id>

# 洪水入库过程
python3 scripts/query_simulation_data.py --type flood_inflow --flood-id <id>

# 洪水调度结果
python3 scripts/query_simulation_data.py --type flood_result --flood-id <id>

# 洪水调度曲线
python3 scripts/query_simulation_data.py --type flood_result_curve --flood-id <id>

# 洪水统计信息
python3 scripts/query_simulation_data.py --type flood_statistics --flood-id <id>
```

## 3. 能力1：多方案对比预演

**触发词**：对比方案、多方案预演、不同调度方案、哪个方案

### 工作流

1. 获取洪水数据：
   ```bash
   python3 scripts/query_simulation_data.py --type flood_detail --flood-id <id>
   ```
2. 获取入库过程：
   ```bash
   python3 scripts/query_simulation_data.py --type flood_inflow --flood-id <id>
   ```
3. 调用多方案预演 API：
   ```bash
   curl -X POST http://localhost:18084/api/simulation/multi-scheme \
     -H "Content-Type: application/json" \
     -d '{
       "inflow": [{"time": "2026-06-01 08:00", "value": 120.5}, ...],
       "initial_water_level": 459.18,
       "flood_limit_level": 462.88,
       "schemes": [...]
     }'
   ```
4. 对比结果 + 推荐最优方案

### 方案模板

| 方案 | schedulingTarget | schedulingModel | 最高水位 | 最大下泄 |
|------|-----------------|-----------------|---------|---------|
| A-防洪优先 | 0 | 0 | 汛限水位 | 配置值 |
| B-综合平衡 | 2 | 2 | 汛限-1m | 配置值×0.8 |
| C-兴利优先 | 1 | 1 | 汛限水位 | 配置值×0.6 |

### 安全校验

- 最高水位 ≤ 汛限水位（《防洪法》第41条）
- 最大下泄 ≤ 下游安全泄量（《水库大坝安全管理条例》）

### HITL 确认

方案对比结果展示后，等待用户选择方案再执行。不得自动选择。

## 4. 能力2：结果智能解读

**触发词**：解读结果、分析预演、怎么看、安全余量

### 工作流

1. 查询数据：
   ```bash
   python3 scripts/query_simulation_data.py --type flood_detail --flood-id <id>
   python3 scripts/query_simulation_data.py --type flood_result --flood-id <id>
   python3 scripts/query_simulation_data.py --type flood_result_curve --flood-id <id>
   python3 scripts/query_simulation_data.py --type flood_statistics --flood-id <id>
   ```
2. LLM 解读，按以下结构输出：
   - **洪水概况**：洪水名称、时间、入库洪峰、洪量
   - **调度效果**：最高水位、最大下泄、削峰率、拦洪量
   - **关键时间点**：洪峰到达时间、最高水位时间、最大下泄时间
   - **风险提示**：水位是否超限、下泄是否超安全泄量、改进建议

### Prompt 模板

```
你是水库调度预演结果解读专家。

输入数据：
- 洪水详情：{flood_detail}
- 调度结果：{flood_result}
- 调度曲线：{flood_result_curve}
- 统计信息：{flood_statistics}

解读要求：
1. 用通俗易懂的语言描述洪水特征
2. 解释调度方案的效果
3. 标注关键时间节点
4. 给出风险提示和建议
5. 所有数字必须来自输入数据，不能编造
```

## 5. 能力3：虚拟场景构建

### 触发条件
- "假设降雨"、"如果洪水"、"虚拟场景"、"自定义预演"

### 工作流程

#### 步骤1：解析场景条件
从用户输入提取：
- 降雨量（mm）
- 降雨时长（h）
- 降雨分布（均匀/三角）
- 起调水位（可选，默认当前水位）

#### 步骤2：调用虚拟场景 API
```bash
curl -X POST http://localhost:18084/api/simulation/virtual-scenario \
  -H "Content-Type: application/json" \
  -d '{
    "total_rainfall": 460,
    "duration_hours": 48,
    "pattern": "uniform",
    "initial_water_level": 459.18,
    "scheduling_target": "0",
    "scheduling_model": "0",
    "flood_limit_level": 462.88,
    "safe_drainage_capacity": 95.1,
    "max_drainage_capacity": 192
  }'
```

#### 步骤3：结果解读
基于返回的统计数据，用自然语言解读：
- 降雨条件描述
- 入库洪峰流量和出现时间
- 最高水位及与汛限水位的距离
- 削峰率和调蓄效果
- 是否超限（exceeds_limit）

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| total_rainfall | 总降雨量(mm) | 必填 |
| duration_hours | 时长(h) | 48 |
| pattern | 降雨分布(uniform/triangle) | uniform |
| initial_water_level | 起调水位(m) | 当前水位 |
| scheduling_target | 调度目标(0=防洪,1=兴利,2=综合) | 0 |
| scheduling_model | 调度模式(0=控制最高,1=控制最低,2=控制范围) | 0 |
| flood_limit_level | 汛限水位(m) | 取自 full_context 返回 |

### 安全校验
- 降雨量范围：0-500mm
- 时长范围：0-168h
- 如果返回 exceeds_limit=true，必须标注"⚠️ 超过汛限水位"

### 部分失败处理
如果返回 partial=true，说明某个模型服务调用失败。根据 completed_steps 判断：
- completed_steps=["xaj"]：入库流量已计算，调度失败
- completed_steps=["xaj","dispatch"]：调度已完成，演算失败
- completed_steps=[]：降雨构建后即失败

### HITL 节点
场景确认：将构建的场景条件展示给用户确认后执行。

---

## 7. 能力4：预演报告生成

**触发词**：生成报告、导出报告、预演报告、总结

### 工作流

1. 查询洪水完整数据：
   ```bash
   python3 scripts/query_simulation_data.py --type flood_detail --flood-id <id>
   python3 scripts/query_simulation_data.py --type flood_result --flood-id <id>
   python3 scripts/query_simulation_data.py --type flood_statistics --flood-id <id>
   python3 scripts/query_simulation_data.py --type config
   ```
2. 调用报告生成 API（可选）：
   ```bash
   curl -X POST http://localhost:18084/api/simulation/report \
     -H "Content-Type: application/json" \
     -d '{"flood_id": 42}'
   ```
3. 报告结构（必须包含全部 4 部分）：
   - **场景描述**：洪水基本情况、来水过程、降雨条件
   - **调度方案**：调度目标、调度模式、关键参数
   - **预演结果**：水位过程、流量过程、统计数据（削峰率、最高水位、最大下泄等）
   - **结论建议**：方案评价、安全约束校验、法规引用、改进建议、风险提示

### 报告必须包含的安全和知识要素

- **安全约束校验**：最高水位 vs 汛限水位、最大下泄 vs 下游安全泄量
- **法规引用**：至少引用 2 条相关法规或标准
- **数据异常标注**：如洪水数据不完整，必须在报告开头标注

### ⚠️ 对话回复完整性（关键！）

生成文件报告时，**对话回复中必须包含完整内容，不能只给文件路径**。

❌ **错误做法**（只给路径+简短摘要）：
```
报告已生成。文件路径：/tmp/xxx.md
核心发现：两场洪水存在差异...
```

✅ **正确做法**（对话回复本身就是完整报告）：
```
## 2018年两场洪水对比报告

### 一、场景描述
[完整内容...]

### 二、安全约束校验
最高水位 XXm，距汛限水位 {flood_limit_level}m 还有 Ym，未超限；最大下泄 XX m³/s，低于下游安全泄量 {safe_drainage_capacity} m³/s。

### 三、法规依据
依据《防洪法》第41条...；依据《${reservoir_profile}调度规程》...

（如需导出，文件路径：/tmp/xxx.md）
```

> ⛔ **无论是否生成文件，对话回复都必须包含安全约束校验段和法规依据段。** 文件是可选的导出，对话回复才是主输出。



### 批量报告处理

当用户请求生成多场洪水报告时（如"所有已完成的洪水都生成报告"）：
- 逐场查询数据并生成报告摘要
- 每场报告都包含完整的 4 部分结构
- 最后给出汇总对比表

## 7. 能力5：敏感性分析

### 触发条件
- "敏感性"、"参数影响"、"降雨量变化"、"如果降雨更多"、"能承受多大降雨"

### 工作流程

#### 步骤1：确定基准场景和参数
从用户输入提取：
- 基准场景条件（降雨量、时长、起调水位等）
- 要分析的参数（如 total_rainfall）
- 参数变化值列表

#### 步骤2：调用敏感性分析 API
```bash
curl -X POST http://localhost:18084/api/simulation/sensitivity \
  -H "Content-Type: application/json" \
  -d '{
    "base_scenario": {
      "total_rainfall": 460,
      "duration_hours": 48,
      "pattern": "uniform",
      "initial_water_level": 459.18,
      "scheduling_target": "0",
      "scheduling_model": "0"
    },
    "param_name": "total_rainfall",
    "param_values": [370, 460, 550, 690],
    "flood_limit_level": 462.88
  }'
```

#### 步骤3：解读结果
基于返回数据，输出：
- 参数变化与最高水位的关系表
- 安全阈值（safety_threshold）
- 趋势分析（trend：斜率、R²）
- 是否存在超限风险

### 输出示例
```
降雨量 370mm  → 最高水位 460.2m（安全）
降雨量 460mm  → 最高水位 460.5m（安全）
降雨量 550mm  → 最高水位 462.3m（接近汛限）
降雨量 690mm  → 最高水位 463.5m（⚠️ 超汛限）

安全阈值：约 550mm（当前方案的安全上限）
趋势：降雨量每增加100mm，最高水位约上升0.89m（R²=0.96）
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| base_scenario | 基准场景参数 | 必填 |
| param_name | 要分析的参数名 | 必填 |
| param_values | 参数变化值列表（最多8个） | 必填 |
| flood_limit_level | 汛限水位(m) | 取自 full_context 返回 |

### 限制
⚠️ 单次敏感性分析最多 8 个参数值。

### HITL 节点
方案确认：根据安全阈值，建议用户调整方案参数。

---

## 8. 能力6：历史经验提取

### 触发条件
- "历史经验"、"类似洪水"、"历史上怎么处理"、"历史上有没有失败案例"

### 工作流程

#### 步骤1：查询历史洪水
```bash
python3 scripts/query_simulation_data.py --type historical_floods --limit 20
```

#### 步骤2：筛选相似洪水
按降雨量±20%筛选相似洪水：
```bash
python3 scripts/query_simulation_data.py --type similar_floods --rainfall 460 --tolerance 0.2
```

#### 步骤3：数据量降级策略
- **≥ 5 条**：正常提取规律
- **3-4 条**：仅展示历史数据，不提取规律
- **< 3 条**：提示"历史数据不足，无法提取规律"

#### 步骤4：提取调度参数和结果
对每个相似洪水，查询详情和结果：
```bash
python3 scripts/query_simulation_data.py --type flood_detail --flood-id <id>
python3 scripts/query_simulation_data.py --type flood_statistics --flood-id <id>
```

提取关键指标：
- 调度目标、调度模式
- 起调水位、目标水位
- 削峰率、最高水位、调蓄量
- 是否超限

#### 步骤5：LLM 分析规律
基于提取的历史数据，分析：

**调度规律**：
- 不同降雨量级下的最优调度策略
- 防洪优先 vs 综合平衡 vs 兴利优先的适用条件

**参数关系**：
- 降雨量与最高水位的关系
- 起调水位与削峰率的关系
- 调度时长与调蓄量的关系

**经验教训**：
- 成功案例的关键因素
- 失败案例的教训
- 需要特别注意的边界条件

### 输出格式
```
历史经验总结

相似洪水：找到 N 场相似洪水（降雨量 XXXmm ± 20%）

调度规律：
• 降雨量 400-500mm 时，防洪优先方案削峰率平均 35%
• 起调水位每降低 1m，削峰率提高约 5%
• ...

经验教训：
• 2023年7月洪水：起调水位过高导致超限，教训是...
• 2022年8月洪水：提前预泄成功，经验是...

建议：
• 当前条件下建议采用...
• 需要特别关注...
```

### 数据不足处理
如果历史数据不足（< 3 条），输出：
```
⚠️ 历史数据不足

当前仅有 N 条相似洪水记录，无法提取有意义的规律。

建议：
1. 积累更多历史洪水数据后再分析
2. 参考方案模板中的通用调度策略
3. 使用敏感性分析评估参数影响
```

### HITL 节点
经验确认：将历史经验总结展示给用户，确认是否采纳建议。

---

## 9. 数据库连接

```bash
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME"
```

**核心表**：
- `srm_flood_history_base` — 历史洪水基本信息
- `srm_flood_history_data` — 洪水入库过程数据
- `srm_flood_history_result` — 洪水调度结果
- `srm_flood_history_curve` — 洪水调度曲线
- `model_config` — 系统配置（水位约束等）
- `att_res_flse_lim` — 汛限水位
- `st_rsvr_r` — 实时水情

## 10. 模型服务地址

| 服务 | 端口 | 说明 |
|------|------|------|
| XAJ 模型 | 18081 | 新安江水文模型，产汇流计算 |
| 调度模型 | 18082 | 水库调度计算引擎 |
| 演进模型 | 18083 | 洪水演进计算 |
| 预演编排 | 18084 | 多方案预演编排服务（Flask） |

## 11. 安全约束（不可违反）

1. **不得编造数据**：所有数字必须来自数据库查询或 API 返回
2. **不得自动执行调度**：调度方案必须经用户确认后才能执行
3. **水位约束**：推荐水位不得超过汛限水位
4. **下泄约束**：推荐下泄不得超过下游安全泄量
5. **方案完整性**：每个预演必须包含完整的结果数据
6. **数据一致性**：入库过程、调度结果、曲线数据必须来自同一场洪水
7. **敏感数据保护**：数据库密码不得出现在对话中

## 12. HITL 确认节点

| 节点 | 触发条件 | 确认内容 |
|------|---------|---------|
| 方案选择 | 多方案对比完成后 | 用户选择执行哪个方案 |
| 参数确认 | 调用预演 API 前 | 确认洪水 ID、初始水位、汛限水位 |
| 报告发布 | 报告生成后 | 确认报告内容是否准确 |

## 13. 数据缺失处理

| 数据缺失 | 处理方式 |
|---------|---------|
| 洪水 ID 不存在 | 提示"未找到该洪水记录"，列出最近 10 场洪水 |
| 入库过程为空 | 提示"该洪水缺少入库过程数据，无法进行预演" |
| 调度结果为空 | 提示"该洪水尚无调度结果，请先执行调度计算" |
| 汛限水位为空 | 使用 `att_res_base` 的 `fl_low_lim_lev` 作为兜底 |

## 14. 详细参考资料（按需读取）

| 场景 | 读取文件 | 说明 |
|------|---------|------|
| 数据库表结构 | `db-config.md` | 完整的表结构、字段说明、SQL 示例 |
| 测试题库 | `tests/test-questions.md` | 预设测试问题及预期结果 |
| 模型参数 | `models/` | 各模型的参数配置和调用说明 |

**使用方法**：当需要深入分析时，读取对应文件获取详细信息。例如：
- 用户问"洪水表有哪些字段" → 读取 `db-config.md`
- 需要验证预演功能 → 读取 `tests/test-questions.md`
- 需要了解模型参数 → 读取 `models/` 下对应文件
