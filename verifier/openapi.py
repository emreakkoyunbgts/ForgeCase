"""Verifier OpenAPI documentation: accepted draft shapes, verdicts and real failures.

The examples are the bodies the routes actually produce. Nothing here calls Vault or
the model provider, imports a test module, or reads a file.
"""

from common.drafts import SECTION_FIELDS
from common.openapi import (
    LANGUAGES,
    OPTIONAL_SECURITY,
    SECTION_DESCRIPTIONS,
    apply_shared_headers,
    bad_header_response,
    entry_schema,
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

RECORD_ID = "eng-cf123-01"

INPUT_ENTRY_COMPONENTS = {
    "titles": "TitleEntryInput",
    "context": "ContextEntryInput",
    "challenge": "ChallengeEntryInput",
    "approach": "ApproachEntryInput",
    "technology": "TechnologyEntryInput",
    "outcomes": "OutcomesEntryInput",
}

INFO_DESCRIPTION = """
Verifier compares a submitted final draft against its original Vault record and
answers `PASS` or `BLOCK`. It never trusts source facts supplied in the request: the
record is always read from `GET {VAULT_URL}/engagements/{record_id}`.

`BLOCK` is a normal result and is returned with HTTP 200 and a populated `problems`
list. An HTTP error is not a verdict and can never authorise publication.

Deterministic checks (quantities, naming consent, citation references) can BLOCK on
their own, but they cannot produce a PASS. Every PASS additionally requires the
independent semantic gate to assess every visible span against the source, so
`OPENAI_API_KEY` must be configured for any PASS in any language.

`GET /health` reports liveness only and contacts no dependency. See
`docs/CF-123-runbook.md` for setup, dependencies, timeouts and troubleshooting.
""".strip()

HEALTH_SCHEMA = {
    "type": "object",
    "title": "VerifierHealth",
    "description": "Liveness only; no dependency is contacted to produce it.",
    "additionalProperties": False,
    "required": ["status"],
    "properties": {"status": {"type": "string", "enum": ["ok"]}},
}

SEMANTIC_CAUSES = {
    "502": [
        ("semantic_coverage", "Model did not assess every span exactly once",
         "Semantic assessment did not cover the complete draft"),
        ("semantic_evidence",
         "Model cited a source pointer or quotation that is not in the record",
         "Semantic assessment returned invalid source evidence"),
        ("semantic_missing_evidence",
         "Model marked a factual span entailed without citing evidence",
         "Semantic assessment omitted source evidence"),
    ]
}

PASS_BODY = {"engagement_id": RECORD_ID, "verdict": "PASS", "problems": []}

BLOCK_BODY = {
    "engagement_id": RECORD_ID,
    "verdict": "BLOCK",
    "problems": [
        {
            "type": "ungrounded_number",
            "value": "999%",
            "unit": "percent",
            "why": "this quantity and unit are not supported by the source evidence",
            "span": "/sections/outcomes/0/outcomes",
        },
        {
            "type": "invalid_source_reference",
            "why": "citation reference is not present in the Vault record",
        },
    ],
}

# The canonical route reports identity conflicts through the validation list, because
# normalisation runs inside the request model. The legacy route reports them as a string.
CANONICAL_VALIDATION_EXAMPLE = (
    "Draft identity conflicts with record_id",
    {"detail": [{"loc": ["body"],
                 "msg": "Value error, draft engagement_id must match record_id",
                 "type": "value_error"}]},
)

LEGACY_VALIDATION_EXAMPLE = (
    "Rejected request field",
    {"detail": [{"loc": ["body", "mcs"],
                 "msg": "Value error, draft.sections must contain case-study text",
                 "type": "value_error"}]},
)

LEGACY_STRING_CAUSES = [
    ("record_id", "Path record id is not a single Vault path segment",
     "record_id must identify one Vault record"),
    ("record_mismatch", "Submitted `record.id` differs from the path",
     "record.id must match the path record_id"),
    ("draft_identity", "Submitted draft is bound to a different source",
     "draft engagement_id must match record_id"),
    ("draft_page", "A section or title entry cites a different source",
     "draft page source must match record_id"),
]

DRAFT_INPUT_DESCRIPTION = """
The draft to verify. Two shapes are accepted and normalised to the same canonical
document before any check runs:

* each section as plain prose, e.g. `"outcomes": "Payment latency reduced by 45%."`
* each section as a list of MCS entries, e.g.
  `"outcomes": [{"outcomes": "...", "page": "eng-cf123-01"}]`

`sections` is the only required key, and at least one section must contain text. Use
`title` or `titles`, never both. `titles`, `citations` and `client_named` are filled
in by normalisation when absent, so they are not required on input.

Every source identity in the draft must agree with the request `record_id`:
`engagement_id`, `engagement_ids`, each entry's `page` and each citation's `page_ref`.
A `language` key, if present, must equal the request `language`. These cross-field
rules cannot be expressed in JSON Schema alone; a conflict returns 422.
""".strip()


def draft_input_schemas():
    """Input entry shapes, which unlike the canonical draft may omit `page`."""
    schemas = {
        INPUT_ENTRY_COMPONENTS["titles"]: entry_schema(
            INPUT_ENTRY_COMPONENTS["titles"], "title", "Case-study title prose.",
            page_required=False,
        )
    }
    for name, field in SECTION_FIELDS.items():
        schemas[INPUT_ENTRY_COMPONENTS[name]] = entry_schema(
            INPUT_ENTRY_COMPONENTS[name], field, SECTION_DESCRIPTIONS[name],
            page_required=False,
        )
    schemas["CitationInput"] = {
        "type": "object",
        "title": "CitationInput",
        "additionalProperties": False,
        "required": ["claim", "source_ref"],
        "properties": {
            "claim": {"type": "string", "description": "The asserted outcome text."},
            "source_ref": {
                "type": "string",
                "description": (
                    "Must match one of the source record's outcome `source_ref` values. "
                    "Anything else becomes an `invalid_source_reference` problem."
                ),
            },
            "page_ref": {
                "type": "string",
                "description": (
                    "Optional on input. When present it must equal the requested "
                    "`record_id`; when absent, normalisation fills it in."
                ),
            },
        },
    }

    def flexible(component, description):
        return {
            "description": description,
            "anyOf": [
                {"type": "string", "description": "Plain prose."},
                {"type": "array",
                 "items": {"$ref": "#/components/schemas/" + component},
                 "description": "MCS entries."},
            ],
        }

    schemas["DraftInput"] = {
        "type": "object",
        "title": "DraftInput",
        "description": DRAFT_INPUT_DESCRIPTION,
        "additionalProperties": False,
        "required": ["sections"],
        "properties": {
            "engagement_id": {
                "type": "string",
                "description": "If present, must equal the request `record_id`.",
            },
            "engagement_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 1,
                "description": "If present, must be exactly `[record_id]`.",
            },
            "title": flexible(INPUT_ENTRY_COMPONENTS["titles"],
                              "Title prose. Mutually exclusive with `titles`."),
            "titles": flexible(INPUT_ENTRY_COMPONENTS["titles"],
                               "Title entries. Mutually exclusive with `title`."),
            "sections": {
                "type": "object",
                "description": (
                    "The standard case-study sections. Absent sections normalise to an "
                    "empty list, but at least one must contain text."
                ),
                "additionalProperties": False,
                "properties": {
                    name: flexible(INPUT_ENTRY_COMPONENTS[name], SECTION_DESCRIPTIONS[name])
                    for name in SECTION_FIELDS
                },
            },
            "citations": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/CitationInput"},
                "description": "Defaults to an empty list.",
            },
            "client_named": {
                "type": "boolean",
                "description": (
                    "Defaults to false. Setting it true when the source record does not "
                    "set `may_be_named` does not grant consent; the naming checks still "
                    "compare against the record."
                ),
            },
            "language": {
                "type": "string",
                "enum": LANGUAGES,
                "description": "If present, must equal the request `language`.",
            },
        },
    }
    return schemas


