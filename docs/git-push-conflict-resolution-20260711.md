# Git 推送冲突解决方案

## 问题

推送被 GitHub 拒绝，原因是仓库历史中存在一个超过 100MB 的大文件：
- 文件：`forecasting/20260710_170809_e9d454`
- 大小：143.03 MB（超过 GitHub 100MB 限制）
- 位置：在提交 `62ef157` 中被删除，但历史记录中仍然存在

## 原因

GitHub 的 pre-receive hook 会扫描整个提交历史，即使文件已被删除，只要历史中存在超过 100MB 的文件，推送就会被拒绝。

## 解决方案

### 方案 A：使用 BFG Repo-Cleaner（推荐，最快）

```bash
# 1. 安装 BFG (需要 Java)
# https://rtyley.github.io/bfg-repo-cleaner/

# 2. 删除大文件历史
bfg --delete-files forecasting/20260710_170809_e9d454 .

# 3. 清理并推送
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push origin main
```

**时间**：约 5-10 分钟

---

### 方案 B：使用 git filter-repo（备选）

```bash
# 1. 安装 git-filter-repo
# https://github.com/newren/git-filter-repo

# 2. 备份仓库
cd ..
cp -r SmartTwinRes-skills SmartTwinRes-skills-backup
cd SmartTwinRes-skills

# 3. 删除大文件历史
git filter-repo --path forecasting/20260710_170809_e9d454 --invert-paths

# 4. 推送
git push origin main
```

**时间**：约 15-30 分钟

---

### 方案 C：重建分支（最简单，但会丢失部分历史）

如果您不需要保留完整的 git 历史，可以创建一个全新的分支：

```bash
# 1. 创建新分支，只包含我们的更改
git checkout -b clean-main
git cherry-pick b211e27 62ef157 4e27867

# 2. 删除大文件（如果存在）
git rm --cached forecasting/20260710_170809_e9d454 2>/dev/null || true

# 3. 推送新分支
git push origin clean-main:main --force
```

**时间**：约 2-3 分钟  
**缺点**：会丢失一些历史提交（3b03c55, 9123698 等）

---

### 方案 D：联系 GitHub Support

如果以上方法都失败，可以联系 GitHub Support 请求帮助清除大文件。

---

## 推荐操作

**推荐方案 A（BFG Repo-Cleaner）**，因为：
1. ✅ 最快（5-10 分钟）
2. ✅ 完全从历史中删除大文件
3. ✅ 保留完整的提交历史
4. ✅ 简单可靠

---

## 临时解决（如果您想继续工作）

在解决推送问题之前，您可以：

1. **继续本地开发**：所有更改已安全保存在本地
2. **创建新分支**：`git checkout -b feature/new-work`
3. **稍后处理推送**：使用上述任一方案解决问题后再推送

---

**维护**: SmartTwinRes Team  
**创建时间**: 2026-07-11
