# ragflow_client.py
"""
RAGFlow API client with RSA login and full dataset/document surface.
Import API_BASE and PUBLIC_PEM from config (resolved relative to ragflow_import/).
"""
import pathlib
import time
from typing import Optional

import requests

from config import API_BASE, PUBLIC_PEM


def encrypt_password(password: str, public_pem_path: str) -> str:
    """Encrypt a password using PKCS1_v1_5 with the given RSA public key PEM file."""
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.PublicKey import RSA
    import base64

    key = RSA.import_key(open(public_pem_path).read())
    cipher = PKCS1_v1_5.new(key)
    # Encrypt password bytes (not base64 — the password string itself encoded to bytes)
    ciphertext = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(ciphertext).decode()


class RAGFlowClient:
    """RAGFlow API client. Handles RSA login and carries session cookie for all requests."""

    def __init__(self, email: str, password: str, public_pem_path: str):
        self.session = requests.Session()
        self._email = email
        self._encrypted_password = encrypt_password(password, public_pem_path)
        self.login()

    def login(self) -> None:
        resp = self.session.post(
            f"{API_BASE}/auth/login",
            json={"email": self._email, "password": self._encrypted_password},
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Dataset CRUD
    # ------------------------------------------------------------------
    def list_datasets(self) -> list[dict]:
        resp = self.session.get(
            f"{API_BASE}/datasets", params={"offset": 0, "limit": 100}
        )
        resp.raise_for_status()
        return resp.json()["data"].get("list", [])

    def create_dataset(self, name: str, chunk_method: str = "naive") -> dict:
        resp = self.session.post(
            f"{API_BASE}/datasets", json={"name": name, "chunk_method": chunk_method}
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def get_dataset(self, dataset_id: str) -> dict:
        resp = self.session.get(f"{API_BASE}/datasets/{dataset_id}")
        resp.raise_for_status()
        return resp.json()["data"]

    def update_dataset(self, dataset_id: str, parser_config: dict) -> dict:
        resp = self.session.put(
            f"{API_BASE}/datasets/{dataset_id}", json={"parser_config": parser_config}
        )
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Metadata schema
    # ------------------------------------------------------------------
    def put_metadata_config(self, dataset_id: str, metadata: list[dict]) -> dict:
        resp = self.session.put(
            f"{API_BASE}/datasets/{dataset_id}/metadata/config",
            json={"metadata": metadata, "built_in_metadata": []},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def upload_document(
        self, dataset_id: str, file_path: pathlib.Path, filename: str | None = None
    ) -> dict:
        name = filename or file_path.name
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{API_BASE}/datasets/{dataset_id}/documents",
                files={"file": (name, f, "application/octet-stream")},
            )
        resp.raise_for_status()
        return resp.json()["data"]

    def patch_document(
        self, dataset_id: str, doc_id: str, meta_fields: dict
    ) -> dict:
        resp = self.session.patch(
            f"{API_BASE}/datasets/{dataset_id}/documents/{doc_id}",
            json={"meta_fields": meta_fields},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def list_documents(self, dataset_id: str) -> list[dict]:
        resp = self.session.get(
            f"{API_BASE}/datasets/{dataset_id}/documents",
            params={"offset": 0, "limit": 100},
        )
        resp.raise_for_status()
        return resp.json()["data"].get("list", [])

    def parse_documents(self, dataset_id: str, document_ids: list[str]) -> dict:
        resp = self.session.post(
            f"{API_BASE}/datasets/{dataset_id}/documents/parse",
            json={"document_ids": document_ids},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def wait_document(
        self, dataset_id: str, doc_id: str, timeout: float = 300
    ) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.list_documents(dataset_id)
            doc = next((d for d in docs if d["id"] == doc_id), None)
            if doc is None:
                raise ValueError(
                    f"Document {doc_id} not found in dataset {dataset_id}"
                )
            run = str(doc.get("run", ""))
            progress = doc.get("progress", 0)
            if run == "3" or progress >= 1:
                return doc
            if run == "4" or progress < 0:
                raise RuntimeError(
                    f"Document {doc_id} failed: run={run} progress={progress}"
                )
            time.sleep(5)
        raise TimeoutError(
            f"Document {doc_id} did not complete within {timeout}s"
        )

    # ------------------------------------------------------------------
    # Search (QC)
    # ------------------------------------------------------------------
    def search_datasets(
        self,
        dataset_ids: list[str],
        question: str,
        top_k: int = 10,
        use_kg: bool = False,
        meta_data_filter: dict | None = None,
    ) -> dict:
        payload = {
            "dataset_ids": dataset_ids,
            "question": question,
            "top_k": top_k,
            "use_kg": use_kg,
        }
        if meta_data_filter is not None:
            payload["meta_data_filter"] = meta_data_filter
        resp = self.session.post(f"{API_BASE}/datasets/search", json=payload)
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Tag KB
    # ------------------------------------------------------------------
    def upload_tag_vocab(self, dataset_id: str, vocab_file_path: pathlib.Path) -> dict:
        with open(vocab_file_path, "rb") as f:
            resp = self.session.post(
                f"{API_BASE}/datasets/{dataset_id}/documents",
                files={"file": (vocab_file_path.name, f, "application/octet-stream")},
            )
        resp.raise_for_status()
        return resp.json()["data"]

    def wait_parse(self, dataset_id: str, timeout: float = 300) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.list_documents(dataset_id)
            if not docs:
                time.sleep(5)
                continue
            runs = [str(d.get("run", "")) for d in docs]
            progresses = [d.get("progress", 0) for d in docs]
            if all(r == "3" or p >= 1 for r, p in zip(runs, progresses)):
                return docs[0]
            if any(r == "4" or p < 0 for r, p in zip(runs, progresses)):
                raise RuntimeError(f"Tag KB parse failed for dataset {dataset_id}")
            time.sleep(5)
        raise TimeoutError(f"Tag KB {dataset_id} did not parse within {timeout}s")
