# 三岔水库调度预案执行失败 — 根因诊断报告

**诊断日期**: 2026-09-11
**租户**: 18（三岔水库）
**优先级**: P0
**诊断阶段**: 8 Phase 完整覆盖

---

## Phase 0：澄清确认

| 项目 | 确认值 |
|------|--------|
| 问题类型 | 调度预案执行失败（srm_flood_history_base status=3） |
| 时间范围 | 2025-09-24 ~ 2026-09-11（最近一次失败更新 2026-01-23） |
| 影响范围 | forecasting / plan-generation / simulation / early-warning 全链路 |
| 优先级 | **P0**（真实监测数据缺失 74 天，MOCK 数据污染调度决策） |

---

## Phase 1：全景扫描

### 数据源验证

| Skill | 正确数据源 | 实际数据源 | 状态 |
|-------|-----------|-----------|------|
| forecasting | `query_forecast_data.py` | st_rsvr_r (无 eq_code 过滤) | ❌ **混用** |
| plan-generation | `query_plan_data.py` | st_rsvr_r (无 eq_code 过滤) | ❌ **混用** |
| simulation | `query_simulation_data.py` | st_rsvr_r (无 eq_code 过滤) | ❌ **混用** |

### 错误统计

| 类别 | 数量 | 说明 |
|------|------|------|
| srm_flood_history_base status=3（执行失败） | **2 条** | id=16（2025年6月洪水）、id=9（2018年第一场次洪水） |
| st_rsvr_r 真实监测数据缺失 | **74 天** | 606K215502 最后更新 2026-05-29，606K215303 最后更新 2026-06-07 |
| st_rsvr_r MOCK 数据污染 | **935 条** | eq_code='sancha'，2026-08-03 起，creator='MOCK' |
| ew_info_message 未确认告警 | **1165 条** | 57% 未确认，606K 占 79% |
| supervisor 事件（三岔） | **0 条** | 三岔从未接入 supervisor 编排 |

---

## Phase 2：数据质量检查

### 完整性

| 数据类型 | 覆盖率 | 缺失率 | 评级 |
|---------|--------|--------|------|
| 真实水位（606K215502） | 2026-01-11 ~ 2026-05-29 | **74 天断更** | ❌ 差 |
| 真实水位（606K215303） | 2026-01-11 ~ 2026-06-07 | **66 天断更** | ❌ 差 |
| MOCK 水位（sancha） | 2026-08-03 ~ 2026-09-11 | 39 天 | ✅ 覆盖 |
| 降雨预报（f_rnfl_h） | MOCK 标记 | 无真实数据源 | ⚠️ 中 |
| 告警（ew_info_message） | 最后 2026-06-09 | **93 天无新告警** | ❌ 差 |

### 准确性

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 水位值范围 | ✅ 459.18-462.65m（合理） | st_rsvr_r eq_code='sancha' |
| 水位交替模式 | ❌ **每小时跳变 459.18↔462.65** | 48h 内 47 次跳变 >1m |
| 入库流量 | ❌ **恒定 15.0 / 43.3** | 与水位交替同步，非真实水文过程 |
| 出库流量 | ❌ **恒定 90.5 / 135.1** | 同上 |
| 蓄水量 | ❌ **恒定 7124 / 9169** | 同上 |
| 预报精度（MOCK） | ⚠️ MAPE 4.5-6.5% | forecast_accuracy_record 全为 MOCK |

### 时效性

| 数据类型 | 最后更新 | 最大允许延迟 | 状态 |
|---------|---------|------------|------|
| 真实水位 | 2026-05-29 16:55 | 1 小时 | ❌ **超时 4517h** |
| MOCK 水位 | 2026-09-11 09:00 | — | ✅ 最新（但非真实） |
| 告警 | 2026-06-09 10:49 | 24 小时 | ❌ **超时 721h** |
| 降雨预报 | MOCK | 6 小时 | ⚠️ 无真实源 |

