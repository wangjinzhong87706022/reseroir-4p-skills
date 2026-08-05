# 三岔水库 — 特征水位与预警阈值

> **profile**: sancha（tenant_id=18）
> **数据来源**: plan-generation/tests/test-questions.md（水库基础信息参考表）、forecast-rules.md 参考值
> **说明**: 从现有测试用例/规则文档的硬编码值抽取。水位基面 ~460m。

---

## 特征水位（高程基准：~460m 量级）

| 特征水位 | 高程(m) | 来源 |
|---|---|---|
| 死水位 | 451.000 | test-questions.md |
| 正常蓄水位 / 汛限 | 462.500 | test-questions.md / 多处 fallback |
| 设计洪水位（百年一遇） | 461.960 | test-questions.md |
| 校核洪水位（千年一遇） | 462.880 | test-questions.md |
| 当前水位（测试样本） | ~459.18 | test-questions.md |

> ⚠️ 三岔的"汛限=正常蓄水位=462.5"（无主汛/次汛分段），与桃曲坡（主汛786.8/次汛788.0）不同。如三岔实际有汛期分段，请 DBA/业务核对后修正本 profile 与 att_res_flse_lim。

---

## 泄流约束

| 项 | 值 |
|---|---|
| 最大泄流能力 | 192 m³/s |
| 下游安全泄量 | 95.1 m³/s |

---

## 水位-库容曲线（dispatch_model/flood_routing 兜底，三岔简化数据）

> 来源: plan-generation/models/dispatch_model.py DEFAULT_WL_CURVE（451–468m）
> 这也是多水库改造前模型层 fallback 的三岔专属曲线，现已加废弃警告。

| 水位(m) | 库容(万m³) | | 水位(m) | 泄量(m³/s) |
|---|---|---|---|---|
| 451.0 | 3900 | | 451.0 | 0 |
| 455.0 | 5200 | | 453.0 | 20 |
| 458.0 | 6455 | | 455.0 | 80 |
| 462.0 | 8723 | | 458.0 | 87 |
| 462.5 | 9064 | | 462.0 | 99 |
| 465.0 | 10819 | | 462.5 | 94 |
| 468.0 | 14500 | | 468.0 | 500 |

> 完整曲线见 `plan-generation/models/dispatch_model.py`（行 249-264）。

---

## 待补

以下三岔信息在现有 skill 中缺失或未结构化，建议后续从三岔正式预案/规程补充：
- 预警阈值（24h/6h 面雨量分级）— 现有 forecast-rules.md 的 339.x 值疑似另一站/基面，需核对
- 洪峰分级
- 监测站网清单
- 巡检对象/检查项/险情处置（可复用桃曲坡模板结构，填三岔实测值）

> sancha 的巡检类 profile（inspection-items / defect-disposal）暂未建——三岔若需智能巡检能力，可复制 `reservoirs/taoqupo/` 对应文件结构后填入三岔数据。
