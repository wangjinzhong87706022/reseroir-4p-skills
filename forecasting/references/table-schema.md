# 表结构元数据（预报场景）

> **用途**：LLM 走"灵活路径"自己写 SQL 时的参考字典
> **数据基线**：本地 mock + 迁移自现网（103）只读快照；量级标注为现网实测量级，本地环境数量更小但表结构一致

---

## ⚠️ 大表判定标准

| 判定条件 | 示例 | 标记 |
|---------|------|------|
| 现网数据量 > 10万行 | st_rsvr_r（约19万）、st_pptn_r（约26万） | ⚠️ |
| 现网数据量达万级且持续增长 | f_rnfl_h（逐时预报，每小时新增） | ⚠️ |
| 静态/配置参考数据 | att_res_flse_lim、model_config | 无 ⚠️ |

**安全规则**：
- 大表（⚠️）的多行提取查询（SELECT 返回多行）→ **必须**加时间范围条件 + LIMIT
- 大表的统计/聚合查询（COUNT/SUM/AVG）→ 视用户意图决定是否加时间范围
- 统计"全量数据质量/预报精度"类问题 → 不加时间范围（整表聚合才有意义）
- 不确定时 → 默认加时间范围（保守策略）

---

## 总览（预报场景核心表）

| 表名 | 中文名 | 现网量级 | 需时间过滤 | 有无 tenant_id | 有无 deleted | taskid 拼写 |
|------|--------|---------|-----------|---------------|-------------|------------|
| st_rsvr_r | 实时水情（水位/流量） | 19万 ⚠️ | 是（tm） | 有（=18） | 有 | — |
| st_pptn_r | 实测降雨 | 26万 ⚠️ | 是（tm） | 有（=18） | 有（stcd='46'） | — |
| f_rnfl_h | 和风逐时降雨预报 | 8千 ⚠️ | 是（YMDH/FYMDH） | **无** | 有 | — |
| st_mx_preset_cal_r | 模型预报结果（流量/水位过程） | 1.3万 | 是（tm）/按 taskid | 有 | 有 | **taskid（varchar）** |
| model_result_files | 模型结果文件/任务 | 91 | 否 | 有 | **无** | **taskid（varbinary）** |
| weather_info | 和风天气预报（30d 日总量） | 30 | 否 | **无** | 有 | — |
| weather_warn | 气象预警 | 数十 | 否 | **无** | **无** | — |
| st_pptn_re_forecast | 分区降雨预报 | 8千 | 是（tm） | 有（=18） | 有（按 re_id，**无 stcd**） | — |
| forecast_accuracy_record | 预报精度记录（mock 新表） | mock | 否 | 有 | 有 | — |
| dispatch_history | 调度历史 | 万级 | 通过 task_id 关联 | 有 | 有 | **task_id（varchar，下划线）** |
| srm_flood_history_base | 历史洪水 | 十条级 | 否 | 有 | 有 | — |
| att_res_flse_lim | 汛限水位（分汛期） | 十条级 | 否 | 有 | **无** | — |
| att_res_base | 水库基础（汛限兜底） | 1 | 否 | 有 | 有 | — |
| model_config | 系统配置（master stcd 等） | 百级 | 否 | 有（=18） | 有 | — |

### 用法规则（六条）

1. **软删除按表对待（不要无脑加 `deleted=0`）**：
   - `model_result_files`、`weather_warn`、`att_res_flse_lim` **无 deleted 列** → 拼接 SQL 时**不要**加 `AND deleted = 0`，否则报未知列错误。
   - 其余预报场景表（st_*、f_rnfl_h、srm_flood_history_base、st_pptn_re_forecast、att_res_base、model_config、forecast_accuracy_record、weather_info）有 deleted 列 → 加 `AND deleted = 0`。

2. **`f_rnfl_h` 不过滤 tenant**：该表**无可用 tenant 字段**，直接按 YMDH/FYMDH 时间窗口查询即可，不要拼 `AND tenant_id = ...`。

3. **`model_result_files` 用 `type` 过滤**：该表混存多种结果（1=预报来水过程，2=调度流量过程，…）。取预报来水曲线须 `type = 1`；取调度预案须 `type = 2`。**且无 deleted 列**。

