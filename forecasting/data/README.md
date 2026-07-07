# data/ -- 预报模拟数据层

本目录是 forecasting skill 的**数据层**:Task 3/4 的查询脚本与 Task 8 的 eval 直接读取这里产出的数据。
对标 `plan-generation/data/README.md` 的三层结构(参数 → 生成 → 验证)。

**生成器覆盖**:`generate_forecast_data.py` 一次性填满 **10 张表**(实测 5 + 预报 3 + 预警/闸门 2),
支持 **15 种故障注入**(6 类 A~F)、**2 个场景序列**、跨源物理一致性,以及 **MOCK 标记 + 一键清理**。
默认是**手动窗口模式**(演示前跑一次即可);cron 可选(见 §5.6)。

## 文件清单

| 文件 | 作用 |
|------|------|
| `generate_forecast_data.py` | 预报 demo 数据模拟器:默认手动窗口 + 10 表 + 15 故障 + 场景 + 跨源一致 + 清理 |
| `baseline_seed.sql` | 三岔 (tenant 18) 基线显式 seed:汛限 + model_config 关键键(幂等) |
| `purge_mock.sql` | 一键清理全 MOCK 行(各表 marker + 脏故障行),`--purge-mock` 调用 |
| `crontab.demo` | 可选 cron 部署(每 ~50min `--roll` 持续新鲜),默认不用 —— 手动窗口为主 |
| `generate_test.py` | 生成器的 window 模型单元测试(T1) |
| `scenarios/nmc_rainfall_24.json` | NMC 24h 降雨预报 HTTP fixture(JSONP,含 ≥1 场强降雨) |
| `scenarios/backup_flse_lim.sql` | E 类故障(missing_flood_limit)备份:`--clear-faults` 从此还原 att_res_flse_lim |
| `scenarios/backup_master_stcd.txt` | F 类故障(bad_master_stcd)备份:`--clear-faults` 从此还原 model_config master |
| `scenarios/` | 场景 seed / 备份目录 |

---

## 1. 参数-覆盖矩阵(生成器内置波形)

生成器内置物理合理的波形,覆盖预报评测的核心维度:

| 维度 | 取值范围 | 实现位置 |
|------|----------|----------|
| **预见期** | 24h(实测接续)/ 72h(模型预报)/ 60d(精度回溯) | `extend_model_forecast` / `create_mock_accuracy` |
| **降雨量级** | 45~80mm(三角分布,可调 `total_mm`) | `gen_rainfall_series` |
| **水位区间** | 基线 459.5 → 逼近汛限 462.2(含上涨段) | `gen_water_level_wave` |
| **流量区间** | 入库 30~800 m³/s,出库 = 入库×0.85(削峰) | `gen_inflow_series` |
| **季节** | 主汛期 0701~0831(`att_res_flse_lim` id=2, 462.5m) | `baseline_seed.sql` |
| **预报源** | XAJ(模型)/ NMC(fixture)/ MOCK(精度表) | `extend_model_forecast` / NMC fixture / `forecast_accuracy_record.source` |

## 2. 断点接续说明

生成器读各表 `MAX(tm)` 真实断点,从断点+1h 续写到 `NOW`(每小时 1 行),保持时序连续:

| 表 | 真实断点(实测) | 续写策略 |
|----|------------------|----------|
| `st_rsvr_r` | tenant18 stcd='3' → 续到 NOW | 48h 水位/流量波形 |
| `st_pptn_r` | tenant18 stcd='46' → 续到 NOW | 48h 降雨(三角) |
| `st_mx_preset_cal_r` | taskid LIKE 'MOCK%' → NOW+72h | type 22 水位 + type 21 流量 |
| `model_result_files` | alias='MOCK' → NOW | 1 行(type=1, 72h horizon) |
| `weather_info` | fx_date 2025-07(断档近 1 年) | NOW-7d → NOW 重建 |
| `f_rnfl_h` | YMDH 停在 2026-06-10(过去) | NOW+1h → NOW+168h 未来逐时降雨(暴雨波形) |
| `st_pptn_re_forecast` | tm 2025-12(断档近 6 月) | re_id>=9000 区段:过去 24h + 未来 168h |
| `forecast_accuracy_record` | 新建表 | 60d 合成预报-实测对 |

