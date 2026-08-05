# 新增水库标准流程（Reservoir Onboarding SOP）

> **目的**：把"新增一个水库"变成可复制的标准操作，实现快速迁移部署。
> **适用**：独立部署形态——每个水库一套独立数据库 + 独立服务实例，代码仓库单一。
> **参考实例**：桃曲坡水库（见 `data/taoqupo-reservoir-data.sql`）。

---

## 一、整体流程（7 步）

```
1. 定 tenant_id          → DBA 分配未占用号
2. 部署代码              → git clone 仓库到新实例
3. 建库 + DDL            → 建库，执行表 DDL（含曲线表加列）
4. 录数据                → DBA 执行录入 SQL（model_config + att_res + 曲线）
5. 配 env                → SRM_TENANT_ID / SRM_RESERVOIR_NAME / SRM_DB_*
6. 填 reservoir profile  → reservoirs/{水库名}/ 6 个 md（从该水库 PDF 提取）
7. 跑验证                → test_skills.py --reservoir {名} --all
```

---

## 二、逐步详解

### 步骤 1：确定 tenant_id
- 向 DBA 申请一个现网未占用的租户号。现网占用情况（截至 2026-08-04）：17=石盘 / 18=三岔 / 19=测试水库 / **20=桃曲坡**。下一个新水库建议从 21 起。
- 该值将贯穿 model_config / att_res_base / 曲线表的所有录入行。

### 步骤 2：部署代码
```bash
git clone <repo> /home/scada/SmartTwinRes-skills
cd SmartTwinRes-skills
git checkout feat/multi-reservoir   # 多水库扩展分支
```
> 代码仓库单一，所有水库 profile 都在仓库内（`reservoirs/{name}/`），靠 env 激活对应 profile。

### 步骤 3：建库 + DDL
- 建独立数据库实例（或独立 schema）。
- 执行项目表 DDL。
- **曲线表 `res_guid` + `tenant_id` 列**：现网 `powerelf_srm_yml` 的 `att_res_stag_cap_disc` / `att_res_discharge_curve` **已含**这两列（实测确认），按平台当前 DDL 建新库即已包含。**仅当迁移缺列的旧库时**才需 `ALTER TABLE ... ADD COLUMN`（脚本旧版有注释，新库默认跳过）。
- 录入脚本采用"先 `DELETE WHERE tenant_id=X` 再 `INSERT`"的幂等模式，可安全重跑。

### 步骤 4：录数据（DBA 执行）
参照 `data/taoqupo-reservoir-data.sql`，按新水库参数改写后执行。**必须录入**：

| 表 | 内容 | 关键字段 |
|---|---|---|
| `model_config` | 配置键全集（17键） | config_key / value / tenant_id |
| `att_res_base` | 水库基础（1行） | fl_low_lim_lev / dead_level / tenant_id |
| `att_res_flse_lim` | 汛限分段（主汛/次汛） | flse_lim_stag / 汛期起止(MMdd) |
| `att_res_stag_cap_disc` | 水位-库容曲线（逐点） | stag / cap / tenant_id / res_guid |
| `att_res_discharge_curve` | 泄流曲线（逐点） | stag / q / tenant_id / res_guid |

> model_config 必填键：`st_rsvr_r_master`/`st_pptn_r_master`/`res_guid`/`watershed_area_km2`/
> `flood_limit_main`/`flood_limit_secondary`/`normal_pool_level`/`design_flood_level`/
> `check_flood_level`/`dead_water_level`/`total_storage`/`max_drainage_capacity`/`safe_drainage_capacity`/
> `max_water_level`/`min_water_level`。

执行后跑自检 SQL（脚本第8步）确认：曲线点数、汛限分段数、config 键完整度、串库检测。

### 步骤 5：配环境变量
```bash
# ~/.bashrc 或 systemd service
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=<该水库库>
export SRM_DB_USER=<user>
export SRM_DB_PASSWORD=<pass>
export SRM_TENANT_ID=<该水库 tenant>        # 多水库身份
export SRM_RESERVOIR_NAME=<该水库 profile名>  # 激活 reservoirs/{名}/
```
> 切换水库 = 改这两个 env，代码零改动。详见 `DB-CONFIG-STANDARD.md`。

### 步骤 6：填 reservoir profile
在 `reservoirs/{水库名}/` 下建 6 个 md（从该水库的预案/规程/鉴定 PDF 提取）：

| 文件 | 内容 | 数据来源 |
|---|---|---|
| `identity.md` | tenant/流域/总库容/坝型/枢纽组成/安全鉴定 | 调度规程、应急预案 |
| `characteristic-levels.md` | 特征水位 + 预警阈值 + 洪峰分级 + 调洪规则 | 汛期调度运用计划 |
| `curve-data.md` | 水位-库容-泄流曲线 + 物理校验规则 | 调度计划附表 |
| `stations.md` | 水文站/雨量站主数据 + 监测频次 | 应急预案 |
| `inspection-items.md` | 巡检对象×检查项 + 频次 + 路线 | 应急预案巡查章 |
| `defect-disposal.md` | 险情处置措施 + 抢险资源 | 应急预案处置章 |

> 桃曲坡是完整样板，复制 `reservoirs/taoqupo/` 改数值即可。
> PDF 提取方法见 `pdf_text_analysis/`（pdfplumber + tesseract OCR）。

### 步骤 7：跑验证
```bash
python3 test_skills.py --reservoir {水库名} --all --timeout 300
# 以及 hermes 端到端：
hermes chat -q "{水库名}的汛限水位是多少" --skills plan-generation -Q
```
- 看关键数值命中（汛限/特征水位/曲线点）。
- **防串库**：forbidden_keywords 检查不出现其他水库的数值（如桃曲坡不应出现 462.5）。

---

## 三、桃曲坡实例对照

桃曲坡已完成本流程的代码/知识/数据脚本层：

| 步骤 | 桃曲坡产物 | 状态 |
|---|---|---|
| 1 tenant_id | **20（已分配）** | ✅ |
| 2 代码 | `feat/multi-reservoir` 分支 | ✅ |
| 3 DDL | 曲线表已含列，无需 ALTER | ✅ |
| 4 录数据 | `data/taoqupo-reservoir-data.sql`（已执行） | ✅ |
| 5 env | `SRM_TENANT_ID=20 SRM_RESERVOIR_NAME=taoqupo` | ⏳ 待部署 |
| 6 profile | `reservoirs/taoqupo/` 6 文件 | ✅ |
| 7 验证 | config/flood_limit/曲线 按 tenant=20 命中 ✅；曲线串库修复 ✅；hermes 端到端已跑通（主汛限786.8/设计788.54/校核790.5/泄量2331，无三岔污染） | ✅ |

---

## 四、常见问题

| 问题 | 处理 |
|---|---|
| 曲线表无 tenant_id 列 | 现网平台 DDL 已含该列；仅旧库迁移时需 ALTER 加列（步骤3） |
| model_config 读不到值 | 确认 config_key 拼写、tenant_id 匹配、deleted=0；数值比较需 CAST |
| agent 返回其他水库数值 | 检查 SRM_RESERVOIR_NAME env；reservoir profile 是否填对；hermes 重启使 env 生效 |
| 位移/沉陷监测误报缺失 | 这些是季度人工观测，不套 60min 在线阈值（见 profile stations.md） |
| 站名↔eq_equip_base.code 对不上 | 文档站名需现场补 eq_business_equip_relation 映射表 |
