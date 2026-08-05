# SmartTwinRes Skills — 智慧水利水库运行管理矩阵平台 Skill 集合

**版本**: 1.0
**更新日期**: 2026-07-11
**维护团队**: SmartTwinRes Team

---

## 📖 项目简介

**SmartTwinRes Skills** 是 [SmartTwinRes（智慧水利水库运行管理矩阵平台）](https://github.com/your-org/SmartTwinRes) 的 Claude Code Skill 集合，提供水库运行管理各领域的专业知识和自动化脚本支持。

本 Skill 集合基于 **Hermes Agent + Claude Code** 平台构建，覆盖水库调度全业务流程，包括：

- 🌧️ **预报** — 降雨预报、水情查询、汛限水位、气象预警
- 📋 **预案** — 调度预案生成、形势研判、方案对比
- 🎬 **预演** — 多方案对比预演、虚拟场景构建、结果智能解读
- ⚠️ **预警** — 早期预警、阈值监控、应急响应
- 🔍 **诊断验证** — 系统诊断、数据验证、问题排查

---

## 🎯 核心特性

### 1. **专业领域知识**
- 内置水库调度法规库（《防洪法》、《调度规程》、《防洪标准》等）
- 标准化的安全约束和合规性检查
- 领域特定的 Prompt 模板和工作流程

### 2. **数据库集成**
- 统一的数据库配置标准（`SRM_DB_*` 环境变量）
- 支持 MySQL 8.0 直接查询
- 自动连接池管理和超时控制

### 3. **自动化测试**
- 端到端测试框架（`test_skills.py`）
- 支持单个 Skill / 全部 Skill 测试
- Markdown 和 JSON 格式测试报告

### 4. **脚本工具集**
- 每个 Skill 配套独立的查询脚本
- 支持 SQL 直连和 API 调用两种模式
- 标准化的数据格式和错误处理

---

## 📦 Skill 清单

### 🌧️ forecasting（预报系统）

**描述**: 降雨预报、水情查询、汛限水位、气象预警

**核心功能**:
- 当前水位查询
- 未来24小时逐时降雨预报
- 汛限水位查询
- 气象预警查询
- 数据时效性检查

**文档**: [forecasting/SKILL.md](forecasting/SKILL.md)
**脚本**: [forecasting/scripts/](forecasting/scripts/)
**测试**: [forecasting/tests/](forecasting/tests/)

---

### 📋 plan-generation（预案生成）

**描述**: 调度预案、形势研判、方案对比

**核心功能**:
- 当前水情查询
- 调度预案生成
- 形势研判分析
- 多方案对比评估
- 法规符合性检查

**文档**: [plan-generation/SKILL.md](plan-generation/SKILL.md)
**脚本**: [plan-generation/scripts/](plan-generation/scripts/)
**测试**: [plan-generation/tests/](plan-generation/tests/)

---

### 🎬 simulation（预演模拟）

**描述**: 多方案对比预演、结果智能解读、虚拟场景构建、预演报告生成

**核心功能**:
- 多方案对比预演（防洪优先 / 综合平衡 / 兴利优先）
- 虚拟场景构建（假设降雨、自定义预演）
- 预演结果智能解读
- 敏感性分析（参数影响评估）
- 历史经验提取
- 预演报告自动生成

**版本**: 1.9.3

**文档**: [simulation/SKILL.md](simulation/SKILL.md)
**脚本**: [simulation/scripts/](simulation/scripts/)
**测试**: [simulation/tests/](simulation/tests/)

---

### ⚠️ early-warning（预警系统）

**描述**: 早期预警、阈值监控、应急响应

**核心功能**:
- 多级预警阈值监控
- 自动预警触发
- 预警消息推送
- 应急响应建议
- 预警历史分析

**文档**: [early-warning/SKILL.md](early-warning/SKILL.md)
**脚本**: [early-warning/scripts/](early-warning/scripts/)
**测试**: [early-warning/tests/](early-warning/tests/)

---

### 🧭 supervisor（四预智能体协同编排层）— 新增

**描述**: 四预智能体集群的编排层（Supervisor）：场景识别、DAG 编排、跨 skill 调度、结果仲裁、全局 State 持久化与断点续跑。

**状态**: v0.2.0 四场景（A/B/C/D）全部实测跑通（2026-08-05）

**核心功能**:
- 四类场景识别（A暴雨研判 / B大坝诊断 / C日常管控 / D应急）
- 场景 A 七步 DAG 一键编排（forecasting→diagnosis→inspection→simulation→plan-gen→仲裁→报告）
- SQLite 全局 State（事件/阶段结果持久化、断点续跑、HITL 检查点）
- 结果仲裁（方案 vs 仿真一致性、下泄 vs 安全泄量、风险等级取高）

**文档**: [supervisor/SKILL.md](supervisor/SKILL.md)
**落地状态**: [supervisor/README.md](supervisor/README.md)
**脚本**: [supervisor/scripts/](supervisor/scripts/)

> 背景：详见 [docs/多Agent集群方案评估与Supervisor落地.md](docs/多Agent集群方案评估与Supervisor落地.md) 与 [docs/四预智能体深入分析报告.md](docs/四预智能体深入分析报告.md)

---

### 🔍 diagnosis-verification（诊断验证）

**描述**: 系统诊断、数据验证、问题排查

**核心功能**:
- 数据质量检查
- 系统状态诊断
- 异常检测与定位
- 自动修复建议
- 验证报告生成

**文档**: [diagnosis-verification/SKILL.md](diagnosis-verification/SKILL.md)
**脚本**: [diagnosis-verification/scripts/](diagnosis-verification/scripts/)
**测试**: [diagnosis-verification/tests/](diagnosis-verification/tests/)

---

## 🚀 快速开始

### 1. 环境要求

**硬件**:
- CPU: 4核+
- 内存: 8GB+
- 磁盘: 50GB+

**软件**:
- Python 3.8+
- MySQL 8.0（SmartTwinRes 数据库）
- Redis 6.0+（可选，用于缓存）
- Claude Code（Claude AI 插件）
- Hermes Agent（本地 LLM 编排服务）

### 2. 数据库配置

**方式一：环境变量（推荐）**

```bash
# 编辑 shell 配置文件
cat >> ~/.bashrc << 'EOF'
# SmartTwinRes Skills 数据库配置
export SRM_DB_HOST=127.0.0.1
export SRM_DB_PORT=3306
export SRM_DB_NAME=powerelf_srm_yml
export SRM_DB_USER=root
export SRM_DB_PASSWORD='your_password'
EOF

source ~/.bashrc
```

**方式二：systemd 服务配置**

```ini
[Service]
Environment="SRM_DB_HOST=127.0.0.1"
Environment="SRM_DB_PORT=3306"
Environment="SRM_DB_NAME=powerelf_srm_yml"
Environment="SRM_DB_USER=root"
Environment="SRM_DB_PASSWORD=your_password"
```

**验证配置**:

```bash
# 检查环境变量
env | grep -E "SRM_DB_|POWERELF_DB_"

# 测试连接
mysql -h "$SRM_DB_HOST" -P "$SRM_DB_PORT" -u "$SRM_DB_USER" -p"$SRM_DB_PASSWORD" "$SRM_DB_NAME" -e "SELECT 1"
```

📖 **详细配置指南**: [DB-CONFIG-STANDARD.md](DB-CONFIG-STANDARD.md)

### 3. 目录结构

每个 Skill 遵循统一的目录结构：

```
<skill-name>/
├── SKILL.md              # Skill 核心文档（Prompt + 工作流）
├── db-config.md          # 数据库配置说明
├── scripts/              # Python 查询脚本
│   ├── query_*.py        # 数据查询脚本
│   └── ...
├── tests/                # 测试用例
│   ├── test-*.md         # 测试问题集
│   └── ...
├── references/           # 参考资料
│   └── *.md              # 参考文档
├── docs/                 # 额外文档
│   └── *.md              # 文档
├── models/               # 模型配置文件（如适用）
└── test-data-*.sql       # 测试数据脚本（如适用）
```

### 4. Claude Code 集成

**方式一：项目级配置**

在 Claude Code 项目设置中启用需要的 Skill：

```json
{
  "skills": {
    "enabled": ["forecasting", "plan-generation", "simulation"],
    "disabled": []
  }
}
```

**方式二：对话中手动调用**

在 Claude Code 对话中使用 `/skill` 命令：

```
/skill forecasting
/skill simulation
```

### 5. Hermes Agent 集成

所有 Skill 均通过 **Hermes Agent** 进行本地 LLM 编排：

```bash
# 检查 Hermes 状态
hermes status

# 测试 Skill
hermes chat -q "查询三岔水库当前水位" --skills forecasting
```

---

## 🧪 测试框架

### 运行所有测试

```bash
cd SmartTwinRes-skills
python3 test_skills.py --all --timeout 300
```

### 测试指定 Skill

```bash
# 测试 forecasting
python3 test_skills.py --skill forecasting --timeout 300

# 测试 simulation
python3 test_skills.py --skill simulation --timeout 300
```

### 运行单个测试用例

```bash
python3 test_skills.py --test-case F1
```

### 列出所有测试用例

```bash
python3 test_skills.py --list
```

### 生成测试报告

```bash
# Markdown 报告
python3 test_skills.py --all --output report.md

# JSON 报告
python3 test_skills.py --all --report-format json --output report.json
```

---

## 📚 使用示例

### 示例1：查询当前水位

**Forecasting Skill**:

```bash
# 使用查询脚本
python3 forecasting/scripts/query_water_level.py

# 通过 Hermes Agent
hermes chat -q "查询三岔水库当前水位" --skills forecasting
```

### 示例2：生成调度预案

**Plan-Generation Skill**:

```bash
hermes chat -q "根据当前情况生成一个调度预案" --skills plan-generation
```

### 示例3：多方案预演对比

**Simulation Skill**:

```bash
hermes chat -q "对比防洪优先和兴利优先两个方案" --skills simulation
```

### 示例4：敏感性分析

**Simulation Skill**:

```bash
hermes chat -q "如果降雨量增加到550mm，最高水位会怎样？" --skills simulation
```

---

## 🗂️ 项目结构

```
SmartTwinRes-skills/
├── README.md                      # 📖 本文件（中文说明）
├── DB-CONFIG-STANDARD.md          # 🗄️ 数据库环境变量配置标准
├── test_skills.py                 # 🧪 Skill 自动化测试框架
│
├── forecasting/                   # 🌧️ 预报 Skill
│   ├── SKILL.md
│   ├── db-config.md
│   ├── scripts/
│   ├── tests/
│   └── ...
│
├── plan-generation/               # 📋 预案 Skill
│   ├── SKILL.md
│   ├── db-config.md
│   ├── scripts/
│   ├── tests/
│   └── ...
│
├── simulation/                    # 🎬 预演 Skill
│   ├── SKILL.md
│   ├── db-config.md
│   ├── scripts/
│   ├── tests/
│   └── ...
│
├── early-warning/                 # ⚠️ 预警 Skill
│   ├── SKILL.md
│   ├── db-config.md
│   ├── scripts/
│   └── ...
│
└── diagnosis-verification/        # 🔍 诊断验证 Skill
    ├── SKILL.md
    ├── db-config.md
    ├── scripts/
    └── ...
```

---

## 🔧 数据库连接标准

### 环境变量优先级

```
SRM_DB_*  →  POWERELF_DB_*  →  默认值
（优先）     （兼容）        （兜底）
```

| 配置项 | 变量名 | 默认值 | 必填 |
|-------|--------|--------|------|
| 主机 | `SRM_DB_HOST` | `127.0.0.1` | 否 |
| 端口 | `SRM_DB_PORT` | `3306` | 否 |
| 数据库 | `SRM_DB_NAME` | `powerelf_srm_yml` | 否 |
| 用户 | `SRM_DB_USER` | - | **是** |
| 密码 | `SRM_DB_PASSWORD` | - | **是** |

### Python 实现

```python
import os

DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': os.getenv('SRM_DB_USER'),
    'password': os.getenv('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 30,
}
```

📖 **详细配置文档**: [DB-CONFIG-STANDARD.md](DB-CONFIG-STANDARD.md)

---

## 🛡️ 安全与合规

### 数据库安全
- ✅ 禁止硬编码数据库密码
- ✅ 强制从环境变量读取凭据
- ✅ 连接超时控制（10s）
- ✅ 读取超时控制（30s）
- ✅ UTF-8 字符集（utf8mb4）

### 法规引用

所有 Skill 输出必须引用以下法规标准：

| 场景 | 必须引用 |
|------|----------|
| 水位/安全评估 | 《防洪法》第41条 |
| 调度方案推荐 | 《三岔水库调度规程》 |
| 设计标准/安全等级 | GB 50201-2014《防洪标准》 |
| 大坝安全评估 | SL 210-2015《水库大坝安全评价导则》 |
| 洪水调度/防汛 | 《防汛条例》 |
| 预报/模型精度 | SL 61-2003《水文预报规范》 |
| 下游防护 | 《水库大坝安全管理条例》 |

### 安全约束

所有 Skill 必须遵守以下安全约束：

1. **不得编造数据**：所有数字必须来自数据库查询或 API 返回
2. **不得自动执行调度**：调度方案必须经用户确认后才能执行
3. **水位约束**：推荐水位不得超过汛限水位
4. **下泄约束**：推荐下泄不得超过下游安全泄量
5. **方案完整性**：每个预演必须包含完整的结果数据
6. **数据一致性**：入库过程、调度结果、曲线数据必须来自同一场洪水
7. **敏感数据保护**：数据库密码不得出现在对话中

---

## 🤝 贡献指南

### 新建 Skill 流程

1. **创建目录结构**

```bash
mkdir -p SmartTwinRes-skills/<skill-name>/{scripts,tests,references,docs}
```

2. **编写 SKILL.md**

遵循现有 Skill 的文档结构，包含：
- Skill 元数据（name, version, description）
- 意图识别表
- 工作流程说明
- 输出规范
- 数据库查询示例

3. **实现查询脚本**

```python
#!/usr/bin/env python3
"""<Skill Name> 查询脚本"""

import os
import pymysql
from pymysql.cursors import DictCursor

# 数据库配置（遵循 DB-CONFIG-STANDARD.md）
DB_CONFIG = {
    'host': os.getenv('SRM_DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('SRM_DB_PORT', '3306')),
    'user': os.getenv('SRM_DB_USER'),
    'password': os.getenv('SRM_DB_PASSWORD'),
    'database': os.getenv('SRM_DB_NAME', 'powerelf_srm_yml'),
    'charset': 'utf8mb4',
}

def query_data(query_type, **kwargs):
    """查询数据"""
    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor(DictCursor) as cursor:
            # 执行查询
            ...
    finally:
        connection.close()

if __name__ == "__main__":
    import sys
    result = query_data(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

4. **编写测试用例**

```bash
# 添加到 test_skills.py
SKILLS.append(SkillDefinition(
    id="<skill-name>",
    name="<Skill Name>",
    description="<描述>",
    skill_dir=SKILLS_DIR / "<skill-name>",
    enabled=True
))

# 添加测试用例
TESTS.append(TestCase(
    id="<ID>",
    skill_id="<skill-name>",
    description="<测试描述>",
    question="<测试问题>",
    expected_keywords=["关键词1", "关键词2"],
    timeout=120
))
```

5. **更新 DB-CONFIG-STANDARD.md**

在"已适配 Skill 清单"表中添加新 Skill：

| Skill | 文件路径 | 适配日期 | 状态 |
|-------|---------|---------|------|
| **<skill-name>** | `scripts/query_<name>.py` | YYYY-MM-DD | ✅ 已适配 |

6. **提交 Pull Request**

```bash
git add SmartTwinRes-skills/<skill-name>
git add test_skills.py
git add DB-CONFIG-STANDARD.md
git commit -m "feat(skill): add <skill-name> skill"
git push
```

### 代码规范

- **Python 代码**: 遵循 PEP 8，使用 `black` 格式化
- **文档**: 使用 Markdown，中英文均可
- **测试**: 每个 Skill 至少包含 2 个测试用例
- **数据库**: 统一使用 `SRM_DB_*` 环境变量命名空间

---

## 📊 测试覆盖率

当前测试覆盖率：

| Skill | 测试用例数 | 状态 |
|-------|----------|------|
| forecasting | 6 | ✅ 已验证 |
| plan-generation | 3 | 🟡 待验证 |
| simulation | 2 | 🟡 待验证 |
| early-warning | - | ⏳ 开发中 |
| diagnosis-verification | - | ⏳ 开发中 |

**运行测试**:
```bash
python3 test_skills.py --all
```

---

## 📖 参考文档

### Skill 详细文档
- [forecasting/SKILL.md](forecasting/SKILL.md)
- [plan-generation/SKILL.md](plan-generation/SKILL.md)
- [simulation/SKILL.md](simulation/SKILL.md)
- [early-warning/SKILL.md](early-warning/SKILL.md)
- [diagnosis-verification/SKILL.md](diagnosis-verification/SKILL.md)

### 数据库配置
- [DB-CONFIG-STANDARD.md](DB-CONFIG-STANDARD.md)

### 技能参考
- [Claude Code Skill 官方文档](https://docs.claude.com/en/docs/claude-code/skills)
- [Hermes Agent 文档](https://github.com/your-org/hermes-agent)

---

## 📝 更新日志

### v1.0 (2026-07-11)
- ✨ 初始版本
- 🌧️ forecasting Skill v1.0
- 📋 plan-generation Skill v1.0
- 🎬 simulation Skill v1.9.3
- ⚠️ early-warning Skill v1.0
- 🔍 diagnosis-verification Skill v1.0
- 🧪 自动化测试框架（test_skills.py）
- 📖 数据库配置标准（DB-CONFIG-STANDARD.md）

---

## 📄 许可证

**MIT License**

```
Copyright (c) 2026 SmartTwinRes Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 📞 联系我们

- **Issues**: [GitHub Issues](https://github.com/your-org/SmartTwinRes/issues)
- **Email**: smartwinres@example.com
- **维护团队**: SmartTwinRes Team

---

## 🙏 致谢

感谢以下开源项目的支持：

- [Claude Code](https://claude.ai/code) — AI 编程助手
- [Hermes Agent](https://github.com/your-org/hermes-agent) — 本地 LLM 编排服务
- [RuoYi-Vue-Pro](https://github.com/yangzongzhuan/RuoYi-Vue-Pro) — 快速开发平台
- [AirCity BIM](https://github.com/your-org/aircity) — BIM 数字孪生引擎

---

*最后更新时间: 2026-07-11*
