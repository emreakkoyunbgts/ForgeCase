"""
PUBLISHER — Ahmet

Case study -> branded BGTS document.

    python -m publisher.publisher <case_study.json> --out out/eng-01.docx

See the Project Specification, sections 4.1 and 7.
"""
import argparse
import json
import sys
from pathlib import Path

from docx import Document

from common.contract import load_seed
from common.errors import die

TEMPLATE = "caseforge-testdata/templates/case_study_template.docx"


def anonymise_text(value, real_client, client_type):
    """Replace a real client name in text with the safe client type."""
    if not isinstance(value, str):
        return value
    return value.replace(real_client, client_type)


def render_docx(case_study, template_path, out_path):
    """
    Fill the template's {{PLACEHOLDERS}} from the case study.

    TODO(Ahmet) L2:
        - a missing field writes "[MISSING]" — it does NOT crash
    """
    sections = case_study.get("sections", {})
    record = load_seed(case_study.get("engagement_id"))
    client_type = record["client_type"]
    real_client = record["client"]
    sections = {
        key: anonymise_text(value, real_client, client_type)
        for key, value in sections.items()
    }

    values = {
        "{{TITLE}}":      anonymise_text(
            case_study.get("title", "[MISSING]"), real_client, client_type
        ),
        "{{CLIENT}}":     client_type,
        "{{DOMAIN}}":     "",
        "{{REGION}}":     "",
        "{{CHALLENGE}}":  sections.get("challenge", "[MISSING]"),
        "{{APPROACH}}":   sections.get("approach", "[MISSING]"),
        "{{TECHNOLOGY}}": sections.get("technology", "[MISSING]"),
        "{{OUTCOMES}}":   sections.get("outcomes", "[MISSING]"),
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

    written = render_docx(case_study, args.template, args.out)
    print(f"[publisher] wrote {written}", file=sys.stderr)


if __name__ == "__main__":
    main()
