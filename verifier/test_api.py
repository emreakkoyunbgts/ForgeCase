"""CF-100 HTTP gate tests using synthetic data and an in-memory Vault transport."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from common.contract import REQUIRED_FIELDS
from verifier.VerifierController import app
from verifier.service import get_vault_client


RECORD_ID = "eng-synthetic"
PRIVATE_MARKER = "synthetic-vault-private-marker"


@pytest.fixture
def record():
    return {
        "id": RECORD_ID,
        "client": "Synthetic Example Bank",
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
        "private_note": PRIVATE_MARKER,
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


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    monkeypatch.setenv("VAULT_URL", "https://vault.test.invalid/base/")
    monkeypatch.delenv("CASEFORGE_TOKEN", raising=False)

    def reject_network(*args, **kwargs):
        pytest.fail("A test attempted a real HTTP connection")

    async def reject_async_network(*args, **kwargs):
        pytest.fail("A test attempted a real HTTP connection")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_network)


@pytest.fixture
def api(record):
    vault = SimpleNamespace(
        requests=[],
        respond=lambda request: httpx.Response(200, json=deepcopy(record)),
    )

    def handle(request):
        vault.requests.append(request)
        return vault.respond(request)

    async def override_vault_client():
        # Deliberately permissive defaults expose missing per-request safeguards.
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), timeout=73.0, follow_redirects=True
        ) as client:
            yield client

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_vault_client] = override_vault_client
    try:
        with TestClient(app) as client:
            yield client, vault
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def post_draft(client, draft, **kwargs):
    return client.post("/verify", json={"record_id": RECORD_ID, "draft": draft}, **kwargs)


def test_grounded_draft_passes_using_vault_facts(api, draft):
    client, vault = api
    response = post_draft(client, draft, headers={"X-Correlation-ID": "cf100-synthetic"})

    assert response.status_code == 200
    assert response.json() == {"engagement_id": RECORD_ID, "verdict": "PASS", "problems": []}
    assert response.headers["X-Correlation-ID"] == "cf100-synthetic"
    assert len(vault.requests) == 1
    request = vault.requests[0]
    assert request.method == "GET"
    assert str(request.url) == f"https://vault.test.invalid/base/engagements/{RECORD_ID}"
    assert request.headers["X-Correlation-ID"] == "cf100-synthetic"
    assert set(request.extensions["timeout"].values()) == {5.0}
    assert PRIVATE_MARKER not in response.text


@pytest.mark.parametrize(
    ("prose", "problem_type"),
    [
        ("Payment latency reduced by 42%.", "ungrounded_number"),
        ("Synthetic Example Bank improved processing.", "client_named_without_consent"),
    ],
)
def test_real_verifier_blocks_invented_facts_and_missing_consent(api, draft, prose, problem_type):
    client, _ = api
    draft["sections"]["outcomes"] = prose

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK"
    assert problem_type in {problem["type"] for problem in response.json()["problems"]}


def test_real_verifier_blocks_nonnumeric_fact_absent_from_vault(api, draft):
    client, _ = api
    draft["sections"]["approach"] = "The platform was migrated to COBOL."

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK"
    assert any(
        problem["type"] == "unsupported_vocabulary" and problem["value"] == "cobol"
        for problem in response.json()["problems"]
    )


def test_missing_marker_makes_no_unsupported_fact_claim(api, record, draft):
    client, _ = api
    record["outcomes"] = []
    draft["sections"]["outcomes"] = "[MISSING: measurable outcomes]"

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"


def test_invented_number_in_title_is_blocked(api, draft):
    client, _ = api
    draft["title"] = "Saved 777%"

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK"
    assert any(problem.get("type") == "ungrounded_number" and problem.get("value") == "777%"
               for problem in response.json()["problems"])


def test_synthetic_poisoned_draft_blocks_all_inventions_without_rejecting_true_figures(api, record, draft):
    client, _ = api
    record["duration_months"] = 11
    record["outcomes"].extend([
        {"metric": "Batch processing completed in 6 hours", "source_ref": "synthetic-memory"},
        {"metric": "Approval took 90 minutes", "source_ref": "synthetic-memory"},
    ])
    draft["sections"]["context"] = "Synthetic Example Bank completed the work in 3 months in 2019."
    draft["sections"]["outcomes"] = (
        "Cost savings reached 42% and satisfaction increased by 300%. "
        "Payment latency reduced by 45%, with batch processing in 6 hours "
        "and approval in 90 minutes. The source schedule was 11 months."
    )

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK"
    flagged = {problem.get("value") for problem in response.json()["problems"]
               if isinstance(problem.get("value"), str)}
    assert {"42%", "300%", "3", "2019", record["client"]} <= flagged
    assert {"45%", "6", "90", "11"}.isdisjoint(flagged)


def test_generator_single_source_mcs_shape_is_supported(api):
    client, _ = api
    mcs = {
        "engagement_ids": [RECORD_ID],
        "sections": {
            "outcomes": [{"outcomes": "Payment latency reduced by 45%.", "page": RECORD_ID}]
        },
    }

    response = post_draft(client, mcs)

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"


def test_explicit_vault_consent_allows_client_name(api, record, draft):
    client, _ = api
    record["may_be_named"] = True
    draft["sections"]["context"] = "Synthetic Example Bank in TR."

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"


def test_legacy_body_cannot_replace_vault_facts_or_consent(api, record, draft):
    client, vault = api
    forged = deepcopy(record)
    forged["may_be_named"] = True
    forged["outcomes"] = [{"metric": "Payment latency reduced by 42%"}]
    draft["sections"]["outcomes"] = "Synthetic Example Bank reduced payment latency by 42%."

    response = client.post(f"/verify/{RECORD_ID}", json={"record": forged, "mcs": draft})

    assert response.status_code == 200
    assert response.json()["engagement_id"] == RECORD_ID
    assert response.json()["verdict"] == "BLOCK"
    problems = {problem["type"] for problem in response.json()["problems"]}
    assert {"ungrounded_number", "client_named_without_consent"} <= problems
    assert len(vault.requests) == 1
    assert vault.requests[0].url.path.endswith(f"/engagements/{RECORD_ID}")


def test_optional_vault_fields_are_preserved_for_core_grounding(api, record, draft):
    client, _ = api
    record["supports_qualitative_claims"] = True
    draft["sections"]["context"] = "The work was a huge success."

    response = post_draft(client, draft)

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"


@pytest.mark.parametrize("invalid_draft", [None, [], {}, {"sections": {}}, {"sections": "prose"},
    {"sections": {"context": "  "}}, {"sections": {"outcomes": []}},
    {"sections": {"outcomes": 45}}, {"sections": {"outcomes": {}}}])
def test_malformed_or_empty_draft_never_reaches_vault(api, invalid_draft):
    client, vault = api

    response = post_draft(client, invalid_draft, headers={"X-Correlation-ID": "invalid-draft"})

    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"] == "invalid-draft"
    assert vault.requests == []


def test_metadata_without_case_study_sections_is_rejected(api):
    client, vault = api

    response = post_draft(client, {"sections": {"engagement_id": RECORD_ID}})

    assert response.status_code == 422
    assert vault.requests == []


@pytest.mark.parametrize("location", ["sections", "titles"])
def test_nested_mcs_source_reference_must_match_record(api, location):
    client, vault = api
    mcs = {
        "engagement_ids": [RECORD_ID],
        "titles": [{"title": "A retail bank", "page": RECORD_ID}],
        "sections": {"context": [{"region": "A retail bank in TR.", "page": RECORD_ID}]},
    }
    if location == "sections":
        mcs["sections"]["context"][0]["page"] = "different-id"
    else:
        mcs["titles"][0]["page"] = "different-id"

    response = post_draft(client, mcs)

    assert response.status_code == 422
    assert vault.requests == []


def test_excessive_draft_nesting_is_rejected_before_vault(api):
    client, vault = api
    prose = "A retail bank in TR."
    for _ in range(100):
        prose = [prose]

    response = post_draft(client, {"sections": {"context": prose}})

    assert response.status_code == 422
    assert vault.requests == []


@pytest.mark.parametrize("record_id", [None, "", "  ", 123, "..", "../other", "a\\b"])
def test_invalid_record_id_never_reaches_vault(api, draft, record_id):
    client, vault = api

    response = client.post("/verify", json={"record_id": record_id, "draft": draft})

    assert response.status_code == 422
    UUID(response.headers["X-Correlation-ID"])
    assert vault.requests == []


def test_missing_required_input_never_reaches_vault(api, draft):
    client, vault = api

    for body in ({"draft": draft}, {"record_id": RECORD_ID}):
        response = client.post("/verify", json=body)
        assert response.status_code == 422
        assert response.headers["X-Correlation-ID"]
    assert vault.requests == []


@pytest.mark.parametrize(
    "identity", [{"engagement_id": "other"}, {"engagement_ids": ["other"]},
    {"engagement_ids": [RECORD_ID, "other"]}, {"engagement_ids": []}]
)
def test_draft_cannot_claim_different_or_multiple_sources(api, draft, identity):
    client, vault = api
    draft.update(identity)

    response = post_draft(client, draft)

    assert response.status_code == 422
    assert vault.requests == []


@pytest.mark.parametrize("body_id", [None, "other"])
def test_legacy_source_id_must_match_path(api, record, draft, body_id):
    client, vault = api
    forged = deepcopy(record)
    if body_id is None:
        forged.pop("id")
    else:
        forged["id"] = body_id

    response = client.post(f"/verify/{RECORD_ID}", json={"record": forged, "mcs": draft})

    assert response.status_code == 422
    assert vault.requests == []


@pytest.mark.parametrize(
    ("incoming", "configured", "expected"),
    [("Bearer synthetic-caller", "synthetic-service", "Bearer synthetic-caller"),
     (None, "synthetic-service", "Bearer synthetic-service"), (None, None, None)],
)
def test_vault_auth_uses_incoming_header_then_service_token(api, draft, monkeypatch,
                                                         incoming, configured, expected):
    client, vault = api
    if configured is not None:
        monkeypatch.setenv("CASEFORGE_TOKEN", configured)

    response = post_draft(client, draft, headers={"Authorization": incoming} if incoming else {})

    assert response.status_code == 200
    assert vault.requests[0].headers.get("Authorization") == expected


def test_generated_correlation_id_is_forwarded_and_returned(api, draft):
    client, vault = api

    response = post_draft(client, draft)

    assert response.status_code == 200
    correlation_id = response.headers["X-Correlation-ID"]
    UUID(correlation_id)
    assert vault.requests[0].headers["X-Correlation-ID"] == correlation_id


@pytest.mark.parametrize("header_name", [b"X-Correlation-ID", b"Authorization"])
def test_non_ascii_forwarded_headers_fail_safely_before_vault(api, draft, header_name):
    client, vault = api

    response = post_draft(client, draft, headers=[(header_name, b"\xff")])

    assert response.status_code == 400
    UUID(response.headers["X-Correlation-ID"])
    assert response.json()["detail"]
    assert response.json()["detail"].isascii()
    assert vault.requests == []


@pytest.mark.parametrize(("upstream_status", "expected_status"),
                         [(404, 404), (401, 401), (403, 403), (500, 502), (503, 502)])
def test_vault_http_failures_preserve_safe_status_and_correlation(api, draft,
                                                               upstream_status, expected_status):
    client, vault = api
    vault.respond = lambda request: httpx.Response(upstream_status, text=PRIVATE_MARKER)

    response = post_draft(client, draft, headers={"X-Correlation-ID": "upstream-failure"})

    assert response.status_code == expected_status
    assert response.headers["X-Correlation-ID"] == "upstream-failure"
    assert "detail" in response.json()
    assert PRIVATE_MARKER not in response.text
    assert len(vault.requests) == 1
    if expected_status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(("error", "expected_status"),
                         [(httpx.ReadTimeout, 504), (httpx.ConnectError, 503)])
def test_vault_transport_failures_fail_closed(api, draft, error, expected_status):
    client, vault = api

    def fail(request):
        raise error(PRIVATE_MARKER, request=request)

    vault.respond = fail
    response = post_draft(client, draft)

    assert response.status_code == expected_status
    UUID(response.headers["X-Correlation-ID"])
    assert PRIVATE_MARKER not in response.text
    assert "verdict" not in response.json()
    assert len(vault.requests) == 1


def test_vault_redirect_is_rejected_without_forwarding_auth_to_target(api, draft):
    client, vault = api
    vault.respond = lambda request: httpx.Response(
        302, headers={"Location": "https://untrusted.test.invalid/records"}
    )

    response = post_draft(client, draft, headers={"Authorization": "Bearer synthetic-caller"})

    assert response.status_code == 502
    assert len(vault.requests) == 1
    assert vault.requests[0].url.host == "vault.test.invalid"


def test_non_json_vault_response_fails_closed(api, draft):
    client, vault = api
    vault.respond = lambda request: httpx.Response(200, text=PRIVATE_MARKER)

    response = post_draft(client, draft)

    assert response.status_code == 502
    assert PRIVATE_MARKER not in response.text
    assert "verdict" not in response.json()


@pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
def test_incomplete_vault_record_cannot_produce_pass(api, record, draft, missing_field):
    client, _ = api
    record.pop(missing_field)

    response = post_draft(client, draft)

    assert response.status_code == 502
    assert PRIVATE_MARKER not in response.text
    assert "verdict" not in response.json()


@pytest.mark.parametrize("patch", [
    {"id": "other"}, {"may_be_named": "false"}, {"may_be_named": 0},
    {"may_be_named": None}, {"client": ""}, {"client": None},
    {"outcomes": "invalid"}, {"outcomes": ["invalid"]},
    {"outcomes": [{"metric": 45}]},
    {"outcomes": [{"metric": "Payment latency reduced by 45%"}]},
    {"outcomes": [{"metric": "Payment latency reduced by 45%", "source_ref": ""}]},
    {"supports_qualitative_claims": "false"},
])
def test_invalid_vault_field_types_or_identity_fail_closed(api, record, draft, patch):
    client, _ = api
    record.update(patch)

    response = post_draft(client, draft)

    assert response.status_code == 502
    assert PRIVATE_MARKER not in response.text
    assert "verdict" not in response.json()


def test_vault_response_must_be_a_record_object(api, draft):
    client, vault = api
    vault.respond = lambda request: httpx.Response(200, json=[])

    response = post_draft(client, draft)

    assert response.status_code == 502


def test_health_is_live_without_vault(api):
    client, vault = api
    vault.respond = lambda request: pytest.fail("Health must not query Vault")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert vault.requests == []


def test_openapi_describes_canonical_input_and_shared_verdict_contract(api):
    client, vault = api
    schema = client.get("/openapi.json").json()

    def resolve(node):
        while "$ref" in node:
            node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
        return node

    operation = schema["paths"]["/verify"]["post"]
    request = resolve(operation["requestBody"]["content"]["application/json"]["schema"])
    response = resolve(operation["responses"]["200"]["content"]["application/json"]["schema"])

    assert set(request["required"]) == {"record_id", "draft"}
    assert set(response["required"]) == {"engagement_id", "verdict", "problems"}
    assert set(response["properties"]) == {"engagement_id", "verdict", "problems"}
    assert set(resolve(response["properties"]["verdict"])["enum"]) == {"PASS", "BLOCK"}
    assert "get" in schema["paths"]["/health"]
    assert vault.requests == []
