# 物理模型服务

> **部署日期**：2026-06-05
> **端口范围**：18081-18083
> **技术栈**：Python Flask + NumPy + SciPy

---

## 模型清单

| 模型 | 端口 | 功能 | API |
|------|------|------|-----|
| 新安江模型 | 18081 | 降雨 → 入库流量 | POST /api/xaj/forecast |
| 调度优化模型 | 18082 | 入库流量 + 约束 → 闸门开度 + 出库流量 | POST /api/dispatch/optimize |
| 调洪演算模型 | 18083 | 入库 + 出库 → 水位过程 | POST /api/routing/calculate |

---

## 完整流水线

```
降雨数据
  ↓
新安江模型 (18081)
  ↓ 入库流量
调度优化模型 (18082)
  ↓ 闸门开度 + 出库流量
调洪演算模型 (18083)
  ↓ 水位过程 + 统计指标
结果输出
```

---

## API 文档

### 1. 新安江模型

```bash
POST http://localhost:18081/api/xaj/forecast
```

**请求**：
```json
{
  "rainfall": [5, 8, 15, 25, 35, 42, ...],      // 逐小时降雨量(mm)
  "evaporation": [1, 1, 1, ...],                 // 逐小时蒸发量(mm)，可选
  "watershed_area": 161.25                        // 流域面积(km²)，可选
}
```

**响应**：
```json
{
  "flow": [334.4, 420.01, ...],                  // 逐小时入库流量(m³/s)
  "peak_flow": 1553.59,                          // 洪峰流量
  "peak_time": 17,                               // 洪峰时段
  "total_runoff": 7688.49,                       // 总径流量(万m³)
  "runoff_coefficient": 1.786                    // 径流系数
}
```

### 2. 调度优化模型

```bash
POST http://localhost:18082/api/dispatch/optimize
```

**请求**：
```json
{
  "inflow": [50, 80, 120, ...],                  // 入库流量过程(m³/s)
  "initial_water_level": 459.18,                 // 初始水位(m)
  "max_water_level": 462.88,                     // 最高允许水位
  "min_water_level": 451.0,                      // 最低允许水位
  "max_drainage_capacity": 192,                  // 最大泄流能力
  "safe_drainage_capacity": 95.1,                // 下游安全泄量
  "target_water_level": 460.0,                   // 目标水位
  "scheduling_target": "0",                      // 0=防洪, 1=兴利, 2=综合
  "scheduling_model": "0"                        // 0=控制最高, 1=控制最低, 2=范围
}
```

**响应**：
```json
{
  "water_levels": [459.18, 459.35, ...],         // 逐时水位
  "outflows": [30.5, 50.2, ...],                // 逐时出库流量
  "gate_openings": [0.15, 0.25, ...],           // 逐时闸门开度(0-1)
  "statistics": {
    "peak_inflow": 200.0,
    "peak_outflow": 91.13,
    "peak_shaving_rate": 54.44,
    "max_water_level": 460.06,
    "total_inflow": 1320.0,
    "total_outflow": 680.5
  }
}
```

### 3. 调洪演算模型

```bash
POST http://localhost:18083/api/routing/calculate
```

**请求**：
```json
{
  "inflow": [50, 80, 120, ...],                  // 入库流量(m³/s)
  "outflow": [30, 50, 70, ...],                  // 出库流量(m³/s)
  "initial_water_level": 459.18,                 // 初始水位
  "dt_hours": 1                                  // 时间间隔(h)
}
```

**响应**：
```json
{
  "water_levels": [459.18, 459.35, ...],
  "capacities": [6960, 7050, ...],
  "statistics": {
    "initial_water_level": 459.18,
    "final_water_level": 459.65,
    "max_water_level": 459.65,
    "peak_shaving_rate": 54.44,
    "total_inflow": 1320.0,
    "total_outflow": 680.5,
    "storage_change": 639.5
  }
}
```

---

## 启动/停止

```bash
cd SmartTwinRes-skills/plan-generation/models

# 启动所有服务
bash start_models.sh start

# 停止所有服务
bash start_models.sh stop

# 查看状态
bash start_models.sh status

# 重启
bash start_models.sh restart
```

---

## 测试验证

```bash
# 测试新安江模型
curl -X POST http://localhost:18081/api/xaj/forecast \
  -H "Content-Type: application/json" \
  -d '{"rainfall": [5, 8, 15, 25, 35, 42, 38, 30, 22, 15, 10, 8]}'

# 测试调度优化
curl -X POST http://localhost:18082/api/dispatch/optimize \
  -H "Content-Type: application/json" \
  -d '{"inflow": [50, 80, 120, 150, 180, 200], "initial_water_level": 459.18}'

# 测试调洪演算
curl -X POST http://localhost:18083/api/routing/calculate \
  -H "Content-Type: application/json" \
  -d '{"inflow": [50, 80, 120], "outflow": [30, 50, 70], "initial_water_level": 459.18}'
```

---

## 与 Skill 的集成

Skill 通过 HTTP 调用这些模型 API：

```bash
# Skill 中调用新安江模型
curl -X POST http://localhost:18081/api/xaj/forecast \
  -H "Content-Type: application/json" \
  -d '{"rainfall": [...]}'

# Skill 中调用调度优化
curl -X POST http://localhost:18082/api/dispatch/optimize \
  -H "Content-Type: application/json" \
  -d '{"inflow": [...], "initial_water_level": 459.18, ...}'

# Skill 中调用调洪演算
curl -X POST http://localhost:18083/api/routing/calculate \
  -H "Content-Type: application/json" \
  -d '{"inflow": [...], "outflow": [...], "initial_water_level": 459.18}'
```

---

## 参数校准说明

当前模型参数为**默认值**，未针对三岔水库进行率定。实际使用前需要：

1. **新安江模型**：用历史降雨-径流数据率定产流参数（B、WM、KG、KSS等）
2. **调度优化模型**：用历史调度数据验证约束参数
3. **调洪演算模型**：用实测水位数据验证水量平衡精度

---

*生成时间: 2026-06-05*
