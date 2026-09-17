"""Generator OpenAPI documentation: operation prose, synthetic examples and failures.

The example draft is produced by the real `generate_mcs`, so the published contract
cannot drift from what the route actually returns. No Vault, Librarian or model call
is made here, and no source file is read.
"""

from common.openapi import (
    OPTIONAL_SECURITY,
    apply_shared_headers,
    bad_header_response,
    error_response,
    install_shared,
    json_response,
    merge_causes,
    provider_causes,
    provider_input_cause,
    unprocessable_response,
    vault_causes,
    vault_denied_response,
)
from generator.core import generate_mcs

RECORD_ID = "eng-cf123-01"

# Fully synthetic: no real client, no naming consent, one recorded outcome.
EXAMPLE_SOURCE = {
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
        {"metric": "Payment latency reduced by 45%", "source_ref": "synthetic.pdf#page=1"}
    ],
}

# Turkish prose for the same grounded draft: structure, ids and quantity are fixed.
TURKISH_SPANS = {
    "/titles/0/title": "perakende bankası için ödemeler",
    "/sections/context/0/region": "TR bölgesinde perakende bankası.",
    "/sections/challenge/0/challenge": "Yavaş ödeme işlemleri.",
    "/sections/approach/0/approach": "Ödeme işlemleri iyileştirildi.",
    "/sections/technology/0/technologies": "Python",
    "/sections/outcomes/0/outcomes": "Ödeme gecikmesi %45 azaltıldı.",
    "/citations/0/claim": "Ödeme gecikmesi %45 azaltıldı.",
}

INFO_DESCRIPTION = """
Generator turns one authoritative Vault Engagement Record into an in-memory
case-study draft in English, German or Turkish. It never reads a source corpus, a
seed file or a PDF at request time, and it never trusts facts supplied in a request
body: `POST /generate` takes a record id and fetches the record from Vault itself.

Every language, English included, is produced through the configured model, so
`OPENAI_API_KEY` is required for all three. The model may only rewrite visible prose:
source ids, references, missing-data markers, quantities, technologies and naming
consent are re-checked afterwards, and a violation is an HTTP error rather than a
successful draft.

Generating a draft is not approval. Submit the final edited draft to Verifier, obtain
human approval, then publish through Publisher's independent final gate.

`GET /health` reports liveness only. It proves nothing about Vault, Librarian or the
model provider. See `docs/CF-123-runbook.md` for setup, dependencies, timeouts and
troubleshooting.
""".strip()

HEALTH_SCHEMA = {
    "type": "object",
    "title": "GeneratorHealth",
    "description": "Liveness only; no dependency is contacted to produce it.",
    "additionalProperties": False,
    "required": ["status", "service", "languages"],
    "properties": {
        "status": {"type": "string", "enum": ["ok"]},
        "service": {"type": "string", "enum": ["generator"]},
        "languages": {"type": "array", "items": {"type": "string"}},
    },
}

HEALTH_BODY = {"status": "ok", "service": "generator", "languages": ["en", "de", "tr"]}

TRANSLATION_CAUSES = {
    "502": [
        ("translation_coverage", "Model did not return every span exactly once",
         "Translation did not cover the complete draft"),
        ("translation_empty", "Model returned an empty span",
         "Translation returned empty content"),
        ("translation_marker", "Model altered a `[MISSING: ...]` marker",
         "Translation changed a missing-data marker"),
        ("translation_quantity", "Model moved, dropped or duplicated a quantity",
         "Translation changed or omitted a quantity in its source span"),
        ("translation_ambiguous", "A quantity could not be read unambiguously",
         "Translation contains an ambiguous quantity"),
        ("translation_unsupported_quantity",
         "Model introduced a quantity the source does not support",
         "Translation changed or introduced an unsupported quantity"),
        ("translation_naming", "Model disclosed a client name the source does not permit",
         "Translation violated source naming consent"),
        ("translation_name_dropped", "Model dropped a client name the source permits",
         "Translation changed or omitted the source client name"),
        ("translation_technology", "Model altered a technology identifier",
         "Translation changed a technology identifier"),
    ]
}

LIBRARIAN_CAUSES = {
    "502": [
        ("librarian_unsuccessful", "Librarian answered with an unexpected status",
         "Librarian returned an unsuccessful response"),
        ("librarian_invalid", "Librarian answered with a body that is not a usable match",
         "Librarian returned an invalid match response"),
    ],
    "503": [
        ("librarian_unavailable", "Librarian could not be reached",
         "Librarian is unavailable"),
    ],
    "504": [
        ("librarian_timeout", "Librarian exceeded the 20-second timeout",
         "Librarian request timed out"),
    ],
}

