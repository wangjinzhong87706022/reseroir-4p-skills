-- ============================================================================
-- drought.sql -- 长期干旱场景（极低水位 + 近乎无雨）
-- ============================================================================
-- 用途: 供 v1 Q8/Q37、v2 Q8/Q37 等干旱题。
-- 场景: 过去 7 天累计降雨 ~0mm，水位已降至 451.5m（逼近死水位 451m）。
-- 幂等: DELETE-before-INSERT 按 Task 2 marker（creator='MOCK'）。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml。
-- ============================================================================

SET @now0 := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. st_pptn_r: 近 7 天几乎无降雨（每天仅 0~0.3mm，dyp 合计 ~2mm）
-- ---------------------------------------------------------------------------
DELETE FROM st_pptn_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 168 HOUR) AND tm < DATE_SUB(@now0, INTERVAL 6 HOUR);

-- 每 6h 一条微量雨，共 28 条（7d × 4）
INSERT INTO st_pptn_r (tm, p, dr, dyp, stcd, tenant_id, deleted, creator, eq_code) VALUES
(DATE_SUB(@now0, INTERVAL 162 HOUR), 0.1, 6.0, 0.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 156 HOUR), 0.0, 6.0, 0.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 150 HOUR), 0.2, 6.0, 0.3, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 144 HOUR), 0.1, 6.0, 0.4, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 138 HOUR), 0.0, 6.0, 0.4, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 132 HOUR), 0.3, 6.0, 0.7, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 126 HOUR), 0.1, 6.0, 0.8, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 120 HOUR), 0.0, 6.0, 0.8, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 114 HOUR), 0.2, 6.0, 1.0, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 108 HOUR), 0.1, 6.0, 1.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL 102 HOUR), 0.0, 6.0, 1.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  96 HOUR), 0.3, 6.0, 1.4, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  90 HOUR), 0.0, 6.0, 1.4, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  84 HOUR), 0.1, 6.0, 1.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  78 HOUR), 0.0, 6.0, 1.5, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  72 HOUR), 0.2, 6.0, 1.7, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  66 HOUR), 0.1, 6.0, 1.8, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  60 HOUR), 0.0, 6.0, 1.8, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  54 HOUR), 0.1, 6.0, 1.9, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  48 HOUR), 0.0, 6.0, 1.9, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  42 HOUR), 0.2, 6.0, 2.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  36 HOUR), 0.0, 6.0, 2.1, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  30 HOUR), 0.1, 6.0, 2.2, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  24 HOUR), 0.0, 6.0, 2.2, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  18 HOUR), 0.0, 6.0, 2.2, '46', 18, 0, 'MOCK', 'MOCK'),
(DATE_SUB(@now0, INTERVAL  12 HOUR), 0.0, 6.0, 2.2, '46', 18, 0, 'MOCK', 'MOCK');

-- ---------------------------------------------------------------------------
-- 2. st_rsvr_r: 水位缓慢下降至 451.5m（逼近死水位 451m），近 48h 每小时一条
-- ---------------------------------------------------------------------------
DELETE FROM st_rsvr_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 48 HOUR) AND tm < DATE_SUB(@now0, INTERVAL 6 HOUR);

-- 水位从 452.3 缓降至 451.5，入库流量极低（~5 m³/s），出库维持供水（~8 m³/s）
INSERT INTO st_rsvr_r (tm, rz, inq, otq, w, stcd, tenant_id, deleted, creator, eq_code)
SELECT t.tm,
       ROUND(452.3 - 0.8 * (TIMESTAMPDIFF(HOUR, DATE_SUB(@now0, INTERVAL 48 HOUR), t.tm) / 48.0), 3),
       5.0, 8.0,
       ROUND(3900 + 200 * (452.3 - 0.8 * (TIMESTAMPDIFF(HOUR, DATE_SUB(@now0, INTERVAL 48 HOUR), t.tm) / 48.0) - 451.0), 1),
       '3', 18, 0, 'MOCK', 'MOCK'
FROM (
  SELECT DATE_SUB(@now0, INTERVAL seq HOUR) AS tm
  FROM (
    SELECT a.N + b.N*10 AS seq
    FROM (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
          UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a
    CROSS JOIN (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) b
  ) nums
  WHERE seq BETWEEN 7 AND 48
) t;

-- 验证：
-- SELECT MIN(rz), MAX(rz), COUNT(*) FROM st_rsvr_r WHERE creator='MOCK' AND tm < NOW();
-- SELECT SUM(p), COUNT(*) FROM st_pptn_r WHERE creator='MOCK' AND tm >= NOW()-INTERVAL 168 HOUR;
