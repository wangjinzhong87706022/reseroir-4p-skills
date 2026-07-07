-- 批量插入测试数据脚本
-- 目标：增加到 2000+ 条记录
-- 数据库：powerelf_srm_yml

USE powerelf_srm_yml;

-- =====================================================
-- 1. 批量插入2025年数据（每月50条，共6个月）
-- =====================================================

-- 2025年7月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '低水位预警'
       WHEN RAND() < 0.6 THEN '高水位预警'
       WHEN RAND() < 0.8 THEN '蓝色雨量预警'
       ELSE '设备已经离线，请关注' END as ew_name,
  CASE WHEN RAND() < 0.25 THEN '606K2155'
       WHEN RAND() < 0.5 THEN '606K2158'
       WHEN RAND() < 0.75 THEN '606K2152'
       ELSE '606K2153' END as st_code,
  CASE WHEN RAND() < 0.25 THEN '606K215502'
       WHEN RAND() < 0.5 THEN '606K215802'
       WHEN RAND() < 0.75 THEN '606K215201'
       ELSE '606K215301' END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  ROUND(450 + RAND() * 20, 2) as value,
  DATE_ADD('2025-07-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  '0' as type,
  '0' as ew_rules_type,
  230 as ew_rules_id,
  IF(RAND() < 0.7, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-07-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- 2025年8月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '渗流一级预警'
       WHEN RAND() < 0.6 THEN '渗流二级预警'
       WHEN RAND() < 0.8 THEN '溢洪道流量黄色预警'
       ELSE '设备已经离线，请关注' END as ew_name,
  CASE WHEN RAND() < 0.5 THEN '2023510006-SL'
       WHEN RAND() < 0.75 THEN '606K2153'
       ELSE '606K2148' END as st_code,
  CASE WHEN RAND() < 0.5 THEN '2023510006-SL01'
       WHEN RAND() < 0.75 THEN '606K215301'
       ELSE '606K214801' END as eq_code,
  CASE WHEN RAND() < 0.7 THEN 'YZ' ELSE NULL END as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.5 THEN ROUND(15 + RAND() * 25, 2)
       ELSE ROUND(50 + RAND() * 50, 2) END as value,
  DATE_ADD('2025-08-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.7 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.5 THEN '40' ELSE '20' END as ew_rules_type,
  CASE WHEN RAND() < 0.5 THEN 250 ELSE 247 END as ew_rules_id,
  IF(RAND() < 0.6, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-08-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- 2025年9月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '红色雨量预警'
       WHEN RAND() < 0.6 THEN '橙色雨量预警'
       WHEN RAND() < 0.8 THEN '黄色雨量预警'
       ELSE '蓝色雨量预警' END as ew_name,
  CASE WHEN RAND() < 0.5 THEN '606K2152'
       ELSE '606K2150' END as st_code,
  CASE WHEN RAND() < 0.5 THEN '606K215201'
       ELSE '606K215001' END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  ROUND(30 + RAND() * 140, 2) as value,
  DATE_ADD('2025-09-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  '0' as type,
  '2' as ew_rules_type,
  CASE WHEN RAND() < 0.25 THEN 239
       WHEN RAND() < 0.5 THEN 238
       WHEN RAND() < 0.75 THEN 240
       ELSE 237 END as ew_rules_id,
  IF(RAND() < 0.5, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-09-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- 2025年10月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '断面二一级预警'
       WHEN RAND() < 0.6 THEN '断面三渗压二级预警'
       WHEN RAND() < 0.8 THEN '断面三渗压三级预警'
       ELSE '设备已经离线，请关注' END as ew_name,
  NULL as st_code,
  NULL as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.3 THEN '1'
       WHEN RAND() < 0.6 THEN '2'
       ELSE '3' END as level_r,
  NULL as value,
  DATE_ADD('2025-10-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.7 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.7 THEN '5' ELSE '12' END as ew_rules_type,
  0 as ew_rules_id,
  b'0' as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-10-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- 2025年11月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '低水位预警'
       WHEN RAND() < 0.6 THEN '高水位预警'
       WHEN RAND() < 0.8 THEN '渗流一级预警'
       ELSE '渗流二级预警' END as ew_name,
  CASE WHEN RAND() < 0.5 THEN '606K2155'
       WHEN RAND() < 0.75 THEN '606K2158'
       ELSE '2023510006-SL' END as st_code,
  CASE WHEN RAND() < 0.5 THEN '606K215502'
       WHEN RAND() < 0.75 THEN '606K215802'
       ELSE '2023510006-SL01' END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.5 THEN ROUND(450 + RAND() * 20, 2)
       ELSE ROUND(15 + RAND() * 25, 2) END as value,
  DATE_ADD('2025-11-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  '0' as type,
  CASE WHEN RAND() < 0.5 THEN '0' ELSE '40' END as ew_rules_type,
  CASE WHEN RAND() < 0.5 THEN 230 ELSE 250 END as ew_rules_id,
  IF(RAND() < 0.6, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-11-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- 2025年12月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '溢洪道流量黄色预警'
       WHEN RAND() < 0.6 THEN '溢洪道出库流量蓝色预警'
       WHEN RAND() < 0.8 THEN '设备已经离线，请关注'
       ELSE '低水位预警' END as ew_name,
  CASE WHEN RAND() < 0.5 THEN '606K2153'
       WHEN RAND() < 0.75 THEN '606K2148'
       ELSE '606K2158' END as st_code,
  CASE WHEN RAND() < 0.5 THEN '606K215301'
       WHEN RAND() < 0.75 THEN '606K214801'
       ELSE '606K215802' END as eq_code,
  CASE WHEN RAND() < 0.7 THEN 'YZ' ELSE NULL END as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.5 THEN ROUND(50 + RAND() * 50, 2)
       ELSE ROUND(450 + RAND() * 20, 2) END as value,
  DATE_ADD('2025-12-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.7 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.5 THEN '20' ELSE '0' END as ew_rules_type,
  CASE WHEN RAND() < 0.5 THEN 247 ELSE 233 END as ew_rules_id,
  IF(RAND() < 0.5, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2025-12-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 50;

-- =====================================================
-- 2. 批量插入2026年数据（每月100条，共6个月）
-- =====================================================

-- 2026年1月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.2 THEN '低水位预警'
       WHEN RAND() < 0.4 THEN '高水位预警'
       WHEN RAND() < 0.6 THEN '蓝色雨量预警'
       WHEN RAND() < 0.8 THEN '渗流二级预警'
       ELSE '设备已经离线，请关注' END as ew_name,
  CASE WHEN RAND() < 0.2 THEN '606K2155'
       WHEN RAND() < 0.4 THEN '606K2158'
       WHEN RAND() < 0.6 THEN '606K2152'
       WHEN RAND() < 0.8 THEN '2023510006-SL'
       ELSE '606K2148' END as st_code,
  CASE WHEN RAND() < 0.2 THEN '606K215502'
       WHEN RAND() < 0.4 THEN '606K215802'
       WHEN RAND() < 0.6 THEN '606K215201'
       WHEN RAND() < 0.8 THEN '2023510006-SL01'
       ELSE '606K214801' END as eq_code,
  CASE WHEN RAND() < 0.8 THEN 'YZ' ELSE NULL END as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.3 THEN ROUND(450 + RAND() * 20, 2)
       WHEN RAND() < 0.6 THEN ROUND(15 + RAND() * 25, 2)
       ELSE ROUND(30 + RAND() * 50, 2) END as value,
  DATE_ADD('2026-01-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.8 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.2 THEN '0'
       WHEN RAND() < 0.4 THEN '2'
       WHEN RAND() < 0.6 THEN '40'
       WHEN RAND() < 0.8 THEN '12'
       ELSE '20' END as ew_rules_type,
  CASE WHEN RAND() < 0.2 THEN 230
       WHEN RAND() < 0.4 THEN 237
       WHEN RAND() < 0.6 THEN 250
       WHEN RAND() < 0.8 THEN 0
       ELSE 247 END as ew_rules_id,
  IF(RAND() < 0.5, b'0', b'1') as message_confirm,
  CASE WHEN RAND() < 0.7 THEN 18 ELSE 17 END as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-01-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 100;

-- 2026年2月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.2 THEN '低水位预警'
       WHEN RAND() < 0.4 THEN '高水位预警'
       WHEN RAND() < 0.6 THEN '黄色雨量预警'
       WHEN RAND() < 0.8 THEN '渗流一级预警'
       ELSE '溢洪道流量黄色预警' END as ew_name,
  CASE WHEN RAND() < 0.2 THEN '606K2155'
       WHEN RAND() < 0.4 THEN '606K2158'
       WHEN RAND() < 0.6 THEN '606K2152'
       WHEN RAND() < 0.8 THEN '2023510006-SL'
       ELSE '606K2153' END as st_code,
  CASE WHEN RAND() < 0.2 THEN '606K215502'
       WHEN RAND() < 0.4 THEN '606K215802'
       WHEN RAND() < 0.6 THEN '606K215201'
       WHEN RAND() < 0.8 THEN '2023510006-SL01'
       ELSE '606K215301' END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.3 THEN ROUND(450 + RAND() * 20, 2)
       WHEN RAND() < 0.6 THEN ROUND(15 + RAND() * 25, 2)
       ELSE ROUND(50 + RAND() * 50, 2) END as value,
  DATE_ADD('2026-02-01', INTERVAL FLOOR(RAND() * 28) DAY) as gather_time,
  '0' as type,
  CASE WHEN RAND() < 0.25 THEN '0'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '40'
       ELSE '20' END as ew_rules_type,
  CASE WHEN RAND() < 0.25 THEN 230
       WHEN RAND() < 0.5 THEN 240
       WHEN RAND() < 0.75 THEN 250
       ELSE 247 END as ew_rules_id,
  IF(RAND() < 0.5, b'0', b'1') as message_confirm,
  CASE WHEN RAND() < 0.7 THEN 18 ELSE 17 END as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-02-01', INTERVAL FLOOR(RAND() * 28) DAY) as create_time
FROM information_schema.tables
LIMIT 100;

-- 2026年3月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.15 THEN '低水位预警'
       WHEN RAND() < 0.3 THEN '高水位预警'
       WHEN RAND() < 0.45 THEN '红色雨量预警'
       WHEN RAND() < 0.6 THEN '橙色雨量预警'
       WHEN RAND() < 0.75 THEN '渗流一级预警'
       ELSE '设备已经离线，请关注' END as ew_name,
  CASE WHEN RAND() < 0.15 THEN '606K2155'
       WHEN RAND() < 0.3 THEN '606K2158'
       WHEN RAND() < 0.45 THEN '606K2152'
       WHEN RAND() < 0.6 THEN '2023510006-SL'
       WHEN RAND() < 0.75 THEN '606K2148'
       ELSE '606K2153' END as st_code,
  CASE WHEN RAND() < 0.15 THEN '606K215502'
       WHEN RAND() < 0.3 THEN '606K215802'
       WHEN RAND() < 0.45 THEN '606K215201'
       WHEN RAND() < 0.6 THEN '2023510006-SL01'
       WHEN RAND() < 0.75 THEN '606K214801'
       ELSE '606K215301' END as eq_code,
  CASE WHEN RAND() < 0.8 THEN 'YZ' ELSE NULL END as ew_type,
  CASE WHEN RAND() < 0.2 THEN '1'
       WHEN RAND() < 0.4 THEN '2'
       WHEN RAND() < 0.6 THEN '3'
       WHEN RAND() < 0.8 THEN '4'
       ELSE '3' END as level_r,
  CASE WHEN RAND() < 0.2 THEN ROUND(450 + RAND() * 20, 2)
       WHEN RAND() < 0.4 THEN ROUND(100 + RAND() * 70, 2)
       WHEN RAND() < 0.6 THEN ROUND(15 + RAND() * 25, 2)
       ELSE NULL END as value,
  DATE_ADD('2026-03-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.7 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.15 THEN '0'
       WHEN RAND() < 0.3 THEN '2'
       WHEN RAND() < 0.45 THEN '40'
       WHEN RAND() < 0.6 THEN '12'
       WHEN RAND() < 0.75 THEN '20'
       ELSE '5' END as ew_rules_type,
  CASE WHEN RAND() < 0.15 THEN 230
       WHEN RAND() < 0.3 THEN 239
       WHEN RAND() < 0.45 THEN 250
       WHEN RAND() < 0.6 THEN 0
       WHEN RAND() < 0.75 THEN 247
       ELSE 0 END as ew_rules_id,
  IF(RAND() < 0.4, b'0', b'1') as message_confirm,
  CASE WHEN RAND() < 0.7 THEN 18 ELSE 17 END as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-03-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 100;

-- 2026年4月批量数据（大量告警）
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.3 THEN '低水位预警'
       WHEN RAND() < 0.5 THEN '高水位预警'
       WHEN RAND() < 0.7 THEN '蓝色雨量预警'
       WHEN RAND() < 0.85 THEN '设备已经离线，请关注'
       ELSE '渗流二级预警' END as ew_name,
  CASE WHEN RAND() < 0.3 THEN '606K2158'
       WHEN RAND() < 0.5 THEN '606K2155'
       WHEN RAND() < 0.7 THEN '606K2152'
       WHEN RAND() < 0.85 THEN '606K2148'
       ELSE '2023510006-SL' END as st_code,
  CASE WHEN RAND() < 0.3 THEN '606K215802'
       WHEN RAND() < 0.5 THEN '606K215502'
       WHEN RAND() < 0.7 THEN '606K215201'
       WHEN RAND() < 0.85 THEN '606K214801'
       ELSE '2023510006-SL01' END as eq_code,
  CASE WHEN RAND() < 0.85 THEN 'YZ' ELSE NULL END as ew_type,
  CASE WHEN RAND() < 0.3 THEN '4'
       WHEN RAND() < 0.5 THEN '3'
       WHEN RAND() < 0.7 THEN '2'
       ELSE '1' END as level_r,
  CASE WHEN RAND() < 0.4 THEN ROUND(450 + RAND() * 15, 2)
       WHEN RAND() < 0.6 THEN ROUND(30 + RAND() * 50, 2)
       WHEN RAND() < 0.8 THEN ROUND(15 + RAND() * 20, 2)
       ELSE NULL END as value,
  DATE_ADD('2026-04-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.8 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.3 THEN '0'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.7 THEN '40'
       ELSE '12' END as ew_rules_type,
  CASE WHEN RAND() < 0.3 THEN 233
       WHEN RAND() < 0.5 THEN 237
       WHEN RAND() < 0.7 THEN 251
       ELSE 0 END as ew_rules_id,
  IF(RAND() < 0.3, b'0', b'1') as message_confirm,
  CASE WHEN RAND() < 0.8 THEN 18 ELSE 17 END as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-04-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 200;

-- 2026年5月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.2 THEN '低水位预警'
       WHEN RAND() < 0.35 THEN '高水位预警'
       WHEN RAND() < 0.5 THEN '红色雨量预警'
       WHEN RAND() < 0.65 THEN '渗流一级预警'
       WHEN RAND() < 0.8 THEN '设备已经离线，请关注'
       ELSE '断面二一级预警' END as ew_name,
  CASE WHEN RAND() < 0.2 THEN '606K2155'
       WHEN RAND() < 0.35 THEN '606K2158'
       WHEN RAND() < 0.5 THEN '606K2152'
       WHEN RAND() < 0.65 THEN '2023510006-SL'
       WHEN RAND() < 0.8 THEN '2023510006-SY'
       ELSE NULL END as st_code,
  CASE WHEN RAND() < 0.2 THEN '606K215502'
       WHEN RAND() < 0.35 THEN '606K215802'
       WHEN RAND() < 0.5 THEN '606K215201'
       WHEN RAND() < 0.65 THEN '2023510006-SL01'
       WHEN RAND() < 0.8 THEN '2023510006-SY01'
       ELSE NULL END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.25 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.75 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.3 THEN ROUND(450 + RAND() * 20, 2)
       WHEN RAND() < 0.5 THEN ROUND(100 + RAND() * 70, 2)
       WHEN RAND() < 0.7 THEN ROUND(15 + RAND() * 25, 2)
       ELSE NULL END as value,
  DATE_ADD('2026-05-01', INTERVAL FLOOR(RAND() * 30) DAY) as gather_time,
  CASE WHEN RAND() < 0.8 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.2 THEN '0'
       WHEN RAND() < 0.4 THEN '2'
       WHEN RAND() < 0.6 THEN '40'
       WHEN RAND() < 0.8 THEN '12'
       ELSE '5' END as ew_rules_type,
  CASE WHEN RAND() < 0.2 THEN 230
       WHEN RAND() < 0.4 THEN 239
       WHEN RAND() < 0.6 THEN 250
       WHEN RAND() < 0.8 THEN 0
       ELSE 0 END as ew_rules_id,
  IF(RAND() < 0.4, b'0', b'1') as message_confirm,
  CASE WHEN RAND() < 0.7 THEN 18 ELSE 17 END as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-05-01', INTERVAL FLOOR(RAND() * 30) DAY) as create_time
FROM information_schema.tables
LIMIT 150;

-- 2026年6月批量数据
INSERT INTO ew_info_message (ew_name, st_code, eq_code, ew_type, level_r, value, gather_time, type, ew_rules_type, ew_rules_id, message_confirm, tenant_id, deleted, create_time)
SELECT
  CASE WHEN RAND() < 0.15 THEN '低水位预警'
       WHEN RAND() < 0.3 THEN '水位红色预警'
       WHEN RAND() < 0.45 THEN '红色雨量预警'
       WHEN RAND() < 0.6 THEN '渗流一级预警'
       WHEN RAND() < 0.75 THEN '设备已经离线，请关注'
       ELSE '断面二一级预警' END as ew_name,
  CASE WHEN RAND() < 0.15 THEN '606K2158'
       WHEN RAND() < 0.3 THEN '606K2155'
       WHEN RAND() < 0.45 THEN '606K2152'
       WHEN RAND() < 0.6 THEN '2023510006-SL'
       WHEN RAND() < 0.75 THEN '606K2148'
       ELSE NULL END as st_code,
  CASE WHEN RAND() < 0.15 THEN '606K215802'
       WHEN RAND() < 0.3 THEN '606K215502'
       WHEN RAND() < 0.45 THEN '606K215201'
       WHEN RAND() < 0.6 THEN '2023510006-SL01'
       WHEN RAND() < 0.75 THEN '606K214801'
       ELSE NULL END as eq_code,
  'YZ' as ew_type,
  CASE WHEN RAND() < 0.3 THEN '1'
       WHEN RAND() < 0.5 THEN '2'
       WHEN RAND() < 0.7 THEN '3'
       ELSE '4' END as level_r,
  CASE WHEN RAND() < 0.3 THEN ROUND(480 + RAND() * 10, 2)
       WHEN RAND() < 0.5 THEN ROUND(100 + RAND() * 70, 2)
       WHEN RAND() < 0.7 THEN ROUND(30 + RAND() * 10, 2)
       ELSE NULL END as value,
  DATE_ADD('2026-06-01', INTERVAL FLOOR(RAND() * 3) DAY) as gather_time,
  CASE WHEN RAND() < 0.8 THEN '0' ELSE '2' END as type,
  CASE WHEN RAND() < 0.2 THEN '0'
       WHEN RAND() < 0.4 THEN '2'
       WHEN RAND() < 0.6 THEN '40'
       ELSE '5' END as ew_rules_type,
  CASE WHEN RAND() < 0.2 THEN 249
       WHEN RAND() < 0.4 THEN 239
       WHEN RAND() < 0.6 THEN 250
       ELSE 0 END as ew_rules_id,
  IF(RAND() < 0.5, b'0', b'1') as message_confirm,
  18 as tenant_id,
  b'0' as deleted,
  DATE_ADD('2026-06-01', INTERVAL FLOOR(RAND() * 3) DAY) as create_time
FROM information_schema.tables
LIMIT 100;

-- =====================================================
-- 3. 验证插入结果
-- =====================================================

-- 统计总记录数
SELECT '总记录数' as category, COUNT(*) as count FROM ew_info_message WHERE deleted = 0;

-- 按年份统计
SELECT YEAR(gather_time) as year, COUNT(*) as count
FROM ew_info_message
WHERE deleted = 0
GROUP BY YEAR(gather_time)
ORDER BY year;

-- 按月份统计
SELECT DATE_FORMAT(gather_time, '%Y-%m') as month, COUNT(*) as count
FROM ew_info_message
WHERE deleted = 0
GROUP BY DATE_FORMAT(gather_time, '%Y-%m')
ORDER BY month;

-- 按告警类型统计
SELECT ew_type, level_r, COUNT(*) as count
FROM ew_info_message
WHERE deleted = 0
GROUP BY ew_type, level_r
ORDER BY ew_type, level_r;
