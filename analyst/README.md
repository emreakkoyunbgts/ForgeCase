# Analyst

Analyst summarizes engagement coverage and gaps using Vault HTTP records.
The supported dashboard also loads Vault; users do not supply a corpus filename.

```powershell
python -m uvicorn analyst.api:app --host 127.0.0.1 --port 8007
```

`GET /coverage` returns the profile of stored engagements. `GET /gaps` returns
`{total_gaps, gaps}`. Vault pagination is followed until all source records are
read. Missing outcomes remain missing evidence instead of invented proof points.

```powershell
python -m analyst.analyst --coverage
python -m analyst.analyst --recommend
python -m streamlit run analyst/app.py --server.port 8502
```

Set `VAULT_URL` and `ANALYST_URL` in the root `.env`; service calls preserve
correlation and applicable authorization. Empty or unavailable Vault data is
reported by the interface. There is no supported runtime corpus-file fallback.

Default `analyst/test_api.py` fixtures use Vault's actual
`items/total/limit/offset` response contract. Offline research/report scripts and
external archive experiments are not live mesh evidence. See the
[CF-105 runbook](../docs/CF-105-runbook.md) for full setup and acceptance.
