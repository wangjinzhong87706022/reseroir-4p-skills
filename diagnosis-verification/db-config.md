# 数据库连接配置

> **标准文档**: 完整的配置规范和命名空间说明见 [`../../docs/db-credential-config.md`](../../docs/db-credential-config.md)。

## 连接信息

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **主机** | ${SRM_DB_HOST:-127.0.0.1} | SmartResMatrix 数据库 |
| **端口** | ${SRM_DB_PORT:-3306} | MySQL 默认端口 |
| **数据库** | ${SRM_DB_NAME:-powerelf_srm_yml} | 水库业务数据库 |
| **用户** | ${SRM_DB_USER} | 只读用户 (必填) |
| **密码** | ${SRM_DB_PASSWORD} | 数据库密码 (必填,必须通过环境变量设置) |

## 环境变量设置

```bash
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD   # 必须从 application-prod.yaml 取值并 export；严禁写入本仓库
```

## 连接命令

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p"$SRM_DB_PASSWORD" powerelf_srm_yml
```

## 核心数据表 (诊断 skill 使用)

诊断 skill 跨多个 skill 查询数据,必须遵守各 skill 的数据源优先级规则:

### 水文预报相关 (forecasting)

| 表名 | 说明 | 过滤规则 | 来源 |
|------|------|---------|------|
| **st_rsvr_r** | 水库水情表 | `tenant_id=18 AND deleted=0` | forecasting |
| **st_pptn_r** | 降雨数据表 | `deleted=0` (部分含 tenant_id) | forecasting |
| **f_rnfl_h** | 逐时降雨预报 | ⚠️ **不加 tenant 过滤** | forecasting |
| **model_result_files** | 模型结果文件 | ⚠️ **不加 deleted 过滤** | forecasting |
| **st_mx_preset_cal_r** | 预报模型结果 | `tenant_id=18 AND deleted=0` | forecasting |
| **weather_warn** | 气象预警 | ⚠️ **不加 tenant/deleted 过滤** | forecasting |
| **weather_info** | 天气预报 | ⚠️ **不加 tenant/deleted 过滤** | forecasting |
| **att_res_flse_lim** | 汛限水位 | ⚠️ **不加 deleted 过滤** | forecasting |
| **att_res_base** | 水库基础信息 | `deleted=0` | forecasting |
| **model_config** | 系统配置 | `tenant_id=18 AND deleted=0` | forecasting |
| **forecast_accuracy_record** | 预报精度记录 | `tenant_id=18 AND deleted=0` | forecasting |

### 预演调度相关 (simulation)

| 表名 | 说明 | 过滤规则 | 来源 |
|------|------|---------|------|
| **srm_flood_history_base** | 历史洪水基础 | `deleted=0` | simulation |
| **srm_flood_history_result** | 历史洪水结果 | `deleted=0` (部分含 tenant_id) | simulation |
| **dispatch_history** | 调度历史 | `deleted=0` | simulation |
| **srm_scheduling_scenario** | 调度场景 | `deleted=0` | simulation |

### 告警相关 (early-warning)

| 表名 | 说明 | 过滤规则 | 来源 |
|------|------|---------|------|
| **ew_info_message** | 告警消息 | `deleted=0` | early-warning |
| **ew_info_rules** | 告警规则 | `deleted=0` | early-warning |

## 诊断 skill 数据源优先级规则

> ⚠️ **必须遵守**: 诊断 skill 跨多个 skill 查询数据时,必须使用各 skill 的正确数据源。

### 数据源优先级

| 诊断目标 | 数据源 | 脚本 | 说明 |
|---------|-------|------|------|
| **水位/降雨预报** | forecasting | `query_forecast_data.py` | 三岔水库 (tenant=18) |
| **预演结果** | simulation | `query_simulation_data.py` | 调度推演 |
| **告警堆积** | early-warning | `query_early_warning.py` | 未确认告警 |
| **历史洪水** | simulation/forecasting | 共享库 `lib.db` | srm_flood_history_* |
| **系统配置** | forecasting | `query_forecast_data.py --type config` | model_config |
| **汛限水位** | forecasting | `query_forecast_data.py --type flood_limit` | att_res_flse_lim |

### ⚠️ 禁止混用规则

诊断 skill 在分析问题时,**禁止**直接查询以下不适用于诊断的数据源:

| 禁用数据源 | 原因 | 正确替代 |
|-----------|------|---------|
| `model_result_files(type=2)` | 调度结果,不适用于水文预报 | `type=1` 预报结果 |
| `sl323` 全区域河道站 | 非三岔水库数据 | 使用 forecasting 的 `tenant_id=18` |
| `dispatch_history` 直接查询 | 必须通过 simulation 脚本 | `query_simulation_data.py` |

## 重要 Caveats（诊断 skill 特别注意）

1. **数据源隔离**: 每个 skill 的数据源优先级不同,诊断时不要混用 (见上方优先级表)
2. **tenant_id 过滤**: forecasting/simulation 使用 `tenant_id=18` (三岔水库),early-warning 不使用 tenant 过滤
3. **deleted 过滤**: model_result_files/weather_warn/att_res_flse_lim **无 deleted 列**,查询时不要加 `AND deleted=0`
4. **taskid 三拼写**: ⚠️ 不同表里 taskid 列名/类型不一致 (见下方说明)
5. **跨 skill 关联**: srm_flood_history_base 同时被 forecasting/simulation/diagnosis 使用,字段需兼容三个 skill

### taskid 三种拼写说明

不同表里「任务ID」的列名/类型不一致,JOIN 时必须显式转换类型:

| 表 | 列名 | 类型 |
|----|------|------|
| `dispatch_history` | `task_id` | varchar(32) — **下划线** |
| `model_result_files` | `taskid` | **varbinary**(32) |
| `st_mx_preset_cal_r` | `taskid` | **varchar** — 无下划线 |

JOIN 示例:
```sql
SELECT m.*, d.dispatch_opening
FROM model_result_files m
LEFT JOIN dispatch_history d
  ON d.task_id = CAST(m.taskid AS CHAR)
