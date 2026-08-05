# Supervisor 协同编排层（四预智能体落地）

> **状态**: v0.2.0 —— 四场景（A/B/C/D）全部实测跑通（2026-08-05）
> **定位**: 把 forecasting / early-warning / plan-generation / simulation / diagnosis-verification 等专业 skill 编排成自动化闭环，非新专业能力。

## 已实现能力

| 模块 | 文件 | 能力 |
|------|------|------|
| 场景识别 | `scripts/scene_router.py` | 四类场景路由（A暴雨研判/B大坝诊断/C日常管控/D应急），关键词表 + 强信号词（应急/日常优先） |
| 全局 State | `scripts/supervisor_state.py` | SQLite 事件持久化（event_id + 阶段结果 + 断点续跑 + HITL状态） |
| 结果仲裁 | `scripts/arbitrator.py` | 方案vs仿真一致性、下泄vs安全泄量、风险等级取高（防洪优先） |
| 设备核查 | `scripts/inspection_check.py` | **真实数据源**：设备清单/异常/缺陷/离线/闸门状态（按 tenant 过滤） |
| DAG 编排 | `scripts/orchestrator.py` | 四场景 DAG 一键执行 / 断点续跑 / 单阶段调试 / HITL 检查点 |
| DAG 定义 | `references/dag_order.py` | 四场景步骤顺序（A七步/B五步/C三步/D五步） |

## 快速使用

```bash
# 环境（桃曲坡 tenant 20；三岔默认无需设）
export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml \
       SRM_DB_USER=root SRM_DB_PASSWORD=*** SRM_TENANT_ID=20 SRM_RESERVOIR_NAME=taoqupo

# 1. 一键编排（场景识别→建事件→执行 DAG）
python3 supervisor/scripts/orchestrator.py run \
  --trigger "暴雨预警，水位超汛限" --flood-limit 786.8 --safe-discharge 500

# 2. HITL：方案生成后暂停等确认，确认后续跑
python3 supervisor/scripts/orchestrator.py resume --event A-20260805-004 --approve

# 3. 单独调试某个阶段
python3 supervisor/scripts/orchestrator.py stage --event <id> --stage step1
```

## 已验证闭环（2026-08-05，桃曲坡 tenant 20）

### 场景 A：汛期暴雨研判调度（七步）— 事件 `A-20260805-004` ✅ done

| 步骤 | 数据源 | 结果 |
|------|--------|:----:|
| step1 forecasting | query_forecast_data.py full_context | ✅ 连库 |
| step2 diagnosis | **check_data_quality.py --type all**（水位/降雨/告警质量核查） | ✅ 连库 |
| step3 inspection | **inspection_check.py --type all**（128台设备/异常/缺陷/离线/闸门） | ✅ 连库 |
| step4 simulation | query_simulation_data.py full_context（汛限786.8m） | ✅ 连库 |
| step5 plan-gen | query_plan_data.py full_context（含MOCK气象预警） | ✅ 连库 |
| step6 [仲裁] | arbitrator：方案vs仿真一致 → accept | ✅ |
| step7 chatbi | 研判报告模板 | ✅ |

### 场景 B：大坝安全智能诊断（五步）— 事件 `B-20260805-001` ✅ done

step1 diagnosis（数据质量）→ step2 inspection（缺陷核查）→ step3 simulation（推演）→ step4 仲裁 → step5 诊断报告

### 场景 C：日常精细化管控（三步）— 事件 `C-20260805-001` ✅ done

step1 forecasting（水情）→ step2 simulation（蓄水节律）→ step3 日报台账

### 场景 D：应急响应（五步）— 事件 `D-20260805-001` ✅ done

step1 early-warning（高级别告警）→ step2 plan-gen（应急方案）→ step3 simulation（推演校验）→ step4 仲裁+HITL → step5 应急报告

## 场景识别修复记录

- **问题**：v0.1 中"每日例行水情汇报"因"水情"关键词命中场景A（优先级80 > C的40）被误判为暴雨研判。
- **修复**：v0.2 增加强信号词机制——应急强词（险情/溃坝/管涌/闸门故障/抢险/漫坝）→ 场景D；日常强词（每日/例行/日报/定时/周报）→ 场景C。已回归验证四类场景全部正确。

