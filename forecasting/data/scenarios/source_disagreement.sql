-- ============================================================================
-- source_disagreement.sql -- 四源降雨预报分歧场景（>20mm）
-- ============================================================================
-- 用途: 供 v1 Q11/Q12/Q38、v2 Q11/Q14/Q38 等多源融合题。
-- 场景: 和风 f_rnfl_h 预报未来 24h ~120mm（偏激进），分区预报
--       st_pptn_re_forecast 仅 ~60mm（偏保守），分歧 >60mm，远超 20mm 阈值。
-- 关键: 仅注入 f_rnfl_h 与 st_pptn_re_forecast 两源，使其在 NOW+1~24h 每小时
--       的累计差 >20mm，触发 multi_source_overview 的"分歧"标注。
-- 幂等: DELETE-before-INSERT 按 Task 2 marker（COMMENTS='MOCK' / re_id>=9000）。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml。
-- ============================================================================

SET @now0 := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. f_rnfl_h: 和风激进预报（未来 24h 累计 ~120mm，峰值 18mm/h @ NOW+12h）
-- ---------------------------------------------------------------------------
DELETE FROM f_rnfl_h WHERE COMMENTS = 'MOCK';

INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_ADD(@now0, INTERVAL  1 HOUR), @now0,  2.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  2 HOUR), @now0,  3.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  3 HOUR), @now0,  5.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  4 HOUR), @now0,  7.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  5 HOUR), @now0,  9.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  6 HOUR), @now0, 12.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  7 HOUR), @now0, 14.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  8 HOUR), @now0, 16.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  9 HOUR), @now0, 17.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 10 HOUR), @now0, 18.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 11 HOUR), @now0, 17.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 12 HOUR), @now0, 15.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 13 HOUR), @now0, 12.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 14 HOUR), @now0,  9.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 15 HOUR), @now0,  6.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 16 HOUR), @now0,  4.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 17 HOUR), @now0,  3.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 18 HOUR), @now0,  2.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 19 HOUR), @now0,  1.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 20 HOUR), @now0,  1.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 21 HOUR), @now0,  1.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 22 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 23 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 24 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1);

-- ---------------------------------------------------------------------------
-- 2. st_pptn_re_forecast: 分区保守预报（未来 24h 累计 ~60mm，约为和风一半）
--    re_id 9300（mock 区段）确保与和风每小时差 >2mm，累计差 >60mm。
-- ---------------------------------------------------------------------------
DELETE FROM st_pptn_re_forecast WHERE re_id >= 9000 AND tm > @now0;

INSERT INTO st_pptn_re_forecast (re_id, tm, drp, intv, dyp, tenant_id, deleted) VALUES
(9300, DATE_ADD(@now0, INTERVAL  1 HOUR),  1.0, 1.00,  1.0, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  2 HOUR),  1.8, 1.00,  2.8, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  3 HOUR),  2.5, 1.00,  5.3, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  4 HOUR),  3.5, 1.00,  8.8, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  5 HOUR),  4.8, 1.00, 13.6, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  6 HOUR),  6.0, 1.00, 19.6, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  7 HOUR),  7.0, 1.00, 26.6, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  8 HOUR),  8.0, 1.00, 34.6, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL  9 HOUR),  8.8, 1.00, 43.4, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 10 HOUR),  9.0, 1.00, 52.4, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 11 HOUR),  8.5, 1.00, 60.9, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 12 HOUR),  7.5, 1.00, 68.4, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 13 HOUR),  6.0, 1.00, 74.4, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 14 HOUR),  4.5, 1.00, 78.9, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 15 HOUR),  3.3, 1.00, 82.2, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 16 HOUR),  2.3, 1.00, 84.5, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 17 HOUR),  1.5, 1.00, 86.0, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 18 HOUR),  1.0, 1.00, 87.0, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 19 HOUR),  0.8, 1.00, 87.8, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 20 HOUR),  0.5, 1.00, 88.3, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 21 HOUR),  0.5, 1.00, 88.8, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 22 HOUR),  0.3, 1.00, 89.1, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 23 HOUR),  0.3, 1.00, 89.4, 18, 0),
(9300, DATE_ADD(@now0, INTERVAL 24 HOUR),  0.2, 1.00, 89.6, 18, 0);

-- 验证：
-- SELECT 'hefeng_24h', SUM(RN) FROM f_rnfl_h WHERE COMMENTS='MOCK' AND YMDH > NOW();
-- SELECT 'zonal_24h', SUM(drp) FROM st_pptn_re_forecast WHERE re_id>=9000 AND tm > NOW();
-- 预期: hefeng ~188mm(window) vs zonal ~89mm，分歧 >90mm。
