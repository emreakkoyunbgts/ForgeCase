"""Focused regressions for the service boundary defects found by CF-120.

Dependency status cases use a real local HTTP socket with valid JSON even on
redirects, so parsing a plausible body cannot conceal a rejected response.
"""
import importlib.util
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import UUID

import pytest
import requests
from fastapi.testclient import TestClient

from analyst import api as analyst
from common.services import request_headers
from librarian import service as librarian
from verifier import VerifierController as verifier


@pytest.fixture(autouse=True)
def isolated_service_env(monkeypatch):
    monkeypatch.delenv("CASEFORGE_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")


@pytest.fixture
def vault_boundary():
    state = SimpleNamespace(status=200, body={"items": [], "total": 0}, requests=[])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state.requests.append({"path": self.requestline.split()[1], "headers": dict(self.headers)})
            body = json.dumps(state.body).encode("utf-8")
            # A followed redirect reaches a success payload: both following and
            # accepting the original response must be caught by the regression.
            self.send_response(200 if self.path == "/redirect-target" else state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Location", "/redirect-target")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("name", ["X-Correlation-ID", "Authorization", "Idempotency-Key"])
@pytest.mark.parametrize("value", [b"x" * 4097, b"invalid\x1fvalue", b"invalid\xffvalue"],
                         ids=["oversized", "control-character", "non-ascii"])
def test_verifier_rejects_invalid_shared_headers_before_route(name, value):
    with TestClient(verifier.app) as client:
        response = client.post("/verify", json={}, headers=[(name.encode(), value)])
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid HTTP tracing or authorization header"}
    UUID(response.headers["X-Correlation-ID"])


@pytest.mark.parametrize("name", ["X-Correlation-ID", "Authorization", "Idempotency-Key"])
def test_verifier_accepts_shared_header_at_4096_boundary(name):
    with TestClient(verifier.app) as client:
        response = client.get("/health", headers={name: "x" * 4096})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    if name == "X-Correlation-ID":
        assert response.headers[name] == "x" * 4096


def test_verifier_logs_validation_failure_with_trace_and_keeps_input_private(caplog):
    caplog.set_level(logging.INFO, logger="common.services")
    with TestClient(verifier.app) as client:
        response = client.post("/verify", json={"draft": {"secret": "private-draft"}},
                               headers={"X-Correlation-ID": "cf120-invalid-draft"})
    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"] == "cf120-invalid-draft"
    assert "private-draft" not in response.text
    assert "POST /verify status=422 correlation_id=cf120-invalid-draft" in caplog.text


def test_verifier_inherits_all_shared_headers_and_resets_between_calls(monkeypatch):
    seen = []

    async def source(record_id, client, correlation_id, authorization):
        seen.append(request_headers())
        return {"id": record_id, "client": "Private Bank", "client_type": "retail bank",
                "may_be_named": False, "domain": "payments", "region": "TR",
                "challenge": "Slow payments.", "solution": "Faster payments.",
                "technologies": [], "outcomes": []}

    monkeypatch.setattr(verifier, "get_record_from_vault", source)
    payload = {"record_id": "eng-cf120-headers", "draft": {"sections": {
        "outcomes": "Unsupported savings of 999%."}}}
    supplied = {"X-Correlation-ID": "cf120-headers", "Authorization": "Bearer caller",
                "Idempotency-Key": "cf120-key"}
    with TestClient(verifier.app) as client:
        first = client.post("/verify", json=payload, headers=supplied)
        second = client.post("/verify", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["verdict"] == second.json()["verdict"] == "BLOCK"
    assert seen[0] == supplied
    assert seen[1] == {"X-Correlation-ID": second.headers["X-Correlation-ID"]}
    assert seen[1]["X-Correlation-ID"] != supplied["X-Correlation-ID"]


def test_analyst_trailing_slash_config_calls_canonical_vault_path(monkeypatch, vault_boundary):
    monkeypatch.setenv("VAULT_URL", vault_boundary.url + "/")
    # A fresh module import exercises the environment-based startup setting
    # without reloading and replacing the app used by unrelated test modules.
    spec = importlib.util.spec_from_file_location("cf120_analyst_config", analyst.__file__)
    configured = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configured)
    assert configured.VAULT_URL == vault_boundary.url
    with TestClient(configured.app) as client:
        response = client.get("/coverage")
    assert response.status_code == 200
    assert len(vault_boundary.requests) == 1
    assert vault_boundary.requests[0]["path"] == "/engagements?limit=100&offset=0"


@pytest.mark.parametrize("service,path", [(analyst, "/coverage"), (librarian, "/search?q=payments")])
@pytest.mark.parametrize("status", [201, 302, 307])
def test_vault_non_200_payload_is_rejected_without_redirect(service, path, status,
                                                            monkeypatch, vault_boundary):
    monkeypatch.setattr(service, "VAULT_URL", vault_boundary.url)
    vault_boundary.status = status
    with TestClient(service.app) as client:
        response = client.get(path, headers={"Authorization": "Bearer caller",
                                            "X-Correlation-ID": "cf120-dependency"})
    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "vault_error"
    assert response.headers["X-Correlation-ID"] == "cf120-dependency"
    assert len(vault_boundary.requests) == 1
    assert vault_boundary.requests[0]["headers"]["Authorization"] == "Bearer caller"
    assert "/redirect-target" not in vault_boundary.requests[0]["path"]


@pytest.mark.parametrize("service,path", [(analyst, "/coverage"), (librarian, "/search?q=payments")])
@pytest.mark.parametrize("status", [401, 403, 404, 500, 503, 504])
def test_vault_failure_status_and_retry_contract_is_preserved(service, path, status,
                                                              monkeypatch, vault_boundary):
    monkeypatch.setattr(service, "VAULT_URL", vault_boundary.url)
    vault_boundary.status = status
    with TestClient(service.app) as client:
        response = client.get(path)
    if service is librarian and status >= 500:
        expected_status, expected_calls, error = 503, librarian.VAULT_MAX_RETRIES + 1, "vault_page_failed"
    else:
        expected_status = status if status in {401, 403, 404, 503, 504} else 502
        expected_calls, error = 1, "vault_error"
    assert response.status_code == expected_status
    detail = response.json()["detail"]
    assert detail["error"] == error
    assert set(detail) == ({"error", "offset", "message"} if service is librarian else {"error", "message"})
    assert vault_boundary.url not in response.text
    assert len(vault_boundary.requests) == expected_calls


@pytest.mark.parametrize("service,path", [(analyst, "/coverage"), (librarian, "/search?q=payments")])
@pytest.mark.parametrize("failure,status", [(requests.ConnectionError, 503), (requests.Timeout, 504)])
def test_dependency_transport_error_keeps_safe_public_envelope(service, path, failure, status, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise failure("http://private-vault.invalid/internal?token=private-token")

    monkeypatch.setattr(service.requests, "get", fail)
    with TestClient(service.app) as client:
        response = client.get(path)
    assert response.status_code == status
    detail = response.json()["detail"]
    if service is analyst and failure is requests.Timeout:
        assert detail == {"error": "vault_timeout"}
    else:
        assert set(detail) == ({"error", "offset", "message"} if service is librarian else {"error", "message"})
    assert "private-vault" not in response.text
    assert "private-token" not in response.text
    assert len(calls) == (librarian.VAULT_MAX_RETRIES + 1 if service is librarian else 1)


@pytest.mark.parametrize("service", ["vault", "reader", "librarian"])
def test_invalid_source_document_or_rfp_does_not_echo_private_input(service, monkeypatch, tmp_path):
    from reader.api import create_app as reader_app
    from vault import vault

    private = "CF120-SYNTHETIC-PRIVATE-INPUT"
    monkeypatch.setattr(vault, "DB_PATH", str(tmp_path / "vault.db"))
    monkeypatch.setenv("CASEFORGE_TOKEN", "cf120-privacy-local")
    cases = {
        "vault": (vault.create_app, "/engagements", {"json": [{"client": private}]}),
        "reader": (reader_app, "/extract", {"data": {"document": private}}),
        "librarian": (librarian.create_app, "/match", {"json": {"rfp_text": {"source": private}}}),
    }
    factory, path, kwargs = cases[service]
    with TestClient(factory()) as client:
        response = client.post(path, headers={"Authorization": "Bearer cf120-privacy-local",
                                             "X-Correlation-ID": "cf120-privacy"}, **kwargs)
    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"] == "cf120-privacy"
    assert private not in response.text
    assert isinstance(response.json()["detail"], list) and response.json()["detail"]
    assert all(set(error) == {"loc", "msg", "type"} for error in response.json()["detail"])
