-- ============================================================================
-- over_flood_limit.sql -- 水位逼近/超汛限场景（rz ≥ 462.5）
-- ============================================================================
-- 用途: 供 v1 Q7/Q40/Q45、v2 Q7/Q40 等超汛限紧急调度题。
-- 场景: 近 12 小时水位快速上涨至 462.8m，超汛限 462.5m 且逼近校核 462.88m。
-- 关键设计（满足 Task 4 forecast_timeline 非空需求）:
--   包含 NOW-6h~NOW-1h 共 6 小时 forecast-observed 重叠段：
--     - f_rnfl_h（COMMENTS='MOCK'）预报未来 + 过去 6h
--     - st_pptn_r（creator='MOCK'）实测同 tm，略高于预报（模拟预报偏小）
--   使 forecast_timeline bias 非空。
-- 幂等: DELETE-before-INSERT 按 creator='MOCK' / COMMENTS='MOCK'。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml。
-- ============================================================================

SET @now0 := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. st_rsvr_r: 水位近 12h 上涨至 462.8m（超汛限 462.5）
-- ---------------------------------------------------------------------------
DELETE FROM st_rsvr_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 12 HOUR) AND tm < @now0;

-- 水位从 461.5 涨到 462.8（每 2h 一条，6 条），入库激增，出库滞后
INSERT INTO st_rsvr_r (tm, rz, inq, otq, w, stcd, tenant_id, deleted, creator, eq_code) VALUES
(DATE_SUB(@now0, INTERVAL 11 HOUR), 461.500, 180.0,  90.0, 18500.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  9 HOUR), 461.800, 240.0, 110.0, 18900.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  7 HOUR), 462.100, 310.0, 130.0, 19300.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  6 HOUR), 462.300, 350.0, 140.0, 19550.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  5 HOUR), 462.500, 390.0, 150.0, 19800.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  4 HOUR), 462.650, 420.0, 160.0, 20000.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  3 HOUR), 462.750, 440.0, 170.0, 20150.0, '3', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  2 HOUR), 462.800, 450.0, 180.0, 20250.0, '3', 18, 0, 'MOCK', 'MOCK');

-- ---------------------------------------------------------------------------
-- 2. st_pptn_r: 过去 6h 实测（与 f_rnfl_h 重叠，实测偏高，预报偏小）
-- ---------------------------------------------------------------------------
DELETE FROM st_pptn_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 6 HOUR) AND tm < @now0;

INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) VALUES
(DATE_SUB(@now0, INTERVAL 6 HOUR), 10.5, 1.0, 10.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 5 HOUR), 14.0, 1.0, 24.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 4 HOUR), 18.5, 1.0, 43.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 3 HOUR), 22.0, 1.0, 65.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 2 HOUR), 25.5, 1.0, 90.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 1 HOUR), 20.0, 1.0, 110.5, '46', 18, 0, 'MOCK', 'MOCK');

-- ---------------------------------------------------------------------------
-- 3. f_rnfl_h: 过去 6h 预报（偏小，与实测对照）+ 未来 12h 预报（持续降雨）
-- ---------------------------------------------------------------------------
DELETE FROM f_rnfl_h WHERE COMMENTS = 'MOCK';

-- (a) 过去 6h 预报（偏小，模拟预报低估）
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_SUB(@now0, INTERVAL 6 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  8.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 5 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 11.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 4 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 15.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 3 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 18.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 2 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 21.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 1 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 16.5, '1', '1', 'MOCK', 0, 1);

-- (b) 未来 12h 预报（退水但仍中雨，可能继续推高水位）
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_ADD(@now0, INTERVAL  1 HOUR), @now0, 14.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  2 HOUR), @now0, 11.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  3 HOUR), @now0,  8.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  4 HOUR), @now0,  6.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  5 HOUR), @now0,  4.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  6 HOUR), @now0,  2.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  7 HOUR), @now0,  1.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  8 HOUR), @now0,  1.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  9 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 10 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 11 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 12 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1);

-- 验证：
-- SELECT MAX(rz) FROM st_rsvr_r WHERE creator='MOCK';  -- 预期 462.800（超汛限）
-- SELECT COUNT(*) FROM st_pptn_r WHERE creator='MOCK' AND tm < NOW();  -- 重叠实测 6 行
-- SELECT COUNT(*) FROM f_rnfl_h WHERE COMMENTS='MOCK' AND YMDH < NOW();  -- 重叠预报 6 行
