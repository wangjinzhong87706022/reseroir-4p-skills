-- ============================================================
-- 补充测试数据
-- 目标：确保45个测试问题都能得到较好结果
-- 生成日期：2026-06-08
-- ============================================================

-- ============================================================
-- 一、补充水位数据（最近7天逐小时，模拟水位变化）
-- ============================================================
-- 生成 2026-06-01 到 2026-06-08 的逐小时水位数据
-- 模拟：从 458.5m 缓慢上涨到 459.18m（受降雨影响）

INSERT INTO st_rsvr_r (st_id, rz, inq, otq, w, tm, deleted, tenant_id)
SELECT
    1,
    458.5 + (ROW_NUMBER() OVER (ORDER BY h) * 0.01) + (RAND() * 0.05),
    50 + (RAND() * 30),
    20 + (RAND() * 10),
    14000 + (ROW_NUMBER() OVER (ORDER BY h) * 5),
    h,
    0,
    18
FROM (
    SELECT DATE_ADD('2026-06-01 00:00:00', INTERVAL n HOUR) as h
    FROM (
        SELECT a.N + b.N * 10 + c.N * 100 as n
        FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
             (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b,
             (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2) c
    ) numbers
    WHERE n < 168  -- 7天 × 24小时
) hours;

-- ============================================================
-- 二、补充降雨数据（最近7天，模拟间歇性降雨）
-- ============================================================

-- 6月1日：小雨
INSERT INTO st_pptn_r (st_id, p, dr, tm, deleted, tenant_id)
SELECT 1, CASE WHEN RAND() > 0.3 THEN 0 ELSE ROUND(RAND() * 3, 1) END, 1,
       DATE_ADD('2026-06-01 00:00:00', INTERVAL n HOUR), 0, 18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2) b
      WHERE a.N + b.N * 10 < 24) numbers;

-- 6月2日：中雨
INSERT INTO st_pptn_r (st_id, p, dr, tm, deleted, tenant_id)
SELECT 1, ROUND(5 + RAND() * 15, 1), 1,
       DATE_ADD('2026-06-02 00:00:00', INTERVAL n HOUR), 0, 18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2) b
      WHERE a.N + b.N * 10 < 24) numbers;

-- 6月3-4日：晴天
INSERT INTO st_pptn_r (st_id, p, dr, tm, deleted, tenant_id)
SELECT 1, 0, 1,
       DATE_ADD('2026-06-03 00:00:00', INTERVAL n HOUR), 0, 18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2) b
      WHERE a.N + b.N * 10 < 48) numbers;

-- 6月5日：暴雨
INSERT INTO st_pptn_r (st_id, p, dr, tm, deleted, tenant_id)
SELECT 1,
       CASE
           WHEN n BETWEEN 6 AND 12 THEN ROUND(15 + RAND() * 25, 1)  -- 暴雨时段
           WHEN n BETWEEN 13 AND 18 THEN ROUND(5 + RAND() * 15, 1)   -- 减弱
           ELSE ROUND(RAND() * 5, 1)                                  -- 小雨
       END,
       1, DATE_ADD('2026-06-05 00:00:00', INTERVAL n HOUR), 0, 18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2) b
      WHERE a.N + b.N * 10 < 24) numbers;

-- 6月6-8日：间歇小雨
INSERT INTO st_pptn_r (st_id, p, dr, tm, deleted, tenant_id)
SELECT 1, CASE WHEN RAND() > 0.6 THEN 0 ELSE ROUND(RAND() * 5, 1) END, 1,
       DATE_ADD('2026-06-06 00:00:00', INTERVAL n HOUR), 0, 18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b
      WHERE a.N + b.N * 10 < 72) numbers;

-- ============================================================
-- 三、补充降雨预报（未来7天，模拟多种天气）
-- ============================================================

-- 先清除旧的预报数据
DELETE FROM f_rnfl_h WHERE ymdh >= NOW();

-- 6月8-9日：阵雨
INSERT INTO f_rnfl_h (fymdh, ymdh, rn, pop, text, temp, wind_dir, wind_speed, unitname, deleted, tenant_id)
SELECT
    NOW(),
    DATE_ADD(NOW(), INTERVAL n HOUR),
    CASE WHEN RAND() > 0.5 THEN 0 ELSE ROUND(RAND() * 3, 2) END,
    70,
    '阵雨',
    '22',
    '东北风',
    '10',
    '1',
    0,
    18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b
      WHERE a.N + b.N * 10 < 48) numbers;

