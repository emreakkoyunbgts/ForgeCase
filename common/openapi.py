"""Documentation-only OpenAPI enrichment for the Generator and Verifier contracts.

Nothing here runs while a request is handled. The helpers rewrite the schema FastAPI
has already generated, so accepted input and response filtering stay exactly as the
route declarations define them. No dependency is called and no source file is read.
"""

from typing import get_args

from common.drafts import MAX_DRAFT_CHARACTERS, SECTION_FIELDS, Language
from common.structured_llm import MAX_PROVIDER_INPUT_CHARACTERS
from verifier.models import MAX_DRAFT_DEPTH

LANGUAGES = list(get_args(Language))
HEADER_LIMIT = 4096

SOURCE_ID_NOTE = (
    "The id of the Vault record this text is grounded in, not a PDF page number. "
    "Normalisation pins it to the requested `record_id`."
)


def install_openapi(app, enrich):
    """Serve an enriched `/openapi.json` while leaving every route untouched.

    The original bound method is reused rather than calling `get_openapi` directly,
    so the generated base document keeps whatever arguments this FastAPI version
    passes to it.
    """
    original = app.openapi

    def custom():
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = enrich(original())
        return app.openapi_schema

    app.openapi = custom
    return app


# --- Shared security, headers and error bodies ------------------------------------

BEARER_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "description": (
        "Optional service-to-service credential. This API never enforces a bearer token "
        "on its own endpoints. An incoming `Authorization` header is forwarded to Vault "
        "unchanged; when it is absent the configured `CASEFORGE_TOKEN` is sent instead. "
        "A rejected credential therefore surfaces as Vault's own 401 or 403, not as a "
        "local authentication failure."
    ),
}

# An empty alternative is how OpenAPI expresses optional authentication.
OPTIONAL_SECURITY = [{}, {"BearerAuth": []}]

CORRELATION_RESPONSE_HEADER = {
    "description": (
        "The trace used for this request. A submitted value is preserved; a missing or "
        "empty one is replaced by a generated UUID. Requests the HTTP server rejects "
        "before the application sees them, and unhandled server errors, carry no trace."
    ),
    "schema": {"type": "string"},
}

SHARED_PARAMETERS = {
    "CorrelationId": {
        "name": "X-Correlation-ID",
        "in": "header",
        "required": False,
        "description": (
            "Trace forwarded to every dependency and returned on handled responses. Any "
            f"printable-ASCII value of at most {HEADER_LIMIT} characters is accepted; it "
            "does not have to be a UUID. Omit it to have one generated."
        ),
        "schema": {"type": "string", "maxLength": HEADER_LIMIT},
    },
    "IdempotencyKey": {
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "description": (
            "Validated under the same printable-ASCII and "
            f"{HEADER_LIMIT}-character rule as the other shared headers. This API neither "
            "deduplicates on it nor forwards it to Vault, so sending it guarantees no "
            "persistent deduplication."
        ),
        "schema": {"type": "string", "maxLength": HEADER_LIMIT},
    },
}

ERROR_SCHEMAS = {
    "ErrorDetail": {
        "type": "object",
        "title": "ErrorDetail",
        "description": "Domain and dependency failures report a single message string.",
        "properties": {"detail": {"type": "string"}},
        "required": ["detail"],
    },
    # Replaces FastAPI's generated component, which advertises `input` and `ctx`.
    # Both controllers strip those fields so submitted content is never reflected.
    "ValidationError": {
        "type": "object",
        "title": "ValidationError",
        "description": "One rejected field. The submitted value is deliberately omitted.",
        "additionalProperties": False,
        "required": ["loc", "msg", "type"],
        "properties": {
            "loc": {
                "type": "array",
                "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                "description": 'Path to the rejected field, e.g. `["body", "language"]`.',
            },
            "msg": {"type": "string"},
            "type": {"type": "string"},
        },
    },
    "HTTPValidationError": {
        "type": "object",
        "title": "HTTPValidationError",
        "description": "Request-validation failures report a list of rejected fields.",
        "required": ["detail"],
        "properties": {
            "detail": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/ValidationError"},
            }
        },
    },
}

MIXED_422_SCHEMA = {
    "oneOf": [
        {"$ref": "#/components/schemas/HTTPValidationError"},
        {"$ref": "#/components/schemas/ErrorDetail"},
    ],
    "description": (
        "Request validation returns a list of rejected fields; the domain and "
        "content-limit rules return a single message string."
    ),
}


def example(summary, value):
    return {"summary": summary, "value": value}


def json_response(description, schema, examples):
    return {
        "description": description,
        "headers": {"X-Correlation-ID": CORRELATION_RESPONSE_HEADER},
        "content": {"application/json": {"schema": schema, "examples": examples}},
    }


