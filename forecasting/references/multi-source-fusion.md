# 多源降雨融合知识库

> **用途**：Agent 处理"多源降雨对比/融合/分歧"时的判定依据
> **触发场景**：`fusion_detail` / `multi_source_overview` 类型查询，或用户问"几个源报的不一样怎么办"
> **核心原则**：融合判定是 **LLM 推理过程，不是固定算法**——四源对齐后由 Agent 综合置信度/分歧/方向趋势做裁决，脚本只负责取数与逐小时对齐

---

## 一、四源时间窗对齐表

| 数据源 | 数据表 | 预见期 | 时间粒度 | 置信度 | 关键字段 |
|--------|--------|--------|---------|--------|---------|
| **和风 168h** | `f_rnfl_h` | 未来 168h | 逐时（1h） | 中 | RN / YMDH / FYMDH（无 tenant） |
| **和风 30d** | `weather_info` | 未来 30d | 日总量 | 中 | precip / fx_date（无 tenant） |
| **NMC 24h** | 中央气象台 fixture | 未来 24h | 等值面（标量 max） | 高 | contours（JSONP fixture） |
| **分区模型** | `st_pptn_re_forecast` | 未来 168h | 逐时（1h，按 re_id） | 高 | drp / tm / re_id（tenant=18） |

### 对齐策略

```
时间轴基准: NOW() 起的未来小时序列(YYYY-MM-DD HH:00:00)

逐小时对齐:
  - 和风 168h:  YMDH → hour_key (RN)
  - 分区模型:   tm → hour_key (drp, 同小时多 re_id 取均值代表该源)
  - NMC 24h:    标量(等值面 max),不逐时对齐,作"该源强度上限"参照
  - 和风 30d:   日粒度(precip),展平到"日"轴,与逐时源不同轴

# 只有"逐时源"(和风168h + 分区模型)做逐小时对齐与分歧标注
# NMC / 30d 作为宏观参照,不进逐时分歧计算
```

---

## 二、融合判定规则（LLM 推理，非固定算法）

> ⚠️ 以下为 Agent 的**推理框架**，不是加权公式。具体采信哪个源、如何区间化，由 Agent 结合 `forecast-rules.md` 的置信度模型现场裁决。脚本（`fusion_detail`）只产出对齐时间轴 + 分歧标注，**不输出融合后的单一数值**。

### 推理步骤

```
Step 1: 取数对齐
  → 调 fusion_detail / multi_source_overview,获得四源原始值 + 逐时对齐表 + disagreement_hours

Step 2: 源可用性评估
  → 逐源判断 available(yes/no/缺失)
  → NMC 看 fixture 文件存在性(data/scenarios/nmc_rainfall_24.json)
  → 缺失源不参与后续裁决,标注"该源不可用"

Step 3: 分歧识别
  → 看 disagreement_hours 与 aligned_hours 的比值
  → 比值高 → 源间一致性差 → 融合结论降置信度 + 触发区间估算

Step 4: 方向趋势判断
  → 各源未来 6h/24h 是"上升/平稳/下降"
  → 多源方向一致 → 采信;方向冲突 → 保守取较大值(利于防洪)

Step 5: 裁决采信(参考 forecast-rules.md 规则9)
  → NMC 覆盖该小时 → 采信 NMC
  → 模型源与和风同向 → 采信模型源
  → 源间反向 → 取保守值 + 【估算值 ±20%】

Step 6: 输出
  → 融合结论(点估或区间) + 各源明细 + 置信度 + 分歧统计
```

---

## 三、每源置信度模板

### 标注格式

```
源: {source_name}
  - 数据表: {table}
  - 置信度: {高/中/低/缺失}
  - 预见期: {hours}h
  - 覆盖小时数: {n}
  - 该源 24h 总量: {total_mm} mm
  - 备注: {note}
```

### 各源默认置信度（与 forecast-rules.md 一致）

| 源 | 默认置信度 | 调整条件 |
|----|-----------|---------|
| NMC 24h | 高 | fixture 缺失 → 缺失；等值面 max=0 → 低 |
| 分区模型（st_pptn_re_forecast） | 高 | 行数=0 → 缺失 |
| 和风 168h（f_rnfl_h） | 中 | 行数=0 → 缺失 |
| 和风 30d（weather_info） | 中 | 仅日粒度，作宏观参照，不单独定级 |

### 分歧阈值

