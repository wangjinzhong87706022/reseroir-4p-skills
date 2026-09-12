-- ============================================================================
-- stale_forecast.sql -- 陈旧预报场景（FYMDH 距今 >6h）
-- ============================================================================
-- 用途: 供 v1 Q5/Q41、v2 Q5/Q41 等"陈旧预报"判定题。
-- 场景: f_rnfl_h 最新批次的发布时间 FYMDH 距今 >6h（此处设为 NOW-8h），
--       触发 forecast_advisor 的"陈旧预报"提示，建议等待新批次或降权。
-- 关键: FYMDH 设为 NOW-8h（>6h 阈值），YMDH 覆盖 NOW+1~24h（仍是未来预报）。
-- 幂等: DELETE-before-INSERT 按 COMMENTS='MOCK-STALE'。
-- 2026-09-11: tenant_id 1→18 修正——原值写租户 1，租户 18 的评测题查不到（潜伏 bug，
-- 7 月建库时遗留）；须与 hide_fresh_forecast（eval/data/scenarios.yaml）成对使用，
-- 否则 cron 新鲜批次盖过本场景。
-- 2026-09-11: 标记 'MOCK'→'MOCK-STALE'——cron 的 --forecast 批次本身也写
-- COMMENTS='MOCK'（generate_sancha_data.py:146），按 'MOCK' 清场会误删在用预报批，
-- teardown 后到下个 cron tick 之间租户 18 无预报数据。
-- 2026-09-12: ID 1→20001——复合主键 (ID,YMDH,UNITNAME,TYPE)；ID=1 的遗留行占着
-- 未来时段的 YMDH 槽位（软删/suppress 不释放 PK），ID=1 注入必撞 Duplicate entry。
-- 20001 与存量（1/2/10001-10047）无交集。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml。
-- ============================================================================

SET @now0 := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. 清旧 mock
-- ---------------------------------------------------------------------------
DELETE FROM f_rnfl_h WHERE COMMENTS = 'MOCK-STALE';

-- ---------------------------------------------------------------------------
-- 2. 注入"陈旧"批次：FYMDH = NOW-8h（>6h 阈值），YMDH 覆盖 NOW+1~24h
--    预报内容为中等降雨（累计 ~70mm），不影响极端判定，聚焦"陈旧"维度。
-- ---------------------------------------------------------------------------
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(20001, DATE_ADD(@now0, INTERVAL  1 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  1.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  2 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  2.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  3 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  3.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  4 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  4.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  5 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  5.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  6 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  6.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  7 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  6.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  8 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  6.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL  9 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  5.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 10 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  5.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 11 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  4.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 12 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  4.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 13 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  3.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 14 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  3.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 15 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  2.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 16 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  2.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 17 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  1.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 18 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  1.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 19 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  1.0, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 20 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  0.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 21 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  0.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 22 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  0.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 23 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  0.5, '1', '1', 'MOCK-STALE', 0, 18),
(20001, DATE_ADD(@now0, INTERVAL 24 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  0.5, '1', '1', 'MOCK-STALE', 0, 18);

-- 验证：
-- SELECT MAX(FYMDH) AS latest_issue, TIMESTAMPDIFF(HOUR, MAX(FYMDH), NOW()) AS age_h
--   FROM f_rnfl_h WHERE COMMENTS='MOCK-STALE';
-- 预期: age_h = 8（>6h 阈值）→ 触发"陈旧预报"提示。
