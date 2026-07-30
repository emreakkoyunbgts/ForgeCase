# 1 · READER — Çağrı

**Document (PDF or scan) → `engagement_record.json`**

You build the front door. Everything downstream depends on your output.

## Run it
```bash
# full record (the LLM step is still a stub)
python -m reader.reader caseforge-testdata/documents/eng-01_closeout.pdf

# just the extracted text, in reading order (L1)
python -m reader.reader caseforge-testdata/documents/eng-01_closeout.pdf --text-only

# the layout analysis: columns, tables, labelled fields, sections, regions (L4)
python -m reader.reader reader/fixtures/two_column_closeout.pdf --layout
```

Exit codes: `0` success · `2` bad input (empty / corrupt / blank — a clear
message on stderr, never a stack trace).

## Setup — the OCR tools (needed for scanned PDFs)

Text-layer PDFs work with the Python packages in `requirements.txt` alone.
Scanned PDFs need two extra **programs** (not pip packages): **Tesseract**
(the OCR engine) and **Poppler** (renders PDF pages to images).

**Windows** (the cohort's setup):
```powershell
winget install UB-Mannheim.TesseractOCR
winget install oschwartz10612.Poppler
```
Then open a **new** terminal so PATH updates take effect.

The Tesseract installer does not always add itself to PATH. The reader falls
back to the default install location (`C:\Program Files\Tesseract-OCR`)
automatically — or set `TESSERACT_CMD` / `POPPLER_PATH` to point at them
explicitly. On Linux: `apt-get install tesseract-ocr poppler-utils`.

## Your levels
- **L1** — Get text out of a normal PDF (`pdfplumber`). Detect a scan (almost no
  text comes out) and OCR it instead (`pytesseract`).
- **L2** — Send the text to the LLM, get back a valid Engagement Record.
  Every outcome carries a `source_ref`. Flag `eng-12` as `outcome_missing`.
  Fail cleanly on the three broken files.
- **L3** — Confidence per field; a review screen.
- **L4** — Layout-aware extraction (CF-49, done) and per-field confidence with
  region-level `source_ref` (CF-50, next).

## Layout-aware extraction (CF-49)

`reader/layout.py` reads a page by its geometry rather than straight down it:

| It handles | How |
|---|---|
| **Columns** | Finds the whitespace gutters, then reads column by column. A top-to-bottom read of a two-column page interleaves the columns mid-sentence and fuses side-by-side headings into `"1. The Challenge 3. Technology"`. |
| **Ruled tables** | `pdfplumber` line-based detection. |
| **Unruled tables** | Aligned cell starts repeating across consecutive lines — the common case in business documents, where a table is laid out with tabs and no ink at all. |
| **Labelled fields** | `Label: value` from lines *and* from two-column tables, mapped to contract names (`Client profile` → `client_type`), with `14 people` → `14`. |
| **Sections** | Numbered headings (`1. The Challenge`) split the body, so the next stage can ask for one section instead of one long string. |
| **Figures** | Reported with their region, not silently dropped. |

Every field, table and section records the **region** (page + bbox) it came
from. That is what CF-50 builds `source_ref` regions and confidence on.

A false table is worse than a missed one — it invents structure — so cell
contents have to be short and the alignment has to repeat before something is
called a table. The single-column closeouts correctly yield no tables at all.

### Test fixtures

The supplied pack is all single-column prose — no table, no multi-column page —
so there was nothing to test this against. `reader/fixtures/` holds three PDFs
carrying eng-01's facts laid out three other ways (two columns, ruled table,
whitespace-aligned table). They are committed, so the tests need nothing extra;
`reader/fixtures/make_fixtures.py` regenerates them (needs `reportlab`).

### Known limitation, not repaired

`eng-11_closeout.pdf` has a broken font encoding: the Turkish dotless ı (U+0131)
is mapped to the wrong code point, so **every** extractor misreads the client
name — `pdfplumber` gives `Pera Yatnrnm`, Poppler's `pdftotext` gives
`Pera Yat?r?m`, where `corpus.json` says `Pera Yatırım`. The glyphs look right
on screen; the text behind them is wrong.

We do not add a repair table. Deciding that `n` was meant to be `ı` is a guess
about a client's name, and CaseForge never invents a fact. The Reader reports
what the document says; the fix belongs wherever these PDFs are generated.

## Your test data
| File | Why |
|---|---|
| `documents/eng-01..12_closeout.pdf` | normal PDFs — the easy path |
| `documents/eng-03_closeout_SCANNED.pdf` | **zero text inside.** OCR is the only way |
| `documents/eng-08_closeout_SCANNED.pdf` | same |
| `documents/edge_cases/empty.pdf` | 0 bytes — must not crash you |
| `documents/edge_cases/corrupt.pdf` | not a real PDF — must not crash you |
| `documents/edge_cases/blank_pages.pdf` | valid PDF, no words |
| `records/corpus.json` | the answer key — your output should look like this |

## Check yourself
```bash
python caseforge-testdata/validate_record.py records/eng-01.json
```

**The trap:** `eng-12` has no measurable outcome. Flag it. Never invent one.