VALIDATION_EXAMPLE = (
    "Rejected request field",
    {"detail": [{"loc": ["body", "language"],
                 "msg": "Input should be 'en', 'de' or 'tr'",
                 "type": "literal_error"}]},
)


def example_draft(language):
    """The exact draft `generate_mcs` builds, with prose translated for `tr`."""
    draft = generate_mcs(EXAMPLE_SOURCE)
    if language == "tr":
        draft["titles"][0]["title"] = TURKISH_SPANS["/titles/0/title"]
        for name, entries in draft["sections"].items():
            for index, entry in enumerate(entries):
                field = next(key for key in entry if key != "page")
                entry[field] = TURKISH_SPANS[f"/sections/{name}/{index}/{field}"]
        for index, citation in enumerate(draft["citations"]):
            citation["claim"] = TURKISH_SPANS[f"/citations/{index}/claim"]
        draft["language"] = "tr"
    return draft


def draft_response():
    return json_response(
        "The grounded draft in the requested language. Nothing here is verified yet.",
        {"$ref": "#/components/schemas/McsDraft"},
        {
            "english": {"summary": "English draft", "value": example_draft("en")},
            "turkish": {"summary": "Turkish draft, same ids and quantity",
                        "value": example_draft("tr")},
        },
    )


def _failures(*extra):
    """Compose the dependency failures a Vault-reading, model-calling route returns."""
    return merge_causes(vault_causes(), provider_causes(), *extra)


def build_responses():
    source_failures = _failures(TRANSLATION_CAUSES)
    query_failures = _failures(TRANSLATION_CAUSES, LIBRARIAN_CAUSES)
    return {
        "BadHeader": bad_header_response(),
        "VaultUnauthorized": vault_denied_response(401),
        "VaultForbidden": vault_denied_response(403),
        "DependencyUnauthorized": error_response(
            "Vault or Librarian rejected the credential used on this request. Generator "
            "applies no authentication of its own; the status is propagated.",
            [("vault", "Vault denied the source read",
              "Vault denied access to the source record"),
             ("librarian", "Librarian denied the match request",
              "Librarian denied access")],
        ),
        "DependencyForbidden": error_response(
            "Vault or Librarian refused access with the supplied credential.",
            [("vault", "Vault denied the source read",
              "Vault denied access to the source record"),
             ("librarian", "Librarian denied the match request",
              "Librarian denied access")],
        ),
        "SourceNotFound": error_response(
            "Vault holds no record under this id. No draft is produced, and nothing is "
            "read from a local file as a substitute.",
            [("record", "Unknown record id", "Source record was not found in Vault")],
        ),
        "MatchNotFound": error_response(
            "Librarian returned no engagement for this query, so there is no single "
            "authoritative source to generate from.",
            [("match", "Query matched nothing", "No matching engagement was found")],
        ),
        "Unprocessable": unprocessable_response(
            "The request failed validation, or the draft exceeded the model input limit.",
            VALIDATION_EXAMPLE,
            [provider_input_cause()],
        ),
        "LegacyUnprocessable": unprocessable_response(
            "The submitted body carried no usable `id`, the request failed validation, "
            "or the draft exceeded the model input limit.",
            VALIDATION_EXAMPLE,
            [("record_id", "Body has no usable `id`", "A valid record.id is required"),
             provider_input_cause()],
        ),
        "QueryUnprocessable": unprocessable_response(
            "The query was blank, the request failed validation, or the draft exceeded "
            "the model input limit.",
            VALIDATION_EXAMPLE,
            [("query", "Blank query string", "Query must contain text"),
             provider_input_cause()],
        ),
        "BadGateway": error_response(
            "A dependency answered, but not with something this route may use. Redirects "
            "are never followed, and an unusable model answer is an error, not a draft.",
            source_failures["502"],
        ),
        "Unavailable": error_response(
            "A dependency or the model provider could not be reached or is not "
            "configured. There is no local fallback source.",
            source_failures["503"],
        ),
        "GatewayTimeout": error_response(
            "A dependency or the model provider exceeded its deadline. Nothing is retried "
            "automatically and no backoff is applied.",
            source_failures["504"],
        ),
        "QueryBadGateway": error_response(
            "Librarian, Vault or the model provider answered with something this route "
            "may not use.",
            query_failures["502"],
        ),
        "QueryUnavailable": error_response(
            "Librarian, Vault or the model provider could not be reached or is not "
            "configured.",
            query_failures["503"],
        ),
        "QueryGatewayTimeout": error_response(
            "Librarian, Vault or the model provider exceeded its deadline.",
            query_failures["504"],
        ),
        "Health": json_response(
            "The process is running. This says nothing about Vault, Librarian or the "
            "model provider.",
            {"$ref": "#/components/schemas/GeneratorHealth"},
            {"ok": {"summary": "Liveness", "value": HEALTH_BODY}},
        ),
        "Draft": draft_response(),
    }


