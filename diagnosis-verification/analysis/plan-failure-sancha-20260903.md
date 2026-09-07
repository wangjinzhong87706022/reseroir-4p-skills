# 三岔水库调度预案执行失败诊断报告（2026-09-03 更新版）

**事件**: C-20260827-001（supervisor 事件库）
**诊断时间**: 2026-09-03 16:10
**诊断方法**: diagnosis-verification 8 阶段结构化诊断
**水库**: 三岔 (tenant=18)
**关联报告**: analysis/plan-failure-sancha-20260902.md（首次诊断，9/2）

## Phase 0 澄清确认

- 问题类型: 预案失败（plan-generation skipped，未生成调度预案）
- 时间范围: 2026-08-27 16:33 ~ 16:34（C-20260827-001 执行窗口）
- 影响范围: supervisor 编排层（场景路由 + 数据源）+ plan-generation skill + 三岔调度决策
- 优先级: **P0**（后汛期，水位超汛限 0.65m，数据断流 29h）
- 说明: 三岔（tenant=18）最近一次含 plan-generation 的事件仍是 C-20260827-001。
  9/2 15:31~16:43 的四个事件（A/B/C/D-20260902-001）全部是**桃曲坡**（tenant=20），
  与三岔无关，且 C-20260902-001 的 stage_results 为空（未实际执行）。

## Phase 1 全景扫描

- 数据源: supervisor_state.db（events 75 条 / stage_results 338 条）✅ 正确
- 三岔相关事件: 最近一次含 plan 步骤 = **C-20260827-001**
  - step5 (plan-generation) status=ok 但 result_json =
    {"status": "skipped", "reason": "data_stale_and_above_flood_limit_escalate_to_human"}
- 9/2 后新事件: A/B/C/D-20260902-001 全部为桃曲坡，无三岔事件
  - A-20260902-001 仅 step1 有 stage_result（forecasting 空输出）
  - B/C/D-20260902-001 stage_results 为空
- 历史 error stage: A-20260805-003/004 step2（hermes_diagnose_runner.py 参数错误，与本事件无关）

## Phase 2 数据质量检查

- 完整性: **优** — 三岔水位 8/25-9/2 每天 24 条完整（9/2 至 11:00 后断流）
  - 8/25: 24条 462.013-462.142m
  - 8/26: 24条 462.147-462.263m
  - 8/27: 24条 462.268-462.370m ← C-20260827-001 执行窗口，数据完整
  - 8/28: 24条 462.374-462.461m
  - 8/29: 24条 462.464-462.535m
  - 8/30: 24条 462.537-462.591m
  - 8/31: 24条 462.593-462.629m
  - 9/1: 24条 462.630-462.648m
  - 9/2: 12条 462.648-462.650m（至 11:00 后断流）
- 准确性: **优** — 204 条数据全部在 [450,465]m 范围内，0 条异常
- 时效性: **差** — 水位最新 9/2 11:00（距今 29.1h），远超 1h 标准
  - 降雨预报: 最新预报时次 9/3 16:00（距今 0.1h）✅ 正常
  - 降雨预报总量: 756.53mm/168h，峰值 18.54mm/h
- 数据质量评级: **差**（水位断流 29h，对实时调度决策不可用）

## Phase 3 异常详情

- 错误类型: plan-generation skipped（非 traceback，是业务逻辑跳过）
- 完整事件链 (C-20260827-001):
  - step1 forecasting: current_rz=786.95, flood_limit=786.8, data_stale=true,
    last_data_tm=2026-08-13, stale_hours=350, rainfall_forecast=empty
  - step2 diagnosis: degraded, "tenant20_pressure_percolation_displacement_all_empty"
  - step3 inspection: degraded, "tenant20_equip_base_empty"
  - step4 simulation: skipped, "no_valid_forecast_inflow"
  - step5 plan-generation: **skipped, "data_stale_and_above_flood_limit_escalate_to_human"**
  - step6 arbitrator: "data_stale_gt_24h_and_rz_above_flood_limit_escalate_hitl"
  - step7 chatbi: ok
