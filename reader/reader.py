"""
READER — Çağrı

Turns an engagement document into an Engagement Record.

    python -m reader.reader <document.pdf>  > records/eng-01.json
    python -m reader.reader <document.pdf> --text-only   # just the text (L1)

See the Project Specification, sections 3 and 5.
"""
import argparse
import json
import os
import shutil
import sys

from common.contract import load_seed
from common.errors import die, BAD_INPUT
from common.llm import ask_for_json, GROUNDING_RULES

# Below this many characters of extractable text we treat a PDF as a scan and
# fall back to OCR. The text-layer closeouts yield 500+ characters; the two
# SCANNED samples yield 0. 50 sits safely between the two — the same threshold
# the Training Handbook suggests.
MIN_TEXT_CHARS = 50


class ExtractionError(Exception):
    """
    The document could not be turned into text: empty, corrupt, or a blank /
    unreadable scan. main() turns this into a clean exit code 2 — never a
    stack trace. See the Project Specification, section 6.
    """


def _read_text_layer(pdf_path):
    """Pull whatever text lives in the PDF's text layer. Returns a string."""
    import pdfplumber

    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _locate_tesseract():
    """
    Where is the Tesseract binary?  Order: explicit TESSERACT_CMD override,
    then PATH, then the UB-Mannheim installer's default location on Windows
    (its installer does not always add itself to PATH). Returns a path to set
    on pytesseract, or None to let pytesseract use its own default.
    """
    override = os.environ.get("TESSERACT_CMD")
    if override:
        return override
    if shutil.which("tesseract"):
        return None
    windows_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    return windows_default if os.path.exists(windows_default) else None


def _ocr(pdf_path):
    """
    Slow path: rasterise each page and read it with OCR. Returns a string.

    Tesseract and Poppler must be installed. If they are not on PATH, point to
    them with the TESSERACT_CMD and POPPLER_PATH environment variables. Any
    missing dependency raises ExtractionError (a clean message), never a raw
    traceback.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise ExtractionError(f"OCR libraries not available: {e}")

    tesseract_cmd = _locate_tesseract()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    poppler_path = os.environ.get("POPPLER_PATH") or None

    try:
        images = convert_from_path(pdf_path, poppler_path=poppler_path)
    except Exception as e:
        # Poppler missing, or the file cannot be rendered to images.
        raise ExtractionError(f"could not render {pdf_path} for OCR: {e}")

    parts = []
    for image in images:
        try:
            parts.append(pytesseract.image_to_string(image) or "")
        except Exception as e:
            # Tesseract binary missing or failed on this page.
            raise ExtractionError(f"OCR failed on {pdf_path}: {e}")
    return "\n".join(parts)


def extract_text(pdf_path):
    """
    Document → text. Handles three kinds of input and never crashes on the
    bad ones (see the Project Specification, section 6):

      - a normal text-layer PDF  → pdfplumber (the fast path)
      - a scanned PDF (no text)  → OCR fallback (pytesseract + pdf2image)
      - empty / corrupt / blank  → ExtractionError, which main() reports as
                                   exit code 2. We never return empty text
                                   pretending we succeeded.
    """
    if not os.path.exists(pdf_path):
        raise ExtractionError(f"no such file: {pdf_path}")
    if os.path.getsize(pdf_path) == 0:
        raise ExtractionError(f"{pdf_path}: file is empty")

    # 1) fast path — the text layer
    try:
        text = _read_text_layer(pdf_path)
    except Exception as e:
        # pdfplumber could not parse it → corrupt / not really a PDF.
        raise ExtractionError(f"could not read {pdf_path}: {e}")

    if len(text.strip()) >= MIN_TEXT_CHARS:
        return text

    # 2) little or no text → it is a scan (or blank). Try OCR.
    print(f"[reader] {pdf_path}: {len(text.strip())} chars in text layer "
          f"— looks like a scan, trying OCR", file=sys.stderr)
    ocr_text = _ocr(pdf_path)
    if len(ocr_text.strip()) >= MIN_TEXT_CHARS:
        return ocr_text

    # 3) still nothing → genuinely blank or unreadable. Fail; never invent.
    raise ExtractionError(
        f"{pdf_path}: no text found — the document appears blank or is an "
        f"unreadable scan")


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
    # --- STUB: replace me (L2, next sprint) -------------------------------
    print("[reader] STUB: returning seed record instead of extracting",
          file=sys.stderr)
    return load_seed("eng-01")
    # ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Document -> Engagement Record")
    parser.add_argument("document", help="path to a PDF")
    parser.add_argument("--text-only", action="store_true",
                        help="print the extracted text and stop (Reader L1); "
                             "do not build a record")
    args = parser.parse_args()

    try:
        text = extract_text(args.document)
    except ExtractionError as e:
        # Bad input, reported clearly. Not a crash — the program working.
        die(str(e), BAD_INPUT)

    if args.text_only:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            print()
        return

    record = extract_record(text, args.document)

    if record is None:
        die(f"could not extract a record from {args.document}", BAD_INPUT)

    # stdout is the record. Everything else goes to stderr.
    json.dump(record, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
