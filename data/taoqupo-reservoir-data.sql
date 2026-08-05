-- =============================================================================
-- 桃曲坡水库数据录入脚本（v2 — 基于现网真实表结构）
-- 项目: SmartTwinRes-skills 多水库扩展
-- 用途: 将桃曲坡水库录入 powerelf_srm_yml，使其可被 skill 按 tenant_id=20 查询
-- ----------------------------------------------------------------------------
-- ⚠️ 本脚本基于 2026-08-04 现网 DESCRIBE 实测（非 table-schema.md 文档）：
--   • 曲线表 att_res_stag_cap_disc / att_res_discharge_curve 已有 res_guid+tenant_id 列 → 无需 ALTER
--   • 现网 3 个水库: 石盘(tenant=17) / 三岔(tenant=18) / 测试水库(tenant=19)
--   • 桃曲坡 tenant_id=20（已确认空闲）；测试水库(19)保留不动
--   • res_guid 沿用现网曲线表习惯 = 中文名 "桃曲坡水库"（用户确认）
--   • model_config 无 (config_key,tenant_id) 唯一键 → 先 DELETE 再 INSERT 保证幂等可重跑
-- 数据来源: reservoirs/taoqupo/*.md + docs/水位-库容-泄流能力曲线详解.md
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 第 0 步：变量（DBA 如需调整，只改这一段）
-- ---------------------------------------------------------------------------
SET @tenant   := 20;                   -- 桃曲坡租户ID（已确认：17石盘/18三岔/19测试/20桃曲坡）
SET @name     := '桃曲坡水库';           -- 水库名称
SET @guid     := '桃曲坡水库';           -- res_guid（现网曲线表习惯用中文名；用户确认）
SET @res_code := 'TQP-RES-2026';       -- ⚠️ res_code 占位（现网三岔=BFA0027855X），DBA 替换为正式编码
SET @dept_id  := 148;                  -- ⚠️ 复用三岔 dept_id=148（开发期占位，DBA 改为桃曲坡管理单位）

-- ---------------------------------------------------------------------------
-- 第 1 步：幂等清理（仅 tenant=20，重跑安全；现网该 tenant 当前为空）
--   注：若首次执行，以下 DELETE 命中 0 行，无副作用
-- ---------------------------------------------------------------------------
DELETE FROM att_res_base            WHERE tenant_id = @tenant;
DELETE FROM att_res_flse_lim        WHERE tenant_id = @tenant;
DELETE FROM att_res_stag_cap_disc   WHERE tenant_id = @tenant;
DELETE FROM att_res_discharge_curve WHERE tenant_id = @tenant;
DELETE FROM model_config            WHERE tenant_id = @tenant;

-- ---------------------------------------------------------------------------
-- 第 2 步：att_res_base 桃曲坡基础信息（NOT NULL 必填: res_code/res_name/dept_id）
--   字段映射依据现网三岔行(id=8)语义 + 桃曲坡 profile 实测值
--   ⚠️ 总库容取 4420（校核洪水位790.5m 库容，与1997实测曲线一致）
--      identity.md 记 5720 疑为早期设计值/含其它口径，待与工程特性表核对后由 DBA 修正
-- ---------------------------------------------------------------------------
INSERT INTO att_res_base (
  res_code, res_name, res_loc, res_type, eng_grea, eng_scal,
  wat_shed_area, upp_lev_flco, norm_wat_lev, norm_pool_stag_cap,
  fl_low_lim_lev, dead_lev, dead_cap, tot_cap,
  design_water_level, check_water_level, avg_rainfall,
  dam_crest_elevation, weir_crest_elevation,
  note, dept_id, pro_id, tenant_id
) VALUES (
  @res_code, @name, '陕西省铜川市耀州区马咀山峡谷', '1', '3', '3',
  1335.00,            -- wat_shed_area  控制流域面积 km²（沮河830+马栏河505）
  788.540,            -- upp_lev_flco   设计洪水位 m（三岔该列=设计洪水位461.96）
  788.500,            -- norm_wat_lev   正常蓄水位 m
  3949.00,            -- norm_pool_stag_cap 正常蓄水位库容 万m³
  786.800,            -- fl_low_lim_lev 主汛限水位 m
  755.000,            -- dead_lev       死水位 m（低洞进口）
  1050.00,            -- dead_cap       死库容 万m³（与曲线一致）
  4420.00,            -- tot_cap        总库容 万m³（校核790.5m，curve一致；5720待核）
  788.540,            -- design_water_level 设计洪水位 m（百年一遇）
  790.500,            -- check_water_level  校核洪水位 m（千年一遇）
  512.80,             -- avg_rainfall   多年平均降雨量 mm
  '792',              -- dam_crest_elevation 坝顶高程 m
  '783.5',            -- weir_crest_elevation 溢洪道堰顶高程 m
  '桃曲坡水库位于陕西省铜川市耀州区，渭河水系石川河支流沮水河下游，Ⅲ等中型水库，以灌溉、防洪、城市供水为主。坝顶高程792m，溢洪道堰顶783.5m，校核洪水位790.5m。多数据见 reservoirs/taoqupo/。',
  @dept_id, 142, @tenant
);

-- ---------------------------------------------------------------------------
-- 第 3 步：att_res_flse_lim 汛限分段（3 段）
--   主汛 7-9月 786.8m；次汛 6月+10月 788.0m
--   注：现网三岔 flse_lim.res_guid 用 res_code(BFA...)，此处按用户确认统一用中文名；
--       该表实际按 tenant_id 过滤，res_guid 仅作标识，不影响查询。
-- ---------------------------------------------------------------------------
INSERT INTO att_res_flse_lim (flse_lim_stag, flood_season_name, flood_season_start, flood_season_end, res_guid, tenant_id) VALUES
  (786.800, '主汛期', '0701', '0930', @guid, @tenant),
  (788.000, '次汛期', '0601', '0630', @guid, @tenant),
  (788.000, '次汛期', '1001', '1031', @guid, @tenant);

-- ---------------------------------------------------------------------------
-- 第 4 步：att_res_stag_cap_disc 水位-库容曲线（8 关键节点，调洪工作段 783.5–790.5m）
--   来源: docs/水位-库容-泄流能力曲线详解.md §2.1（1997实测，溢洪道堰顶→校核洪水位）
--   注：仅录调洪工作段（汛期洪水运行区间）；低水段查对表(762.5-783.5m)待与 DBA 核定基面后补录。
-- ---------------------------------------------------------------------------
INSERT INTO att_res_stag_cap_disc (stag, cap, order_id, res_guid, tenant_id, title) VALUES
  (783.5, 2820, 1, @guid, @tenant, '水位-库容曲线'),
  (784.5, 3020, 1, @guid, @tenant, '水位-库容曲线'),
  (785.5, 3250, 1, @guid, @tenant, '水位-库容曲线'),
  (786.5, 3485, 1, @guid, @tenant, '水位-库容曲线'),
  (787.5, 3719, 1, @guid, @tenant, '水位-库容曲线'),
  (788.5, 3949, 1, @guid, @tenant, '水位-库容曲线'),  -- 正常蓄水位
  (789.5, 4175, 1, @guid, @tenant, '水位-库容曲线'),
  (790.5, 4420, 1, @guid, @tenant, '水位-库容曲线');  -- 校核洪水位

-- ---------------------------------------------------------------------------
-- 第 5 步：att_res_discharge_curve 水位-泄流曲线（8 节点，总泄量 = 溢洪道 + 低洞97）
-- ---------------------------------------------------------------------------
INSERT INTO att_res_discharge_curve (stag, q, order_id, res_guid, tenant_id, title) VALUES
  (783.5,   97, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),  -- 堰顶，仅低洞
  (784.5,  241, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),
  (785.5,  447, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),
  (786.5,  747, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),
  (787.5, 1087, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),
  (788.5, 1507, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),  -- 正常蓄水位
  (789.5, 1947, 1, @guid, @tenant, '水位-泄流曲线(总泄量)'),
  (790.5, 2331, 1, @guid, @tenant, '水位-泄流曲线(总泄量)');  -- 校核洪水位

-- ---------------------------------------------------------------------------
-- 第 6 步：model_config 桃曲坡配置键（tenant=20，17 键）
--   skill 的 get_master_stcd / query_config 按这些键 + tenant 动态读取
--   ⚠️ st_rsvr_r_master / st_pptn_r_master = 'TBD'：桃曲坡 SRM 系统站码待 DBA 分配
--      （站码不在调度文档中，属 SRM 实时数据接入范畴，不影响静态曲线/阈值验证）
-- ---------------------------------------------------------------------------
INSERT INTO model_config (config_key, value, tenant_id, deleted) VALUES
  ('st_rsvr_r_master',          'TBD',      @tenant, 0),   -- ⚠️ 待 SRM 水位master站码
  ('st_pptn_r_master',          'TBD',      @tenant, 0),   -- ⚠️ 待 SRM 雨量master站码
  ('res_guid',                  '桃曲坡水库', @tenant, 0),
  ('watershed_area_km2',        '1335',     @tenant, 0),
  ('total_storage',             '4420',     @tenant, 0),   -- 校核洪水位库容万m³（curve一致）
  ('flood_limit_main',          '786.8',    @tenant, 0),   -- 主汛限（7-9月）
  ('flood_limit_secondary',     '788.0',    @tenant, 0),   -- 次汛限（6/10月）
  ('normal_pool_level',         '788.5',    @tenant, 0),
  ('design_flood_level',        '788.54',   @tenant, 0),   -- 百年一遇
  ('check_flood_level',         '790.5',    @tenant, 0),   -- 千年一遇
  ('dead_water_level',          '755',      @tenant, 0),
  ('max_drainage_capacity',     '2331',     @tenant, 0),   -- 校核总最大泄量 m³/s
  ('safe_drainage_capacity',    '500',      @tenant, 0),   -- 下游设计安全泄量 m³/s
  ('max_water_level',           '790.5',    @tenant, 0),
  ('min_water_level',           '755',      @tenant, 0),
  ('highest_water_level_history','789.29',  @tenant, 0),   -- 2025-10 历史最高
  ('lowest_water_level_history', '755',     @tenant, 0);

-- ===========================================================================
-- 第 7 步：自检（执行后逐条核对）
-- ===========================================================================

-- 7.1 全水库总览（应 4 行：17石盘/18三岔/19测试/20桃曲坡）
SELECT '7.1 reservoirs in att_res_base' AS step;
SELECT tenant_id, id, res_code, res_name FROM att_res_base ORDER BY tenant_id;

-- 7.2 桃曲坡 config 键完整度（应 17 行）
SELECT '7.2 taoqupo model_config keys (expect 17)' AS step;
SELECT COUNT(*) AS taoqupo_config_keys FROM model_config WHERE tenant_id = @tenant;

-- 7.3 曲线多水库隔离（三岔18 不受影响；桃曲坡20 各 8 点）
SELECT '7.3 curve tenant isolation' AS step;
SELECT tenant_id, COUNT(*) AS cap_points FROM att_res_stag_cap_disc   GROUP BY tenant_id ORDER BY tenant_id;
SELECT tenant_id, COUNT(*) AS q_points   FROM att_res_discharge_curve GROUP BY tenant_id ORDER BY tenant_id;

-- 7.4 桃曲坡汛限分段（应 3 行：主汛786.8 / 次汛788.0×2）
SELECT '7.4 taoqupo flood-limit segments (expect 3)' AS step;
SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
FROM att_res_flse_lim WHERE tenant_id = @tenant ORDER BY flood_season_start;

-- 7.5 曲线点抽查（788.5→cap3949/q1507；790.5→cap4420/q2331）
SELECT '7.5 curve spot check' AS step;
SELECT stag, cap FROM att_res_stag_cap_disc   WHERE tenant_id=@tenant AND stag IN (788.5, 790.5) ORDER BY stag;
SELECT stag, q   FROM att_res_discharge_curve WHERE tenant_id=@tenant AND stag IN (788.5, 790.5) ORDER BY stag;

-- 7.6 串库检测（桃曲坡曲线不应出现三岔水位段，应 0 行）
SELECT '7.6 cross-contamination check (expect 0)' AS step;
SELECT COUNT(*) AS cross_contamination FROM att_res_stag_cap_disc
WHERE tenant_id=@tenant AND (stag < 783 OR stag > 791);

-- ===========================================================================
-- 回滚（撤销本次录入，恢复 tenant=20 为空）
-- ===========================================================================
-- DELETE FROM att_res_base            WHERE tenant_id = 20;
-- DELETE FROM att_res_flse_lim        WHERE tenant_id = 20;
-- DELETE FROM att_res_stag_cap_disc   WHERE tenant_id = 20;
-- DELETE FROM att_res_discharge_curve WHERE tenant_id = 20;
-- DELETE FROM model_config            WHERE tenant_id = 20;
