---
name: supervisor
description: "四预智能体协同编排层（Supervisor）：场景识别、任务拆解、DAG 编排、跨 skill 调度、结果仲裁、全局 State 持久化与断点续跑。把 forecasting / early-warning / plan-generation / simulation / diagnosis-verification 等专业 skill 组织成自动化闭环。"
version: 0.4.0
author: SmartTwinRes Team
license: MIT
platforms: [linux, windows, macos]
metadata:
  hermes:
    tags: [water-conservancy, supervisor, orchestration, dag, state, multi-agent]
    related_skills: [forecasting, early-warning, plan-generation, simulation, diagnosis-verification]
  reservoir:
    default: sancha
    env: SRM_RESERVOIR_NAME
prerequisites:
  env_vars: [SRM_DB_HOST, SRM_DB_PORT, SRM_DB_NAME, SRM_DB_USER, SRM_DB_PASSWORD, SRM_TENANT_ID, SRM_RESERVOIR_NAME]
---

# 四预智能体 Supervisor 协同编排层 v0.4（速查卡）

> **定位**：本 skill 是四预智能体集群的**编排层**，不是新专业能力。它把已有的
> `forecasting`（预知/预报）、`early-warning`（预警）、`simulation`（预演/仿真）、
> `plan-generation`（预演/方案）、`diagnosis-verification`（工情）等 skill **当作工具**，
> 按场景 DAG 编排调用，统一维护全局 State，并在结果冲突时仲裁。
>
> **铁律**：Supervisor **不重写**任何专业能力，所有专业判断都走子 skill 的脚本/规则；
> Supervisor 只负责"顺序、状态、仲裁、断点"。

---

## 一、四类场景识别（路由）

| 场景 | 触发信号 | 对应 DAG |
|------|---------|---------|
| **A 汛期暴雨研判调度** | 超限告警 / 人工指令 / 暴雨预警 | 七步研判（见下） |
| **B 大坝安全智能诊断** | 渗流/位移/渗压异常告警 | 诊断链 |
| **C 日常精细化管控** | 定时（每日）/ 人工 | 日报链 |
| **D 应急响应** | 险情上报 / Ⅰ/Ⅱ级响应触发 | 应急链 |

**识别入口**：`scripts/scene_router.py --trigger "<用户输入/告警摘要>"` → 返回 `{scene, dag, reason}`。

## 二、场景 A 七步 DAG（核心闭环）

```
触发: 超限告警 / 人工指令
  → Step1 forecasting    雨情水情研判（降雨/水位/入库流量/风险等级）   [scripts/query_forecast_data.py --type full_context]
  → Step2 diagnosis      工情核查（渗压/渗流/位移异常）                [diagnosis-verification 脚本]
  → Step3 inspection     设备可调度性核查（闸门/启闭机/机电）          [powerelf inspection]
  → Step4 simulation     多方案洪水推演（水情边界+设备约束）           [simulation 脚本 + xaj/dispatch/routing 模型]
  → Step5 plan-gen       生成调度方案（A防洪/B综合/C兴利）            [plan-generation scripts/query_plan_data.py]
  → Step6 [仲裁]         方案 vs 仿真结果一致性检查（冲突以仿真为准）   [scripts/arbitrator.py]
  → Step7 chatbi         研判报告 + 值班台账 + 推送                    [报告模板]
```

> ⛔ **Step6 仲裁是刚性的**：plan-generation 输出的调度方案必须与 simulation
> 推演结果交叉校验——最高水位是否超汛限、下泄是否超下游安全泄量。**冲突时以仿真为准**，
> 不允许纯 LLM 臆断出方案。Step5/6 之间是 HITL 检查点：生成方案后**暂停等待人工确认**。

## 三、全局 State（SQLite 持久化）

所有阶段结果统一写入 `state/` 下的 SQLite 数据库（`supervisor_state.db`），支持断点续跑：

```sql
-- 核心表（scripts/supervisor_state.py 自动建表）
CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,        -- 事件号：A-20260805-001
    scene         TEXT NOT NULL,           -- A/B/C/D
    status        TEXT NOT NULL DEFAULT 'running',  -- running|awaiting_approval|done|aborted
    risk_level    TEXT,                    -- 高/中/低（阶段性更新）
    priority      TEXT NOT NULL DEFAULT '中',   -- 高/中/低（优先级队列排序依据，v0.4）
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stage_results (
    event_id   TEXT NOT NULL,
    stage      TEXT NOT NULL,              -- step1..step7
    agent      TEXT NOT NULL,              -- forecasting/simulation/...
    result_json TEXT,                      -- 该阶段结构化结果
    status     TEXT NOT NULL,              -- pending|ok|skipped|error
    ts         TEXT NOT NULL,
    PRIMARY KEY (event_id, stage)
);
```

