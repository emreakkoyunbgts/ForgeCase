# Verifier

Verifier independently compares the submitted final draft with its original
Vault source. Every HTTP PASS in English, German or Turkish requires semantic
provider assessment; deterministic checks can BLOCK but cannot bypass that gate.

```powershell
python -m uvicorn verifier.VerifierController:app --host 127.0.0.1 --port 8004
```

`POST /verify` accepts `{record_id, draft, language}`. The language defaults to
`en` and must be `en`, `de` or `tr`. The draft may use single-source MCS sections
or supported flat section strings. Source IDs and language must match across the
request, draft, section/title entries and citations; conflicts return `422`.
Source facts always come from `GET {VAULT_URL}/engagements/{record_id}`.

Successful HTTP responses retain the existing contract:

```json
{"engagement_id":"eng-01","verdict":"PASS","problems":[]}
```

Unsupported, contradictory or uncertain claims return HTTP 200 with verdict
`BLOCK` and problems. Provider/dependency failures return an HTTP error instead
of a verdict. None authorize publication.

Checks cover titles, nested section prose and visible citation claims. Numeric
normalization handles supported EN/DE/TR percentages, decimal separators and
duration units, distinguishing percent from percentage points. A matching
number in a different source metric is insufficient. Naming checks account for
Unicode and punctuation variants; semantic assessment also checks meaning,
negation, direction, dates and translated disclosures.

The model response must assess every visible span and cite real source fields
with literal evidence quotations. Missing/duplicate assessments, invalid source
pointers, invented quotations and missing evidence fail closed. The original
Vault record and submitted final draft are used, not an English reconstruction.

Configure `OPENAI_API_KEY`, `VERIFIER_SEMANTIC_MODEL` (default `gpt-5.5`), and
`VAULT_URL`. Calls have a 60-second limit and SDK retries disabled. Incoming
authorization is forwarded; otherwise the configured service token is used.
`X-Correlation-ID` is preserved or created and returned on handled responses.
The deprecated `POST /verify/{record_id}` adapter also reads its source from
Vault and ignores submitted source facts.

```powershell
python -m pytest -q verifier/test_api.py verifier/test_vault_contract.py tests/test_cf105_semantic.py
```

The HTTP regression tests inject a synthetic semantic provider to stay offline.
They demonstrate contracts and failure behavior, not real-model accuracy. Older
archive-based Verifier experiments are outside the default suite. See the
[runbook](../docs/CF-105-runbook.md) for real-provider and release gates.
