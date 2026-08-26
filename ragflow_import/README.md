# 桃曲坡水库知识库 RAGFlow 导入工具

## 环境准备

```bash
# 1. 创建 venv（Python 3.11+）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 确认 RAGFlow 运行中
curl http://localhost:9380/api/v1/datasets  # 应返回 JSON

# 3. 设置凭据（环境变量，不入库）
export RAGFLOW_EMAIL="736599796@qq.com"
export RAGFLOW_PASSWORD="你的密码"
```

## 命令序列

### 阶段 0 — 扫描 + 映射表

```bash
# 扫描语料，生成 out/mapping.csv
python -m corpus
# 人工审查 mapping.csv（重点：flood_event 列、skip_reason 列）
# 确认后继续
```

### 阶段 1 — 表格预处理（可选）

```bash
# 生成 .md / .qa.md 表格式产物
python -m tables

# 离线 VLM 识别（需人工复核）
python vision_extract.py --limit 2   # dry-run，先看两幅图
# 人工审查 out/vision/compare_report.md
# 确认数值正确后批准
python vision_extract.py --approve
```

### 阶段 2 — 建库（幂等）

```bash
# dry-run 检查
python run_setup.py --dry-run

# 正式建库（创建 dataset + 标签库 + metadata schema）
python run_setup.py

# 确认 out/setup_state.json 生成
```

### 阶段 3 — 导入（先导，后全量）

```bash
# 导入门槛：标签库已完成 parse（run_setup.py 最后一步）
# 先导：ds3 抽 5 个文件，验证 GraphRAG
python run_import.py --dataset ds3 --limit 5
# 人工抽查 RAGFlow Web UI：检索"2021年10月3日洪水"
# 确认 chunks 有图谱关系后继续

# 全量导入（无 --limit）
python run_import.py --apply --dataset ds3   # ds3 全量（含 GraphRAG，较慢）
python run_import.py --apply --dataset ds1   # ds1（含 GraphRAG + Raptor）
python run_import.py --apply --dataset ds2   # ds2
python run_import.py --apply --dataset ds4   # ds4
python run_import.py --apply --dataset ds5   # ds5（含 Raptor）
```

### 阶段 4 — 人工验收

```bash
python run_qc.py
# 审查 out/qc/report_*.md
# Q1-Q4 使用 use_kg=true，需图谱
# Q5-Q6 验证 meta_data_filter 硬过滤
```

## 人工门槛

| 门槛 | 位置 | 通过标准 |
|---|---|---|
| mapping.csv 审查 | `out/mapping.csv` | flood_event 列正确；skip_reason 无误 |
| VLM 批准 | `out/vision/approved.flag` | 人工确认库容表/泄流曲线数值正确 |
| 10% OCR 抽样 | `pdf_text_analysis/ocr_new/` | 随机抽 5 个文本，肉眼确认 quality 标注 |
| 导入门槛 | ds3 5 文件 pilot | 检索"2021年10月3日洪水"有图谱关系返回 |

## 故障排查

- **Login 失败 (401)**: 密码错误或 RSA 加密格式不匹配；`python -c "from ragflow_client import encrypt_password; print(encrypt_password('pass','/opt/git/ragflow/conf/public.pem'))"` 验证
- **create_dataset 400**: tenant 未配置 embedding 模型 → RAGFlow Web UI → 模型配置
- **parse 一直 running**: 重启 RAGFlow 容器；检查 `docker compose -f docker/docker-compose-base.yml logs deepdoc`
- **meta_data_filter 无效**: 运行 `python run_qc.py` 时观察错误信息；filter shape 见 spec §4.3
- **导入状态卡住**: 检查 `out/import_state.json` 的 `failed` 条目；删除对应 doc 后重跑
