# 2 · VAULT — Kaan

**Store the Engagement Records. Serve them over a REST API.**

You have 15 days. This is deliberately bounded so you can **finish it**.
Finishing cleanly and handing over to Ömer IS your success criterion.
Do not start stretch goals.

## Run it
```bash
python -m vault.vault store records/eng-01.json
python -m vault.vault get eng-01
python -m vault.vault serve          # starts the API on :8000
```

## Your levels
- **L1** — E-R model, SQLite schema. Save a record, read it back *identically*.
- **L2** — FastAPI: `POST /engagements`, `GET /engagements/{id}`,
  `GET /engagements`. Two tests: one happy, one 404.
- **L3** — Filter by domain/region. A tiny HTML list page.

## Your test data
| File | Why |
|---|---|
| `records/corpus.json` | all 12 records — load them all |
| `records/seed/eng-01.json` | round-trip test: save, reload, compare |

**Watch out:** `eng-12` has an **empty** `outcomes` list — your schema must
handle that. And `eng-02` is the only record with `may_be_named: true` — do
not lose that flag.
