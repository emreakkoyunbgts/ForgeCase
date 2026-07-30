"""Tests for the Reader. The failure cases are the ones that matter."""
import json
import os
import shutil

import pytest

from reader import layout
from reader.reader import (extract_record, extract_text, ExtractionError,
                           MIN_TEXT_CHARS, _locate_tesseract)

# Test data lives at the repo root, regardless of where pytest is invoked from.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "caseforge-testdata", "documents")
EDGE = os.path.join(DOCS, "edge_cases")

# The supplied pack has no multi-column or tabular document, so the layout
# fixtures carry eng-01's facts laid out three other ways. See
# reader/fixtures/make_fixtures.py.
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# Fields the supplied PDFs cannot yield correctly because of a font-encoding
# defect in the document itself. See the dedicated test at the bottom of this
# file — the Reader reports what the PDF says rather than guessing a repair.
BROKEN_ENCODING = {"eng-11": {"client"}}

ENG01_FIELDS = {
    "id": "eng-01",
    "client": "Gulf Union Bank",
    "client_type": "Tier-1 GCC retail bank",
    "domain": "core banking",
    "region": "GCC",
    "team_size": 14,
    "duration_months": 11,
}


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


# --- layout L4 (CF-49): columns ----------------------------------------------

def test_two_column_page_is_detected_as_two_columns():
    page = layout.analyse(os.path.join(FIXTURES,
                                       "two_column_closeout.pdf"))["pages"][0]
    assert page["columns"] == 2, "a two-column page must be seen as two columns"
    assert page["gutters"], "the gutter between the columns must be found"


def test_two_column_text_is_not_interleaved():
    """
    THE POINT OF CF-49. Read top to bottom, a two-column page mixes the two
    columns together mid-sentence. Read column by column, each sentence stays
    whole.
    """
    path = os.path.join(FIXTURES, "two_column_closeout.pdf")
    text = layout.analyse(path)["text"]

    # The left column's sentence must appear unbroken by the right column's.
    assert "could not support real-time payments" in text.replace("\n", " ")
    # And no single line may contain text from both columns at once.
    for line in text.split("\n"):
        assert not ("legacy core banking platform" in line
                    and "phased migration" in line), \
            f"columns interleaved on one line: {line!r}"


def test_two_column_sections_come_out_in_reading_order():
    """
    The fixture flows down the left column (sections 1, 2) and continues at the
    top of the right (3, 4). A naive read fuses the headings that sit side by
    side into "1. The Challenge 3. Technology"; reading column by column
    recovers all four, in order.
    """
    doc = layout.analyse(os.path.join(FIXTURES, "two_column_closeout.pdf"))
    assert [s["number"] for s in doc["sections"]] == [1, 2, 3, 4]
    assert [s["heading"] for s in doc["sections"]] == [
        "The Challenge", "Our Approach", "Technology", "Outcomes"]


def test_each_two_column_section_holds_its_own_complete_text():
    """
    Ordering the headings correctly is not enough — the text under each one has
    to be that section's text, whole.

    This is the assertion that catches a line being wrongly treated as
    full-width: when that happens the headings can still come out in order
    while a paragraph is torn out of its section and dropped further down the
    page, next to unrelated text.
    """
    doc = layout.analyse(os.path.join(FIXTURES, "two_column_closeout.pdf"))
    sections = {s["number"]: s["text"] for s in doc["sections"]}

    assert sections[1].startswith("The legacy core banking platform")
    assert sections[1].rstrip().endswith("business hours.")

    assert sections[2].startswith("A phased migration"), \
        f"section 2 lost its paragraph: {sections[2]!r}"
    assert sections[2].rstrip().endswith("cutover.")

    assert "Java, Spring Boot, Kafka, PostgreSQL" in sections[3]

    for outcome in ("payment latency reduced 45%",
                    "batch window shortened from 6 hours to 90 minutes",
                    "zero unplanned downtime during cutover"):
        assert outcome in sections[4], f"outcome missing: {outcome}"

    # The header block belongs to no section: its lines must not leak into one.
    for number, text in sections.items():
        assert "Region: GCC" not in text, \
            f"a header field leaked into section {number}"


