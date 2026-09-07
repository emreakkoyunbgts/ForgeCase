# 8 · VERIFIER — Ömer

**The gate. Catches invented facts before they reach a client.**

Taha's Generator has grounding rules *in its prompt*. But prompts can be
ignored, and models drift. **You are the independent check that actually
enforces the rule.** Nothing gets published that you reject.

This is a parsing and matching problem — which is exactly what your compiler
coursework (Lex, Yacc, grammars) trained you for.

## Run it

### HTTP service (CF-100)

From the repository root, with the dependencies in `requirements.txt` installed:

```bash
python -m uvicorn verifier.VerifierController:app --host 127.0.0.1 --port 8004
```

- `VAULT_URL`: Vault base URL, default `http://localhost:8000`.
- `CASEFORGE_TOKEN`: optional service credential for Vault. An incoming
  `Authorization` header takes precedence; it is forwarded without substitution.
  Without that header, a configured token is sent as a Bearer credential.
  Keep credentials in the environment, never in request examples or source files.
- `GET /health`: returns `200 {"status":"ok"}`. This is process liveness;
  it does not claim that Vault is reachable.
- `GET /docs` and `GET /openapi.json`: generated API documentation and schema.

`POST /verify` accepts a record ID and a draft. The source of truth is always
`GET {VAULT_URL}/engagements/{record_id}`; there is no record-file fallback.
For example, after a **synthetic** `eng-demo` record with a 45% outcome exists in Vault:

```json
{
  "record_id": "eng-demo",
  "draft": {
    "engagement_id": "eng-demo",
    "sections": {"outcomes": "Payment latency reduced by 45%."}
  }
}
```

A valid request returns HTTP 200 with the existing report contract:

```json
{"engagement_id":"eng-demo","verdict":"PASS","problems":[]}
```

A draft containing an invented number or an unconsented client name instead
returns `verdict: "BLOCK"` with reasons in `problems`, still HTTP 200. An HTTP
error is not a verification verdict and must never authorize publication.
Nonnumeric factual vocabulary must also occur in the authoritative record;
common connective words are ignored. This conservative lexical check can
reject a synonym that the source does not use.

The draft must contain a nonempty `sections` object with case-study text in at
least one standard section: context, challenge, approach, technology, outcomes.
Plain section text and the Generator's nested MCS section lists are supported.
If present, `engagement_id` must equal `record_id`; `engagement_ids` must be
exactly `[record_id]`. MCS section/title `page` source IDs must also match.
Draft nesting is limited to 32 levels. This endpoint verifies one source record per request.
Flat translation payloads and drafts for multiple source records are rejected.

`POST /verify/{record_id}` remains available for Console and Publisher with the
existing `{"record": {...}, "mcs": {...}}` body. `record.id` must match the path,
but all submitted record facts are ignored: this route also fetches its source
from Vault. It returns the same report and is marked deprecated in OpenAPI.

Vault calls use a 5-second timeout for each HTTP network phase and one attempt.
Redirects are not followed. The source response must have the shared required
fields, the requested ID, explicit boolean naming consent, and valid outcome
objects. Invalid or incomplete source responses cannot produce PASS.

| Condition | HTTP status |
|---|---|
| Invalid request, empty draft, conflicting record IDs | 422 |
| Invalid tracing/authorization header characters | 400 |
| Source record missing in Vault | 404 |
| Vault rejects access | 401 / 403 |
| Vault timeout | 504 |
| Vault connection/transport failure | 503 |
| Other Vault status, redirect, malformed JSON or invalid source | 502 |

Errors use FastAPI's JSON `detail` envelope. Upstream bodies and credentials
are not copied into errors or logs. `X-Correlation-ID` is preserved (or created
when absent), sent to Vault, and returned on success and handled errors.
Verifier imports do not create log files; configure logging through the server.

Run the self-contained HTTP acceptance tests with synthetic data:

```bash
python -m pytest -q verifier/test_api.py verifier/test_vault_contract.py
```

These tests execute the real Verifier checks. Failure cases use a controlled
HTTP transport; the Vault contract tests use its actual FastAPI routes with
storage replaced by in-memory synthetic records. They need no API key, LLM,
live services, database changes, or external test-data archive. They do not
establish full-mesh or Publisher publication safety.

The older `test_verifier.py` clean/poisoned tests still require the separately
provided `caseforge-testdata` archive. The existing claim-checking limitations
(including metric meaning, semantic paraphrases and translation grounding)
remain. Numeric and lexical checks include titles and sections.

### CLI

```bash
python -m verifier.verifier drafts/eng-01.json records/eng-01.json
echo $?     # 0 = PASS, 1 = BLOCK
```

## Your levels
- **L1** — Extract every number / % / date from the case study. Check each one
  against the source record. Report anything in the output but not the source.
- **L2** — Also catch the client's real name appearing when `may_be_named` is
  false. Clear report. Exit **1** on failure so you can gate a build.
- **L3** — Claim-level parsing (split prose into assertions and verify each).
  Fuzzy matching so `45 percent` == `45%`.

## Your test data — this is the good bit
| File | Expected result |
|---|---|
| `case_studies/eng-01_clean.json` | **PASS** — find nothing wrong |
| `case_studies/eng-01_POISONED.json` | **BLOCK** — 5 invented facts. Catch all 5. |
| `records/seed/eng-01.json` | the source of truth |
| `expected/poisoned_expected_flags.json` | the answer key |

The poisoned file contains: a fake **42%**, a fake **300%**, a wrong **3 months**
(it was 11), a wrong **2019**, and the client **named without consent**.

You must catch all five — and you must **NOT** flag the three real figures
(**45%**, **6 hours**, **90 minutes**). A false alarm is as bad as a miss.