**用法**：
```bash
# 新建事件（--priority 可选，缺省按场景自动映射：D=高/A·B=中/C=低）
python3 scripts/supervisor_state.py new --scene A --trigger "暴雨预警" [--priority 高]
# 写入某阶段结果
python3 scripts/supervisor_state.py set --event A-20260805-001 --stage step4 --agent simulation --result '{"max_level": 787.1}'
# 读事件全貌 / 断点续跑（列出未完成阶段）
python3 scripts/supervisor_state.py get --event A-20260805-001
python3 scripts/supervisor_state.py resume --event A-20260805-001
# 优先级队列（v0.4）：未结束事件按 优先级(高>中>低) + 创建时间 排序——多事件并行的调度视图
python3 scripts/supervisor_state.py queue
```

## 四、仲裁规则（arbitrator.py）

**通用规则（场景A）**：

| 冲突类型 | 仲裁规则 |
|---------|---------|
| 方案 vs 仿真水位 | 方案预估最高水位 > 仿真结果 → 以仿真为准（保守） |
| 方案下泄 vs 安全泄量 | 超下游安全泄量（桃曲坡 500m³/s / 三岔看 profile）→ 否决并降档 |
| 多 skill 风险等级不一致 | 取**更高**等级（防洪优先原则） |
| 预报源分歧 | 沿用 forecasting 的多源裁决（NMC>模型源>和风，反向取保守） |

**场景B 专用仲裁（`arbitrate_dam_diagnosis`，v0.4）**——风险定级 + 处置建议：

| 维度 | 定级 |
|------|------|
| 数据严重过期(>24h)或空值率>50% | 高（数据可信度不足） |
| 存在未处理缺陷 | 中（一般）/ 高（P0/P1 级） |
| 仿真最高水位超汛限 | 高 |
| 数据正常且无缺陷 | 低 |

**场景D 专用仲裁（`arbitrate_emergency`，v0.4）**——方案否决 + 超限升级 + HITL 强制：

| 规则 | 裁决 |
|------|------|
| Ⅰ/Ⅱ级告警存在 | escalate（强制升级） |
| 方案下泄 > 安全泄量 | reject（否决，重新拟定） |
| 仿真最高水位 > 汛限 | escalate（降库/预泄） |
| 其余 | pending_approval（HITL，`hitl_required=true` 恒强制） |

> 阈值（汛限/安全泄量/特征水位）**全部运行时从 reservoir profile / model_config / full_context 读取**，
> 禁止在仲裁代码里硬编码数字（与各 skill 的 C2 拦截口径一致）。

## 五、多水库适配

Supervisor 本身**无水库特定逻辑**——子 skill 已全部接入 reservoir profile
（`SRM_RESERVOIR_NAME`），编排层只透传环境变量。桃曲坡用 `SRM_RESERVOIR_NAME=taoqupo`
（tenant 20），三岔默认（tenant 18）。

## 六、输出蓝图（回答必须包含 3 段）

1. **【依据】**（开头）— 引用场景对应的法规/规范框架
2. **【编排过程】**（中间）— 各阶段执行摘要（Step1→7，每步 1-2 行结论）
3. **【校验与依据】**（结尾，**必填，必须是回答的绝对最后内容**）：
   ```
   【安全校验】最高水位 XXm，距汛限水位 {flood_limit}m 还有 Ym，[未超限/接近/超限]；
     最大下泄 XX m³/s，[低于/超过]下游安全泄量 {safe_drainage_capacity} m³/s。
   【编排状态】event={event_id} status={status}，下一步={next_stage}。
   【法规依据】依据《防洪法》第41条…
   ```

## 七、按需加载

- 场景 DAG 定义: `references/dag_order.py`（`SCENE_RULES` / `dag` 字段）
- 仲裁细则: `scripts/arbitrator.py`（`arbitrate_plan_vs_simulation` / `arbitrate_dam_diagnosis` / `arbitrate_emergency`）
- 部署与验证: `README.md`