### 数据质量评级：**差**

> **核心问题**：真实监测数据完全断更（74 天），当前唯一"活"的水位数据是 MOCK 生成器写入的 459.18/462.65 每小时交替值。所有 skill 的查询脚本无 eq_code 过滤，直接消费了 MOCK 数据作为真实水位。

---

## Phase 3：异常详情

### 完整错误上下文

**错误 1：srm_flood_history_base id=16（2025年6月洪水）执行失败**

```
表: srm_flood_history_base
id=16, name="2025年6月洪水", status=3（执行失败）
create_time: 2025-12-25 11:28:41
update_time: 2026-01-23 13:41:46
adjusted_water_level: null  ← 未设置调整水位（输入缺失）
target_water_level: 460.0
data_source: 1
agent_task_id: null  ← 无 agent 任务关联
```

- srm_flood_history_result 中 flood_id=16 的记录数：**0 条**（无任何计算结果）
- rainfall_data 包含 2025-06-01 ~ 2025-06-03 逐时降雨（60-65mm/h 持续 48h）
- 最后一条降雨 YMDH=1764518400000 → **2025-11-30**（时间戳异常，应为 2025-06-02）

**错误 2：srm_flood_history_base id=9（2018年第一场次洪水）执行失败**

```
表: srm_flood_history_base
id=9, name="2018年第一场次洪水", status=3（执行失败）
create_time: 2025-09-24 14:19:52
update_time: 2025-12-25 11:22:49
adjusted_water_level: 458.0
target_water_level: 458.0
data_source: 1
agent_task_id: null
```

- srm_flood_history_result 中 flood_id=9 有结果但 **outPeakFlow=0.0、sumDischargeVolume=0.0**
- 预报闸门开度全为 0.0（24h）
- 预报出库流量全为 0.0（24h）
- 说明：模型未正确计算泄洪过程，入库 319.44m³/s 但出库为 0

### git log 交叉验证

| commit | 日期 | 关联 |
|--------|------|------|
| `49082e9` | 2026-08-06 | **feat(sancha): 三岔水库接入——汛限tenant过滤修复 + 模拟数据生成器** |
| `f23f277` | 2026-08-06 | **fix(sancha): 三岔四场景实测修复——生成器断点续写 + 报告阶段映射** |
| `aa9cb7b` | 近期 | fix(plan-generation): 调度时长按降雨历时分类 |
| `5a7d6ea` | 近期 | refactor(lib): 三处汛限查询统一为 lib.flood_limit.current_flood_limit |

**首次出现**：MOCK 数据生成器 `generate_sancha_data.py` 在 `49082e9`（2026-08-06）引入，`f23f277` 修复断点续写。此后 MOCK 数据持续写入 st_rsvr_r。

**历史同类问题**：
- 2026-09-02 起 145h+ 数据冻结（DV1 假超时根因，generate_sancha_data.py 注释中已记录）
- 三岔 606K 雨量站（606K2148/2149/2150/2155）数据停在 2026-05-29，66 天断更（已知问题）

---

## Phase 4：关联分析

### 跨域关联

| 关联维度 | 发现 | 严重度 |
|---------|------|--------|
| 水位 × 降雨 × 渗流 | 渗压/渗流数据全租户最新 2026-08-23（tenant 20=0 行），三岔无工情监测数据 | ⚠️ 中 |
| 水位交替 × 汛限 | MOCK 交替高水位 462.65m > 后汛期汛限 462.0m（超出 0.65m），触发"接近超汛限"假象 | ❌ 高 |
| MOCK 数据 × 调度决策 | 所有 skill 无 eq_code 过滤 → MOCK 459.18/462.65 被当作真实水位消费 | ❌ **P0** |
| 告警 × 设备离线 | 1165 条未确认告警（57%），606K 占 79%，全部断更 5/29，告警引擎无离线检测 | ❌ 高 |

