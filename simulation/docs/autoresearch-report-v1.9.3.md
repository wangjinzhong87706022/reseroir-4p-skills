# 预演 Skill Autoresearch 报告 v1.9.3 + Harness 层探索

> 阶段:Exp 7（SkillEvolver Auditor + 过拟合修复）+ Exp 8（harness 层 code_retry_guard 插件）
> 日期:2026-06-16
> 关联:前序报告 `autoresearch-report-v1.9.md`（v1.0→v1.9,66.7%→95.6%）

---

## 0. TL;DR

- **Exp 7**:引入 SkillEvolver 的 5 项 Auditor,发现 v1.9 有 **C2 过拟合**（汛限 `462.88m` 硬编码 9 次、DB 口令明文 —— eval 测不出,因为硬编码值恰=三岔真值）。经 v1.9.1/1.2 两轮失败,最终 **v1.9.3 用"读 JSON 字段"措辞** 治好过拟合,分数 ~94.1%（推算）。
- **Exp 8**:为根治 execute_code 死循环,做了 harness 层 `code_retry_guard` 插件。机制验证通过、零误伤,但**最重要的发现是:真正的元凶是 stream stall（讯飞 endpoint 流式不稳),不是代码循环** —— guard 拦不到它。
- **当前交付**:v1.9.3 skill + guard 插件（安全网）+ skill-auditor.py 工具。**真正下一步是上游 stream 稳定性,不在 skill 层。**

---

## 1. Exp 7 — SkillEvolver Auditor 与过拟合修复

### 1.1 起因:用论文方法审视自己的 skill

读完 SkillEvolver（arXiv:2605.10500）后,把它的 5 项 Auditor 落地为 `skill-auditor.py`,对 v1.9 跑了一遍:

| 检查 | v1.9 结果 |
|------|----------|
| C1 self-contained | ✅ PASS |
| **C2 hardcoded-const** | **❌ FAIL** —— `462.88m`(汛限)×9、`95.1`(安全泄量)×2、DB 口令 `123456aA.` 明文 |
| C3 param-axis | ✅ PASS |
| C4 entry-point | ✅ PASS |
| C5 silent-bypass | ✅ PASS |

**关键洞察 —— 为什么 eval 测不出 C2**:`462.88m` 恰好是三岔水库的真实汛限值,所以在这套 eval 上"看起来全对"。这正是 SkillEvolver 的核心论点:**过拟合在训练实例 eval 上隐形,必须独立 Auditor**。硬编码值会随 skill 部署到其他水库而 silently 出错。

### 1.2 三轮迭代:v1.9.1 → v1.9.2 → v1.9.3

| 版本 | 改动 | 分数 | 结论 |
|------|------|------|------|
| v1.9 | (基线) | 95.6% | C2 过拟合未发现 |
| **v1.9.1** | `<查询汛限>` 占位符 + "必须动态查询"铁律 | **86.8%（−6）** | ❌ 回归 |
| **v1.9.2** | 铁律改轻"复用已查值" + 结尾段优先 | 86.8% | ❌ 无效 |
| **v1.9.3** | "读 JSON 字段"措辞 + 防卡死强化 | **94.1%（推算）** | ✅ 成功 |

**失败原因（v1.9.1/1.2）**:`<查询汛限>` 占位符 + "查询"动词**诱导模型走 execute_code 去查参数**,触发反复执行,导致回答在写结尾段前被截断,E4/E2 段没生成。

**成功原因（v1.9.3）**:把占位符从"去查的动作"改成 `{flood_limit_level}`（指向字段名）,并明确"值就在你已拿到的 full_context JSON 里,直接读,别 execute_code"。模型意识到值在手边,不再去写代码。

### 1.3 核心教训（跨 skill 通用）

> **skill 里凡是暗示"去查/去算"的措辞,都可能诱导模型走 execute_code 死路。正确的参数化是"读你已有的返回字段",让模型意识到值就在手边。**

---

## 2. Exp 8 — harness 层 code_retry_guard 插件

### 2.1 目标

v1.9.3 只是 prompt 疏导,模型偶尔仍反复 execute_code（单题 14-23 次）。从 hermes harness 层物理拦截,让结果**稳健**而非靠运气。

### 2.2 调研结论（Explore agent）

