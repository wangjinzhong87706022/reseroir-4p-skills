# common-schema（跨 skill 复用的表结构）

本目录收录被多个 skill 共同引用的数据库表结构文档，避免每个 skill 的 `references/table-schema.md` 各复制一份且漂移。

## 已收录表

| 表名 | 说明 | 引用 skill |
|------|------|-----------|
| `st_stbprp_b` | 测站基本信息（stcd/stnm/位址/类型） | forecasting / plan-generation / simulation / early-warning / diagnosis-verification |
| `st_rvfcch_b` | 洪水指标（水位/流量/降雨） | forecasting / simulation / plan-generation |

## 待补表

按需补充，每次新增表结构时同步更新本表。

## 维护规则

1. 本目录文档是**唯一真相源**，各 skill 的 `references/table-schema.md` 如有重复内容应改为引用此处。
2. 修改表结构文档时，**必须**同步更新本目录对应文件，避免文档漂移。
3. 新增跨 skill 表时，先在此处建档，再在 skill 的 `references/` 里引用。