4. **taskid 三拼写 → JOIN 必须 CAST**：
   | 表 | 列名 | 类型 |
   |----|------|------|
   | `dispatch_history` | `task_id` | varchar(32) — **下划线** |
   | `model_result_files` | `taskid` | **varbinary**(32) — 无下划线 |
   | `st_mx_preset_cal_r` | `taskid` | **varchar** — 无下划线 |
   JOIN 时先转字符串再比较：`ON s.taskid = CAST(m.taskid AS CHAR)`，否则隐式截断/类型不匹配。

5. **汛限水位兜底 `att_res_base`**：`att_res_flse_lim` 按当前 MMdd 落在哪段汛期取该段 `flse_lim_stag`；若为空或当前日期不命中任何汛期 → 回退 `att_res_base.fl_low_lim_lev`。**严禁硬编码汛限数值进判定逻辑**（三岔汛限 462.500 仅是种子参考值）。

6. **主站 stcd 从 `model_config` 读**：master 测站编码绝不硬编码。水位站读 `config_key = 'st_rsvr_r_master'`（值 '3'），雨量站读 `config_key = 'st_pptn_r_master'`（值 '46'），均取 `tenant_id = 18`。

---

## 详细表结构

---

### st_rsvr_r（实时水情）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 1234567890 | 唯一标识 |
| stcd | varchar(20) | 测站编码 | "3" | 筛选测站（master 从 config 读） |
| tm | datetime | 观测时间 | "2026-06-10 08:00:00" | **必须的时间过滤字段** |
| rz | decimal(8,3) | 水位（m） | 460.12 | 当前水位 / 水位趋势 |
| inq | decimal(10,3) | 入库流量（m³/s） | 150.5 | 入库流量分析 |
| otq | decimal(10,3) | 出库流量（m³/s） | 120.3 | 出库流量分析 |
| w | decimal(12,3) | 蓄水量（万m³） | 850.2 | 库容分析 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：任何非 `LIMIT 1` 的查询必须包含 `tm` 时间范围条件。master stcd 从 `model_config` 的 `st_rsvr_r_master` 键获取（**绝不硬编码 '3'**）。

```sql
-- ✅ 安全: master stcd 从 config 读 + 时间窗口
SELECT rz, inq, otq, w, tm, stcd
FROM st_rsvr_r
WHERE tenant_id = 18 AND deleted = 0
  AND stcd = (SELECT value FROM model_config
              WHERE config_key='st_rsvr_r_master' AND tenant_id=18 AND deleted=0 LIMIT 1)
  AND tm >= NOW() - INTERVAL {hours|24} HOUR
ORDER BY tm DESC
LIMIT {limit|1000};
```

---

### st_pptn_r（实测降雨）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 9876543210 | 唯一标识 |
| stcd | varchar(20) | 测站编码 | "46" | 筛选测站（master 从 config 读） |
| tm | datetime | 观测时间 | "2026-06-10 08:00:00" | **必须的时间过滤字段** |
| drp / p | decimal(7,1) | 时段降雨量（mm） | 5.3 | 当前时段雨量（drp 优先） |
| dr | decimal(5,1) | 时段长（h） | 1.0 | 降雨历时 |
| dyp | decimal(7,1) | 日降雨量（mm） | 23.5 | 日雨量 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：master stcd 从 `model_config` 的 `st_pptn_r_master` 键获取（**绝不硬编码 '46'**）。

```sql
-- ✅ 安全: 实测降雨对照预报
SELECT tm, drp, dr, dyp
FROM st_pptn_r
WHERE tenant_id = 18 AND deleted = 0
  AND stcd = (SELECT value FROM model_config
              WHERE config_key='st_pptn_r_master' AND tenant_id=18 AND deleted=0 LIMIT 1)
  AND tm >= NOW() - INTERVAL {hours|24} HOUR
ORDER BY tm
LIMIT {limit|1000};
```

---