def test_text_reaching_the_column_edge_is_not_treated_as_full_width():
    """
    Justified body text routinely runs a few points past the column edge and
    into the gutter. If that counts as spanning the page, the whole band's
    reading order collapses. Only a word whose centre is in the gutter really
    spans the columns.
    """
    path = os.path.join(FIXTURES, "two_column_closeout.pdf")
    with __import__("pdfplumber").open(path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        gutters = layout.find_gutters(words, page.width)
        lines = layout.group_lines(words, gutters)

    assert gutters, "the fixture must have a gutter for this test to mean anything"

    def centred_in_a_gutter(word):
        middle = (word["x0"] + word["x1"]) / 2
        return any(start <= middle <= end for start, end in gutters)

    # The fixture has to contain the awkward case, or this proves nothing.
    assert any(w["x0"] < gutters[0][1] and w["x1"] > gutters[0][0]
               and not centred_in_a_gutter(w) for w in words), \
        "the fixture must contain text that reaches into the gutter"

    # The invariant: a line is full-width only when a word genuinely straddles
    # the gutter — never merely because one reached into it.
    for line in lines:
        if line["column"] is None:
            assert any(centred_in_a_gutter(w) for w in line["words"]), \
                (f"line treated as full-width with no word straddling the "
                 f"gutter: {line['text']!r}")

    # And concretely: the left column's paragraph runs to the column edge, yet
    # stays in column 0.
    paragraph = [l for l in lines if l["text"].startswith("A phased migration")]
    assert paragraph, "the left column's paragraph line was not found"
    assert paragraph[0]["column"] == 0, \
        "a line that reaches the column edge was pushed out of its column"


def test_fields_extract_from_a_two_column_page():
    """CF-49's acceptance criterion, for the multi-column case."""
    fields = layout.analyse(os.path.join(FIXTURES,
                                         "two_column_closeout.pdf"))["fields"]
    for key, expected in ENG01_FIELDS.items():
        assert key in fields, f"field '{key}' was not extracted"
        assert fields[key]["value"] == expected, \
            f"{key}: got {fields[key]['value']!r}, expected {expected!r}"


# --- layout L4 (CF-49): tables -----------------------------------------------

def test_fields_extract_from_a_ruled_table():
    """CF-49's acceptance criterion, for a table drawn with lines."""
    doc = layout.analyse(os.path.join(FIXTURES, "ruled_table_closeout.pdf"))
    assert any(t["kind"] == "ruled" for t in doc["tables"])
    for key, expected in ENG01_FIELDS.items():
        assert doc["fields"].get(key, {}).get("value") == expected, \
            f"field '{key}' not read from the ruled table"


def test_fields_extract_from_a_whitespace_aligned_table():
    """
    The harder case: a table held together by alignment with no ruling lines at
    all, which a line-based table finder cannot see.
    """
    doc = layout.analyse(os.path.join(FIXTURES, "unruled_table_closeout.pdf"))
    assert any(t["kind"] == "unruled" for t in doc["tables"])
    for key, expected in ENG01_FIELDS.items():
        assert doc["fields"].get(key, {}).get("value") == expected, \
            f"field '{key}' not read from the unruled table"


def test_prose_is_not_mistaken_for_a_table():
    """
    A false table is worse than a missed one: it invents structure that isn't
    there. The single-column closeouts contain no table at all.
    """
    doc = layout.analyse(os.path.join(DOCS, "eng-01_closeout.pdf"))
    assert doc["tables"] == [], f"found phantom tables: {doc['tables']}"


# --- layout L4 (CF-49): regions and sections ---------------------------------

def test_every_field_carries_the_region_it_came_from():
    """
    Each field records its page and box. CF-50 builds region-level source_ref
    on top of this, so a fact can point at a spot on the page, not just a page.
    """
    fields = layout.analyse(os.path.join(DOCS, "eng-01_closeout.pdf"))["fields"]
    for key, field in fields.items():
        assert field["page"] >= 1, f"{key} has no page"
        x0, top, x1, bottom = field["bbox"]
        assert x1 > x0 and bottom > top, f"{key} has an empty box: {field['bbox']}"


def test_numbered_sections_are_separated():
    doc = layout.analyse(os.path.join(DOCS, "eng-01_closeout.pdf"))
    headings = [s["heading"].lower() for s in doc["sections"]]
    assert "the challenge" in headings
    assert "outcomes" in headings
    challenge = next(s for s in doc["sections"]
                     if s["heading"].lower() == "the challenge")
    assert "real-time payments" in challenge["text"]


def test_extracted_fields_match_the_corpus_answer_key():
    """
    The extraction is checked against the answer key, not against itself:
    every text-layer closeout must agree with records/corpus.json.
    """
    with open(os.path.join(REPO, "caseforge-testdata", "records",
                           "corpus.json"), encoding="utf-8") as f:
        corpus = {r["id"]: r for r in json.load(f)}

    for engagement_id, record in corpus.items():
        path = os.path.join(DOCS, f"{engagement_id}_closeout.pdf")
        if not os.path.exists(path):
            continue
        fields = layout.analyse(path)["fields"]
        assert fields["id"]["value"] == engagement_id
        for key in ("client", "client_type", "domain", "region"):
            if key in BROKEN_ENCODING.get(engagement_id, ()):
                continue               # see the test below — a PDF defect
            assert fields[key]["value"] == record[key], \
                f"{engagement_id}.{key}: {fields[key]['value']!r} != {record[key]!r}"


def test_turkish_dotless_i_cannot_be_read_from_eng11_and_is_not_guessed():
    """
    A defect in the supplied PDF, not in the Reader — and deliberately not
    repaired.

    eng-11's client is "Pera Yatırım". The font embedded in that PDF maps the
    Turkish dotless i (U+0131) to the wrong code point, so every extractor gets
    it wrong: pdfplumber reads "Yatnrnm", Poppler's pdftotext reads "Yat?r?m".
    The glyphs look right on screen; the text behind them is wrong.

    We could add a repair table, and we deliberately do not. Deciding that "n"
    was meant to be "ı" is a guess about a client's name, and the one rule this
    project has is that CaseForge never invents a fact. So the Reader reports
    what the document actually says, the mismatch stays visible, and the fix
    belongs in whoever generates these PDFs.
    """
    fields = layout.analyse(os.path.join(DOCS, "eng-11_closeout.pdf"))["fields"]
    client = fields["client"]["value"]

    assert client != "Pera Yatırım", \
        ("the PDF's encoding defect appears to be fixed — if the test pack was "
         "regenerated, delete BROKEN_ENCODING and this test")
    assert "Pera" in client, "the readable part of the name must still come out"
    # No silent repair: the mangled form is reported as-is.
    assert client == "Pera Yatnrnm"


# --- extract_text L1: OCR (needs Tesseract + Poppler) ------------------------

@pytest.mark.skipif(not _ocr_available(),
                    reason="Tesseract/Poppler not installed")
def test_scanned_pdf_yields_text_via_ocr():
    """A scanned PDF has no text layer; OCR is the only way in."""
    text = extract_text(os.path.join(DOCS, "eng-03_closeout_SCANNED.pdf"))
    assert len(text.strip()) >= MIN_TEXT_CHARS