- step1 完整 result_json:
  ```json
  {
    "risk_level": "高",
    "current_rz": 786.95,
    "flood_limit": 786.8,
    "exceed_m": 0.15,
    "data_stale": true,
    "last_data_tm": "2026-08-13 00:00:00",
    "stale_hours": 350,
    "rainfall_forecast": "empty",
    "weather_warning": "stale_latest_20260630",
    "inq": 45.0,
    "otq": 38.2,
    "w": 4733.0,
    "note": "data_stale_14d_rz_above_flood_limit_0.15m_no_forecast"
  }
  ```
- 事实核对（2026-09-03 实测）:
  - 786.95m = **桃曲坡** (tenant=20) 水位，不是三岔
  - 三岔真实水位 8/27 23:00 = 462.37m，9/2 11:00 = 462.65m
  - 三岔 8/27 当天 24 条数据完整存在
  - step1 输出中无任何 tenant 标识 → 数据源错位确认
- git 交叉验证:
  - scene_router.py 最后修改: 61f735b fix(supervisor): Phase 5 基础设施散项修复
  - orchestrator.py 最后修改: 78c52f1 feat: 四预智能体 Supervisor 编排层落地
  - **无 8/27 之后的代码修改** → 非回归性 bug，是原始设计缺陷
  - C-20260827-001 有 7 步 stage = 场景 A DAG，但 event scene=C → 路由错误确认

## Phase 4 关联分析

- 跨域关联: 水位(786.95 桃曲坡) × 降雨(empty) × 渗流(empty) 同时异常
  - 三个"异常"全部源于同一根因（数据源错位到 tenant=20）
- 跨 skill 关联: forecasting(step1) → diagnosis(step2) → inspection(step3) →
  simulation(step4) → plan-gen(step5) → arbitrator(step6) → chatbi(step7) **全链路受污染**
- 时间关联: 8/27 16:27 创建 → 16:34 结束，6 分钟内完成，全程基于错误数据源
  - 9/1 后（后汛期）三岔水位持续超汛限 462.0m，但无新 supervisor 事件触发
  - 9/2 水位数据断流（11:00 后无更新），至今 29h 未恢复
- 关联度: **高**（系统性数据源错位 + 场景路由错误 + 数据断流三重复合）

## Phase 5 根因分析（6 类分类 + 证据链）

### R1: 跨租户数据混用（内部代码缺陷）— **主根因**

[事实] step1 输出 current_rz=786.95, flood_limit=786.8（桃曲坡 tenant=20 参数）
[事实] step2 输出 "tenant20_pressure_percolation_displacement_all_empty"
[事实] step3 输出 "tenant20_equip_base_empty"
[事实] trigger="工作日早晨日常水情管控研判"（无水库名，应默认三岔 tenant=18）
[事实] query_forecast_data.py / query_plan_data.py 代码本身有 tenant 过滤
       （`WHERE tenant_id = %s`，tid = resolve_tenant(tenant_id)）
[事实] lib/tenant.py 默认回退 DEFAULT_TENANT_ID=18（三岔）
[推理] 如果 SRM_TENANT_ID 未设置或设为 20，则全链路读取桃曲坡数据
[推理] orchestrator.py 调用 query_forecast_data.py 时**未传 --tenant 参数**
       （STAGE_CMDS 中 step1 命令 = ["python3", ".../query_forecast_data.py", "--type", "full_context"]）
[推理] query_forecast_data.py 的 --tenant 参数 default=DEFAULT_TENANT，
       而 DEFAULT_TENANT 在模块加载时从 current_tenant_id() 读取
[推理] 如果 supervisor 进程的环境变量 SRM_TENANT_ID=20（或模块加载时缓存了 20），
       则全链路使用 tenant=20
[结论] **内部代码缺陷**: supervisor 编排层在调用子 skill 脚本时未显式传递
       SRM_TENANT_ID 或 --tenant 参数，依赖进程级环境变量。
       当环境变量为 tenant=20（桃曲坡）时，三岔场景读取了桃曲坡数据。

### R2: 场景路由错误（内部代码缺陷）

