# 1 · READER — Çağrı

**Document (PDF or scan) → `engagement_record.json`**

You build the front door. Everything downstream depends on your output.

## Run it
```bash
# full record (L2 is still a stub for now)
python -m reader.reader caseforge-testdata/documents/eng-01_closeout.pdf

# just the extracted text (L1)
python -m reader.reader caseforge-testdata/documents/eng-01_closeout.pdf --text-only
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
