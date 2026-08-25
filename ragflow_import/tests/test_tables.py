import sys; sys.path.insert(0, "..")
from tables import lines_to_markdown, markdown_table_doc, qa_rows
import tempfile, pathlib, shutil

def test_tab_separated():
    lines = ["站名\t降雨量mm", "柳林\t52.3", "瑶曲\t38.7"]
    md = lines_to_markdown(lines)
    assert "站名" in md and "柳林" in md and "52.3" in md

def test_space_separated():
    lines = ["站名  降雨量mm", "柳林  52.3"]
    md = lines_to_markdown(lines)
    assert "柳林" in md

def test_fenced_block():
    lines = ["这是一段普通文本", "包含数字123和456"]
    md = lines_to_markdown(lines)
    assert "```" in md

def test_markdown_table_doc():
    doc = markdown_table_doc("柳林站降雨量", ["站名","雨量"], [["柳林","52.3"]])
    assert "# 表：柳林站降雨量" in doc
    assert "| 站名 | 雨量 |" in doc

def test_qa_rows_numeric():
    headers = ["站名","降雨量mm"]
    rows = [["柳林","52.3"], ["瑶曲","38.7"]]
    qas = qa_rows("降雨量统计", headers, rows)
    assert len(qas) >= 1
    q, a = qas[0]
    assert "柳林" in a or "52.3" in a