**重要**:`st_rsvr_r_master`/`st_pptn_r_master` 的 config 值(`3`/`46`)作为 mock 行的 `stcd`,
与 `model_config` 保持一致 —— 这样下游 Task 3/4 脚本读取 config master stcd 时能命中 mock 行。

## 3. MOCK 标记规则(可清理性)

**每条 mock 行必须可识别**,清理命令见下方第 4 节:

| 表 | MOCK 标记列 | 标记值 |
|----|------------|--------|
| `st_rsvr_r` | `creator` | `'MOCK'` |
| `st_pptn_r` | `creator` | `'MOCK'` |
| `model_result_files` | `alias` + `taskid` | `alias='MOCK'` / `taskid LIKE 'MOCK%'`(+ 脏故障 `taskid LIKE 'JUNK%'`/`='MOCK-ORPHAN'`) |
| `st_mx_preset_cal_r` | `taskid` | `LIKE 'MOCK%'` |
| `weather_info` | `icon_day` | `'MOCK'` |
| `weather_warn` | `docabstract` | `LIKE '%[MOCK]%'`(无 tenant_id 列) |
| `dispatch_history` | `dispatch_opening` | `LIKE '%[MOCK]%'` |
| `f_rnfl_h` | `COMMENTS` | `'MOCK'`(tenant_id=1, UNITNAME='1', TYPE='1') |
| `st_pptn_re_forecast` | `re_id` | `>= 9000`(mock 区段) |
| `forecast_accuracy_record` | `remark` | `'MOCK'` |

> **10 张表全覆盖**:实测 5(st_rsvr_r/st_pptn_r/model_result_files/dispatch_history/weather_warn)+
> 预报 3(f_rnfl_h/st_mx_preset_cal_r/st_pptn_re_forecast)+ 重建 2(weather_info/forecast_accuracy_record)。

## 4. 清理命令(一键回滚所有 mock 数据)

一键清理:`python3 data/generate_forecast_data.py --purge-mock`(跑 `purge_mock.sql`),
或手动执行等价 SQL(10 表全标记 + 脏故障行 JUNK/ORPHAN):

```sql
-- 预报 mock 数据一键清理(不影响真实数据)
DELETE FROM st_rsvr_r              WHERE creator='MOCK';
DELETE FROM st_pptn_r              WHERE creator='MOCK';
DELETE FROM st_mx_preset_cal_r     WHERE taskid LIKE 'MOCK%';
DELETE FROM model_result_files     WHERE alias='MOCK' OR taskid LIKE 'MOCK%';
DELETE FROM model_result_files     WHERE taskid LIKE 'JUNK%';        -- future_junk 脏行
DELETE FROM model_result_files     WHERE taskid='MOCK-ORPHAN';        -- taskid_orphan 脏行
DELETE FROM weather_info           WHERE icon_day='MOCK';
DELETE FROM weather_warn           WHERE docabstract LIKE '%[MOCK]%';
DELETE FROM dispatch_history       WHERE dispatch_opening LIKE '%[MOCK]%';
DELETE FROM f_rnfl_h               WHERE COMMENTS='MOCK';
DELETE FROM st_pptn_re_forecast    WHERE re_id >= 9000;
DELETE FROM forecast_accuracy_record WHERE remark='MOCK';
```

> 还原 E/F 配置故障(改过真实 seed/config 表)须额外跑 `--clear-faults`,它从备份还原
> `att_res_flse_lim`(3 行)+ `model_config.st_rsvr_r_master`(原值)。
> **注**:`st_pptn_re_forecast` 的 8402 条真实数据(从 103 迁入)不受影响 —— mock 行用 `re_id>=9000` 隔离。

## 5. 用法

### 5.1 准备环境变量

