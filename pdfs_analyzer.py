#!/usr/bin/env python3
"""
桃曲坡水库 PDF 综合分析脚本
============================
使用 PyMuPDF 对 pdfs/ 下的所有文件进行全面分析：
  - PDF 分析（文本提取、扫描件识别、OCR、损坏修复）
  - 图像文件 OCR（JPG/PNG）
  - 压缩包（RAR/ZIP）内文件清单
  - 对比之前分析结果
"""

import os, sys, json, hashlib, shutil, textwrap, re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Optional

# ============================================================
# 依赖导入（带降级处理）
# ============================================================
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import rarfile
    rarfile.UNRAR_TOOL = '/usr/bin/unrar'
except ImportError:
    rarfile = None

# pdfplumber 作为备用
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# ============================================================
# 配置
# ============================================================
PDFS_DIR = Path("/home/scada/SmartTwinRes-skills/pdfs")
OUT_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis")  # 已有输出
REPORT_DIR = Path("/home/scada/SmartTwinRes-skills/docs")
OCR_OUT_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/ocr_new")
REPAIR_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/repaired")
EXTRACT_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/extracted")

for d in [OCR_OUT_DIR, REPAIR_DIR, EXTRACT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 之前分析报告中的已知结果（用于对比）
PREVIOUS_ANALYSIS = {
    "total_unique_pdfs": 23,
    "text_extractable": 14,
    "scanned_no_text": 3,
    "corrupted_invalid": 2,
    "duplicate_dirs": 7,
    "extracted_text_size_chars": 230000,
    "knowledge_rules": "200+",
    "data_elements": "150+",
    "scanned_files": [
        "大坝安全鉴定报告书2020.pdf",
        "桃曲坡水库大坝安全鉴定.pdf",
        "汛情专报_20211006.pdf"
    ],
    "corrupted_files": [
        "桃曲坡水库安全设施建设工程（2026-6-1）.pdf",
        "桃曲坡水库数字孪生工程（2026-6-1）.pdf"
    ],
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

# ============================================================
# 工具函数
# ============================================================

def file_md5(path: Path) -> str:
    """计算文件 MD5 用于去重"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_text(text: str, max_len: int = 200) -> str:
    """截断并清理文本"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def get_file_size_str(path_or_size) -> str:
    if isinstance(path_or_size, (int, float)):
        size = path_or_size
    else:
        size = path_or_size.stat().st_size
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ============================================================
# 阶段 1：扫描文件清单
# ============================================================

def scan_all_files() -> dict:
    """扫描 pdfs/ 下所有文件，识别类型、去重、计算哈希"""
    results = {
        "scan_time": datetime.now().isoformat(),
        "root_dir": str(PDFS_DIR),
        "total_size_total": "",
        "files": [],
        "by_type": defaultdict(list),
        "md5_map": defaultdict(list),  # md5 -> [paths]
        "duplicates": [],
        "summary": {}
    }

    total_size = 0
    for root, dirs, files in os.walk(PDFS_DIR):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(PDFS_DIR)
            ext = fpath.suffix.lower()
            size = fpath.stat().st_size
            total_size += size

            entry = {
                "rel_path": str(rel),
                "abs_path": str(fpath),
                "ext": ext,
                "size": size,
                "size_str": get_file_size_str(fpath),
            }

            # 计算 MD5 用于去重
            if ext in (".pdf", ".docx", ".xlsx", ".xls", ".rar", ".zip", ".doc", ".wps"):
                try:
                    entry["md5"] = file_md5(fpath)
                    results["md5_map"][entry["md5"]].append(str(rel))
                except Exception:
                    entry["md5"] = None

            results["files"].append(entry)
            results["by_type"][ext if ext else "(no_ext)"].append(entry)

    # 检测重复
    for md5, paths in results["md5_map"].items():
        if len(paths) > 1:
            results["duplicates"].append({
                "md5": md5,
                "count": len(paths),
                "paths": paths
            })

    results["total_size_total"] = get_file_size_str(total_size) if total_size > 0 else "0B"
    results["summary"]["total_files"] = len(results["files"])
    results["summary"]["total_size"] = results["total_size_total"]
    results["summary"]["unique_by_md5"] = len(results["md5_map"])
    results["summary"]["duplicate_groups"] = len(results["duplicates"])
    results["summary"]["file_types"] = {k: len(v) for k, v in results["by_type"].items()}

    return results


# ============================================================
# 阶段 2：PDF 分析（PyMuPDF + OCR + 修复）
# ============================================================

def analyze_pdf_with_pymupdf(filepath: Path) -> dict:
    """使用 PyMuPDF 分析单个 PDF，返回详细结果"""
    result = {
        "file": str(filepath.relative_to(PDFS_DIR)),
        "status": "ok",
        "page_count": 0,
        "has_text_layer": False,
        "text_length": 0,
        "text_preview": "",
        "is_scanned": False,
        "is_damaged": False,
        "damage_details": "",
        "repair_attempted": False,
        "repair_success": False,
        "ocr_attempted": False,
        "ocr_text_length": 0,
        "ocr_text_preview": "",
        "metadata": {},
        "images_found": 0,
        "tables_found": 0,
        "error": ""
    }

    if fitz is None:
        result["status"] = "error"
        result["error"] = "PyMuPDF not installed"
        return result

    try:
        doc = fitz.open(str(filepath))
    except Exception as e:
        result["status"] = "damaged"
        result["is_damaged"] = True
        result["damage_details"] = str(e)
        result["error"] = str(e)
        return result

    try:
        result["page_count"] = len(doc)
        result["metadata"] = {k: str(v) for k, v in doc.metadata.items() if v}

        # 提取文本
        full_text = ""
        for page in doc:
            full_text += page.get_text()

        result["text_length"] = len(full_text)
        result["text_preview"] = safe_text(full_text, 500)

        # 判断是否有文本层
        if len(full_text.strip()) > 50:
            result["has_text_layer"] = True
            result["is_scanned"] = False
        else:
            result["has_text_layer"] = False
            result["is_scanned"] = True

        # 统计图片数量
        img_count = 0
        for page in doc:
            img_count += len(page.get_images())
        result["images_found"] = img_count

        doc.close()
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        try:
            doc.close()
        except Exception:
            pass

    return result


def try_repair_pdf(filepath: Path) -> Optional[Path]:
    """尝试修复损坏的 PDF 文件"""
    repair_out = REPAIR_DIR / f"repaired_{filepath.stem}{filepath.suffix}"
    if repair_out.exists():
        return repair_out

    try:
        # 方法 1: 用 PyMuPDF 的 repair 能力
        if fitz:
            try:
                doc = fitz.open(str(filepath))
                # 如果能打开，尝试保存为修复版本
                doc.save(str(repair_out), garbage=4, deflate=True, clean=True)
                doc.close()
                if repair_out.stat().st_size > 100:
                    return repair_out
            except Exception:
                pass

        # 方法 2: 直接用 pdfplumber 尝试
        if pdfplumber:
            try:
                with pdfplumber.open(str(filepath)) as pdf:
                    text = ""
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t
                    if len(text.strip()) > 50:
                        # 写出文本
                        txt_out = REPAIR_DIR / f"{filepath.stem}_extracted.txt"
                        txt_out.write_text(text, encoding="utf-8")
                        return txt_out
            except Exception:
                pass

        # 方法 3: 尝试二进制修复（去除损坏的 PDF 尾部垃圾）
        try:
            raw = filepath.read_bytes()
            # 找到最后一个 %%EOF
            last_eof = raw.rfind(b"%%EOF")
            if last_eof > 0:
                # 可能还有更多内容，尝试找倒数第二个
                second_eof = raw.rfind(b"%%EOF", 0, last_eof - 1)
                if second_eof > 0:
                    # 尝试截断到第二个 EOF
                    repair_out.write_bytes(raw[:second_eof + 5])
                    # 验证
                    try:
                        doc = fitz.open(str(repair_out))
                        doc.close()
                        return repair_out
                    except Exception:
                        pass
        except Exception:
            pass

    except Exception as e:
        print(f"   修复失败 {filepath.name}: {e}")

    return None


def ocr_pdf_page(filepath: Path, page_num: int = 0, dpi: int = 300) -> str:
    """对 PDF 单页执行 OCR（使用 pytesseract）"""
    if fitz is None or pytesseract is None:
        return ""

    try:
        doc = fitz.open(str(filepath))
        if page_num >= len(doc):
            doc.close()
            return ""
        page = doc[page_num]
        # 渲染为图片
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # OCR
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        doc.close()
        return text
    except Exception as e:
        return f"[OCR Error: {e}]"


def ocr_full_pdf(filepath: Path, dpi: int = 300, max_pages: int = 50) -> str:
    """对完整 PDF 进行 OCR"""
    if fitz is None or pytesseract is None:
        return ""

    all_text = []
    try:
        doc = fitz.open(str(filepath))
        total = min(len(doc), max_pages)
        for i in range(total):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            all_text.append(f"--- Page {i+1} ---\n{text}")
            sys.stdout.write(f"\r  OCR 进度: {i+1}/{total} 页")
            sys.stdout.flush()
        doc.close()
    except Exception as e:
        all_text.append(f"[OCR Error: {e}]")

    print()
    return "\n\n".join(all_text)


def analyze_all_pdfs(file_scan: dict) -> list:
    """分析所有 PDF 文件"""
    pdf_files = [
        Path(f["abs_path"]) for f in file_scan["files"]
        if f["ext"] == ".pdf"
    ]

    # 去重（按 MD5）
    seen_md5 = set()
    unique_pdfs = []
    for fp in pdf_files:
        if file_md5(fp) not in seen_md5:
            seen_md5.add(file_md5(fp))
            unique_pdfs.append(fp)

    results = []
    total = len(unique_pdfs)
    print(f"\n{'='*60}")
    print(f"阶段 2：PDF 分析（共 {total} 个唯一 PDF）")
    print(f"{'='*60}")

    for i, fpath in enumerate(unique_pdfs, 1):
        print(f"\n[{i}/{total}] 分析: {fpath.relative_to(PDFS_DIR)}")
        result = analyze_pdf_with_pymupdf(fpath)

        if result["is_damaged"]:
            print(f"  ⚠️  损坏: {result['damage_details']}")
            print(f"  → 尝试修复...")
            repaired = try_repair_pdf(fpath)
            if repaired:
                result["repair_attempted"] = True
                result["repair_success"] = True
                result["repaired_path"] = str(repaired)
                print(f"  ✅ 修复成功: {repaired.name}")
                # 重新分析修复后的文件
                repaired_result = analyze_pdf_with_pymupdf(repaired)
                result["repaired_analysis"] = repaired_result
            else:
                result["repair_attempted"] = True
                result["repair_success"] = False
                print(f"  ❌ 修复失败")

        if result["is_scanned"] and not result["is_damaged"]:
            print(f"  📄 扫描件（无文本层），执行 OCR...")
            ocr_text = ocr_full_pdf(fpath, dpi=300)
            result["ocr_attempted"] = True
            result["ocr_text_length"] = len(ocr_text)
            result["ocr_text_preview"] = safe_text(ocr_text, 500)

            # 保存 OCR 结果
            ocr_name = f"{fpath.stem}_OCR.txt"
            ocr_path = OCR_OUT_DIR / ocr_name
            ocr_path.write_text(ocr_text, encoding="utf-8")
            result["ocr_saved_to"] = str(ocr_path)
            print(f"  ✅ OCR 完成: {len(ocr_text)} 字符，保存至 {ocr_path.name}")

        print(f"  页数: {result['page_count']}, 文本: {result['text_length']} 字符, "
              f"图片: {result['images_found']}, 扫描件: {result['is_scanned']}")
        results.append(result)

    return results


# ============================================================
# 阶段 3：图像 OCR（JPG/PNG）
# ============================================================

def ocr_image_file(filepath: Path) -> str:
    """对单个图像执行 OCR"""
    if pytesseract is None or Image is None:
        return ""
    try:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return text
    except Exception as e:
        return f"[Image OCR Error: {e}]"


def analyze_images(file_scan: dict) -> list:
    """分析所有图像文件 — 跳过明显是照片的文件（目录名含"照片""洪水""泄洪"等）"""
    img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    img_files = [
        Path(f["abs_path"]) for f in file_scan["files"]
        if f["ext"] in img_exts
    ]

    # 去重
    seen_md5 = set()
    unique_imgs = []
    for fp in img_files:
        m = file_md5(fp)
        if m not in seen_md5:
            seen_md5.add(m)
            unique_imgs.append(fp)

    # 跳过明显是洪水照片的目录
    skip_dirs = {"照片", "洪水", "泄洪", "photo", "photos", "image", "images", "现场"}
    skip_keywords = {"洪水来势", "深夜泄洪", "清理", "抢险", "雨夜", "拉网式", "及时封锁",
                     "驱离", "疏通", "雨中", "高边坡", "过程线", "微信图片", "及时排查",
                     "洪水过程线", "5B4A", "2.1", "6.JPG", "7.JPG"}
    
    def is_photo(fp: Path) -> bool:
        rel = str(fp.relative_to(PDFS_DIR)).lower()
        # 检查目录名
        for part in fp.parts:
            if any(s in part for s in skip_dirs):
                return True
        # 检查文件名关键词
        fname = fp.stem.lower()
        for kw in skip_keywords:
            if kw.lower() in fname or kw.lower() in rel:
                return True
        # 大文件（>3MB）通常是照片
        if fp.stat().st_size > 3 * 1024 * 1024:
            return True
        return False

    results = []
    total = len(unique_imgs)
    meaningful = [fp for fp in unique_imgs if not is_photo(fp)]
    skipped = total - len(meaningful)
    print(f"\n{'='*60}")
    print(f"阶段 3：图像 OCR（共 {total} 个唯一图像，跳过 {skipped} 个照片，处理 {len(meaningful)} 个文档类图像）")
    print(f"{'='*60}")

    for i, fpath in enumerate(meaningful, 1):
        print(f"[{i}/{len(meaningful)}] OCR: {fpath.relative_to(PDFS_DIR)} ({get_file_size_str(fpath)})")
        text = ocr_image_file(fpath)
        length = len(text.strip())
        preview = safe_text(text, 200)

        result = {
            "file": str(fpath.relative_to(PDFS_DIR)),
            "size": get_file_size_str(fpath),
            "ocr_text_length": length,
            "ocr_text_preview": preview,
        }

        if length > 10:
            ocr_name = f"{fpath.stem}_OCR.txt"
            ocr_path = OCR_OUT_DIR / ocr_name
            ocr_path.write_text(text, encoding="utf-8")
            result["ocr_saved_to"] = str(ocr_path)
            print(f"  ✅ 识别到 {length} 字符，保存至 {ocr_path.name}")
        else:
            print(f"  ⚠️  未识别到有效文本 ({length} 字符)")

        results.append(result)

    return results


# ============================================================
# 阶段 4：压缩包分析
# ============================================================

def analyze_archives(file_scan: dict) -> list:
    """分析压缩包内容"""
    archive_exts = {".rar", ".zip", ".7z"}
    archive_files = [
        Path(f["abs_path"]) for f in file_scan["files"]
        if f["ext"] in archive_exts
    ]

    results = []
    print(f"\n{'='*60}")
    print(f"阶段 4：压缩包分析（共 {len(archive_files)} 个）")
    print(f"{'='*60}")

    for fpath in archive_files:
        ext = fpath.suffix.lower()
        print(f"\n分析: {fpath.relative_to(PDFS_DIR)} ({get_file_size_str(fpath)})")

        result = {
            "file": str(fpath.relative_to(PDFS_DIR)),
            "size": get_file_size_str(fpath),
            "format": ext,
            "contents": [],
            "pdf_count": 0,
            "image_count": 0,
            "other_count": 0,
            "total_entries": 0,
            "error": ""
        }

        try:
            if ext == ".rar" and rarfile:
                rf = rarfile.RarFile(str(fpath))
                for info in rf.infolist():
                    entry = {
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                    }
                    result["contents"].append(entry)
                    lname = info.filename.lower()
                    if lname.endswith(".pdf"):
                        result["pdf_count"] += 1
                    elif any(lname.endswith(e) for e in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")):
                        result["image_count"] += 1
                    else:
                        result["other_count"] += 1
                rf.close()

            elif ext == ".zip":
                import zipfile
                with zipfile.ZipFile(str(fpath)) as zf:
                    for info in zf.infolist():
                        entry = {
                            "name": info.filename,
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                        }
                        result["contents"].append(entry)
                        lname = info.filename.lower()
                        if lname.endswith(".pdf"):
                            result["pdf_count"] += 1
                        elif any(lname.endswith(e) for e in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")):
                            result["image_count"] += 1
                        else:
                            result["other_count"] += 1

            elif ext == ".7z":
                # 用 7z 命令行
                import subprocess
                p = subprocess.run(
                    ["7z", "l", str(fpath)],
                    capture_output=True, text=True, timeout=60
                )
                for line in p.stdout.split("\n"):
                    result["contents"].append({"line": line.strip()})
                # 简单统计
                pdf_count = p.stdout.lower().count(".pdf")
                img_count = sum(
                    p.stdout.lower().count(e) for e in (".jpg", ".jpeg", ".png")
                )
                result["pdf_count"] = pdf_count
                result["image_count"] = img_count
                result["other_count"] = len(result["contents"]) - pdf_count - img_count

            result["total_entries"] = len(result["contents"])
            print(f"  总条目: {result['total_entries']}, PDF: {result['pdf_count']}, "
                  f"图片: {result['image_count']}, 其他: {result['other_count']}")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ⚠️  分析失败: {e}")

        results.append(result)

    return results


# ============================================================
# 阶段 5：对比分析
# ============================================================

def compare_with_previous(
    file_scan: dict,
    pdf_results: list,
    image_results: list,
    archive_results: list
) -> dict:
    """与之前分析结果进行对比，生成差异报告"""
    print(f"\n{'='*60}")
    print(f"阶段 5：与之前分析结果对比")
    print(f"{'='*60}")

    # 当前分析汇总
    # 唯一 PDF 文件（去重后）
    pdf_files = [f for f in file_scan["files"] if f["ext"] == ".pdf"]
    seen_md5 = {}
    unique_pdf_files = []
    for f in pdf_files:
        m = f.get("md5", "")
        if m and m not in seen_md5:
            seen_md5[m] = f["rel_path"]
            unique_pdf_files.append(f)
        elif not m:
            unique_pdf_files.append(f)

    # 文本可提取的 PDF
    text_extractable = sum(1 for r in pdf_results if r.get("has_text_layer") and not r.get("is_damaged"))
    scanned = [r for r in pdf_results if r.get("is_scanned") and not r.get("is_damaged")]
    damaged = [r for r in pdf_results if r.get("is_damaged")]

    # 新发现的
    prev_analyzed_names = {p.replace(".pdf", "").replace("_", "") for p in PREVIOUS_ANALYSIS["previously_analyzed_docs"]}
    newly_discovered_pdfs = []
    for f in unique_pdf_files:
        fname = Path(f["rel_path"]).stem.replace("_", "").replace(" ", "")
        if not any(p in fname for p in prev_analyzed_names):
            # 进一步检查
            newly_discovered_pdfs.append(f["rel_path"])

    # 修复情况
    repaired_count = sum(1 for r in pdf_results if r.get("repair_success"))
    repair_failed = sum(1 for r in pdf_results if r.get("repair_attempted") and not r.get("repair_success"))

    # OCR 情况
    ocr_new = sum(1 for r in pdf_results if r.get("ocr_attempted") and r.get("ocr_text_length", 0) > 50)
    image_ocr = sum(1 for r in image_results if r.get("ocr_text_length", 0) > 10)

    # 压缩包内容
    total_archive_entries = sum(a.get("total_entries", 0) for a in archive_results)
    archive_pdfs = sum(a.get("pdf_count", 0) for a in archive_results)

    # 文件去重后的实际数量
    actual_unique_files = len(seen_md5)

    # 重复检测
    duplicate_groups = file_scan.get("duplicates", [])
    duplicate_files = sum(g["count"] for g in duplicate_groups)
    duplicate_wasted_space = 0
    for g in duplicate_groups:
        sizes = []
        for p in g["paths"]:
            fpath = PDFS_DIR / p
            if fpath.exists():
                sizes.append(fpath.stat().st_size)
        # 保留一份，浪费 n-1 份
        if sizes:
            duplicate_wasted_space += sum(sizes) - sizes[0]

    comparison = {
        "previous_analysis_date": "2026-08-03",
        "current_analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "changes": [],
        "summary": {
            # 之前
            "prev_total_unique_pdfs": PREVIOUS_ANALYSIS["total_unique_pdfs"],
            "prev_text_extractable": PREVIOUS_ANALYSIS["text_extractable"],
            "prev_scanned_no_text": PREVIOUS_ANALYSIS["scanned_no_text"],
            "prev_corrupted_invalid": PREVIOUS_ANALYSIS["corrupted_invalid"],
            "prev_duplicate_dirs": PREVIOUS_ANALYSIS["duplicate_dirs"],
            # 现在
            "cur_total_unique_pdfs": len(unique_pdf_files),
            "cur_text_extractable": text_extractable,
            "cur_scanned_no_text": len(scanned),
            "cur_corrupted_invalid": len(damaged),
            "cur_duplicate_files": duplicate_groups,
            "cur_total_files": file_scan["summary"]["total_files"],
            "cur_unique_files_by_md5": actual_unique_files,
            # 新增维度
            "cur_image_files": len(image_results),
            "cur_archives": len(archive_results),
            "cur_archive_pdfs": archive_pdfs,
            "cur_archive_entries": total_archive_entries,
            "cur_repaired_count": repaired_count,
            "cur_repair_failed": repair_failed,
            "cur_ocr_new_pdfs": ocr_new,
            "cur_ocr_images": image_ocr,
            "cur_duplicate_wasted_bytes": duplicate_wasted_space,
            "cur_duplicate_wasted_str": get_file_size_str(duplicate_wasted_space) if duplicate_wasted_space else "0B",
        },
        "newly_discovered_pdfs": newly_discovered_pdfs,
        "detailed_pdf_comparison": [],
    }

    # 逐个 PDF 对比
    for r in pdf_results:
        fname = r["file"]
        was_analyzed = False
        was_scanned = False
        was_corrupted = False
        for prev in PREVIOUS_ANALYSIS["previously_analyzed_docs"]:
            if Path(prev).stem.replace("_", "") in fname.replace("_", "").replace("/", ""):
                was_analyzed = True
                break
        for s in PREVIOUS_ANALYSIS["scanned_files"]:
            if Path(s).stem.replace("_", "") in fname.replace("_", "").replace("/", ""):
                was_scanned = True
                break
        for c in PREVIOUS_ANALYSIS["corrupted_files"]:
            if Path(c).stem.replace("_", "") in fname.replace("_", "").replace("/", ""):
                was_corrupted = True
                break

        status_now = "ok"
        if r.get("is_damaged"):
            status_now = "damaged"
            if r.get("repair_success"):
                status_now = "repaired"
        elif r.get("is_scanned"):
            status_now = "scanned"
            if r.get("ocr_attempted"):
                status_now = "scanned+ocr"

        prev_status = "analyzed"
        if was_corrupted:
            prev_status = "corrupted"
        elif was_scanned:
            prev_status = "scanned"
        elif not was_analyzed:
            prev_status = "not_analyzed"
        else:
            prev_status = "analyzed"

        change = "unchanged"
        if prev_status == "corrupted" and status_now == "repaired":
            change = "🟢 损坏→已修复"
        elif prev_status == "corrupted" and status_now == "damaged":
            change = "🔴 仍损坏"
        elif prev_status == "scanned" and status_now == "scanned+ocr":
            change = "🟡 扫描件→已OCR"
        elif prev_status == "scanned" and status_now == "scanned":
            change = "🟡 扫描件未OCR"
        elif prev_status == "not_analyzed":
            change = "🆕 新发现"

        entry = {
            "file": fname,
            "prev_status": prev_status,
            "now_status": status_now,
            "change": change,
            "pages": r.get("page_count", 0),
            "text_length": r.get("text_length", 0),
            "ocr_text_length": r.get("ocr_text_length", 0),
            "has_text_layer": r.get("has_text_layer", False),
            "is_scanned": r.get("is_scanned", False),
            "is_damaged": r.get("is_damaged", False),
            "repair_success": r.get("repair_success", False),
            "images_found": r.get("images_found", 0),
        }
        comparison["detailed_pdf_comparison"].append(entry)

        if change != "unchanged":
            comparison["changes"].append(f"{change}: {fname}")

    return comparison


# ============================================================
# 阶段 6：生成报告
# ============================================================

def generate_report(
    file_scan: dict,
    pdf_results: list,
    image_results: list,
    archive_results: list,
    comparison: dict
) -> str:
    """生成综合报告 Markdown"""
    lines = []
    lines.append("# 桃曲坡水库 PDF 综合分析与对比报告")
    lines.append("")
    lines.append(f"**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**分析工具**: PyMuPDF {fitz.version if fitz else 'N/A'} + Tesseract OCR + pdfplumber")
    lines.append(f"**分析目录**: `{PDFS_DIR}`")
    lines.append("")

    # ============ 一、总览 ============
    lines.append("---")
    lines.append("## 一、总体统计")
    lines.append("")
    lines.append("| 指标 | 之前报告 (2026-08-03) | 本次分析 (当前) | 变化 |")
    lines.append("|------|----------------------|----------------|------|")
    s = comparison["summary"]

    def diff_str(prev, cur):
        if prev == cur:
            return "—"
        return f"{prev} → {cur}"

    lines.append(f"| 文件总数（含重复） | — | {s['cur_total_files']} | — |")
    lines.append(f"| 唯一 PDF 数（去重） | {s['prev_total_unique_pdfs']} | {s['cur_total_unique_pdfs']} | {diff_str(s['prev_total_unique_pdfs'], s['cur_total_unique_pdfs'])} |")
    lines.append(f"| 文本可提取 | {s['prev_text_extractable']} | {s['cur_text_extractable']} | {diff_str(s['prev_text_extractable'], s['cur_text_extractable'])} |")
    lines.append(f"| 扫描件（无文本层） | {s['prev_scanned_no_text']} | {s['cur_scanned_no_text']} | {diff_str(s['prev_scanned_no_text'], s['cur_scanned_no_text'])} |")
    lines.append(f"| 损坏/无效 | {s['prev_corrupted_invalid']} | {s['cur_corrupted_invalid']} | {diff_str(s['prev_corrupted_invalid'], s['cur_corrupted_invalid'])} |")
    lines.append(f"| 重复文件组 | {s['prev_duplicate_dirs']} | {s['cur_duplicate_files']} | — |")
    lines.append(f"| 图像文件（JPG/PNG） | — | {s['cur_image_files']} | 新增 |")
    lines.append(f"| 压缩包 | — | {s['cur_archives']} | 新增 |")
    lines.append(f"| 压缩包内 PDF | — | {s['cur_archive_pdfs']} | 新增 |")
    lines.append(f"| 已修复文件 | — | {s['cur_repaired_count']} | 新增 |")
    lines.append(f"| PDF新OCR | — | {s['cur_ocr_new_pdfs']} | 新增 |")
    lines.append(f"| 图像新OCR | — | {s['cur_ocr_images']} | 新增 |")
    lines.append(f"| 重复浪费空间 | — | {s['cur_duplicate_wasted_str']} | 新增 |")
    lines.append("")

    # ============ 二、文件类型分布 ============
    lines.append("---")
    lines.append("## 二、文件类型分布")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("|------|------|")
    for ext, count in sorted(file_scan["summary"]["file_types"].items()):
        if ext == ".pdf":
            emoji = "📄"
        elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
            emoji = "🖼️"
        elif ext in (".rar", ".zip", ".7z"):
            emoji = "📦"
        elif ext in (".xls", ".xlsx"):
            emoji = "📊"
        elif ext in (".doc", ".docx", ".wps"):
            emoji = "📝"
        else:
            emoji = "📁"
        lines.append(f"| {emoji} {ext} | {count} |")
    lines.append("")

    # ============ 三、PDF 详细分析 ============
    lines.append("---")
    lines.append("## 三、PDF 详细分析")
    lines.append("")
    lines.append("| # | 文件 | 页数 | 文本(字符) | 图片 | 有文本层 | 扫描件 | 损坏 | 修复 | OCR | 变化 |")
    lines.append("|---|------|:----:|:----------:|:----:|:--------:|:------:|:----:|:----:|:---:|:----:|")

    for i, r in enumerate(pdf_results, 1):
        fname = r["file"]
        # 简短文件名
        short = Path(fname).name
        pages = r.get("page_count", "?")
        text_len = r.get("text_length", 0)
        images = r.get("images_found", 0)
        has_text = "✅" if r.get("has_text_layer") else "❌"
        is_scanned = "✅" if r.get("is_scanned") else "❌"
        is_damaged = "⚠️" if r.get("is_damaged") else "❌"
        repaired = "✅" if r.get("repair_success") else ("❌" if r.get("repair_attempted") else "—")
        ocr_done = "✅" if r.get("ocr_attempted") and r.get("ocr_text_length", 0) > 50 else "—"

        # 变化标识
        change = "—"
        for c in comparison["detailed_pdf_comparison"]:
            if c["file"] == fname:
                change = c["change"]
                break

        lines.append(f"| {i} | {short} | {pages} | {text_len} | {images} | {has_text} | {is_scanned} | {is_damaged} | {repaired} | {ocr_done} | {change} |")

    lines.append("")

    # ============ 四、损坏文件修复结果 ============
    damaged = [r for r in pdf_results if r.get("is_damaged") or r.get("repair_attempted")]
    if damaged:
        lines.append("---")
        lines.append("## 四、损坏文件修复结果")
        lines.append("")
        lines.append("| 文件 | 大小 | 损坏原因 | 修复结果 |")
        lines.append("|------|:----:|---------|:--------:|")
        for r in damaged:
            fname = Path(r["file"]).name
            size = ""
            for f in file_scan["files"]:
                if f["rel_path"] == r["file"]:
                    size = f["size_str"]
                    break
            reason = r.get("damage_details", r.get("error", "未知"))
            result = "✅ 修复成功" if r.get("repair_success") else "❌ 修复失败"
            lines.append(f"| {fname} | {size} | {reason[:80]} | {result} |")
        lines.append("")

    # ============ 五、OCR 结果 ============
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

    if image_results:
        lines.append("### 5.1 图像 OCR 结果")
        lines.append("")
        lines.append("| 文件 | 大小 | 识别文本 | 输出 |")
        lines.append("|------|:----:|:--------:|:----:|")
        for r in image_results:
            fname = Path(r["file"]).name
            preview = r.get("ocr_text_preview", "")[:60]
            out = r.get("ocr_saved_to", "—")
            if out != "—":
                out = f"`{Path(out).name}`"
            lines.append(f"| {fname} | {r['size']} | {preview} | {out} |")
        lines.append("")

    # ============ 六、压缩包分析 ============
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
            lines.append(f"- 其他文件: {a['other_count']}")
            if a.get("error"):
                lines.append(f"- ⚠️ 错误: {a['error']}")
            lines.append("")
            # 列出 PDF 文件
            pdfs_in_archive = [c for c in a.get("contents", []) if isinstance(c, dict) and c.get("name", "").lower().endswith(".pdf")]
            if pdfs_in_archive:
                lines.append("**包含的 PDF：**")
                for c in pdfs_in_archive:
                    lines.append(f"- {c['name']} ({get_file_size_str(Path(str(c.get('size', 0))))})")
                lines.append("")
        lines.append("")

    # ============ 七、重复文件 ============
    if file_scan.get("duplicates"):
        lines.append("---")
        lines.append("## 七、重复文件分析")
        lines.append("")
        lines.append(f"发现 **{len(file_scan['duplicates'])}** 组重复，共涉及 **{sum(g['count'] for g in file_scan['duplicates'])}** 个文件，")
        lines.append(f"浪费空间约 **{s['cur_duplicate_wasted_str']}**。")
        lines.append("")
        lines.append("| 重复组 | 文件数 | 浪费空间 | 文件路径 |")
        lines.append("|:------:|:------:|:--------:|---------|")
        for idx, g in enumerate(file_scan["duplicates"][:10], 1):
            paths = g["paths"]
            # 估算浪费
            wasted = 0
            for p in paths:
                fp = PDFS_DIR / p
                if fp.exists():
                    wasted += fp.stat().st_size
            # 减去第一份
            fp0 = PDFS_DIR / paths[0]
            wasted -= fp0.stat().st_size if fp0.exists() else 0
            lines.append(f"| {idx} | {g['count']} | {get_file_size_str(Path(str(wasted)))} | {paths[0]}<br/>{'<br/>'.join(paths[1:])} |")
        lines.append("")

    # ============ 八、变化对比总结 ============
    lines.append("---")
    lines.append("## 八、与之前分析的变化对比")
    lines.append("")
    lines.append("### 8.1 变化摘要")
    lines.append("")
    if comparison["changes"]:
        for c in comparison["changes"]:
            lines.append(f"- {c}")
    else:
        lines.append("无显著变化。")
    lines.append("")

    lines.append("### 8.2 详细对比")
    lines.append("")
    lines.append("| 对比维度 | 之前 (2026-08-03) | 当前 | 说明 |")
    lines.append("|---------|:----------------:|:----:|:----:|")

    # 构建对比表
    compare_items = [
        ("唯一 PDF 数", str(s['prev_total_unique_pdfs']), str(s['cur_total_unique_pdfs']),
         "之前按文件名去重，当前按 MD5 去重"),
        ("文本可提取", str(s['prev_text_extractable']), str(s['cur_text_extractable']),
         "当前新增了 PyMuPDF 的文本层检测"),
        ("扫描件", str(s['prev_scanned_no_text']), str(s['cur_scanned_no_text']),
         "新增 OCR 处理"),
        ("损坏文件", str(s['prev_corrupted_invalid']), str(s['cur_corrupted_invalid']),
         "新增修复尝试"),
        ("重复问题", f"{s['prev_duplicate_dirs']} 个目录", f"{s['cur_duplicate_files']} 组",
         "之前按目录统计，当前按 MD5 文件级统计"),
        ("图像文件", "未分析", str(s['cur_image_files']),
         "新增维度"),
        ("压缩包", "未分析", str(s['cur_archives']),
         "新增维度"),
        ("压缩包内 PDF", "未分析", str(s['cur_archive_pdfs']),
         "新增维度"),
        ("PDF 修复", "未尝试", f"{s['cur_repaired_count']} 成功 / {s['cur_repair_failed']} 失败",
         "新增维度"),
        ("PDF OCR", "未执行", f"{s['cur_ocr_new_pdfs']} 个",
         "新增维度"),
        ("图像 OCR", "未执行", f"{s['cur_ocr_images']} 个",
         "新增维度"),
    ]

    for name, prev, cur, note in compare_items:
        lines.append(f"| {name} | {prev} | {cur} | {note} |")

    lines.append("")

    # ============ 九、结论与建议 ============
    lines.append("---")
    lines.append("## 九、结论与建议")
    lines.append("")

    # 结论
    lines.append("### 9.1 核心发现")
    lines.append("")

    # 统计关键发现
    findings = []
    if damaged:
        success_repaired = [r for r in damaged if r.get("repair_success")]
        failed_repair = [r for r in damaged if r.get("repair_attempted") and not r.get("repair_success")]
        if success_repaired:
            findings.append(f"✅ 成功修复 {len(success_repaired)} 个之前报告为损坏的 PDF 文件")
        if failed_repair:
            findings.append(f"❌ 仍有 {len(failed_repair)} 个文件无法修复")
    if ocr_pdfs:
        findings.append(f"📄 对 {len(ocr_pdfs)} 个扫描件 PDF 执行了 OCR 文本提取")
    if image_results:
        meaningful = sum(1 for r in image_results if r.get("ocr_text_length", 0) > 10)
        findings.append(f"🖼️ 对 {meaningful}/{len(image_results)} 个图像文件执行了 OCR 识别")
    if archive_results:
        findings.append(f"📦 分析了 {len(archive_results)} 个压缩包，内含 {s['cur_archive_pdfs']} 个 PDF 和更多资料")
    if file_scan.get("duplicates"):
        findings.append(f"🔁 发现 {len(file_scan['duplicates'])} 组重复文件，可释放 {s['cur_duplicate_wasted_str']} 空间")

    for f in findings:
        lines.append(f"- {f}")
    lines.append("")

    lines.append("### 9.2 建议")
    lines.append("")
    lines.append("1. **去重整理**：清理重复文件，释放空间")
    lines.append("2. **压缩包提取**：解压 RAR/ZIP 中的 PDF 纳入知识库")
    lines.append("3. **OCR 文本入库**：将新生 OCR 文本导入 RAG 知识库")
    lines.append("4. **损坏文件处理**：对无法修复的文件联系数据源重新获取")
    lines.append("5. **图像资料**：将关键图像（库容曲线、泄流曲线等）OCR 结果结构化入库")
    lines.append("")

    # 脚注
    lines.append("---")
    lines.append(f"*分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*分析脚本: pdfs_analyzer.py*")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  桃曲坡水库 PDF 综合分析")
    print("=" * 60)

    # 阶段 1: 扫描文件
    print("\n阶段 1: 扫描文件清单...")
    file_scan = scan_all_files()
    print(f"  共发现 {file_scan['summary']['total_files']} 个文件，"
          f"{file_scan['summary']['file_types'].get('.pdf', 0)} 个 PDF，"
          f"{len(file_scan['duplicates'])} 组重复")

    # 阶段 2: PDF 分析
    pdf_results = analyze_all_pdfs(file_scan)

    # 阶段 3: 图像 OCR
    image_results = analyze_images(file_scan)

    # 阶段 4: 压缩包分析
    archive_results = analyze_archives(file_scan)

    # 阶段 5: 对比分析
    comparison = compare_with_previous(file_scan, pdf_results, image_results, archive_results)

    # 阶段 6: 生成报告
    print(f"\n{'='*60}")
    print("阶段 6: 生成报告")
    print(f"{'='*60}")
    report = generate_report(file_scan, pdf_results, image_results, archive_results, comparison)

    report_path = REPORT_DIR / "PDF综合分析与对比报告.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 报告已生成: {report_path}")

    # 保存结构化数据
    data = {
        "file_scan": file_scan,
        "pdf_analysis": pdf_results,
        "image_ocr": image_results,
        "archive_analysis": archive_results,
        "comparison": comparison,
    }
    data_path = REPORT_DIR / "PDF综合分析数据.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"✅ 结构化数据已保存: {data_path}")

    print("\n" + "=" * 60)
    print("  分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()