# Simulation Skill Autoresearch Changelog

## Experiment 0 — baseline

**Score:** 32/48 (66.7%)
**Change:** 无修改，原始 v1.0 SKILL.md
**Result:** 基线评估

### 评估维度通过率
- E1 数据正确性: 11/12 (92%) ✅
- E2 安全约束: 5/12 (42%) ❌ 主要优化目标
- E3 结构完整: 12/12 (100%) ✅
- E4 知识引用: 4/12 (33%) ❌ 主要优化目标

### 失败模式分析

**E2 失败 (7题):** Q17,Q24,Q40,Q44,Q45,Q62,Q74
- 共同特征：输出未提及汛限水位、下游安全泄量等安全约束
- 集中在结果解读、预演报告、历史经验异常类别

**E4 失败 (8题):** Q14,Q17,Q26,Q40,Q44,Q45,Q50,Q62
- 共同特征：输出未引用任何法规标准（防洪法、GB、SL、调度规程）
- 几乎所有能力类型都受影响

### 下一步
Exp 1 目标：在 SKILL.md 中增加"输出规范"通用规则，强制引用安全约束和法规标准

## Experiment 1 — baseline (模型切换)

**Score:** 36/48 (75.0%)
**Change:** mimo-v2.5-pro → 讯飞 Qwen xopqwen36v35b，保持 v1.1 SKILL.md
**Reasoning:** mimo 配额耗尽(429)，切换模型；同时验证 v1.1 优化效果
**Result:** E2大幅提升(42%→83%)，E1+E3满分，但E4知识引用下降(33%→17%)
**结论:** v1.1的E4"软指令"不够强，需要强化为强制模板

## Experiment 2 — running

**目标:** E4知识引用优化
**Change:** v1.1 → v1.2
- 强化E4为"强制必做"硬性要求
- 增加法规标准库表（7种场景对应7条法规）
- 增加强制输出模板（结尾必须有"法规依据"段落）
- 明确"不引用法规视为不合格"
**评估样本:** 12题→17题（新增Q1,Q11,Q46,Q66,Q42覆盖更多能力）

## Experiment 4 — keep ✅

**Score:** 50/60 = 83.3%（15有效题，剔除Q74/Q66 stream错误）
**Change:** v1.2 → v1.4 分级引用策略
- E4改为分级：A类(安全/评估/报告)必须引用≥2条，B类(计算/预演)建议≥1条，C类(查询)无需
- 增加判断口诀降低分类负担
- 给具体可复制的示例句
**Result:** E4大幅提升(17%→60%)，总分75%→83.3%
**新增题表现:** Q1/Q11/Q46/Q42 全部4/4满分
**剩余失败:** Q24,Q40,Q62(E2+E4双败)，Q45,Q50,Q56(仅E4败) — 集中在边界/异常场景

## Experiment 5d — keep ✅✅ 重大突破

**Score:** 61/68 = 89.7%（17题全跑通，0失败）
**Change:** v1.4 → v1.8
- v1.6: "输出蓝图"3段结构（依据/分析/校验与依据）
- v1.7: 禁止import pymysql（后改为v1.8分级引导）
- v1.8: 三级数据获取策略 + 防卡死规则（同代码最多2次）
- 鲁棒运行器：10s间隔 + 错误自动重试2次 + 跳过已成功
**Result:** E4从60%→76%，E2从80%→88%，总分83.3%→89.7%
**关键:** Q24(数据核实)、Q40/Q44/Q45(报告类stream stalled)全部修复
**剩余失败:** Q40/Q56/Q62/Q46（4题，集中在历史/无数据/敏感性场景）

## Experiment 6 — keep ✅✅ 突破95%

**Score:** 65/68 = 95.6%（17题）
**Change:** v1.8 → v1.9 三项针对性改动
- 顺序铁律：文件路径必须放在【校验与依据】之前，不能当结尾（针对Q40）
- 敏感性分析精简模板：用汇总表，禁止逐档详述（针对Q46的token超限）
- 历史经验类任务表：明确引用《调度规程》（针对Q56）
**Result:** Q40(2/4→4/4)、Q46(2/4→4/4)修复；Q56仍3/4（历史叙事型难根治）；Q62接受为合理无引用场景
**最终:** 89.7% → 95.6%（+5.9%），3/4失败题修复

## Experiment 7 — SkillEvolver Auditor + 过拟合修复（v1.9.1→v1.9.3）

**起因:** 引入 SkillEvolver(arXiv:2605.10500) 的 5 项 Auditor 检查,发现 v1.9 有 C2 过拟合:
- `462.88m`(汛限)硬编码 9 次、`95.1`(安全泄量)2 次、DB 口令明文
- 这些"规则类字面量"会被 fresh agent 照抄进输出 → 换水库就错(eval 测不出,因为硬编码值恰=三岔真值)

**新增工具:** `skill-auditor.py` — 规则化检查 C1 self-contained / C2 hardcoded-const / C3 param-axis / C4 entry-point / C5 silent-bypass

