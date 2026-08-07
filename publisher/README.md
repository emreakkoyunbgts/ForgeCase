# 4 · PUBLISHER — Ahmet

**Case study → a branded BGTS document (DOCX and PDF).**

You build the thing everyone actually sees. No AI, no guessing — this is
deterministic, and you can *see* the result immediately.

## Windows local setup
Run all commands below from the `ForgeCase` project root.

Check that Python 3.11 is installed:

```powershell
py -3.11 --version
```

Create a virtual environment with Python 3.11:

```powershell
py -3.11 -m venv .venv
```

Activate the virtual environment in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the project dependencies from `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
```

Verify the active Python version and executable path:

```powershell
python --version
python -c "import sys; print(sys.executable)"
```

The test data pack must be available as `caseforge-testdata` in the project
root. The Publisher expects paths such as
`caseforge-testdata/case_studies/eng-01_clean.json` and
`caseforge-testdata/templates/case_study_template.docx`.

Run the Publisher tests from the project root:

```powershell
python -m pytest publisher -q
```

Or, equivalently:

```powershell
.\.venv\Scripts\python.exe -m pytest publisher/test_publisher.py -q
```

Publisher tests cover source collection, deterministic SHA-256 hashing,
freshness boundaries, missing/invalid dates, PDF layouts, DOCX output,
automatic sidecars, CLI `--as-of-date` forwarding, asset-level STALE
acceptance, and client-name leak protection.

Run the Publisher from the project root:

```powershell
python -m publisher.publisher caseforge-testdata/case_studies/eng-01_clean.json --out out/eng-01.docx
```

## Run it
```bash
python -m publisher.publisher drafts/eng-01.json --out out/eng-01.docx
```

## Runtime PDF layouts

Supported `--layout` values:

- `full-case-study`
- `one-pager`
- `single-slide`

Layout differences:

- `full-case-study`: detailed portrait document; may span multiple pages
- `one-pager`: compact single-page portrait document
- `single-slide`: single-page landscape slide-like document

Runtime layout selection is currently supported for PDF output.
DOCX output continues to use the existing full-case-study template.
Non-default layouts with DOCX are rejected instead of silently ignored.

Same case-study input, three PDF layouts (Windows PowerShell):

```powershell
.venv\Scripts\python.exe -m publisher.publisher caseforge-testdata\case_studies\eng-01_clean.json --layout full-case-study --out out\full-case-study.pdf

.venv\Scripts\python.exe -m publisher.publisher caseforge-testdata\case_studies\eng-01_clean.json --layout one-pager --out out\one-pager.pdf

.venv\Scripts\python.exe -m publisher.publisher caseforge-testdata\case_studies\eng-01_clean.json --layout single-slide --out out\single-slide.pdf
```

## CF-53 — Provenance and Freshness

Every published PDF and DOCX includes a visible provenance block.
Beside each asset, the Publisher also writes a machine-readable JSON
sidecar that downstream systems can consume. Content older than six
calendar months is flagged `STALE`. The feature is deterministic and
does not use AI.

### Visible provenance fields

Published documents show:

- **Source records** — engagement identifiers that sourced the case study
- **Source references** — unique citation `source_ref` values
- **Content hash** — SHA-256 of the safe published content
- **Freshness** — `FRESH`, `STALE`, or `UNKNOWN`
- **Reason** — why that freshness status was chosen
- **Completed at** — `completed_at` from the case study, or `UNKNOWN`
  when missing
- **As of date** — the freshness evaluation date

### Freshness rules

Freshness compares `completed_at` to `as_of_date` using **calendar
months**, not a fixed 180-day window:

| Condition | Status | Reason |
|---|---|---|
| `completed_at` older than six calendar months before `as_of_date` | `STALE` | `OLDER_THAN_SIX_MONTHS` |
| Exactly six calendar months before `as_of_date` | `FRESH` | `WITHIN_SIX_MONTHS` |
| Newer than six calendar months before `as_of_date` | `FRESH` | `WITHIN_SIX_MONTHS` |
| `completed_at` missing | `UNKNOWN` | `DATE_MISSING` |
| `completed_at` present but not a valid `YYYY-MM-DD` | `UNKNOWN` | `DATE_INVALID` |

### Current data note

Existing CaseForge test records may not include `completed_at`.
The Publisher does not invent dates. In that case output is
`UNKNOWN` / `DATE_MISSING`. When upstream modules later supply
`completed_at`, the Publisher evaluates the same field automatically.

### Content hash

- Algorithm: SHA-256
- Format: 64-character lowercase hexadecimal
- Not computed from PDF or DOCX file bytes
- Computed from the safe, normalized published content used for output
- PDF and DOCX sidecars from the same content therefore share the same
  `content_hash`
- The real client name is not part of the hash payload when it is not
  included in safe published content

### Sidecar naming

The sidecar keeps the full asset filename, including its extension:

```text
case-study.pdf
case-study.pdf.provenance.json

case-study.docx
case-study.docx.provenance.json
```

Keeping the asset extension in the sidecar name prevents PDF and DOCX
sidecars for the same stem from colliding.

### Sidecar JSON schema

Example when `completed_at` is missing:

```json
{
  "as_of_date": "2026-08-06",
  "completed_at": null,
  "content_hash": "<64-character-sha256>",
  "freshness_reason": "DATE_MISSING",
  "freshness_status": "UNKNOWN",
  "source_records": [
    "eng-01"
  ],
  "source_references": [
    "closeout.pdf#page=5"
  ]
}
```

### CLI usage with `--as-of-date`

`--as-of-date` is optional and expects `YYYY-MM-DD`. When omitted, the
renderer uses the publication date. Passing an explicit date keeps test
and demo outputs reproducible. The option applies to document render
flows; `--print-json` still prints the case-study JSON only and does
not add provenance fields.

PDF (Windows PowerShell):

```powershell
python -m publisher.publisher caseforge-testdata/case_studies/eng-01_clean.json `
  --out out/eng-01.pdf `
  --layout full-case-study `
  --as-of-date 2026-08-06
```

DOCX (Windows PowerShell):

```powershell
python -m publisher.publisher caseforge-testdata/case_studies/eng-01_clean.json `
  --out out/eng-01.docx `
  --template caseforge-testdata/templates/case_study_template.docx `
  --as-of-date 2026-08-06
```

### Output example

Publishing `out/case-study.pdf` produces both:

```text
out/case-study.pdf
out/case-study.pdf.provenance.json
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
A matching `*.provenance.json` sidecar is written beside the published asset.
