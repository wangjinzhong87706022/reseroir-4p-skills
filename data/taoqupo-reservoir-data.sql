-- =============================================================================
-- 桃曲坡水库数据录入脚本
-- 项目: SmartTwinRes-skills 多水库扩展
-- 用途: 将桃曲坡水库录入数据库，使其可被 skill 按 tenant_id 查询
-- 前置: 由 DBA 在现网执行；执行前务必核对变量值（标 ⚠️TBD 的项）
-- 数据来源: reservoirs/taoqupo/*.md（2026 防洪抢险应急预案/汛期调度运用计划/调度规程）
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 第 0 步：变量定义（⚠️ DBA 执行前请核对/修改这些值）
-- ---------------------------------------------------------------------------
SET @taoqupo_tenant   := 19;                       -- ⚠️ 桃曲坡租户ID（建议19，确认现网未占用）
SET @taoqupo_guid     := 'RES-TAOQUPO-2026-TBD';   -- ⚠️ 桃曲坡水库GUID（建议现场生成正式GUID替换）
SET @sancha_tenant    := 18;                       -- 三岔租户ID（回填用）
SET @stcd_rsvr_master := 'TBD';                    -- ⚠️ 桃曲坡水位master站码（待现网分配）
SET @stcd_pptn_master := 'TBD';                    -- ⚠️ 桃曲坡雨量master站码（待现网分配）

-- ===========================================================================
-- 第 1 步：曲线表 DDL 加列（多水库支持，用户已确认方案）
--   两表原本只有 stag/cap(q)，无 tenant_id/res_guid，无法区分多水库
--   加列后与 att_res_base 等 att_* 表的 res_guid 体系对齐
--   表是百条级静态表，DDL 风险极低
-- ===========================================================================

-- 1.1 水位-库容曲线加列
ALTER TABLE att_res_stag_cap_disc
  ADD COLUMN res_guid  VARCHAR(64) DEFAULT NULL COMMENT '水库GUID（多水库路由）',
  ADD COLUMN tenant_id BIGINT     DEFAULT NULL COMMENT '租户ID（多水库隔离）',
  ADD INDEX idx_tenant_stag (tenant_id, stag);

-- 1.2 泄流曲线加列
ALTER TABLE att_res_discharge_curve
  ADD COLUMN res_guid  VARCHAR(64) DEFAULT NULL COMMENT '水库GUID（多水库路由）',
  ADD COLUMN tenant_id BIGINT     DEFAULT NULL COMMENT '租户ID（多水库隔离）',
  ADD INDEX idx_tenant_stag (tenant_id, stag);

-- ===========================================================================
-- 第 2 步：回填三岔现有曲线数据（tenant_id = 18）
--   现网现有曲线均为三岔，全部归属 tenant=18
-- ===========================================================================
UPDATE att_res_stag_cap_disc   SET tenant_id = @sancha_tenant, res_guid = 'RES-SANCHA-EXISTING' WHERE tenant_id IS NULL;
UPDATE att_res_discharge_curve SET tenant_id = @sancha_tenant, res_guid = 'RES-SANCHA-EXISTING' WHERE tenant_id IS NULL;

-- ===========================================================================
-- 第 3 步：model_config 录入桃曲坡配置键全集（tenant = @taoqupo_tenant）
--   skill 的 get_master_stcd / query_config 按这些键 + tenant 动态读取
--   注意：config_key 字段名（不是 key_name）；value 为 text，数值比较需 CAST
-- ===========================================================================

INSERT INTO model_config (config_key, value, tenant_id, deleted) VALUES
  -- 测站 master（skill 动态读取，绝不硬编码）
  ('st_rsvr_r_master',       @stcd_rsvr_master,    @taoqupo_tenant, 0),  -- ⚠️ 待站码
  ('st_pptn_r_master',       @stcd_pptn_master,    @taoqupo_tenant, 0),  -- ⚠️ 待站码
  ('res_guid',               @taoqupo_guid,        @taoqupo_tenant, 0),
  -- 流域/库容
  ('watershed_area_km2',     '1335',               @taoqupo_tenant, 0),  -- km²（沮河830+马栏河505）
  ('total_storage',          '5720',               @taoqupo_tenant, 0),  -- 万m³
  -- 特征水位（m）
  ('flood_limit_main',       '786.80',             @taoqupo_tenant, 0),  -- 主汛限（7-9月）
  ('flood_limit_secondary',  '788.00',             @taoqupo_tenant, 0),  -- 次汛限（6/10月）
  ('normal_pool_level',      '788.50',             @taoqupo_tenant, 0),  -- 正常蓄水位
  ('design_flood_level',     '788.54',             @taoqupo_tenant, 0),  -- 百年一遇
  ('check_flood_level',      '790.50',             @taoqupo_tenant, 0),  -- 千年一遇
  ('dead_water_level',       '755.00',             @taoqupo_tenant, 0),
  -- 泄流约束
  ('max_drainage_capacity',  '2234',               @taoqupo_tenant, 0),  -- 溢洪道最大泄量 m³/s（校核水位时）
  ('safe_drainage_capacity', '500',                @taoqupo_tenant, 0),  -- 下游安全泄量 m³/s（设计）
  -- 预报/水位阈值兜底
  ('max_water_level',        '790.50',             @taoqupo_tenant, 0),
  ('min_water_level',        '755.00',             @taoqupo_tenant, 0)
ON DUPLICATE KEY UPDATE value = VALUES(value);  -- 幂等：重跑覆盖

-- ===========================================================================
-- 第 4 步：att_res_base 录入桃曲坡基础信息
--   ⚠️ 字段集需与现网 DDL 核对（两份 table-schema 说法不一致）
--      forecasting 版无 res_name/total_cap；plan 版有。按现网实际调整下方列
-- ===========================================================================

INSERT INTO att_res_base (fl_low_lim_lev, dead_level, tenant_id, deleted)
VALUES (786.80, 755.00, @taoqupo_tenant, 0);
-- 若现网 att_res_base 含 res_name/res_guid/total_cap 等列，改为：
-- INSERT INTO att_res_base (res_name, res_guid, fl_low_lim_lev, dead_level, total_cap, tenant_id, deleted)
-- VALUES ('桃曲坡水库', @taoqupo_guid, 786.80, 755.00, 5720, @taoqupo_tenant, 0);

-- ===========================================================================
-- 第 5 步：att_res_flse_lim 录入汛限水位（按汛期分段）
--   字段：flse_lim_stag(汛限), flood_season_name, flood_season_start(MMdd), flood_season_end(MMdd)
--   ⚠️ 确认现网该表是否有 tenant_id 列（filters.py 标 filter:False；forecasting table-schema 标有 tenant_id）
--      若有 tenant_id 列，取消下方注释的 tenant_id 部分
--   汛期：6-10月。主汛7-9月(786.80)，次汛6月+10月(788.00)
-- ===========================================================================

INSERT INTO att_res_flse_lim (flse_lim_stag, flood_season_name, flood_season_start, flood_season_end) VALUES
  (786.80, '主汛期', '0701', '0930'),   -- 7-9月
  (788.00, '次汛期', '0601', '0630'),   -- 6月
  (788.00, '次汛期', '1001', '1031');   -- 10月
-- 若有 tenant_id 列：(786.80, '主汛期', '0701', '0930', @taoqupo_tenant), ...

-- ===========================================================================
-- 第 6 步：录入桃曲坡水位-库容曲线（att_res_stag_cap_disc，8 关键节点）
--   来源: reservoirs/taoqupo/curve-data.md（汛期调度运用计划附表）
--   完整 0.1m 间隔查对表见 docs/水位-库容-泄流能力曲线详解.md（可补录）
-- ===========================================================================

INSERT INTO att_res_stag_cap_disc (stag, cap, tenant_id, res_guid) VALUES
  (783.5, 2820, @taoqupo_tenant, @taoqupo_guid),  -- 溢洪道堰顶
  (784.5, 3020, @taoqupo_tenant, @taoqupo_guid),
  (785.5, 3250, @taoqupo_tenant, @taoqupo_guid),
  (786.5, 3485, @taoqupo_tenant, @taoqupo_guid),
  (787.5, 3719, @taoqupo_tenant, @taoqupo_guid),
  (788.5, 3949, @taoqupo_tenant, @taoqupo_guid),  -- 正常蓄水位
  (789.5, 4175, @taoqupo_tenant, @taoqupo_guid),
  (790.5, 4420, @taoqupo_tenant, @taoqupo_guid);  -- 校核洪水位

-- ===========================================================================
-- 第 7 步：录入桃曲坡泄流曲线（att_res_discharge_curve，8 节点，总泄量）
--   来源: curve-data.md（溢洪道泄量 + 低洞97）。低洞恒定97，783.5以下仅低洞
-- ===========================================================================

INSERT INTO att_res_discharge_curve (stag, q, tenant_id, res_guid) VALUES
  (783.5,   97, @taoqupo_tenant, @taoqupo_guid),  -- 堰顶，仅低洞
  (784.5,  241, @taoqupo_tenant, @taoqupo_guid),
  (785.5,  447, @taoqupo_tenant, @taoqupo_guid),
  (786.5,  747, @taoqupo_tenant, @taoqupo_guid),
  (787.5, 1087, @taoqupo_tenant, @taoqupo_guid),
  (788.5, 1507, @taoqupo_tenant, @taoqupo_guid),  -- 正常蓄水位
  (789.5, 1947, @taoqupo_tenant, @taoqupo_guid),
  (790.5, 2331, @taoqupo_tenant, @taoqupo_guid);  -- 校核洪水位

-- ===========================================================================
-- 第 8 步：自检（执行后跑这些查询确认录入正确）
-- ===========================================================================

-- 8.1 曲线表多水库隔离确认：三岔与桃曲坡各自一套曲线
SELECT tenant_id, COUNT(*) AS cap_points FROM att_res_stag_cap_disc   GROUP BY tenant_id;
SELECT tenant_id, COUNT(*) AS q_points   FROM att_res_discharge_curve GROUP BY tenant_id;
-- 预期: tenant=18 三岔 N点, tenant=19 桃曲坡 8点

-- 8.2 桃曲坡 model_config 键完整度（应 15 行）
SELECT COUNT(*) AS taoqupo_config_keys FROM model_config WHERE tenant_id = @taoqupo_tenant AND deleted = 0;

-- 8.3 桃曲坡汛限分段（应 3 行）
SELECT flse_lim_stag, flood_season_name, flood_season_start, flood_season_end
FROM att_res_flse_lim ORDER BY flood_season_start;

-- 8.4 曲线点抽查：788.5m 库容应 3949，790.5m 总泄量应 2331
SELECT stag, cap FROM att_res_stag_cap_disc   WHERE tenant_id=@taoqupo_tenant AND stag IN (788.5, 790.5);
SELECT stag, q   FROM att_res_discharge_curve WHERE tenant_id=@taoqupo_tenant AND stag IN (788.5, 790.5);

-- 8.5 串库检测：桃曲坡曲线不应混入三岔水位（应 0 行）
SELECT COUNT(*) AS cross_contamination FROM att_res_stag_cap_disc
WHERE tenant_id=@taoqupo_tenant AND (stag < 783 OR stag > 791);

-- ===========================================================================
-- 回滚（如需撤销本次录入）
-- ===========================================================================
-- DELETE FROM att_res_stag_cap_disc   WHERE tenant_id = 19;
-- DELETE FROM att_res_discharge_curve WHERE tenant_id = 19;
-- DELETE FROM model_config            WHERE tenant_id = 19;
-- DELETE FROM att_res_base            WHERE tenant_id = 19;
-- （回滚不撤销曲线表 DDL 加列；如需还原列：ALTER TABLE ... DROP COLUMN res_guid, DROP COLUMN tenant_id;）
