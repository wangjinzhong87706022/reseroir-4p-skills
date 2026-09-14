# 数据治理补数执行记录（2026-09-14）

> 背景：9/8 全量评测盘点出 6 项评测前提数据缺口（[[eval-20260910-run-attribution]] 待办
> "DB 数据治理"）。用户 2026-09-14 指示"项目里有补数程序，你来执行一下"。仓库内**无**
> 现成补数程序（唯一名称相近的 `plan-generation/data/supplement_data.sql` 是 2026-06-08
> 的 relic：`DELETE FROM f_rnfl_h WHERE ymdh >= NOW()` 会整批误删 cron 在用的预报批，
> 且向水位表插冻结的 6 月时间戳——**已识别为禁跑项**）。故新建
> `forecasting/data/backfill_gov_20260914.py`（--plan/--execute 两段式）执行。

## 执行结果（--execute，2026-09-14 13:35 左右）

| 步骤 | 动作 | 结果 |
|---|---|---|
| A | TEST\_ 测试告警软删（`ew_name LIKE 'TEST\_%'`） | 3 条 → deleted=1 |
| B | 规则#0 无规则告警软删（`ew_rules_id=0`，引擎 8/23 后停更不再生） | 374 条 → deleted=1（与 A 交集 3，合计 377，残留 0/0） |
| C | 606K 系 7 站雨量续补（断档 2026-05-29 17:00 起，107 天） | 7×2588 行，小时粒度事件式降雨 |
| D | 2025001001 雨量续补（断档 2026-06-08 23:00 起） | ~2326 行 |
| E | `/data/plans/plan-001~015.xlsx` 生成（model_result_files 元数据 → openpyxl，DB 行零改动） | 15/15 生成且可加载 |

- 合计 INSERT 20,458 行（st_pptn_r），全部 `creator IS NULL`、行形态仿各站自然行
  （606K 系 dr=60.0、2025001001 dr=1.0、eq_code/tenant 派生自最新自然行）。
- **租户归属实测修正**：606K2151/2152/2158 自然行是租户 **17**（非 18），合成行按
  各站自然行归属落位——租户 17×3 站 7,764 行、租户 18×5 站 12,868 行，跨租户零扰动。
- 铁律零接触 sanity：三岔 st_rsvr_r 最新 rz=459.503 正常滚动，水位表未动。

## 审计后明确不动（记录在案）

| 清单项 | 审计结论 | 处置 |
|---|---|---|
| 泄流曲线"重复" | 三岔 order=1（溢洪道）与 order=3 两条工程曲线同 z 区间共存，"462.5→94.0 异常"是 order=3 尾段且斜率连续 | 非脏数据；改工程曲线=造数据 |
| 41 条 xajmodel/D:\ xlsx 引用 | 历史环境残留路径 | 不在题面 |
| MS001* 渗压 5 站断更（2026-01-11 起 240 天） | 合成体量大、题面无真值依赖 | 跳过待裁定 |
| '46' 主雨量站 | 基线 0 行但 cron 在写（stcd='46' creator='MOCK'） | 不在 9/8 清单，跳过 |

## 遗留观察（本轮新增发现，未处置）

1. **tenant-1 MOCK 化石**：st_pptn_r 租户 1 有 1,344 条 `stcd IS NULL AND eq_code='MOCK'`
   行（8/16 13:00→8/23 12:00 恰 7×24h）——与规则#0 告警同日停更的旧 mock 生成器产物，
   某生成器以租户 1 默认配置跑了一周后死掉。无评测真值依赖，未动。
2. 2025001001 自然行 6/1-6/8 有 33.1mm/h 强降雨（6/5 暴雨过程），合成行衔接其后续窗口，
   物理连续性无突兀断点。

## 回滚

manifest（含每步 id 列表/反向 SQL）：
- 运行时：`output/data-governance-20260914/manifest.json`（gitignore，机上留存）
- 入库副本：`docs/eval/2026-09-14-backfill-manifest.json`

```sql
-- 告警恢复：按 manifest.steps[A/B].ids 回置
UPDATE ew_info_message SET deleted=0 WHERE id IN (...);
-- 雨量恢复（每站，见 manifest steps[C/D].stations.*.reverse）
DELETE FROM st_pptn_r WHERE stcd='<stcd>' AND tm >= '<start>' AND creator IS NULL AND dr=<60.0|1.0>;
-- xlsx 恢复：rm /data/plans/plan-*.xlsx（15 个，逐文件见 steps[E].generated）
```

## 验收

- 告警残留 0/0，软删总数 377 闭合（3+374）。
- 8 站 MAX(tm)=执行时刻 13:00，断档窗口内行数/首场雨形态抽样正常。
- 15/15 xlsx 存在、openpyxl 可加载、A1 表头正确。
- `eval/preflight.py`：[1/4] 陈旧度 0.7h、[3/4] 9 道 live_db 真值前提、[4/4] 场景残留
  全零 —— **数据门全过**。[2/4] hermes ping 连续两次超时（>120s）；手工复刻精确调用
  `hermes chat -q "只回答一个字：通" -Q` 实测 **99.7s 返回"通"** —— 端点活着但极慢
  （1 字回答 ~100s；9/10-9/12 全量跑时为秒回），判定为 LLM 端点负载问题，与本次数改
  无关（本脚本不触 hermes/LLM 链路）。不做调大超时的掩盖处理——门禁拒得对：
  以此延迟开全量（133 题 × LLM 判分）不可行，Step 6 放行前须端点恢复正常延迟。
