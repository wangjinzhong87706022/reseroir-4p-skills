# 预报判定规则知识库

> **用途**：Agent 给出预报结论/预警等级/影响估算时的规则依据
> **触发场景**：预报等级判定、置信度标注、影响估算触发、多源分歧裁决
> **引用方式**：回答中引用本文件时请注明"根据预报规则"
> **铁律**：**判定逻辑零硬编码数值**——所有阈值/参考值/特征水位均从 `full_context` 返回字段或 `model_config` 动态读取。下文出现的 339.x / 462.x / 50 / 20 等数字**仅作参考标注**，不进 IF 分支（skill-auditor C2 会拦截硬编码）。

---

## 一、字段读取约定（前置）

下列占位符代表**运行时从 `full_context` / `model_config` 读取的值**，而非字面常量：

| 占位符 | 读取来源 | 说明 |
|--------|---------|------|
| `{current_rz}` | `full_context.current_water_level.rz` | 当前实时水位（m） |
| `{flood_limit}` | `full_context.flood_limit.value` | 汛限水位（m，分汛期/回退） |
| `{design_level}` | `model_config.max_water_level` 或工程设计值 | 设计洪水位（m） |
| `{check_level}` | 工程设计校核值 | 校核洪水位（m） |
| `{warning_blue_level}` | 趋势预警配置字段 | 蓝色预警水位阈值（m） |
| `{warning_yellow_level}` | 趋势预警配置字段 | 黄色预警水位阈值（m） |
| `{warning_orange_level}` | 趋势预警配置字段 | 橙色预警水位阈值（m） |
| `{warning_red_level}` | 趋势预警配置字段 | 红色预警水位阈值（m） |
| `{forecast_rain_24h}` | 多源融合后 24h 预报总量（mm） | 融合判定产出 |
| `{inflow_forecast_peak}` | `model_forecast_result.flow_curve` 峰值 | 预报入库洪峰（m³/s） |

> **⚠️ 阈值来源说明**：`{warning_*_level}` 在 docs/33 标注的参考值为 339.0 / 339.5 / 340.0 / 340.5m（趋势预测用），但三岔水库实际汛限为 462.5m、设计 461.96m、校核 462.88m，**两者不在同一高程基准**，存在不一致。因此判定逻辑**只信任运行时读到的字段值**，任何文档里的 339.x / 462.x 数字都不进分支。

---

## 二、预警等级判定规则

### 规则1：基于水位的趋势预警等级

```
# 所有阈值从 full_context / model_config 读,绝不硬编码
IF {current_rz} >= {warning_red_level}:
    → 红色预警（特别严重）
ELIF {current_rz} >= {warning_orange_level}:
    → 橙色预警（严重）
ELIF {current_rz} >= {warning_yellow_level}:
    → 黄色预警（警戒）
ELIF {current_rz} >= {warning_blue_level}:
    → 蓝色预警（关注）
ELSE:
    → 无趋势预警
```

> 参考值（docs/33，仅标注不进判定）：蓝色≈339.0m / 黄色≈339.5m / 橙色≈340.0m / 红色≈340.5m。**实际阈值以 `{warning_*_level}` 运行时值为准**。

### 规则2：基于降雨预报的等级

```
# {forecast_rain_24h} 来自多源融合(fusion_detail),非单源
IF {forecast_rain_24h} >= {rainfall_red_threshold}:   # 参考 >250mm/24h, 仅标注
    → 红色（全力防洪）
ELIF {forecast_rain_24h} >= {rainfall_orange_threshold}:  # 参考 100~250mm, 仅标注
    → 橙色（紧急调度）
ELIF {forecast_rain_24h} >= {rainfall_yellow_threshold}:  # 参考 50~100mm, 仅标注
    → 黄色（启动防洪预案）
ELIF {forecast_rain_24h} >= {rainfall_blue_threshold}:    # 参考 25~50mm, 仅标注
    → 蓝色（关注天气）
ELSE:
    → 无降雨预警
```

> 上述 `{rainfall_*_threshold}` 阈值参考《水文情报预报规范》GB/T 22482 降雨等级划分，具体数值由配置读入，**严禁硬编码进判定**。

### 规则3：特征水位越限（与趋势预警独立，用于应急触发）

```
IF {current_rz} >= {check_level}:       # 参考 462.88m, 仅标注
    → 紧急调度（全力泄洪+人员转移）
ELIF {current_rz} >= {design_level}:    # 参考 461.96m, 仅标注
    → 加大泄洪（控水位不超校核）
ELIF {current_rz} >= {flood_limit}:     # 参考 462.50m, 仅标注
    → 启动防洪预案（控水位不超设计）
ELSE:
    → 正常调度
```

---

## 三、置信度模型规则

### 每源置信度（来自 `multi_source_overview` / `fusion_detail`）

| 数据源 | 置信度 | 依据 |
|--------|--------|------|
| NMC（中央气象台）24h | **高** | 官方权威源，fixture 验证格式 |
| 和风天气 168h 逐时 | **中** | 商业源，长预见期衰减 |
| 和风天气 30d 日总量（weather_info） | **中** | 长期趋势，日精度 |
| 模型预报（分区 st_pptn_re_forecast） | **高** | 本地水文模型，站点校准 |
| 模型预报来水过程（st_mx_preset_cal_r） | **高** | 经过产汇流演算 |

### 规则4：综合置信度裁决

