# 知识库索引（预报场景）

> **用途**：Agent 根据问题类型，选择读取对应的知识文件
> **规则**：遇到以下场景时，先读取对应文件再回答
> **自洽**：本索引引用的所有文件均在 `references/` 目录下实际存在（skill-auditor C1 校验项）

---

## 索引表

| 场景 | 触发关键词 | 读取文件 |
|------|-----------|---------|
| **表结构/字段** | "字段"、"表结构"、"哪张表"、"f_rnfl_h 列名"、"有无 deleted"、"taskid 拼写" | `table-schema.md` |
| **SQL 拼接** | "查询模板"、"怎么查"、"参数化"、"forecast_timeline"、"fusion_detail" | `sql-templates.md` |
| **预警等级判定** | "蓝色预警"、"黄色预警"、"橙色预警"、"红色预警"、"预警等级"、"趋势预警"、"339.0" | `forecast-rules.md` |
| **置信度/精度** | "置信度"、"高/中/低"、"MAPE"、"合格率"、"准不准"、"精度" | `forecast-rules.md` |
| **影响估算** | "估算值"、"±20%"、"预计最高水位"、"洪峰到达"、"影响多大" | `forecast-rules.md` |
| **多源降雨** | "多源"、"四个源"、"NMC"、"和风"、"分区"、"对齐"、"分歧"、"源报的不一样" | `multi-source-fusion.md` |
| **NMC fixture** | "NMC"、"diamond14"、"等值面"、"JSONP"、"fixture"、"typhoon.nmc.cn" | `multi-source-fusion.md` |
| **法规标准** | "防洪法"、"GB/T 22482"、"SL 250"、"水文情报预报规范"、"精度评定" | `knowledge-base.md` |
| **预报精度评定** | "合格率"、"MAPE 标准"、"许可误差"、"20%"、"0.3m" | `knowledge-base.md` |
| **特征水位** | "汛限"、"设计洪水位"、"校核洪水位"、"462.5"、"461.96"、"462.88" | `table-schema.md`（参考值） + `forecast-rules.md`（规则3） |
| **特征水位不一致** | "339 和 462 对不上"、"阈值基准"、"高程基准" | `table-schema.md`（末尾说明） + `forecast-rules.md`（字段读取约定） |
| **tenant/deleted 策略** | "tenant"、"租户"、"deleted"、"软删除"、"f_rnfl_h 不过滤" | `table-schema.md`（用法规则1-2） |
| **taskid JOIN** | "taskid"、"CAST JOIN"、"varbinary"、"下划线"、"关联" | `table-schema.md`（用法规则4） |

---

## 使用方法

```
用户问题："未来 24 小时降雨预报准不准？要不要预泄？"

Agent 判断:
  - 关键词"准不准" → 精度/置信度 → 读 forecast-rules.md（置信度模型）
  - 关键词"24 小时降雨" → 多源降雨 → 读 multi-source-fusion.md（四源融合）
  - 关键词"预泄" → 影响估算 → 读 forecast-rules.md（规则6 触发区间估算）

Agent 操作:
  1. 调 query_forecast_analysis.py --type accuracy_report 获取 MAPE
  2. 调 query_forecast_analysis.py --type fusion_detail 获取多源对齐
  3. 读 references/forecast-rules.md 第三节（置信度模型）+ 第四节（影响估算）
  4. 读 references/multi-source-fusion.md 第二节（融合判定）
  5. 综合输出: 等级 + 置信度 + 【估算值 ±20%】区间(若触发) + 数据源明细
```

---

## 文件清单（C1 自洽校验对象）

| 文件 | 行数级 | 主要内容 |
|------|--------|---------|
| `table-schema.md` | ~280 | 14 张预报表结构 + 6 条用法规则 + 特征水位参考 |
| `sql-templates.md` | ~230 | 19 个参数化模板（Q1–Q12 / J1–J4 / A1）+ 适用速查 |
| `forecast-rules.md` | ~190 | 9 条 IF/ELIF 规则（等级/置信度/影响/分歧）+ C2 拦截清单 |
| `multi-source-fusion.md` | ~170 | 四源对齐表 + 融合推理框架 + NMC fixture 说明 |
| `knowledge-base.md` | ~210 | 法规标准（GB/T 22482 等）+ 精度评定原则 + 待核事项 |
| `INDEX.md` | 本文件 | 场景/关键词 → 文件路由 |

> **C1 校验**：以上 6 个文件均实际存在于 `references/` 目录。任何 SKILL.md 引用的 references 下文件必须在此清单内，否则 skill-auditor C1（self-contained）失败。

---

## 注意事项

1. **先读再答**：遇到上述场景，先读取对应文件，不要凭记忆回答
2. **阈值动态读**：所有数值阈值（339.x / 462.x / 50mm / 20mm 等）从 `full_context` / `model_config` 字段读取，**严禁硬编码进判定**（见 `forecast-rules.md` 第七节）
3. **数据不足禁编造**：精度表为空 → gated 结构，绝不输出虚构数字
4. **结合实际**：知识库提供通用规则，具体结论须结合实时数据 + 多源融合结果
5. **标准待核**：`knowledge-base.md` 标 `[条款号待核]` 的项不引用具体条款号，只述原则