WHERE m.type = 1;
```

## 索引建议

```sql
-- 水位查询优化
CREATE INDEX idx_rsvr_r_tm_deleted ON st_rsvr_r(tm, deleted);

-- 告警查询优化
CREATE INDEX idx_ew_info_message_confirm ON ew_info_message(message_confirm, deleted, create_time);

-- 历史洪水查询优化
CREATE INDEX idx_flood_history_status_deleted ON srm_flood_history_base(status, deleted);

-- 降雨预报查询优化
CREATE INDEX idx_rnfl_h_ymdh ON f_rnfl_h(ymdh);
```

## 共享库使用

诊断 skill 应使用 **SmartTwinRes-skills/lib/db.py** 统一数据库库:

```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from lib.db import execute_query_list, _require_env

# 查询水位
sql = "SELECT rz, inq, otq, w, tm FROM st_rsvr_r WHERE deleted=0 AND tenant_id=18 LIMIT 1"
result = execute_query_list(sql)
```

**优势**:
- ✅ 统一超时配置 (connect_timeout=10s, read_timeout=30s)
- ✅ 统一连接池 (dbutils.PooledDB)
- ✅ 统一序列化 (datetime/Decimal/bytes 自动处理)
- ✅ 统一 MAX_ROWS=1000 限制 (防止全表扫描)
- ✅ 强制环境变量检查 (_require_env)

## 验证配置

```bash
# 检查环境变量
env | grep -E "SRM_DB_|POWERELF_DB_"

# 测试连接
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME" -e "SELECT 1"

# 测试共享库
cd SmartTwinRes-skills
python3 -c "from lib.db import get_connection; c=get_connection(); print('✅ 连接成功'); c.close()"
```

## 常见问题

### Q1: 提示 `环境变量 SRM_DB_PASSWORD 未设置`

**解决**: 配置环境变量后重启 Hermes
```bash
export SRM_DB_PASSWORD='your_password'
# 重启 hermes
systemctl --user restart hermes-gateway  # 或直接重启 hermes 进程
```

### Q2: 诊断 skill 查询到错误数据源

**原因**: 混用了 forecasting/simulation/early-warning 的数据源

**解决**: 严格按照上方"数据源优先级"表选择正确的数据源和脚本

### Q3: taskid JOIN 类型不匹配

**原因**: 三个表里 taskid 拼写/类型不一致

**解决**: JOIN 时必须 CAST: `ON d.task_id = CAST(m.taskid AS CHAR)`

---

*维护: SmartTwinRes Team*
*最后更新: 2026-07-11*
*迁移自 forecasting/docs/db-credential-config.md*