OUTCOME_TEXT = "Payment latency reduced by 45%"

EXAMPLE_FLAT_DRAFT = {
    "engagement_id": RECORD_ID,
    "sections": {
        "context": "retail bank in TR.",
        "challenge": "Slow payment processing.",
        "approach": "Optimised payment processing.",
        "technology": "Python",
        "outcomes": OUTCOME_TEXT,
    },
}

EXAMPLE_MCS_DRAFT = {
    "engagement_ids": [RECORD_ID],
    "titles": [{"title": "payments for retail bank", "page": RECORD_ID}],
    "sections": {
        "context": [{"region": "retail bank in TR.", "page": RECORD_ID}],
        "challenge": [{"challenge": "Slow payment processing.", "page": RECORD_ID}],
        "approach": [{"approach": "Optimised payment processing.", "page": RECORD_ID}],
        "technology": [{"technologies": "Python", "page": RECORD_ID}],
        "outcomes": [{"outcomes": OUTCOME_TEXT, "page": RECORD_ID}],
    },
    "citations": [{"claim": OUTCOME_TEXT,
                   "source_ref": "synthetic.pdf#page=1", "page_ref": RECORD_ID}],
    "client_named": False,
    "language": "en",
}


def verify_request_examples():
    return {
        "flat": {"summary": "Plain section prose",
                 "value": {"record_id": RECORD_ID, "draft": EXAMPLE_FLAT_DRAFT,
                           "language": "en"}},
        "mcs": {"summary": "A Generator draft submitted unchanged",
                "value": {"record_id": RECORD_ID, "draft": EXAMPLE_MCS_DRAFT,
                          "language": "en"}},
    }


