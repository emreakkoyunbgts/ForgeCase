# 8 · VERIFIER — Ömer

**The gate. Catches invented facts before they reach a client.**

Taha's Generator has grounding rules *in its prompt*. But prompts can be
ignored, and models drift. **You are the independent check that actually
enforces the rule.** Nothing gets published that you reject.

This is a parsing and matching problem — which is exactly what your compiler
coursework (Lex, Yacc, grammars) trained you for.

## Run it
```bash
python -m verifier.verifier drafts/eng-01.json records/eng-01.json
echo $?     # 0 = PASS, 1 = BLOCK
```

## Your levels
- **L1** — Extract every number / % / date from the case study. Check each one
  against the source record. Report anything in the output but not the source.
- **L2** — Also catch the client's real name appearing when `may_be_named` is
  false. Clear report. Exit **1** on failure so you can gate a build.
- **L3** — Claim-level parsing (split prose into assertions and verify each).
  Fuzzy matching so `45 percent` == `45%`.

## Your test data — this is the good bit
| File | Expected result |
|---|---|
| `case_studies/eng-01_clean.json` | **PASS** — find nothing wrong |
| `case_studies/eng-01_POISONED.json` | **BLOCK** — 5 invented facts. Catch all 5. |
| `records/seed/eng-01.json` | the source of truth |
| `expected/poisoned_expected_flags.json` | the answer key |

The poisoned file contains: a fake **42%**, a fake **300%**, a wrong **3 months**
(it was 11), a wrong **2019**, and the client **named without consent**.

You must catch all five — and you must **NOT** flag the three real figures
(**45%**, **6 hours**, **90 minutes**). A false alarm is as bad as a miss.
