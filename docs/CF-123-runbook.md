# CF-123 runbook — Generator and Verifier

How to start these two services, send correct requests, and tell one failure from
another. Everything here is reproducible with synthetic data.

The published contracts are the other half of this guide: start each service and open
`/docs`, or read [`docs/openapi/generator.json`](openapi/generator.json) and
[`docs/openapi/verifier.json`](openapi/verifier.json). Full request and response
examples live there; this runbook covers operation.

For the seven-service mesh, the UIs and the release gates, see the
[CF-105 runbook](CF-105-runbook.md). For the HTTP contract acceptance suite, see the
[CF-120 guide](CF-120-contract-suite.md).

---

## A. Prerequisites and running

Work from the repository root with Python 3.11.

If a virtual environment already exists, use it. On Windows the `python` on `PATH` is
often a different interpreter, so call the environment's executable explicitly rather
than relying on activation:

```powershell
.\.venv\Scripts\python.exe --version     # expect 3.11.x
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configuration comes from the process environment first and `.env` second, so an
exported variable wins over the file. Copy `.env.example` to `.env` only if `.env`
does not already exist — never overwrite one that does.

**The minimum useful setup is Vault + Generator + Verifier.** Generating from a record
id you already know needs neither Librarian, Node.js nor either UI. Only the
deprecated query adapter needs Librarian.

Give Vault a private database before running the examples below, so nothing is written
to an existing store:

```powershell
$env:CASEFORGE_VAULT_DB = "$env:TEMP\cf123-vault.db"
```

Without that variable Vault falls back to `vault/engagements.db`.

Start each service in its own terminal, with the shared logging configuration so
request traces are visible:

```powershell
.\.venv\Scripts\python.exe -m uvicorn vault.vault:create_app --factory --host 127.0.0.1 --port 8000 --log-config scripts/http_logging.json
.\.venv\Scripts\python.exe -m uvicorn generator.GeneratorController:app --host 127.0.0.1 --port 8001 --log-config scripts/http_logging.json
.\.venv\Scripts\python.exe -m uvicorn verifier.VerifierController:app --host 127.0.0.1 --port 8004 --log-config scripts/http_logging.json
```

All examples use PowerShell. `curl` on Windows is an alias for `Invoke-WebRequest` and
does not take the flags you may expect, so the examples call `Invoke-RestMethod`
directly.

---

## B. Dependencies, timeouts and configuration

| Flow | Depends on | Timeout | Retry |
|---|---|---|---|
| Generator `POST /generate` | Vault `GET /engagements/{id}` | 5 s | none; redirects are not followed |
| Generator translation (all languages) | Model provider | 60 s | none; SDK retries are disabled |
| Generator `POST /generator/mcs/query` | Librarian `POST /match`, then Vault | 20 s, then 5 s | none |
| Verifier `POST /verify` | Vault, then the semantic provider when nothing blocked | 5 s, then 60 s | none |
| Publisher's final gate | Verifier `POST /verify` | 75 s on the Publisher side | none |

These are per-attempt HTTP timeouts, not an end-to-end service level. **No backoff is
implemented anywhere on these paths**; a failed call is reported, never retried.

| Variable | Used by | Notes |
|---|---|---|
| `VAULT_URL` | Generator, Verifier | Where each service reads source records. Default `http://127.0.0.1:8000`. |
| `LIBRARIAN_URL` | Generator | Query adapter only. Default `http://127.0.0.1:8002`. |
| `OPENAI_API_KEY` | Generator, Verifier | Required for every generation **and every PASS**, in all three languages. |
| `GENERATOR_TRANSLATION_MODEL` | Generator | Default `gpt-5.5`. |
| `VERIFIER_SEMANTIC_MODEL` | Verifier | Default `gpt-5.5`. |
| `CASEFORGE_TOKEN` | Generator, Verifier | Sent to Vault when the caller supplies no `Authorization`. |
| `CASEFORGE_VAULT_DB` | Vault | Database path. Default `vault/engagements.db`. |
| `GENERATOR_URL`, `VERIFIER_URL` | callers and launchers | Where *clients* reach these services. Neither service reads its own. |

