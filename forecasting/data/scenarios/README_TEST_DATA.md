# Forecasting Skill 测试数据插入指南

## 📋 概述

**目标**: 为 forecasting skill 插入未来 48 小时降雨预报测试数据，以验证 skill 功能。

**适用场景**: 本地测试、集成测试、演示

---

## 📦 包含的文件

| 文件 | 说明 |
|------|------|
| `insert_test_forecast_data.sql` | SQL 插入脚本（46 条逐时预报 + 36 条分区预报） |
| `insert_forecast_test_data.sh` | 一键执行脚本（带确认提示） |

---

## 🗂️ 数据说明

### f_rnfl_h (和风天气逐时降雨预报)

**插入数据**: 46 条

| 日期 | 时段 | 条数 | 降雨量范围 |
|------|------|------|-----------|
| 2026-07-10 (今天) | 14:00 ~ 23:00 | 10 | 0 ~ 12 mm |
| 2026-07-11 (明天) | 00:00 ~ 23:00 | 24 | 0 ~ 20 mm (暴雨) |
| 2026-07-12 (后天) | 00:00 ~ 11:00 | 12 | 0 ~ 11 mm |

**发布单位**: 和风天气
**发布时间**: 2026-07-10 13:00:00

---

### st_pptn_re_forecast (分区降雨预报)

**插入数据**: 36 条

| 日期 | 时段 | 条数 | 累计雨量 |
|------|------|------|---------|
| 2026-07-11 | 全天 | 24 | 85 mm |
| 2026-07-12 | 00:00 ~ 11:00 | 12 | 52 mm |

**预报ID**: re_id = 1 (明天), 2 (后天)

---

### weather_info (和风30天天气)

**插入数据**: 1 条（2026-07-10）

| 字段 | 值 |
|------|-----|
| 最高温 | 32°C |
| 最低温 | 24°C |
| 白天天气 | 大雨 |
| 夜间天气 | 小雨 |
| 降水量 | 25.0 mm |

---

## 🚀 快速开始

### 方式 1：一键脚本（推荐）

```bash
cd /home/scada/SmartTwinRes20260601
./insert_forecast_test_data.sh
```

脚本会：
1. 显示数据摘要
2. 等待确认（输入 `y`）
3. 执行 SQL 插入
4. 验证插入结果

### 方式 2：手动执行 SQL

```bash
# 设置环境变量
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD='123456aA.'

# 执行插入
mysql powerelf_srm_yml < \
  /home/scada/SmartTwinRes20260601/SmartTwinRes-skills/forecasting/data/scenarios/insert_test_forecast_data.sql
```

---

## ✅ 验证

### 验证数据已插入

```bash
# 检查 f_rnfl_h 未来48小时数据
export SRM_DB_PASSWORD='123456aA.'
python3 /home/scada/SmartTwinRes20260601/SmartTwinRes-skills/forecasting/scripts/query_forecast_data.py \
  --type rainfall_forecast --hours 48
```

期望输出：
```json
{
  "source": "f_rnfl_h (和风天气)",
  "hours": 48,
  "count": 46,
  "data": [...]
}
```

### 验证多源融合

```bash
python3 /home/scada/SmartTwinRes20260601/SmartTwinRes-skills/forecasting/scripts/query_forecast_data.py \
  --type multi_source_overview
```

期望输出：
```json
{
  "f_rnfl_h": {"count": 46, ...},
  "st_pptn_re_forecast": {"count": 36, ...},
  "weather_info_30d": {"count": 9, ...},
  ...
}
```

### 验证 Skill 完整流程

```bash
python3 /home/scada/SmartTwinRes20260601/SmartTwinRes-skills/forecasting/scripts/query_forecast_data.py \
  --type full_context
```

期望输出包含：
- `current_water_level`: 当前水位 ~462.92m
- `rainfall_forecast`: 46 条逐时预报
- `flood_limit`: 汛限水位 462.5m
- `weather_warning`: 气象预警
- `config`: 配置信息

---

## 🧹 清理测试数据

如果需要删除测试数据，执行：

```sql
-- 删除今天插入的数据
DELETE FROM f_rnfl_h
WHERE FYMDH >= '2026-07-10 13:00:00'
  AND UNITNAME = '和风天气';

DELETE FROM st_pptn_re_forecast
WHERE tm >= '2026-07-11 00:00:00';

DELETE FROM weather_info
WHERE fx_date >= '2026-07-10'
  AND precip = '25.0';
```

---

## ⚠️ 注意事项

1. **重复执行**: 脚本会重复插入相同数据，如需多次测试请先清理旧数据
2. **时间窗口**: 测试数据的时间范围是固定的（2026-07-10 ~ 2026-07-12），超过这个时间后需要更新
3. **生产环境**: **严禁**在生产数据库执行此脚本

---

## 📚 参考资料

- Forecasting Skill 文档: `SmartTwinRes-skills/forecasting/SKILL.md`
- 数据库配置: `SmartTwinRes-skills/forecasting/db-config.md`
- 测试报告: `/tmp/forecasting-script-test-20260709-203109/README.md`
