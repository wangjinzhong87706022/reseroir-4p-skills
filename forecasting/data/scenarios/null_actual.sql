-- ============================================================================
-- null_actual.sql -- 预报有但实测空场景
-- ============================================================================
-- 用途: 供 v1 Q39、v2 Q39 等"预报失败 vs 实测缺失"判定题。
-- 场景: 过去 6 小时 f_rnfl_h 预报有显著降雨（5~15mm/h），
--       但 st_pptn_r 在同 tm 完全无记录（实测缺失），或雨量站故障。
-- 关键: 仅注入 f_rnfl_h 的过去时段行，故意不注入 st_pptn_r 的对应行，
--       形成"预报有/实测空"的不对称，供 skill 判断为"实测缺失"而非"预报失败"。
-- 幂等: DELETE-before-INSERT 按 COMMENTS='MOCK'。
-- 目标库: LOCAL 127.0.0.1 powerelf_srm_yml。
-- ============================================================================

SET @now0 := DATE_FORMAT(NOW(), '%Y-%m-%d %H:00:00');

-- ---------------------------------------------------------------------------
-- 1. 清旧 mock（同时清 f_rnfl_h；st_pptn_r 本场景故意不留同 tm 行）
-- ---------------------------------------------------------------------------
DELETE FROM f_rnfl_h WHERE COMMENTS = 'MOCK';
-- 清掉 extreme_storm 可能留下的过去 6h 重叠实测，确保本场景"实测空"
DELETE FROM st_pptn_r WHERE creator = 'MOCK' AND tenant_id = 18
  AND tm >= DATE_SUB(@now0, INTERVAL 6 HOUR) AND tm < @now0;

-- ---------------------------------------------------------------------------
-- 2. f_rnfl_h: 过去 6h 预报显示明显降雨（但实测空）
-- ---------------------------------------------------------------------------
INSERT INTO f_rnfl_h (ID, YMDH, FYMDH, RN, UNITNAME, TYPE, COMMENTS, deleted, tenant_id) VALUES
(1, DATE_SUB(@now0, INTERVAL 6 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  5.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 5 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR),  7.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 4 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 10.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 3 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 13.5, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 2 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 15.0, '1', '1', 'MOCK', 0, 1),
(1, DATE_SUB(@now0, INTERVAL 1 HOUR), DATE_SUB(@now0, INTERVAL 8 HOUR), 11.0, '1', '1', 'MOCK', 0, 1);

-- ---------------------------------------------------------------------------
-- 3. 故意不插入 st_pptn_r 的同 tm 行 —— 这就是"实测空"
--    （注释提示：若需表达"雨量站故障"，可插一条 NULL drp，但默认完全缺失更典型）
-- ---------------------------------------------------------------------------

-- 验证：
-- SELECT COUNT(*) AS forecast_past_6h FROM f_rnfl_h WHERE COMMENTS='MOCK' AND YMDH < NOW();
-- SELECT COUNT(*) AS observed_past_6h  FROM st_pptn_r WHERE creator='MOCK' AND tm < NOW() AND tm >= NOW()-INTERVAL 6 HOUR;
-- 预期: forecast_past_6h=6, observed_past_6h=0 → 不对称。
