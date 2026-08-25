"""corpus.py — 语料扫描、去重、映射表生成 (spec §6 阶段0)."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from config import (
    DERIVED_ROOT,
    ORIGINALS_ROOT,
    TOP_LEVEL_ASSIGNMENTS,
    FLOOD_EVENT_BY_SUBDIR,
    QA_TABLE_KEYWORDS,
    SKIP_DIRS,
    IMPORT_COLS,
)


# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    rel: str                       # relative path under DERIVED_ROOT
    native_xlsx_path: str | None   # absolute path to pdfs/ native xlsx, or None
    dataset_key: str               # ds1..ds5
    doc_category: str
    sub_category: str
    flood_event: str | None
    doc_type: str                  # 文本/表格/图片/图纸
    year: int | None
    source_format: str
    quality: str
    responsible_dept: str | None
    doc_nature: str
    location: str | None
    flood_magnitude: str
    skip_reason: str | None        # None = importable; set if skipped
    duplicate_of: str | None       # rel of canonical file if this is a dup
    sha256: str                    # hex digest of file content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_hex(path: Path) -> str:
    """Return SHA-256 hex digest of file at *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_dup_suffix(name: str) -> str:
    """Remove _dupx or trailing x suffix for dedupe grouping."""
    if name.endswith("_dupx"):
        return name[:-5]
    if name.endswith("x") and not name.endswith("含生态x"):
        return name[:-1]
    return name


def find_native_xlsx(rel: str) -> Path | None:
    """
    Progressive stem-suffix match for native xlsx alongside a derived .txt file.

    Given rel like ``06-历年洪水资料_08-历年洪水统计_弃水量统计表（含生态）.txt``,
    tries (in order):
      1.  ORIGINALS_ROOT/.../弃水量统计表（含生态）.xlsx
      2.  ORIGINALS_ROOT/.../弃水量统计表.xlsx
      3.  ORIGINALS_ROOT/.../弃水量统计表.xls
      4.  Same three variants with ``（含生态）`` stripped
      5.  None found → return None
    """
    # Strip .txt and split by underscore to reconstruct originals path
    txt_stem = rel.rsplit(".", 1)[0]
    parts = txt_stem.split("_")
    if len(parts) < 2:
        return None

    originals_dir = ORIGINALS_ROOT / "/".join(parts[:-1])

    # Stems to try: original and stripped of parenthetical suffix
    stems_to_try = [parts[-1]]
    stripped = re.sub(r"（[^）]+）", "", parts[-1])
    if stripped != parts[-1]:
        stems_to_try.append(stripped)

    for stem in stems_to_try:
        for ext in (".xlsx", ".xls"):
            candidate = originals_dir / (stem + ext)
            if candidate.exists():
                return candidate

    return None


def _first_seg(rel: str) -> str:
    """First underscore-delimited segment of the filename (no extension)."""
    filename = rel.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
    return filename.split("_")[0]


