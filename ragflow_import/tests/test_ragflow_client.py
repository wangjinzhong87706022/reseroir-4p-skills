# tests/test_ragflow_client.py
import sys
sys.path.insert(0, "..")

from ragflow_client import encrypt_password, RAGFlowClient
from unittest.mock import patch, MagicMock
import os


def test_encrypt_password_format():
    import tempfile
    from Crypto.PublicKey import RSA
    key = RSA.generate(2048)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write(key.publickey().export_key().decode())
        pem_path = f.name
    result = encrypt_password("testpass", pem_path)
    import base64
    data = base64.b64decode(result)
    assert len(data) == 256  # 2048-bit RSA → 256-byte ciphertext
    os.unlink(pem_path)


def test_encrypt_password_nondeterministic():
    from Crypto.PublicKey import RSA
    import tempfile
    key = RSA.generate(2048)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write(key.publickey().export_key().decode())
        pem_path = f.name
    r1 = encrypt_password("testpass", pem_path)
    r2 = encrypt_password("testpass", pem_path)
    assert r1 != r2  # PKCS1_v1_5 is non-deterministic (random padding)
    import base64
    d1 = base64.b64decode(r1)
    d2 = base64.b64decode(r2)
    assert len(d1) == len(d2) == 256  # same format, different ciphertext
    os.unlink(pem_path)


@patch("ragflow_client.requests.Session")
def test_client_login_called(mock_session_class):
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_session.post.return_value = mock_response
    with patch("ragflow_client.encrypt_password", return_value="encrypted"):
        client = RAGFlowClient("test@test.com", "pass", "/fake/pem")
    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args
    assert "/auth/login" in call_args[0][0]


@patch("ragflow_client.requests.Session")
def test_search_payload_structure(mock_session_class):
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"chunks": [], "total": 0}}
    mock_session.post.return_value = mock_response
    with patch("ragflow_client.encrypt_password", return_value="e"):
        c = RAGFlowClient("t@t.com", "p", "/fake/pem")
    c.search_datasets(
        ["ds1", "ds2"],
        "溢洪道设计泄量",
        use_kg=True,
        meta_data_filter={"method": "manual", "logic": "and", "conditions": []},
    )
    payload = mock_session.post.call_args[1]["json"]
    assert "dataset_ids" in payload
    assert payload["use_kg"] is True
