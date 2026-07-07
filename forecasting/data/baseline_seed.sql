-- ============================================================================
-- baseline_seed.sql -- 三岔 (tenant 18) 基线显式 seed
-- ============================================================================
-- 幂等执行:所有 INSERT 均为 ON DUPLICATE KEY UPDATE,可重复运行。
-- 来源:
--   att_res_flse_lim 三岔汛限 462.500 (主汛期) -- att_res_base id=8 实测
--     LOCAL 已存在 3 条季节行 (id1 前汛期 461.5 / id2 主汛期 462.5 / id3 后汛期 462.0,
--     res_guid=BFA0027855X, tenant 18)。本 seed 仅确保「主汛期 462.500」存在,绝不覆盖。
--   model_config tenant 18 关键键 -- 来自 application-prod.yaml + 实测配置
--     max_water_level=462.88 (设计洪水位)
--     min_water_level=451   (死水位)
--     st_rsvr_r_master=3    (水库水情 master stcd)
--     st_pptn_r_master=46   (降雨 master stcd)
--     st_river_r_master=136 (河道水情 master stcd)
--     st_gate_r_master=144  (闸门 master stcd)
--     Forecast_Q=Forecast_Q.csv (预报降雨文件名)
-- 幂等保证:LOCAL model_config 已有 59 行,本 seed 用 (config_key, tenant_id) 复合幂等,
--   不影响其它 tenant (如 tenant 17) 的配置。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. att_res_flse_lim: 三岔主汛期汛限水位 462.500 (幂等, 不覆盖既有 3 条季节行)
-- ---------------------------------------------------------------------------
-- 注意:att_res_flse_lim 无 deleted 列,且无 (res_guid, flood_season_start) 唯一索引,
-- 故 INSERT IGNORE / ON DUPLICATE KEY UPDATE 均无法去重。改用 WHERE NOT EXISTS,
-- 仅当主汛期 0701~0831 / res_guid=BFA0027855X 行缺失时才插入。
-- LOCAL 既有:id2 主汛期 462.5 (res_guid=BFA0027855X, tenant 18),故此语句为 no-op,
-- 不会插入也不会覆盖。
INSERT INTO att_res_flse_lim
    (flse_lim_stag, flood_season_name, flood_season_start, flood_season_end, res_guid, tenant_id)
SELECT 462.500, '主汛期', '0701', '0831', 'BFA0027855X', 18
WHERE NOT EXISTS (
    SELECT 1 FROM att_res_flse_lim
    WHERE res_guid = 'BFA0027855X'
      AND flood_season_start = '0701'
      AND flood_season_end = '0831'
      AND tenant_id = 18
);

-- ---------------------------------------------------------------------------
-- 2. model_config: tenant 18 预报关键键 (幂等)
-- ---------------------------------------------------------------------------
-- 注意:model_config 仅有 PRIMARY KEY(id),无 (config_key, tenant_id) 唯一索引,
-- 故 ON DUPLICATE KEY UPDATE 无法去重。改用 INSERT ... SELECT ... WHERE NOT EXISTS,
-- 已存在则跳过;既有值不覆盖(LOCAL model_config 已含 59 行,其中 tenant 18 这些键已存在)。
INSERT INTO model_config (config_key, value, tenant_id, deleted)
SELECT t.k, t.v, 18, 0
FROM (
    SELECT 'max_water_level'  AS k, '462.88'         AS v
    UNION ALL SELECT 'min_water_level',  '451'
    UNION ALL SELECT 'st_rsvr_r_master', '3'
    UNION ALL SELECT 'st_pptn_r_master', '46'
    UNION ALL SELECT 'st_river_r_master','136'
    UNION ALL SELECT 'st_gate_r_master', '144'
    UNION ALL SELECT 'Forecast_Q',       'Forecast_Q.csv'
) AS t
WHERE NOT EXISTS (
    SELECT 1 FROM model_config mc
    WHERE mc.config_key = t.k AND mc.tenant_id = 18 AND mc.deleted = 0
);

-- 验证(可选执行,不写入)
-- SELECT config_key, value, tenant_id FROM model_config
--   WHERE tenant_id=18 AND config_key IN
--   ('max_water_level','min_water_level','st_rsvr_r_master','st_pptn_r_master',
--    'st_river_r_master','st_gate_r_master','Forecast_Q') ORDER BY config_key;
