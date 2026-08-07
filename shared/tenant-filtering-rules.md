# 租户过滤铁律（多水库）

> **适用范围**：SmartTwinRes 全部 skill 的 SQL 查询、业务逻辑。
> **背景**：本平台支持多水库（三岔 sancha / 桃曲坡 taoqupo），每个水库一套独立数据库 + 独立服务实例，通过环境变量激活对应水库 profile。

## 一、租户身份来源（优先级）

```
1. 显式传入的参数（函数调用时传 tenant_id=...）
2. 环境变量 SRM_TENANT_ID（部署实例级配置，每水库一套）
3. 默认回退 18（三岔水库，保证现网不设 env 时行为不变）
```

**唯一入口**：`lib/tenant.py` 的 `current_tenant_id()`。

**禁止**在业务代码里硬编码 `18` 或 `20`。

## 二、SQL 必须按 tenant_id 过滤

所有查询水库数据的 SQL，**必须**包含 `WHERE tenant_id = %s`：

```python
from lib.tenant import current_tenant_id
from lib.db import execute_query_list

tid = current_tenant_id()
sql = """
    SELECT stcd, stnm, rz FROM st_stbprp_b
    WHERE tenant_id = %s AND tm >= %s
    LIMIT 1000
"""
rows = execute_query_list(sql, (tid, start_time))
```

**历史 bug**：曾因漏过滤 tenant_id，导致三岔（18）查到桃曲坡（20）的水位数据，汛限水位判断错误。这是 AGENTS.md 第 2 条铁律的由来。

## 三、多水库适配流程

新增水库（如第三个水库）时：

1. 在 `reservoirs/` 下新建 `<name>/` 目录，放入：
   - `identity.md`（水库基本信息）
   - `characteristic-levels.md`（特征水位：汛限/正常/设计/校核）
   - `curve-data.md`（水位-库容-泄流曲线）
   - `stations.md`（测站清单）
   - `defect-disposal.md`（缺陷处置记录）
   - `inspection-items.md`（设备巡检项目）
2. 在数据库里为该水库分配新 `tenant_id`（如 21）。
3. 部署实例设置 `SRM_TENANT_ID=21 SRM_RESERVOIR_NAME=<name>`。
4. **不需要改任何 skill 代码**——所有查询都通过 `current_tenant_id()` 动态获取。

## 四、reservoir profile 定位

水库 profile 目录由 `SRM_RESERVOIR_NAME` 环境变量决定：

```python
from lib.paths import get_reservoir_dir

profile_dir = get_reservoir_dir()  # 默认读 SRM_RESERVOIR_NAME，缺省 sancha
identity = (profile_dir / "identity.md").read_text()
```

**禁止**硬编码 `reservoirs/sancha/...` 字符串——一律用 `get_reservoir_dir()`。

## 五、桃曲坡特殊配置

桃曲坡（taoqupo，tenant 20）需额外设置：

```bash
export SRM_TENANT_ID=20 SRM_RESERVOIR_NAME=taoqupo
```

三岔（sancha，tenant 18）是默认值，无需设置。

## 六、汛限水位差异（重要）

不同水库的汛限水位基准不同，**禁止**跨水库复用兜底曲线：

| 水库 | 汛限水位 | 基准 |
|------|---------|------|
| 三岔 sancha | ~460m | 黄海基面 |
| 桃曲坡 taoqupo | ~788m | 大沽基面 |

模型计算所需水位-库容/泄流曲线**必须**从当前水库的 `curve-data.md` 读取。
