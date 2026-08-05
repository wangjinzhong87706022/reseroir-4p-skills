# 测试层多水库参数化 — 设计规格

> **日期**: 2026-08-05
> **范围**: Task #10（计划 `dynamic-hatching-piglet.md` 第 4 阶段 / 第 4 节）
> **状态**: 已确认，待实现

---

## 1. 背景与目标

`test_skills.py`（566 行单文件）当前是**三岔水库硬编码**原型：

- `TestCase.question` 全部写死"三岔水库"字样（F1-F6 / PG1-3 / SIM1-2）。
- `SkillTestRunner.run_test_case` 调用 `hermes chat` 时**未传 env** → agent 永远走默认 `tenant_id=18`，无法切换水库。
- 判定只有 `expected_keywords` 子串匹配；无防串库机制。
- 无 `tests/` 目录、无水库 profile、无 `--reservoir` 参数。

**目标**：把测试层改造成**多水库可参数化**，支持双水库回归（三岔 + 桃曲坡），并自动化防串库（跑桃曲坡时不得返回三岔数值，反之亦然）。

**成功标准**：
1. `--all-reservoirs` 下 sancha 全绿、taoqupo 静态数值全命中。
2. 全程 `forbidden_keywords` 命中数 = 0（零串库）。
3. 加一个新水库 = 加一个 yaml，不改 `test_skills.py`。

---

## 2. 架构决策：per-reservoir 独立用例集

每个水库一个完整 yaml 用例集（`tests/reservoirs/{name}.yaml`），question / expected 全部写死在该水库的 yaml 里。`test_skills.py` 读取 yaml 按水库执行，**不做模板渲染**。

**选择理由**（vs "全局模板 + per-reservoir 变量"）：简单直接、无渲染逻辑、无占位符；接受两水库用例重复的代价换取零魔法。加水库只需新增一个 yaml。

---

## 3. yaml profile schema

```yaml
# tests/reservoirs/taoqupo.yaml
name: taoqupo                       # = SRM_RESERVOIR_NAME（激活 reservoirs/taoqupo/ profile）
tenant_id: 20                       # = SRM_TENANT_ID
display_name: 桃曲坡水库             # question 文案用的中文水库名
forbidden_keywords: [三岔, 462.5, 462.88, 451]   # 防串库：此水库任何回答禁出现这些其他水库的标识
cases:
  - id: TQ-PG1
    skill: plan-generation
    description: 查询主汛限水位
    question: 桃曲坡水库的主汛限水位是多少米？
    expected_keywords: [786.8, 汛限]
    expected_range: {min: 786.5, max: 787.0}     # 可选
    timeout: 120
```

**字段语义**：
- `name` / `tenant_id`：注入 hermes 子进程的 env（见 §6）。
- `display_name`：仅供报告展示与 question 文案参考，不参与逻辑。
- `forbidden_keywords`：**profile 顶层**，自动继承到该水库全部 case。
- `cases[]`：用例数组，`id` 全局唯一（建议前缀水库缩写，如 `TQ-` / `SC-`）。
- 每个 case 的 `expected_keywords` / `expected_range` / `timeout` 均可选；`timeout` 缺省取 `--timeout`。

---

## 4. 判定逻辑（三种模式，可组合）

单个 case 判定 PASS 当且仅当**所有启用的判定都通过**：

| 判定 | 字段 | 逻辑 | 必填 |
|---|---|---|---|
| 关键词 | `expected_keywords` | 每个关键词作为子串出现在输出中（大小写不敏感） | 建议 |
| 数值区间 | `expected_range` `{min,max}` | 正则提取输出中所有数值（含小数），**有任一** ∈ [min, max] 即通过 | 可选 |
| 禁词 | `forbidden_keywords`（顶层继承） | 输出含**任一**禁词即整体 FAIL | profile 顶层必填 |

**实现细节**：
- 数值提取正则：`r'-?\d+\.?\d*'`，逐个 `float()` 后检查是否落在区间。容忍 agent 输出"786.80m""约 786.8"等表述。
- forbidden 命中时，结果状态直接置 FAIL，并在报告里标红该禁词（便于定位串库来源）。
- 关键词判定沿用现有 `_verify_output` 大小写不敏感逻辑。

---

## 5. 用例集

### 5.1 sancha.yaml（迁移现有用例，内容不变）
把 `FORECASTING_TESTS`(F1-F6) / `PLAN_GENERATION_TESTS`(PG1-3) / `SIMULATION_TESTS`(SIM1-2) 原样搬进 yaml。三岔实时数据齐全，全部保留。示例：
```yaml
name: sancha
tenant_id: 18
display_name: 三岔水库
forbidden_keywords: [桃曲坡, 786.8, 788.5, 790.5, 788.54]
cases:
  - {id: SC-F1, skill: forecasting, description: 查询当前水位,
     question: 查询三岔水库当前水位（只返回数值）,
     expected_keywords: [462, 水位, m], timeout: 60}
  - {id: SC-F3, skill: forecasting, description: 查询汛限水位,
     question: 当前三岔水库的汛限水位是多少？,
     expected_keywords: [汛限, 水位], timeout: 60}
  # ... F2/F4-F6, PG1-3, SIM1-2 同理
```

### 5.2 taoqupo.yaml（只列静态数据类用例）
桃曲坡 tenant=20 **实时表为空**（`st_rsvr_r` / `st_pptn_r` count=0），实时类用例（当前水位 / 降雨预报 / 气象预警 / 时效）会失败，**不列**。只列走静态表（`model_config` / `att_res_*` / 曲线）的用例：

