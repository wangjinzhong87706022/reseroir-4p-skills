# Reservoir Profile 标准（水库知识层规范）

> **定位**：本目录是水库领域知识的**单一事实源**，按水库分目录组织。
> 一份 profile 同时服务 SmartTwinRes 四预 skill 和（联邦模式下）powerelf 的数据治理/智能巡检智能体。
>
> **激活方式**：环境变量 `SRM_RESERVOIR_NAME`（如 `taoqupo`）决定当前使用哪个 profile。
> 切换水库 = 改 env + 换 profile 目录，**代码零改动**。

---

## 目录结构（每个水库一套）

```
reservoirs/
├── README.md              # 本规范
├── sancha/                # 三岔水库（tenant_id=18，原型）
└── taoqupo/               # 桃曲坡水库（tenant_id=19，目标）
    ├── identity.md              # 水库身份与基础参数
    ├── characteristic-levels.md # 特征水位 + 预警阈值
    ├── curve-data.md            # 水位-库容-泄流曲线
    ├── stations.md              # 监测站网
    ├── inspection-items.md      # 巡检对象×检查项（智能巡检用）
    └── defect-disposal.md       # 险情处置措施（智能巡检 few-shots）
```

---

## 文件职责与消费方

| 文件 | 内容 | SmartTwinRes 四预 | powerelf 数据治理 | powerelf 智能巡检 |
|------|------|:---:|:---:|:---:|
| `identity.md` | tenant_id、流域面积、总库容、坝型、枢纽组成 | ✅ 调度身份 | ✅ 数据隔离/主数据 | ✅ 巡检对象身份 |
| `characteristic-levels.md` | 汛限/设计/校核/死水位、预警阈值、洪峰分级 | ✅ 调度约束 | ✅ 极端事件校准 | ✅ 缺陷判定边界 |
| `curve-data.md` | 水位-库容-泄流关系表 | ✅ 调洪计算 | ✅ 物理一致性校验 | — |
| `stations.md` | 水文站/雨量站主数据 | ✅ 预报站网 | ✅ 离线监测清单 | ✅ 巡检路线锚点 |
| `inspection-items.md` | 6类巡检对象×检查项清单 | — | ✅ 监测频次规则 | ✅ 巡检知识库 |
| `defect-disposal.md` | 9类险情处置措施+物资 | ✅ 应急处置 | — | ✅ 处置 few-shots |

---

## 分层判据（什么内容进 profile，什么不进）

| 归属 profile | 归属 skill 的 common/ |
|---|---|
| 物理量值（水位 m、流量 m³/s、库容、曲线点） | 法规条文（GB/SL） |
| 标识符（tenant_id、stcd、站名、GUID） | 通用公式（水量平衡、调洪演算） |
| 专有名词（河名、工程名、机构） | 通用算法（MAD、插值） |
| 水库特定阈值（汛限、预警级别） | 通用规则骨架（用 `{占位符}` 的 IF/ELIF） |

**反硬编码护栏**：skill 的 common 规则文件**禁止**出现具体水库数值，所有数值必须引用本 profile。推广自 forecasting 已有的"C2 拦截清单"机制。

---

## 数据时效性

| 数据类型 | 时效 | 更新触发 |
|---|---|---|
| 工程基础参数（identity） | 中长期 | 工程改造后 |
| 特征水位/曲线 | 年度 | 除险加固/淤积测量后 |
| 监测站网 | 低频 | 站点增减 |
| 巡检/处置知识 | 低频 | 预案修订（年度） |

> 桃曲坡 profile 数据来源：2026 年防洪抢险应急预案、汛期调度运用计划、调度规程、大坝安全鉴定报告（OCR）。