hermes v0.13.0 有干净的 per-tool-call 拦截机制:
- `pre_tool_call` 钩子:插件返回 `{"action":"block","message":...}` 即拦截,信息以 `{"error":...}` 回流 LLM,模型自然转向文本回答
- `execute_code` 工具**无状态**（每次新子进程）,死循环必须在调用层拦
- **零核心改动**,只需一个 ~120 行插件

`VALID_HOOKS` 完整列表确认含 pre_tool_call / post_tool_call / on_session_end。

### 2.3 实现

- `/opt/git/hermes-agent/plugins/code_retry_guard/__init__.py`
- `/opt/git/hermes-agent/plugins/code_retry_guard/plugin.yaml`
- `~/.hermes/config.yaml` 加 `plugins.enabled: [code_retry_guard]`
- 逻辑:`post_tool_call` 判定 execute_code 失败→累计 consec_fails,成功清零;`pre_tool_call` 在连续失败≥3 或总调用≥15 时 block

### 2.4 验证过程的两次纠错

**纠错 1 —— 初版"按 code-hash 去重"无效。** debug 日志显示 10 次 execute_code 每次 code_hash 都不同（n=1,永远到不了 limit=3）。真相:模型每次写**完整脚本**（虽以 import 开头但内容各异）,按代码去重累加不起来。**这是我和 Explore 都误判的失败模式。**

**纠错 2 —— 改为"连续失败 N 次"。** 单元测试通过（连续失败 3 次→BLOCK,成功清零）。实跑确认零误伤（6 次成功 exec→consec 全程 0→正确不 block）。

### 2.5 🔴 最重要的发现:真正元凶是 Stream Stall

guard 版 Q24 输出第一行:
```
⚠ Stream stalled mid tool-call (execute_code); the action was not executed.
```

运行 3m17s 后**流式连接在工具调用中途中断**,回答没写完 → 0/4。

| 问题 | 性质 | guard 能否治 |
|------|------|-------------|
| 模型反复执行同类代码 | 应用层 | ✅ 能（consec_fails） |
| **Stream stalled mid tool-call** | **传输层** | ❌ **不能** |

stream stall 不产生"失败结果",`post_tool_call` 根本收不到事件 → guard 拦不到。**真正的元凶是讯飞 Qwen endpoint 的流式连接不稳**,属上游问题。

### 2.6 结论

- guard **作为安全网保留**:机制正确、零误伤、偶尔真代码循环时能兜住
- 但它**不是关键瓶颈**。继续在 skill/plugin 层抠,边际收益已很低
- 真正下一步是**上游 stream 稳定性**（讯飞 endpoint / hermes stream 自动重连）

---

## 3. 对前期结论的重要修正

### 3.1 非确定性极高,单次 run eval 不可靠

同一个 Q24 在不同 run 出现过:4/4、3/4、2/4、0/4、stream stalled。**模型 + endpoint 双重非确定性**,让"调 prompt → 跑一次 → 看分"的优化方法**逼近失效**。

**含义**:之前 v1.9→v1.9.1 的 95.6%→86.8% 回归里,有多少是真实回归、多少是 stream stall 随机噪声,**单次 run 分不清**。

### 3.2 后续优化方法学建议

- ❌ 单次 run 评分:噪声太大,无法干净归因
- ✅ 多次 run 取均值（每题跑 3-5 次取通过率）
- ✅ 区分"应用层失败"（代码循环,guard 可治）和"传输层失败"（stream stall,需上游）

---

## 4. 交付物清单

| 文件 | 说明 | 状态 |
|------|------|------|
| `simulation/SKILL.md` v1.9.3 | 参数化用"读 JSON 字段"措辞,治 C2 过拟合 | ✅ 已同步 hermes 双副本 |
| `plugins/code_retry_guard/` | harness 层 execute_code 死循环拦截插件 | ✅ 已启用,安全网 |
| `skill-auditor.py` | SkillEvolver 5 项过拟合检查工具（可复用其他 skill） | ✅ |
| `changelog.md` | Exp 7 + Exp 8 完整记录 | ✅ |
| `results.tsv` | Exp 7a/7b/7c 结果 | ✅ |
| `results.v1.9/.v1.9.1/.v1.9.2/.v1.9.3.bak` | 逐版结果留痕 | ✅ |

---

## 5. 下一步建议（按性价比排序）