def report_response():
    """Inline so a `$ref`-following client reaches the report schema directly."""
    return json_response(
        "A completed verification. `BLOCK` is a normal result: it is reported here with "
        "HTTP 200 and a populated `problems` list, never as an HTTP error.",
        {"$ref": "#/components/schemas/VerificationReport"},
        {
            "pass": {"summary": "Every visible span is supported by the source",
                     "value": PASS_BODY},
            "block": {"summary": "An unsupported quantity and an unknown citation reference",
                      "value": BLOCK_BODY},
        },
    )


def build_responses():
    failures = merge_causes(vault_causes(), provider_causes(), SEMANTIC_CAUSES)
    return {
        "BadHeader": bad_header_response(),
        "VaultUnauthorized": vault_denied_response(401),
        "VaultForbidden": vault_denied_response(403),
        "SourceNotFound": error_response(
            "Vault holds no record under this id, so there is nothing to verify against. "
            "No verdict is produced.",
            [("record", "Unknown record id", "Source record was not found in Vault")],
        ),
        "Unprocessable": unprocessable_response(
            "The request failed validation. Draft identity and language conflicts are "
            "reported here because normalisation runs inside the request model.",
            CANONICAL_VALIDATION_EXAMPLE,
            [provider_input_cause()],
        ),
        "LegacyUnprocessable": unprocessable_response(
            "The request failed validation, or an identity rule was violated. This route "
            "reports its own identity checks as a single message string.",
            LEGACY_VALIDATION_EXAMPLE,
            [*LEGACY_STRING_CAUSES, provider_input_cause()],
        ),
        "BadGateway": error_response(
            "Vault or the model provider answered with something this route may not use. "
            "An unusable semantic assessment fails closed; it never becomes a PASS.",
            failures["502"],
        ),
        "Unavailable": error_response(
            "Vault or the model provider could not be reached or is not configured. "
            "Without the semantic gate no PASS can be issued.",
            failures["503"],
        ),
        "GatewayTimeout": error_response(
            "Vault or the model provider exceeded its deadline. Nothing is retried "
            "automatically and no backoff is applied.",
            failures["504"],
        ),
        "Health": json_response(
            "The process is running. This says nothing about Vault or the model provider.",
            {"$ref": "#/components/schemas/VerifierHealth"},
            {"ok": {"summary": "Liveness", "value": {"status": "ok"}}},
        ),
    }


def _ref(name):
    return {"$ref": f"#/components/responses/{name}"}


SOURCE_FAILURES = {
    "400": "BadHeader", "401": "VaultUnauthorized", "403": "VaultForbidden",
    "404": "SourceNotFound", "502": "BadGateway", "503": "Unavailable",
    "504": "GatewayTimeout",
}