| id | skill | 问题要点 | expected |
|---|---|---|---|
| TQ-PG1 | plan-generation | 主汛限水位 | keywords:[786.8,汛限] range:[786.5,787.0] |
| TQ-PG2 | plan-generation | 设计/校核洪水位 | keywords:[788.54,790.5] |
| TQ-PG3 | plan-generation | 校核洪水位总泄量 | keywords:[2331] range:[2300,2340] |
| TQ-PG4 | plan-generation | 校核洪水位库容 | keywords:[4420] range:[4400,4450]（防误读 5720） |
| TQ-F1 | forecasting | 主汛限水位 | keywords:[786.8,汛限] range:[786.5,787.0] |
| TQ-SIM1 | simulation | 特征水位/配置查询 | keywords:[786.8] |

> **TQ-PG4 的意义**：identity.md 已做总库容口径消歧（5720 设计值 / 4420 实测，DB 与调洪用 4420）。此用例固化"agent 必须答 4420"，回归保护消歧注不被回退。

---

## 6. hermes 身份注入（关键 bug 修复）

现有 `run_test_case` 的 `subprocess.run(cmd, cwd=skill_dir)` 漏掉 `env` 参数 → 子进程继承 shell 默认 env，agent 永远 `tenant_id=18`。改为显式注入水库身份：

```python
env = {
    **os.environ,
    "SRM_TENANT_ID": str(profile["tenant_id"]),
    "SRM_RESERVOIR_NAME": profile["name"],
}
result = subprocess.run(cmd, capture_output=True, text=True,
                        timeout=test_case.timeout,
                        cwd=str(skill.skill_dir),
                        env=env)
```

这是多水库测试能成立的前提——与本次手工端到端验证（`export SRM_TENANT_ID=20 ...`）等价的程序化注入。

---

## 7. CLI

| 参数 | 说明 |
|---|---|
| `--reservoir sancha\|taoqupo` | 指定单水库；默认读 `SRM_RESERVOIR_NAME` env，再缺省 `sancha` |
| `--all-reservoirs` | 跑 `tests/reservoirs/*.yaml` 全部（双水库回归） |
| `--tenant N` | 覆盖当前水库的 tenant_id（调试用） |
| `--skill` / `--test-case` | 保留，限定到当前水库的子集 |
| `--list` | 改为**按 reservoir 分组**列出 |
| `--timeout` / `--report-format` / `--output` | 保留 |

**向后兼容**：旧 `--all`（无 reservoir 语义）映射为"当前水库的全部 skill"；真正双水库回归用 `--all-reservoirs`。

---

## 8. 回归策略与报告

- `--all-reservoirs`：遍历 `tests/reservoirs/*.yaml`，每个水库依次跑其 cases。
- 报告按 **(reservoir × skill)** 两级分组统计（pass/fail/timeout/error/forbidden_hits）。
- 结果 JSON 落盘 `results/{reservoir}/skills-test-results-{timestamp}.json`。
- 退出码：任一 case FAIL/TIMEOUT/ERROR/forbidden 命中 → exit 1，全绿 → exit 0（便于 CI 判定）。

---

## 9. 文件清单

- **改** `test_skills.py`：
  - `TestCase` 加 `expected_range` 字段（可选）
  - `SkillTestRunner`：加 yaml profile 加载、`env` 注入、`forbidden_keywords` + `expected_range` 判定、reservoir 维度的报告分组
  - `main()`：加 `--reservoir` / `--all-reservoirs`，`--list` 按水库分组
- **新** `tests/reservoirs/sancha.yaml`（迁移 F1-F6 / PG1-3 / SIM1-2）
- **新** `tests/reservoirs/taoqupo.yaml`（§5.2 表）

---

## 10. YAGNI 取舍（明确不做）

- **不做** question 模板渲染（已选独立用例集）。
- **不做** `skip` 字段机制（实时类用例直接不列入桃曲坡 yaml 即可；未来实时数据接入后再加用例）。
- **不扩到 5 skill**（early-warning / diagnosis-verification 加用例是独立工作，不在本任务范围）。
- **不引入** Jinja2 / 新依赖（pyyaml 6.0.3 已装，沿用）。

---

## 11. 验证方法

```bash
# 单水库
set -a; source /root/.hermes/.env; set +a
python3 test_skills.py --reservoir sancha --timeout 300
python3 test_skills.py --reservoir taoqupo --timeout 300

# 双水库回归（最终验收）
python3 test_skills.py --all-reservoirs --timeout 300
```

**通过判据**：
- sancha：F/PG/SIM 用例全 PASS。
- taoqupo：TQ-* 静态用例全 PASS（数值命中 786.8 / 788.54 / 790.5 / 2331 / 4420）。
- forbidden_keywords：两水库全程 0 命中。
- 退出码 0。

---

## 12. 决策记录

1. **用例组织** = per-reservoir 独立集（用户选定，偏好简单无渲染）。
2. **桃曲坡实时类用例** = 不列（实时表 t20 全空）。
3. **forbidden_keywords** = profile 顶层、继承全部 case（防串库核心）。
4. **expected_range** = 可选、正则提数、任一落区间即过（容忍中文表述）。
5. **hermes env 注入** = 必须修复（多水库测试成立的前提）。
