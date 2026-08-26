"""run_import.py — Task 8: three-step import (upload → metadata → parse) + resume support."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from config import DERIVED_ROOT, OUT_DIR, RAGFLOW_EMAIL, RAGFLOW_PASSWORD, PUBLIC_PEM
from corpus import read_mapping_csv
from ragflow_client import RAGFlowClient

# ---------------------------------------------------------------------------
# Metadata field mapping
# ---------------------------------------------------------------------------
# CSV column → meta_fields key (spec §4.1)
_META_FIELD_MAP = {
    "doc_category":    "doc_category",
    "sub_category":    "sub_category",
    "flood_event":     "flood_event",
    "doc_type":        "doc_type",
    "year":            "year",
    "source_format":   "source_format",
    "quality":         "quality",
    "responsible_dept":"responsible_dept",
    "doc_nature":      "doc_nature",
    "location":        "location",
    "flood_magnitude": "flood_magnitude",
}


def row_to_meta_fields(row: dict) -> dict:
    """
    Convert a mapping CSV row dict to the ``meta_fields`` payload for ``patch_document``.

    - Map CSV column names to the 11 metadata fields
    - Coerce ``year`` to ``int`` if non-empty
    - Omit fields with empty string or None values
    - Return ``{"meta_fields": {...}}`` shape
    """
    meta = {}
    for csv_col, field_key in _META_FIELD_MAP.items():
        val = row.get(csv_col, "")
        if val is None or val == "":
            continue
        if field_key == "year":
            try:
                val = int(val)
            except (ValueError, TypeError):
                continue
        meta[field_key] = val
    return {"meta_fields": meta}


# ---------------------------------------------------------------------------
# Import state
# ---------------------------------------------------------------------------

@dataclass
class DocImportState:
    rel: str
    status: str  # pending → uploaded → meta_done → parse_requested → done/failed
    dataset_key: str
    doc_id: str | None = None
    error: str | None = None


class ImportStateMachine:
    """
    Manages ``import_state.json`` persistence.

    State file is keyed by ``rel``; each value is a ``DocImportState`` dict.
    Supports resume: loading an existing state file preserves progress.
    """

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path = state_path or (OUT_DIR / "import_state.json")
        self._state: dict[str, dict] = {}
        if self._state_path.exists():
            try:
                raw = json.loads(self._state_path.read_text())
                for k, v in raw.items():
                    self._state[k] = v  # already dict (from JSON)
            except (json.JSONDecodeError, OSError):
                print("[WARN] import_state.json corrupt, starting fresh")

    def get(self, rel: str) -> str | None:
        return self._state.get(rel, {}).get("status")

    def set(self, rel: str, status: str, **extra: object) -> None:
        if rel in self._state:
            self._state[rel]["status"] = status
        else:
            self._state[rel] = {"rel": rel, "status": status, **extra}
        for k, v in extra.items():
            if v is not None:
                self._state[rel][k] = v

    def save(self) -> None:
        self._state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))

    def items(self):
        return self._state.items()


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def run_import(
    apply: bool,
    dataset_key: str | None = None,
    limit: int | None = None,
) -> dict:
    """
    Execute (or dry-run) the three-step import pipeline.

    Parameters
    ----------
    apply: if False, run in dry-run mode (no RAGFlow calls that modify state).
    dataset_key: if set, only import files belonging to this dataset key.
    limit: if set, cap the total number of files imported.

    Steps per file
    ---------------
    1. ``upload_document`` → extract doc_id, status = "uploaded"
    2. ``patch_document`` with ``row_to_meta_fields`` → status = "meta_done"
    3. ``parse_documents`` → status = "parse_requested"
    4. ``wait_document(timeout=600)`` → status = "done" or "failed"

    Progress is persisted to ``import_state.json`` after every step.
    """
    # Load ds_key → dataset_id mapping from Task 7 output
    setup_path = OUT_DIR / "setup_state.json"
    if not setup_path.exists():
        raise FileNotFoundError(f"setup_state.json not found at {setup_path}")
    setup = json.loads(setup_path.read_text())

    # Load mapping CSV (list[dict])
    mapping_path = OUT_DIR / "mapping.csv"
    if not mapping_path.exists():
        raise FileNotFoundError(f"mapping.csv not found at {mapping_path}")
    rows = read_mapping_csv(mapping_path)

    # Load existing import state (resume support)
    sm = ImportStateMachine()

    # Filter: skip already-done, optionally by dataset_key or limit
    pending = []
    for row in rows:
        rel = row.get("rel", "")
        if not rel:
            continue
        status = sm.get(rel)
        if status == "done":
            continue
        ds_k = row.get("dataset_key", "")
        if dataset_key and ds_k != dataset_key:
            continue
        pending.append(row)

    # Order: ds1..ds5 (ds0 tag KB is already done)
    ds_order = ["ds1", "ds2", "ds3", "ds4", "ds5"]
    pending.sort(key=lambda r: ds_order.index(r.get("dataset_key", "ds1")) if r.get("dataset_key", "ds1") in ds_order else len(ds_order))

    if limit:
        pending = pending[:limit]

    # ── Dry-run ──────────────────────────────────────────────────────────────
    if not apply:
        print(f"[dry-run] Would import {len(pending)} file(s)")
        for row in pending:
            print(f"  {row.get('dataset_key')}/{row.get('rel')}")
        return {"done": 0, "failed": 0, "skipped": len(pending)}

    # ── Real import ─────────────────────────────────────────────────────────
    client = RAGFlowClient(
        email=RAGFLOW_EMAIL,
        password=RAGFLOW_PASSWORD,
        public_pem_path=PUBLIC_PEM,
    )

    done = 0
    failed = 0
    t0 = time.time()

    for row in pending:
        rel = row["rel"]
        ds_k = row.get("dataset_key", "")
        dataset_id = setup.get(ds_k, {}).get("id")
        if not dataset_id:
            sm.set(rel, "failed", error=f"Unknown dataset_key {ds_k}")
            sm.save()
            failed += 1
            continue

        file_path = DERIVED_ROOT / rel
        if not file_path.exists():
            sm.set(rel, "failed", error=f"File not found: {file_path}")
            sm.save()
            failed += 1
            continue

        try:
            # Step 1: upload
            result = client.upload_document(dataset_id, file_path)
            doc_id = result.get("id") if isinstance(result, dict) else None
            if not doc_id:
                doc_id = result[0].get("id") if isinstance(result, list) else None
            if not doc_id:
                raise ValueError(f"No doc_id in upload response: {result}")
            sm.set(rel, "uploaded", dataset_key=ds_k, doc_id=doc_id)
            sm.save()

            # Step 2: patch metadata
            meta_payload = row_to_meta_fields(row)
            client.patch_document(dataset_id, doc_id, meta_payload)
            sm.set(rel, "meta_done")
            sm.save()

            # Step 3: request parse
            client.parse_documents(dataset_id, [doc_id])
            sm.set(rel, "parse_requested")
            sm.save()

            # Step 4: wait for completion
            client.wait_document(dataset_id, doc_id, timeout=600)
            sm.set(rel, "done")
            sm.save()
            done += 1

        except Exception as exc:
            sm.set(rel, "failed", error=str(exc))
            sm.save()
            failed += 1

    elapsed = time.time() - t0
    print(f"Import complete: {done} done, {failed} failed, {len(pending)-done-failed} skipped in {elapsed:.1f}s")
    return {"done": done, "failed": failed, "skipped": len(pending) - done - failed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RAGFlow three-step import")
    parser.add_argument("--apply", action="store_true", help="Actually import (omit for dry-run)")
    parser.add_argument("--dataset", dest="dataset_key", default=None, help="Limit to dataset key (e.g. ds3)")
    parser.add_argument("--limit", type=int, default=None, help="Cap total files imported")
    args = parser.parse_args()

    result = run_import(apply=args.apply, dataset_key=args.dataset_key, limit=args.limit)
    print(result)


if __name__ == "__main__":
    main()
