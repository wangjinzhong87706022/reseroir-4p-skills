# 三岔水库最近一次调度预案执行失败 — 根因诊断报告

**诊断时间**: 2026-09-10 21:35 CST
**诊断对象**: 三岔水库（tenant_id=18, sancha）
**失败事件**: C-20260827-001（最近一次含 plan-generation 的三岔调度执行）
**优先级**: P1（P0 为伴生安全问题，见根因 2）
**诊断方法**: 8 阶段结构化诊断（diagnose）

---

## 一、Phase 0：澄清确认

- **问题类型**: 预案执行失败（调度预案跳过/未产出）
- **时间范围**: 2026-08-27（失败事件）→ 2026-09-10（本次复核）
- **影响范围**: supervisor 场景路由 → forecasting → plan-generation（三岔租户）
- **优先级**: P1（预案缺失导致超汛限调度无系统支撑）

## 二、Phase 1：全景扫描

| 检查项 | 结果 |
|--------|------|
| 数据源 | `dispatch_history` / `supervisor state` / 知识库（✅ 无混用） |
| 模型服务 18081/18082/18083 | ✅ 全部 /health 200 健康 |
| 三岔 8 月以来调度执行批次 | **0 次**（dispatch_history 无写入） |
| 最近一次三岔 plan 执行 | **C-20260827-001**（2026-08-27，step5 plan-generation skipped） |
| 知识库匹配 | ✅ 命中 C-20260827-001 条目（status=待执行，**修复未落地**） |

## 三、Phase 2：数据质量检查

| 维度 | 结果 | 评级 |
|------|------|------|
| 完整性 | stcd=3 主站每小时 1 条连续写入（21:00 最新，滞后 21min ✅） | 良 |
| 准确性 | **❌ 伪造交替**：459.18/462.65 两值严格奇偶交替，inq/otq 同步两值交替（47 次跳变/48h） | 差 |
| 时效性 | 水位 ✅ <1h；**降雨主站 stcd=46 无数据**（st_pptn_r 三岔最新记录停在 6 月） | 差 |

## 四、Phase 3：异常详情

C-20260827-001 执行轨迹（来源：知识库证据 + 当时 supervisor state）：

```
trigger = "工作日早晨日常水情管控研判"（应为场景 C）
step1 forecasting    → current_rz = 786.95   ← ❌ 桃曲坡（tenant 20）水位！
step2 diagnosis      → "tenant20_pressure_percolation_displacement_all_empty"
step3 inspection     → "tenant20_equip_base_empty"
step5 plan-generation → skipped
  reason = "data_stale_and_above_flood_limit_escalate_to_human"
```

失败直接原因：plan-generation 读取到 786.95m（桃曲坡水位）> 三岔任何汛限值，
判"超汛限 + 数据陈旧"，走升级人工分支并跳过预案生成。
但三岔当天（8/27）DB 中 24 条真实数据完整存在（462.27-462.37m）——**不是数据缺失，是数据读错了租户**。

## 五、Phase 4：关联分析

- **跨域关联**: 水位(786.95) × 诊断(tenant20_empty) × 巡检(tenant20_empty) 同时指向 tenant=20 → 复合问题，非单点故障
- **跨 skill 关联**: scene_router（路由错）→ forecasting（读错租户）→ plan-generation（跳过）
- **关联度**: 高（三个 skill 同一根因传导）
- **伴生问题**: 三岔真实水位 462.65m 超后汛期汛限 462.0m（att_res_flse_lim，0901-1015），
  系统全程未识别 → 调度决策缺位

## 六、Phase 5：根因分析

### 根因 1（主因）: 跨租户数据混用 + 场景路由错误
**分类**: 内部代码缺陷

```
[事实1] trigger "工作日早晨日常水情管控研判" 未命中场景 C 规则
        scene_router.py:57 关键词表 = [日报,例行,日常,值班,汇报,水情汇报,巡检,台账,
        今天情况,当前水情,状态] —— 不含 "管控研判"（scene_router.py 当前代码仍无此词，
        2026-09-10 实测确认修复未落地）
[事实2] 该事件实际走了场景 A 的 7 步 DAG（知识库证据：C-20260827-001 有 7 步）
[事实3] forecasting/diagnosis/inspection 查询未正确按 tenant_id=18 过滤，
        读到 tenant=20 的 786.95m
[事实4] plan-generation 对 786.95m 判超汛限 → skipped
[推理] 路由错（C→A）+ 租户过滤缺失（18→20）两个缺陷叠加，
       导致预案步骤基于错误租户数据做出"超汛限"误判
[结论] 根因 = 内部代码缺陷（租户过滤缺失 + 场景路由错误）
```