-- 6月10-11日：暴雨
INSERT INTO f_rnfl_h (fymdh, ymdh, rn, pop, text, temp, wind_dir, wind_speed, unitname, deleted, tenant_id)
SELECT
    NOW(),
    DATE_ADD(NOW(), INTERVAL (48 + n) HOUR),
    CASE
        WHEN n BETWEEN 6 AND 18 THEN ROUND(10 + RAND() * 20, 2)  -- 暴雨时段
        ELSE ROUND(RAND() * 5, 2)
    END,
    90,
    '暴雨',
    '20',
    '南风',
    '15',
    '1',
    0,
    18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b
      WHERE a.N + b.N * 10 < 48) numbers;

-- 6月12-14日：晴天
INSERT INTO f_rnfl_h (fymdh, ymdh, rn, pop, text, temp, wind_dir, wind_speed, unitname, deleted, tenant_id)
SELECT
    NOW(),
    DATE_ADD(NOW(), INTERVAL (96 + n) HOUR),
    0,
    10,
    '晴',
    '28',
    '西南风',
    '8',
    '1',
    0,
    18
FROM (SELECT a.N + b.N * 10 as n
      FROM (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
           (SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b
      WHERE a.N + b.N * 10 < 72) numbers;

-- ============================================================
-- 四、补充气象预警（当前有效的预警）
-- ============================================================

INSERT INTO weather_warn (docid, docabstract, chnlname, model_type, docpubtime, docpuburl, warn_status, update_time, deleted, tenant_id) VALUES
('warn-20260608-001', '简阳市气象台2026年06月08日10时00分发布暴雨黄色预警信号：预计未来24小时内我市将出现50-80mm的降雨，请注意防范。', '预警信息', '2', '2026-06-08 10:00:00', 'https://www.qweather.com', '1', '2026-06-08 10:00:00', 0, 18),
('warn-20260608-002', '四川省气象台2026年06月08日08时00分发布暴雨蓝色预警信号：预计未来12小时内盆地部分地区将出现50mm以上降雨。', '预警信息', '2', '2026-06-08 08:00:00', 'https://www.qweather.com', '1', '2026-06-08 08:00:00', 0, 18),
('warn-20260608-003', '简阳市气象台2026年06月07日18时00分发布大风蓝色预警信号：预计未来24小时我市将出现6级以上大风。', '预警信息', '2', '2026-06-07 18:00:00', 'https://www.qweather.com', '1', '2026-06-07 18:00:00', 0, 18);

-- ============================================================
-- 五、补充历史预案（覆盖更多场景）
-- ============================================================

-- 预案11：汛限水位附近的防洪调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-011', '汛限水位防洪-2026年5月15日08时-24h-461m', '01',
 '汛限水位防洪_2026051508-2026051608.xlsx', '/data/plans/plan-011.xlsx', 0,
 '2026-05-15 08:00:00', '2026-05-16 08:00:00', 2,
 '防洪安全-2026年05月15日08时-01', '461.00', '462.20',
 '{"name":"汛限水位附近防洪调度","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.88,"minWaterLevel":458.0,"maxDrainageCapacity":191,"safeDrainageCapacity":95.1}',
 18, '2026-05-15 08:05:00');

-- 预案12：综合平衡调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-012', '综合平衡-2026年5月10日10时-48h-459m', '01',
 '综合平衡_2026051010-2026051210.xlsx', '/data/plans/plan-012.xlsx', 0,
 '2026-05-10 10:00:00', '2026-05-12 10:00:00', 2,
 '综合调度-2026年05月10日10时-01', '459.00', '458.50',
 '{"name":"综合平衡调度","schedulingTarget":"2","schedulingModel":"2","maxWaterLevel":460.0,"minWaterLevel":457.0,"maxDrainageCapacity":100,"safeDrainageCapacity":95.1}',
 18, '2026-05-10 10:10:00');

