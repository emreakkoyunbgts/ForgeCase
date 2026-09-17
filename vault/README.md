# Vault

Vault owns Engagement Record persistence and exposes it over HTTP. Reader is the
only writer in the supported document-upload workflow. Downstream services use
Vault endpoints instead of record or corpus files.

python -m vault.vault load-all
python -m vault.vault serve          # API on :8000 — docs at /docs
python -m vault.vault smoke          # CF-114: corpus reachable over HTTP
```

These CLI reads use HTTP. `load-all` imports the corpus fixtures directly into
the database to seed an empty Vault; it is a bootstrap step, not part of the
supported runtime pipeline, where Reader is the only writer. Do not delete a
persistent database to resolve a schema error: inspect and migrate it separately.
The [CF-105 runbook](../docs/CF-105-runbook.md) documents setup, contracts and
isolated acceptance. Historical Vault test modules are not part of default
cutover selection; inspect them before explicit execution.

## Levels
- **L1** — E-R model, SQLite schema. Save a record, read it back *identically*.
- **L2** — FastAPI: `POST`, `GET /{id}`, `GET` list. Happy path + 404 tests.
- **L4** — Full REST + ETag concurrency:
  - `POST /engagements` → 201 create, **409** if id exists
  - `PUT /engagements/{id}` → replace (needs `If-Match` ETag)
  - `DELETE /engagements/{id}` → 204 (needs `If-Match`)
  - `GET /engagements?domain=&region=&limit=&offset=` → filter + pagination
  - Stale ETag → **412**; missing `If-Match` → **428**
- **L5 (stretch)** — Record versioning (as-of):
  - Every `store` / create / update appends an immutable snapshot to `engagement_versions`
  - `GET /engagements/{id}?as_of=ISO8601` → newest snapshot with `recorded_at <= as_of`
  - `GET /engagements/{id}/versions` → version list (`version`, `recorded_at`, `etag`)
  - DELETE removes the current row but keeps history (as-of still works)
- **Validation** — POST/PUT check content against the contract (valid region,
  non-empty `client_type` / `metric` / `source_ref`, boolean `may_be_named`).
  Bad data gets a **422** that names the problem, never an opaque 500.
- **CF-84 (service APIs)** — `GET /health` for the mesh: reports `ok` +
  record count when the database answers, **503** when it does not.
- **CF-85 (auth)** — every data endpoint needs
  `Authorization: Bearer <CASEFORGE_TOKEN>`; missing or wrong → **401** with
  `WWW-Authenticate: Bearer`. `/health` and `/docs` stay open so the mesh can
  still poll us. In `/docs`, use the **Authorize** padlock (top right) — paste
  the token only, Swagger adds `Bearer` itself.
- **CF-114 (cutover)** — Vault is the only live engagement store.
  `caseforge-testdata/` stays as seed/fixtures. After `load-all` or
  `smoke`, other services read and write through
  `http://127.0.0.1:8000/engagements`. `python -m vault.vault smoke`
  POSTs the 12 records (or accepts 409 if they are already there), then
  checks `/health`, the list, every id, and a duplicate POST → 409.
```

These CLI reads use HTTP. The legacy `load-all` file import is not a supported
pipeline. Do not delete a persistent database to resolve a schema error: inspect
and migrate it separately. The [CF-105 runbook](../docs/CF-105-runbook.md) documents
setup, contracts and isolated acceptance. Historical Vault test modules are not
part of default cutover selection; inspect them before explicit execution.

## CF-86 concurrency contract

- Duplicate POST returns `409`.
- PUT/DELETE without `If-Match` returns `428`.
- A stale `If-Match` returns `412` and the current `ETag` for a refreshed retry.
- `If-Match: *` accepts any current version; the record must still exist.
- `/docs` documents the `If-Match` header on PUT and DELETE.