## 已知差距（下阶段）

| 项 | 现状 | 计划 |
|----|------|------|
| step7 报告 | 模板占位 | 接 chatbi 生成台账/推送 |
| 仲裁阈值 | CLI 传入（--flood-limit / --safe-discharge） | 自动读 reservoir profile |
| 场景B/D 仲裁 | 复用 plan-vs-sim 仲裁 | 细化诊断定级/应急处置专用仲裁规则 |
| 多事件并行 | 单事件顺序执行 | 支持并发事件与优先级队列 |

## 桃曲坡数据时效方案（2026-08-05 落地）

桃曲坡（tenant 20）模拟实时数据由 `forecasting/data/generate_taoqupo_data.py` 维护，
配合 supervisor 闭环形成"数据→研判→方案"全链路可演示：

| 数据 | 表 | 状态 |
|------|-----|:----:|
| 水位/入库/出库/蓄水 | `st_rsvr_r`（stcd=TQP, 720h） | ✅ 已入库 |
| 实测降雨 | `st_pptn_r`（TQPSN 枢纽 + TQPLL 柳林, 各720h） | ✅ 已入库 |
| 降雨预报 | `f_rnfl_h`（未来168h, 峰值22mm/h） | ✅ 已入库 |
| master stcd | `model_config`（st_rsvr_r_master=TQP / st_pptn_r_master=TQPSN） | ✅ 已更新 |

**数据时效（cron 已部署，每50分钟）**：

```bash
# 手动：断点续写 + 预报滚动（cron 即此命令）
SRM_TENANT_ID=20 python3 forecasting/data/generate_taoqupo_data.py --roll --forecast

# 手动：全量重建30天（--clean 先清 mock 再生成）
SRM_TENANT_ID=20 python3 forecasting/data/generate_taoqupo_data.py --clean
SRM_TENANT_ID=20 python3 forecasting/data/generate_taoqupo_data.py --forecast --days 30
```

- `--roll`：读 `st_rsvr_r` 断点（MOCK 数据 MAX(tm)）续写到 NOW，数据已最新则跳过（幂等）
- `--forecast`：重建 f_rnfl_h 未来168h 降雨预报（峰值 22mm/h 暴雨场景）
- crontab：`*/50 * * * * flock /tmp/taoqupo-sim.lock ... --roll --forecast`（flock 防重叠）
- 清理：`--clean` 按 creator='MOCK' 删除，不污染真实数据

**full_context 验证结果（2026-08-05）**：

```json
{"current_water_level": {"status": "ok", "stcd": "TQP", "rz": 786.794, "inq": 55.0, ...},
 "rainfall_forecast": {"source": "f_rnfl_h", "count": 48, "data": [{"YMDH": "2026-08-06 09:00:00", "RN": 22.0}, ...]},
 "flood_limit": {"value": 786.8, "source": "att_res_flse_lim(主汛期)"}}
```

> ⚠️ 模拟数据均为 `creator='MOCK'` 标记；现网真实数据到位后，`--clean` 清模拟数据、
> 把 master stcd 换成真实测站编码即可无缝切换（见 `forecasting/data/generate_taoqupo_data.py` 参数注释）。

## 目录结构

```
supervisor/
├── SKILL.md                    # skill 速查卡（场景/State/仲裁/输出蓝图）
├── README.md                   # 本文件（落地状态）
├── scripts/
│   ├── scene_router.py         # 场景识别（关键词 + 强信号）
│   ├── supervisor_state.py     # SQLite State 持久化
│   ├── arbitrator.py           # 结果仲裁
│   ├── inspection_check.py     # 设备可调度性核查（真实数据源）
│   └── orchestrator.py         # DAG 编排主脚本（四场景）
├── references/
│   └── dag_order.py            # 四场景 DAG 步骤定义
└── state/
    └── supervisor_state.db     # 运行时生成（事件/阶段结果）
```
