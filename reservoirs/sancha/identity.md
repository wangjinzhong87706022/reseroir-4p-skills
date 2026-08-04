# 三岔水库 — 身份与基础参数

> **profile**: sancha（原型水库，tenant_id=18）
> **数据来源**: 现有 skill 硬编码值 + test-questions.md 参考值
> **说明**: 本 profile 从原 SmartTwinRes-skills 散落的硬编码数值抽取归集，作为多水库改造的回归基准。

---

## 基本信息

| 项 | 值 |
|---|---|
| 水库名称 | 三岔水库 |
| tenant_id | 18 |
| 管理单位 | （现网 powerelf_srm_yml 库） |
| 工程定位 | 原型/基准水库（sl323 区域河道站数据对照） |

---

## 流域与库容

| 项 | 值 |
|---|---|
| 流域面积 | 161.25 km²（xaj_model 默认值） |
| 总库容 | 22870 万 m³（test-questions.md 参考） |
| 水位量级 | ~460m（三岔水位基面；与桃曲坡 ~788m 不同基面） |

---

## 枢纽参数（调度模型默认/fallback）

| 项 | 值 | 来源 |
|---|---|---|
| 水位 master stcd | 3 | model_config.st_rsvr_r_master |
| 雨量 master stcd | 46 | model_config.st_pptn_r_master |
| 最大泄流能力 | 192 m³/s | model_config.max_drainage_capacity |
| 下游安全泄量 | 95.1 m³/s | model_config.safe_drainage_capacity |

---

## 数据库定位

| 项 | 值 |
|---|---|
| 数据库 | powerelf_srm_yml（与桃曲坡等共用，按 tenant_id 隔离） |
| 对照数据源 | sl323（全区域河道站：古运河、邗沟等，非三岔调度用） |

> ⚠️ 三岔水位 ~460m 与 sl323 站 ~240m 不在同一高程基准，混用会导致调度决策错误——这正是各 skill "数据源优先级"铁律的由来。
