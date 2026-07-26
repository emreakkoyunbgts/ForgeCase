"""Tests for the Publisher."""
from copy import deepcopy
import json

from docx import Document

from common.contract import load_seed
from publisher.publisher import anonymise_text, render_docx, render_pdf


def read_docx_text(path):
    """Return all normal paragraph text from a DOCX file."""
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_renders_without_crashing(tmp_path):
    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        case_study = json.load(f)

    out = tmp_path / "eng-01.docx"
    written = render_docx(
        case_study,
        "caseforge-testdata/templates/case_study_template.docx",
        out,
    )

    assert written.exists()
    assert written.suffix == ".docx"

    content = read_docx_text(written)
    sections = case_study["sections"]
    record = load_seed(case_study["engagement_id"])
    for expected in [
        case_study["title"],
        sections["challenge"],
        sections["approach"],
        sections["technology"],
        sections["outcomes"],
    ]:
        assert expected in content

    metadata_line = next(
        line for line in content.splitlines() if record["client_type"] in line
    )
    assert not metadata_line.rstrip().endswith("·")
    assert "· ·" not in metadata_line

    for placeholder in [
        "{{TITLE}}",
        "{{CHALLENGE}}",
        "{{APPROACH}}",
        "{{TECHNOLOGY}}",
        "{{OUTCOMES}}",
    ]:
        assert placeholder not in content


def test_real_client_name_never_leaks(tmp_path):
    """eng-01 may NOT be named. Check the real name is nowhere in the output."""
    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        case_study = json.load(f)

    record = load_seed("eng-01")
    out = tmp_path / "eng-01.docx"
    written = render_docx(case_study, "caseforge-testdata/templates/case_study_template.docx", out)

    content = read_docx_text(written)
    assert record["client"] not in content, \
        "the real client name leaked into a published document — spec section 7"


def test_poisoned_client_name_is_anonymised(tmp_path):
    with open("caseforge-testdata/case_studies/eng-01_POISONED.json") as f:
        case_study = json.load(f)

    record = load_seed("eng-01")
    assert record["client"] in case_study["sections"]["context"]
    safe_context = anonymise_text(
        case_study["sections"]["context"],
        record["client"],
        record["client_type"],
    )
    assert record["client"] not in safe_context
    assert record["client_type"] in safe_context

    out = tmp_path / "eng-01-poisoned.docx"
    written = render_docx(
        case_study,
        "caseforge-testdata/templates/case_study_template.docx",
        out,
    )

    content = read_docx_text(written)
    assert record["client"] not in content
    assert record["client_type"] in content


def test_missing_fields_render_as_missing(tmp_path):
    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        original = json.load(f)

    case_study = deepcopy(original)
    case_study["title"] = None
    case_study["sections"]["challenge"] = None
    case_study["sections"]["approach"] = ""
    case_study["sections"]["technology"] = "   "
    del case_study["sections"]["outcomes"]

    out = tmp_path / "eng-01-missing.docx"
    written = render_docx(
        case_study,
        "caseforge-testdata/templates/case_study_template.docx",
        out,
    )

    assert written.exists()
    assert written.suffix == ".docx"

    content = read_docx_text(written)
    assert "[MISSING]" in content
    assert content.count("[MISSING]") >= 5
    assert "None" not in content

    for placeholder in [
        "{{TITLE}}",
        "{{CHALLENGE}}",
        "{{APPROACH}}",
        "{{TECHNOLOGY}}",
        "{{OUTCOMES}}",
    ]:
        assert placeholder not in content


def test_export_to_pdf(tmp_path):
    import pdfplumber

    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        case_study = json.load(f)

    record = load_seed("eng-01")
    out = tmp_path / "eng-01.pdf"
    written = render_pdf(case_study, out)

    assert written.exists()
    assert written.suffix == ".pdf"
    assert written.stat().st_size > 0
    assert written.read_bytes()[:4] == b"%PDF"

    with pdfplumber.open(written) as pdf:
        content = "\n".join((page.extract_text() or "") for page in pdf.pages)

    assert case_study["title"] in content
    assert record["client_type"] in content
    assert record["client"] not in content
    for heading in ["The Challenge", "Our Approach", "Technology", "Outcomes"]:
        assert heading in content