```
逐小时分歧判定（仅逐时源参与）:
  IF len(present_sources) >= 2 AND (max - min) > {disagree_mm_threshold}:
      → disagreement[hour] = True

参考值: {disagree_mm_threshold} = 20mm（来自 fusion_detail.disagreement_threshold_mm 字段）
⚠️ 此值从脚本返回字段读,不硬编码进 Agent 推理

汇总指标:
  disagreement_hours: 标记为 True 的小时数
  disagreement_ratio: disagreement_hours / aligned_hours
  → ratio > {disagree_ratio_threshold}（参考 0.3）→ 综合置信度降为"中"
```

---

## 四、NMC HTTP fixture 说明

### 文件位置

```
SmartTwinRes-skills/forecasting/data/scenarios/nmc_rainfall_24.json
```

### 格式（JSONP 外壳）

生产环境 NMC（typhoon.nmc.cn）返回的是 JSONP，形如：

```
diamond14_rainfall_{type}_json(  {  ...JSON...  }  )
```

其中 `{type}` 对应预见期类型（如 `24` 表示 24h）。fixture 文件保留了这一外壳：

```
diamond14_rainfall_24_json({
  "contours": [
    {"value": 10,  "points": [[105.5,26.0], ...]},
    {"value": 25,  "points": [...]},
    {"value": 50,  "points": [...]},
    {"value": 100, "points": [...]},
    {"value": 250, "points": [...]}
  ],
  "legend": [
    {"min":0,"max":10,"color":"#A6F28F","label":"0~10mm"},
    {"min":10,"max":25,"color":"#3DBA3D","label":"10~25mm"},
    ...
  ],
  "issue_time": "2026-06-22 12:00:00",
  "lead_hours": 24,
  "source": "NMC-MOCK",
  "remark": "MOCK fixture;生产代码 rainfallController 实时拉取 typhoon.nmc.cn 此格式"
})
```

### 解析规则（脚本 `_parse_nmc_fixture`）

```
1. 读文件原文
2. 正则剥外壳: ^\s*\w+\((.*)\)\s*$ （DOTALL）→ 取捕获组为 payload
3. json.loads(payload) → dict
4. 取 contours 列表里所有 value,求 max → nmc_max_mm（代表该源强度上限）
5. issue_time / lead_hours / source 作为元数据回传
```

### 等值面语义

- `contours[].value` = 降雨量等值面值（mm）
- `contours[].points` = 等值面多边形顶点经纬度 [lng, lat]
- `legend[]` = 量级色带（0~10 / 10~25 / 25~50 / 50~100 / 100~250 / ≥250mm）
- **取 max(contours[].value)** 作为该源覆盖区域的降雨强度上限，用于与逐时源对照（不逐时对齐，因 NMC 是面状预报非点预报）

### mock 与生产差异

| 维度 | mock fixture | 生产（rainfallController） |
|------|-------------|-------------------------|
| 来源 | 本地文件 | HTTP GET typhoon.nmc.cn |
| 时效 | 固定 issue_time | 实时拉取 |
| 标记 | `source: "NMC-MOCK"` | `source: "NMC"` |
| 用途 | 验证解析逻辑 + 置信度标注 | 真实预报输入 |

> Agent 见 `source: "NMC-MOCK"` 时应在结论里标注"基于 mock fixture，非实时数据"。

---

## 五、四源融合输出模板

```
多源降雨融合结论:

【宏观趋势】
  - NMC 24h 等值面 max: {nmc_max_mm} mm（置信度:高,源:{nmc_source}）
  - 和风 30d 日总量序列: {weather_map}（置信度:中,日粒度）

【逐时对齐】（未来 {hours}h）
  - 和风 168h 总量: {hefeng_total_mm} mm（{hefeng_rows} 行）
  - 分区模型总量: {zonal_total_mm} mm（{zonal_rows} 行）
  - 分歧小时数: {disagreement_hours} / {aligned_hours}（阈值 {disagree_mm}mm）

【裁决】
  - 方向趋势: {上升/平稳/下降}
  - 采信源: {source}（依据: {reason}）
  - 综合置信度: {高/中/低}

【输出形式】
  - 点估: {value} mm
  - 或区间: 【{low} ~ {high} mm】（±20%, 触发原因: {reason}）

【数据源明细】
  {逐源置信度模板列表}
```

---

## 六、与 forecast-rules.md 的衔接

- **置信度模型**：见 `forecast-rules.md` 第三节（每源置信度 + 综合裁决）
- **分歧阈值**：`{disagree_mm_threshold}` 参考值 20mm，从 `fusion_detail.disagreement_threshold_mm` 字段读
- **影响估算触发**：见 `forecast-rules.md` 第四节规则6（融合后 24h 总量 ≥ 阈值 或 多源分歧 → `【估算值 ±20%】`）
- **严禁硬编码**：分歧阈值/采信规则里的数字均走字段/配置，C2 拦截字面常量
