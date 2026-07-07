-- ============================================================
-- 高质量历史预案数据
-- 水库：三岔水库（成都市东部新区）
-- 生成日期：2026-06-05
-- 说明：覆盖防洪/兴利/综合三种调度目标，5种调度模式，5种时长
-- ============================================================

-- 预案1：暴雨防洪 — 高水位紧急预泄
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-001', '防洪紧急预泄-2026年6月5日08时-24h-460m', '01',
 '防洪紧急预泄_2026060508-2026060608.xlsx', '/data/plans/plan-001.xlsx', 0,
 '2026-06-05 08:00:00', '2026-06-06 08:00:00', 2,
 '防洪安全-2026年06月05日08时-01', '460.00', '461.50',
 '{"name":"暴雨防洪紧急预泄","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.88,"minWaterLevel":458.0,"maxDrainageCapacity":192,"safeDrainageCapacity":95.1}',
 18, '2026-06-05 08:05:00');

-- 预案2：中雨防洪 — 常规预泄
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-002', '防洪常规预泄-2026年6月4日14时-24h-459m', '01',
 '防洪常规预泄_2026060414-2026060514.xlsx', '/data/plans/plan-002.xlsx', 0,
 '2026-06-04 14:00:00', '2026-06-05 14:00:00', 2,
 '防洪安全-2026年06月04日14时-01', '459.00', '460.00',
 '{"name":"中雨防洪常规预泄","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.50,"minWaterLevel":457.0,"maxDrainageCapacity":192,"safeDrainageCapacity":95.1}',
 18, '2026-06-04 14:10:00');

-- 预案3：综合平衡 — 中水位运行
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-003', '综合平衡-2026年6月3日08时-48h-459m', '01',
 '综合平衡_2026060308-2026060508.xlsx', '/data/plans/plan-003.xlsx', 0,
 '2026-06-03 08:00:00', '2026-06-05 08:00:00', 2,
 '综合调度-2026年06月03日08时-01', '459.00', '458.50',
 '{"name":"综合平衡调度","schedulingTarget":"2","schedulingModel":"2","maxWaterLevel":460.0,"minWaterLevel":457.0,"maxDrainageCapacity":100,"safeDrainageCapacity":95.1}',
 18, '2026-06-03 08:15:00');

-- 预案4：兴利保供 — 低水位蓄水
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-004', '兴利保供-2026年6月1日08时-72h-455m', '01',
 '兴利保供_2026060108-2026060408.xlsx', '/data/plans/plan-004.xlsx', 0,
 '2026-06-01 08:00:00', '2026-06-04 08:00:00', 2,
 '水资源利用-2026年06月01日08时-01', '455.00', '453.00',
 '{"name":"兴利保供水","schedulingTarget":"1","schedulingModel":"1","maxWaterLevel":458.0,"minWaterLevel":451.0,"maxDrainageCapacity":50,"safeDrainageCapacity":95.1}',
 18, '2026-06-01 08:20:00');

-- 预案5：大洪水应对 — 极限调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-005', '大洪水极限调度-2026年6月6日06时-24h-459m', '01',
 '大洪水极限调度_2026060606-2026060706.xlsx', '/data/plans/plan-005.xlsx', 0,
 '2026-06-06 06:00:00', '2026-06-07 06:00:00', 2,
 '防洪安全-2026年06月06日06时-01', '459.00', '462.00',
 '{"name":"大洪水极限调度","schedulingTarget":"0","schedulingModel":"3","maxWaterLevel":462.88,"minWaterLevel":456.0,"maxDrainageCapacity":192,"safeDrainageCapacity":95.1}',
 18, '2026-06-06 06:03:00');

-- 预案6：短时强降雨 — 6小时快速响应
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-006', '短时强降雨-2026年6月5日16时-6h-460m', '01',
 '短时强降雨_2026060516-2026060522.xlsx', '/data/plans/plan-006.xlsx', 0,
 '2026-06-05 16:00:00', '2026-06-05 22:00:00', 2,
 '防洪安全-2026年06月05日16时-01', '460.00', '461.00',
 '{"name":"短时强降雨快速响应","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.50,"minWaterLevel":459.0,"maxDrainageCapacity":192,"safeDrainageCapacity":95.1}',
 18, '2026-06-05 16:02:00');

-- 预案7：下游防洪 — 限制下泄流量
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-007', '下游防洪限泄-2026年6月4日10时-24h-461m', '01',
 '下游防洪限泄_2026060410-2026060510.xlsx', '/data/plans/plan-007.xlsx', 0,
 '2026-06-04 10:00:00', '2026-06-05 10:00:00', 2,
 '综合调度-2026年06月04日10时-01', '461.00', '460.50',
 '{"name":"下游防洪限制下泄","schedulingTarget":"2","schedulingModel":"4","maxWaterLevel":462.0,"minWaterLevel":458.0,"maxDrainageCapacity":60,"safeDrainageCapacity":50}',
 18, '2026-06-04 10:08:00');

-- 预案8：汛末蓄水 — 从低水位回蓄
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-008', '汛末蓄水-2026年9月15日08时-72h-460m', '01',
 '汛末蓄水_2026091508-2026091808.xlsx', '/data/plans/plan-008.xlsx', 0,
 '2026-09-15 08:00:00', '2026-09-18 08:00:00', 2,
 '水资源利用-2026年09月15日08时-01', '460.00', '454.00',
 '{"name":"汛末回蓄","schedulingTarget":"1","schedulingModel":"1","maxWaterLevel":462.5,"minWaterLevel":451.0,"maxDrainageCapacity":50,"safeDrainageCapacity":95.1}',
 18, '2026-09-15 08:12:00');

-- 预案9：闸门故障 — 降低下泄能力
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-009', '闸门故障降级-2026年6月5日12时-24h-460m', '01',
 '闸门故障降级_2026060512-2026060612.xlsx', '/data/plans/plan-009.xlsx', 0,
 '2026-06-05 12:00:00', '2026-06-06 12:00:00', 2,
 '防洪安全-2026年06月05日12时-02', '460.00', '461.00',
 '{"name":"闸门故障降级调度","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.50,"minWaterLevel":458.0,"maxDrainageCapacity":80,"safeDrainageCapacity":95.1}',
 18, '2026-06-05 12:05:00');

-- 预案10：连续降雨 — 48小时持续调度
INSERT INTO model_result_files
(taskid, scheme_id, version, file_name, file_path, file_size, start_time, end_time, type, alias, target_water_level, adjusted_water_level, extend, tenant_id, create_time)
VALUES
('plan-010', '连续降雨48h-2026年6月5日08时-48h-458m', '01',
 '连续降雨48h_2026060508-2026060708.xlsx', '/data/plans/plan-010.xlsx', 0,
 '2026-06-05 08:00:00', '2026-06-07 08:00:00', 2,
 '防洪安全-2026年06月05日08时-02', '458.00', '460.50',
 '{"name":"连续降雨持续调度","schedulingTarget":"0","schedulingModel":"0","maxWaterLevel":462.50,"minWaterLevel":456.0,"maxDrainageCapacity":192,"safeDrainageCapacity":95.1}',
 18, '2026-06-05 08:10:00');