```bash
export SRM_DB_HOST=127.0.0.1 SRM_DB_PORT=3306 SRM_DB_NAME=powerelf_srm_yml SRM_DB_USER=root
export SRM_DB_PASSWORD   # 从 application-prod.yaml 取值,严禁写入本仓库
```

### 5.2 跑 baseline seed(幂等,首次必跑)

```bash
mysql -h $SRM_DB_HOST -u root -p"$SRM_DB_PASSWORD" $SRM_DB_NAME < data/baseline_seed.sql
```

### 5.3 跑数据生成器(默认 = 手动窗口模式)

**默认用法是【手动窗口模式】**:演示前手动跑一次 `generate_forecast_data.py`(无任何模式标志),
即生成标准 demo 窗口(实测 NOW-30d→NOW,预报 NOW→NOW+168h),10 表全覆盖。这是最常见的用法。

```bash
# ★ 默认:标准 demo 窗口(手动)—— 演示前跑这一条即可
python3 data/generate_forecast_data.py
#   → obs[NOW-30d → NOW]   实测接续(8 表实测/历史类)
#   → fc [NOW → NOW+168h]  预报续写(3 表预报类)
#   → 一并写 scenarios/nmc_rainfall_24.json (NMC fixture)

# 自定义时间窗口(--start/--end,日期 YYYY-MM-DD)
python3 data/generate_forecast_data.py --start 2026-06-01 --end 2026-06-30
#   → obs[min(end,NOW) 钳到 NOW], fc[max(start,NOW) 钳到 NOW]:实测段不越未来、预报段不越过去

# 断点续到 NOW(--roll):读各表 MAX(tm) 真实断点,从断点+1h 续到 NOW。
#   这是【cron 可选】路径,见 §5.6;手动演示一般不用。
python3 data/generate_forecast_data.py --roll

# 只写 NMC JSONP fixture(不连 DB,离线可用)
python3 data/generate_forecast_data.py --nmc-fixture

# 兼容旧标志(仍可用,映射到 extender 子集;=默认 demo 窗口语义)
python3 data/generate_forecast_data.py --extend-all                 # 全部 extender
python3 data/generate_forecast_data.py --extend-observed            # st_rsvr_r + st_pptn_r
python3 data/generate_forecast_data.py --extend-model               # model_result_files + st_mx_preset_cal_r
python3 data/generate_forecast_data.py --extend-rainfall            # f_rnfl_h 未来 168h 逐时降雨
python3 data/generate_forecast_data.py --rebuild-stale              # weather_info + st_pptn_re_forecast
python3 data/generate_forecast_data.py --mock-accuracy              # forecast_accuracy_record
python3 data/generate_forecast_data.py --warn-dispatch              # weather_warn + dispatch_history

# 执行模式控制(任何生成/故障命令均可叠加)
python3 data/generate_forecast_data.py --dry-run                    # 只打印 SQL,不执行(预览)
python3 data/generate_forecast_data.py --via-mysql-cli              # 渲染 SQL 到 /tmp 后用 mysql 客户端执行(无 pymysql 环境)
```

### 5.4 故障注入(`--inject-fault`,共 15 种 / 6 类 A~F)

在已生成的 mock 数据上 **OVERLAY** 故障条件(只动 MOCK 标记行,绝不触碰真实数据,
除 E/F 两类配置故障 —— 它们改真实 seed/config 表,见下方说明 + §5.5 还原)。
可逗号分隔一次注入多种;`--at YYYY-MM-DD HH:MM` 指定注入时刻(默认 NOW)。

