# 预报 Skill Changelog

## v1.0.0 — 2026-06-22(首版交付:Tasks 1-8 完成 + 审计通过 + 缩减基线)

### 构建内容(Tasks 1-8,均经 task-reviewer 双阶段评审通过)

- **T1 脚手架 + COPY infra**:目录树 + `query_utils.py`/`skill-auditor.py`/`eval-txt.py`/`quick_validate.py`(逐字 COPY)+ `hermes-safe.sh`(软链 simulation)+ `db-config.md`(3 caveat + taskid 三拼写)。commit `c209070`
- **T2 生成器 + 迁移 + seed**:`st_pptn_re_forecast` 103→本地(8402 行);`generate_forecast_data.py`(断点接续 + mock 源/精度 + NMC fixture);`baseline_seed.sql` 三岔基线幂等。commit `2ebfd2b` + fix `88ad893`(补未来 f_rnfl_h 168h)
- **T3 `query_forecast_data.py`**:12 `--type` + `full_context` 聚合;stcd 从 config 读;taskid CAST JOIN;flood_limit 字段+值;精度 gated。commit `21da6cb`
- **T4 `query_forecast_analysis.py`**:fusion_detail/accuracy_report/similar_floods/forecast_timeline;NMC JSONP 解析。commit `1e14419`
- **T5 references/**:6 文件(1445 行);C1 自洽 ✅;C2 零硬编码。commit `2501abc`
- **T6 `SKILL.md`**:v1.0.0,15 节,5 意图路由 + 输出蓝图;skill-auditor 🟢 0/10。commit `78f75a6`
- **T7 测试 + 边缘 seed**:v1 45Q + v2 41Q(8 类)+ 6 幂等边缘 seed + 预报-实测重叠。commit `c6b608e`
- **T8 eval 工具链**:eval-txt 4→6 维(E5/E6 条件分类);run_tests.sh(copy run-17-robust + 9 分层题)。commit `73518bd`

### T9 审计 + 基线

- **skill-auditor**:🟢 **通过,风险分 0/10**(C1-C5 全 PASS,C2/C4 必须)。见 `results/audit.txt`。
- **quick_validate**:标注 4 个 Hermes 专有 frontmatter 键(author/platforms/prerequisites/version)——预期(plan-generation 同),skill-auditor 为约束闸门。
- **hermes 加载**:本 skill 未预装 builtin,经软链注册 `~/.hermes/skills/forecasting → <repo>/SmartTwinRes-skills/forecasting` 后由 hermes 按名加载。`run_tests.sh` 调用改为 `hermes -z "$Q" --skills forecasting` + 注册守卫(本 commit 含该修复)。

### 基线结果(缩减 4 题 × 1 跑,本地端点不稳)

| 题 | 分 | 状态 |
|----|----|----|
| Q1 预报解读 | 1/4 | clean(查对数据 + 触发陈旧检测,但无蓝图/引用) |
| Q2 水库影响 | **5/5** | clean(**完整蓝图 + GB/T 22482 引用 + 安全/置信 + C1 gated + HITL**) |
| Q3 多源融合 | 0/5 | stall(endpoint connection error) |
| Q4 趋势预测 | 0/5 | stall(endpoint HTTP 503) |

- clean 题 E1-E4 均 = 62.5%(n=2);Q2 含 E5/E6 = 5/5 = 100%。
- 详见 `results.tsv` 与 `analysis.md`(达标判断 + 缺口 + 下轮实验)。

### 已知缺口(诚实)

1. **完整 9×3 基线未完成**:本地 LLM 端点(Qwen 系)503/connection 不稳 + 并发互锁,仅得 4 题×1 跑。≥90% 达标**未证实**,待端点稳定补跑。
2. **蓝图遵守不稳**:Q2 完整产出三段蓝图 + 引用,Q1(同端点不同时刻)无蓝图标记——模型对蓝图模板遵守随机,需强化(下轮实验)。
3. eval-txt glob 命中非题面文件(audit/validate)→ 总分失真,待收窄为 `Q*.txt`。
4. skill-creator eval-viewer/grader/comparator 盲评 + run_loop description 优化未实现(可选增强)。
5. 场景边缘 seed 的 clean-load-eval-clean 循环未跑。

### 关键修正(实测驱动)

- 运行时 DB 改本地 127.0.0.1(与兄弟 skill 一致),103 仅迁移只读源;仅 `st_pptn_re_forecast` 本地缺失已补迁。
- 预报值在 `st_mx_preset_cal_r`(type 21/22)经 taskid 关联 `model_result_files`。
- taskid 三拼写 → CAST JOIN;`f_rnfl_h` 不加 tenant;`model_result_files` 无 deleted;`weather_info/warn` 无 tenant。
- C1 缺陷 → 精度 gated;NMC = HTTP fixture(JSONP)非 DB 行。

## Autoresearch 迭代(2026-06-23)
- v1.1 瘦身(`7d56679`):full_context 11→5,Q3 staller 修复(5/5),clean 7/9。
- v1.2 E4 TL;DR(`a65f2d3`):输出契约前置;单跑未证增益(Q2 跑偏掩盖),平均增益。
- 详见 analysis.md「Autoresearch 迭代记录」。基线:弱端点最佳努力,skill 功能已验证;≥90% 待端点升级。
