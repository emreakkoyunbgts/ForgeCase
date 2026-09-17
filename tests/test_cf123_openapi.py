"""CF-123: the published Generator and Verifier contracts describe the real behaviour."""

import json
import re
from copy import deepcopy

import pytest

from generator.GeneratorController import app as generator_app
from generator.openapi import RECORD_ID
from tests.cf123_support import (
    SERVICES,
    dereference,
    documented_examples,
    json_block,
    snapshot,
    validate,
)
from verifier.VerifierController import app as verifier_app

APPS = {"generator": generator_app, "verifier": verifier_app}

# The route surface CF-123 documents. Enrichment must not add or drop an operation.
OPERATIONS = {
    "generator": {
        ("/health", "get"): ("health_health_get", False),
        ("/generate", "post"): ("generate_generate_post", False),
        ("/generator/mcs", "post"): ("legacy_en_generator_mcs_post", True),
        ("/generator/mcs/eng", "post"): ("legacy_en_generator_mcs_eng_post", True),
        ("/generator/mcs/german", "post"): ("legacy_de_generator_mcs_german_post", True),
        ("/generator/mcs/turkish", "post"): ("legacy_tr_generator_mcs_turkish_post", True),
        ("/generator/mcs/query", "post"): ("query_generate_generator_mcs_query_post", True),
    },
    "verifier": {
        ("/verify", "post"): ("verify_draft_verify_post", False),
        ("/verify/{record_id}", "post"): ("verify_record_id_verify__record_id__post", True),
        ("/health", "get"): ("health_check_health_get", False),
    },
}

VERSIONS = {"generator": "1.1.0", "verifier": "1.0.0"}

# Every status either service can actually produce on a business route.
BUSINESS_STATUSES = {"200", "400", "401", "403", "404", "422", "502", "503", "504"}


@pytest.fixture(params=SERVICES)
def service(request):
    return request.param


@pytest.fixture
def document(service):
    # Read-only: the schema is cached on the app and shared with every other test.
    return APPS[service].openapi()


def test_live_schema_matches_the_versioned_snapshot(service, document):
    assert document == snapshot(service)


def test_route_surface_and_versions_are_unchanged(service, document):
    found = {
        (path, method): (operation["operationId"], operation.get("deprecated", False))
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    }
    assert found == OPERATIONS[service]
    assert document["info"]["version"] == VERSIONS[service]
    assert document["openapi"] == "3.1.0"
    assert document["info"]["description"].strip()


def test_every_local_reference_resolves_and_nothing_is_orphaned(service, document):
    text = json.dumps(document)
    for section in ("schemas", "responses", "parameters"):
        used = set(re.findall(rf"#/components/{section}/([A-Za-z0-9_]+)", text))
        declared = set(document["components"].get(section, {}))
        assert used - declared == set(), f"{section} pointers with no component"
        assert declared - used == set(), f"{section} components nothing references"
    assert not re.findall(r'"\$ref": "(?!#/components/)', text), "only local refs are used"


def test_no_response_is_documented_as_an_empty_schema(service, document):
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            for status, response in operation["responses"].items():
                block = json_block(document, response)
                assert block, f"{method} {path} {status} documents no JSON body"
                assert block["schema"] != {}, f"{method} {path} {status} has an empty schema"
                assert block.get("examples"), f"{method} {path} {status} has no example"


def test_business_routes_document_every_reachable_failure(service, document):
    for path, method in OPERATIONS[service]:
        statuses = set(document["paths"][path][method]["responses"])
        if path == "/health":
            # Liveness touches no dependency; only a rejected shared header can fail.
            assert statuses == {"200", "400"}
        else:
            assert statuses == BUSINESS_STATUSES


def test_validation_and_domain_error_bodies_both_satisfy_the_422_schema(service, document):
    for path, method in OPERATIONS[service]:
        if path == "/health":
            continue
        block = json_block(document, document["paths"][path][method]["responses"]["422"])
        validate(document, block["schema"],
                 {"detail": [{"loc": ["body", "language"], "msg": "bad", "type": "x"}]})
        validate(document, block["schema"], {"detail": "a single message"})


def test_error_schema_never_advertises_the_submitted_value(service, document):
    validation_error = document["components"]["schemas"]["ValidationError"]
    assert set(validation_error["properties"]) == {"loc", "msg", "type"}
    assert validation_error["additionalProperties"] is False


def test_optional_bearer_is_offered_and_health_needs_none(service, document):
    scheme = document["components"]["securitySchemes"]["BearerAuth"]
    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    for path, method in OPERATIONS[service]:
        security = document["paths"][path][method].get("security")
        if path == "/health":
            assert security is None
        else:
            # An empty alternative is how OpenAPI says "credentials are optional".
            assert security == [{}, {"BearerAuth": []}]


