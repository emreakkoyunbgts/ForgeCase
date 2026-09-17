# Generator

Generator obtains one authoritative Engagement Record from Vault and returns an
in-memory MCS draft in English, German or Turkish. It does not write PDF outputs
or read a source corpus during generation.

```powershell
python -m uvicorn generator.GeneratorController:app --host 127.0.0.1 --port 8001
```

Canonical `POST /generate` request:

```json
{"record_id":"eng-01","language":"tr"}
```

`language` is `en`, `de` or `tr` (default `en`). Responses preserve
`engagement_ids`, `titles`, five `sections`, `citations`, `client_named` and
`language`. Translation applies only to visible prose; source IDs, references,
missing-data markers, quantities, technologies and naming permission remain
constrained by the original record. Invalid or incomplete model output is an
HTTP error, not a successful draft.

Configure `VAULT_URL`, `OPENAI_API_KEY`, and `GENERATOR_TRANSLATION_MODEL`
(default `gpt-5.5`). Source lookup is independent of Librarian for a known ID.
The query adapter uses Librarian to choose a single source and returns an error
when selection is unavailable or empty. Older `/generator/mcs` adapters also
fetch facts from Vault rather than trusting a submitted record body.

Generation is not approval: submit the final edited draft to Verifier, obtain
human approval, then publish through Publisher's independent final gate.
Model calls have a 60-second limit and no SDK retries. Correlation, error mapping,
UI/CLI setup and acceptance boundaries are in the
[CF-105 runbook](../docs/CF-105-runbook.md).

Historical generator experiments may read the separate test-data archive, write
outputs or call models. They are not selected by default pytest and do not
constitute HTTP cutover acceptance.
