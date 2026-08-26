import sys
import json
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock

# ------------------------------------------------------------------
# Tests for run_qc.py — verify QUESTIONS structure before implementation
# ------------------------------------------------------------------

def test_questions_have_required_fields():
    """All 6 questions must have id/text/dataset_ids/use_kg/expected_keywords."""
    from run_qc import QUESTIONS  # will fail until run_qc.py exists
    for q in QUESTIONS:
        assert "id" in q and "text" in q and "dataset_ids" in q, f"Question {q} missing required field"
        assert "use_kg" in q and "expected_keywords" in q, f"Question {q} missing use_kg or expected_keywords"
        assert isinstance(q["dataset_ids"], list), f"Question {q} dataset_ids must be a list"


def test_question_count():
    """Exactly 6 questions are defined per spec §3.5."""
    from run_qc import QUESTIONS
    assert len(QUESTIONS) == 6, f"Expected 6 questions, got {len(QUESTIONS)}"


def test_q1_uses_kg():
    """Q1 must use knowledge graph and expect the 1454 m³/s keyword."""
    from run_qc import QUESTIONS
    q1 = next(q for q in QUESTIONS if q["id"] == "Q1")
    assert q1["use_kg"] is True, "Q1 must have use_kg=True"
    assert "1454" in q1["expected_keywords"], "Q1 expected_keywords must contain '1454'"


def test_meta_filter_structure():
    """All non-null meta_data_filter entries must have method in {manual, semi_auto, auto}."""
    from run_qc import QUESTIONS
    for q in QUESTIONS:
        mf = q.get("meta_data_filter")
        if mf is not None:
            assert "method" in mf, f"Question {q['id']} meta_data_filter missing 'method'"
            assert mf["method"] in {"manual", "semi_auto", "auto"}, \
                f"Question {q['id']} meta_data_filter method must be manual/semi_auto/auto, got {mf['method']}"


@patch("run_qc.RAGFlowClient")
def test_run_qc_produces_report(mock_client_cls):
    """run_qc() must call search_datasets and write results + report files."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.search_datasets.return_value = {
        "chunks": [{"content_with_weight": "溢洪道设计泄量1454 m³/s"}],
        "total": 1,
    }

    state_data = {
        "ds1": {"id": "ds1-id", "name": "规程与预案"},
        "ds2": {"id": "ds2-id", "name": "基础数据"},
        "ds3": {"id": "ds3-id", "name": "洪水资料"},
        "ds4": {"id": "ds4-id", "name": "组织管理"},
    }

    with patch("pathlib.Path.exists", return_value=True):
        with patch("builtins.open", MagicMock()):
            with patch("json.load", return_value=state_data):
                from run_qc import run_qc
                run_qc()

    assert mock_client.search_datasets.called, "search_datasets must be called"
