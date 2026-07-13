# 4 · PUBLISHER — Ahmet

**Case study → a branded BGTS document (DOCX and PDF).**

You build the thing everyone actually sees. No AI, no guessing — this is
deterministic, and you can *see* the result immediately.

## Run it
```bash
python -m publisher.publisher drafts/eng-01.json --out out/eng-01.docx
```

## Your levels
- **L1** — Load a case study, fill the `{{PLACEHOLDERS}}` in the Word template,
  save the `.docx`.
- **L2** — Export a PDF too. Use `client_label()` — **never** the real client
  name unless `may_be_named` is true. A missing field writes `[MISSING]` and
  does not crash.
- **L3** — A PowerPoint version. A Streamlit download page.

## Your test data
| File | Why |
|---|---|
| `templates/case_study_template.docx` | your template — `{{TITLE}}`, `{{CLIENT}}`, `{{CHALLENGE}}`, `{{APPROACH}}`, `{{TECHNOLOGY}}`, `{{OUTCOMES}}` |
| `case_studies/eng-01_clean.json` | main input |
| `records/seed/eng-01.json` | `may_be_named: false` → print "Tier-1 GCC retail bank" |
| `records/seed/eng-02.json` | `may_be_named: true` → "Nordbank Deutschland" is allowed |

## Check yourself
Someone who has never seen your code runs **one command** and gets a branded PDF.
Client name hidden for `eng-01`, shown for `eng-02`.
