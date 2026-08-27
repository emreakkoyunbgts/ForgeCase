# CaseForge — Test Data Pack

Everything in here is **synthetic**. No real client, no real data. Use it freely.

## What's in the box

```
records/
  corpus.json              12 engagement records — the full corpus
  seed/eng-01..03.json     THE 3 SEED RECORDS. Everyone starts here on Day 1.
documents/
  eng-01..12_closeout.pdf  Engagement documents (text-layer PDFs)
  eng-03_..._SCANNED.pdf   Scanned — NO text layer. Forces the OCR path.
  eng-08_..._SCANNED.pdf   Scanned — same.
  edge_cases/
    empty.pdf              0 bytes. Must not crash you.
    corrupt.pdf            Not really a PDF. Must not crash you.
    blank_pages.pdf        Valid PDF, no text at all.
    eng-06_PROMPT_INJECTION.pdf   Contains "IGNORE ALL PREVIOUS INSTRUCTIONS..."
case_studies/
  eng-01_clean.json        A good, fully-grounded case study.
  eng-01_POISONED.json     Contains INVENTED facts. Your job is to catch them.
rfp/
  rfp_01_realtime_payments.txt
  rfp_02_regulatory_dora.txt
templates/
  case_study_template.docx  Word template with {{PLACEHOLDERS}}
expected/
  *.json                   The answer keys. Check yourself against these.
```

## The golden rule
`eng-12` has **no measurable outcome**. Your tools must FLAG that, never invent one.
`eng-01_POISONED.json` contains numbers that are **not in the source**. They must be caught.

## Quick start
```bash
python -c "import json; r=json.load(open('records/seed/eng-01.json')); print(r['outcomes'])"
```
