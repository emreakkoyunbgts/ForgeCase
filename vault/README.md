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
- **L5 (stretch)** — Record versioning (as-of):
  - Every `store` / create / update appends an immutable snapshot to `engagement_versions`
  - `GET /engagements/{id}?as_of=ISO8601` → newest snapshot with `recorded_at <= as_of`
  - `GET /engagements/{id}/versions` → version list (`version`, `recorded_at`, `etag`)
  - DELETE removes the current row but keeps history (as-of still works)

## Watch out
- `eng-12` has an empty `outcomes` list — schema must handle it.
- `eng-02` is the only record with `may_be_named: true` — do not lose that flag.
- If you change the schema, delete `vault/engagements.db` and run `load-all` again
  (old stub DBs cause "no column named client" errors).
