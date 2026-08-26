"""Tests for the Reader HTTP service (CF-81, CF-82).

Two things matter here: bad input must be a clear 422, and a Vault outage
must degrade the call instead of failing it.
"""
import io
import os

import pytest
import requests
from fastapi.testclient import TestClient

from reader import api
from reader.api import create_app

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
EDGE = os.path.join(REPO, "caseforge-testdata", "documents", "edge_cases")


def _post_pdf(client, path, **params):
    with open(path, "rb") as f:
        return client.post(
            "/extract",
            files={"document": (os.path.basename(path), f, "application/pdf")},
            params=params,
        )


class _FakeResponse:
    """Stand-in for a requests Response — only what store_in_vault reads."""

    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def real_pdf():
    return os.path.join(FIXTURES, "two_column_closeout.pdf")


@pytest.fixture(autouse=True)
def never_call_the_real_vault(monkeypatch):
    """
    Tests must not depend on a Vault running on this machine.

    Default: pretend the Vault created the record. Individual tests
    override this to simulate outages and rejections.
    """
    monkeypatch.setattr(
        api.requests, "post", lambda *a, **k: _FakeResponse(201)
    )


def test_health_reports_service_and_ocr_flag():
    """/health says who it is and whether the OCR fallback is usable."""
    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "reader"
    assert isinstance(body["ocr_available"], bool)


def test_extract_returns_a_record_from_a_real_pdf():
    """A text-layer PDF comes back as a record with the required fields."""
    client = TestClient(create_app())
    response = _post_pdf(
        client, os.path.join(FIXTURES, "two_column_closeout.pdf")
    )
    assert response.status_code == 200
    record = response.json()
    for field in ["id", "client", "client_type", "may_be_named", "outcomes"]:
        assert field in record


def test_extract_empty_file_returns_422():
    """An empty upload is the caller's problem — 422, not a 500."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_extract_corrupt_file_returns_422():
    """Garbage bytes that are not a PDF get a clear 422."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("corrupt.pdf",
                            io.BytesIO(b"this is not a pdf at all"),
                            "application/pdf")},
    )
    assert response.status_code == 422


def test_error_message_names_the_uploaded_file_not_a_temp_path():
    """The caller sent 'empty.pdf'; the error must talk about that name,
    not about whatever temp file the server used internally."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    detail = response.json()["detail"]
    assert "empty.pdf" in detail
    assert "Temp" not in detail and "tmp" not in detail


# ---------------------------------------------------------------------------
# CF-82 — the Reader writes into the Vault
# ---------------------------------------------------------------------------

def test_extracted_record_is_sent_to_the_vault(monkeypatch, real_pdf):
    """The happy path: one POST to the Vault, with the record as its body."""
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse(201)

    monkeypatch.setattr(api.requests, "post", fake_post)
    response = _post_pdf(TestClient(create_app()), real_pdf)

    assert response.status_code == 200
    assert response.headers["X-Vault-Stored"] == "true"
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/engagements")
    assert calls[0]["json"]["id"] == response.json()["id"]
    assert calls[0]["timeout"] == api.VAULT_TIMEOUT_SECONDS


def test_vault_being_down_degrades_but_does_not_fail(monkeypatch, real_pdf):
    """THE CF-82 RULE: a caller must survive its callee being down."""
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(api.requests, "post", refuse)
    response = _post_pdf(TestClient(create_app()), real_pdf)

    assert response.status_code == 200
    assert response.json()["id"]
    assert response.headers["X-Vault-Stored"] == "false"
    assert "unreachable" in response.headers["X-Vault-Detail"]


def test_a_timeout_is_not_retried(monkeypatch, real_pdf):
    """No retry on POST: the first attempt may have stored the record, so
    retrying would risk a duplicate. Safe retries need Idempotency-Key."""
    attempts = []

    def time_out(*args, **kwargs):
        attempts.append(1)
        raise requests.Timeout("took too long")

    monkeypatch.setattr(api.requests, "post", time_out)
    response = _post_pdf(TestClient(create_app()), real_pdf)

    assert response.status_code == 200
    assert len(attempts) == 1


def test_record_already_in_the_vault_is_not_an_error(monkeypatch, real_pdf):
    """409 means the record is already stored — the caller still gets it."""
    monkeypatch.setattr(
        api.requests, "post", lambda *a, **k: _FakeResponse(409)
    )
    response = _post_pdf(TestClient(create_app()), real_pdf)

    assert response.status_code == 200
    assert response.headers["X-Vault-Stored"] == "false"
    assert "already exists" in response.headers["X-Vault-Detail"]


def test_service_token_is_forwarded_to_the_vault(monkeypatch, real_pdf):
    """CF-85: when a token is configured we present it to the Vault."""
    seen = {}

    def capture(url, json=None, headers=None, timeout=None):
        seen.update(headers or {})
        return _FakeResponse(201)

    monkeypatch.setenv("CASEFORGE_TOKEN", "shared-secret")
    monkeypatch.setattr(api.requests, "post", capture)
    _post_pdf(TestClient(create_app()), real_pdf)

    assert seen["Authorization"] == "Bearer shared-secret"


def test_store_false_skips_the_vault_entirely(monkeypatch, real_pdf):
    """?store=false extracts without writing — useful for a dry run."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("the Vault must not be called with store=false")

    monkeypatch.setattr(api.requests, "post", fail_if_called)
    response = _post_pdf(TestClient(create_app()), real_pdf, store=False)

    assert response.status_code == 200
    assert response.headers["X-Vault-Stored"] == "false"


def test_health_names_the_vault_it_writes_to():
    """Operators need to see where this Reader is pointed."""
    body = TestClient(create_app()).get("/health").json()
    assert body["vault_url"] == api.VAULT_URL