### 跨 skill 关联

```
forecasting ──→ plan-generation ──→ simulation ──→ arbitrator ──→ 报告
     │                │                  │
     ▼                ▼                  ▼
  st_rsvr_r        st_rsvr_r         st_rsvr_r
  (MOCK 459.18/    (MOCK 459.18/     (MOCK 459.18/
   462.65 交替)     462.65 交替)      462.65 交替)
     │
     ▼
  f_rnfl_h (MOCK 降雨预报)
```

**三个 skill 消费同一份 MOCK 数据**，导致：
- forecasting 的"当前水位"在 459.18 和 462.65 之间跳变
- plan-generation 的调度预案基于跳变水位生成
- simulation 的预演结果基于跳变初始条件
- arbitrator 的仲裁结论基于不一致的仿真/预案水位

### 时间序列关联

```
2026-05-29  606K215502 真实水位最后更新（rz=459.18）
2026-06-07  606K215303 真实水位最后更新
2026-06-09  最后一条告警（606K2157 level=3）
   ↓ 74 天真空期
2026-08-03  MOCK 数据生成器开始写入（eq_code='sancha', creator='MOCK'）
2026-09-08  MOCK 正弦波结束，进入 459.18/462.65 每小时交替模式
2026-09-11  诊断执行时（当前）
```

---

## Phase 5：根因分析

### 6 类根因分类

| # | 根因 | 分类 | 证据链 |
|---|------|------|--------|
| **RC-1** | **真实监测数据断更 74 天** | **数据问题** | 606K215502 最后 2026-05-29，606K215303 最后 2026-06-07。[事实] 水位数据源完全断更。[推理] 无真实数据 → 系统失去调度依据。[结论] 数据断更是执行失败的上游根因，**不修代码，转工单给监测设备 Owner** |
| **RC-2** | **MOCK 数据生成器污染生产数据表** | **内部代码缺陷** | generate_sancha_data.py 向 st_rsvr_r 写入 creator='MOCK' 数据（935 条）。[事实] MOCK 数据与真实数据混存于同一表。[推理] 查询脚本无 eq_code/creator 过滤 → MOCK 被当真实数据消费。[结论] 数据隔离缺失是 P0 代码缺陷，**精确修改查询脚本加过滤** |
| **RC-3** | **查询脚本无 eq_code/creator 过滤** | **内部代码缺陷** | query_forecast_data.py / query_plan_data.py / query_simulation_data.py 均无 eq_code 过滤。[事实] 三个 skill 消费同一份 MOCK 数据。[推理] 水位在 459.18/462.65 间跳变 → 调度决策不稳定。[结论] **精确修改三个查询脚本，加 eq_code 白名单 + creator 过滤** |
| **RC-4** | **flood_id=16 输入数据缺失** | **数据问题** | adjusted_water_level=null，agent_task_id=null，flood_result 0 条。[事实] 输入不完整。[推理] 模型无法执行 → status=3。[结论] 转工单，补全输入数据 |
| **RC-5** | **flood_id=9 模型计算异常** | **内部代码缺陷** | inPeakFlow=319.44 但 outPeakFlow=0.0，闸门开度全 0。[事实] 入库有流量但出库为 0。[推理] 泄流模型未正确计算闸门开启过程。[结论] 检查 flood-routing 模型的闸门调度逻辑 |
| **RC-6** | **告警引擎无离线检测** | **内部代码缺陷** | 1165 条未确认告警堆积，设备断更 74 天无告警。[事实] 告警引擎只检测阈值，不检测设备离线。[推理] 数据断更 → 无告警 → 人工无法及时发现。[结论] 增加设备离线告警规则 |

### 根因优先级