def _ref(name):
    return {"$ref": f"#/components/responses/{name}"}


SOURCE_FAILURES = {
    "400": "BadHeader", "401": "VaultUnauthorized", "403": "VaultForbidden",
    "404": "SourceNotFound", "502": "BadGateway", "503": "Unavailable",
    "504": "GatewayTimeout",
}

QUERY_FAILURES = {
    "400": "BadHeader", "401": "DependencyUnauthorized", "403": "DependencyForbidden",
    "404": "MatchNotFound", "502": "QueryBadGateway", "503": "QueryUnavailable",
    "504": "QueryGatewayTimeout",
}

LEGACY_NOTE = (
    "\n\nDeprecated. Use `POST /generate` with `{record_id, language}`. This adapter is "
    "kept for existing callers and reads its facts from Vault like every other route."
)

OPERATIONS = {
    ("/generate", "post"): {
        "summary": "Generate a draft from one Vault record",
        "description": (
            "Reads `GET {VAULT_URL}/engagements/{record_id}`, builds the grounded draft "
            "and returns it in the requested language.\n\n"
            "`language` defaults to `en`; unknown fields are rejected. English is not a "
            "shortcut: it is produced through the same model step as German and Turkish, "
            "so the provider must be configured for every language.\n\n"
            "`page` and `page_ref` carry the **source record id**, not a PDF page number."
        ),
        "success": "Draft",
        "failures": {**SOURCE_FAILURES, "422": "Unprocessable"},
    },
    ("/generator/mcs", "post"): {
        "summary": "Generate an English draft from a submitted record body",
        "description": (
            "Only the `id` field of the submitted body is used. Every fact comes from "
            "Vault, so a modified body cannot change the generated content." + LEGACY_NOTE
        ),
        "success": "Draft",
        "failures": {**SOURCE_FAILURES, "422": "LegacyUnprocessable"},
    },
    ("/generator/mcs/eng", "post"): {
        "summary": "Generate an English draft from a submitted record body",
        "description": (
            "Identical to `POST /generator/mcs`. Only the body's `id` is used; the facts "
            "come from Vault." + LEGACY_NOTE
        ),
        "success": "Draft",
        "failures": {**SOURCE_FAILURES, "422": "LegacyUnprocessable"},
    },
    ("/generator/mcs/german", "post"): {
        "summary": "Generate a German draft from a submitted record body",
        "description": (
            "The German form of the body adapter. Only the body's `id` is used; the "
            "facts come from Vault." + LEGACY_NOTE
        ),
        "success": "Draft",
        "failures": {**SOURCE_FAILURES, "422": "LegacyUnprocessable"},
    },
    ("/generator/mcs/turkish", "post"): {
        "summary": "Generate a Turkish draft from a submitted record body",
        "description": (
            "The Turkish form of the body adapter. Only the body's `id` is used; the "
            "facts come from Vault." + LEGACY_NOTE
        ),
        "success": "Draft",
        "failures": {**SOURCE_FAILURES, "422": "LegacyUnprocessable"},
    },
    ("/generator/mcs/query", "post"): {
        "summary": "Select one record through Librarian, then generate",
        "description": (
            "`query` and `language` are **query-string parameters**, not a JSON body. "
            "Librarian's `POST /match` picks a single engagement id with `top_k=1`, and "
            "that record is then read from Vault as usual.\n\n"
            "This route is the only one that depends on Librarian: generating from a "
            "record id you already know works while Librarian is down." + LEGACY_NOTE
        ),
        "success": "Draft",
        "failures": {**QUERY_FAILURES, "422": "QueryUnprocessable"},
    },
    ("/health", "get"): {
        "summary": "Liveness",
        "description": (
            "Returns a fixed body without contacting Vault, Librarian or the model "
            "provider. A green health check does not mean a draft can be generated."
        ),
        "success": "Health",
        "failures": {"400": "BadHeader"},
        "security": False,
    },
}


def describe_generator(schema):
    """Rewrite the generated document; route behaviour is untouched."""
    schema["info"]["description"] = INFO_DESCRIPTION
    install_shared(schema, draft_output=True)
    schema["components"]["schemas"]["GeneratorHealth"] = HEALTH_SCHEMA
    schema["components"]["responses"] = build_responses()

    for (path, method), spec in OPERATIONS.items():
        operation = schema["paths"][path][method]
        operation["summary"] = spec["summary"]
        operation["description"] = spec["description"]
        apply_shared_headers(operation)
        if spec.get("security", True):
            operation["security"] = OPTIONAL_SECURITY
        success = _ref(spec["success"])
        operation["responses"] = {
            "200": success,
            **{status: _ref(name) for status, name in sorted(spec["failures"].items())},
        }
    return schema
