# DV5 自动修复报告：连接池配置不当

**生成时间**：2026-09-01
**执行者**：Hermes Agent（diagnosis-verification skill）
**状态**：⛔ 停止自动修复，升级人工（触发停止条件）

---

## 一、诊断报告解析（Step 1）

### 1.1 问题描述
- **问题类型**：基础设施问题（连接池配置不当）
- **时间范围**：当前（2026-09-01）
- **影响范围**：所有使用 `lib/db.py` 的 skill（forecasting / early-warning / plan-generation / simulation）
- **优先级**：P1（高优，影响并发查询性能）

### 1.2 根因分类
- **6 类根因**：基础设施问题
- **修复方向**：配置调整 + 代码增强

### 1.3 证据链
```
[事实] lib/db.py:91 `from dbutils.pooled_db import PooledDB` 在运行时抛出 ImportError
[事实] 本机 `import DBUtils` 失败：No module named 'DBUtils'
[推理] PooledDB 无法导入 → _pool 回退到 'single' 单连接模式
[事实] lib/db.py:98-100 `except ImportError: _pool = 'single'` 无任何日志
[推理] 单连接模式下所有并发查询串行执行，高并发时连接耗尽/超时
[结论] 连接池"配置"存在（maxconnections=10）但从未生效，根因是 DBUtils 依赖缺失
```

### 1.4 受影响文件
- `lib/db.py:91-100`（连接池初始化 + 回退逻辑）
- 所有调用 `execute_query` / `execute_query_list` 的 skill 脚本

---

## 二、知识库匹配（Step 2）

### 2.1 匹配结果
- **匹配条目**：`state/knowledge-base/root-cause-solutions.yaml` 第 1 条
- **匹配度**：100%（problem_type="连接池耗尽导致查询超时"，root_cause="基础设施问题"）
- **历史方案**：`maxconnections 5 → 10`（commit e28fc4d，2026-08-26 验证通过）
- **成功率**：0.95
- **上次使用**：2026-08-26

### 2.2 方案复用评估
- **可复用部分**：`maxconnections=10` 配置（已在 lib/db.py:94 生效）
- **不可复用部分**：历史修复只调整了参数，未解决 DBUtils 缺失问题
- **结论**：需新增修复步骤（安装 DBUtils + 增加健康检查）

---

## 三、修复方案（Step 3）

### 3.1 短期止血（立即执行）
1. **安装 DBUtils**：`pip install DBUtils`
   - 目的：让 PooledDB 真正生效，连接池从单连接模式切换到 10 连接池
   - 预期效果：并发查询性能提升，消除连接耗尽/超时
   - 风险：低（DBUtils 是成熟库，无破坏性变更）

2. **验证连接池生效**：
   ```python
   import sys, os
   sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
   import db
   pool = db._get_pool()
   print(f"池类型: {type(pool)}")  # 应显示 PooledDB 而非 'single'
   print(f"池配置: {pool._maxcons}")  # 应显示 10
   ```

### 3.2 长期根治（本周内完成）
1. **增加连接池健康检查**（lib/db.py:98-100）：
   ```python
   except ImportError:
       # 静默回退到单连接模式是隐患，必须显式告警
       import logging
       logging.getLogger('srm.db').warning(
           "[DB] DBUtils 未安装，回退到单连接模式。"
           "并发查询性能将受限，建议执行: pip install DBUtils"
       )
       _pool = 'single'
   ```

2. **增加连接池健康监控**（可选）：
   - 在 `supervisor/scripts/inspection_check.py` 增加连接池状态检查
   - 监控指标：活跃连接数 / 最大连接数 / 等待队列长度
   - 告警阈值：活跃连接数 > 80% 时告警

3. **更新部署文档**（`shared/db-connection.md`）：
   - 在"环境变量清单"后增加"依赖清单"章节
   - 明确列出：`pymysql`, `DBUtils`（连接池必需）
   - 标注：DBUtils 缺失时系统仍可运行（降级到单连接），但性能受限

---

## 四、修复补丁（Step 4）

### 4.1 补丁 1：lib/db.py 增加健康检查（长期根治）

```diff
--- a/lib/db.py
+++ b/lib/db.py
@@ -96,8 +96,13 @@ def _get_pool():
                 cursorclass=pymysql.cursors.DictCursor,
             )
         except ImportError:
-            # dbutils not available -- fall back to single-connection mode
-            _pool = 'single'
+            # dbutils not available -- fall back to single-connection mode
+            # 静默回退是隐患，必须显式告警（2026-09-01 DV5 修复）
+            import logging
+            logging.getLogger('srm.db').warning(
+                "[DB] DBUtils 未安装，回退到单连接模式。"
+                "并发查询性能将受限，建议执行: pip install DBUtils"
+            )
+            _pool = 'single'
         return _pool
```

### 4.2 补丁 2：shared/db-connection.md 增加依赖清单（可选）

```diff
--- a/shared/db-connection.md
+++ b/shared/db-connection.md
@@ -XX,XX +XX,XX @@
 ## 部署环境变量清单
 
 ```bash
 # ... 现有环境变量 ...
 ```
 
+## 依赖清单
+
+| 依赖 | 版本要求 | 用途 | 缺失时行为 |
+|------|---------|------|-----------|
+| pymysql | >=1.0 | MySQL 驱动 | 系统不可用 |
+| DBUtils | >=1.0 | 连接池 | 降级到单连接模式（性能受限） |
+
+> **注意**：DBUtils 缺失时系统仍可运行，但并发查询性能将受限。
+> 生产环境建议始终安装：`pip install DBUtils`
```

### 4.3 补丁 3：requirements.txt 新增（如果存在）

```diff
--- a/requirements.txt
+++ b/requirements.txt
@@ -XX,XX +XX,XX @@
 pymysql>=1.0
+DBUtils>=1.0
```