### f_rnfl_h（和风逐时降雨预报）⚠️ 大表

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 100001 | 唯一标识 |
| RN | decimal(7,1) | 预报降雨量（mm） | 12.5 | 预报雨量值（**列名大写**） |
| YMDH | datetime | 预报目标时间 | "2026-06-11 14:00:00" | 预报的时刻（**大写**） |
| FYMDH | datetime | 预报发布时间 | "2026-06-10 08:00:00" | 区分预报批次（**大写**） |
| UNITNAME | varchar(50) | 发布单位标识 | "1" | 区分来源（1=和风天气） |
| type | tinyint | 预报类型 | 1 | 区分预报模式 |
| deleted | tinyint | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 强制规则**：列名是**大写** `RN / YMDH / FYMDH / UNITNAME`（MySQL 默认大小写不敏感，但脚本里保持大写以与现网一致）。**无 tenant_id 列 → 不要过滤 tenant**。取最新批次先 `MAX(FYMDH)` 再按 YMDH 查。

```sql
-- ✅ 安全: 未来 N 小时逐时预报（无 tenant 过滤）
SELECT RN, YMDH, FYMDH, UNITNAME
FROM f_rnfl_h
WHERE YMDH BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {hours|48} HOUR)
  AND deleted = 0
ORDER BY YMDH
LIMIT {limit|1000};
```

---

### st_mx_preset_cal_r（模型预报结果）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 200001 | 唯一标识 |
| type | int | 类型 | 21 | **21=入库流量预报，22=坝前水位预报** |
| vals | double | 结果值 | 152.3 | 过程线数据点 |
| tm | datetime | 时间点 | "2026-06-10 09:00:00" | 时序轴 |
| taskid | varchar | 任务ID | "TASK20260610001" | **varchar**，关联 model_result_files.taskid（需 CAST） |
| step | int | 时序步号 | 1 | 排序 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：`type` 字段取 **'21'（流量）/ '22'（水位）**（脚本里按字符串比较，故引号）。JOIN `model_result_files` 必须 `ON s.taskid = CAST(m.taskid AS CHAR)`。

```sql
-- ✅ 安全: 模型预报两条曲线（流量+水位）
SELECT m.taskid, m.target_water_level, m.adjusted_water_level, m.create_time,
       s.tm, s.type AS series_type, s.vals
FROM model_result_files m
JOIN st_mx_preset_cal_r s ON s.taskid = CAST(m.taskid AS CHAR)
WHERE m.tenant_id = 18
  AND m.create_time = (SELECT MAX(create_time) FROM model_result_files
                       WHERE tenant_id=18 AND create_time<=NOW())
  AND s.type IN ('21','22')
ORDER BY s.tm;
```

---

### model_result_files（模型结果文件/任务）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 300001 | 唯一标识 |
| taskid | **varbinary(32)** | 任务ID | 0x54415... | 关联 st_mx_preset_cal_r / dispatch_history（**需 CAST AS CHAR**） |
| type | tinyint | 结果类型 | 1 | **1=预报来水过程，2=调度流量过程** |
| target_water_level | varchar(50) | 目标水位（m） | "460.00" | 预期控制水位（**VARCHAR，比较须 CAST**） |
| adjusted_water_level | varchar(50) | 起调水位（m） | "458.06" | 实际起调水位（**VARCHAR，比较须 CAST**） |
| extend | text | 扩展信息（JSON） | '{"schedulingTarget":...}' | 方案参数详情 |
| create_time | datetime | 创建时间 | "2026-06-10 09:00:00" | 取最新 run 的排序键 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |
| **deleted** | — | **无此列** | — | **查询时不要加 deleted=0！** |

**⚠️ 强制规则**：**无 deleted 列**。取预报用 `type = 1`。水位列是 VARCHAR，数值比较必须 `CAST(adjusted_water_level AS DECIMAL(10,3))`。取最新 run 用子查询 `MAX(create_time)`。

---

### weather_info（和风天气预报，30d 日总量）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 400001 | 唯一标识 |
| fx_date | varchar(20) | 预报日期 | "2026-06-10" | 时间轴（**字符串日期**） |
| temp_max | varchar(10) | 最高温度（℃） | "32" | 气温 |
| temp_min | varchar(10) | 最低温度（℃） | "22" | 气温 |
| text_day | varchar(50) | 白天天气 | "中雨" | 天气文字 |
| text_night | varchar(50) | 夜间天气 | "大雨" | 天气文字 |
| precip | varchar(10) | 日降水量（mm） | "25.6" | 日总量（**VARCHAR**） |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| **tenant_id** | — | **无此列** | — | **不要过滤 tenant** |

