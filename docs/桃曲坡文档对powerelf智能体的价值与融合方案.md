# 桃曲坡文档对 powerelf 智能体的价值与三项目融合方案

**日期**: 2026-08-04
**涉及项目**: SmartTwinRes-skills（四预）、powerelf-skills（数据治理/巡检/预警/监测/BI）、桃曲坡文档资产

---

## 一、三个项目的关系定位

| 项目 | 定位 | 现状 |
|-----|------|------|
| **powerelf-skills** | 通用水利 AI Skill 平台（数据治理/巡检/预警/监测/BI），已有 `_shared` 共享层 | 通用水利层，缺具体水库领域知识 |
| **SmartTwinRes-skills** | 水库四预垂直应用（预报/预案/预演/诊断），正在做多水库扩展 | 已建 `reservoirs/{name}/` profile 机制（reservoir 抽象层） |
| **桃曲坡文档** | 水库领域知识资产（19.4万字，已结构化提取） | 知识源，待注入 |

**同构性**：三个项目都用 Hermes + Skill 架构，powerelf 的 `_shared/` 与 SmartTwinRes 的 `lib/` 是同一概念。powerelf 的 `_shared/lib/db.py` 已支持 `POWERELF_DB_* + SRM_DB_*` 双命名空间——本就设计为可共存。

---

## 二、价值映射 A：桃曲坡文档 → 数据治理智能体

**智能体现状**：已是"通用水库水利"级别（治理 st_rsvr_r/st_pptn_r/渗压/渗流/GNSS 等水利表，含 5 条 PHYSICS_RULES），但**缺桃曲坡特定层**（无 788.5/汛限/库容曲线等具体值）。

| 桃曲坡内容 | 填补的缺口 | 增强的能力 | 注入文件 |
|-----------|-----------|-----------|---------|
| 监测频次（位移/沉陷**季度**人工观测，裂缝渗流每天） | 缺失检测误报（现按 60min 默认会把季度观测判为严重缺失） | 缺失检测准确性 | `rules/missing-detection.md` 加分支 + `business_rules.md` 第7节 |
| 水位-库容-泄流曲线（8点） | 无物理一致性校验 | **新增 rz↔w↔otq 守恒校验** | `algorithm.md` 第8节 PHYSICS_RULES 追加3条 |
| 特征水位+预警阈值（主汛7-9月、Ⅳ级60mm） | 极端事件区分过宽（现 6-9月+20mm） | 极端事件校准 + 评分边界 | `algorithm.md` 第7节 + `business_rules.md` 第3节 |
| 14 站监测网（柳林+3自建+10共享） | 离线监测实体清单覆盖率仅32% | 离线监测应然集合 | 新建 `reservoir-stations.md` |
| 观测项目/精度标准 | schema 无业务观测标准 | 数据血缘/主数据 | `_shared/schema.md` 附注 |

**推荐注入模式**：新建 `references/reservoir-domain.md` 作为**可替换领域插件**——"未来切换水库只换这一份"。

---

## 三、价值映射 B：桃曲坡文档 → 智能巡检智能体（价值更高）

**智能体现状**：传感器层异常检测已体系化（5层+15维+3诊断路由+5复杂工况），但**工程结构层巡检/缺陷/处置几乎一片空白**——它知道"渗压计 P03 MAD 离群怎么诊断"，却不知道"坝体背水坡纵向裂缝怎么处置"。

| 桃曲坡内容 | 填补的缺口 | 增强的能力 | 注入文件 | 优先级 |
|-----------|-----------|-----------|---------|--------|
| **6类巡检对象×检查项**（坝体13项/放水洞/溢洪道/闸门启闭机/高边坡/机电） | `business_check_obj_type` 表骨架空 | 巡检对象知识库+关键词匹配 | `rules/data-collection-strategy.md` | **P0** |
| **9类险情处置措施**（裂缝/滑坡/渗漏/管涌/流土/护坡塌陷/集中漏水/渗水/高边坡滑坡，每类带步骤+物资） | few_shots.md 纯 SQL，零处置示例 | **few-shot 处置推荐**（最大缺口） | 新建 `references/defect-disposal-shots.md` | **P0** |
| **巡查频次表**（坝体/机电1次/天、高边坡1次/周、主汛期加密2次/天）+7人编成 | scheduling-rules.md 只有值班/班组，无对象级频次 | 任务生成/排班规则 | 新建 `rules/inspection-frequency.md` | **P0** |
| **13项真实缺陷样本**（带位置/尺寸/等级，如"高边坡护坡裂缝长19m、缝宽1.5-2.5cm"） | defect-classification.md 仅4档通用等级 | 缺陷分类真实样本+评测用例 | `defect-classification.md` + `eval_cases/` | P1 |
| **目视征兆组合判定**（滑坡三联征：下部水平位移>上部+上部垂直向下/下部向上+主缝错动） | anomaly-detection 仅5层数值时序 | **第6层：目视征兆组合判定**（跨传感器+目视） | `anomaly-detection-hierarchy.md` | P1 |

