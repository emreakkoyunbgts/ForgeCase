# 3 · GENERATOR — Taha

**Engagement Record → a grounded case study.**

The heart of CaseForge, and the piece with real value to BGTS.
Every claim you write MUST trace back to the source. You never invent a fact.

## Run it
```bash
python -m generator.generator records/eng-01.json > drafts/eng-01.json
```

## Your levels
- **L1** — Take a seed record, produce a case study with the five sections.
- **L2** — Enforce grounding. Missing facts become `[MISSING: x]`. Anonymise
  the client by default. Generate from `eng-12` (no outcomes) and prove you
  do **not** invent one.
- **L3** — Citations per claim. Confidence flags. Survive the injection doc.

## Your test data
| File | Why |
|---|---|
| `records/seed/eng-01..03.json` | start here on day one — no waiting |
| `records/corpus.json` (`eng-12`) | **no outcomes.** Must produce `[MISSING]` |
| `documents/edge_cases/eng-06_PROMPT_INJECTION.pdf` | tells the AI to lie. Ignore it. |
| `case_studies/eng-01_clean.json` | roughly what good looks like |

## The bar
Run **Ömer's Verifier** over your output. It must find **nothing**.
```bash
python -m generator.generator records/eng-01.json > drafts/eng-01.json
python -m verifier.verifier drafts/eng-01.json records/eng-01.json
```
If Ömer's Verifier flags your output, one of you has a bug. Go and find out which.

For first push and pull request!