def error_response(description, causes):
    """A single-string `detail` failure, with one example per real cause."""
    return json_response(
        description,
        {"$ref": "#/components/schemas/ErrorDetail"},
        {name: example(summary, {"detail": detail}) for name, summary, detail in causes},
    )


def unprocessable_response(description, validation_example, causes):
    """422 covers both the validation list and the single-string domain bodies."""
    examples = {"validation": example(*validation_example)}
    examples.update(
        {name: example(summary, {"detail": detail}) for name, summary, detail in causes}
    )
    return json_response(description, MIXED_422_SCHEMA, examples)


def bad_header_response():
    return error_response(
        "A shared HTTP header was rejected before the route ran; the response still "
        f"carries a generated trace. The limit is {HEADER_LIMIT} characters of printable "
        "ASCII (code points 32-126) on `X-Correlation-ID`, `Authorization` and "
        "`Idempotency-Key`.",
        [("header", "Rejected shared header",
          "Invalid HTTP tracing or authorization header")],
    )


def vault_denied_response(status):
    challenge = " A `WWW-Authenticate: Bearer` challenge is returned." if status == 401 else ""
    return error_response(
        "Vault refused the credential used to read the source record. This API applies "
        "no authentication of its own; the status is propagated from Vault." + challenge,
        [("vault", "Vault denied the source read",
          "Vault denied access to the source record")],
    )


def provider_causes():
    """Model-provider failures shared by translation and semantic assessment."""
    return {
        "502": [
            ("provider_incomplete", "Provider answered without a usable result",
             "Language model returned an incomplete assessment"),
            ("provider_unsuccessful", "Provider answered with an error status",
             "Language model returned an unsuccessful response"),
            ("provider_invalid",
             "Provider answered with something other than the expected object",
             "Language model returned an invalid assessment"),
        ],
        "503": [
            ("provider_unconfigured", "OPENAI_API_KEY is unset or empty",
             "Language model service is not configured"),
            ("provider_unavailable",
             "Provider connection, authentication or rate-limit failure. Authentication "
             "and rate-limit errors are mapped here, not to 502.",
             "Language model service is unavailable"),
        ],
        "504": [
            ("provider_timeout", "Provider exceeded the 60-second deadline",
             "Language model request timed out"),
        ],
    }


def provider_input_cause():
    return (
        "provider_input",
        f"Serialised model input exceeded {MAX_PROVIDER_INPUT_CHARACTERS} characters",
        "Content exceeds the language model input limit",
    )


def vault_causes():
    """Failures every route that reads an authoritative Vault record can return."""
    return {
        "502": [
            ("vault_unsuccessful",
             "Vault answered with an unexpected status, including a refused redirect",
             "Vault returned an unsuccessful response"),
            ("vault_json", "Vault answered with a body that is not JSON",
             "Vault returned invalid JSON"),
            ("vault_record", "Vault answered with a record that fails the source contract",
             "Vault returned an invalid source record"),
        ],
        "503": [
            ("vault_unavailable", "Vault could not be reached",
             "Vault is unavailable"),
            ("vault_token",
             "CASEFORGE_TOKEN holds characters that cannot be sent as a header",
             "Vault authentication is not configured correctly"),
        ],
        "504": [
            ("vault_timeout", "Vault exceeded the 5-second timeout",
             "Vault request timed out"),
        ],
    }


def merge_causes(*groups):
    """Combine cause groups keyed by status, preserving order and dropping duplicates."""
    merged = {}
    for group in groups:
        for status, causes in group.items():
            existing = merged.setdefault(status, [])
            names = {name for name, _, _ in existing}
            existing.extend(cause for cause in causes if cause[0] not in names)
    return merged


# --- Draft components shared by both services -------------------------------------

SECTION_DESCRIPTIONS = {
    "context": "Client type and region, composed from the source record.",
    "challenge": "The engagement problem statement.",
    "approach": "The solution that was delivered.",
    "technology": "Technologies recorded on the source, joined into one entry.",
    "outcomes": "Measured outcomes, or a `[MISSING: ...]` marker when the source records none.",
}

ENTRY_COMPONENTS = {
    "titles": "TitleEntry",
    "context": "ContextEntry",
    "challenge": "ChallengeEntry",
    "approach": "ApproachEntry",
    "technology": "TechnologyEntry",
    "outcomes": "OutcomesEntry",
}

