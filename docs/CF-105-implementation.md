# CF-105 implementation evidence

Candidate branch: `cf-105-http-only-cutover`. Base: `b4bf5c3`
(`cf-100-verifier-vault-gate`). Implementation and checks were performed in the
working tree on 8–9 September 2026. Pre-existing local changes were preserved.
The implementation is a review candidate; release acceptance remains incomplete
and no `cf-105-http-only` tag exists.

## Implemented

- HTTP-only Reader → Vault → Generator → Verifier → Publisher workflow,
  single-source MCS, shared trace/auth headers and bounded dependency errors.
- Real structured PDF extraction; required/contradictory fields fail with 422,
  absent outcomes stay empty, naming consent defaults to false. Reader confirms
  ambiguous Vault writes before one bounded retry. No OCR/seed fallback.
- EN/DE/TR translation with complete span coverage, quantity preservation,
  unchanged source references, missing markers and consent protection.
- Independent semantic PASS gate, literal source evidence validation, numeric
  units/percentage points, identity/language checks, and fail-closed model errors.
- Publisher verifies final display prose, checks privacy in visible provenance,
  and renders DOCX or three Unicode PDF layouts. Literal template-like source
  text is preserved. Artifacts and provenance are downloaded through HTTP.
- React and Streamlit selection/upload, editing, verification, content-bound
  approval, publication and downloads. Invalid responses cannot enter approved
  state. Streamlit suppresses duplicate publication within the current session;
  this is not distributed idempotency.
- Vault-backed Librarian/Analyst, HTTP CLI, seven-process launcher, configured
  private stores, packaged assets, OpenAPI snapshots and runbook.

## Verification and its limits

The default `pytest` suite uses temporary stores and injected providers. It
retains the 85 Verifier HTTP/Vault regressions and adds real PDF extraction,
real DOCX/PDF rendering, full HTTP route contracts, Streamlit AppTest, provider
errors, consent leaks, translation corruption and repeated publication tests.
The final default suite result was **243 passed**. Historical archive/model
experiments excluded by `pytest.ini` were not counted as passing.

Frontend `npm test`: 15 passed. These exercise request/response contracts,
approval binding, invalid payloads, proxy authentication and HTTP download bytes.
`npm run build` and `npm run lint` passed without warnings after cleanup.

`python -m tests.process_smoke`: 18 real HTTP checks passed across seven distinct
OS processes and private temporary stores. Reader storage, Vault lookup, real
Librarian retrieval and Analyst coverage/gaps were exercised. Missing provider
configuration and stopped Vault/Librarian/Verifier processes did not produce
artifacts. The same correlation ID appeared in every checked response. The
Windows child-process cleanup was fixed and the smoke run completed normally.
Evidence is generated at `out/acceptance/process-smoke.json`.

Browser checks used explicitly synthetic providers in `tests.ui_mesh`, not real
model results. React Turkish DOCX and German PDF publication/download were
observed. A changed German percentage produced BLOCK and disabled publication.
Streamlit English publication and edit-triggered approval invalidation were
observed. Streamlit supplied document/provenance bytes successfully in AppTest;
its final browser download completion was not independently confirmed.

The Edge extension refused the synthetic PDF file chooser because access to file
URLs was disabled. Browser upload acceptance remains pending; HTTP upload and
storage reconciliation tests passed. Browser upload QA requires file-URL access
on the test browser extension.

Synthetic Turkish and long German PDF previews were visually checked after
font embedding, including the one-pager and slide. Turkish characters and German
umlauts rendered; no text overlap or overflow was observed in these examples.
Generated review files are under `out/qa/` and are not production publications.

## Release remains blocked

`OPENAI_API_KEY` was absent. `scripts/live_acceptance.py` was invoked and wrote an
explicit incomplete result to `out/acceptance/live.json`, before any real model
calls. The 12 sources × 3 languages and labelled negative real-model evaluation
therefore have **not passed**. Both UIs still need complete real-provider
acceptance, browser upload/download completion, and final visual review of the
real outputs on the same clean commit.

The live runner refuses a nonempty Vault, records failures, and never creates a
release tag. Follow [the runbook](CF-105-runbook.md) to complete these gates.