| 优先级 | 根因 | 修复方向 |
|--------|------|---------|
| **P0** | RC-2 + RC-3（MOCK 污染 + 无过滤） | 立即修复查询脚本 + 清理 MOCK 数据 |
| **P0** | RC-1（真实数据断更 74 天） | 转工单给监测设备 Owner |
| **P1** | RC-5（flood_id=9 模型计算异常） | 修复泄流模型 |
| **P1** | RC-6（告警引擎无离线检测） | 增加离线检测规则 |
| **P2** | RC-4（flood_id=16 输入缺失） | 补全输入数据 |

### 区分"掩盖故障"和"合理降级"

| 行为 | 类型 | 判断 |
|------|------|------|
| 查询脚本不过滤 MOCK 数据，直接消费 | ❌ **掩盖故障** | MOCK 数据不是合理降级，是数据隔离缺失 |
| 真实数据断更后自动切换到 MOCK 源 | ✅ **合理降级** | 前提：有降级日志 + 标记 + 人工确认机制 |
| 告警引擎不检测离线 | ❌ **掩盖故障** | 设备离线是严重故障，不应静默 |

---

## Phase 6：影响评估

### 影响范围

| 维度 | 影响 |
|------|------|
| Skill | forecasting / plan-generation / simulation / early-warning **全部 4 个** |
| 场景 | 场景 A（防洪调度）/ B（数据质量）/ C（预报）/ D（告警）全部受影响 |
| 用户 | 水库调度员（基于错误水位做决策）、防汛值班员（告警堆积无法确认） |
| 场景 | **汛期**（后汛期 0901-1015，当前 9/11 处于后汛期） |

### 严重程度

- **P0**：真实数据断更 + MOCK 污染 → 调度决策基于虚假数据
- **P1**：告警堆积 1165 条 → 防汛响应能力下降
- **P2**：flood_id=16/9 历史洪水计算失败 → 预案库不完整

### 紧迫性

**高** — 当前处于后汛期（0901-1015），MOCK 交替水位 462.65m 已超后汛期汛限 462.0m，若调度员基于此数据决策，可能触发错误的预泄/限泄操作。

---

## Phase 7：修复建议

### 短期止血（立即执行，<1 小时）

1. **清理 MOCK 数据**
   ```sql
   DELETE FROM st_rsvr_r WHERE tenant_id=18 AND creator='MOCK';
   ```
   效果：消除 459.18/462.65 交替数据，查询脚本将返回"无数据"而非"错误数据"

2. **标记数据断更**
   - 在 ew_info_message 中插入数据断更告警（level=1，P0）
   - 通知调度员：真实水位数据自 2026-05-29 起断更

3. **暂停基于 MOCK 数据的自动调度**
   - 设置 supervisor 配置：tenant 18 的 plan-generation 阶段增加数据质量前置检查
   - 若 st_rsvr_r 无 creator<>'MOCK' 的数据 → 中止调度，转人工

### 长期根治（本周内完成）

1. **修复查询脚本数据隔离（P0）**
   - `query_forecast_data.py`：加 `AND creator<>'MOCK' AND eq_code IN ('606K215502','606K215303')`
   - `query_plan_data.py`：同上
   - `query_simulation_data.py`：同上
   - 或统一在 `lib/db.py` 的 `execute_query` 中加全局 MOCK 过滤（推荐）

2. **修复真实数据断更（P0）**
   - 联系监测设备 Owner 排查 606K215502 / 606K215303 断更原因
   - 转工单：设备断更 74 天，需要现场检修

3. **修复 flood_id=9 泄流模型（P1）**
   - 检查 flood-routing 模型的闸门调度逻辑
   - 输入 inPeakFlow=319.44m³/s 但 outPeakFlow=0.0 → 闸门未开启
   - 可能原因：闸门调度策略配置错误或缺失

4. **增加设备离线告警（P1）**
   - ew_info_rules 增加离线检测规则：
     - 水位数据 >1h 未更新 → level=2 告警
     - 水位数据 >6h 未更新 → level=1 告警
     - 告警引擎增加"数据时效"维度（当前只有"阈值"维度）

