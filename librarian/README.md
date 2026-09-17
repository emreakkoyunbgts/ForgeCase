# Librarian

Librarian ranks Vault engagements for an RFP or requirement. Its corpus is loaded
from the Vault HTTP API, with pagination and cache invalidation when source data
changes. Search can select one Generator source; CF-105 does not mix facts from
several records into one draft.

Provision embedding weights explicitly once before serving search:

```powershell
python scripts/provision_librarian.py
python -m uvicorn librarian.service:app --host 127.0.0.1 --port 8002
```

`LIBRARIAN_MODEL` defaults to `sentence-transformers/all-MiniLM-L6-v2`. Provisioning
may download weights; request handling loads only the cached model and fails
when it is unavailable. Known-ID generation remains independent of this service.

`GET /search?q=...&top=3&strategy=hybrid` returns ranked matches. `POST /match`
accepts an RFP, for example:

```json
{"rfp_text":"Python payment reconciliation","top_k":3,"strategy":"hybrid"}
```

The CLI also calls HTTP:

```powershell
python -m librarian.librarian "Python payment reconciliation" --top 3
```

Configure `VAULT_URL` and `LIBRARIAN_URL` through `.env`. Authorization and
correlation headers follow the [shared runbook](../docs/CF-105-runbook.md).
An empty selection or dependency failure is surfaced to the caller, not replaced
with seed records. Default regression tests use controlled model/search inputs;
real cached-model ranking is a separate live acceptance check.
