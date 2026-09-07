"""CF-100 contract checks across real Verifier and Vault ASGI routes.

Only Vault's storage read is replaced with synthetic in-memory data. Neither
application is started as a server, and no database or corpus is touched.
"""

from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from vault import vault
from verifier.VerifierController import app
from verifier.service import get_vault_client


RECORD_ID = "eng-contract-synthetic"


@pytest.fixture
def source():
    return {
        "id": RECORD_ID,
        "client": "Synthetic Contract Bank",
        "client_type": "retail bank",
        "may_be_named": False,
        "domain": "payments",
        "region": "TR",
        "challenge": "Slow payment processing.",
        "solution": "Optimised payment processing.",
        "technologies": ["Python"],
        "outcomes": [
            {"metric": "Payment latency reduced by 45%", "source_ref": "synthetic-memory"}
        ],
    }


@pytest.fixture
def draft():
    return {
        "engagement_id": RECORD_ID,
        "sections": {
            "context": "A retail bank in TR.",
            "outcomes": "Payment latency reduced by 45%.",
        },
    }


@pytest.fixture
def mesh(monkeypatch, source):
    monkeypatch.setenv("VAULT_URL", "http://vault.contract.invalid")
    monkeypatch.setenv("CASEFORGE_TOKEN", "cf-contract-synthetic-token")
    observed = SimpleNamespace(reads=[], requests=[], responses=[])

    def read_source(engagement_id, as_of=None):
        observed.reads.append((engagement_id, as_of))
        return deepcopy(source) if engagement_id == RECORD_ID else None

    monkeypatch.setattr(vault, "get", read_source)
    # create_app only constructs routes/auth; /health would open the database,
    # so this fixture only calls the real GET /engagements/{id} route.
    vault_app = vault.create_app()

    async def capture_request(request):
        observed.requests.append(request)

    async def capture_response(response):
        await response.aread()
        observed.responses.append(response)

    async def local_vault_client():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=vault_app),
            event_hooks={"request": [capture_request], "response": [capture_response]},
        ) as client:
            yield client

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_vault_client] = local_vault_client
    try:
        with TestClient(app) as client:
            yield client, observed
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_verify_consumes_real_vault_record_response(mesh, source, draft):
    client, observed = mesh

    response = client.post(
        "/verify",
        json={"record_id": RECORD_ID, "draft": draft},
        headers={"X-Correlation-ID": "cf-contract-request"},
    )

    assert response.status_code == 200
    assert response.json() == {"engagement_id": RECORD_ID, "verdict": "PASS", "problems": []}
    assert observed.reads == [(RECORD_ID, None)]
    assert len(observed.requests) == len(observed.responses) == 1
    assert observed.requests[0].method == "GET"
    assert observed.requests[0].url.path == f"/engagements/{RECORD_ID}"
    assert observed.requests[0].headers["X-Correlation-ID"] == "cf-contract-request"
    assert observed.responses[0].status_code == 200
    # Vault returns the record directly, including its ETag, with no wrapper.
    assert observed.responses[0].json() == source
    assert observed.responses[0].headers["ETag"] == f'"{vault.etag_for(source)}"'
    assert response.headers["X-Correlation-ID"] == "cf-contract-request"


@pytest.mark.parametrize(
    ("prose", "problem_type"),
    [
        ("Payment latency reduced by 99%.", "ungrounded_number"),
        ("Synthetic Contract Bank improved processing.", "client_named_without_consent"),
    ],
)
def test_verify_blocks_against_real_vault_source(mesh, draft, prose, problem_type):
    client, observed = mesh
    draft["sections"]["outcomes"] = prose

    response = client.post("/verify", json={"record_id": RECORD_ID, "draft": draft})

    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK"
    assert problem_type in {problem["type"] for problem in response.json()["problems"]}
    assert observed.reads == [(RECORD_ID, None)]
    assert observed.responses[0].status_code == 200


def test_verify_propagates_real_vault_missing_record(mesh, draft):
    client, observed = mesh
    missing_id = "eng-contract-missing"
    draft["engagement_id"] = missing_id

    response = client.post("/verify", json={"record_id": missing_id, "draft": draft})

    assert response.status_code == 404
    assert "verdict" not in response.json()
    assert observed.reads == [(missing_id, None)]
    assert observed.responses[0].status_code == 404
    assert observed.responses[0].json() == {"detail": f"no engagement with id '{missing_id}'"}


def test_verify_forwards_credentials_accepted_by_real_vault(mesh, draft):
    client, observed = mesh

    response = client.post(
        "/verify",
        json={"record_id": RECORD_ID, "draft": draft},
        headers={"Authorization": "Bearer cf-contract-synthetic-token"},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
    assert observed.reads == [(RECORD_ID, None)]
    assert observed.responses[0].status_code == 200


@pytest.mark.parametrize("authorization", ["Bearer deliberately-invalid", "Basic invalid"])
def test_verify_respects_real_vault_auth_rejection(mesh, draft, authorization):
    client, observed = mesh

    response = client.post(
        "/verify",
        json={"record_id": RECORD_ID, "draft": draft},
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "verdict" not in response.json()
    assert observed.reads == []
    assert len(observed.responses) == 1
    assert observed.responses[0].status_code == 401
    assert observed.responses[0].headers["WWW-Authenticate"] == "Bearer"
