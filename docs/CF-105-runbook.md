# CF-105 HTTP-only runbook

## Scope and state

The supported runtime has seven separate APIs and two interfaces. Records and
drafts cross service boundaries over HTTP. Vault's database, Publisher's
artifact store, packaged templates/fonts, model cache, temporary uploads and
user downloads remain local storage; they are not shared service inputs.

The cutover started from `cf-100-verifier-vault-gate` at `b4bf5c3`, on branch
`cf-105-http-only-cutover`, preserving pre-existing local changes. A working-tree
implementation is not a released revision. This document does not imply that
live acceptance has passed or a release tag exists.

Full EN/DE/TR generation and verification are in scope. General PDF extraction,
OCR, multi-source synthesis and generic idempotency infrastructure are outside
this delivery. Librarian can select a source; generation uses one Vault record.

## Setup and processes

Use Python 3.11 and Node.js. From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix front-end ci
```

Use an existing virtual environment if already configured. Copy `.env.example`
to `.env` only if that local file does not exist, then supply credentials there.
The process environment takes precedence over `.env`.

| Setting | Meaning |
|---|---|
| `OPENAI_API_KEY` | OpenAI credential for generation and semantic verification |
| `GENERATOR_TRANSLATION_MODEL` | Generation/translation model, default `gpt-5.5` |
| `VERIFIER_SEMANTIC_MODEL` | Independent verifier model, default `gpt-5.5` |
| `CASEFORGE_TOKEN` | Optional service credential forwarded server-side by both UIs |
| `CASEFORGE_VAULT_DB` | Vault-owned SQLite file |
| `CASEFORGE_ARTIFACT_DIR` | Publisher-owned artifact directory |
| `LIBRARIAN_MODEL` | Cached embedding model, default `sentence-transformers/all-MiniLM-L6-v2` |
| `VAULT_URL`, `GENERATOR_URL`, `LIBRARIAN_URL`, `READER_URL`, `VERIFIER_URL`, `PUBLISHER_URL`, `ANALYST_URL` | Service base URLs |

Never put secrets in `VITE_*` variables or commit `.env`. Provision Librarian's
embedding model once, then start the real APIs and both interfaces:

```powershell
python scripts/provision_librarian.py
python scripts/run_mesh.py --isolated --with-ui
```

Provisioning downloads weights to the model cache. Requests do not download
missing weights. Generation by known record ID does not depend on Librarian.
`--isolated` creates temporary Vault/artifact stores and removes them at shutdown.
Omit it to use configured persistent storage. An isolated Vault starts empty:
upload a supported PDF first. Logs are under `out/logs/`. Ctrl+C stops the
processes owned by this launcher. Save acceptance evidence outside its temporary
store.

| API | Port | Main routes |
|---|---|---|
| Vault | 8000 | `/engagements`, `/engagements/{id}` |
| Generator | 8001 | `/generate` |
| Librarian | 8002 | `/search`, `/match` |
| Reader | 8003 | `/extract` |
| Verifier | 8004 | `/verify` |
| Publisher | 8005 | `/publish`, `/artifacts/{id}/download`, `/artifacts/{id}/provenance` |
| Analyst | 8007 | `/coverage`, `/gaps` |

Default host is `127.0.0.1`. React is at **http://127.0.0.1:5173** and Streamlit
at **http://127.0.0.1:8501**. The local launcher requires loopback service URLs
without path prefixes. Each API has `/health`, `/docs`, and `/openapi.json`.
Liveness alone does not establish dependency or model availability.

To run individual services, use separate terminals:

```powershell
python -m uvicorn vault.vault:create_app --factory --host 127.0.0.1 --port 8000
python -m uvicorn generator.GeneratorController:app --host 127.0.0.1 --port 8001
python -m uvicorn librarian.service:app --host 127.0.0.1 --port 8002
python -m uvicorn reader.api:create_app --factory --host 127.0.0.1 --port 8003
python -m uvicorn verifier.VerifierController:app --host 127.0.0.1 --port 8004
python -m uvicorn publisher.service:app --host 127.0.0.1 --port 8005
python -m uvicorn analyst.api:app --host 127.0.0.1 --port 8007
```

## Reader documents and storage

Upload a text-layer PDF containing explicit labelled fields and numbered
sections. For example:

```text
Engagement ID: eng-demo-01
Client: Example Bank
Client type: Retail bank
Domain: Payments
Region: TR

1. Challenge
Payment processing required manual reconciliation.

2. Approach
The team automated reconciliation with Python.

3. Technology
Python

