#!/usr/bin/env python3
"""快速生成对比分析报告 — 复用已有OCR结果，不重新OCR"""
import os, sys, json, hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PDFS_DIR = Path("/home/scada/SmartTwinRes-skills/pdfs")
OUT_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis")
REPORT_DIR = Path("/home/scada/SmartTwinRes-skills/docs")
OCR_OUT_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/ocr_new")
REPAIR_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/repaired")

try:
    import fitz
except ImportError:
    fitz = None

try:
    import rarfile
    rarfile.UNRAR_TOOL = '/usr/bin/unrar'
except ImportError:
    rarfile = None

# ========== 工具函数 ==========

def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def get_size_str(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def safe_text(text, max_len=200):
    if not text: return ""
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text

# ========== 阶段1: 扫描文件 ==========
print("阶段1: 扫描文件...")
all_files = []
by_type = defaultdict(list)
md5_map = defaultdict(list)
total_size = 0

for root, dirs, files in os.walk(PDFS_DIR):
    for fname in files:
        fp = Path(root) / fname
        rel = str(fp.relative_to(PDFS_DIR))
        ext = fp.suffix.lower()
        size = fp.stat().st_size
        total_size += size
        entry = {"rel": rel, "ext": ext, "size": size, "size_str": get_size_str(size)}
        all_files.append(entry)
        by_type[ext].append(entry)
        if ext in (".pdf", ".docx", ".xlsx", ".xls", ".rar", ".zip", ".doc", ".wps"):
            try:
                md5 = file_md5(fp)
                entry["md5"] = md5
                md5_map[md5].append(rel)
            except:
                entry["md5"] = None

# 重复
duplicates = []
for md5, paths in md5_map.items():
    if len(paths) > 1:
        duplicates.append({"md5": md5, "count": len(paths), "paths": paths})

pdf_files = [f for f in all_files if f["ext"] == ".pdf"]
img_files = [f for f in all_files if f["ext"] in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")]
archive_files = [f for f in all_files if f["ext"] in (".rar", ".zip", ".7z")]

print(f"  共 {len(all_files)} 个文件，{len(pdf_files)} 个PDF，{len(img_files)} 个图片，{len(archive_files)} 个压缩包，{len(duplicates)} 组重复")

# ========== 阶段2: PDF分析 (使用PyMuPDF) ==========
print("\n阶段2: PDF分析...")
seen_md5 = set()
unique_pdfs = []
for f in pdf_files:
    m = f.get("md5", "")
    if m and m not in seen_md5:
        seen_md5.add(m)
        unique_pdfs.append(f["rel"])
    elif not m:
        unique_pdfs.append(f["rel"])

pdf_results = []
for i, rel in enumerate(unique_pdfs, 1):
    fp = PDFS_DIR / rel
    print(f"  [{i}/{len(unique_pdfs)}] {Path(rel).name}", end="")
    
    result = {
        "file": rel,
        "page_count": 0, "text_length": 0, "text_preview": "",
        "has_text_layer": False, "is_scanned": False, "is_damaged": False,
        "damage_details": "", "images_found": 0,
        "repair_attempted": False, "repair_success": False,
        "ocr_attempted": False, "ocr_text_length": 0,
    }
    
    if fitz:
        try:
            doc = fitz.open(str(fp))
            result["page_count"] = len(doc)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
            result["text_length"] = len(full_text)
            result["text_preview"] = safe_text(full_text, 300)
            result["has_text_layer"] = len(full_text.strip()) > 50
            result["is_scanned"] = not result["has_text_layer"]
            img_count = 0
            for page in doc:
                img_count += len(page.get_images())
            result["images_found"] = img_count
            doc.close()
            
            # 检查是否已有OCR结果
            stem = Path(rel).stem
            ocr_paths = list(OCR_OUT_DIR.glob(f"{stem}*_OCR.txt"))
            existing_ocr = [p for p in ocr_paths if p.exists()]
            if existing_ocr:
                result["ocr_attempted"] = True
                result["ocr_text_length"] = len(existing_ocr[0].read_text(encoding="utf-8"))
                result["ocr_saved_to"] = str(existing_ocr[0])
                result["ocr_found_existing"] = True
                print(f" 页={result['page_count']} 文本={result['text_length']} 扫描={result['is_scanned']} OCR已有={result['ocr_text_length']}字符")
            else:
                print(f" 页={result['page_count']} 文本={result['text_length']} 扫描={result['is_scanned']}")
                
        except Exception as e:
            result["is_damaged"] = True
            result["damage_details"] = str(e)
            print(f" ⚠️损坏: {str(e)[:60]}")
    else:
        print(" (无PyMuPDF)")
    
    pdf_results.append(result)

# ========== 阶段3: 压缩包分析 ==========
print("\n阶段3: 压缩包分析...")
archive_results = []
for f in archive_files:
    fp = PDFS_DIR / f["rel"]
    ext = f["ext"]
    print(f"  {Path(f['rel']).name} ({f['size_str']})", end="")
    
    result = {
        "file": f["rel"], "size": f["size_str"], "format": ext,
        "total_entries": 0, "pdf_count": 0, "image_count": 0, "other_count": 0,
        "contents": [], "error": ""
    }
    
    try:
        if ext == ".rar" and rarfile:
            rf = rarfile.RarFile(str(fp))
            for info in rf.infolist():
                entry = {"name": info.filename, "size": info.file_size}
                result["contents"].append(entry)
                ln = info.filename.lower()
                if ln.endswith(".pdf"): result["pdf_count"] += 1
                elif any(ln.endswith(e) for e in (".jpg",".jpeg",".png")): result["image_count"] += 1
                else: result["other_count"] += 1
            rf.close()
        elif ext == ".zip":
            import zipfile
            with zipfile.ZipFile(str(fp)) as zf:
                for info in zf.infolist():
                    entry = {"name": info.filename, "size": info.file_size}
                    result["contents"].append(entry)
                    ln = info.filename.lower()
                    if ln.endswith(".pdf"): result["pdf_count"] += 1
                    elif any(ln.endswith(e) for e in (".jpg",".jpeg",".png")): result["image_count"] += 1
                    else: result["other_count"] += 1
        result["total_entries"] = len(result["contents"])
        print(f" → {result['total_entries']}条目, {result['pdf_count']}PDF, {result['image_count']}图片")
    except Exception as e:
        result["error"] = str(e)
        print(f" ⚠️ {e}")
    
    archive_results.append(result)

# ========== 阶段4: 对比分析 ==========
print("\n阶段4: 对比分析...")

# 之前分析数据
PREV = {
    "total_unique_pdfs": 23, "text_extractable": 14,
    "scanned_no_text": 3, "corrupted_invalid": 2, "duplicate_dirs": 7,
    "scanned_files": ["大坝安全鉴定报告书2020.pdf", "桃曲坡水库大坝安全鉴定.pdf", "汛情专报_20211006.pdf"],
    "corrupted_files": ["桃曲坡水库安全设施建设工程（2026-6-1）.pdf", "桃曲坡水库数字孪生工程（2026-6-1）.pdf"],
    "previously_analyzed_docs": [
        "2026年桃曲坡水库防洪抢险应急预案(1).pdf",
        "2026年度桃曲坡水库汛期调度运用计划(2).pdf",
        "2026年桃曲坡水库调度规程(1)(1).pdf",
        "2026年桃曲坡水库大坝安全管理应急预案(1).pdf",
        "陕西省桃曲坡灌区水利工程管理范围及保护范围划界报告.pdf",
        "《桃曲坡等三座大坝安全评价报告》.pdf",
        "水情通报第161期.pdf",
        "重要水情快报（第121期）-总结预测.pdf",
        "关于转发_水利部办公厅关于切实做好渭河流域暴雨洪水防御工作的通知_的通知_陕水防明电_2021_7.pdf",
    ]
}

text_extractable = sum(1 for r in pdf_results if r.get("has_text_layer") and not r.get("is_damaged"))
scanned = [r for r in pdf_results if r.get("is_scanned") and not r.get("is_damaged")]
damaged = [r for r in pdf_results if r.get("is_damaged")]
repaired_count = sum(1 for r in pdf_results if r.get("repair_success"))
ocr_count = sum(1 for r in pdf_results if r.get("ocr_attempted") and r.get("ocr_text_length", 0) > 50)

# 重复浪费空间
dup_wasted = 0
for g in duplicates:
    paths = g["paths"]
    sizes = [(PDFS_DIR / p).stat().st_size for p in paths if (PDFS_DIR / p).exists()]
    if sizes:
        dup_wasted += sum(sizes) - sizes[0]

# 检查修复
for r in pdf_results:
    if r["is_damaged"]:
        fp = PDFS_DIR / r["file"]
        # 尝试用PyMuPDF修复
        if fitz:
            try:
                doc = fitz.open(str(fp))
                repair_out = REPAIR_DIR / f"repaired_{Path(r['file']).name}"
                doc.save(str(repair_out), garbage=4, deflate=True, clean=True)
                doc.close()
                if repair_out.stat().st_size > 100:
                    r["repair_attempted"] = True
                    r["repair_success"] = True
                    repaired_count += 1
                    print(f"  ✅ 修复: {Path(r['file']).name}")
            except:
                r["repair_attempted"] = True
                r["repair_success"] = False
                print(f"  ❌ 修复失败: {Path(r['file']).name}")

# 新发现的PDF
prev_names = {p.replace(".pdf","").replace("_","").replace("(","").replace(")","") for p in PREV["previously_analyzed_docs"]}
new_pdfs = []
for r in pdf_results:
    fname = Path(r["file"]).stem.replace("_","").replace(" ","").replace("(","").replace(")","")
    if not any(p in fname for p in prev_names):
        new_pdfs.append(r["file"])

# 对比条目
comparison_items = []
for r in pdf_results:
    fname = r["file"]
    was_analyzed = any(Path(p).stem.replace("_","") in fname.replace("_","").replace("/","") for p in PREV["previously_analyzed_docs"])
    was_scanned = any(Path(s).stem.replace("_","") in fname.replace("_","").replace("/","") for s in PREV["scanned_files"])
    was_corrupted = any(Path(c).stem.replace("_","") in fname.replace("_","").replace("/","") for c in PREV["corrupted_files"])
    
    now = "ok"
    if r["is_damaged"]:
        now = "repaired" if r.get("repair_success") else "damaged"
    elif r["is_scanned"]:
        now = "scanned+ocr" if r.get("ocr_attempted") else "scanned"
    
    prev = "not_analyzed"
    if was_corrupted: prev = "corrupted"
    elif was_scanned: prev = "scanned"
    elif was_analyzed: prev = "analyzed"
    
    change = "unchanged"
    if prev == "corrupted" and now == "repaired": change = "🟢 损坏→已修复"
    elif prev == "corrupted" and now == "damaged": change = "🔴 仍损坏"
    elif prev == "scanned" and now == "scanned+ocr": change = "🟡 扫描件→已OCR"
    elif prev == "not_analyzed": change = "🆕 新发现"
    
    comparison_items.append({"file": fname, "prev": prev, "now": now, "change": change, **r})
    if change != "unchanged":
        print(f"  {change}: {Path(fname).name}")

# ========== 阶段5: 生成报告 ==========
print("\n阶段5: 生成报告...")

lines = []
lines.append("# 桃曲坡水库 PDF 综合分析与对比报告")
lines.append("")
lines.append(f"**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"**分析工具**: PyMuPDF {fitz.version if fitz else 'N/A'} + Tesseract OCR + rarfile")
lines.append(f"**分析目录**: `{PDFS_DIR}`")
lines.append("")

# 一、总览
lines.append("---")
lines.append("## 一、总体统计")
lines.append("")
lines.append("| 指标 | 之前报告 (2026-08-03) | 本次分析 (当前) | 变化 |")
lines.append("|------|----------------------|----------------|------|")
lines.append(f"| 文件总数（含重复） | — | {len(all_files)} | — |")
prev_val = PREV['total_unique_pdfs']
cur_val = len(unique_pdfs)
diff = "—" if prev_val == cur_val else f"{prev_val}→{cur_val}"
lines.append(f"| 唯一 PDF 数（去重） | {prev_val} | {cur_val} | {diff} |")
prev_val = PREV['text_extractable']
cur_val = text_extractable
diff = "—" if prev_val == cur_val else f"{prev_val}→{cur_val}"
lines.append(f"| 文本可提取 | {prev_val} | {cur_val} | {diff} |")
prev_val = PREV['scanned_no_text']
cur_val = len(scanned)
diff = "—" if prev_val == cur_val else f"{prev_val}→{cur_val}"
lines.append(f"| 扫描件（无文本层） | {prev_val} | {cur_val} | {diff} |")
prev_val = PREV['corrupted_invalid']
cur_val = len(damaged)
diff = "—" if prev_val == cur_val else f"{prev_val}→{cur_val}"
lines.append(f"| 损坏/无效 | {prev_val} | {cur_val} | {diff} |")
lines.append(f"| 重复问题 | {PREV['duplicate_dirs']} 个目录 | {len(duplicates)} 组({sum(g['count'] for g in duplicates)}文件) | 文件级精确统计 |")
lines.append(f"| 图像文件 (JPG/PNG) | 未分析 | {len(img_files)} 个唯一 | 新增维度 |")
lines.append(f"| 压缩包 | 未分析 | {len(archive_results)} 个 | 新增维度 |")
lines.append(f"| 压缩包内 PDF | 未分析 | {sum(a['pdf_count'] for a in archive_results)} 个 | 新增维度 |")
lines.append(f"| PDF OCR 处理 | 未执行 | {ocr_count} 个 | 新增维度 |")
lines.append(f"| 损坏文件修复 | 未尝试 | {repaired_count} 成功 / {len(damaged)-repaired_count} 失败 | 新增维度 |")
lines.append(f"| 重复浪费空间 | 未统计 | {get_size_str(dup_wasted)} | 新增维度 |")
lines.append("")

# 二、文件类型分布
lines.append("---")
lines.append("## 二、文件类型分布")
lines.append("")
lines.append("| 类型 | 数量 | 说明 |")
lines.append("|------|:----:|------|")
for ext, count in sorted(by_type.items()):
    emoji = {"pdf":"📄", ".jpg":"🖼️", ".jpeg":"🖼️", ".png":"🖼️", ".rar":"📦", ".zip":"📦", ".7z":"📦", ".xls":"📊", ".xlsx":"📊", ".doc":"📝", ".docx":"📝", ".wps":"📝"}.get(ext, "📁")
    lines.append(f"| {emoji} `{ext}` | {count} | |")
lines.append("")

# 三、PDF详细分析
lines.append("---")
lines.append("## 三、PDF 详细分析")
lines.append("")
lines.append("| # | 文件 | 页数 | 文本(字符) | 图片 | 有文本 | 扫描件 | 损坏 | 修复 | OCR | 对比变化 |")
lines.append("|---|------|:----:|:----------:|:----:|:------:|:------:|:----:|:----:|:---:|:--------:|")

for i, r in enumerate(pdf_results, 1):
    short = Path(r["file"]).name
    pages = r.get("page_count", "?")
    tl = r.get("text_length", 0)
    im = r.get("images_found", 0)
    ht = "✅" if r.get("has_text_layer") else "❌"
    sc = "✅" if r.get("is_scanned") else "❌"
    dm = "⚠️" if r.get("is_damaged") else "❌"
    rp = "✅" if r.get("repair_success") else ("❌" if r.get("repair_attempted") else "—")
    oc = "✅" if r.get("ocr_attempted") and r.get("ocr_text_length",0) > 50 else "—"
    
    ch = "—"
    for c in comparison_items:
        if c["file"] == r["file"]:
            ch = c["change"]
            break
    
    lines.append(f"| {i} | {short} | {pages} | {tl} | {im} | {ht} | {sc} | {dm} | {rp} | {oc} | {ch} |")

lines.append("")

# 四、损坏文件修复
damaged_list = [r for r in pdf_results if r.get("is_damaged") or r.get("repair_attempted")]
if damaged_list:
    lines.append("---")
    lines.append("## 四、损坏文件修复结果")
    lines.append("")
    lines.append("| 文件 | 大小 | 损坏原因 | 修复结果 |")
    lines.append("|------|:----:|---------|:--------:|")
    for r in damaged_list:
        fname = Path(r["file"]).name
        size = ""
        for f in all_files:
            if f["rel"] == r["file"]:
                size = f["size_str"]; break
        reason = r.get("damage_details", r.get("error", "未知"))[:80]
        result = "✅ 修复成功" if r.get("repair_success") else "❌ 修复失败"
        lines.append(f"| {fname} | {size} | {reason} | {result} |")
    lines.append("")

# 五、OCR结果
ocr_pdfs = [r for r in pdf_results if r.get("ocr_attempted") and r.get("ocr_text_length", 0) > 10]
if ocr_pdfs:
    lines.append("---")
    lines.append("## 五、PDF OCR 结果")
    lines.append("")
    lines.append("| 文件 | OCR 文本长度 | 输出路径 |")
    lines.append("|------|:-----------:|---------|")
    for r in ocr_pdfs:
        lines.append(f"| {Path(r['file']).name} | {r['ocr_text_length']} | `{r.get('ocr_saved_to', 'N/A')}` |")
    lines.append("")

# 六、压缩包分析
if archive_results:
    lines.append("---")
    lines.append("## 六、压缩包内容分析")
    lines.append("")
    for a in archive_results:
        lines.append(f"### {Path(a['file']).name} ({a['size']})")
        lines.append("")
        lines.append(f"- 格式: {a['format']}")
        lines.append(f"- 总条目: {a['total_entries']}")
        lines.append(f"- PDF 文件: {a['pdf_count']}")
        lines.append(f"- 图片文件: {a['image_count']}")
        if a.get("error"):
            lines.append(f"- ⚠️ 错误: {a['error']}")
        # 列出PDF
        pdfs_in = [c for c in a.get("contents", []) if isinstance(c, dict) and c.get("name","").lower().endswith(".pdf")]
        if pdfs_in:
            lines.append("")
            lines.append("**包含的 PDF：**")
            for c in pdfs_in:
                fname = Path(c["name"]).name
                lines.append(f"- {fname} ({get_size_str(c.get('size',0))})")
        lines.append("")

# 七、重复文件
if duplicates:
    lines.append("---")
    lines.append("## 七、重复文件分析")
    lines.append("")
    lines.append(f"发现 **{len(duplicates)}** 组重复，共涉及 **{sum(g['count'] for g in duplicates)}** 个文件，")
    lines.append(f"浪费空间约 **{get_size_str(dup_wasted)}**。")
    lines.append("")
    lines.append("| 重复组 | 文件数 | 浪费空间 | 示例路径 |")
    lines.append("|:------:|:------:|:--------:|---------|")
    for idx, g in enumerate(duplicates[:10], 1):
        paths = g["paths"]
        wasted = 0
        for p in paths:
            fp = PDFS_DIR / p
            if fp.exists(): wasted += fp.stat().st_size
        fp0 = PDFS_DIR / paths[0]
        if fp0.exists(): wasted -= fp0.stat().st_size
        lines.append(f"| {idx} | {g['count']} | {get_size_str(wasted)} | {paths[0]}<br/>等{g['count']-1}个副本 |")
    lines.append("")

# 八、对比变化
lines.append("---")
lines.append("## 八、与之前分析的变化对比")
lines.append("")
lines.append("### 8.1 变化摘要")
lines.append("")
changes = [c for c in comparison_items if c["change"] != "unchanged"]
if changes:
    for c in changes:
        lines.append(f"- {c['change']}: {Path(c['file']).name}")
else:
    lines.append("无显著变化。")
lines.append("")

lines.append("### 8.2 详细对比")
lines.append("")
lines.append("| 对比维度 | 之前 (2026-08-03) | 当前 | 说明 |")
lines.append("|---------|:----------------:|:----:|:----:|")

compare_table = [
    ("唯一 PDF 数", str(PREV['total_unique_pdfs']), str(len(unique_pdfs)), "之前按文件名去重，当前按MD5"),
    ("文本可提取", str(PREV['text_extractable']), str(text_extractable), "PyMuPDF 文本层检测"),
    ("扫描件", str(PREV['scanned_no_text']), str(len(scanned)), "新增OCR处理"),
    ("损坏文件", str(PREV['corrupted_invalid']), str(len(damaged)), "新增修复尝试"),
    ("重复问题", f"{PREV['duplicate_dirs']}个目录", f"{len(duplicates)}组({sum(g['count'] for g in duplicates)}文件)", "文件级MD5精确统计"),
    ("图像文件", "未分析", str(len(img_files)), "新增维度"),
    ("压缩包", "未分析", str(len(archive_results)), "新增维度"),
    ("压缩包内PDF", "未分析", str(sum(a['pdf_count'] for a in archive_results)), "新增维度"),
    ("PDF修复", "未尝试", f"{repaired_count}成功/{len(damaged)-repaired_count}失败", "新增维度"),
    ("PDF OCR", "未执行", f"{ocr_count}个", "新增维度"),
]

for name, prev, cur, note in compare_table:
    lines.append(f"| {name} | {prev} | {cur} | {note} |")
lines.append("")

# 九、结论
lines.append("---")
lines.append("## 九、结论与建议")
lines.append("")
lines.append("### 9.1 核心发现")
lines.append("")

findings = []
if repaired_count > 0:
    findings.append(f"✅ 成功修复 {repaired_count} 个之前报告为损坏的 PDF 文件")
if damaged and repaired_count < len(damaged):
    findings.append(f"❌ 仍有 {len(damaged)-repaired_count} 个文件无法修复（需重新获取）")
if ocr_count > 0:
    findings.append(f"📄 对 {ocr_count} 个扫描件 PDF 执行了 OCR 文本提取")
if archive_results:
    findings.append(f"📦 分析了 {len(archive_results)} 个压缩包，内含 {sum(a['pdf_count'] for a in archive_results)} 个 PDF")
if duplicates:
    findings.append(f"🔁 发现 {len(duplicates)} 组重复文件，可释放 {get_size_str(dup_wasted)} 空间")

for f in findings:
    lines.append(f"- {f}")

lines.append("")
lines.append("### 9.2 建议")
lines.append("")
lines.append("1. **去重整理**：清理重复文件，释放空间")
lines.append("2. **压缩包提取**：解压 RAR/ZIP 中的 PDF 纳入知识库")
lines.append("3. **OCR 文本入库**：将新生成的 OCR 文本导入 RAG 知识库")
lines.append("4. **损坏文件处理**：对无法修复的文件联系数据源重新获取")
lines.append("5. **图像资料**：对关键图像（库容曲线、泄流曲线等）补充 OCR 后结构化入库")
lines.append("")

lines.append("---")
lines.append(f"*分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
lines.append(f"*分析脚本: analyze_fast.py*")
lines.append("")

report = "\n".join(lines)

# 保存
report_path = REPORT_DIR / "PDF综合分析与对比报告.md"
report_path.write_text(report, encoding="utf-8")
print(f"\n✅ 报告已生成: {report_path}")

# 简短摘要
print("\n" + "=" * 60)
print("  分析完成！")
print("=" * 60)
print(f"  📄 唯一PDF: {len(unique_pdfs)}")
print(f"  📝 文本可提取: {text_extractable}")
print(f"  🔍 扫描件: {len(scanned)}")
print(f"  ⚠️ 损坏: {len(damaged)}")
print(f"  ✅ 修复成功: {repaired_count}")
print(f"  📦 压缩包: {len(archive_results)} (含{sum(a['pdf_count'] for a in archive_results)}PDF)")
print(f"  🔁 重复: {len(duplicates)}组 ({get_size_str(dup_wasted)})")
print(f"  📄 报告: {report_path}")