5. **补全 flood_id=16 输入数据（P2）**
   - adjusted_water_level=null → 补设为 460.0（与 target_water_level 一致）
   - 重新触发计算

6. **MOCK 数据隔离架构（P2）**
   - 将 MOCK 数据写入独立表（st_rsvr_r_mock）或加独立 tenant_id
   - generate_sancha_data.py 改为写入隔离表
   - 查询脚本默认不读 MOCK 表，仅演示模式读取

---

## Phase 8：知识沉淀

### 知识库条目

```yaml
# state/knowledge-base/root-cause-solutions.yaml
- id: SANCHA-MOCK-CONTAMINATION-20260911
  problem: 三岔水库 MOCK 数据污染 st_rsvr_r，查询脚本无 eq_code/creator 过滤
  root_cause:
    - generate_sancha_data.py (commit 49082e9) 向生产表写入 MOCK 数据
    - 查询脚本无数据源隔离
  symptoms:
    - st_rsvr_r 水位 459.18/462.65 每小时交替
    - 入库/出库/蓄水量恒定（15.0/90.5/7124 和 43.3/135.1/9169）
    - srm_flood_history_base status=3（执行失败）
  fix:
    immediate:
      - DELETE FROM st_rsvr_r WHERE tenant_id=18 AND creator='MOCK'
      - 标记数据断更告警
    long_term:
      - 查询脚本加 eq_code 白名单 + creator 过滤
      - MOCK 数据隔离到独立表
      - 增加设备离线告警规则
  related:
    - 三岔 606K 雨量站断更 66 天（2026-05-29 起）
    - 1165 条未确认告警（57%），606K 占 79%
  first_seen: "2026-08-03"
  diagnosed: "2026-09-11"
  resolution_time_estimate: "首次 48min → 有知识库后 15min"
```

### 监控规则更新

```yaml
# state/infrastructure-config/alert-rules.yaml
- rule: sancha_data_freshness
  description: 三岔水库真实水位数据时效
  condition: st_rsvr_r 无 creator<>'MOCK' 数据 >1h
  level: 2
  action: 通知调度员
- rule: sancha_mock_detection
  description: 检测 MOCK 数据混入生产表
  condition: st_rsvr_r 中 creator='MOCK' 占比 >50%
  level: 1
  action: P0 告警 + 暂停自动调度
```

---

## 诊断检查清单

- [x] **Phase 0**：问题类型、时间范围、影响范围、优先级已确认
- [x] **Phase 1**：数据源已验证（❌ 混用）、错误统计已完成
- [x] **Phase 2**：完整性（❌ 差）、准确性（❌ 差）、时效性（❌ 差）已检查
- [x] **Phase 3**：完整错误上下文已提取、git log 已交叉验证
- [x] **Phase 4**：跨域关联（水位×汛限×MOCK）、跨 skill 关联（4 个 skill 全受影响）已分析
- [x] **Phase 5**：6 类根因已分类、证据链已推理
- [x] **Phase 6**：影响范围（全链路）、严重程度（P0）、紧迫性（后汛期）已评估
- [x] **Phase 7**：短期止血 + 长期根治方案已输出
- [x] **Phase 8**：知识库已更新

### 最终答复

时效性/完整性评分：**差**（真实水位断更 74 天，MOCK 数据污染，告警 93 天无更新）

**短期止血**：
1. 清理 st_rsvr_r 中 tenant_id=18 的 MOCK 数据
2. 标记数据断更告警（P0）
3. 暂停基于 MOCK 数据的自动调度

**长期根治**：
1. 查询脚本加 eq_code 白名单 + creator 过滤（P0）
2. 联系监测设备 Owner 排查断更原因（P0）
3. 修复 flood-routing 模型闸门调度逻辑（P1）
4. 增加设备离线告警规则（P1）
5. MOCK 数据隔离到独立表（P2）