### 根因 2（伴生 P0）: 三岔主站水位数据伪造
**分类**: 数据问题（不修代码，转工单）

```
[事实] stcd=3 自 2026-08-03 起仅 459.18/462.65 两值交替（Δ3.47m/h），
       inq/otq 同步两值交替，持续至 2026-09-10 21:00（本次复核实测）
[推理] 模拟器/测试数据源持续写入生产表 st_rsvr_r
[结论] 即使路由和租户修复，预案输入数据仍不可信
```

### 根因 3（放大因素）: flood_limit 模块 bug
**分类**: 内部代码缺陷

```
[事实] att_res_flse_lim 表无 deleted 列，lib/flood_limit.py 查询报错
       → 回退 att_res_base.fl_low_lim_lev=462.5m（主汛期值）
[推理] 9/1-10/15 后汛期权威汛限是 462.0m，回退值偏松 0.5m
[结论] 汛限判断系统性偏松（P1，影响所有依赖汛限的 skill）
```

## 七、Phase 6：影响评估

| 维度 | 评估 |
|------|------|
| 影响范围 | 三岔（tenant 18）全部调度预案能力；8/27 至今 0 次成功调度执行 |
| 严重程度 | P1（预案缺失）+ P0 伴生（真实超汛限 0.65m 未识别） |
| 紧迫性 | 9 月处于后汛期（0901-1015），汛限 462.0m，水位 462.65m 已超限 |

## 八、Phase 7：修复建议

### 短期止血（P0/P1，今日）
1. **[P0] 人工介入调度**: 三岔 462.65m > 汛限 462.0m，按《防洪法》启动预泄调度（系统不可依赖）
2. **[P0] 停伪造数据写入**: 排查 2026-08-03 起 stcd=3 写入源，隔离模拟器
3. **[P1] 修 scene_router**: DAILY_STRONG/场景 C 关键词增加 "管控研判"、"管控"
4. **[P1] 修租户过滤**: forecasting/diagnosis/inspection 的 st_rsvr_r 查询强制 `tenant_id = current_tenant_id()`，
   并加水位值域校验（三岔 ∈ [450,465]，超出即拒收）

### 长期根治（P2，本周）
1. 修复 `lib/flood_limit.py`: att_res_flse_lim 查询去掉 deleted 列引用（或给表补列）
2. 跨租户隔离测试: SRM_TENANT_ID=18 时查询返回 tenant=20 数据必须 fail（加入 tests/）
3. supervisor step 间传递结构化上下文（water_level/tenant_id），下游 skill 禁止独立重查库
4. 数据新鲜度 SLA 监控进 inspection_check.py（水位 1h / 降雨 6h / 告警 24h）

## 九、Phase 8：知识沉淀

- 知识库条目 C-20260827-001 已存在（root-cause-solutions.yaml:197），status 维持"待执行"
- 本次复核（2026-09-10）确认: **修复未落地**（scene_router 实测无 "管控研判"；8 月以来 0 次调度执行）
- 新增关联: 主站水位伪造（根因 2）+ flood_limit bug（根因 3）已在 9/3、9/8 诊断中记录

## 验证（verify 6 层摘要）

| Layer | 结果 |
|-------|------|
| L1 数据源 | ✅ 正确（dispatch_history/supervisor state/知识库），无 skill 混用 |
| L2 格式 | ✅ 三段式完整，证据均标注来源 |
| L3 业务规则 | ✅ 数值范围合理（786.95 属桃曲坡值域，462.65 属三岔值域） |
| L4 安全约束 | ⚠️ 462.65 > 462.0 超汛限 0.65m → P0 升级人工（本报告已声明） |
| L5 跨域一致性 | ✅ 786.95 与 tenant=20 数据吻合；三岔 8/27 真实值 462.27-462.37 吻合 |
| L6 法规 | ✅ 引用《防洪法》、att_res_flse_lim 权威汛限 |

**诊断结论**: 根因可信，证据链完整，可进入 auto-fix（Step 1-2 已完成：诊断完整 + 知识库命中，匹配度 >90%）。

---
*诊断执行: diagnosis-verification skill, 8 阶段全部完成*
*复核脚本: _tmp_model_health.py / _tmp_final_verify.py / _tmp_find_event.py*