-- 预案13：兴利保供调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-013', '兴利保供-2026年4月20日08时-72h-456m', '01',
 '兴利保供_2026042008-2026042308.xlsx', '/data/plans/plan-013.xlsx', 0,
 '2026-04-20 08:00:00', '2026-04-23 08:00:00', 2,
 '水资源利用-2026年04月20日08时-01', '456.00', '453.50',
 '{"name":"兴利保供水","schedulingTarget":"1","schedulingModel":"1","maxWaterLevel":458.0,"minWaterLevel":451.0,"maxDrainageCapacity":50,"safeDrainageCapacity":95.1}',
 18, '2026-04-20 08:15:00');

-- 预案14：下游限泄调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-014', '下游限泄-2026年5月25日14时-24h-460m', '01',
 '下游限泄_2026052514-2026052614.xlsx', '/data/plans/plan-014.xlsx', 0,
 '2026-05-25 14:00:00', '2026-05-26 14:00:00', 2,
 '综合调度-2026年05月25日14时-01', '460.00', '460.50',
 '{"name":"下游限泄调度","schedulingTarget":"2","schedulingModel":"4","maxWaterLevel":462.0,"minWaterLevel":458.0,"maxDrainageCapacity":60,"safeDrainageCapacity":50}',
 18, '2026-05-25 14:08:00');

-- 预案15：短时强降雨快速响应
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-015', '短时强降雨-2026年5月28日16时-6h-461m', '01',
 '短时强降雨_2026052816-2026052822.xlsx', '/data/plans/plan-015.xlsx', 0,
 '2026-05-28 16:00:00', '2026-05-28 22:00:00', 2,
 '防洪安全-2026年05月28日16时-01', '461.00', '460.00',
 '{"name":"短时强降雨快速响应","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.50,"minWaterLevel":459.0,"maxDrainageCapacity":191,"safeDrainageCapacity":95.1}',
 18, '2026-05-28 16:02:00');

-- ============================================================
-- 六、补充调度历史数据（关联新预案）
-- ============================================================

-- 预案11的调度历史（汛限水位附近，较大泄量）
INSERT INTO dispatch_history (tm, dispatch_opening, gate_opening_flow, task_id) VALUES
('2026-05-15 08:00:00', 0.10, 10.5, 'plan-011'),
('2026-05-15 10:00:00', 0.15, 15.8, 'plan-011'),
('2026-05-15 12:00:00', 0.20, 21.0, 'plan-011'),
('2026-05-15 14:00:00', 0.25, 26.5, 'plan-011'),
('2026-05-15 16:00:00', 0.30, 31.0, 'plan-011'),
('2026-05-15 18:00:00', 0.35, 36.0, 'plan-011'),
('2026-05-15 20:00:00', 0.30, 31.0, 'plan-011'),
('2026-05-15 22:00:00', 0.25, 26.0, 'plan-011'),
('2026-05-16 00:00:00', 0.20, 21.0, 'plan-011'),
('2026-05-16 02:00:00', 0.15, 15.5, 'plan-011'),
('2026-05-16 04:00:00', 0.10, 10.0, 'plan-011'),
('2026-05-16 06:00:00', 0.08, 8.0, 'plan-011');

-- 预案13的调度历史（兴利保供，小流量）
INSERT INTO dispatch_history (tm, dispatch_opening, gate_opening_flow, task_id) VALUES
('2026-04-20 08:00:00', 0.02, 2.0, 'plan-013'),
('2026-04-20 12:00:00', 0.03, 3.0, 'plan-013'),
('2026-04-20 16:00:00', 0.02, 2.0, 'plan-013'),
('2026-04-20 20:00:00', 0.02, 2.0, 'plan-013'),
('2026-04-21 00:00:00', 0.01, 1.0, 'plan-013'),
('2026-04-21 04:00:00', 0.01, 1.0, 'plan-013'),
('2026-04-21 08:00:00', 0.02, 2.0, 'plan-013'),
('2026-04-21 12:00:00', 0.03, 3.0, 'plan-013');

-- ============================================================
-- 七、补充历史洪水结果数据
-- ============================================================