| 类 | 故障名 | 模拟的异常 | 预期下游检出 |
|----|--------|-----------|-------------|
| **A 断档** | `stale_forecast` | f_rnfl_h FYMDH 锁在 NOW-7d(预报发布极旧) | 预报源过期/不刷新 |
| | `stale_observed` | st_rsvr_r/st_pptn_r mock 截到 NOW-11d | 实测长期断档 |
| | `null_observed` | f_rnfl_h 有预报但近 24h pptn 空 | 预报存在而实测缺测 |
| | `empty_model` | st_mx_preset_cal_r/model_result_files 空 | 模型预报结果缺失 |
| | `gated_accuracy` | forecast_accuracy_record 空 | 精度评分被 gate |
| **B 冲突** | `source_disagree` | 和风 f_rnfl_h 120mm/24h vs 分区 60mm/24h | 多源降雨分歧(>20mm) |
| | `single_source` | 仅留和风,删分区 + weather_info | 单源缺失 |
| **C 越限** | `over_flood_limit` | st_rsvr_r 水位 462.0→462.92 越过汛限 462.5 | 水位超汛限告警 |
| | `extreme_storm` | f_rnfl_h 144mm/24h + 红色 weather_warn | 极端暴雨预警 |
| | `drought` | 7d st_pptn_r≈0 + st_rsvr_r 逼近死水位 451 | 干旱 |
| **D 脏数据** | `future_junk` | model_result_files create_time=NOW+90d(未来脏行) | 未来时间戳脏数据 |
| | `negative_rain` | st_pptn_r dr=-1.0(负降雨) | 物理量负值脏数据 |
| | `taskid_orphan` | model_result_files 有 taskid 但 st_mx_preset_cal_r 无对应 | JOIN 空集(孤儿 taskid) |
| **E 配置**(改真实 seed) | `missing_flood_limit` | 清空真实 att_res_flse_lim(3 行汛期) | 汛限缺失,回退 att_res_base |
| **F 配置**(改真实 config) | `bad_master_stcd` | UPDATE model_config.st_rsvr_r_master='999999' | master 站码配置错误 |

> **E/F 两类改真实 seed/config 表**,注入前自动 `_backup_for_fault` dump 到
> `scenarios/backup_flse_lim.sql` / `scenarios/backup_master_stcd.txt`(随 repo 提交);
> demo 后必须用 `--clear-faults`(§5.5)还原。E/F 仅 direct 模式生效(via_cli 无法回读备份)。

```bash
python3 data/generate_forecast_data.py --inject-fault stale_forecast
python3 data/generate_forecast_data.py --inject-fault source_disagree,over_flood_limit   # 多故障叠加
python3 data/generate_forecast_data.py --inject-fault extreme_storm --at "2026-06-25 09:00"
```

### 5.5 场景触发 / 清理 / 还原

```bash
# 场景序列(live demo 故事线,多步 win→fault 自动编排)
python3 data/generate_forecast_data.py --scenario demo_flow   # 平静→暴雨→超汛限→退水(3 步)
python3 data/generate_forecast_data.py --scenario extreme     # 仅极端组合(2 步,无前置正常生成)

# 清全部 MOCK 行(各表 marker + JUNK/ORPHAN 脏故障行)—— 一键回滚所有 mock,不动真实数据
python3 data/generate_forecast_data.py --purge-mock

# 清除已注入故障 + 还原真实 seed/config 表(E/F)—— 演示后必跑,把数据重置为正常 demo 态
#   (a) purge-mock → (b) 重跑正常窗口生成 → (c) _restore_config × 2(att_res_flse_lim 3 行 + master='3')
python3 data/generate_forecast_data.py --clear-faults
```

`--clear-faults` 是 E/F 配置故障后**唯一**的还原手段:它不仅清 mock、重生成,
还会从备份文件把 `att_res_flse_lim`(3 行汛期)和 `model_config.st_rsvr_r_master`(原值,
通常 `'3'`)还原。漏跑会让真实表停在故障态(汛限空 / master='999999'),demo 后无法恢复。

### 5.6 cron 可选部署(持续新鲜)

默认手动窗口模式已足够 demo。若需 mock 数据**长期实时跟随系统时钟**(无需每次手动重跑),
可选部署 `crontab.demo`:每 ~50min 跑一次 `--roll`(断点续到 NOW),flock 防重叠。

```bash
# 部署:把 <预置> 换成 application-prod.yaml 真实 DB 密码(严禁提交),再 crontab crontab.demo
cp data/crontab.demo /tmp/crontab.demo   # 编辑 <预置> 后:crontab /tmp/crontab.demo
# 日志:/var/log/demo-sim.log
```

