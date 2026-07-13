"""
READER — Çağrı

Turns an engagement document into an Engagement Record.

    python -m reader.reader <document.pdf>  > records/eng-01.json

See the Project Specification, sections 3 and 5.
"""
import argparse
import json
import sys

from common.contract import load_seed
from common.errors import die, BAD_INPUT
from common.llm import ask_for_json, GROUNDING_RULES


def extract_text(pdf_path):
    """
    STEP 1 — get the text out of the PDF.

    TODO(Çağrı) L1:
      - use pdfplumber to pull text from a normal PDF
      - if you get back almost nothing (< 50 chars), it is a SCAN:
        fall back to OCR with pytesseract + pdf2image
      - raise / die cleanly on empty.pdf, corrupt.pdf, blank_pages.pdf

    Right now this is a stub so the pipeline runs end to end from day one.
    """
    # --- STUB: replace me -------------------------------------------------
    print(f"[reader] STUB: pretending to read {pdf_path}", file=sys.stderr)
    return None
    # ----------------------------------------------------------------------


def extract_record(text, source_name):
    """
    STEP 2 — turn the text into a structured Engagement Record.

    TODO(Çağrı) L2:
      - prompt the LLM for strict JSON matching the contract
      - EVERY outcome must carry a source_ref (which page it came from)
      - if the document states no measurable outcome, set:
            "outcomes": [], "outcome_missing": True
        ...and do NOT invent one. This is the core rule of the project.

    Useful:
        record = ask_for_json(system=GROUNDING_RULES + "...", user=text)
    """
    # --- STUB: replace me -------------------------------------------------
    print("[reader] STUB: returning seed record instead of extracting",
          file=sys.stderr)
    return load_seed("eng-01")
    # ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Document -> Engagement Record")
    parser.add_argument("document", help="path to a PDF")
    args = parser.parse_args()

    text = extract_text(args.document)
    record = extract_record(text, args.document)

    if record is None:
        die(f"could not extract a record from {args.document}", BAD_INPUT)

    # stdout is the record. Everything else goes to stderr.
    json.dump(record, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
