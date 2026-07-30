"""Tests for the Publisher."""
from copy import deepcopy
import json
import sys

import pytest
from docx import Document
from common.contract import load_seed
from publisher.publisher import anonymise_text, main, render_docx, render_pdf


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


def test_print_json_skips_document_output(tmp_path, monkeypatch, capsys):
    with open("caseforge-testdata/case_studies/eng-01_clean.json", encoding="utf-8") as f:
        case_study = json.load(f)

    docx_out = tmp_path / "should-not-exist.docx"
    pdf_out = tmp_path / "should-not-exist.pdf"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publisher",
            "caseforge-testdata/case_studies/eng-01_clean.json",
            "--print-json",
            "--out",
            str(docx_out),
        ],
    )

    main()

    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed["engagement_id"] == case_study["engagement_id"]
    assert printed["title"] == case_study["title"]
    assert not docx_out.exists()
    assert not pdf_out.exists()


@pytest.mark.parametrize(
    "layout",
    [
        "full-case-study",
        "one-pager",
        "single-slide",
    ],
)
def test_all_pdf_layouts_render_from_same_case_study(tmp_path, layout):
    with open(
        "caseforge-testdata/case_studies/eng-01_clean.json",
        encoding="utf-8",
    ) as f:
        case_study = json.load(f)

    out = tmp_path / f"{layout}.pdf"
    written = render_pdf(case_study, out, layout=layout)

    assert written.exists()
    assert written.suffix == ".pdf"
    assert written.stat().st_size > 0
    assert written.read_bytes()[:4] == b"%PDF"

def test_single_slide_pdf_is_one_page_and_landscape(tmp_path):
    import pdfplumber

    with open(
        "caseforge-testdata/case_studies/eng-01_clean.json",
        encoding="utf-8",
    ) as f:
        case_study = json.load(f)

    out = tmp_path / "single-slide.pdf"
    written = render_pdf(case_study, out, layout="single-slide")

    with pdfplumber.open(written) as pdf:
        assert len(pdf.pages) == 1

        page = pdf.pages[0]
        assert page.width > page.height
    
@pytest.mark.parametrize(
    ("layout", "expect_landscape"),
    [
        ("full-case-study", False),
        ("one-pager", False),
        ("single-slide", True),
    ],
)
def test_cli_selects_each_pdf_layout(
    tmp_path,
    monkeypatch,
    layout,
    expect_landscape,
):
    import pdfplumber

    out = tmp_path / f"{layout}-cli.pdf"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publisher",
            "caseforge-testdata/case_studies/eng-01_clean.json",
            "--layout",
            layout,
            "--out",
            str(out),
        ],
    )

    main()

    assert out.exists()
    assert out.suffix == ".pdf"
    assert out.stat().st_size > 0
    assert out.read_bytes()[:4] == b"%PDF"

    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) >= 1
        page = pdf.pages[0]

        if expect_landscape:
            assert page.width > page.height
        else:
            assert page.height > page.width


def test_single_slide_pdf_uses_slide_headings(tmp_path):
    import pdfplumber

    with open(
        "caseforge-testdata/case_studies/eng-01_clean.json",
        encoding="utf-8",
    ) as f:
        case_study = json.load(f)

    out = tmp_path / "single-slide-headings.pdf"
    written = render_pdf(
        case_study,
        out,
        layout="single-slide",
    )

    with pdfplumber.open(written) as pdf:
        content = "\n".join(
            (page.extract_text() or "")
            for page in pdf.pages
        )

    for heading in [
        "THE CHALLENGE",
        "OUR APPROACH",
        "TECHNOLOGY",
        "OUTCOMES",
    ]:
        assert heading in content


def test_one_pager_compacts_long_case_study_to_one_portrait_page(tmp_path):
    import pdfplumber

    with open(
        "caseforge-testdata/case_studies/eng-01_clean.json",
        encoding="utf-8",
    ) as f:
        original = json.load(f)

    case_study = deepcopy(original)

    for section_name in [
        "challenge",
        "approach",
        "technology",
        "outcomes",
    ]:
        original_text = case_study["sections"][section_name]
        case_study["sections"][section_name] = " ".join(
            [original_text] * 12
        )

    full_out = tmp_path / "long-full-case-study.pdf"
    one_pager_out = tmp_path / "long-one-pager.pdf"

    render_pdf(
        case_study,
        full_out,
        layout="full-case-study",
    )
    render_pdf(
        case_study,
        one_pager_out,
        layout="one-pager",
    )

    with pdfplumber.open(full_out) as full_pdf:
        full_page_count = len(full_pdf.pages)

    with pdfplumber.open(one_pager_out) as one_pager_pdf:
        one_pager_page_count = len(one_pager_pdf.pages)
        one_pager_page = one_pager_pdf.pages[0]

    assert full_page_count > 1
    assert one_pager_page_count == 1
    assert one_pager_page.height > one_pager_page.width


def test_cli_rejects_non_default_layout_for_docx(
    tmp_path,
    monkeypatch,
    capsys,
):
    out = tmp_path / "unsupported-layout.docx"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publisher",
            "caseforge-testdata/case_studies/eng-01_clean.json",
            "--layout",
            "single-slide",
            "--out",
            str(out),
        ],
    )

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()

    assert not out.exists()
    assert "PDF output only" in captured.err
