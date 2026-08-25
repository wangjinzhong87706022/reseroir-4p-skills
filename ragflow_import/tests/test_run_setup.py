"""Tests for run_setup: idempotent dataset creation + tag KB upload."""
import sys
sys.path.insert(0, "..")

import json
import pathlib
from unittest.mock import patch, MagicMock

import pytest

import run_setup as run_setup_module


@patch("run_setup.RAGFlowClient")
def test_idempotent_lookup_existing(mock_client_cls):
    """ds1 already exists → reuse its id, don't call create_dataset."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    # Simulate ds1 ("规程与预案") already exists
    mock_client.list_datasets.return_value = [
        {"id": "abc123", "name": "规程与预案"},
    ]
    mock_client.create_dataset.return_value = {"id": "new"}
    mock_client.update_dataset.return_value = {}
    mock_client.put_metadata_config.return_value = {}
    mock_client.upload_tag_vocab.return_value = {}
    mock_client.wait_parse.return_value = {}

    with patch("run_setup.write_vocab_txt"):
        state = run_setup_module.run_setup(dry_run=True)

    # ds1 must reuse abc123, not create a new id
    ds1_entry = state.get("ds1", {})
    assert ds1_entry.get("id") == "abc123", (
        f"Expected ds1 to reuse id 'abc123' but got {ds1_entry.get('id')}"
    )


@patch("run_setup.RAGFlowClient")
def test_dry_run_does_not_create(mock_client_cls):
    """dry_run=True must not call create_dataset."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.list_datasets.return_value = []
    mock_client.create_dataset.return_value = {"id": "new"}

    with patch("run_setup.write_vocab_txt"):
        run_setup_module.run_setup(dry_run=True)

    mock_client.create_dataset.assert_not_called()


def test_setup_state_schema():
    """If out/setup_state.json exists, validate its shape."""
    state_path = pathlib.Path("/home/scada/SmartTwinRes-skills/ragflow_import/out/setup_state.json")
    if not state_path.exists():
        pytest.skip("setup_state.json not written yet")

    with open(state_path) as f:
        state = json.load(f)

    for ds_key in ["ds0", "ds1", "ds2", "ds3", "ds4", "ds5"]:
        assert ds_key in state, f"{ds_key} missing from setup_state.json"
        assert "id" in state[ds_key], f"{ds_key} missing 'id' field"
        assert "name" in state[ds_key], f"{ds_key} missing 'name' field"


@patch("run_setup.RAGFlowClient")
def test_tag_kb_id_propagated_to_datasets(mock_client_cls):
    """tag_kb_id must be injected into tag_kb_ids for ds1..ds5."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.list_datasets.return_value = []
    mock_client.create_dataset.return_value = {"id": "new_id"}
    mock_client.update_dataset.return_value = {}
    mock_client.put_metadata_config.return_value = {}
    mock_client.upload_tag_vocab.return_value = {}
    mock_client.wait_parse.return_value = {}

    with patch("run_setup.write_vocab_txt"):
        state = run_setup_module.run_setup(dry_run=False)

    # Verify update_dataset was called for ds1..ds5 with tag_kb_ids=[tag_kb_id]
    tag_kb_id = state["ds0"]["id"]
    calls = mock_client.update_dataset.call_args_list
    # There should be 5 update_dataset calls (ds1..ds5)
    assert len(calls) == 5, f"Expected 5 update_dataset calls, got {len(calls)}"
    for call in calls:
        args, _ = call
        # update_dataset(ds_id, parser_config) — parser_config is the 2nd positional arg
        parser_config = args[1] if len(args) > 1 else {}
        assert parser_config.get("tag_kb_ids") == [tag_kb_id], (
            f"Expected tag_kb_ids=[{tag_kb_id}], got {parser_config.get('tag_kb_ids')}"
        )


@patch("run_setup.RAGFlowClient")
def test_metadata_config_applied_to_all(mock_client_cls):
    """put_metadata_config must be called for ds0..ds5 (6 calls)."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.list_datasets.return_value = []
    mock_client.create_dataset.return_value = {"id": "new_id"}
    mock_client.update_dataset.return_value = {}
    mock_client.put_metadata_config.return_value = {}
    mock_client.upload_tag_vocab.return_value = {}
    mock_client.wait_parse.return_value = {}

    with patch("run_setup.write_vocab_txt"):
        run_setup_module.run_setup(dry_run=False)

    assert mock_client.put_metadata_config.call_count == 6, (
        f"Expected 6 put_metadata_config calls, got {mock_client.put_metadata_config.call_count}"
    )
