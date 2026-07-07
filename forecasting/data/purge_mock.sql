-- 一键清理全 MOCK(各表 marker)。
-- 各表 mock 行的识别 marker(与 generate_forecast_data.py 的 extender/fault 一一对应):
--   st_rsvr_r / st_pptn_r        : creator='MOCK'
--   f_rnfl_h                      : COMMENTS='MOCK'
--   st_mx_preset_cal_r            : taskid LIKE 'MOCK%'
--   model_result_files            : alias='MOCK' OR taskid LIKE 'MOCK%'
--   st_pptn_re_forecast           : re_id>=9000(mock 区段)
--   weather_info                  : icon_day='MOCK'
--   weather_warn                  : docabstract LIKE '%[MOCK]%'
--   dispatch_history              : dispatch_opening LIKE '%[MOCK]%'
--   forecast_accuracy_record      : remark='MOCK'
-- 另清非 MOCK marker 的脏故障行:
--   model_result_files            : taskid LIKE 'JUNK%'(future_junk)+ taskid='MOCK-ORPHAN'(taskid_orphan)
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- === 实测表(creator='MOCK')===
DELETE FROM st_rsvr_r WHERE creator='MOCK';
DELETE FROM st_pptn_r WHERE creator='MOCK';

-- === 和风逐时降雨预报(COMMENTS='MOCK')===
DELETE FROM f_rnfl_h WHERE COMMENTS='MOCK';

-- === 模型预报(taskid LIKE 'MOCK%')===
DELETE FROM st_mx_preset_cal_r WHERE taskid LIKE 'MOCK%';

-- === 模型结果文件(alias='MOCK' OR taskid LIKE 'MOCK%' + 脏故障 JUNK/ORPHAN)===
DELETE FROM model_result_files WHERE alias='MOCK' OR taskid LIKE 'MOCK%';
DELETE FROM model_result_files WHERE taskid LIKE 'JUNK%';
DELETE FROM model_result_files WHERE taskid='MOCK-ORPHAN';

-- === 分区降雨预报(re_id>=9000 mock 区段)===
DELETE FROM st_pptn_re_forecast WHERE re_id>=9000;

-- === 气象信息(icon_day='MOCK')===
DELETE FROM weather_info WHERE icon_day='MOCK';

-- === 气象预警(docabstract LIKE '%[MOCK]%')===
DELETE FROM weather_warn WHERE docabstract LIKE '%[MOCK]%';

-- === 闸门时序(dispatch_opening LIKE '%[MOCK]%')===
DELETE FROM dispatch_history WHERE dispatch_opening LIKE '%[MOCK]%';

-- === 预报精度(remark='MOCK')===
DELETE FROM forecast_accuracy_record WHERE remark='MOCK';