详见 `crontab.demo` 注释。**不需要可不装** —— 手动 `generate_forecast_data.py` 是默认主用法。

### 5.7 跨源物理一致性(T7)

默认/暴雨 demo 路径下,水位、实测雨、预报雨、模型预报水位由**同一个降雨事件**驱动
(`gen_coherent_event`):实测雨是预报雨的滞后(+OBS_LAG_HOURS)+ 偏差(×OBS_BIAS)重现;
水位由实测雨累积驱动(径流系数 RUNOFF_COEFF × 汇流滞后 WL_LAG_HOURS);
模型预报水位取实测末水位为起点、沿同一预报雨继续累积。这样一条连续雨型被 obs/fc 两窗口共同
覆盖,实测峰早于模型预报峰,呈现"实测已涨 → 模型预报继续涨"的连贯故事线。
(`--roll` 断点动态续写为 cron 边缘路径,回退独立波形。)

### 5.8 验证(MAX(tm)≈ NOW)

```sql
-- 默认窗口跑完后:10 表 MAX(tm) 检查
SELECT 'st_rsvr_r' t, MAX(tm) max_tm FROM st_rsvr_r WHERE creator='MOCK'            -- ≈ NOW(实测)
UNION ALL SELECT 'st_pptn_r', MAX(tm) FROM st_pptn_r WHERE creator='MOCK'           -- ≈ NOW(实测)
UNION ALL SELECT 'f_rnfl_h', MAX(YMDH) FROM f_rnfl_h WHERE COMMENTS='MOCK'          -- ≈ NOW+168h(预报)
UNION ALL SELECT 'st_mx_preset_cal_r', MAX(tm) FROM st_mx_preset_cal_r WHERE taskid LIKE 'MOCK%'  -- ≈ NOW+168h
UNION ALL SELECT 'model_result_files', MAX(create_time) FROM model_result_files WHERE alias='MOCK'  -- ≈ NOW
UNION ALL SELECT 'st_pptn_re_forecast', MAX(tm) FROM st_pptn_re_forecast WHERE re_id>=9000  -- ≈ NOW+168h
UNION ALL SELECT 'weather_info', MAX(fx_date) FROM weather_info WHERE icon_day='MOCK'  -- ≈ NOW 当日
UNION ALL SELECT 'weather_warn', MAX(docpubtime) FROM weather_warn WHERE docabstract LIKE '%[MOCK]%'  -- ≈ NOW
UNION ALL SELECT 'dispatch_history', MAX(tm) FROM dispatch_history WHERE dispatch_opening LIKE '%[MOCK]%'  -- ≈ NOW
UNION ALL SELECT 'forecast_accuracy_record', MAX(issued_tm) FROM forecast_accuracy_record WHERE remark='MOCK';  -- ≈ NOW-1d
```

## 6. NMC fixture 说明

`scenarios/nmc_rainfall_24.json`:合法 JSONP `diamond14_rainfall_24_json({ "contours": [...] })`。

- 生产代码 `rainfallController.getRainfallForecast` 实时从 `typhoon.nmc.cn` 拉取此格式,JSONP wrapper 由 controller 剥离。
- mock 时:把 `typhoon.nmc.cn` 指向本文件(或 skill 直接读 fixture 解析 JSONP body)。
- 含 5 条等值线(10/25/50/100/250mm),其中 ≥1 场强降雨(100mm + 250mm 暴雨-大暴雨)。

## 7. 数据来源与对标

- 真实断点:LOCAL `127.0.0.1` `powerelf_srm_yml` 各表 `MAX(tm)`(见第 2 节)。
- `st_pptn_re_forecast`:8402 行从 `192.168.100.103` 迁入(只读源,mysqldump)。
- 物理常量:三岔水库实测/设计值,`baseline_seed.sql` 显式 seed(`att_res_base id=8` 实测汛限)。
- 对标:`simulation/tests/generate_test_data_v2.py`(预演 skill 的数据补充脚本,同款断点接续思路)。