def test_every_operation_documents_the_shared_request_headers(service, document):
    for path, method in OPERATIONS[service]:
        parameters = [
            dereference(document, parameter, "parameters")
            for parameter in document["paths"][path][method]["parameters"]
        ]
        by_name = {p["name"]: p for p in parameters if p["in"] == "header"}
        assert set(by_name) == {"X-Correlation-ID", "Idempotency-Key"}
        for parameter in by_name.values():
            assert parameter["required"] is False
            assert parameter["schema"]["maxLength"] == 4096
        # `Authorization` is covered by the security scheme; OpenAPI ignores it as a
        # parameter, so documenting it twice would be dead weight.
        assert "Authorization" not in by_name


def test_handled_responses_document_the_returned_trace(service, document):
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            for status, response in operation["responses"].items():
                resolved = dereference(document, response, "responses")
                assert "X-Correlation-ID" in resolved["headers"], f"{method} {path} {status}"


def test_query_adapter_takes_query_string_parameters(service, document):
    if service != "generator":
        pytest.skip("only the Generator has a query adapter")
    operation = document["paths"]["/generator/mcs/query"]["post"]
    resolved = [dereference(document, p, "parameters") for p in operation["parameters"]]
    assert {p["name"] for p in resolved if p["in"] == "query"} == {"query", "language"}
    assert "requestBody" not in operation


def test_every_documented_example_satisfies_its_own_schema(service, document):
    seen = 0
    for path, method, name, schema, value in documented_examples(document):
        try:
            validate(document, schema, value)
        except Exception as exc:  # pragma: no cover - the message is the point
            pytest.fail(f"{method} {path} example {name!r}: {exc}")
        seen += 1
    assert seen > 0


def test_generator_documents_the_grounded_draft_fields(service, document):
    if service != "generator":
        pytest.skip("only the Generator returns a draft")
    draft = document["components"]["schemas"]["McsDraft"]
    assert set(draft["required"]) == {
        "engagement_ids", "titles", "sections", "citations", "client_named", "language",
    }
    sections = draft["properties"]["sections"]
    assert set(sections["required"]) == {
        "context", "challenge", "approach", "technology", "outcomes",
    }
    fields = {
        name: set(dereference(document, entry["items"], "schemas")["properties"])
        for name, entry in sections["properties"].items()
    }
    assert fields == {
        "context": {"region", "page"}, "challenge": {"challenge", "page"},
        "approach": {"approach", "page"}, "technology": {"technologies", "page"},
        "outcomes": {"outcomes", "page"},
    }
    # `page` and `page_ref` carry a record id, and the docs must not imply otherwise.
    entry = dereference(document, sections["properties"]["outcomes"]["items"], "schemas")
    assert "not a PDF page number" in entry["properties"]["page"]["description"]


def test_verifier_keeps_the_shared_verdict_contract(service, document):
    if service != "verifier":
        pytest.skip("only the Verifier returns a report")
    report = document["components"]["schemas"]["VerificationReport"]
    assert set(report["properties"]) == {"engagement_id", "verdict", "problems"}
    assert set(report["required"]) == {"engagement_id", "verdict", "problems"}
    assert set(report["properties"]["verdict"]["enum"]) == {"PASS", "BLOCK"}
    problem = dereference(document, report["properties"]["problems"]["items"], "schemas")
    # Checks report different fields; only `type` and `why` are common to all of them.
    assert set(problem["required"]) == {"type", "why"}
    assert problem["additionalProperties"] is True


def test_verifier_documents_both_accepted_draft_shapes(service, document):
    if service != "verifier":
        pytest.skip("only the Verifier accepts a draft")
    draft = document["components"]["schemas"]["DraftInput"]
    assert draft["required"] == ["sections"]
    for optional in ("titles", "citations", "client_named"):
        assert optional not in draft["required"]
    outcomes = draft["properties"]["sections"]["properties"]["outcomes"]
    assert {branch.get("type") for branch in outcomes["anyOf"]} == {"string", "array"}
    entries = next(b for b in outcomes["anyOf"] if b.get("type") == "array")
    assert dereference(document, entries["items"], "schemas")["required"] == ["outcomes"]


def test_block_is_documented_as_a_two_hundred_result(service, document):
    if service != "verifier":
        pytest.skip("only the Verifier returns a verdict")
    block = json_block(document, document["paths"]["/verify"]["post"]["responses"]["200"])
    verdicts = {example["value"]["verdict"] for example in block["examples"].values()}
    assert verdicts == {"PASS", "BLOCK"}


def test_examples_use_only_the_synthetic_source(service, document):
    text = json.dumps(document, ensure_ascii=False)
    assert RECORD_ID in text
    for leaked in ("OPENAI_API_KEY=", "Bearer ey", "sk-", "127.0.0.1", "localhost"):
        assert leaked not in text, f"the published contract must not embed {leaked!r}"


def test_the_schema_is_built_once_and_reused(service):
    app = APPS[service]
    assert app.openapi() is app.openapi_schema
    assert app.openapi() is app.openapi()


def test_enrichment_is_deterministic(service, document):
    """A second build from a cleared cache produces the same document."""
    app = APPS[service]
    cached = deepcopy(app.openapi_schema)
    try:
        app.openapi_schema = None
        assert app.openapi() == document
    finally:
        app.openapi_schema = cached
