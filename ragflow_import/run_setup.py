"""
run_setup — idempotent dataset creation for the 桃曲坡 RAGFlow import.

Procedure (dry_run-aware):
  1. Connect via RAGFlowClient.
  2. List existing datasets → name→id lookup.
  3. For each dataset (TAG_KB ds0 + DATASETS ds1..ds5):
       reuse id if name already exists, else create.
  4. TAG_KB special handling:
       write vocab → upload_tag_vocab → wait_parse.
  5. Inject tag_kb_id into parser_config.tag_kb_ids for ds1..ds5.
  6. Apply METADATA_SCHEMA to every dataset.
  7. Persist OUT_DIR/setup_state.json.
  8. Print summary.
"""

import sys
import json
from pathlib import Path

import requests

from config import DATASETS, TAG_KB, METADATA_SCHEMA, OUT_DIR, RAGFLOW_EMAIL, RAGFLOW_PASSWORD, PUBLIC_PEM
from ragflow_client import RAGFlowClient
from tag_vocab import write_vocab_txt


def run_setup(dry_run: bool = False) -> dict[str, dict]:
    """
    Create or reuse datasets and write setup_state.json.

    Returns:
        dict mapping ds_key → {"name": ..., "id": ...}
    """
    # ------------------------------------------------------------------
    # Step 1 – connect
    # ------------------------------------------------------------------
    try:
        client = RAGFlowClient(RAGFLOW_EMAIL, RAGFLOW_PASSWORD, PUBLIC_PEM)
    except ConnectionError as exc:
        print(f"[ERROR] Could not connect to RAGFlow: {exc}")
        print("Hint: make sure RAGFlow is running and RAGFLOW_EMAIL / RAGFLOW_PASSWORD are set.")
        sys.exit(1)
    except Exception:
        raise   # HTTP errors are not connection errors — let them propagate

    # ------------------------------------------------------------------
    # Step 2 – list existing datasets (read-only, always called)
    # ------------------------------------------------------------------
    try:
        existing_datasets = client.list_datasets()
    except ConnectionError as exc:
        print(f"[ERROR] list_datasets() failed — connection error: {exc}")
        print("Hint: make sure RAGFlow is running.")
        sys.exit(1)
    except Exception:
        raise   # HTTP errors are not connection errors — let them propagate

    existing_lookup: dict[str, str] = {ds["name"]: ds["id"] for ds in existing_datasets}
    print(f"[INFO] Found {len(existing_lookup)} existing dataset(s): {list(existing_lookup.keys())}")

    # ------------------------------------------------------------------
    # Step 3 – create or reuse datasets (TAG_KB first, then DATASETS)
    # ------------------------------------------------------------------
    all_defs = [TAG_KB] + DATASETS          # ds0 then ds1..ds5
    state: dict[str, dict] = {}
    created: list[str] = []
    reused: list[str] = []

    for ds_def in all_defs:
        key = ds_def["key"]
        name = ds_def["name"]
        chunk_method = ds_def["chunk_method"]

        if name in existing_lookup:
            ds_id = existing_lookup[name]
            reused.append(name)
            print(f"[INFO] Reusing existing dataset '{name}' (id={ds_id})")
        elif dry_run:
            ds_id = "<would-create-id>"
            created.append(name)
            print(f"[dry_run] Would create dataset '{name}' (chunk_method={chunk_method})")
        else:
            result = client.create_dataset(name, chunk_method)
            ds_id = result["id"]
            created.append(name)
            print(f"[INFO] Created dataset '{name}' (id={ds_id})")

        state[key] = {"name": name, "id": ds_id}

    # ------------------------------------------------------------------
    # Step 4 – TAG_KB special handling
    # ------------------------------------------------------------------
    tag_kb_id = state["ds0"]["id"]

    vocab_path = OUT_DIR / "tag_vocab" / "taoqupo_vocab.txt"
    if dry_run:
        print(f"[dry_run] Would write vocab to {vocab_path}")
    else:
        write_vocab_txt(vocab_path)
        print(f"[INFO] Wrote tag vocab to {vocab_path}")

    if dry_run:
        print(f"[dry_run] Would upload_tag_vocab({tag_kb_id}, {vocab_path})")
    else:
        client.upload_tag_vocab(tag_kb_id, vocab_path)
        print(f"[INFO] Uploaded tag vocab for dataset '{TAG_KB['name']}'")

    if dry_run:
        print(f"[dry_run] Would wait_parse({tag_kb_id}, timeout=300)")
    else:
        client.wait_parse(tag_kb_id, timeout=300)
        print(f"[INFO] Tag KB parse complete for '{TAG_KB['name']}'")

    # ------------------------------------------------------------------
    # Step 5 – inject tag_kb_id into parser_config for ds1..ds5
    # ------------------------------------------------------------------
    for ds_def in DATASETS:            # ds1..ds5 only
        key = ds_def["key"]
        ds_id = state[key]["id"]
        parser_config = {**ds_def["parser_config"], "tag_kb_ids": [tag_kb_id]}

        if dry_run:
            print(f"[dry_run] Would update_dataset({key}, tag_kb_ids=[{tag_kb_id}])")
        else:
            client.update_dataset(ds_id, parser_config)
            print(f"[INFO] Updated dataset '{ds_def['name']}' with tag_kb_id={tag_kb_id}")

    # ------------------------------------------------------------------
    # Step 6 – apply METADATA_SCHEMA to every dataset
    # ------------------------------------------------------------------
    for ds_def in all_defs:            # ds0..ds5
        key = ds_def["key"]
        ds_id = state[key]["id"]

        if dry_run:
            print(f"[dry_run] Would put_metadata_config({key})")
        else:
            client.put_metadata_config(ds_id, METADATA_SCHEMA)
            print(f"[INFO] Applied metadata schema to '{ds_def['name']}'")

    # ------------------------------------------------------------------
    # Step 7 – persist state
    # ------------------------------------------------------------------
    state_path = OUT_DIR / "setup_state.json"
    if dry_run:
        print(f"[dry_run] Would write {state_path}")
    else:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {state_path}")

    # ------------------------------------------------------------------
    # Step 8 – summary
    # ------------------------------------------------------------------
    print("\n=== Dataset Summary ===")
    for ds_key, entry in state.items():
        status = "(created)" if entry["name"] in created else "(reused)"
        print(f"  {ds_key}: {entry['name']} id={entry['id']} {status}")

    return state
