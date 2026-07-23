"""
PUBLISHER — Ahmet

Case study -> branded BGTS document.

    python -m publisher.publisher <case_study.json> --out out/eng-01.docx
    python -m publisher.publisher <case_study.json> --out out/eng-01.pdf

See the Project Specification, sections 4.1 and 7.
"""
import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from common.contract import load_seed
from common.errors import die

TEMPLATE = "caseforge-testdata/templates/case_study_template.docx"

NAVY = HexColor("#1B2A4A")
ORANGE = HexColor("#C45C26")


def safe_text(value):
    """Return display-ready text, using [MISSING] for blank values."""
    if value is None:
        return "[MISSING]"
    if isinstance(value, str):
        return value if value.strip() else "[MISSING]"
    return str(value)


def anonymise_text(value, real_client, client_type):
    """Replace a real client name in text with the safe client type."""
    if not isinstance(value, str):
        return value
    return value.replace(real_client, client_type)


def prepare_display_values(case_study):
    """
    Build the safe display values used by both DOCX and PDF output.

    Returns a dict with title, client_type, challenge, approach,
    technology and outcomes. The real client name is never included.
    """
    sections = case_study.get("sections")
    if not isinstance(sections, dict):
        sections = {}

    record = load_seed(case_study.get("engagement_id"))
    client_type = record["client_type"]
    real_client = record["client"]

    sections = {
        key: anonymise_text(
            safe_text(sections.get(key)), real_client, client_type
        )
        for key in [
            "context",
            "challenge",
            "approach",
            "technology",
            "outcomes",
        ]
    }

    return {
        "title": anonymise_text(
            safe_text(case_study.get("title")), real_client, client_type
        ),
        "client_type": client_type,
        "challenge": sections["challenge"],
        "approach": sections["approach"],
        "technology": sections["technology"],
        "outcomes": sections["outcomes"],
    }


def render_docx(case_study, template_path, out_path):
    """Fill the template's {{PLACEHOLDERS}} from the case study."""
    display = prepare_display_values(case_study)

    values = {
        "{{TITLE}}":      display["title"],
        "{{CLIENT}}":     display["client_type"],
        "{{DOMAIN}}":     "",
        "{{REGION}}":     "",
        "{{CHALLENGE}}":  display["challenge"],
        "{{APPROACH}}":   display["approach"],
        "{{TECHNOLOGY}}": display["technology"],
        "{{OUTCOMES}}":   display["outcomes"],
    }

    doc = Document(template_path)
    metadata_keys = ("{{CLIENT}}", "{{DOMAIN}}", "{{REGION}}")
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if all(key in run.text for key in metadata_keys):
                metadata_values = [
                    values[key] for key in metadata_keys if values[key]
                ]
                run.text = " · ".join(metadata_values)
                continue

            for key, value in values.items():
                if key in run.text:
                    run.text = run.text.replace(key, value)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


def render_pdf(case_study, out_path):
    """Create a branded BGTS PDF from a case study."""
    display = prepare_display_values(case_study)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=NAVY,
        spaceAfter=12,
    )
    title = ParagraphStyle(
        "CaseTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=NAVY,
        spaceAfter=10,
    )
    client = ParagraphStyle(
        "ClientLine",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=11,
        textColor=ORANGE,
        spaceAfter=18,
    )
    heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=NAVY,
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )
    footer = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=NAVY,
        spaceBefore=24,
    )

    story = [
        Paragraph(escape("BGTS INTERNATIONAL"), brand),
        Paragraph(escape(display["title"]), title),
        Paragraph(escape(display["client_type"]), client),
        Paragraph(escape("The Challenge"), heading),
        Paragraph(escape(display["challenge"]), body),
        Paragraph(escape("Our Approach"), heading),
        Paragraph(escape(display["approach"]), body),
        Paragraph(escape("Technology"), heading),
        Paragraph(escape(display["technology"]), body),
        Paragraph(escape("Outcomes"), heading),
        Paragraph(escape(display["outcomes"]), body),
        Spacer(1, 18),
        Paragraph(escape("Confidential — BGTS International"), footer),
    ]

    document = SimpleDocTemplate(str(out_path), pagesize=A4)
    document.build(story)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Case study -> branded document")
    parser.add_argument("case_study")
    parser.add_argument("--out", default="out/case_study.docx")
    parser.add_argument("--template", default=TEMPLATE)
    args = parser.parse_args()

    try:
        with open(args.case_study, encoding="utf-8") as f:
            case_study = json.load(f)
    except FileNotFoundError:
        die(f"no such file: {args.case_study}")
    except json.JSONDecodeError as e:
        die(f"{args.case_study} is not valid JSON: {e}")

    out_path = Path(args.out)
    suffix = out_path.suffix.lower()
    if suffix == ".docx":
        written = render_docx(case_study, args.template, out_path)
    elif suffix == ".pdf":
        written = render_pdf(case_study, out_path)
    else:
        die(f"unsupported output type '{suffix}' — use .docx or .pdf")

    print(f"[publisher] wrote {written}", file=sys.stderr)


if __name__ == "__main__":
    main()