**注意**：无 tenant_id 列。`precip` 是 VARCHAR，聚合时 `CAST(precip AS DECIMAL(7,1))`。30d 窗口：`fx_date >= CURDATE() - INTERVAL 30 DAY`。

---

### weather_warn（气象预警）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 500001 | 唯一标识 |
| docid | varchar(100) | 预警ID | "WARN20260610001" | 预警唯一编号 |
| docabstract | text | 预警摘要内容 | "预计未来6小时内..." | 预警详情 |
| chnlname | varchar(50) | 预警类型名称 | "暴雨预警" | 预警分类 |
| docpubtime | varchar(50) | 发布时间 | "2026-06-10 08:00:00" | 发布时间（**字符串**） |
| warn_status | varchar(5) | 预警状态 | "1" | **1=正在预警，2=解除** |
| **tenant_id** | — | **无此列** | — | **不要过滤 tenant** |
| **deleted** | — | **无此列** | — | **不要加 deleted=0！** |

**注意**：无 tenant_id、无 deleted 列。`warn_status` 是字符串 '1'/'2'。`docpubtime` 是字符串，按字符串排序即可。

---

### st_pptn_re_forecast（分区降雨预报）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 600001 | 唯一标识 |
| drp | decimal(7,1) | 预报降雨量（mm） | 8.5 | 分区预报雨量 |
| dyp | decimal(7,1) | 日累计降雨量（mm） | 32.0 | 日累计 |
| intv | varchar(10) | 时间间隔 | "1h" | 时段标识 |
| wth | varchar(20) | 天气 | "中雨" | 天气描述 |
| tm | datetime | 预报时间 | "2026-06-11 14:00:00" | 时间轴 |
| re_id | bigint | 关联预报ID | 700001 | 分区/批次关联（**无 stcd**） |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**注意**：**无 stcd 列**（与 st_pptn_r 不同）。按 `re_id` 关联，同一小时多 re_id 时取均值代表该源强度。窗口常取 `tm BETWEEN NOW()-INTERVAL 48 HOUR AND NOW()+INTERVAL 168 HOUR`。

---

### forecast_accuracy_record（预报精度记录，mock 新表）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 800001 | 唯一标识 |
| source | varchar(20) | 预报来源 | "hefeng" / "nmc" / "model" | 按源聚合 MAPE |
| mape | decimal(5,2) | 平均绝对百分比误差（%） | 12.5 | 精度指标 |
| issued_tm | datetime | 预报发布时间 | "2026-06-10 08:00:00" | 时间轴 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |

**⚠️ 注意**：这是 **Task 2 引入的 mock 新表**，本地与现网均可能为空。查询须先探测 `COUNT(*)`，为空/不存在 → 返回 `gated` 结构（`status: insufficient`），**绝不编造精度数字**。置信分级：MAPE<15%=高 / 15~30%=中 / >30%=低。

---

### dispatch_history（调度历史）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 900001 | 唯一标识 |
| tm | datetime | 调度时刻 | "2026-06-10 10:00:00" | 该步对应时间 |
| dispatch_opening | varchar(50) | 闸门开度（m） | "2.5" | 闸门开度值 |
| gate_opening_flow | varchar(50) | 闸门出流（m³/s） | "180.5" | 闸门流量 |
| task_id | varchar(32) | 关联任务ID | "TASK20260610001" | **下划线**，关联 model_result_files.taskid |
| create_time | datetime | 创建时间 | "2026-06-10 09:00:00" | 记录创建 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**⚠️ 强制规则**：**不要直接按 tm 查询此表！** 必须通过 `task_id` 关联 `model_result_files.taskid`（JOIN 时 `ON d.task_id = CAST(m.taskid AS CHAR)`）。单独按 tm 查询会混淆不同调度方案。

---

### srm_flood_history_base（历史洪水）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 110001 | 唯一标识 |
| name | varchar(100) | 洪水名称 | "20260610号洪水" | 洪水标识 |
| start_time | datetime | 洪水开始 | "2026-06-10 08:00:00" | 时间范围 |
| end_time | datetime | 洪水结束 | "2026-06-12 20:00:00" | 时间范围 |
| adjusted_water_level | decimal(8,3) | 起调水位（m） | 458.06 | **作为"峰值水位"代理列**（相似洪水排序用） |
| target_water_level | decimal(8,3) | 目标水位（m） | 460.00 | 预期控制水位 |
| status | tinyint | 计算状态 | 2 | 0=待算，1=算中，2=完成，3=失败 |
| data_source | varchar(50) | 数据来源 | "model" | 来源标识 |
| rainfall_data | text | 降雨过程（JSON） | '[{"tm":"...","p":5.3}]' | 输入降雨 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**注意**：该表无显式 `peak_water_level` 列，相似洪水匹配用 `adjusted_water_level` 作为峰值代理（起调水位即泄洪开始时刻库水位，最接近"峰值"语义）。

