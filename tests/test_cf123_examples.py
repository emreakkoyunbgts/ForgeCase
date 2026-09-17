"""CF-123: the documented examples are what the real routes accept and return."""

import json
import re
from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from common.source import get_vault_client, validate_source
from generator.GeneratorController import app as generator_app
from generator.openapi import EXAMPLE_SOURCE, RECORD_ID, example_draft
from generator.translation import get_translator
from tests.cf123_support import ROOT, json_block, validate
from verifier.VerifierController import app as verifier_app
from verifier.openapi import EXAMPLE_FLAT_DRAFT, EXAMPLE_MCS_DRAFT
from verifier.semantic import get_semantic_checker


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    monkeypatch.setenv("VAULT_URL", "https://vault.test.invalid/base")
    monkeypatch.delenv("CASEFORGE_TOKEN", raising=False)

    async def reject(*args, **kwargs):
        pytest.fail("A test attempted a real HTTP connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject)


def vault_serving(state):
    """A Vault the routes reach over the real client, with no socket involved."""
    def handle(request):
        state["requests"].append(request)
        return state["respond"](request)

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    return override


def client_for(app, overrides):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


class Vault(dict):
    """Mutable so a test can swap the response after the client is built."""

    @property
    def requests(self):
        return self["requests"]


@pytest.fixture
def vault():
    return Vault(
        requests=[],
        respond=lambda request: httpx.Response(200, json=deepcopy(EXAMPLE_SOURCE)),
    )


@pytest.fixture
def generator(vault):
    async def translate(draft, record, language, correlation_id):
        # Stands in for the model: English is returned unchanged and Turkish uses the
        # documented prose. Every other step on the route is the real code path.
        if language == "tr":
            return example_draft("tr")
        return {**draft, "language": language}

    yield from client_for(generator_app, {
        get_vault_client: vault_serving(vault),
        get_translator: lambda: translate,
    })


@pytest.fixture
def semantic():
    return {"calls": 0, "problems": []}


@pytest.fixture
def verifier(vault, semantic):
    async def checker(draft, record, language, correlation_id):
        semantic["calls"] += 1
        return list(semantic["problems"])

    yield from client_for(verifier_app, {
        get_vault_client: vault_serving(vault),
        get_semantic_checker: lambda: checker,
    })


def assert_documented(app, path, method, status, body):
    document = app.openapi()
    block = json_block(document, document["paths"][path][method]["responses"][status])
    validate(document, block["schema"], body)


# --- the synthetic source ----------------------------------------------------------

def test_the_documented_source_is_a_valid_engagement_record():
    assert validate_source(deepcopy(EXAMPLE_SOURCE), RECORD_ID)


# --- Generator ---------------------------------------------------------------------

def test_generate_returns_exactly_the_documented_english_draft(generator, vault):
    response = generator.post("/generate", json={"record_id": RECORD_ID, "language": "en"})

    assert response.status_code == 200
    assert response.json() == example_draft("en")
    assert_documented(generator_app, "/generate", "post", "200", response.json())
    assert str(vault.requests[0].url) == (
        f"https://vault.test.invalid/base/engagements/{RECORD_ID}"
    )


@pytest.mark.parametrize("language", ["en", "de", "tr"])
def test_every_language_returns_a_draft_matching_the_published_schema(generator, language):
    response = generator.post("/generate",
                              json={"record_id": RECORD_ID, "language": language})

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == language
    assert body["engagement_ids"] == [RECORD_ID]
    assert_documented(generator_app, "/generate", "post", "200", body)


def test_page_and_page_ref_carry_the_record_id(generator):
    body = generator.post("/generate", json={"record_id": RECORD_ID}).json()

    pages = {entry["page"] for entries in body["sections"].values() for entry in entries}
    assert pages == {RECORD_ID}
    assert {citation["page_ref"] for citation in body["citations"]} == {RECORD_ID}


@pytest.mark.parametrize("path", [
    "/generator/mcs", "/generator/mcs/eng",
    "/generator/mcs/german", "/generator/mcs/turkish",
])
def test_legacy_adapters_take_a_body_and_still_read_facts_from_vault(generator, vault, path):
    # A poisoned body must not reach the draft: the facts come from Vault.
    response = generator.post(path, json={"id": RECORD_ID, "client": "Invented Bank"})

    assert response.status_code == 200
    assert "Invented Bank" not in response.text
    assert_documented(generator_app, path, "post", "200", response.json())
    assert len(vault.requests) == 1


def test_legacy_adapter_rejects_a_body_without_a_usable_id(generator):
    response = generator.post("/generator/mcs", json={"client": "no id here"})

    assert response.status_code == 422
    assert response.json() == {"detail": "A valid record.id is required"}
    assert_documented(generator_app, "/generator/mcs", "post", "422", response.json())


def test_query_adapter_takes_query_parameters_and_reports_no_match(generator, vault):
    vault["respond"] = lambda request: httpx.Response(
        200, json={"requirements": [{"best_match": None}]}
    )

    response = generator.post("/generator/mcs/query",
                              params={"query": "payments", "language": "de"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No matching engagement was found"}
    assert_documented(generator_app, "/generator/mcs/query", "post", "404", response.json())


def test_blank_query_is_rejected_before_any_dependency(generator, vault):
    response = generator.post("/generator/mcs/query", params={"query": "   "})

    assert response.status_code == 422
    assert response.json() == {"detail": "Query must contain text"}
    assert vault.requests == []


def test_unknown_record_is_reported_as_documented(generator, vault):
    vault["respond"] = lambda request: httpx.Response(404, json={"detail": "nope"})

    response = generator.post("/generate", json={"record_id": "eng-missing"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Source record was not found in Vault"}
    assert_documented(generator_app, "/generate", "post", "404", response.json())


def test_unsupported_language_is_reported_as_a_validation_list(generator):
    response = generator.post("/generate", json={"record_id": RECORD_ID, "language": "fr"})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert_documented(generator_app, "/generate", "post", "422", response.json())


def test_generator_health_is_the_documented_body_and_needs_no_dependency(generator, vault):
    vault["respond"] = lambda request: pytest.fail("Health must not read Vault")

    response = generator.get("/health")

    assert response.json() == {"status": "ok", "service": "generator",
                               "languages": ["en", "de", "tr"]}
    assert_documented(generator_app, "/health", "get", "200", response.json())
    assert vault.requests == []


# --- Verifier ----------------------------------------------------------------------

@pytest.mark.parametrize("draft", [EXAMPLE_FLAT_DRAFT, EXAMPLE_MCS_DRAFT],
                         ids=["flat", "mcs"])
def test_both_documented_draft_shapes_pass(verifier, semantic, draft):
    response = verifier.post("/verify", json={
        "record_id": RECORD_ID, "draft": deepcopy(draft), "language": "en",
    })

    assert response.status_code == 200
    assert response.json() == {"engagement_id": RECORD_ID, "verdict": "PASS",
                               "problems": []}
    assert semantic["calls"] == 1, "a PASS always needs the semantic gate"
    assert_documented(verifier_app, "/verify", "post", "200", response.json())


def test_an_ungrounded_quantity_blocks_with_two_hundred_and_no_model_call(verifier, semantic):
    draft = deepcopy(EXAMPLE_FLAT_DRAFT)
    draft["sections"]["outcomes"] = "Payment latency reduced by 999%"

    response = verifier.post("/verify", json={"record_id": RECORD_ID, "draft": draft})

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "BLOCK"
    assert semantic["calls"] == 0, "a deterministic violation blocks before the provider"
    assert body["problems"][0]["type"] == "ungrounded_number"
    assert body["problems"][0]["value"] == "999%"
    assert_documented(verifier_app, "/verify", "post", "200", body)


def test_an_unknown_citation_reference_blocks_without_a_span(verifier):
    draft = deepcopy(EXAMPLE_MCS_DRAFT)
    draft["citations"][0]["source_ref"] = "not-in-source.pdf"

    body = verifier.post("/verify", json={"record_id": RECORD_ID, "draft": draft}).json()

    assert body["verdict"] == "BLOCK"
    problem = next(p for p in body["problems"] if p["type"] == "invalid_source_reference")
    # This problem carries no `span` or `value`, which is why neither is required.
    assert set(problem) == {"type", "why"}
    assert_documented(verifier_app, "/verify", "post", "200", body)


def test_a_semantic_problem_blocks_and_matches_the_published_problem_schema(verifier, semantic):
    semantic["problems"] = [{"type": "unsupported_claim", "span": "/titles/0/title",
                             "value": "payments for retail bank", "why": "uncertain"}]

    body = verifier.post("/verify", json={
        "record_id": RECORD_ID, "draft": deepcopy(EXAMPLE_FLAT_DRAFT),
    }).json()

    assert body["verdict"] == "BLOCK"
    assert_documented(verifier_app, "/verify", "post", "200", body)


def test_draft_bound_to_another_source_is_a_validation_list(verifier):
    draft = deepcopy(EXAMPLE_FLAT_DRAFT)
    draft["engagement_id"] = "eng-somewhere-else"

    response = verifier.post("/verify", json={"record_id": RECORD_ID, "draft": draft})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert_documented(verifier_app, "/verify", "post", "422", response.json())


def test_legacy_route_reports_identity_conflicts_as_a_string(verifier, vault):
    response = verifier.post(f"/verify/{RECORD_ID}", json={
        "record": {"id": "eng-somewhere-else"}, "mcs": deepcopy(EXAMPLE_FLAT_DRAFT),
    })

    assert response.status_code == 422
    assert response.json() == {"detail": "record.id must match the path record_id"}
    assert_documented(verifier_app, "/verify/{record_id}", "post", "422", response.json())
    assert vault.requests == []


def test_legacy_route_ignores_submitted_record_facts(verifier, vault):
    response = verifier.post(f"/verify/{RECORD_ID}", json={
        "record": {"id": RECORD_ID, "client": "Invented Bank",
                   "outcomes": [{"metric": "anything", "source_ref": "made-up"}]},
        "mcs": deepcopy(EXAMPLE_FLAT_DRAFT),
    })

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
    assert len(vault.requests) == 1, "the authoritative record still comes from Vault"
    assert_documented(verifier_app, "/verify/{record_id}", "post", "200", response.json())


def test_verifier_health_is_the_documented_body_and_needs_no_dependency(verifier, vault):
    vault["respond"] = lambda request: pytest.fail("Health must not read Vault")

    response = verifier.get("/health")

    assert response.json() == {"status": "ok"}
    assert_documented(verifier_app, "/health", "get", "200", response.json())
    assert vault.requests == []


# --- shared header and credential behaviour ----------------------------------------

@pytest.fixture(params=["generator", "verifier"])
def any_service(request, generator, verifier):
    return {"generator": (generator_app, generator),
            "verifier": (verifier_app, verifier)}[request.param]


def test_a_submitted_trace_is_echoed_even_when_it_is_not_a_uuid(any_service):
    _, client = any_service

    response = client.get("/health", headers={"X-Correlation-ID": "cf123-not-a-uuid"})

    assert response.headers["X-Correlation-ID"] == "cf123-not-a-uuid"


def test_a_missing_or_empty_trace_is_generated(any_service):
    _, client = any_service
    for headers in ({}, {"X-Correlation-ID": ""}):
        UUID(client.get("/health", headers=headers).headers["X-Correlation-ID"])


def test_the_documented_header_limit_is_the_real_one(any_service):
    app, client = any_service
    assert client.get("/health", headers={"X-Correlation-ID": "x" * 4096}).status_code == 200

    response = client.get("/health", headers={"X-Correlation-ID": "x" * 4097})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid HTTP tracing or authorization header"}
    assert_documented(app, "/health", "get", "400", response.json())
    UUID(response.headers["X-Correlation-ID"])


def test_the_trace_is_forwarded_to_the_source_read(generator, vault):
    generator.post("/generate", json={"record_id": RECORD_ID},
                   headers={"X-Correlation-ID": "cf123-trace"})

    assert vault.requests[0].headers["X-Correlation-ID"] == "cf123-trace"


def test_an_idempotency_key_is_validated_but_never_reaches_vault(generator, vault):
    generator.post("/generate", json={"record_id": RECORD_ID},
                   headers={"Idempotency-Key": "cf123-key"})

    assert "Idempotency-Key" not in vault.requests[0].headers
    assert generator.get("/health",
                         headers={"Idempotency-Key": "x" * 4097}).status_code == 400


def test_an_incoming_credential_wins_and_the_service_token_is_the_fallback(
    generator, vault, monkeypatch
):
    generator.post("/generate", json={"record_id": RECORD_ID},
                   headers={"Authorization": "Bearer caller-token"})
    assert vault.requests[-1].headers["Authorization"] == "Bearer caller-token"

    monkeypatch.setenv("CASEFORGE_TOKEN", "service-token")
    generator.post("/generate", json={"record_id": RECORD_ID})
    assert vault.requests[-1].headers["Authorization"] == "Bearer service-token"


def test_a_denied_source_read_is_propagated_as_documented(generator, vault):
    vault["respond"] = lambda request: httpx.Response(403, json={"detail": "no"})

    response = generator.post("/generate", json={"record_id": RECORD_ID})

    assert response.status_code == 403
    assert response.json() == {"detail": "Vault denied access to the source record"}
    assert_documented(generator_app, "/generate", "post", "403", response.json())


# --- the runbook -------------------------------------------------------------------

RUNBOOK = ROOT / "docs" / "CF-123-runbook.md"

# Every marked block in the runbook, and the contract it has to satisfy.
# (app, path, method, status) — status None means the request body.
RUNBOOK_BLOCKS = {
    "health-generator": (generator_app, "/health", "get", "200"),
    "health-verifier": (verifier_app, "/health", "get", "200"),
    "generate-request": (generator_app, "/generate", "post", None),
    "generate-response-en": (generator_app, "/generate", "post", "200"),
    "verify-request": (verifier_app, "/verify", "post", None),
    "verify-response-pass": (verifier_app, "/verify", "post", "200"),
    "verify-response-block": (verifier_app, "/verify", "post", "200"),
    "error-not-found": (generator_app, "/generate", "post", "404"),
    "error-language": (generator_app, "/generate", "post", "422"),
    "error-identity": (verifier_app, "/verify", "post", "422"),
    "error-legacy-identity": (verifier_app, "/verify/{record_id}", "post", "422"),
}


def runbook_blocks():
    """Marked JSON blocks, keyed by the `<!-- cf123:NAME -->` comment above them."""
    pattern = re.compile(r"<!-- cf123:([a-z0-9-]+) -->\s*```json\n(.*?)```", re.DOTALL)
    text = RUNBOOK.read_text(encoding="utf-8")
    return {name: json.loads(body) for name, body in pattern.findall(text)}


def test_every_runbook_block_is_claimed_by_this_test():
    found = set(runbook_blocks())
    expected = set(RUNBOOK_BLOCKS) | {"source-record"}
    assert found == expected, "a marked block was added or removed without a check"


def test_the_runbook_source_record_is_the_documented_one():
    assert runbook_blocks()["source-record"] == EXAMPLE_SOURCE
    assert validate_source(runbook_blocks()["source-record"], RECORD_ID)


@pytest.mark.parametrize("name", sorted(RUNBOOK_BLOCKS))
def test_every_runbook_block_satisfies_its_published_schema(name):
    app, path, method, status = RUNBOOK_BLOCKS[name]
    document = app.openapi()
    operation = document["paths"][path][method]
    if status is None:
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
    else:
        schema = json_block(document, operation["responses"][status])["schema"]
    validate(document, schema, runbook_blocks()[name])


def test_the_runbook_draft_is_exactly_what_generate_returns(generator):
    body = generator.post("/generate",
                          json=runbook_blocks()["generate-request"]).json()

    assert body == runbook_blocks()["generate-response-en"]


def test_the_runbook_verify_request_really_passes(verifier):
    request = runbook_blocks()["verify-request"]

    response = verifier.post("/verify", json=request)

    assert response.json() == runbook_blocks()["verify-response-pass"]


def test_the_runbook_block_example_is_what_the_route_really_returns(verifier, semantic):
    request = deepcopy(runbook_blocks()["verify-request"])
    request["draft"]["sections"]["outcomes"] = "Payment latency reduced by 999%"

    body = verifier.post("/verify", json=request).json()

    assert body == runbook_blocks()["verify-response-block"]
    assert semantic["calls"] == 0, "the runbook says this blocks without a model call"


def test_the_runbook_never_publishes_a_credential():
    text = RUNBOOK.read_text(encoding="utf-8")
    for leaked in ("sk-", "Bearer ey", "OPENAI_API_KEY=", "CASEFORGE_TOKEN="):
        assert leaked not in text, f"the runbook must not contain {leaked!r}"
