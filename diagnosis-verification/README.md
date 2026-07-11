# diagnosis-verification Skill

> **水库四预系统诊断与验证 Skill**：8 阶段结构化诊断 + 6 层独立验证 + 6 步自动修复

**版本**：v1.0.0  
**作者**：SmartTwinRes Team  
**适用场景**：forecasting、early-warning、plan-generation、simulation 全场景

---

## 🎯 核心能力

### 1. diagnose（诊断）— 8 Phase

- Phase 0：澄清确认
- Phase 1：全景扫描
- Phase 2：数据质量检查
- Phase 3：异常详情
- Phase 4：关联分析
- Phase 5：根因分析（6 类分类 + 证据链推理）
- Phase 6：影响评估
- Phase 7：修复建议（短期止血 + 长期根治）
- Phase 8：知识沉淀

### 2. verify（验证）— 6 Layer

- Layer 1：数据源验证
- Layer 2：格式规范验证
- Layer 3：业务规则验证
- Layer 4：安全约束验证
- Layer 5：跨域一致性验证
- Layer 6：法规符合性验证

### 3. auto-fix（自动修复）— 6 Step

- Step 1：解析诊断报告
- Step 2：查询知识库
- Step 3：生成修复方案
- Step 4：生成修复补丁
- Step 5：执行测试（最多 3 轮重试）
- Step 6：提交并部署

---

## 📦 文件结构

```
diagnosis-verification/
├── SKILL.md                         主文档
├── README.md                        本文件
├── scripts/
│   └── check_data_quality.py        数据质量检查脚本
├── references/
│   ├── diagnose-8phases.md          diagnose 详细文档
│   ├── verify-6layers.md            verify 详细文档
│   ├── auto-fix-6steps.md           auto-fix 详细文档
│   └── goals.md                     Goal 定义
├── analysis/                        分析报告
└── tests/                           测试用例
```

---

## 🚀 快速开始

### 使用 diagnose

```bash
# 加载 Skill
@diagnosis-verification/SKILL.md

# 触发诊断
用户：水位数据异常，连续 3 小时未更新

# Claude 自动执行 8 Phase 诊断
```

### 使用 verify

```bash
# 加载 Skill
@diagnosis-verification/SKILL.md

# 验证输出
输入：预报输出

# verify Agent 执行 6 层验证
```

### 使用 auto-fix

```bash
# 加载 Skill
@diagnosis-verification/SKILL.md

# 基于诊断结果自动修复
输入：诊断报告

# auto-fix Agent 执行 6 Step 自动修复
```

---

## 🔧 实用脚本

### 数据质量检查

```bash
# 检查水位数据
python3 scripts/check_data_quality.py --type water_level

# 检查降雨预报
python3 scripts/check_data_quality.py --type rainfall_forecast

# 检查告警堆积
python3 scripts/check_data_quality.py --type alerts

# 综合检查（生成问题集）
python3 scripts/check_data_quality.py --type all --output problems.md
```

---

## 📚 参考文档

- `references/diagnose-8phases.md` — diagnose 详细文档
- `references/verify-6layers.md` — verify 详细文档
- `references/auto-fix-6steps.md` — auto-fix 详细文档
- `references/goals.md` — Goal 定义

---

## 💡 设计理念

基于两篇 Loop Engineering 文章的方法论：

1. **第一篇**：《Loop Engineering：从写代码到设计循环》
   - 五动作闭环：发现 → 交付 → 验证 → 持久化 → 调度
   - 六组件体系：Connectors + Automations + Skills + Worktrees + Sub Agents + State

2. **第二篇**：《Claude Code 官方 Loop 详解》
   - 四个交接点：检查（Skill）→ 停止（Goal）→ 等待（Loop）→ 权限
   - 渐进式委托：先交检查，再交停止，再交等待，最后才交决策

---

## 🤝 与其他 Skill 的协作

```
forecasting（预报）
    ↓
early-warning（预警）
    ↓
plan-generation（预案） ←→ simulation（预演）
    ↓
diagnosis-verification（诊断 → 验证 → 修复）
```

### 工作流

1. **问题诊断 + 修复**：
   ```
   diagnose → verify → auto-fix → verify → 发布
   ```

2. **输出验证**：
   ```
   verify-*-output → Goal → Claude 执行 → verify → 通过
   ```

---

## 📊 预期收益

| 指标 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 异常发现时间 | 天级 | 分钟级 | 天 → 分钟 |
| 诊断时间 | 2-3 天 | 48 分钟（8 Phase） | 2-3 天 → 48min |
| 修复时间 | 48 分钟（首次） | 15 分钟（知识库） | 48 → 15min |
| 人工介入次数 | 每次都要 | 0 次（到预发） | 全自动 |
| 假修复率 | 高（自证） | 低（6 层验证） | 大幅降低 |

---

## 📝 许可

MIT License

---

**创建时间**：2026-07-10  
**版本**：v1.0