OPERATIONS = {
    ("/verify", "post"): {
        "summary": "Verify a draft against its Vault record",
        "description": (
            "Reads the source record from Vault, normalises the submitted draft, runs the "
            "deterministic checks and, only if those find nothing, the independent "
            "semantic gate.\n\n"
            "`language` defaults to `en`. Deterministic checks can BLOCK without any model "
            "call, but a PASS always requires the semantic assessment, so the provider "
            "must be configured.\n\n"
            "A PASS is not permission to publish: Publisher verifies the final display "
            "content again through this same route."
        ),
        "failures": {**SOURCE_FAILURES, "422": "Unprocessable"},
        "examples": True,
    },
    ("/verify/{record_id}", "post"): {
        "summary": "Verify a draft supplied with its record body",
        "description": (
            "Takes `{record, mcs}`. The submitted `record` is used only to confirm that "
            "its `id` matches the path; **every fact still comes from Vault**, so editing "
            "the submitted record cannot change the verdict.\n\n"
            "Deprecated. Use `POST /verify` with `{record_id, draft, language}`."
        ),
        "failures": {**SOURCE_FAILURES, "422": "LegacyUnprocessable"},
        "examples": False,
    },
}


def describe_verifier(schema):
    """Rewrite the generated document; route behaviour is untouched."""
    schema["info"]["description"] = INFO_DESCRIPTION
    install_shared(schema, problem=True)
    schemas = schema["components"]["schemas"]
    schemas["VerifierHealth"] = HEALTH_SCHEMA
    schemas.update(draft_input_schemas())
    schema["components"]["responses"] = build_responses()

    report = schemas["VerificationReport"]
    report["description"] = (
        "The verification result. `problems` is empty on PASS and populated on BLOCK; "
        "different checks report different fields, so only `type` and `why` are common."
    )
    report["properties"]["engagement_id"]["description"] = (
        "The record the draft was checked against; always the requested `record_id`."
    )
    report["properties"]["verdict"]["description"] = (
        "`PASS` only when every visible span is supported by the source."
    )
    report["properties"]["problems"]["items"] = {"$ref": "#/components/schemas/Problem"}

    request = schemas["VerifyRequest"]
    request["description"] = "A draft plus the id of the record it must be grounded in."
    request["properties"]["record_id"]["description"] = (
        "Identifies one Vault record. Path separators and control characters are rejected."
    )
    request["properties"]["draft"] = {"$ref": "#/components/schemas/DraftInput"}
    request["properties"]["language"]["description"] = (
        "The language the draft is written in. Must match the draft's own `language` key "
        "when that is present."
    )

    legacy = schemas["LegacyVerifyRequest"]
    legacy["description"] = (
        "Compatibility body. `record` is only checked for a matching `id`; the "
        "authoritative facts are always re-read from Vault."
    )
    legacy["properties"]["record"]["description"] = (
        "The caller's copy of the record. Its contents are never trusted."
    )
    legacy["properties"]["mcs"] = {
        "allOf": [{"$ref": "#/components/schemas/DraftInput"}],
        "description": "The draft to verify, in either accepted shape.",
    }

    for (path, method), spec in OPERATIONS.items():
        operation = schema["paths"][path][method]
        operation["summary"] = spec["summary"]
        operation["description"] = spec["description"]
        apply_shared_headers(operation)
        operation["security"] = OPTIONAL_SECURITY
        if spec["examples"]:
            body = operation["requestBody"]["content"]["application/json"]
            body["examples"] = verify_request_examples()
        operation["responses"] = {
            "200": report_response(),
            **{status: _ref(name) for status, name in sorted(spec["failures"].items())},
        }

    health = schema["paths"]["/health"]["get"]
    health["summary"] = "Liveness"
    health["description"] = (
        "Returns a fixed body without contacting Vault or the model provider. A green "
        "health check does not mean a draft can be verified."
    )
    apply_shared_headers(health)
    health["responses"] = {"200": _ref("Health"), "400": _ref("BadHeader")}
    return schema