def classify(rel: str) -> str:
    """
    Map *rel* to a dataset key.

    Priority order:
      1. Exact top-level file match in TOP_LEVEL_ASSIGNMENTS
      2. Subdir / underscore-segment prefix rules
      3. raise ValueError
    """
    # Rule 1: top-level exact match (no "/" in rel)
    if "/" not in rel and rel in TOP_LEVEL_ASSIGNMENTS:
        return TOP_LEVEL_ASSIGNMENTS[rel]

    # Extract segments:
    #   - for "dir/file_name.txt": segments = ["dir", "file_name_seg1", "file_name_seg2", ...]
    #     where file_name has been split on underscores
    #   - for "file_name.txt" (top-level): segments = ["file_name_seg1", ...]
    segments = rel.replace("\\", "/").split("/")
    filename_seg0 = segments[-1].rsplit(".", 1)[0].split("_")[0] if len(segments) >= 1 else ""

    top = segments[0]  # e.g. "excel_extracted" or top-level dir
    # Use first underscore-segment of filename for top-level classification
    first_seg = segments[-1].rsplit(".", 1)[0].split("_")[0]

    # 03-施工图纸与设计_* → ds2
    if first_seg.startswith("03-施工图纸与设计"):
        return "ds2"
    # 04-确权划界_* → ds2
    if first_seg.startswith("04-确权划界"):
        return "ds2"
    # 05-基础数据与曲线_* → ds2
    if first_seg.startswith("05-基础数据与曲线"):
        return "ds2"
    # 06-: check if second underscore-segment is in FLOOD_EVENT_BY_SUBDIR → ds3
    if first_seg.startswith("06-"):
        # Get second underscore segment from filename
        filename = segments[-1].rsplit(".", 1)[0]
        filename_parts = filename.split("_")
        if len(filename_parts) >= 2 and filename_parts[1] in FLOOD_EVENT_BY_SUBDIR:
            return "ds3"
    # 07-管理资料_* → ds4
    if first_seg.startswith("07-管理资料"):
        return "ds4"
    # 08-政策文件_* → ds4
    if first_seg.startswith("08-政策文件"):
        return "ds4"

    # Rule 3: ocr_new/ fallback — files that don't have a numeric prefix
    # These are orphaned OCR outputs; infer from filename keywords
    if "/" in rel and rel.split("/")[0] == "ocr_new":
        filename = rel.split("/")[-1]
        if "确权划界" in filename or "划界图" in filename or "划界附图" in filename:
            return "ds2"
        if "汛情专报" in filename or "水情" in filename:
            return "ds3"
        if "调度规程" in filename or "应急预案" in filename or "调度运用计划" in filename:
            return "ds1"
        if "三个责任人" in filename or "组织" in filename or "注册" in filename or "责任人" in filename:
            return "ds4"
        # Default orphan OCR → ds2
        return "ds2"

    # Rule 4: unknown
    raise ValueError(f"Unknown file: {rel}")


def parse_flood_event(rel: str) -> str | None:
    """
    Derive flood_event from *rel*.

    Priority:
      1. Sub-subdir matching r"(\d+)-(\d+)洪水" → "{year}-{zero_padded_month}"
         (e.g. 9-25洪水 → 2021-09, 10-3洪水 → 2021-10)
      2. Underscore-segment lookup in FLOOD_EVENT_BY_SUBDIR
    """
    rel_normalized = rel.replace("\\", "/")
    parts = rel_normalized.split("/")
    filename = parts[-1].rsplit(".", 1)[0]
    segments = filename.split("_")

    # Check all underscore segments for the flood sub-subdir pattern
    for seg in segments:
        m = re.match(r"(\d+)-(\d+)洪水", seg)
        if m:
            month = m.group(1).zfill(2)
            return f"2021-{month}"

    # Fall back to FLOOD_EVENT_BY_SUBDIR lookup on second segment
    if len(segments) >= 2 and segments[1] in FLOOD_EVENT_BY_SUBDIR:
        return FLOOD_EVENT_BY_SUBDIR[segments[1]]

    return None


def parse_year(rel: str) -> int | None:
    """Extract the first 4-digit year from *rel*."""
    m = re.search(r"\d{4}", rel)
    return int(m.group(0)) if m else None


def source_format_from_rel(rel: str) -> str:
    """Derive source_format from *rel*."""
    if "ocr_new/" in rel and rel.endswith(".jpg.txt"):
        return "ocr_jpg"
    if "ocr_new/" in rel and rel.endswith(".png.txt"):
        return "ocr_png"
    if "excel_extracted/" in rel:
        return "excel"
    if "word_extracted/" in rel:
        return "word"
    return "pdf"


def quality_from_source_format(sf: str) -> str:
    """Derive quality from source_format."""
    if "ocr_jpg" in sf or "ocr_png" in sf:
        return "low"
    if sf in {"pdf", "word", "excel", "native_xlsx"}:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def _doc_category_from_ds_key(ds_key: str) -> str:
    return {
        "ds1": "规程预案",
        "ds2": "基础数据",
        "ds3": "洪水资料",
        "ds4": "组织管理",
        "ds5": "工程资料",
    }.get(ds_key, "未知")


def _doc_type_from_rel(rel: str) -> str:
    """Infer doc_type from rel.  Default to 文本."""
    if "图片" in rel or "照片" in rel or ".jpg" in rel:
        return "图片"
    if "图纸" in rel:
        return "图纸"
    if "xlsx" in rel or "xls" in rel or "表格" in rel:
        return "表格"
    return "文本"


def _should_skip(rel: str) -> bool:
    """Return True if any SKIP_DIR segment appears in rel path parts."""
    parts = rel.replace("\\", "/").split("/")
    return any(skip in parts for skip in SKIP_DIRS)


