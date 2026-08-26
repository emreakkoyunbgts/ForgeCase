# 2 · VAULT — Kaan

**Store the Engagement Records. Serve them over a REST API.**

## Run it
```bash
python -m vault.vault store records/eng-01.json
python -m vault.vault get eng-01
python -m vault.vault load-all
python -m vault.vault serve          # API on :8000 — docs at /docs
```

## Levels
- **L1** — E-R model, SQLite schema. Save a record, read it back *identically*.
- **L2** — FastAPI: `POST`, `GET /{id}`, `GET` list. Happy path + 404 tests.
- **L4** — Full REST + ETag concurrency:
  - `POST /engagements` → 201 create, **409** if id exists
  - `PUT /engagements/{id}` → replace (needs `If-Match` ETag)
  - `DELETE /engagements/{id}` → 204 (needs `If-Match`)
  - `GET /engagements?domain=&region=&limit=&offset=` → filter + pagination
  - Stale ETag → **412**; missing `If-Match` → **428**
- **CF-86 (harden)** — optimistic concurrency, same gate, stricter contract:
  - **409** = POST of an id that already exists (create conflict)
  - **412** = PUT/DELETE with a stale If-Match (lost the race; response
    carries the current `ETag` so you can retry)
  - **428** = If-Match missing
  - `If-Match: *` = any current version (record must still exist)
  - `/docs` documents the If-Match header on PUT and DELETE
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

## Calling Vault from another service

```bash
# leave CASEFORGE_TOKEN unset and Vault serves everyone (it warns at startup)
$env:CASEFORGE_TOKEN = "dev-token"        # PowerShell
python -m vault.vault serve
```

```python
requests.get(
    "http://127.0.0.1:8000/engagements/eng-01",
    headers={"Authorization": f"Bearer {os.environ['CASEFORGE_TOKEN']}"},
    timeout=5,
)
```

The token comes from the environment — never from code, never from git.
Auth is rolled out in stages on purpose: with `CASEFORGE_TOKEN` unset nothing
breaks, so no prototype is blocked mid-migration. Set the variable everywhere
and the door is locked.

## Watch out
- `eng-12` has an empty `outcomes` list — schema must handle it.
- `eng-02` is the only record with `may_be_named: true` — do not lose that flag.
- If you change the schema, delete `vault/engagements.db` and run `load-all` again
  (old stub DBs cause "no column named client" errors).