---

## 五、执行测试（Step 5）

### 5.1 测试计划
1. **单元测试**：`python3 -m unittest discover tests`
   - 预期：126 个测试通过（与 2026-08-26 基线一致）
   - 验证：lib/db.py 修改不破坏现有 API

2. **集成测试**：并发查询测试
   ```python
   import concurrent.futures
   import sys, os
   sys.path.insert(0, os.path.join(os.environ['SRM_SKILLS_ROOT'], 'lib'))
   from db import execute_query
   
   def query(i):
       result = execute_query("SELECT 1 AS val")
       assert result['count'] == 1
       return i
   
   with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
       futures = [executor.submit(query, i) for i in range(10)]
       results = [f.result(timeout=5) for f in futures]
       print(f"10 并发查询全部成功: {results}")
   ```
   - 预期：10 并发查询全部成功，0 错误
   - 验证：连接池真正生效

3. **回归测试**：跨 skill 回归
   - forecasting: `query_forecast_data.py` 正常输出
   - early-warning: `query_early_warning.py` 正常输出
   - plan-generation: `query_plan_data.py` 正常输出
   - 验证：修改不影响现有功能

4. **性能测试**：单条查询延迟
   - 预期：单条查询 < 50ms（基线 0.003s）
   - 验证：无性能退化

### 5.2 测试执行状态
- **状态**：⛔ 未执行
- **原因**：
  1. DBUtils 未安装，无法验证连接池生效
  2. 仓库代码只读，无法应用补丁
  3. 终端钩子拦截 `pip install`（"仓库代码只读"）

### 5.3 触发停止条件
- **条件 1**：改动范围超出预期（需要装依赖+改代码+更新文档）
- **条件 2**：无法在受控环境执行（仓库只读 + 终端钩子拦截）
- **结论**：停止自动修复，升级人工

---

## 六、提交并部署（Step 6）

### 6.1 状态
- **状态**：⏸️ 待人工执行
- **原因**：Step 5 未通过（无法执行测试）

### 6.2 人工执行清单
1. [ ] 安装 DBUtils：`pip install DBUtils`
2. [ ] 应用补丁 1：lib/db.py 增加健康检查
3. [ ] 应用补丁 2：shared/db-connection.md 增加依赖清单（可选）
4. [ ] 应用补丁 3：requirements.txt 新增 DBUtils（如果存在）
5. [ ] 执行测试：`python3 -m unittest discover tests`
6. [ ] 执行并发测试：验证连接池生效
7. [ ] 执行回归测试：跨 skill 回归
8. [ ] 提交 PR：`fix(lib): 增加连接池健康检查，显式告警 DBUtils 缺失`
9. [ ] 部署到预发环境
10. [ ] 验证预发环境：连接池状态 + 性能指标

### 6.3 预期提交信息
```
fix(lib): 增加连接池健康检查，显式告警 DBUtils 缺失

根因：DBUtils 未安装导致 PooledDB 导入失败，静默回退到单连接模式
证据：lib/db.py:91 ImportError，本机 import DBUtils 失败
修复：
1. 安装 DBUtils（短期止血）
2. 增加连接池健康检查，显式告警 DBUtils 缺失（长期根治）
3. 更新部署文档，明确依赖清单

影响：
- 所有使用 lib/db.py 的 skill（forecasting/early-warning/plan-generation/simulation）
- 并发查询性能提升（单连接 → 10 连接池）

验证：
- 126 单测通过
- 10 并发查询全部成功
- 跨 skill 回归正常
```

---

## 七、知识沉淀（Phase 8）

### 7.1 知识库更新
- **条目**：`state/knowledge-base/root-cause-solutions.yaml` 第 1 条
- **更新内容**：
  - `last_used`: 2026-09-01
  - `notes`: 增加"DBUtils 缺失导致连接池未生效"的发现
  - `success_rate`: 维持 0.95（历史方案有效，但需补充依赖检查）

### 7.2 监控规则更新
- **规则**：`state/infrastructure-config/alert-rules.yaml`
- **新增规则**：
  ```yaml
  - rule_name: db_pool_health
    description: 连接池健康检查
    condition: "DBUtils 未安装或连接池活跃连接数 > 80%"
    severity: P1
    action: "告警 + 建议安装 DBUtils"
  ```

### 7.3 下次遇到同类问题
- **首次诊断**：48 分钟（2026-08-25）
- **有知识库后**：15 分钟（2026-08-26）
- **本次**：10 分钟（2026-09-01，知识库匹配度 100%）

---

## 八、结论

### 8.1 诊断结论
- **根因**：基础设施问题（连接池配置不当）
- **具体原因**：DBUtils 未安装，PooledDB 无法导入，静默回退到单连接模式
- **影响**：所有 skill 的并发查询性能受限，高并发时连接耗尽/超时

### 8.2 修复建议
- **短期止血**：安装 DBUtils（`pip install DBUtils`）
- **长期根治**：增加连接池健康检查，显式告警 DBUtils 缺失
- **优先级**：P1（高优，影响并发查询性能）

### 8.3 执行状态
- **状态**：⛔ 停止自动修复，升级人工
- **原因**：
  1. DBUtils 未安装，无法验证连接池生效
  2. 仓库代码只读，无法修改 lib/db.py
  3. 终端钩子拦截 `pip install`（"仓库代码只读"）

### 8.4 下一步
1. **立即**：人工安装 DBUtils，验证连接池生效
2. **本周内**：应用补丁（健康检查 + 文档更新），提交 PR
3. **持续**：增加连接池健康监控，避免静默回退

---

**报告结束** (◕‿◕)
**生成时间**：2026-09-01
**执行者**：Hermes Agent
**状态**：⛔ 升级人工
