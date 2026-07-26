"""Tests for the Reader. The failure cases are the ones that matter."""
import os
import shutil

import pytest

from reader.reader import (extract_record, extract_text, ExtractionError,
                           MIN_TEXT_CHARS, _locate_tesseract)

# Test data lives at the repo root, regardless of where pytest is invoked from.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "caseforge-testdata", "documents")
EDGE = os.path.join(DOCS, "edge_cases")


def _ocr_available():
    """True if the reader can actually reach both OCR tools — using the same
    detection the code uses, not just a bare PATH lookup."""
    tesseract = _locate_tesseract() is not None or shutil.which("tesseract")
    poppler = (shutil.which("pdftoppm") or shutil.which("pdfinfo")
               or os.environ.get("POPPLER_PATH"))
    return bool(tesseract) and bool(poppler)


# --- extract_record (stub, L2) ------------------------------------------------

def test_returns_a_record_with_required_fields():
    """A record must always have the contract's required fields."""
    record = extract_record("some text", "eng-01_closeout.pdf")
    for field in ["id", "client", "client_type", "may_be_named", "outcomes"]:
        assert field in record, f"record is missing '{field}'"


def test_every_outcome_has_a_source_ref():
    """THE CORE RULE: every fact must say where it came from."""
    record = extract_record("some text", "eng-01_closeout.pdf")
    for outcome in record["outcomes"]:
        assert outcome.get("source_ref"), \
            "every outcome MUST have a source_ref — see the spec, section 3.2"


# --- extract_text L1: the happy path -----------------------------------------

def test_extract_text_from_text_layer_pdf():
    """A normal PDF returns real text (Reader L1, the bar)."""
    text = extract_text(os.path.join(DOCS, "eng-01_closeout.pdf"))
    assert len(text.strip()) >= MIN_TEXT_CHARS
    # eng-01 is the real-time payments engagement — its text mentions it.
    assert "payment" in text.lower()


# --- extract_text L1: the failure cases (the important ones) -----------------

def test_empty_pdf_fails_cleanly():
    """0-byte file: a clear error, never a stack trace."""
    with pytest.raises(ExtractionError):
        extract_text(os.path.join(EDGE, "empty.pdf"))


def test_corrupt_pdf_fails_cleanly():
    """Not really a PDF: a clear error, never a stack trace."""
    with pytest.raises(ExtractionError):
        extract_text(os.path.join(EDGE, "corrupt.pdf"))


def test_blank_pdf_fails_cleanly():
    """Valid PDF with no text: we say so, we do not invent text."""
    with pytest.raises(ExtractionError):
        extract_text(os.path.join(EDGE, "blank_pages.pdf"))


def test_missing_file_fails_cleanly():
    """A path that does not exist is bad input, not a crash."""
    with pytest.raises(ExtractionError):
        extract_text(os.path.join(EDGE, "does_not_exist.pdf"))


# --- extract_text L1: OCR (needs Tesseract + Poppler) ------------------------

@pytest.mark.skipif(not _ocr_available(),
                    reason="Tesseract/Poppler not installed")
def test_scanned_pdf_yields_text_via_ocr():
    """A scanned PDF has no text layer; OCR is the only way in."""
    text = extract_text(os.path.join(DOCS, "eng-03_closeout_SCANNED.pdf"))
    assert len(text.strip()) >= MIN_TEXT_CHARS