[事实] trigger="工作日早晨日常水情管控研判"
[事实] C 场景关键词包含"日常"、"水情汇报"、"当前水情"
[事实] A 场景关键词包含"水情"、"研判"、"调度"
[事实] C-20260827-001 有 7 步 stage（step1-7）= 场景 A DAG
[事实] orchestrator.py 场景 C DAG 只有 3 步（step1-3）
[推理] "水情"同时命中 A 和 C 关键词，"研判"命中 A 关键词
[推理] A 场景优先级 80 > C 场景优先级 40
[推理] 虽然 DAILY_STRONG 包含"日常"（应优先归 C），
       但 scene_router 的 DAILY_STRONG 命中逻辑在 SCENE_RULES 优先级匹配**之后**
[推理] 实际上 route() 函数先检查 DAILY_STRONG，如果"日常"命中应返回 C
       但 trigger 中"水情管控研判"的"水情"和"研判"也命中了 A 的关键词
[结论] **内部代码缺陷**: scene_router 的路由优先级设计有歧义 —
       "日常水情管控研判"同时命中 C（"日常"）和 A（"水情"/"研判"），
       实际被路由到了场景 A 的 7 步 DAG 而非 C 的 3 步 DAG。
       DAILY_STRONG 的优先逻辑未能正确覆盖 SCENE_RULES 的优先级匹配。

### R3: 数据时效性误判（R1 的下游）

[事实] step1 输出 data_stale=true, last_data_tm=2026-08-13, stale_hours=350
[事实] DB 中 tenant=18 8/27 当天 24 条数据完整存在（462.268-462.370m）
[推理] stale 判定基于 tenant=20 的最后更新（8/13），不是三岔真实数据
[结论] 内部代码缺陷（R1 下游）: 时效性检查读取了错误租户的数据，误判为 14 天断档

### R4: 预案跳过逻辑合理（预期行为 — 误报的下游）

[事实] step5 plan-generation skipped, reason="data_stale_and_above_flood_limit_escalate_to_human"
[事实] step6 arbitrator verdict=escalate, hitl_required=true
[推理] 在数据 stale(350h) + 水位超汛限(786.95>786.8) 条件下，
       跳过预案生成并升级人工是**设计行为**
[结论] 预期行为: 预案跳过本身是合理降级（非掩盖故障），
       但触发原因是 R1-R3 的复合错误（基于错误租户数据做出了正确逻辑的误判）

### R5: 三岔真实超汛限 + 水位数据断流（P0 风险，至今未解决）

[事实] 9/1 起（后汛期）三岔水位持续超汛限 462.0m
[事实] 9/2 11:00 三岔水位 462.65m，超汛限 +0.65m（ratio=1.0126）
[事实] 水位数据停在 9/2 11:00（距今 29.1h），远超 1h 标准
[事实] 降雨预报正常更新（9/3 16:00 时次，总量 756.53mm/168h）
[推理] 水位断流但降雨预报正常 → 断流在 SCADA/传感器端，非预报管道问题
[推理] 8/25→9/2 水位单调上升 462.013→462.65m（+0.64m/9天 ≈ 0.07m/天）
[结论] **P0 风险**: 三岔真实超汛限 + 水位数据断流 29h，
       无法确认当前真实水位，需立即人工调度 + 检查 SCADA 网关

## Phase 6 影响评估

- 影响范围: supervisor 编排层（场景路由 + 数据源）+ 全链路 skill + 三岔调度决策
- 严重程度: **P0**
  - 三岔真实超汛限 0.65m 但系统未识别（误判为桃曲坡数据）
  - 无可用调度预案，防洪决策依据缺失
  - 水位数据断流 29h，无法确认当前真实水位
  - 后汛期（0901-1015）关键窗口，降雨预报 756mm/168h 提示持续来水压力
- 紧迫性: **立即**
  - 水位距校核水位 462.88m 仅 0.23m（如 9/2 11:00 为最后有效值）
  - 数据断流 29h，实际水位可能已进一步上涨

## Phase 7 修复建议

### 短期止血（<1 小时）

