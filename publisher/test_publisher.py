"""Tests for the Publisher."""
import json

from docx import Document

from common.contract import load_seed
from publisher.publisher import render_docx


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
    for expected in [
        case_study["title"],
        sections["challenge"],
        sections["approach"],
        sections["technology"],
        sections["outcomes"],
    ]:
        assert expected in content

    metadata_line = next(
        line for line in content.splitlines() if sections["context"] in line
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


# TODO(Ahmet): test that a record with a missing field renders "[MISSING]"
#              rather than crashing
