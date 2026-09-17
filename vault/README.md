# Vault

Vault owns Engagement Record persistence and exposes it over HTTP. Reader is the
only writer in the supported document-upload workflow. Downstream services use
Vault endpoints instead of record or corpus files.

```powershell
python -m uvicorn vault.vault:create_app --factory --host 127.0.0.1 --port 8000
```

`CASEFORGE_VAULT_DB` selects the SQLite file. For isolated development and
acceptance, use `python scripts/run_mesh.py --isolated`; never clear an existing
Vault as test setup.

| Route | Behavior |
|---|---|
| `GET /engagements` | Filter/paginate; response `{items, total, limit, offset}` |
| `GET /engagements/{id}` | Current record, or `404` |
| `POST /engagements` | Create; `201`, or `409` when ID exists |
| `PUT /engagements/{id}` | Replace with `If-Match` ETag |
| `DELETE /engagements/{id}` | Delete current record with `If-Match` ETag |
| `GET /engagements/{id}/versions` | Immutable version metadata |
| `GET /engagements/{id}?as_of=ISO8601` | Historical snapshot at or before timestamp |

Missing `If-Match` returns `428`; stale ETags return `412`. Input validation
preserves explicit boolean naming consent, valid regions and outcome objects.
Empty outcomes are valid. Version history remains after deleting a current row.

When `CASEFORGE_TOKEN` is configured, data routes require its Bearer token.
`/health`, `/docs` and the API schema remain available for local diagnostics.
`X-Correlation-ID` follows the shared service middleware. The optional credential
is configured consistently in the APIs and UI servers, never in a browser
bundle.

```powershell
python -m vault.vault list
python -m vault.vault get eng-01
```

These CLI reads use HTTP. The legacy `load-all` file import is not a supported
pipeline. Do not delete a persistent database to resolve a schema error: inspect
and migrate it separately. The [CF-105 runbook](../docs/CF-105-runbook.md) documents
setup, contracts and isolated acceptance. Historical Vault test modules are not
part of default cutover selection; inspect them before explicit execution.