---

### att_res_flse_lim（汛限水位，分汛期）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 120001 | 唯一标识 |
| flse_lim_stag | decimal(8,3) | 汛限水位（m） | 462.500 | 汛限值（三岔主汛期参考） |
| flood_season_name | varchar(50) | 汛期名称 | "主汛期" | 汛期描述 |
| flood_season_start | varchar(10) | 汛期开始（MMdd） | "0601" | 判断是否在汛期（**字符串**） |
| flood_season_end | varchar(10) | 汛期结束（MMdd） | "0930" | 判断是否在汛期（**字符串**） |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |
| **deleted** | — | **无此列** | — | **不要加 deleted=0！** |

**注意**：无 deleted 列。`flood_season_start/end` 是 **MMdd 字符串**。当前日期匹配：`flood_season_start <= DATE_FORMAT(NOW(),'%m%d') AND flood_season_end >= DATE_FORMAT(NOW(),'%m%d')`；未命中 → 回退主汛期行 → 仍无 → 回退 `att_res_base.fl_low_lim_lev`。

---

### att_res_base（水库基础信息，汛限兜底）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 8 | 唯一标识 |
| fl_low_lim_lev | decimal(8,3) | 防洪限制水位（m） | 462.500 | **汛限兜底值**（att_res_flse_lim 为空时用） |
| dead_level | decimal(8,3) | 死水位（m） | — | 最低运行水位 |
| update_time | datetime | 更新时间 | "2026-01-01 00:00:00" | 取最新行排序 |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |
| tenant_id | bigint | 租户ID | 18 | 租户隔离 |

**注意**：通常 1 条记录。`fl_low_lim_lev` 是汛限的兜底值。

---

### model_config（系统配置）

| 字段 | 类型 | 含义 | 示例 | 查询用途 |
|------|------|------|------|---------|
| id | bigint | 主键 | 700001 | 唯一标识 |
| config_key | varchar(100) | 配置键名 | "st_rsvr_r_master" | **按 key 查** |
| value | text | 配置值 | "3" | 配置内容（**数值比较须 CAST**） |
| tenant_id | bigint | 租户ID | 18 | 租户隔离（优先取 18） |
| deleted | bit(1) | 软删除标记 | 0 | 过滤已删除 |

**预报场景关键键**：
- `st_rsvr_r_master` — 水位 master stcd（值 '3'）
- `st_pptn_r_master` — 雨量 master stcd（值 '46'）
- `max_water_level` — 最高允许水位（m）
- `min_water_level` — 最低运行水位（m）
- `Forecast_Q` — 预报流量相关配置

**⚠️ 强制规则**：字段名是 `config_key`（不是 `key_name`）。同一 key 可能多行，优先 `tenant_id = 18`。

---

## 水库特征水位参考（三岔水库，仅参考非硬编码）

> ⚠️ **以下为种子参考值，实际阈值须从 `model_config` / `att_res_flse_lim` / `full_context` 字段动态读取，严禁硬编码进判定逻辑。**

| 特征水位 | 参考值（m） | 来源 |
|---------|-----------|------|
| 汛限水位（主汛期） | 462.50 | att_res_flse_lim 种子（flood_season_name='主汛期'） |
| 设计洪水位 | 461.96 | 工程设计文件（仅参考） |
| 校核洪水位 | 462.88 | 工程设计文件（仅参考） |

**说明**：docs/33 中出现的趋势预警阈值 339.0 / 339.5 / 340.0 / 340.5m 与三岔水库 462.5m 汛限**不在同一高程基准**（疑似另一参考站/另一基面），存在不一致。**优先以 `full_context` 返回的字段值为准**，任何文字里的 339.x / 462.x 都仅作参考标注，不进判定分支。详见 `forecast-rules.md`。