PROBLEM_SCHEMA = {
    "type": "object",
    "title": "Problem",
    "description": (
        "One reason a draft was blocked. Different checks report different fields, so "
        "only `type` and `why` are always present."
    ),
    "required": ["type", "why"],
    "properties": {
        "type": {
            "type": "string",
            "description": "The check that produced the problem.",
            "examples": [
                "ungrounded_number", "unverifiable_quantity", "unsupported_claim",
                "client_named_without_consent", "invalid_source_reference",
                "language_mismatch",
            ],
        },
        "why": {"type": "string", "description": "Why the draft cannot be published."},
        "span": {
            "type": "string",
            "description": (
                "JSON pointer into the draft, e.g. `/sections/outcomes/0/outcomes`. "
                "Absent on problems that are not scoped to one span."
            ),
        },
        "value": {
            "description":
                "The offending value. Usually a string; some claim checks report a list.",
        },
        "unit": {"type": "string", "description": "Normalised unit on quantity problems."},
    },
    "additionalProperties": True,
}


def entry_schema(component, field, description, page_required=True):
    """One title or section entry. Input entries may omit `page`; output entries carry it."""
    page = {"type": "string", "description": SOURCE_ID_NOTE}
    if not page_required:
        page["description"] = (
            "Optional on input. When present it must equal the requested `record_id`; "
            "when absent, normalisation fills it in."
        )
    return {
        "type": "object",
        "title": component,
        "additionalProperties": False,
        "required": [field, "page"] if page_required else [field],
        "properties": {
            field: {"type": "string", "description": description},
            "page": page,
        },
    }


def draft_schemas():
    """Canonical single-source MCS: the Generator response and the normalised draft."""
    schemas = {
        ENTRY_COMPONENTS["titles"]: entry_schema(
            ENTRY_COMPONENTS["titles"], "title", "Case-study title prose."
        )
    }
    for name, field in SECTION_FIELDS.items():
        schemas[ENTRY_COMPONENTS[name]] = entry_schema(
            ENTRY_COMPONENTS[name], field, SECTION_DESCRIPTIONS[name]
        )
    schemas["Citation"] = {
        "type": "object",
        "title": "Citation",
        "additionalProperties": False,
        "required": ["claim", "source_ref", "page_ref"],
        "properties": {
            "claim": {"type": "string", "description": "The asserted outcome text."},
            "source_ref": {
                "type": "string",
                "description": (
                    "Must match one of the source record's outcome `source_ref` values. "
                    "Anything else becomes an `invalid_source_reference` problem."
                ),
            },
            "page_ref": {"type": "string", "description": SOURCE_ID_NOTE},
        },
    }
    schemas["McsDraft"] = {
        "type": "object",
        "title": "McsDraft",
        "description": (
            "Canonical single-source draft. Every title, section entry and citation is "
            "bound to one Vault record, and only this prose may be rendered. The whole "
            f"document is limited to {MAX_DRAFT_CHARACTERS} serialised characters and "
            f"{MAX_DRAFT_DEPTH} levels of nesting."
        ),
        "additionalProperties": False,
        "required": [
            "engagement_ids", "titles", "sections", "citations", "client_named", "language",
        ],
        "properties": {
            "engagement_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 1,
                "description": "Exactly `[record_id]`; a draft never spans two sources.",
            },
            "titles": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/" + ENTRY_COMPONENTS["titles"]},
            },
            "sections": {
                "type": "object",
                "description": "The five standard case-study sections, always all present.",
                "additionalProperties": False,
                "required": list(SECTION_FIELDS),
                "properties": {
                    name: {
                        "type": "array",
                        "description": SECTION_DESCRIPTIONS[name],
                        "items": {"$ref": "#/components/schemas/" + ENTRY_COMPONENTS[name]},
                    }
                    for name in SECTION_FIELDS
                },
            },
            "citations": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Citation"},
                "description":
                    "One entry per recorded outcome; empty when the source records none.",
            },
            "client_named": {
                "type": "boolean",
                "description": (
                    "True only when the source record sets `may_be_named` to true. It "
                    "reports the source's consent; it does not grant it."
                ),
            },
            "language": {"type": "string", "enum": LANGUAGES},
        },
    }
    return schemas


def install_shared(schema, draft_output=False, problem=False):
    """Add the security scheme, shared header parameters and shared components.

    The draft and problem components are opt-in so neither service publishes a
    component nothing in its own document references.
    """
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["BearerAuth"] = BEARER_SCHEME
    components.setdefault("parameters", {}).update(SHARED_PARAMETERS)
    schemas = components.setdefault("schemas", {})
    schemas.update(ERROR_SCHEMAS)
    if draft_output:
        schemas.update(draft_schemas())
    if problem:
        schemas["Problem"] = PROBLEM_SCHEMA
    return schema


def apply_shared_headers(operation):
    """Document the two request headers the middleware validates on every route."""
    operation.setdefault("parameters", []).extend([
        {"$ref": "#/components/parameters/CorrelationId"},
        {"$ref": "#/components/parameters/IdempotencyKey"},
    ])
    return operation


def operations(schema):
    """Yield every (path, method, operation) in the document."""
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            yield path, method, operation