Never print or commit the value of `OPENAI_API_KEY` or `CASEFORGE_TOKEN`.

### Headers

`X-Correlation-ID` is preserved when you send one, generated when you do not, forwarded
to Vault and to the provider, and returned on every response the application handles.
It does not have to be a UUID.

`Authorization` is forwarded to Vault as-is; when absent, `CASEFORGE_TOKEN` is used.
**Neither service enforces a bearer token on its own endpoints** — a 401 or 403 from
`/generate` or `/verify` came from Vault.

`Idempotency-Key` is accepted and validated, but these two services neither deduplicate
on it nor forward it. It guarantees nothing.

All three headers are limited to 4096 characters of printable ASCII (code points
32–126). A violation is rejected with `400` before the route runs.

---

## C. Runnable synthetic examples

One fully synthetic source is used throughout: `eng-cf123-01`, an unnamed client with
one recorded outcome of 45%.

### 1. Store the source record

<!-- cf123:source-record -->
```json
{
  "id": "eng-cf123-01",
  "client": "Synthetic Example Bank",
  "client_type": "retail bank",
  "may_be_named": false,
  "domain": "payments",
  "region": "TR",
  "challenge": "Slow payment processing.",
  "solution": "Optimised payment processing.",
  "technologies": ["Python"],
  "outcomes": [
    {"metric": "Payment latency reduced by 45%", "source_ref": "synthetic.pdf#page=1"}
  ]
}
```

```powershell
$source = Get-Content .\cf123-source.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/engagements `
  -ContentType 'application/json; charset=utf-8' -Body $source
```

Expect `201`. A second attempt returns `409`, meaning the record is already stored.

### 2. Confirm both services are up

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8004/health
```

<!-- cf123:health-generator -->
```json
{"status": "ok", "service": "generator", "languages": ["en", "de", "tr"]}
```

<!-- cf123:health-verifier -->
```json
{"status": "ok"}
```

Interactive docs are at `http://127.0.0.1:8001/docs` and `http://127.0.0.1:8004/docs`;
the raw contracts are at `/openapi.json` on each.

### 3. Generate

<!-- cf123:generate-request -->
```json
{"record_id": "eng-cf123-01", "language": "en"}
```

```powershell
$body = @{ record_id = 'eng-cf123-01'; language = 'en' } | ConvertTo-Json -Depth 10
$draft = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/generate `
  -ContentType 'application/json; charset=utf-8' -Body $body
$draft | ConvertTo-Json -Depth 20
```

`-Depth` matters: PowerShell's default of 2 silently truncates the nested draft into
strings like `System.Object[]`. Use `-Depth 20` whenever you print or forward a draft.

Repeat with `language = 'de'` and `language = 'tr'` for the other two. English is not a
shortcut — it goes through the same model step, so all three need a working provider.

<!-- cf123:generate-response-en -->
```json
{
  "engagement_ids": ["eng-cf123-01"],
  "titles": [{"title": "payments for retail bank", "page": "eng-cf123-01"}],
  "sections": {
    "context": [{"region": "retail bank in TR.", "page": "eng-cf123-01"}],
    "challenge": [{"challenge": "Slow payment processing.", "page": "eng-cf123-01"}],
    "approach": [{"approach": "Optimised payment processing.", "page": "eng-cf123-01"}],
    "technology": [{"technologies": "Python", "page": "eng-cf123-01"}],
    "outcomes": [{"outcomes": "Payment latency reduced by 45%", "page": "eng-cf123-01"}]
  },
  "citations": [
    {
      "claim": "Payment latency reduced by 45%",
      "source_ref": "synthetic.pdf#page=1",
      "page_ref": "eng-cf123-01"
    }
  ],
  "client_named": false,
  "language": "en"
}
```

`page` and `page_ref` hold the **source record id**, not a PDF page number.
`client_named` reports the record's `may_be_named`; it does not grant consent.

### 4. Verify the draft you just received

Send the draft back unchanged — `$draft` still holds what step 3 returned. Editing it
before verification is exactly what the gate is there to catch.

```powershell
$request = @{ record_id = 'eng-cf123-01'; draft = $draft; language = 'en' } |
  ConvertTo-Json -Depth 20
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8004/verify `
  -ContentType 'application/json; charset=utf-8' -Body $request
```