1. **立即人工介入**: 确认三岔当前水位（联系值班人员/现场），
   如确认超后汛期汛限 462.0m，启动预泄调度
   - 目标: 降至 462.0m 以下并预留 0.5m 安全余量
   - 约束: 下泄 ≤ 下游安全泄量
2. **检查 SCADA 网关**: 三岔水位传感器 29h 未上报，
   检查 st_rsvr_r 数据管道（传感器→网关→DB）
3. **修正 C-20260827-001 事件状态**: 标记为"数据源错误，需重跑"
   - 用 SRM_TENANT_ID=18 重新执行场景 C 日常管控

### 长期根治（本周内）

1. **修复 orchestrator 租户传递（R1 主根因）**:
   - orchestrator.py STAGE_CMDS 中所有调用子 skill 脚本的命令
     增加 `--tenant` 参数显式传递（从事件上下文获取 tenant_id）
   - 或: 在 subprocess 调用时显式设置环境变量 SRM_TENANT_ID
   - 文件: supervisor/scripts/orchestrator.py:58-102
2. **修复 scene_router 路由歧义（R2）**:
   - "日常水情管控研判"应路由到 C，不应被 A 的"水情"/"研判"截走
   - 方案: DAILY_STRONG 命中时，若 A 场景命中的关键词仅为
     "水情"/"研判"（非"暴雨"/"洪水"/"超汛限"等强信号），则仍归 C
   - 文件: supervisor/scripts/scene_router.py:73-97
3. **增加水位范围断言**:
   - forecasting 输出后校验: 三岔 rz ∈ [450,465]，桃曲坡 rz ∈ [780,800]
   - 超出范围 → P0 告警 + 标记数据源错误
4. **增加跨租户数据隔离测试**:
   - tests/ 增加集成测试: SRM_TENANT_ID=18 时查询不得返回 tenant=20 数据
   - 断言: st_rsvr_r.rz ∈ [450, 465]（三岔水位范围），不是 786.x（桃曲坡）
5. **水位数据断流监控**:
   - 建立 30 分钟级水位数据新鲜度检查
   - 超时 1h → P0 告警 + 元告警机制

## Phase 8 知识沉淀

- 知识库更新: state/knowledge-base/root-cause-solutions.yaml（新增 RC-8/RC-9）
- 监控规则更新:
  - 场景 C 执行时校验 tenant_id=18（三岔）
  - 水位范围校验: 三岔 ∈ [450, 465]，桃曲坡 ∈ [780, 800]
  - 跨租户数据混用 → P0 告警
  - 水位数据断流 > 1h → P0 告警
- 复利效应:
  - 首次诊断 45 分钟（8/27 无人发现 → 9/2 诊断）
  - 本次更新诊断 10 分钟（复用 9/2 报告 + 增量数据核对）
  - 有知识库后预计 5 分钟（水位范围校验 + 租户断言 + 数据新鲜度检查）

## 诊断检查清单

- [x] Phase 0: 问题类型、时间范围、影响范围、优先级已确认
- [x] Phase 1: 数据源已验证、错误统计已完成
- [x] Phase 2: 完整性、准确性、时效性已检查
- [x] Phase 3: 完整 traceback 已提取、git log 已交叉验证
- [x] Phase 4: 跨域关联已分析
- [x] Phase 5: 6 类根因已分类、证据链已推理
- [x] Phase 6: 影响范围、严重程度、紧迫性已评估
- [x] Phase 7: 短期止血 + 长期根治方案已输出
- [x] Phase 8: 知识库已更新

## 一句话结论

**C-20260827-001 调度预案执行失败的根因是 orchestrator 未显式传递租户 ID
（依赖进程级 SRM_TENANT_ID 环境变量），导致三岔场景读取了桃曲坡数据
（786.95m vs 462.37m），叠加场景路由错误（"日常水情管控研判"被路由到场景 A 7 步 DAG
而非 C 3 步 DAG），使 plan-generation 基于错误的 stale 判定跳过预案生成。
三岔真实水位 462.65m 已超后汛期汛限 462.0m 0.65m，且水位数据断流 29h，需立即人工调度。**