### v1.9.1 — discard ❌（参数化方式错误）
**Change:** 用 `<查询汛限>` 占位符 + "必须动态查询"铁律参数化 7 处
**Result:** **回归!** 95.6% → 86.8%（−6），E4 掉 4、E2 掉 2
**根因(初判错→后纠正):** 占位符+"查询"动词诱导模型走 execute_code 查参数,触发 `import sys` 死循环(单题 exec 14-23 次),**回答在写结尾段前被 stream 中断**,E4/E2 段根本没生成

### v1.9.2 — discard ❌（铁律改轻无效）
**Change:** 铁律从"必须查询"→"复用已查值,不发额外请求" + 结尾段优先
**Result:** 仍 86.8%,E4 仍 2/6 —— **无效**,证明根因不是 token 预算,是 execute_code 中断

### v1.9.3 — keep ✅（读 JSON 字段措辞）
**Change:** 回到 v1.9 行为,但参数化改用"读 JSON 字段"措辞:
- `<查询汛限>m` → `{flood_limit_level}m`（占位符指向字段名,非"去查"动作）
- 安全表/参数表："查询 --type" → "full_context 返回的 flood_limit_level 字段"
- 防卡死规则新增「能用脚本/已有数据就别写 Python」+ 安全校验=纯文字填写
- 保留：结尾段优先、DB 口令环境变量化
**Result(6题定向):** v1.9 24/24 → **v1.9.3 23/24**,E4 从 v1.9.1 的 2/6 恢复到 **5/6**
- Q24/Q38/Q74 完全恢复 4/4,Q45 恢复到 3/4(单次方差:用了"法规依据"元描述而非真引用)
- 2 对照题(Q1/Q50)全程 4/4 稳定
**auditor:** 全 5 项 PASS,风险 0/10(C2 过拟合已治,且未引入新风险)

**核心教训:** skill 里凡是暗示"去查/去算"的措辞,都可能诱导模型走 execute_code 死路;**正确的参数化是"读你已有的返回字段",让模型意识到值就在手边**。

## Experiment 8 — harness 层根治 execute_code 死循环（方案 B，code_retry_guard 插件）

**目标:** v1.9.3 只是 prompt 疏导,模型偶尔仍反复 execute_code(单题 14-23 次)。从 hermes harness 层物理拦截。

**调研(Explore agent):** hermes v0.13.0 有 `pre_tool_call` 钩子,插件返回 `{"action":"block"}` 即拦截单次工具调用,信息以 `{"error":...}` 回流 LLM。零核心改动。`VALID_HOOKS` 含 pre/post_tool_call/on_session_end 等。

**实现:** `/opt/git/hermes-agent/plugins/code_retry_guard/` —— 注册 pre_tool_call + post_tool_call + on_session_end。config.yaml 加 `plugins.enabled: [code_retry_guard]`。

**验证过程(3 次诊断,关键发现):**
1. ✅ hook **确实对 execute_code 触发**,task_id 一致,args 有 `code` 键 —— 机制可用,Explore 结论准确
2. ❌ **初版"按 code-hash 去重"无效**:debug 日志显示 10 次 execute_code 每次 code_hash 都不同(n=1,永远到不了 limit=3)。**真相:模型每次写完整脚本(虽以 import 开头但内容各异)**,按代码去重根本累加不起来。这是我和 Explore 都误判的真实失败模式
3. ✅ **改为"连续失败 N 次"逻辑**:post_tool_call 判定失败(exit_code≠0/Traceback)累计 consec_fails,成功清零;pre_tool_call 在 consec_fails≥3 或 total≥15 时 block。单元测试通过

**结果(实测 4 次 Q24):**
- guard **不误伤**:6 次成功 exec → consec_fails 全程 0 → 正确不 block
- 但**没能在"真正的失败"中验证 block 有效**——因为暴露了**更深的元凶**:

**🔴 最重要的发现 —— 真正的元凶是 Stream Stall,不是代码循环:**
guard 版 Q24 输出第一行: `⚠ Stream stalled mid tool-call (execute_code); the action was not executed`。运行 3m17s 后 **流式连接在工具调用中途中断**,回答没写完 → 0/4。
- stream stall 是**传输层中断**,不产生"失败结果",post_tool_call 根本收不到 → **guard 拦不到**
- 同 Q24 在不同 run 出现过 4/4、3/4、0/4、stalled —— **非确定性极高**
- 根因指向**讯飞 Qwen endpoint 流式连接不稳**,属上游问题,不在 skill/plugin 层

**结论:** guard 作为**安全网保留**(机制正确、零误伤、偶尔真代码循环时能兜住),但它**不是关键**。真正瓶颈是 stream stall,需上游修复(讯飞 endpoint 稳定性 / hermes stream 自动重连)。

**对前期结论的修正(重要):** 因非确定性极高,之前 v1.9→v1.9.1 的 95.6%→86.8% 回归里,**有多少是真实回归、多少是 stream stall 随机噪声,单次 run 分不清**。"单次 run eval"方法在 endpoint 不稳时逼近失效,后续优化应改用多次 run 取均值。
