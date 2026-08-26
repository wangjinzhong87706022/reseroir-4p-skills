import sys
sys.path.insert(0, "..")
from tag_vocab import write_vocab_txt, parse_vocab_txt, VOCAB_ROWS
import tempfile
import pathlib

def test_vocab_rows_count():
    assert len(VOCAB_ROWS) == 12  # 5 knowledge-type + 7 flood-event

def test_write_and_parse_roundtrip():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        tmp = pathlib.Path(f.name)
    write_vocab_txt(tmp)
    rows = parse_vocab_txt(tmp)
    assert len(rows) == 12
    assert rows[0][0] == "规程预案"
    assert rows[0][1] == "规程预案"
    import os
    os.unlink(f.name)

def test_knowledge_type_rows():
    knowledge_rows = [r for r in VOCAB_ROWS if r[1] in {"规程预案", "基础数据", "洪水资料", "组织管理", "工程资料"}]
    assert len(knowledge_rows) == 5  # 5 knowledge-type enums

def test_flood_event_rows():
    flood_rows = [r for r in VOCAB_ROWS if r[1] in {"2021-10", "2020-8", "2019-7", "2013-7", "2008-8", "其他", "历年统计"}]
    assert len(flood_rows) == 7