**最高杠杆单一动作**：新建 `references/dam-inspection-knowledge.md`，整合上述5类内容，在 SKILL.md 索引中引用。

**一句话**：融合后智能体从"传感器巡检"升级为"**传感器+工程结构一体化巡检**"。

---

## 四、融合架构：reservoir profile 统一机制（核心）

两个 agent 独立得出同一结论——**"新建可替换的领域知识文件"**。这不是巧合，而是揭示了三者融合的本质：

```
                 桃曲坡文档（领域知识）
                       ↓ 提取
            ┌──────────────────────┐
            │  reservoir profile   │  ← 三项目共享的水库身份+知识层
            │  (sancha/taoqupo/…)  │
            └──────────┬───────────┘
                       ↓ 激活（SRM_RESERVOIR_NAME）
   ┌───────────────────┼───────────────────┐
   ▼                   ▼                   ▼
SmartTwinRes        powerelf            powerelf
 四预skill          data-governance     inspection
 (已建profile)      (待接入profile)      (待接入profile)
```

**关键洞察**：我在 SmartTwinRes 建的 `references/reservoirs/{name}/` 分层机制，应**提升为三个项目共享的统一 profile 标准**。每个 profile 包含：

| profile 文件 | SmartTwinRes 用途 | data-governance 用途 | inspection 用途 |
|-------------|------------------|---------------------|----------------|
| `identity.md` | tenant/流域面积 | 数据隔离+主数据 | 巡检对象身份 |
| `characteristic-levels.md` | 调度特征水位 | 极端事件校准 | 缺陷判定边界 |
| `curve-data.md` | 调洪计算 | **物理一致性校验** | — |
| `stations.md` | 预报站网 | **离线监测清单** | 巡检路线锚点 |
| `inspection-items.md`（新增） | — | 监测频次规则 | **巡检对象/检查项** |
| `defect-disposal.md`（新增） | 应急处置 | — | **险情处置 few-shots** |

---

## 五、融合落地三阶段

### 阶段1（短期，1-2周）：知识注入——让两个智能体具备桃曲坡领域智能
- data-governance：新建 `reservoir-domain.md`（5类内容）+ 修改 `algorithm.md`/`missing-detection.md`
- inspection：新建 `dam-inspection-knowledge.md`（5类内容）+ 修改 `defect-classification.md`/`scheduling-rules.md`
- **此时两个智能体仍是"桃曲坡专用"，但能力补齐**

### 阶段2（中期，1-2月）：profile 机制统一——可迁移到任意水库
- 把 SmartTwinRes 的 `reservoirs/{name}/` 标准推广到 powerelf 两个智能体
- 每个 smart 的领域知识文件改为"从当前 profile 读取"
- **切换水库 = 换 profile 目录 + 改 env，代码零改动**

### 阶段3（长期，3-6月）：平台统一——powerelf 作基座，SmartTwinRes 作垂直层
- 合并 `_shared/` 与 `lib/` 共享层
- powerelf 通用智能体（治理/巡检/预警/监测）+ SmartTwinRes 四预skill = 完整水库智能体矩阵
- 统一 reservoir profile 标准，支持快速部署到任意水库

---

## 六、与当前 SmartTwinRes 多水库改造的协同

本次 SmartTwinRes 的多水库改造（阶段0-3）正在建的 `reservoirs/{name}/` profile 机制，**正是融合方案阶段2的基础**。建议：

1. **SmartTwinRes 的 profile 标准向上兼容**：在 `reservoirs/{name}/` 里新增 `inspection-items.md`、`defect-disposal.md` 两个文件，让同一份 profile 同时服务四预+治理+巡检三类智能体。
2. **桃曲坡 profile 作为标准样板**：用桃曲坡文档填充完整的 profile（含巡检/处置），作为其他水库复制的模板。
3. **powerelf 注入时引用 SmartTwinRes profile**：阶段2融合时，powerelf 智能体的领域知识直接软链/引用 SmartTwinRes 的 `reservoirs/{name}/`，避免重复维护。

---

## 七、最高杠杆行动建议

如果只做一件事：**新建桃曲坡 reservoir profile 的完整版**（含 inspection-items + defect-disposal），让它同时成为：
- SmartTwinRes 四预 skill 的知识源（阶段2已规划）
- powerelf 数据治理智能体的领域插件（注入 reservoir-domain.md）
- powerelf 智能巡检智能体的知识库（注入 dam-inspection-knowledge.md）

**一份 profile，三个项目共享**——这才是"具备扩展性，方便快速迁移部署"的终极形态。

---

*方案基于 powerelf data-governance + inspection 两份深度调研报告综合*