Two draft shapes are accepted and normalise to the same document: the Generator's
nested entries, as sent above, or plain section prose. The plain form is the shortest
way to verify a draft you wrote by hand, and it produces the identical verdict:

<!-- cf123:verify-request -->
```json
{
  "record_id": "eng-cf123-01",
  "draft": {
    "engagement_id": "eng-cf123-01",
    "sections": {
      "context": "retail bank in TR.",
      "challenge": "Slow payment processing.",
      "approach": "Optimised payment processing.",
      "technology": "Python",
      "outcomes": "Payment latency reduced by 45%"
    }
  },
  "language": "en"
}
```

`sections` is the only required key. `titles`, `citations` and `client_named` are
filled in by normalisation, and each entry's `page` may be omitted — but any source id
or `language` you *do* supply must agree with the request, or you get a `422`.

### 5. Read the verdict

<!-- cf123:verify-response-pass -->
```json
{"engagement_id": "eng-cf123-01", "verdict": "PASS", "problems": []}
```

### 6. Make it BLOCK

Change the recorded 45% to an unsupported 999% and verify again:

```powershell
$draft.sections.outcomes[0].outcomes = 'Payment latency reduced by 999%'
$request = @{ record_id = 'eng-cf123-01'; draft = $draft; language = 'en' } |
  ConvertTo-Json -Depth 20
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8004/verify `
  -ContentType 'application/json; charset=utf-8' -Body $request
