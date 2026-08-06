# Hermes 平台与 Supervisor 架构边界说明

> 创建日期：2026-08-06
> 关联文档：[多Agent集群方案评估与Supervisor落地.md](./多Agent集群方案评估与Supervisor落地.md)、[四预智能体深入分析报告.md](./四预智能体深入分析报告.md)、[code-analysis-2026-08-06.md](./code-analysis-2026-08-06.md)
> 目的：明确 Hermes Agent（平台）与 supervisor（业务编排层）的职责边界，沉淀"平台原语需求清单"，指导后续演进。

---

## 一、背景与动机

在代码评审与优化讨论中，一个反复出现的问题是：

> **"仲裁结果落 State""断点续跑""HITL 检查点"这些功能，不应该是 Hermes Agent 平台提供的吗？为什么 supervisor 要自己实现？**

本文件的结论是：

- **短期**：Hermes 当前未提供任何工作流编排原语，supervisor 在业务层自建 SQLite State 是**正确且必要**的补位，不是重复造轮子。
- **长期**：State 持久化、断点续跑、阶段执行这类**通用机制**值得平台化（workflow API），届时 supervisor 可回归"只写 DAG 和仲裁规则"的纯粹业务形态。

---

## 二、架构分层总览（现状）

```
┌─────────────────────────────────────────────────────────────┐
│  Hermes Agent（平台：LLM 执行环境）                           │
│  · 加载 Skill / 调用 LLM / 执行脚本（execute_code、subprocess）│
│  · 单轮对话（hermes chat -q "..." --skills forecasting）      │
│  · 不感知任何水务业务概念（无 DAG / State / 仲裁 / 汛限）       │
└──────────────────────────────┬──────────────────────────────┘
                               │ 被当作执行引擎调用
┌──────────────────────────────▼──────────────────────────────┐
│  supervisor（业务编排层）                                    │
│  · 场景识别（scene_router）→ DAG 定义（dag_order）            │
│  · 跨 skill 调度（orchestrator）→ 结果仲裁（arbitrator）       │
│  · 全局 State（SQLite：events / stage_results）              │
│  · 断点续跑 + HITL 检查点 + 优先级队列                        │
└──────────────────────────────┬──────────────────────────────┘
                               │ 当作工具调用
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
  forecasting           plan-generation          simulation
  early-warning         diagnosis-verification   （5 个专业 skill）
```

---

## 三、Hermes 平台职责边界（现状，以代码为准）

| 能力 | 是否由 Hermes 提供 | 证据 |
|------|:---:|------|
| Skill 加载 | ✅ | `hermes chat -q "..." --skills forecasting`（README） |
| LLM 调用 | ✅ | hermes chat CLI |
| 脚本/代码执行 | ✅ | execute_code、subprocess（各 SKILL.md） |
| 单轮/多轮对话 | ✅ | hermes chat |
| 工作流编排（DAG） | ❌ | supervisor 自建 `references/dag_order.py` |
| 全局 State 持久化 | ❌ | supervisor 自建 `scripts/supervisor_state.py`（SQLite） |
| 阶段执行与结果记录 | ❌ | supervisor 自建 `execute_dag` + `stage_results` 表 |
| 断点续跑 | ❌ | supervisor 自建 `cmd_resume` |
| HITL 人工确认 | ❌ | supervisor 自建 `awaiting_approval` 状态机 |
| 结果仲裁 | ❌ | supervisor 自建 `scripts/arbitrator.py` |

**证据示例**：`diagnosis-verification/scripts/hermes_diagnose_runner.py` 中 Hermes 的调用方式是 `subprocess` 运行 CLI 并解析 stdout——Hermes 对调用方来说就是一个"能说话、能跑脚本"的执行引擎，**不感知 events 表、不感知"仲裁"、不感知"汛限水位"**。

---

## 四、supervisor 业务职责边界（现状）

supervisor 定位（`supervisor/SKILL.md`）：**四预智能体集群的编排层，不是新专业能力**。铁律：Supervisor **不重写**任何专业能力，所有专业判断走子 skill 的脚本/规则；Supervisor 只负责 **"顺序、状态、仲裁、断点"** 四件事。

| 职责 | 实现 | 性质 |
|------|------|------|
| 场景识别 | `scene_router.py`（关键词路由 A/B/C/D） | 业务规则（领域关键词表） |
| DAG 定义 | `references/dag_order.py`（四场景步骤顺序） | 业务规则（四预流程） |
| 跨 skill 调度 | `orchestrator.py`（execute_dag 按序调用子 skill） | 业务规则（调用编排） |
| 结果仲裁 | `arbitrator.py`（方案 vs 仿真 / 风险取高 / 超限否决） | **纯业务规则**（水务约束） |
| 全局 State | `supervisor_state.py`（SQLite events/stage_results） | ⚠️ 通用机制，**目前被迫自建** |
| 断点续跑 | `cmd_resume`（已完成 stage diff 待跑） | ⚠️ 通用机制，**目前被迫自建** |
| HITL 检查点 | `awaiting_approval` 状态 + `--approve` 续跑 | ⚠️ 通用机制，**目前被迫自建** |
| 优先级队列 | `cmd_queue`（高>中>低 + 创建时间） | 业务规则（调度优先级） |