-- 洪水17（2023年7月典型暴雨）的结果
INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted, tenant_id) VALUES
(1, 150.5, 17, '2023-07-15 10:00:00', '入库流量', 1, 0, 18),
(1, 280.3, 17, '2023-07-15 14:00:00', '入库流量', 1, 0, 18),
(1, 350.0, 17, '2023-07-15 18:00:00', '入库流量', 1, 0, 18),
(1, 220.0, 17, '2023-07-15 22:00:00', '入库流量', 1, 0, 18),
(2, 80.0, 17, '2023-07-15 10:00:00', '出库流量', 2, 0, 18),
(2, 120.0, 17, '2023-07-15 14:00:00', '出库流量', 2, 0, 18),
(2, 150.0, 17, '2023-07-15 18:00:00', '出库流量', 2, 0, 18),
(2, 100.0, 17, '2023-07-15 22:00:00', '出库流量', 2, 0, 18),
(3, 458.5, 17, '2023-07-15 10:00:00', '水库水位', 3, 0, 18),
(3, 459.8, 17, '2023-07-15 14:00:00', '水库水位', 3, 0, 18),
(3, 460.2, 17, '2023-07-15 18:00:00', '水库水位', 3, 0, 18),
(3, 459.5, 17, '2023-07-15 22:00:00', '水库水位', 3, 0, 18),
(6, 5.0, 17, '2023-07-15 10:00:00', '降雨', 6, 0, 18),
(6, 25.0, 17, '2023-07-15 14:00:00', '降雨', 6, 0, 18),
(6, 35.0, 17, '2023-07-15 18:00:00', '降雨', 6, 0, 18),
(6, 15.0, 17, '2023-07-15 22:00:00', '降雨', 6, 0, 18),
(7, 266.0, 17, '2023-07-15 23:00:00', 'sumRainfall', 3, 0, 18),
(7, 350.0, 17, '2023-07-15 23:00:00', 'inPeakFlow', 3, 0, 18),
(7, 150.0, 17, '2023-07-15 23:00:00', 'outPeakFlow', 3, 0, 18),
(7, 460.2, 17, '2023-07-15 23:00:00', 'maxWaterLevel', 3, 0, 18),
(7, 57.14, 17, '2023-07-15 23:00:00', 'peakShavingFlowRate', 3, 0, 18);

-- 洪水19（2019年短时特大暴雨）的结果
INSERT INTO srm_flood_history_result (type, vals, flood_id, tm, type_name, sort, deleted, tenant_id) VALUES
(1, 80.0, 19, '2019-08-03 16:00:00', '入库流量', 1, 0, 18),
(1, 250.0, 19, '2019-08-03 18:00:00', '入库流量', 1, 0, 18),
(1, 420.0, 19, '2019-08-03 20:00:00', '入库流量', 1, 0, 18),
(1, 180.0, 19, '2019-08-03 22:00:00', '入库流量', 1, 0, 18),
(2, 60.0, 19, '2019-08-03 16:00:00', '出库流量', 2, 0, 18),
(2, 90.0, 19, '2019-08-03 18:00:00', '出库流量', 2, 0, 18),
(2, 95.0, 19, '2019-08-03 20:00:00', '出库流量', 2, 0, 18),
(2, 85.0, 19, '2019-08-03 22:00:00', '出库流量', 2, 0, 18),
(3, 459.8, 19, '2019-08-03 16:00:00', '水库水位', 3, 0, 18),
(3, 461.5, 19, '2019-08-03 18:00:00', '水库水位', 3, 0, 18),
(3, 462.3, 19, '2019-08-03 20:00:00', '水库水位', 3, 0, 18),
(3, 461.0, 19, '2019-08-03 22:00:00', '水库水位', 3, 0, 18),
(7, 180.0, 19, '2019-08-03 23:00:00', 'sumRainfall', 3, 0, 18),
(7, 420.0, 19, '2019-08-03 23:00:00', 'inPeakFlow', 3, 0, 18),
(7, 95.0, 19, '2019-08-03 23:00:00', 'outPeakFlow', 3, 0, 18),
(7, 462.3, 19, '2019-08-03 23:00:00', 'maxWaterLevel', 3, 0, 18),
(7, 77.38, 19, '2019-08-03 23:00:00', 'peakShavingFlowRate', 3, 0, 18);
