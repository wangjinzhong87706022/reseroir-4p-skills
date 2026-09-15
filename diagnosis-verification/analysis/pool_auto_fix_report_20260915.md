# 连接池自动修复报告 — 2026-09-15

**生成时间**：2026-09-15
**执行者**：Hermes Agent（diagnosis-verification skill）
**状态**：✅ 验证通过，待提交

---

## Step 1：解析诊断报告

```json
{
  "root_cause": "基础设施问题",
  "root_cause_detail": "连接池配置不当 — DBUtils 导入路径错误（dbutils.exc 在 3.x 不存在）",
  "affected_files": ["lib/db.py:29"],
  "fix_type": "short_term",
  "solution": "dbutils.exc → dbutils.pooled_db 导入修复",
  "evidence": {
    "fact": "HEAD 的 db.py line 27 使用 `from dbutils.exc import TooManyConnectionsError`，但 DBUtils 3.2.0 无 dbutils.exc 模块",
    "reasoning": "ImportError 被捕获 → TooManyConnectionsError=() → 池满时 except () 永不匹配 → 连接泄漏",
    "conclusion": "基础设施问题 — 依赖导入路径与 DBUtils 版本不兼容"
  }
}
```

### 修复历史时间线

| 日期 | commit/事件 | 变更 |
|------|-----------|------|
| 2026-08-25 | e28fc4d | maxconnections 5→10 |
| 2026-09-01 | DV5 | DBUtils 静默回退显式告警 |
| 2026-09-02 | DV6 | DBUtils 3.2.0 持久安装到 venv |
| 2026-09-03 | pool_fix | 验证完成，无代码改动 |
| 2026-09-08 | — | 工作区: maxconnections 10→15 + blocking/mincached/maxcached |
| 2026-09-10 | DV7 | 验证通过（147 单测 + 15/20/30 并发压测） |
| 2026-09-12 | 96c9b94 | 提交: maxconnections=15 + blocking=True + mincached=2 + maxcached=5 |
| 2026-09-14 | 2502717 | blocking=True→False + 有界重试 30s（DBUtils 3.x blocking wait() 无超时） |
| 2026-09-15 | 工作区 | **dbutils.exc→dbutils.pooled_db 导入修复（本次验证对象）** |

---

## Step 2：知识库匹配

- **匹配条目**：`root-cause-solutions.yaml` RC-10
- **匹配度**：100%
- **历史方案**：见 Step 1 时间线
- **历史成功率**：0.95
- **预计修复时间**：5 分钟（有知识库）

---

## Step 3：修复方案

### 当前状态（验证对象）

lib/db.py 工作区唯一未提交变更：

```diff
-    from dbutils.exc import TooManyConnectionsError
+    # DBUtils 3.x: TooManyConnectionsError 定义在 dbutils.pooled_db（无 dbutils.exc 模块）
+    # DBUtils 1.x/2.x 兼容：旧版亦在 dbutils.pooled_db 中定义
+    from dbutils.pooled_db import TooManyConnectionsError
```

### 为什么这个修复必要

| 场景 | 修复前（dbutils.exc） | 修复后（dbutils.pooled_db） |
|------|---------------------|---------------------------|
| import 结果 | ImportError → `TooManyConnectionsError = ()` | 正常导入异常类 |
| 池满行为 | `except ()` 永不匹配 → 原始异常裸抛 | `except TooManyConnectionsError` 匹配 → 有界重试 |
| 连接泄漏 | 无法检测/告警 | 30s 超时后 RuntimeError 指向泄漏排查 |

### 配置参数（已提交，本次验证）

| 参数 | 值 | 来源 commit |
|------|---|-----------|
| maxconnections | 15 | 96c9b94 |
| blocking | False | 2502717 |
| mincached | 2 | 96c9b94 |
| maxcached | 5 | 96c9b94 |
| SRM_DB_POOL_WAIT_S | 30 (默认) | 2502717 |

---

## Step 4：修复补丁

**无需新补丁** — 工作区变更即为修复补丁（见 Step 3 diff）。

---

## Step 5：执行测试

### 5.1 单元测试
```
Ran 147 tests in 31.845s
OK (expected failures=1)
```

