# 2026-09-15 step-3.7-flash 全量评测深度分析

> 运行：output/2026-09-15/full-step37flash-20260915-191735/（19:17→22:35，3.2h，rc=0）。
> 被测 agent：step-3.7-flash（stepfun-plan provider，api.stepfun.com/step_plan/v1）；
> 判官：GLM-5.1（控制变量不变）。接线：eval/lib/transport.py EVAL_HERMES_PROVIDER/MODEL（未提交）。

## 结果：114/133 = 85.7%，vs Qwen3.8-27B 基线 126/133=94.7%，-9pp

- 零 ERROR、零 TIMEOUT（基线 9/14 有 1 ERROR）；最长 PG21 1207s。
- 总答题耗时 3.15h vs 7.17h（中位数 58s vs 127s，快 2.2×）。
- 迁移：17 题 Qwen PASS→step FAIL；**6 题 Qwen 未过→step PASS**
  （PG3/PG20/SIM17/SIM29/SUP5/SIM30，即 9/15 修复批次题——rubric 条件化+终答契约
  修复同时提升了考卷对不同模型的鲁棒性）。

## 19 FAIL 三类归因（轨迹级）

### A 格式/收口失分 ~10 题（step 行为短板：终答契约跟随度弱）
- EW29/EW30：查对"不存在测站"，未输出 rubric 字面提示语；输出带闲聊尾
  （"需要我进一步查吗？♪"）。
- EW10：线性外推数值正确（463.25m）、给依据，缺"置信度"字段。
- EW16：风险定性完整（告警引擎停摆 98 天等），缺"告警数量+级别分布"。
- F24：调度分析正确，缺 HITL 人工复核句。
- EW22/EW6：跨域联合查询做了，未显式声明"已联合/数据局限"。
- DV3（试点已见）：rubric 意图越界——按真实工况加严批判合成演练件。
- 根因：**工具调用层完美（DB 查询全对），收口层不达标**；输出夹带颜文字。

### B 深度/证据链不足 ~6 题
- DV1 四层全挂（Phase 0/2/5/7/8）——多步诊断推理是 step 明显短板。
- SUP1 七步链中断（120s，太快=跳步）。
- PG5/PG16/PG23：缺法规引用/推荐理由/经验提炼——综合分析产出过瘦。

### C 评测资产侧 ~3 题（非 step 全责，需人工裁定）
- DV7 租户纪律条目（历史上易翻题）。
- SIM18/SIM22 异常场景边缘题（Qwen 擦线过）。

## 结论
1. **不能直接替换** Qwen 做正式基线（-9pp）；但快 2.2×、零超时、零 ERROR，
   适合每日回归冒烟与修复验证预跑。
2. A 类 ~10 题可通过 SKILL 终答契约加严（禁闲聊尾/强制字段清单/收口句式）
   挽回大半，预期 ≥92%；但该契约改动会影响 Qwen 基线题面生态，需权衡。
3. C 类 3 题待裁定是否 rubric 再条件化。

## 附：transport 接线
eval/lib/transport.py 新增 EVAL_HERMES_PROVIDER/EVAL_HERMES_MODEL 环境变量可选
覆盖被测 agent 模型，判官走 EVAL_JUDGE_MODEL；缺省行为不变；15 transport 单测过。
**未提交**（provider 配置在 /root/.hermes/config.yaml、密钥在 .env，均在仓库外）。
