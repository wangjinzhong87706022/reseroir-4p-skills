# plan-generation 多水库接入试点 — 现网验证清单

> **验证目标**：确认 `feat/multi-reservoir` 分支的 plan-generation 接入改造在现网正常工作。
> **分支**：`feat/multi-reservoir`（需先 `git checkout feat/multi-reservoir`）

---

## ⚠️ 先理解：现在能验证什么

桃曲坡的**数据库记录尚未录入**（任务9 未做），因此：

| 能完整验证 | 不能完整验证 |
|---|---|
| ✅ 三岔回归不破（默认行为不变） | ❌ 桃曲坡 DB 查询返回真实数据（需先录入） |
| ✅ profile 文件被 agent 正确读取（知识问答类） | |
| ✅ tenant 参数化代码路径生效（SQL 用对的 tenant） | |
| ✅ CLI `--tenant` 覆盖 | |

> 即：`SRM_TENANT_ID=19` 的 DB 查询会返回**空**——这是预期，不是 bug。完整端到端需等任务9 录入桃曲坡数据。

---

## 前置：切到 feature 分支 + 确认数据库凭据

```bash
cd /home/scada/SmartTwinRes-skills
git checkout feat/multi-reservoir
git log --oneline -3   # 应看到 85e5218 / 5e073b2 / 26dd84b 三个 commit

# 确认数据库凭据已配（现网应有）
env | grep SRM_DB
# 若无，按 DB-CONFIG-STANDARD.md 配 SRM_DB_HOST/PORT/NAME/USER/PASSWORD
```

---

## 场景 1：三岔回归不破（最重要）

**目的**：确认改造没破坏现有三岔功能。

```bash
# 方式A：不设 env（默认回退 tenant=18, reservoir=sancha）
unset SRM_TENANT_ID SRM_RESERVOIR_NAME

# 方式B：或显式设三岔
export SRM_TENANT_ID=18 SRM_RESERVOIR_NAME=sancha

# 跑 hermes 问一个常规调度问题
hermes chat -q "查询当前水位和汛限水位" --skills plan-generation
```

**✅ 通过**：返回三岔数据（水位 ~459m 量级、汛限 462.5m 附近），与改造前一致。
**❌ 失败**：报错 / 返回空 / tenant 相关异常 → 改造破坏了默认路径，需排查。

---

## 场景 2：桃曲坡 profile 被正确读取（机制核心）

**目的**：确认 agent 会读 `reservoirs/taoqupo/` 而非用三岔值或编造。

```bash
export SRM_RESERVOIR_NAME=taoqupo
hermes chat -q "桃曲坡水库的汛限水位（主汛/次汛）、设计洪水位、校核洪水位、死水位分别是多少？" --skills plan-generation
```

**✅ 通过**：返回 **786.80 / 788.00 / 788.54 / 790.50 / 755 m**（来自 `reservoirs/taoqupo/characteristic-levels.md`）。
**❌ 失败**：
- 返回 462.5（三岔值）→ profile 路由没生效，agent 仍用旧示例数字
- 编造数字 → agent 没读 profile
- 报找不到文件 → 检查 `reservoirs/taoqupo/` 是否存在、INDEX.md 路径

---

## 场景 3：tenant 参数化代码路径

**目的**：确认脚本按 `SRM_TENANT_ID` 查询，不再硬编码 18。

```bash
# 3a. 切桃曲坡 tenant（DB 无数据，预期返回空，验证的是 SQL 用了 19）
export SRM_TENANT_ID=19
python3 plan-generation/scripts/query_plan_data.py --type config
# 预期：返回 {} （空，因 DB 无 tenant=19 数据）—— 关键是没报错、没返回三岔的 config

# 3b. 显式覆盖回 18，应返回三岔 config
python3 plan-generation/scripts/query_plan_data.py --type config --tenant 18
# 预期：返回三岔的 max_water_level / safe_drainage_capacity 等
```

**✅ 通过**：3a 返回空（tenant=19 生效）、3b 返回三岔 config（--tenant 覆盖生效）。
**❌ 失败**：3a 返回了三岔 config → 说明仍硬编码 18，参数化没生效。

> 进阶：若想看实际 SQL，可在脚本里临时 print 或查 DB 慢日志，确认 `WHERE tenant_id = 19`。

---

## 场景 4（可选）：曲线/水位 profile 知识

```bash
export SRM_RESERVOIR_NAME=taoqupo
hermes chat -q "桃曲坡水库在校核洪水位790.5m时的总泄量是多少？正常蓄水位788.5m的库容是多少？" --skills plan-generation
```

**✅ 通过**：790.5m 总泄量 **2331 m³/s**、788.5m 库容 **3949 万 m³**（来自 `curve-data.md`）。

---

## 判断总结

| 场景 | 验证点 | 通过标志 |
|---|---|---|
| 1 | 三岔回归 | 三岔数据正常返回 |
| 2 | profile 读取 | 桃曲坡水位 786.8/790.5 等 |
| 3 | tenant 参数化 | tenant=19 返空、--tenant 18 返三岔 |
| 4 | 曲线 profile | 2331 / 3949 |

**四个全过 = 接入机制端到端验证成功**，可放心推广到其他 4 个 skill。

---

## 常见问题排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 场景2 返回三岔值 | agent 没读 profile（INDEX/SKILL 路由没生效） | 确认 `SRM_RESERVOIR_NAME` 已 export；检查 hermes 是否重新加载了 SKILL.md |
| 脚本报 `from lib.tenant import` 失败 | lib 不在 path | 确认从项目根跑，或脚本经 query_utils（已加项目根 path） |
| 场景3 报 DB 连接错 | 凭据未配 | 配 SRM_DB_* |
| hermes 不识别新 env | 进程未重启 | 重启 hermes 服务使 env 生效 |

---

## 验证完成后

- **全过**：告诉我结果，我继续推广到其他 4 个 skill + 做任务9（数据录入 SQL）。
- **有问题**：把报错/异常输出贴给我，我来修。
- 现网验证期间**不要** `git checkout` 回 clean-main，保持在 `feat/multi-reservoir`。