### 5.2 连接池状态验证
```
Pool type: PooledDB
maxconnections: 15
maxcached: 5
blocking: False
DBUtils: 3.2.0 (/opt/git/hermes-agent/venv/lib/python3.11/site-packages/dbutils/)
```

### 5.3 并发压测

| 并发数 | 结果 | 总耗时 | 最慢 | 状态 |
|--------|------|--------|------|------|
| 15 (= maxconnections) | 15/15 OK | 23.8ms | 20.0ms | ✅ |
| 20 (> maxconnections) | 20/20 OK | 25.9ms | 24.1ms | ✅ |
| 30 (>> maxconnections) | 30/30 OK | 128.5ms | 119.9ms | ✅ |

> 30 并发超过 maxconnections=15 时，有界重试机制生效（排队等待，非报错）。

### 5.4 跨 skill 回归

| Skill | 查询 | 结果 | 耗时 | 状态 |
|-------|------|------|------|------|
| forecasting | current_water_level | rz=462.447, tm=2026-09-15 13:00 | — | ✅ |
| early-warning | unconfirmed alerts | count=0 | — | ✅ |
| plan-generation | current_water_level | rz=462.447 | — | ✅ |
| simulation | current_water_level | rz=462.447 | — | ✅ |
| lib 直连 | 水位/降雨/告警/设备/渗压 | 5 域正常 | 0.8~178.6ms | ✅ |

### 5.5 测试总结

| 测试项 | 通过标准 | 实际结果 | 状态 |
|--------|---------|---------|------|
| 单元测试 | 全部通过 | 147 OK | ✅ |
| PooledDB 激活 | 非 'single' | PooledDB, maxconnections=15 | ✅ |
| 15 并发 | 15/15 0 错误 | 15/15 OK | ✅ |
| 20 并发 | 20/20 0 错误 | 20/20 OK | ✅ |
| 30 并发 | 30/30 0 错误 | 30/30 OK | ✅ |
| 跨 skill 回归 | 4 skill 均正常 | 全部正常 | ✅ |
| 性能 | < 5s | 0.8~178.6ms | ✅ |

---

## Step 6：提交并部署

### 6.1 提交清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `lib/db.py` | 3 行修改 | dbutils.exc→dbutils.pooled_db 导入修复（+2 行注释） |
| `shared/db-connection.md` | 4 行修改 | 连接池文档同步（maxconnections 10→15 + 池满行为说明） |
| `diagnosis-verification/state/knowledge-base/root-cause-solutions.yaml` | +14 行 | RC-10 复诊记录 |

### 6.2 建议提交信息

```
fix(db): DBUtils 3.x 导入路径修复 + 连接池文档同步

根因：dbutils.exc 在 DBUtils 3.x 不存在，ImportError 被捕获后
TooManyConnectionsError=() 导致池满时 except 永不匹配，
有界重试机制失效，连接泄漏无法检测。

修复：
1. lib/db.py: from dbutils.exc → dbutils.pooled_db（3.x/1.x/2.x 兼容）
2. shared/db-connection.md: maxconnections 10→15 + 池满行为文档
3. 知识库: RC-10 复诊记录

验证：
- 147 单测通过
- 15/20/30 并发压测全部通过（23.8/25.9/128.5ms）
- 跨 skill 回归正常（forecasting/early-warning/plan-generation/simulation）
- PooledDB 激活: maxconnections=15, maxcached=5, blocking=False
```

### 6.3 部署注意事项
- 无代码逻辑变更，仅 import 路径修正 + 文档更新
- 部署后验证命令：`python3 -c "import sys; sys.path.insert(0,'lib'); from db import get_connection; c=get_connection(); c.close(); print('pool OK')"`

---

## 剩余风险 / 后续建议

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P2 | 连接池健康监控 | 活跃连接数 > 80% maxconnections 时告警 |
| P2 | requirements.txt | 加入 `DBUtils>=3.0` 防 venv 重建丢失 |
| P3 | 池满集成测试 | 模拟连接泄漏场景，验证 RuntimeError 正确抛出 |

---

**报告结束**
**状态**：✅ 验证通过，待提交
