# tests/test_config.py
import sys; sys.path.insert(0, "..")
from config import (
    DATASETS, TAG_KB, METADATA_SCHEMA, TOP_LEVEL_ASSIGNMENTS,
    FLOOD_EVENT_BY_SUBDIR, QA_TABLE_KEYWORDS, VISION_SOURCES,
    TEXTUALIZED_VALUES, LOCATION_KEYWORDS, SKIP_DIRS, IMPORT_COLS,
    DERIVED_ROOT, ORIGINALS_ROOT, OUT_DIR, API_BASE,
)

def test_datasets_have_required_keys():
    for ds in DATASETS:
        assert "key" in ds and "parser_config" in ds
    tag = TAG_KB
    assert tag["chunk_method"] == "tag"

def test_metadata_schema_11_fields():
    assert len(METADATA_SCHEMA) == 11
    keys = {f["key"] for f in METADATA_SCHEMA}
    assert "flood_event" in keys
    assert "location" in keys

def test_top_level_assignments_11_files():
    assert len(TOP_LEVEL_ASSIGNMENTS) == 11
    for fname, ds_key in TOP_LEVEL_ASSIGNMENTS.items():
        assert ds_key in {"ds1","ds2","ds3"}

def test_flood_event_subdirs():
    assert FLOOD_EVENT_BY_SUBDIR["02-2021年洪水调度"] == "2021-10"
    assert "video_analysis" in SKIP_DIRS

def test_vision_sources_exist():
    for path, name in VISION_SOURCES:
        assert (ORIGINALS_ROOT / path).exists(), f"{path} not found"

def test_import_cols():
    assert "rel" in IMPORT_COLS
    assert "dataset_key" in IMPORT_COLS
