"""tests/test_run_import.py — Task 8"""
import sys; sys.path.insert(0, "..")
from run_import import row_to_meta_fields, DocImportState, ImportStateMachine, run_import
from unittest.mock import MagicMock, patch

def test_row_to_meta_fields_year_int():
    row = {"rel":"test.txt","year":"2021","flood_event":"2021-10","doc_type":"文本"}
    mf = row_to_meta_fields(row)
    assert mf["meta_fields"]["year"] == 2021  # coerced to int

def test_row_to_meta_fields_omits_empty():
    row = {"rel":"test.txt","year":"","flood_event":"","doc_type":"文本"}
    mf = row_to_meta_fields(row)
    assert "year" not in mf["meta_fields"]
    assert "flood_event" not in mf["meta_fields"]

def test_doc_import_state_defaults():
    s = DocImportState(rel="test.txt", status="pending", dataset_key="ds1")
    assert s.doc_id is None
    assert s.error is None

def test_state_machine_set_get():
    sm = ImportStateMachine(state_path=None)
    sm.set("test.txt", "uploaded")
    assert sm.get("test.txt") == "uploaded"
    sm.set("test.txt", "done")
    assert sm.get("test.txt") == "done"

@patch("run_import.RAGFlowClient")
@patch("run_import.read_mapping_csv")
def test_dry_run_does_not_upload(mock_read, mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_read.return_value = [{"rel":"a.txt","dataset_key":"ds1","year":"2021","flood_event":"","doc_type":"文本","source_format":"pdf","quality":"high","responsible_dept":"","doc_nature":"技术","location":"","flood_magnitude":"不适用"}]
    with patch("builtins.open", MagicMock()):
        with patch("pathlib.Path.exists", return_value=True):
            run_import(apply=False, dataset_key=None, limit=None)
    mock_client.upload_document.assert_not_called()