**三类职责的边界判断标准**：

1. **纯业务规则**（必须留在 supervisor）：仲裁规则、DAG 顺序、场景关键词、优先级映射——这些是水库调度领域知识，平台无论如何都不该内置（否则 Hermes 就从通用平台退化为水务专用平台）。
2. **通用机制**（适合平台化）：State 持久化、断点续跑、阶段执行、HITL 暂停——这些是任何多 Agent 工作流都需要的抽象，与业务无关。
3. **领域数据模型**（留在 supervisor，但可建立在平台原语之上）：`stage_results` 表的字段语义（agent/status/result_json）来自四预流程，但"表怎么存、怎么恢复"应该是平台的事。

---

## 五、理想分工 vs 现状对比

| 层 | 该提供什么（理想） | 现状 | 差距 |
|----|-------------------|------|------|
| **Hermes（平台）** | 通用 workflow API：阶段定义、State 读写、resume 钩子、HITL 暂停原语、事件持久化 | 只有 chat + 脚本执行 | **大**：无任何工作流抽象 |
| **supervisor（业务）** | 只用平台原语定义 DAG + 仲裁规则 + 领域数据模型 | 被迫自建 SQLite 全套 | 中：SQLite 代码与业务耦合 |

**理想形态示例**（若 Hermes 提供 workflow API）：

```python
# 业务只管 DAG 和仲裁，State/断点/持久化全部交给平台
wf = hermes.workflow.start(scene="A")          # 平台创建事件并持久化
wf.run(steps=DAG_ORDER["A"])                   # 平台按序执行、记录阶段结果
wf.set_stage("step6", arbitrate_result)        # 平台写入 stage_results
wf.pause_for_approval("step6")                 # 平台提供 HITL 原语
wf.resume(approve=True)                        # 平台恢复执行
```

此时 supervisor 代码量可缩减约一半（`supervisor_state.py` 大部分逻辑下沉平台），仲裁等业务逻辑保持不变。

---

## 六、平台原语需求清单（给 Hermes 的演进建议）

若 Hermes 后续演进，建议按优先级提供以下原语（按通用性从高到低）：

| 优先级 | 原语 | 说明 | 现状替代实现 |
|:---:|------|------|------------|
| P0 | `workflow.start(scene, trigger)` | 创建工作流实例并持久化 | `supervisor_state.cmd_new` |
| P0 | `workflow.stage.set(stage, result)` | 写入阶段结果（原子、可恢复） | `INSERT OR REPLACE INTO stage_results` |
| P0 | `workflow.stage.status` | 阶段状态查询（ok/error/pending/skipped） | `SELECT ... FROM stage_results` |
| P1 | `workflow.resume(event_id)` | 断点续跑（已完成 stage diff 待跑） | `cmd_resume` + `DAG_ORDER` |
| P1 | `workflow.pause_for_approval(stage)` | HITL 暂停 + 续跑钩子 | `awaiting_approval` 状态机 |
| P1 | `workflow.artifacts` | 大结果落盘（解决 result_json 40000 字符截断） | `[:40000]` 硬截断 |
| P2 | `workflow.queue` | 多事件优先级队列调度 | `cmd_queue` |
| P2 | `workflow.event.retry` | 失败事件重放 | `cmd_replay` |

**注意**：以上只是"建议平台化"的候选清单，不代表当前必须做。在 Hermes 提供这些原语之前，supervisor 自建实现保持现状即可——这是平台能力不足时的正常补位。

---

## 七、演进路径建议

| 阶段 | 动作 | 触发条件 |
|------|------|---------|
| **现在** | supervisor 自建 SQLite State 保持现状；修复 L2（仲裁结果落 State）等业务层缺陷 | 无 |
| **中期** | 若 Hermes 提供 workflow 原语 → 将 supervisor_state 的持久化/恢复逻辑迁移到平台 API，业务只留 DAG + 仲裁 | Hermes 侧发布 workflow API |
| **长期** | supervisor 组件化：scene_router / arbitrator 可独立成可配置规则包（支持按水库定制仲裁规则） | 多水库场景增长后 |

---

## 八、结论

1. **"仲裁结果落 State"是 supervisor 的业务职责**——仲裁规则是纯水务业务（方案 vs 仿真一致性、下泄 vs 安全泄量、风险等级取高），平台不应内置；而"结果要落 State"这一动作目前因平台缺 workflow API，由 supervisor 自己实现，是正常补位。
2. **真正值得平台化的是通用机制**：State 持久化、断点续跑、HITL 暂停、阶段执行。这些与业务无关，任何多 Agent 工作流都需要。
3. **边界判断口诀**：**"规则留业务，机制给平台"**——仲裁规则、DAG 顺序、场景关键词是规则；持久化、恢复、暂停、重放是机制。
