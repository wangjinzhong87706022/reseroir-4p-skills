import sys; sys.path.insert(0, "..")
from corpus import Entry, classify, scan, write_mapping_csv, read_mapping_csv, build_manifest
import tempfile, csv, os

def test_classify_top_level():
    assert classify("2026年桃曲坡水库调度规程_1__1_.pdf.txt") == "ds1"
    assert classify("陕西省桃曲坡灌区水利工程管理范围及保护范围划界报告.pdf.txt") == "ds2"
    assert classify("水情通报第161期.pdf.txt") == "ds3"

def test_classify_subdir():
    assert classify("03-施工图纸与设计_05-数字孪生项目建设方案x.txt") == "ds2"
    assert classify("07-管理资料_04-设备管理_桃曲坡平台设备管理x.txt") == "ds4"

def test_classify_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown file"):
        classify("03-施工图纸与设计_05-数字孪生项目建设方案x.txt".replace("03-","99-"))

def test_flood_event_2021_subdirs():
    # 9-25 subdir maps to 2021-09
    entry_9 = next(e for e in scan() if "_9-25洪水_" in e.rel)
    assert entry_9.flood_event == "2021-09"
    # 10-3 subdir maps to 2021-10
    entry_10 = next(e for e in scan() if "_10-3洪水_" in e.rel)
    assert entry_10.flood_event == "2021-10"

def test_scan_smoke():
    entries = scan()
    rels = [e.rel for e in entries]
    # all video_analysis skipped
    assert not any("video_analysis" in r for r in rels)
    # 97 importable txt files (110 total - 13 duplicates marked skip_reason=duplicate)
    importable = [e for e in entries if e.skip_reason is None]
    assert len(importable) == 97, f"Expected 97, got {len(importable)}"

def test_dedupe_same_content():
    # Two files with same sha256 in same ds should mark one as duplicate_of
    # Dedup key is (sha256, dataset_key) per spec
    from corpus import scan
    entries = scan()
    by_sha_ds = {}
    for e in entries:
        key = (e.sha256, e.dataset_key)
        if key not in by_sha_ds:
            by_sha_ds[key] = []
        by_sha_ds[key].append(e)
    for (sha, ds), group in by_sha_ds.items():
        if len(group) > 1:
            non_dup = [e for e in group if e.duplicate_of is None]
            assert len(non_dup) == 1, f"sha {sha} ds={ds}: expected 1 canonical, got {len(non_dup)}"
            for e in group:
                if e.duplicate_of:
                    assert e.duplicate_of == non_dup[0].rel

def test_mapping_csv_roundtrip():
    entries = scan()[:5]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        write_mapping_csv(entries, f.name)
    loaded = read_mapping_csv(f.name)
    assert len(loaded) == 5
    assert loaded[0]["rel"] == entries[0].rel
    os.unlink(f.name)

def test_build_manifest_excludes_skipped():
    entries = scan()
    manifest = build_manifest(entries)
    assert all(e.skip_reason is None for e in manifest)