def scan() -> list[Entry]:
    """
    Walk DERIVED_ROOT, build Entry list, deduplicate, add synthetic xlsx entries.

    - Skips SKIP_DIRS
    - Dedupes by sha256 + dataset_key (keeps shortest rel)
    - Detects QA table keywords and creates synthetic native_xlsx entries
    """
    entries: list[Entry] = []
    seen: dict[tuple, list[Entry]] = {}   # (sha256, dataset_key) → [Entry, ...]

    for path in sorted(DERIVED_ROOT.rglob("*.txt")):
        rel = str(path.relative_to(DERIVED_ROOT))

        # Skip SKIP_DIRS
        if _should_skip(rel):
            continue

        # Classify
        try:
            ds_key = classify(rel)
        except ValueError:
            # Unknown file — re-raise (scripts must not guess)
            raise

        # Compute sha256
        file_bytes = path.read_bytes()
        sha = hashlib.sha256(file_bytes).hexdigest()

        # Flood event
        flood_event = parse_flood_event(rel)

        # Year
        year = parse_year(rel)

        # Source format & quality
        sf = source_format_from_rel(rel)
        quality = quality_from_source_format(sf)

        # Doc category / sub_category
        doc_category = _doc_category_from_ds_key(ds_key)
        filename = rel.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
        filename_parts = filename.split("_")
        sub_category = filename_parts[1] if len(filename_parts) >= 2 else ""

        # Skip reason
        skip_reason: str | None = None
        if "_dupx" in rel or (rel.endswith("x") and not rel.endswith("含生态x")):
            skip_reason = "duplicate"

        # Native xlsx lookup
        native_xlsx_path: str | None = None
        xlsx_path = find_native_xlsx(rel)
        if xlsx_path:
            native_xlsx_path = str(xlsx_path)
            if any(kw in rel for kw in QA_TABLE_KEYWORDS):
                synthetic_rel = str(xlsx_path.relative_to(ORIGINALS_ROOT))
                synthetic_entry = Entry(
                    rel=synthetic_rel,
                    native_xlsx_path=str(xlsx_path),
                    dataset_key="ds3",
                    doc_category="洪水资料",
                    sub_category=sub_category,
                    flood_event=flood_event,
                    doc_type="表格",
                    year=year,
                    source_format="native_xlsx",
                    quality="high",
                    responsible_dept=None,
                    doc_nature="统计",
                    location=None,
                    flood_magnitude="不适用",
                    skip_reason=None,
                    duplicate_of=None,
                    sha256=hashlib.sha256(xlsx_path.read_bytes()).hexdigest(),
                )
                entries.append(synthetic_entry)

        entry = Entry(
            rel=rel,
            native_xlsx_path=native_xlsx_path,
            dataset_key=ds_key,
            doc_category=doc_category,
            sub_category=sub_category,
            flood_event=flood_event,
            doc_type=_doc_type_from_rel(rel),
            year=year,
            source_format=sf,
            quality=quality,
            responsible_dept=None,
            doc_nature="技术",
            location=None,
            flood_magnitude="不适用",
            skip_reason=skip_reason,
            duplicate_of=None,
            sha256=sha,
        )
        entries.append(entry)

        # Collect for dedup
        key = (sha, ds_key)
        if key not in seen:
            seen[key] = []
        seen[key].append(entry)

    # Dedup: within each sha256+ds_key group, keep shortest rel as canonical
    for (sha, ds_key), group in seen.items():
        if len(group) <= 1:
            continue
        canonical = min(group, key=lambda e: len(e.rel))
        for e in group:
            if e is not canonical:
                e.duplicate_of = canonical.rel
                e.skip_reason = "duplicate"

    return entries


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def write_mapping_csv(entries: list[Entry], path: str | Path) -> None:
    """Write *entries* to CSV at *path* using IMPORT_COLS."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=IMPORT_COLS, extrasaction="ignore")
        writer.writeheader()
        for e in entries:
            writer.writerow(asdict(e))


def read_mapping_csv(path: str | Path) -> list[dict]:
    """Read mapping CSV back to list[dict]."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_manifest(entries: list[Entry]) -> list[Entry]:
    """Return entries where skip_reason is None (files to actually import)."""
    return [e for e in entries if e.skip_reason is None]