```

<!-- cf123:verify-response-block -->
```json
{
  "engagement_id": "eng-cf123-01",
  "verdict": "BLOCK",
  "problems": [
    {
      "type": "ungrounded_number",
      "value": "999%",
      "unit": "percent",
      "why": "this quantity and unit are not supported by the source evidence",
      "span": "/sections/outcomes/0/outcomes"
    }
  ]
}
```

**BLOCK arrives as HTTP 200.** It is a verdict, not an error. This one comes from the
deterministic checks, so it needs no model call at all.

Problems do not share a fixed shape. `type` and `why` are always present; `span`,
`value` and `unit` appear only where the check has them.

### 7. Unknown record — `404`

```powershell
$body = @{ record_id = 'eng-does-not-exist' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/generate `
  -ContentType 'application/json; charset=utf-8' -Body $body
```

<!-- cf123:error-not-found -->
```json
{"detail": "Source record was not found in Vault"}
```

### 8. Identity or language conflict — `422`

Request validation reports a **list**:

<!-- cf123:error-language -->
```json
{
  "detail": [
    {"loc": ["body", "language"], "msg": "Input should be 'en', 'de' or 'tr'", "type": "literal_error"}
  ]
}
```

A draft bound to another source is reported the same way on `POST /verify`, because
normalisation runs inside the request model:

<!-- cf123:error-identity -->
```json
{
  "detail": [
    {"loc": ["body"], "msg": "Value error, draft engagement_id must match record_id", "type": "value_error"}
  ]
}
```

The deprecated `POST /verify/{record_id}` reports its own identity checks as a single
string instead:

<!-- cf123:error-legacy-identity -->
```json
{"detail": "record.id must match the path record_id"}
```

Both shapes are covered by the published `422` schema. Neither ever echoes the draft
you submitted.

### 9. A deprecated adapter

```powershell
$body = @{ id = 'eng-cf123-01' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/generator/mcs/turkish `
  -ContentType 'application/json; charset=utf-8' -Body $body
```

Only the body's `id` is used; every fact still comes from Vault, so a modified body
cannot change the output. **For new work use `POST /generate` with
`{record_id, language}`** — the adapters exist for existing callers.

The query adapter is the one route that needs Librarian, and its two inputs are
query-string parameters rather than a body:

```powershell
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8001/generator/mcs/query?query=payment%20latency&language=en'
```

Every example above that reaches the model needs a real provider credential and
provider access. The offline test suite injects a synthetic provider; passing tests
demonstrate the contracts, not real-model quality.

---

## D. What a green signal does and does not mean

| Situation | Effect |
|---|---|
| Librarian stopped | `POST /generate` with a known id is unaffected; only the query adapter fails (`503`). |
| Vault stopped | Everything fails with `503`. There is no local seed or file fallback. |
| Provider unreachable or unconfigured | No draft is produced, and no PASS can be issued (`503`). |
| Deterministic violation found | Verifier returns BLOCK with HTTP 200 **without** calling the provider. |
| `/health` returns `ok` | The process is running. It says nothing about Vault, Librarian or the provider. |
| Generation succeeded | The draft is grounded, not verified. It is neither approved nor publishable. |
| Verifier returned PASS | Publication re-verifies anyway. A PASS on one draft does not cover an edited one. |

Publisher converts the draft to final display content and sends **that** content back
to `POST /verify` before creating anything. It requires a matching record id, `PASS`
and an empty `problems` list; it does not trust a verdict a UI obtained earlier.

Using Librarian to supply retrieval context to `POST /generate` is separate, still-open
work (finding F-12 / CF-88). Documenting today's query adapter does not deliver it.

---

## E. Troubleshooting

| Symptom | Status | Check | Then |
|---|---|---|---|
| `Invalid HTTP tracing or authorization header` | `400` | Your `X-Correlation-ID`, `Authorization` or `Idempotency-Key`: ≤ 4096 printable-ASCII characters | Resend with a clean header |
| `Vault denied access to the source record` | `401`/`403` | `CASEFORGE_TOKEN`, or the `Authorization` you sent | Fix the credential and resend |
| `Source record was not found in Vault` | `404` | `GET {VAULT_URL}/engagements/{id}` directly | Store the record, then retry |
| `No matching engagement was found` | `404` | Librarian has an indexed corpus | Use `POST /generate` with a known id |
| `detail` is a list | `422` | The field named in `loc` | Correct that field and resend |
| `record.id must match the path record_id` | `422` | Legacy route only: path id against body id | Use `POST /verify` instead |
| `Vault returned an unsuccessful response` | `502` | `VAULT_URL` — a redirect is refused, never followed | Point at the real host with no path prefix |
| `Translation changed …` / `Semantic assessment …` | `502` | The model answered but broke a grounding rule | Retry; if it persists, check the model setting |
| `Language model service is not configured` | `503` | `OPENAI_API_KEY` is set in **this** process | Set it and restart the service |
| `Language model service is unavailable` | `503` | Provider connectivity, credential validity, rate limits | Wait and retry; nothing is retried for you |
| `Vault is unavailable` | `503` | Vault is running on `VAULT_URL` | Start Vault and retry |
| `… request timed out` | `504` | The dependency's own latency | Retry; there is no automatic retry or backoff |

### Following one request through the logs

Send a trace you can search for, then look for it:

```powershell
$trace = 'cf123-' + [guid]::NewGuid()
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/generate `
  -ContentType 'application/json; charset=utf-8' `
  -Headers @{ 'X-Correlation-ID' = $trace } `
  -Body (@{ record_id = 'eng-cf123-01' } | ConvertTo-Json)

Select-String -Path out\logs\*.log -Pattern $trace
```

Logs land in `out/logs/` when the mesh launcher started the services, and on the
terminal when you started uvicorn yourself. The contract runner writes into its own
acceptance directory.

Log the correlation id. Do **not** log the `Authorization` header, the provider key, or
draft bodies.

### Limits

- One source record per draft. Nothing here merges two engagements.
- English, German and Turkish only.
- A draft is capped at 24000 serialised characters and 32 levels of nesting; the model
  input is capped at 80000 characters. Exceeding either returns `422`.
- The `/generator/mcs*` and `/verify/{record_id}` adapters are deprecated.
- Generation and every PASS require the model provider. There is no offline mode.
- The offline suite proves the contracts and the failure behaviour. It does not
  establish real-model accuracy, mesh acceptance or release readiness.

### Keeping the contracts honest

The published snapshots are generated from the running apps, never edited by hand:

```powershell
.\.venv\Scripts\python.exe -B scripts/export_openapi.py --services generator verifier
.\.venv\Scripts\python.exe -B scripts/export_openapi.py --services generator verifier --check
```

`--check` changes nothing and exits non-zero if a snapshot has drifted from the code.