4. Outcomes
- Reconciliation time decreased by 45%.
```

ID, client, client type, domain, region, Challenge and Approach are required.
Regions are `UK`, `DE`, `NL`, `TR`, or `GCC`; IDs cannot contain path separators.
Missing/conflicting fields, scans, corrupt PDFs and unsupported structures cause
`422`. Production extraction does not use OCR or a model to complete missing
facts. Technologies and outcomes come from explicit sections. Absent outcomes
produce `outcomes: []`. References retain the actual upload filename and page.
The document's client name is not naming permission: `may_be_named` defaults to
false.

`POST /extract` takes multipart field `document`, maximum 20 MiB. The extracted
record can still be returned when storage is unconfirmed. Inspect
`X-Vault-Stored` and `X-Vault-Detail`; generation must wait for confirmed storage.
`?store=false` extracts only and does not satisfy that prerequisite. Reader is
the only writer in the supported upload workflow; neither UI POSTs the returned
record a second time.

After a timeout or conflicting create, Reader reads the same ID over HTTP.
Matching content confirms storage; different content is a conflict. If absent,
Reader waits 0.5 seconds and makes at most one further write. An unresolved
result remains unconfirmed. This is a narrow reconciliation protocol, not
general exactly-once delivery.

## HTTP contracts

All calls preserve `X-Correlation-ID`, creating one at the beginning if needed.
Incoming authorization takes precedence over the configured service token.
Writes carry `Idempotency-Key`, but generic POST retries are disabled and the
header alone does not guarantee deduplication.

| Operation | Request | Success |
|---|---|---|
| List | Vault `GET /engagements?limit=100&offset=0` | `{items, total, limit, offset}` |
| Source | Vault `GET /engagements/{id}` | Engagement Record |
| Generate | `POST /generate` with `{record_id, language}` | Single-source MCS |
| Verify | `POST /verify` with `{record_id, draft, language}` | `{engagement_id, verdict, problems}` |
| Publish | `POST /publish` with `{record_id, draft, language, format, layout}` | `201` artifact metadata |
| Download | Publisher `GET /artifacts/{id}/download` | Document bytes |
| Provenance | Publisher `GET /artifacts/{id}/provenance` | JSON sidecar |

Languages are `en`, `de`, and `tr`, default `en`. The canonical draft retains
`engagement_ids`, `titles`, `sections`, `citations`, `client_named`, and `language`.
The five sections are context, challenge, approach, technology, and outcomes.
Translation changes visible prose while preserving keys, IDs, references and
missing-data markers. Conflicting source or language identities return `422`.

For a source already stored in Vault, generate with:

```json
{"record_id":"eng-demo-01","language":"tr"}
```

Send the resulting or edited draft as `draft` to verification. HTTP 200 returns
either `PASS` with no problems or `BLOCK` with problems. HTTP errors are not
verification verdicts and cannot authorize publication.

```json
{"engagement_id":"eng-demo-01","verdict":"PASS","problems":[]}
```

Publication defaults to `docx` and `full-case-study`. PDF also supports
`one-pager` and `single-slide`; DOCX rejects non-default layouts. The Publisher
response provides URLs instead of server filesystem paths:

```json
{
  "artifact_id": "<server-generated-uuid>",
  "filename": "<document-filename>",
  "media_type": "application/pdf",
  "download_url": "/artifacts/<server-generated-uuid>/download",
  "provenance_url": "/artifacts/<server-generated-uuid>/provenance"
}
```

Download these paths from Publisher with applicable authorization. Provenance
contains source IDs/references, a content hash and freshness. Unknown freshness
because a completion date is absent is distinct from an unknown Verifier
verdict; it does not invent a date.

Deprecated Generator/Verifier HTTP adapters also fetch facts from Vault, ignoring
submitted source content. They do not restore file-based runtime inputs.

## Verification and publication boundary

Verifier checks titles, nested section text and visible citation claims. Numeric
normalization handles supported EN/DE/TR percentages, decimal separators and
duration units, distinguishing percentages from percentage points. Ambiguous
forms fail conservatively. A number present under a different source metric is
not sufficient evidence.

Every HTTP `PASS` requires independent semantic assessment of all visible spans
against the original Vault record. Responses must cover every span and bind
factual evidence to real source fields and literal source quotations. Missing
or fabricated evidence cannot become PASS. Unsupported, contradictory or
uncertain claims produce BLOCK. Deterministic checks can BLOCK without a model
call, but never bypass the semantic PASS gate.

Model calls have a 60-second limit and SDK retries disabled. Missing credentials,
provider outages, malformed responses and timeouts produce HTTP errors. Upstream
verification and publication timeouts allow time for the semantic gate.

Publisher converts MCS to final display content before asking Verifier. It
renders that verified prose without later translation or rewriting. Only a
matching source ID, PASS and an empty problem list permit artifact creation.
BLOCK yields `422`; unknown verdicts and malformed/mismatched dependency
responses fail and create no artifact. Publisher does not trust a UI's old PASS.

The DOCX template and licensed DejaVu Unicode fonts are packaged in
`publisher/assets/`. Missing assets are startup errors. PDF embeds these fonts;
template/font maintenance is separate from runtime data transfer.

## Interfaces and CLI

Both interfaces provide upload/select → language → generate → edit → verify →
human approval → publish → document/provenance download. Source, language or
draft changes clear verification and approval. Approval is bound to those
values and draft content. Errors stop the current stage and show the correlation
ID. Duplicate in-flight clicks are prevented.

React calls `/api/{service}/...` through a local Vite proxy. The service token is
added server-side, not included in the browser bundle. Deploying static build
files separately requires an equivalent server-side proxy. Streamlit also calls
HTTP APIs from its server; session state is not another service's record source.

```powershell
python -m streamlit run console/console.py --server.address 127.0.0.1 --server.port 8501
npm --prefix front-end run dev -- --host 127.0.0.1 --port 5173
```

The supported CLI is an HTTP client:

```powershell
python -m integration.one_flow --document reader/fixtures/two_column_closeout.pdf --language en
python -m integration.one_flow --record-id eng-01 --language de
```

Without `--approve`, it generates and verifies but does not publish. For an
explicitly approved CLI run:

```powershell
python -m integration.one_flow --record-id eng-01 --language tr --approve --format pdf --layout one-pager --out out/eng-01-tr.pdf
```

`--out` saves HTTP-downloaded bytes to the user's destination, not an intermediate
service handoff. The flag authorizes publication for that run; use an interface
for interactive draft review. `scripts/run_pipeline.sh` forwards its arguments
to this HTTP client.

Librarian search and Analyst summaries use Vault HTTP:

```powershell
python -m librarian.librarian "Python payment reconciliation" --top 3
python -m analyst.analyst --coverage
python -m analyst.analyst --recommend
python -m streamlit run analyst/app.py --server.port 8502
```

## Failure handling

| Condition | HTTP result |
|---|---|
| Missing source | `404` |
| Dependency authorization denial | `401` or `403` |
| Invalid input or source/language conflict | `422` |
| Dependency unavailable | `503` |
| Dependency timeout | `504` |
| Malformed dependency response | `502` |
| Unsupported Reader document | `422` |
| Publisher final gate BLOCK | `422` |

Errors retain FastAPI's `detail` envelope. Reader's successful extraction with
unconfirmed storage uses its storage headers as described above. Find related
log entries by correlation ID. Fix the failing service or input before retrying
the user action; do not enable a seed/corpus fallback to hide a failure.

## Acceptance and release

```powershell
python -m pytest -q
npm --prefix front-end test
npm --prefix front-end run build
npm --prefix front-end run lint
```

`pytest.ini` explicitly selects isolated cutover tests and compatible regressions.
Synthetic providers are injected only in tests; writes use temporary stores.
These checks demonstrate contracts and controlled failures, not real model
accuracy or a live multi-process mesh.

Run the separate production-process smoke test with `python -m tests.process_smoke`.
It starts seven real APIs with private temporary stores, uses a provisioned
Librarian cache, and checks dependency outages with model access deliberately
disabled. It writes `out/acceptance/process-smoke.json`; it is not model acceptance.
For manual offline UI checks, `python -m tests.ui_mesh --with-ui` starts the
explicit synthetic harness with React on 15173 and Streamlit on 18501.
See [implementation evidence](CF-105-implementation.md) for completed and pending checks.

Historical `generator/test_generator*.py`, `reader/test_reader.py`,
`publisher/test_publisher.py`, `vault/test_vault.py`, and archive-based Verifier
tests are outside the default selection. Some require the separately supplied
`caseforge-testdata` archive, some exercise superseded direct APIs, and some call
real models or write outputs. Inspect dependencies and storage behavior before
running them explicitly. Excluded tests are not counted as passing.

Start a fresh isolated production mesh with a real key and provisioned Librarian
cache, then run:

```powershell
python scripts/live_acceptance.py --output out/acceptance/live.json
```

The runner refuses a nonempty Vault, uploads 12 synthetic PDFs through Reader,
and evaluates every source in EN/DE/TR. It checks labelled negatives,
publishes/downloads clean outputs, and exercises Librarian and Analyst. Evidence
records the commit, dirty-tree state, verdicts, artifacts and correlation IDs.
Missing `OPENAI_API_KEY` or any failure returns exit code `2` with its reason;
that is not completed live acceptance.

A successful runner still leaves these release gates to complete and record:

1. Both actual interfaces using real providers: EN/DE/TR PASS and BLOCK, edit
   and language-change approval invalidation, and working downloads.
2. Vault, Librarian and Verifier outages plus provider failures: expected errors,
   retained correlation IDs, and no artifact after failed final verification.
3. DOCX and all three PDF layouts: Turkish glyphs, long German text, page
   overflow, and agreement between verified and rendered prose.
4. All checks and OpenAPI/runbook evidence on the same clean commit, recording
   environment and model versions without secrets.

`tests/ui_mesh.py` is a synthetic UI harness with fake translation, semantic and
search providers. It cannot satisfy real-provider gates. The real launcher is
`scripts/run_mesh.py`.

Create the annotated `cf-105-http-only` tag only when every release gate passes
on the same clean commit. The runner does not create the tag or declare the
remaining gates complete. Do not tag a dirty tree or mock-only acceptance.

If cutover acceptance fails, preserve the candidate changes/evidence and leave
it untagged. Return the deployment to the recorded pre-cutover revision
`b4bf5c3`; do not re-enable file fallbacks in the candidate. Check persistent
Vault data compatibility before switching deployed revisions. Isolated
acceptance stores are disposable.
