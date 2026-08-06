# SmartTwinRes-Skills 项目代码深入分析与全面解读

> 生成日期：2026-08-06
> 分析基线：main 分支 HEAD `f23f277`
> 分析范围：supervisor 编排层、5 个专业 skill（forecasting / early-warning / plan-generation / simulation / diagnosis-verification）、共享 lib、测试框架、autoresearch 自优化体系

---

## 一、项目定位与总体架构

### 1.1 项目本质

**SmartTwinRes-Skills** 不是传统意义上的"一个程序"，而是 **Claude Code / Hermes Agent 平台上的 Skill 集合**。Skill 是一种"Prompt + 脚本 + 知识库 + 测试"的打包单元，由 LLM 智能体在对话中按需加载执行。因此本仓库的"代码"主要由三类资产构成：

1. **SKILL.md** —— 每个 skill 的核心，本质是写给 LLM 的工作流指令（含法规库、输出蓝图、决策路由表）
2. **scripts/query_*.py** —— Python 数据查询脚本，封装了 MySQL 连接、SQL 模板、结果格式化
3. **references/、reservoirs/、analysis/** —— Markdown 知识库，供 LLM 引用

理解这一点至关重要：**这个项目的"运行"不是 `python main.py`，而是 Hermes Agent 加载某个 SKILL.md 后，按其指令调用脚本、组织语言、产出符合法规要求的研判报告**。

### 1.2 业务背景：水库"四预"

项目服务于智慧水利水库运行管理，核心是水利部推行的 **"四预"体系**：

| 四预 | 含义 | 对应 Skill |
|------|------|-----------|
| **预报** (forecasting) | 降雨/水位/入库流量预报 | forecasting |
| **预警** (early-warning) | 多级阈值监控与告警 | early-warning |
| **预演** (simulation) | 多方案洪水推演仿真 | simulation |
| **预案** (plan-generation) | 调度方案生成与对比 | plan-generation |

外加一个横切的 **诊断验证** skill（diagnosis-verification）和 **supervisor 编排层**，构成完整的"四预智能体集群"。

### 1.3 两层架构

```
┌─────────────────────────────────────────────────────────┐
│  supervisor（编排层 / Orchestrator）                     │
│  场景识别 → DAG 编排 → 跨 skill 调度 → 结果仲裁 → 报告  │
│  全局 State（SQLite）+ 断点续跑 + HITL 检查点            │
└────────────────────────┬────────────────────────────────┘
                         │ 当作工具调用
        ┌────────────────┼────────────────┬──────────────┐
        ▼                ▼                ▼              ▼
  forecasting       early-warning     simulation    plan-generation
  (预报解读)         (告警分析)        (预演仿真)     (预案生成)
        │                │                │              │
        └────────────────┴────────────────┴──────────────┘
                         │
                         ▼
              共享 lib/（db / tenant / filters / paths）
                         │
                         ▼
              MySQL（powerelf_srm_yml，按 SRM_TENANT_ID 隔离）
```

**关键设计原则（README "安全约束" + 各 SKILL.md 反复强调）**：

1. **不得编造数据** —— 所有数字必须来自数据库查询或脚本返回
2. **不得自动执行调度** —— 调度方案必须经用户确认（HITL）
3. **水位约束** —— 推荐水位不得超过汛限水位
4. **下泄约束** —— 推荐下泄不得超过下游安全泄量
5. **数据一致性** —— 入库过程、调度结果、曲线数据必须来自同一场洪水
6. **敏感数据保护** —— 数据库密码不得出现在对话中

---

## 二、Supervisor 编排层深度解读

Supervisor（v0.4.0）是整个项目的"大脑"，它本身不做任何专业判断，只负责 **顺序、状态、仲裁、断点** 四件事。

### 2.1 场景识别（scene_router.py）

通过关键词表把用户输入/告警摘要路由到四类场景：

| 场景 | 名称 | 优先级 | 触发关键词示例 |
|------|------|--------|---------------|
| **D** | 应急响应 | 100 | 闸门故障、险情、溃坝、管涌、滑坡、漫坝、人员转移 |
| **A** | 汛期暴雨研判调度 | 80 | 暴雨、洪水、超汛限、入库流量、红色预警、台风 |
| **B** | 大坝安全智能诊断 | 60 | 渗压、渗流、位移、裂缝、大坝安全、扬压力、沉降 |
| **C** | 日常精细化管控 | 40 | 日报、例行、日常、值班、巡检、台账 |

**路由逻辑（`route()` 函数）**：

1. 应急强信号词（EMERGENCY_STRONG）命中 → 场景 D（人身/大坝安全优先）
2. 日常强信号词（DAILY_STRONG）命中 → 场景 C
3. 否则按 SCENE_RULES 关键词匹配，取优先级最高者
4. 无法识别 → 返回 `scene=UNKNOWN`，**不猜测，交由上层兜底**

这是一个值得注意的设计：**优先级数字越大越优先，应急 > 暴雨 > 大坝 > 日常**，符合防洪安全第一的原则。强信号词（DAILY_STRONG / EMERGENCY_STRONG）单独前置判断，避免"每日例行…但闸门故障"这类复合输入被误归为日常。

### 2.2 四场景 DAG（dag_order.py）

每个场景对应一条有向无环图（DAG），定义了子 skill 的执行顺序：

| 场景 | DAG 步骤（按序） |
|------|----------------|
| **A** 暴雨研判 | step1 forecasting → step2 diagnosis → step3 inspection → step4 simulation → step5 plan-gen → **step6 仲裁** → step7 chatbi 报告 |
| **B** 大坝诊断 | step1 diagnosis → step2 inspection → step3 simulation → **step4 仲裁** → step5 chatbi |
| **C** 日常管控 | step1 forecasting+inspection → step2 simulation → step3 chatbi |
| **D** 应急响应 | step1 early-warning → step2 plan-gen → step3 simulation → **step4 仲裁 + HITL** → step5 chatbi |

**场景 A 的七步闭环是核心**：从雨情水情研判出发，经工情核查、设备可调度性核查、多方案洪水推演、调度方案生成，到方案 vs 仿真一致性仲裁，最终生成研判报告。

### 2.3 全局 State（supervisor_state.py + SQLite）

所有阶段结果统一持久化到 `state/supervisor_state.db`（SQLite），核心表：

```sql
events(event_id PK, scene, status, risk_level, priority, created_at, updated_at)
stage_results(event_id, stage, agent, result_json, status, ts, PK(event_id, stage))
```

**关键能力**：

- **断点续跑**：`resume --event X` 列出未完成阶段并继续执行（`cmd_resume`）
- **优先级队列**：`queue` 命令按 优先级(高>中>低) + 创建时间 排序未结束事件（v0.4）
- **HITL 检查点**：场景 A/D 的仲裁阶段前，事件状态置 `awaiting_approval`，暂停等待人工 `--approve` 确认
- **事件号生成**：`A-20260805-001` 格式，场景前缀 + 日期 + 当日序号（`_next_event_seq`）

**result_json 上限 40000 字符**（`execute_dag` 中 `[:40000]`），避免子脚本 stdout 过长破坏 SQLite 写入。

### 2.4 仲裁规则（arbitrator.py）

仲裁是 Supervisor 的"刚性环节"，避免纯 LLM 臆断出方案。三类仲裁函数：

#### arbitrate_plan_vs_simulation（场景 A 通用仲裁）

| 规则 | 判断 | 裁决 |
|------|------|------|
| 规则1 | 方案预估最高水位 > 仿真推演 | `decision=adjust`，以仿真为准（保守） |
| 规则2 | 方案下泄 > 下游安全泄量 | `decision=reject`，方案需降档或重新拟定 |
| 规则1b | 仿真结果自身超汛限 | 记录 issue + suggestion，**不否决**（passed 不变） |

`ArbitrationResult` dataclass 含 `passed / decision(accept|adjust|reject) / issues[] / adopted_values / suggestion`。

#### arbitrate_emergency（场景 D 应急专用）

- Ⅰ/Ⅱ级告警存在 → `escalate`（强制升级）
- 方案下泄 > 安全泄量 → `reject`（否决，重新拟定）
- 仿真最高水位 > 汛限 → `escalate`（降库/预泄）
- 其余 → `pending_approval`（HITL，`hitl_required=true` 恒强制）

#### arbitrate_dam_diagnosis（场景 B 大坝诊断专用）

按数据可信度 + 缺陷等级 + 仿真超限三维度定级（高/中/低），输出处置建议。

**重要约束（SKILL.md "四、仲裁规则" 末尾）**：阈值（汛限/安全泄量/特征水位）**全部运行时从 reservoir profile / model_config / full_context 读取**，**禁止在仲裁代码里硬编码数字**。这一约束与各 skill 的 C2 拦截口径一致，确保多水库可插拔。

### 2.5 报告生成（do_report）

step7（或各场景最后一步）从 State 汇总各阶段真实结果，生成结构化 Markdown 研判报告：

- **数据源全部为 `stage_results.result_json`**（各阶段子 skill 的真实输出），**不做二次查询、不编造数字**
- 缺失阶段标注"未执行"
- **按场景区分阶段映射**（`stage_map`）：
  - A: fc=step1, insp=step3, sim=step4, plan=step5, arb=step6
  - B: fc=step1, insp=step2, sim=step3, plan=None, arb=step4
  - C: fc=step1, insp=None, sim=step2, plan=None, arb=None
  - D: fc=step1, insp=None, sim=step3, plan=step2, arb=step4

报告五段：水情实况 / 工情与设备核查 / 推演与方案 / 仲裁结论 / 执行链路表。

### 2.6 execute_dag 核心流程

```python
def execute_dag(event_id, scene, conn, flood_limit, safe_discharge, dry_run, approve):
    dag = DAG_ORDER.get(scene, [])
    done = {已完成阶段}
    steps_to_run = [s for s in dag if s not in done]  # 断点续跑

    if dry_run: 打印将执行的命令; return

    for stage in steps_to_run:
        # HITL 检查点：场景 A/D 的仲裁阶段前需人工确认
        if stage == arbitrate_stage and not approve:
            UPDATE events SET status='awaiting_approval'
            return  # 暂停等待人工 --approve

        if stage in (arbitrate, report):
            result = do_arbitration(...) or do_report(...)  # 内存执行
        else:
            out = run_stage_cmd(cmd)  # 调用子 skill 脚本
            if out 失败:
                UPDATE events SET status='error'
                return  # 中断 DAG，待运维 replay

        INSERT OR REPLACE INTO stage_results(...)  # 写入 State

    UPDATE events SET status='done'
```

**三个关键设计**：

1. **断点续跑**：`steps_to_run = [s for s in dag if s not in done]`，已完成的阶段不重跑
2. **HITL 检查点**：仲裁阶段前强制暂停（场景 A/D），等待人工 `--approve` 确认后才继续
3. **失败中断**：子脚本失败 → 事件标记 `error`，中断 DAG，待运维修复后 `resume`

---

## 三、五大专业 Skill 解读

每个 skill 都遵循统一的"输出蓝图"：**【依据】开头 + 【分析】中段 + 【校验与依据】结尾**，结尾段缺失 = 整题不合格（E2/E4 双失）。这是项目最核心的"硬性约束"。

### 3.1 forecasting（预报系统，v1.0.1）

**定位**：水库水文预报智能解读 —— 降雨预报解读、水库影响估算、多源预报融合、水位趋势预测、预报精度评估。

**数据源铁律**：

- 只读 `scripts/query_forecast_data.py` 与 `query_forecast_analysis.py`（按 `SRM_TENANT_ID` 隔离）
- **只读 `model_result_files(type=1)` 预报来水过程，不触发任何模型计算**
- 禁止混用 water-situation / water-warning / rainfall / plan-generation 的数据源

**快捷路径**：`--type full_context` 一次取回 5 类核心数据（当前水位 + 和风降雨预报 + 汛限 + 气象预警 + 配置 + `_meta`），瘦身以降上下文重量/延迟。

**法规依据**：《水文情报预报规范》GB/T 22482、SL 250-2000、《防洪法》、《水库大坝安全管理条例》、GB/T 50138-2010。

**query_forecast_data.py 主要函数（16 个）**：

| 函数 | 用途 |
|------|------|
| `query_current_water_level` | 当前水位（rz/inq/otq/w） |
| `query_rainfall_forecast` | 24h/168h 降雨预报 |
| `query_weather_warning` | 气象预警 |
| `query_flood_limit` | 汛限水位（`_pick_in_season_flse_lim` 按汛期状态选主/次汛） |
| `query_model_forecast_result` | 模型预报来水过程 |
| `query_water_level_curve` | 水位过程线 |
| `query_historical_floods` | 历史相似洪水 |
| `query_forecast_accuracy_stats` | 预报精度统计（MAPE/合格率，空表自动 gated） |
| `query_multi_source_overview` | 多源降雨宏观对比 |
| `query_full_context` | 一次取全 5 类核心数据 |
| `get_master_stcd` | 获取水库主站码 |

### 3.2 early-warning（预警系统，v5.2.0）

**定位**：智慧水利预警系统智能体 —— 告警分析、诊断、预测、问答。**读操作直连数据库，写操作走后端 API**。

**核心表**：`ew_info_message`(2021条)、`ew_info_rules`(25条)、`st_rsvr_r`(19万)、`st_pptn_r`(26万)。

**查询类型**（`query_early_warning.py`）：unconfirmed / by_level / recent / by_station / high_level / rules / station_ranking / device_offline / alarm_storm / confirmation_rate / weather_warning。

**智能分析触发词**：告警情况 / 风险评估 / 安全确认 / 告警分析 / 大坝安全 / 应急预案 / 未来预测 / 值班关注。

**智能分析能力**：

- 自动采集多源告警数据（告警表、水位、降雨、气象预警）
- 告警聚合与去噪（分组、去重、排序）
- 跨域关联分析（水位+降雨+渗流 → 大坝风险）
- 风险评估（高/中/低，基于5因素评分矩阵）
- 趋势预测（未来24小时水位和风险演变）
- 响应建议生成
- 高风险自动触发预案生成（需人工确认）

**依赖模块**：`analysis/risk-scoring-matrix.md`、`analysis/correlation-analysis.md`、`analysis/root-cause-analysis.md`、`analysis/predictive-warning.md`。

**性能优化**：一次查询获取所有数据 / 时间范围限制 / LIMIT 分页 / 避免 SELECT * / `db.py` 的 `query_multi` 批量执行复用连接。

### 3.3 plan-generation（预案生成，v3.2.1）

**定位**：水库调度预案智能生成 —— 防汛形势评估、汛情研判、水情数据分析、调度预案生成、方案对比推荐、历史预案查询、调度决策。

**水库身份感知**：

- 通过 `SRM_RESERVOIR_NAME`（默认 sancha）适配不同水库
- profile 目录：`reservoirs/${SRM_RESERVOIR_NAME:-sancha}/`
- 桃曲坡：汛限 786.80m(主汛)/788.00m(次汛)、正常蓄水位 788.5m、设计洪水位 788.54m、校核洪水位 790.5m、死水位 755m、下游安全泄量 500m³/s
- 三岔：见 `reservoirs/sancha/`（或运行时从 model_config 动态读取）

**法规依据**：《防洪法》第41条、《水库大坝安全管理条例》、《防汛条例》、GB 17621-1998、SL 224-2019、调度规则。

**任务类型**：预案生成 / 预案解读 / 形势研判 / 调度决策 / 应急处置 / 实况/知识问答。

**三组方案**：A防洪优先 / B综合平衡 / C兴利保供 —— 根据调度规则选择条件。

### 3.4 simulation（预演仿真，v1.9.3）

**定位**：水库预演AI增强 —— 多方案对比预演、结果智能解读、虚拟场景构建、预演报告生成。**支持 SQL 直连和 Flask 编排服务两种模式**。

**依赖服务**：xaj-model:18081、dispatch-model:18082、routing-model:18083、orchestrator:18084。

**防卡死规则（最重要）**：

- execute_code 报错时，**绝对不要反复重试同一个操作**
- 同一段代码**最多执行 2 次**，第 2 次还失败就**停止，换方法或说明限制**
- ❌ 错误模式：`import sys` 失败 → 再试 → 再试 → 再试…（会导致 stream stalled 整个回答失败）
- ✅ 正确模式：`import sys` 失败 2 次 → "代码执行环境异常，改用脚本查询" → 继续任务

**v1.9.3 强调**：能用脚本/已有数据就别写 Python。判断标准：

- 读参数/约束 → 用脚本，或直接读已拿到的 `full_context`/`config` 返回 JSON 里的字段，**绝不为此写 Python**
- 取洪水数据 → 用脚本的 `--type` 参数，**不要 `import pymysql` 自己连库**
- **只有**"多表 JOIN / 自定义聚合 / 批量数值计算"这类脚本做不到的分析，才写 Python

**敏感性分析精简模板**：超过 4 个档位时，**禁止**对每档重复输出完整数据过程，否则会触发输出长度限制导致回答被截断。用汇总对比表 + 1段趋势总结即可。

### 3.5 diagnosis-verification（诊断验证，v1.0.0）

**定位**：水库四预系统诊断与验证 —— 8 阶段结构化诊断、6 层独立验证、6 步自动修复，覆盖 forecasting、early-warning、plan-generation、simulation 全场景。

**三大能力**：

| 能力 | 描述 | 触发场景 |
|------|------|---------|
| **diagnose（诊断）** | 8 阶段结构化诊断流程 | 数据异常、告警误报、预案失败、系统错误 |
| **verify（验证）** | 6 层独立验证体系 | 输出验证、诊断验证、修复验证、跨域一致性 |
| **auto-fix（自动修复）** | 6 步自动修复流程 | 基于诊断结果自动生成并执行修复方案 |

**三原则体系**：

- **诊断三原则**：①每个结论必须标注证据来源，禁止"可能"、"大概"、"应该" ②8 个 Phase 缺一不可 ③区分"掩盖故障"和"合理降级"：不能靠修复者自证
- **验证三原则**：①修复者不能给自己打分 — 必须换 Agent 独立验证 ②6 层验证缺一不可 ③验证通过的标准是可重现的证据 — 不是"看起来没问题"
- **修复三原则**：①最小化改动 ②向后兼容 ③最多 3 轮自动重试 — 超过 3 轮停止并升级人工

**8 阶段诊断流程**（详见 `references/diagnose-8phases.md`）：

- Phase 0：澄清确认 ⚠️ 不能跳过（确认诊断范围和时间边界）
- Phase 1：全景扫描 ⚠️ 不能跳过（收集全量数据，统计错误分布）
- Phase 2-7：根因定位 / 影响评估 / 临时处置 / 修复方案 / 验证 / 复盘

---

## 四、共享基础设施（lib/）

### 4.1 模块清单

| 模块 | 职责 |
|------|------|
| `lib/db.py` | 数据库连接封装（`execute_query_list` 等），连接池/超时控制 |
| `lib/tenant.py` | 多租户隔离（`current_tenant_id`），按 `SRM_TENANT_ID` 隔离查询 |
| `lib/filters.py` | 数据过滤通用逻辑 |
| `lib/paths.py` / `lib/paths.sh` | 路径管理（skill 目录解析、HERMES_SKILL_DIR 等） |

### 4.2 多水库可插拔设计

**水库身份感知**是项目的核心设计：通过环境变量 `SRM_RESERVOIR_NAME`（默认 `sancha`）激活对应 reservoir profile。

- profile 目录：`reservoirs/${SRM_RESERVOIR_NAME:-sancha}/`
- profile 内容：`identity.md`（身份）/ `characteristic-levels.md`（特征水位）/ `curve-data.md`（水位-库容/泄流曲线）/ `stations`（站网）

**铁律（README "安全约束" + 各 SKILL.md 反复强调）**：

> **禁止照抄本 skill 示例里的具体数字**——那些只是某个水库的取值，必须以当前 profile 为准。三岔 ~460m 量级、桃曲坡 ~788m 量级，基准不同。

**Supervisor 多水库适配**：Supervisor 本身**无水库特定逻辑**——子 skill 已全部接入 reservoir profile，编排层只透传环境变量。桃曲坡用 `SRM_RESERVOIR_NAME=taoqupo`（tenant 20），三岔默认（tenant 18）。

---

## 五、数据库配置标准（DB-CONFIG-STANDARD.md）

### 5.1 环境变量优先级

```
SRM_DB_*  →  POWERELF_DB_*  →  默认值
（优先）     （兼容）        （兜底）
```

| 配置项 | 变量名 | 默认值 | 必填 |
|-------|--------|--------|------|
| 主机 | `SRM_DB_HOST` | `127.0.0.1` | 否 |
| 端口 | `SRM_DB_PORT` | `3306` | 否 |
| 数据库 | `SRM_DB_NAME` | `powerelf_srm_yml` | 否 |
| 用户 | `SRM_DB_USER` | - | **是** |
| 密码 | `SRM_DB_PASSWORD` | - | **是** |

### 5.2 Python 实现标准

```python
DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': os.getenv('SRM_DB_USER'),
    'password': os.getenv('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 30,
}
```

### 5.3 安全与合规要点

- ✅ 禁止硬编码数据库密码
- ✅ 强制从环境变量读取凭据
- ✅ 连接超时控制（10s）
- ✅ 读取超时控制（30s）
- ✅ UTF-8 字符集（utf8mb4）

---

## 六、测试与自优化体系

### 6.1 自动化测试框架（test_skills.py）

统一框架 `test_skills.py`，支持：

- 单个 Skill / 全部 Skill 测试
- 单个测试用例 / 列出所有用例
- Markdown / JSON 格式测试报告
- 超时控制（`--timeout 300`）

**测试覆盖率（README 表）**：

| Skill | 测试用例数 | 状态 |
|-------|----------|------|
| forecasting | 6 | ✅ 已验证 |
| plan-generation | 3 | 🟡 待验证 |
| simulation | 2 | 🟡 待验证 |
| early-warning | - | ⏳ 开发中 |
| diagnosis-verification | - | ⏳ 开发中 |

### 6.2 Supervisor 集成测试

`tests/integration/test_supervisor_e2e.py` 覆盖四场景（A/B/C/D）端到端实测。

**v0.2.0 落地状态**：四场景（A/B/C/D）全部实测跑通（2026-08-05）。

### 6.3 autoresearch 自优化体系

项目深度集成了 `autoresearch` 方法论（基于 Karpathy 的 autoresearch），用于自主优化 Skill：

- **autoresearch/** 顶层目录
- 各 skill 下 `autoresearch-<skill>/` 子目录（early-warning / forecasting / plan / simulation）
- 流程：读取 skill → 反复运行 → 用 binary evals 评分 → 修改 prompt → 保留改进
- 输出：改进后的 SKILL.md、results log、changelog（每次 mutation 一条）

**autoresearch-early-warning 已迭代到 v5**（`autoresearch-v5/`），是项目中最成熟的优化轨道。

### 6.4 四类 demo 输出

`supervisor/demo-output/` 下有四场景两轮实测产物：

- `A-20260805-192150.json` / `A-20260805-192723.json`（场景 A 两轮）
- `B-20260805-192150.json` / `B-20260805-192723.json`（场景 B 两轮）
- `C-20260805-192150.json` / `C-20260805-192723.json`（场景 C 两轮）
- `D-20260805-192150.json` / `D-20260805-192723.json`（场景 D 两轮）

可通过 `demo.sh` 一键复现四场景编排。

---

## 七、关键设计模式与工程亮点

### 7.1 "输出蓝图"硬性约束（最核心）

每个 skill 的 SKILL.md 都强制 **3 段式输出**：

1. **【依据】**（开头）— 引用场景对应的法规/规范框架
2. **【分析】**（中间）— 任务核心内容（数据、解读、报告、对比等）
3. **【校验与依据】**（结尾，**必填，必须是回答的绝对最后内容**）

> ⛔ 结尾段缺失 = 整题不合格（E2/E4 双失）。无论前面查询多繁，篇幅紧张就精简分析段保结尾段。

这是项目最重要的质量保障机制：**通过 Prompt 硬约束，强制 LLM 在每次回答末尾进行安全校验（水位 vs 汛限 + 下泄 vs 安全泄量）并引用法规依据**。

### 7.2 "铁律"式 Prompt 工程项目反复用"⛔ 铁律"标记不可违反的规则：

- ⛔ **结尾段优先**：无论前面查询/计算多繁重，【校验与依据】必须是回答最后内容
- ⛔ **参数取值规则**：汛限水位、安全泄量等约束值**直接从已拿到的 `full_context`/`config` 返回 JSON 里读对应字段填入**，**严禁照抄本 skill 示例里的具体数字**
- ⛔ 安全校验段 = **纯文字填写**，把已查到的数值填进模板即可，**永远不要为它单独 execute_code**
- ⛔ Step6 仲裁是刚性的：plan-generation 输出的调度方案必须与 simulation 推演结果交叉校验——最高水位是否超汛限、下泄是否超下游安全泄量。**冲突时以仿真为准**，不允许纯 LLM 臆断出方案

### 7.3 "防卡死"规则

simulation SKILL.md v1.9.3 反复强调：

- execute_code 报错时，**绝对不要反复重试同一个操作**
- 同一段代码**最多执行 2 次**，第 2 次还失败就**停止，换方法或说明限制**
- **任务完成度 > 代码优雅度**

这是针对 Hermes Agent 弱本地端点容易超时卡死的实战经验沉淀。

### 7.4 "数据源优先级"告警

每个 skill 都有"数据源优先级告警"：

> **⚠️ 数据源优先级（必须遵守）**：当前水库的所有预报/实况/汛限/精度/历史数据**必须从本 skill 的 `scripts/query_forecast_data.py` 获取**（按 `SRM_TENANT_ID` 隔离查询调度数据库）。**禁止**混用 water-situation / water-warning / rainfall / plan-generation 等 skill 的数据源——它们查询的是全区域河道站或 `model_result_files(type=2)` 调度结果，不适用于水文预报解读。

这避免了不同 skill 查询不同数据源导致的数字混乱（如三岔 ~460m 量级 vs 区域河道站 ~240m 数据）。

### 7.5 多水库可插拔 profile

通过 `SRM_RESERVOIR_NAME` 环境变量激活对应 reservoir profile：

- profile 目录：`reservoirs/${SRM_RESERVOIR_NAME:-sancha}/`
- profile 内容：`identity.md` / `characteristic-levels.md` / `curve-data.md` / `stations`
- **Supervisor 本身无水库特定逻辑**——子 skill 已全部接入 reservoir profile，编排层只透传环境变量

这实现了"一套代码、多个水库"的可插拔适配，桃曲坡（tenant 20）和三岔（tenant 18）共用同一套 skill。

### 7.6 SQLite 全局 State + 断点续跑

Supervisor 用 SQLite（`state/supervisor_state.db`）持久化全局 State：

- **断点续跑**：`resume --event X` 列出未完成阶段并继续执行
- **HITL 检查点**：仲裁阶段前事件状态置 `awaiting_approval`，暂停等待人工 `--approve` 确认
- **优先级队列**：未结束事件按 优先级(高>中>低) + 创建时间 排序

相比内存态编排，SQLite 持久化让长流程编排可以跨会话恢复，是生产级多 Agent 编排的关键能力。

---

## 八、代码质量与潜在改进点

### 8.1 代码质量亮点

1. **统一的输出蓝图**：5 个 skill + supervisor 都遵循"【依据】+【分析】+【校验与依据】"3 段式，结尾段缺失即不合格。这是项目最核心的质量保障机制。
2. **清晰的职责分层**：Supervisor 只编排不判断，子 skill 只管自己的领域，共享 lib 只管基础设施。
3. **铁律式 Prompt 工程**：用"⛔ 铁律"标记不可违反的规则，并通过 `references/` 沉淀领域知识。
4. **断点续跑 + HITL**：SQLite 持久化 + `awaiting_approval` 状态机，支持长流程编排跨会话恢复和人工确认检查点。
5. **多水库可插拔**：`SRM_RESERVOIR_NAME` + reservoir profile 实现"一套代码、多个水库"。
6. **autoresearch 自优化闭环**：基于 Karpathy autoresearch 方法论，用 binary evals 评分驱动 prompt 迭代，early-warning 已迭代到 v5。

### 8.2 潜在改进点

1. **测试覆盖率不均**：forecasting 6 个用例已验证，但 early-warning / diagnosis-verification 标"开发中"，测试覆盖存在缺口。
2. **stage_map 硬编码**：`do_report` 中 `stage_map` 按场景硬编码阶段映射（A: fc=step1, sim=step4...），新增场景需手动维护，可考虑从 `DAG_ORDER` + 各 skill 的"阶段语义"自动推导。
3. **result_json 40000 字符上限**：`execute_dag` 中 `[:40000]` 是硬截断，若子脚本 stdout 转义后超长会破坏合法 JSON，建议改为"超长时落盘到文件 + result_json 存文件路径"。
4. **scene_router 关键词表驱动**：当前是纯关键词匹配，对"红色预警，但只是气象预警不是水库告警"这类语义模糊的输入可能误判。可考虑结合 LLM 语义路由（但需权衡延迟）。
5. **多源融合裁决口径**：forecasting SKILL.md 提到"预报源分歧 → 沿用 forecasting 的多源裁决（NMC>模型源>和风，反向取保守）"，但这一优先级是否应可配置（如某些水库更信任和风）值得评估。
6. **arbitrator.py 硬编码风险等级顺序**：`arbitrate_risk_levels` 中 `order = {"低": 1, "中": 2, "高": 3, "极高": 4}` 硬编码，虽然风险等级词汇相对稳定，但可考虑从配置读取以支持国际化或扩展等级。

---

## 九、项目演进脉络

从 git 历史和文档版本号可看出清晰的演进脉络：

1. **v1.0 (2026-07-11) 初始版本**：5 个专业 skill + 自动化测试框架 + 数据库配置标准
2. **supervisor v0.2.0 (2026-08-05)**：四场景（A/B/C/D）全部实测跑通
3. **supervisor v0.4.0 (当前)**：新增场景 B 大坝诊断专用仲裁 + 场景 D 应急专用仲裁 + 优先级队列
4. **autoresearch 持续迭代**：early-warning 已迭代到 v5，forecasting / plan / simulation 也有各自的 autoresearch 轨道

**最新进展（2026-08-06 git status）**：

- `lib/filters.py` 有未提交修改
- `supervisor/scripts/arbitrator.py` / `orchestrator.py` 有未提交修改（疑似 v0.4 优先级队列相关）
- `tests/integration/test_supervisor_e2e.py` 有未提交修改（新增测试覆盖）
- 新增 `docs/review-2026-08-06.md`（本次代码审查产物）

---

## 十、总结

**SmartTwinRes-Skills 是一个"Prompt 工程 + Python 脚本 + 知识库 + 编排层"四位一体的智慧水利 Skill 集合**，其核心价值在于：

1. **领域专业知识的 Prompt 化沉淀**：把水利法规库（GB/T 22482、《防洪法》、《调度规程》等）、调度规则、预警阈值体系编码进 SKILL.md 和 references/，让 LLM 在对话中按规约产出合规研判。
2. **多 Agent 编排的工程化实现**：Supervisor 通过场景识别 → DAG 编排 → 结果仲裁 → 全局 State 持久化，把 5 个专业 skill 组织成自动化闭环，支持断点续跑和 HITL 检查点。
3. **自优化闭环**：autoresearch 方法论驱动 Skill prompt 持续迭代，用 binary evals 评分保留改进，early-warning 已迭代到 v5。
4. **多水库可插拔**：`SRM_RESERVOIR_NAME` + reservoir profile 实现"一套代码、多个水库"（三岔 tenant 18 / 桃曲坡 tenant 20）。

项目的工程亮点在于**统一的"输出蓝图"硬性约束**（3 段式 + 结尾段缺失即不合格）、**铁律式 Prompt 工程**（⛔ 标记 + 防卡死规则 + 数据源优先级告警）、**SQLite 全局 State + 断点续跑**（生产级多 Agent 编排的关键能力）。

潜在改进方向集中在**测试覆盖率均衡**、**stage_map 自动推导**、**result_json 超长处理**、**scene_router 语义路由**等点，但整体架构清晰、职责分层合理、领域知识沉淀扎实，是一个成熟度较高的智慧水利 AI Agent 项目。
