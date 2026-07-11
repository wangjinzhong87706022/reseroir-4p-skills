-- ============================================================================
-- extreme_storm.sql -- 红色预警级别暴雨场景（>100mm/24h）
-- ============================================================================
-- 用途: 供 v1 Q2/Q36/Q44、v2 Q4/Q36 等极端降雨题。
-- 场景: 未来 24h 累计预报降雨 ~130mm，峰值 ~25mm/h，达到红色预警级别。
-- 关键设计（满足 Task 4 forecast_timeline 非空需求）:
--   包含 NOW-6h~NOW-1h 共 6 小时 forecast-observed 重叠段：
--     - f_rnfl_h（COMMENTS='MOCK'）有过去 6h 已"兑现"的预报行
--     - st_pptn_r（creator='MOCK'）有同 tm 的实测行，与预报存在系统性偏差
--   这样 forecast_timeline 的 MAE/MAPE/bias 可在 eval 中非空。
-- 幂等: 每个 INSERT 前先 DELETE 匹配 MOCK 标记的旧行，可重复运行。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml（绝不写入 103 现网）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. 公共：取 NOW 整点为锚点（MySQL 8 CTE 不可跨语句，故用用户变量）
-- ---------------------------------------------------------------------------
SET @now0  := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. f_rnfl_h: 未来 24h 暴雨预报 + 过去 6h 重叠段（共 30 行）
-- ---------------------------------------------------------------------------
-- 清旧 mock（幂等）
DELETE FROM f_rnfl_h WHERE COMMENTS = 'MOCK';

-- (a) 过去 6h 已兑现段（forecast-observed 重叠，故意偏大 30% 模拟预报偏大）
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_SUB(@now0, INTERVAL 6 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR),  5.2, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 5 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR),  8.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 4 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR), 12.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 3 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR), 18.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 2 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR), 22.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 1 HOUR), DATE_SUB(@now0, INTERVAL 7 HOUR), 15.5, '1', '1', 'MOCK', 0, 1);

-- (b) 未来 24h 预报段（峰值 25mm/h @ NOW+9h，累计 ~130mm）
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_ADD(@now0, INTERVAL  1 HOUR), @now0,  4.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  2 HOUR), @now0,  6.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  3 HOUR), @now0,  9.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  4 HOUR), @now0, 12.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  5 HOUR), @now0, 15.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  6 HOUR), @now0, 18.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  7 HOUR), @now0, 21.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  8 HOUR), @now0, 23.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL  9 HOUR), @now0, 25.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 10 HOUR), @now0, 23.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 11 HOUR), @now0, 19.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 12 HOUR), @now0, 15.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 13 HOUR), @now0, 11.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 14 HOUR), @now0,  7.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 15 HOUR), @now0,  5.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 16 HOUR), @now0,  3.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 17 HOUR), @now0,  2.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 18 HOUR), @now0,  2.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 19 HOUR), @now0,  1.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 20 HOUR), @now0,  1.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 21 HOUR), @now0,  1.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 22 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 23 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_ADD(@now0, INTERVAL 24 HOUR), @now0,  0.5, '1', '1', 'MOCK', 0, 1);

-- ---------------------------------------------------------------------------
-- 2. st_pptn_r: 重叠段实测（与 f_rnfl_h 过去 6h 同 tm 对齐，实测偏低~30%）
--    使 forecast_timeline 的 MAE/bias 非零且方向明确（预报偏大）。
-- ---------------------------------------------------------------------------
DELETE FROM st_pptn_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 6 HOUR) AND tm < @now0;

INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) VALUES
(DATE_SUB(@now0, INTERVAL 6 HOUR),  3.8, 1.0,  3.8, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 5 HOUR),  6.2, 1.0, 10.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 4 HOUR),  9.0, 1.0, 19.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 3 HOUR), 14.0, 1.0, 33.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 2 HOUR), 16.5, 1.0, 49.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 1 HOUR), 11.0, 1.0, 60.5, '46', 18, 0, 'MOCK', 'MOCK');

-- ---------------------------------------------------------------------------
-- 3. st_pptn_re_forecast: 分区预报同步（re_id>=9000 mock 段），未来 24h
-- ---------------------------------------------------------------------------
DELETE FROM st_pptn_re_forecast WHERE re_id >= 9000 AND tm > @now0;

INSERT INTO st_pptn_re_forecast (re_id, tm, drp, intv, dyp, tenant_id, deleted) VALUES
(9200, DATE_ADD(@now0, INTERVAL  1 HOUR),  3.5, 1.00,  3.5, 18, 0),
(9200, DATE_ADD(@now0, INTERVAL  6 HOUR), 17.0, 1.00, 60.0, 18, 0),
(9200, DATE_ADD(@now0, INTERVAL  9 HOUR), 23.0, 1.00, 95.0, 18, 0),
(9200, DATE_ADD(@now0, INTERVAL 12 HOUR), 14.0, 1.00, 130.0, 18, 0),
(9200, DATE_ADD(@now0, INTERVAL 18 HOUR),  2.0, 1.00, 145.0, 18, 0),
(9200, DATE_ADD(@now0, INTERVAL 24 HOUR),  0.5, 1.00, 148.0, 18, 0);

-- 验证（手动执行时取消注释）：
-- SELECT 'f_rnfl_h_mock' AS t, COUNT(*) AS n FROM f_rnfl_h WHERE COMMENTS='MOCK'
-- UNION ALL SELECT 'pptn_overlap', COUNT(*) FROM st_pptn_r WHERE creator='MOCK' AND tm < NOW()
-- UNION ALL SELECT 're_future', COUNT(*) FROM st_pptn_re_forecast WHERE re_id>=9000 AND tm > NOW();