1. **【上游,最高性价比】查讯飞 Qwen endpoint 的 stream stall 根因** → **已查清,见下方第 7 节:Engine Busy 防御已落地**。
2. **【方法学】改多次 run 评分**。把 eval 改成每题 3 次取通过率,降低噪声,让后续优化可归因。
3. **【复用】把 skill-auditor.py + code_retry_guard 应用到其他 skill**（预案/预警）。guard 是通用的 execute_code 安全网;auditor 的 C2 检查能快速发现其他 skill 的硬编码。
4. **【可选】v1.9.3 全 17 题精确分**。当前 64/68=94.1% 是 6 题实测+11 题推算。要精确分需重跑（~40 分钟,且受 stream stall 噪声影响）。

---

## 7. Engine Busy 根因与防御（Exp 8 延伸,已落地）

### 7.1 根因（日志铁证）

hermes 日志 `~/.hermes/logs/agent.log` 实锤:
```
WARNING: Streaming failed after partial delivery, not retrying:
Xunfei request failed code: 10010, msg: RecvFromEngineError:Engine Busy
```

**`Engine Busy`(code 10010) = 讯飞引擎过载/限流信号。** 日志中 Engine Busy 出现 39 次、其他限流信号(429/rate/quota)299 次。

触发模式(Q24 session 99005f):1 分钟内密集打了 8 次 API 调用,第 9 次时讯飞引擎扛不住返回 Engine Busy。且 hermes 策略是"部分发送后不重试"(防重复消息)→ 流死在工具调用发到一半 → 工具调用丢失 → 回答中断 → 0 分。

**因果链**:execute_code 死循环 → API 调用密集 → 触发 Engine Busy → stream stall。所以代码循环是上游放大器,Engine Busy 是下游爆点。

### 7.2 定性:讯飞共享 MaaS 的固有限制

Engine Busy 是讯飞共享引擎被多租户挤占导致,**生产环境用专属实例/更高 QPS 档大概率不会撞上**。但测试环境/共享实例下确实频发,需留防御。

### 7.3 防御方案:hermes-safe.sh wrapper（不改 hermes 源码）

约束:不改 hermes agent 源码。Engine Busy 是瞬态故障(引擎忙一会就恢复),正确处理 = **退避等恢复 + 重跑整题**。而重跑必须在 hermes 单次 turn 之外(工具调用已丢失,turn 内无法恢复),所以**调用层(wrapper/runner)是唯一正确的位置**。

**实现**:`autoresearch-simulation/autoresearch-simulation/hermes-safe.sh`
- 封装 `hermes chat`,透传所有参数
- 检测输出里 `Engine Busy|RecvFromEngineError|10010|Stream stalled mid tool-call`
- 命中 → 退避 `EB_BACKOFF_SECS`(默认 45s,等引擎恢复)→ 重试,最多 `EB_MAX_RETRY`(默认 3)次
- 正常调用零开销直接透传;交互式/eval 通用

**单元测试通过**:用假 hermes(前 2 次返回 Engine Busy、第 3 次正常)验证 → wrapper 正确退避重试,第 3 次成功。

**集成**:`run-17-robust.sh` 改为 `HERMES="bash .../hermes-safe.sh"`,eval 自动获得 Engine Busy 退避重试能力。

### 7.4 三层防御体系（全部不改 hermes 源码）

| 层 | 机制 | 作用 | 状态 |
|----|------|------|------|
| 预防 | code_retry_guard 插件 + skill v1.9.3 引导少 execute_code | 降低 API 调用密度 → 少触发 Engine Busy | ✅ |
| 治疗 | hermes-safe.sh wrapper 退避重试 | Engine Busy 发生时自动恢复 | ✅ |
| 兜底 | run-17-robust.sh 本身的 stall 检测重试 | wrapper 失败后再兜一层 | ✅ |

---

## 6. 总结

这一阶段（Exp 7+8）的价值不在"又涨了 X 分",而在三件事:
1. **发现并修复了 C2 过拟合** —— 一个 eval 测不出、但会真实损害跨水库部署的问题（v1.9.3）
2. **搞清了 execute_code 死循环的真正机制** —— 不是代码重复,是多变体调用;且真元凶是 stream stall
3. **建立了可复用的工具链** —— skill-auditor（过拟合检查）+ code_retry_guard（harness 安全网）

更重要的是:**定位了真正的瓶颈在 endpoint stream 稳定性,不在 skill 层** —— 这避免了后续在 skill prompt 上空转。