```
IF NMC 源 available AND 模型源 available:
    → 综合置信度 = 高（两高源一致）
ELIF 仅和风 168h 源 available:
    → 综合置信度 = 中（单源且长预见期）
ELIF 多源分歧大（disagreement_hours 占比 > {disagree_ratio_threshold}）:
    → 综合置信度 = 中（源间分歧显著）
ELSE:
    → 综合置信度 = 中（默认保守）
```

> `{disagree_ratio_threshold}` 参考值 0.3（即分歧小时占比超 30%），**从配置读，不硬编码**。逐小时分歧判定阈值见 `multi-source-fusion.md`（参考 20mm，仅标注）。

### 规则5：预报精度置信度（来自 `accuracy_report`）

```
IF {avg_mape} < {mape_high_threshold}:    # 参考 15%, 仅标注
    → 精度置信度 = 高
ELIF {avg_mape} <= {mape_medium_threshold}:  # 参考 30%, 仅标注
    → 精度置信度 = 中
ELSE:
    → 精度置信度 = 低

# gated_flag=true 时(精度回灌链路 C1 缺陷未修):
#   → 数据可信但需人工复核,结论加"待复核"标注
```

---

## 四、影响估算触发规则

### 规则6：何时输出 `【估算值 ±20%】`

```
# 触发条件(任一满足即输出区间估算,而非点估)
IF {forecast_rain_24h} >= {impact_rain_threshold}:     # 参考 50mm/24h, 仅标注
    → 输出影响估算,标注【估算值 ±20%】
ELIF {current_rz} 接近 {flood_limit}（差值 <= {near_limit_margin}）:  # 参考 1.0m, 仅标注
    → 输出影响估算,标注【估算值 ±20%】
ELIF 多源分歧大（综合置信度 = 中且涉及防洪）:
    → 输出影响估算,标注【估算值 ±20%】
ELSE:
    → 输出点估计,无需区间
```

> 触发后所有定量结论（如预计最高水位、最大下泄量、洪峰到达时间）均以 `【估算值 ±20%】` 区间形式呈现，并注明数据源与置信度。`{impact_rain_threshold}` 参考值 50mm/24h、`{near_limit_margin}` 参考值 1.0m，**均从配置读，严禁硬编码**。

### 规则7：影响估算内容规范

```
触发影响估算时,输出必须包含:
  ① 预计最高水位: 【{level_low} ~ {level_high} m】（±20% 区间）
  ② 预计最大入库流量: 【{inflow_low} ~ {inflow_high} m³/s】
  ③ 洪峰预计到达时间: 【{t_minus} ~ {t_plus} h 后】
  ④ 超汛限概率: {prob}（基于蒙特卡洛/历史类比,数据不足则标"未知"）
  ⑤ 数据源标注: 列出采纳的源及各自置信度
  ⑥ 复核提示: gated_flag=true 时加"精度链路待复核"
```

---

## 五、多源分歧裁决规则

### 规则8：逐小时分歧标注

```
# 逐小时(对齐时间轴)比对各源 RN
FOR each hour in aligned_timeline:
    present_sources = [源 for 源 in sources if 源[hour] is not None]
    IF len(present_sources) >= 2:
        delta = max(present_sources) - min(present_sources)
        IF delta > {disagree_mm_threshold}:   # 参考 20mm, 仅标注
            → 该小时 disagreement = True
        ELSE:
            → disagreement = False
```

> `{disagree_mm_threshold}` 参考值 20mm（来自 `fusion_detail` 的 `disagreement_threshold_mm` 字段），**从字段读，不硬编码**。

### 规则9：分歧时的取值策略

```
IF 存在 NMC 源 AND NMC 覆盖该小时:
    → 采信 NMC（官方权威,置信度高）
ELIF 模型源与和风源方向一致(同升/同降):
    → 采信模型源（本地校准）
ELIF 源间方向相反(一升一降):
    → 取保守值(利于防洪的较大值),标注【估算值 ±20%】
ELSE:
    → 取多源均值,标注置信度=中
```

---

## 六、预报结论输出规范

```
预报结论结构(必须包含):
  ① 等级判定: 红色/橙色/黄色/蓝色/无（依据规则1-3）
  ② 置信度: 高/中/低（依据规则4-5）
  ③ 影响估算: 点估 或 【估算值 ±20%】区间（依据规则6-7）
  ④ 多源状态: 各源可用性 + 分歧小时数（依据规则8-9）
  ⑤ 数据时间戳: as_of（来自 full_context._meta）
  ⑥ 免责: gated_flag=true 时标注"精度链路待复核,结论仅供决策参考"
```

---

## 七、严禁事项（C2 拦截清单）

1. **禁止在 IF/ELIF 分支里出现字面数字阈值**（如 `if rz > 462.5`、`if rain > 50`）。所有阈值走 `{占位符}` 从字段读。
2. **禁止硬编码 master stcd**（'3' / '46'），一律 `model_config` 子查询。
3. **禁止硬编码汛限值**（462.5 / 339.x），一律 `flood_limit` 字段。
4. **参考值标注**：339.0/339.5/340.0/340.5m（趋势预警）、462.50/461.96/462.88m（特征水位）、50mm/24h（影响触发）、20mm（分歧阈值）等数字**只允许出现在"参考值"注释里，不允许进入判定表达式**。
5. **数据不足禁编造**：精度表空 → gated 结构，绝不输出虚构 MAPE。
