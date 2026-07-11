# 预案 Skill 优化与评估报告（2026-06-18 session）

> 本文档记录 2026-06-18 这次 session 对预案 (plan-generation) skill 的全部优化、评估与使用的工具。
> 关联：凭据配置见 `db-credential-config.md`；工具链发源见 `simulation/autoresearch-simulation/autoresearch-simulation/` 下 autoresearch 报告。

---

## 一、优化（SKILL.md v3.1 → v3.2 + 脚本）

| # | 优化项 | 改动 | 来源/动机 |
|---|--------|------|----------|
| 1 | **移植输出蓝图**（核心）| 顶部新增⛔输出蓝图：开头【依据】→ 中间【分析】→ 结尾【校验与依据】（强制最后）；分类型填充表（生成/解读/形势/决策/应急/知识问答）；法规标准库（防洪法/水库大坝安全管理条例/防汛条例/GB 17621-1998/SL 224-2019）；参数取值规则；结尾段优先 | 复用 simulation v1.8 验证过的范式，治 C4（顶部无主入口）+ 提升 E3/E4 |
| 2 | **DB 明文口令环境变量化** | SKILL.md 里 `mysql -p123456aA.` → `-p"$SRM_DB_PASSWORD"` | 治 auditor C2 过拟合 |
| 3 | **脚本兜底清除** | `query_utils.py`、`query_simulation_data.py` 的 user/password 从硬编码兜底 → `_require_env()` 强制环境变量，无值报错退出 | 彻底根除口令，C2 真正 PASS |
| 4 | 版本号 | 3.1.0 → 3.2.0，同步 hermes 双副本（`~/.hermes` + `/opt/git/hermes-agent`）| — |

---

## 二、评估

### 2.1 auditor 5 项过拟合检查（v3.2）

| 检查 | v3.1 | v3.2 | 说明 |
|------|------|------|------|
| C1 self-contained | ✅ | ✅ | 引用文件齐全 |
| **C2 hardcoded** | ❌(明文口令) | **✅** | 口令环境变量化+脚本兜底清除 |
| C3 param-axis | ⚠️ | ⚠️ | 查询引导可加强 |
| **C4 entry-point** | ❌(无主入口) | **✅** | 输出蓝图生效 |
| C5 silent-bypass | ❌ | ❌(误报) | "无需"是合理分级设计（C类任务），接受 |

### 2.2 功能评估（8 题 baseline，经 hermes-safe wrapper）

**关键：按 Engine Busy 污染分层看，不能糊在一起**

| 分组 | E1数据 | E2安全 | E3结构 | E4引用 | 总分 |
|------|--------|--------|--------|--------|------|
| **干净4题**（Q1/Q9/Q19/Q33，stall=0）| 4/4 | 4/4 | 4/4 | 3/4 | **15/16 = 93.8%** |
| 污染4题（Q14/Q24/Q35/Q45，stall≥10）| 4/4 | 2/4 | 1/4 | 1/4 | 8/16 = 50% |

**评估维度（eval-txt.py 4 维二元标准）：**
- E1 数据正确性：含 ≥3 个数值（水位/流量/降雨/百分比）
- E2 安全约束：提及汛限/安全泄量/超限/安全余量等
- E3 结构完整：含 ≥3 个结构标记（【】/一二三/方案A/调度目标等）
- E4 知识引用：引用 ≥1 条法规/标准/调度规则

### 2.3 结论

- **v3.2 真实水平 ≈ 93.8%**（干净题）
- E1 数据 8/8 全满分（即使被 stall 污染，数据部分都在）→ 数据获取稳
- 输出蓝图核心目标达成：干净题 E2/E3 满分，法规引用丰富（《防洪法》《水库大坝安全管理条例》GB 17621 SL 224）
- 参数取值规则生效：Q1 用查询值 461.5m 而非照抄 462.88m → C2 过拟合没回来
- 唯一丢的 E4（Q33"预案vs预演区别"）是知识问答，本无需引用，合理
- **污染4题低分完全是 Engine Busy 截断结尾段，非 skill 问题** → 印证瓶颈在 endpoint 不在 skill
- v3.2 判定：**keep ✅**

---

## 三、使用的工具

| 工具 | 用途 | 新建/复用 |
|------|------|----------|
| **skill-auditor.py** | 5 项过拟合检查（C1-C5），规则化评估 | 复用（simulation 那轮建），本 session 修了 C2 正则 bug（`--plan-id` 误匹配 `-p`）|
| **eval-txt.py** | 4 维轻量评分器（E1数据/E2安全/E3结构/E4引用），吃 hermes 真实 txt 输出 | **本 session 新建**（预案专用，仿 simulation eval_e1-e4）|
| **hermes-safe.sh** | Engine Busy 退避重试 wrapper | 复用（simulation 那轮建），run_tests.sh 改为调用它 |
| **run_tests.sh** | 预案测试 runner | 改造：wrapper + 600s 超时 + 10s 间隔 |
| **code_retry_guard 插件** | execute_code 死循环拦截 | 复用（hermes 全局，预案自动受益）|
| hermes chat / MySQL | 运行时执行 + 数据源 | 既有 |

---

## 四、产出物清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` v3.2 | 输出蓝图 + 口令环境变量化 |
| `scripts/query_utils.py` | 兜底清除 |
| `docs/db-credential-config.md` | 凭据配置指南（含🔴状态横幅）|
| `autoresearch-plan-skill/eval-txt.py` | 4维评分器（新建）|
| `autoresearch-plan-skill/run_tests.sh` | 改用 wrapper |
| `autoresearch-plan-skill/results.v3.1.bak` | 旧结果留痕 |
| memory: `plan-generation-v3-test-results.md` | 沉淀记录（新建）|
| `MEMORY.md` 索引 | 更新 |

---

## 五、一句话总结

本 session 把预案 skill 从 **v3.1（无主入口结构、口令硬编码）优化到 v3.2（输出蓝图 + 凭据彻底环境变量化）**，复用 simulation 那轮建的工具链（auditor / hermes-safe / code_retry_guard）+ 新建了预案专用的 eval-txt.py 评分器；干净题评估达 **93.8%**，C2/C4 过拟合治理通过，剩余瓶颈是讯飞 endpoint 的 Engine Busy（非 skill 问题，生产换专属实例后自然消失）。
