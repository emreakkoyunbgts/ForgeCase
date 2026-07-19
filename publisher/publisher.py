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

from common.errors import die

TEMPLATE = "caseforge-testdata/templates/case_study_template.docx"


def print_case_study(case_study):
    """Print a case study as readable JSON."""
    print(json.dumps(case_study, indent=2, ensure_ascii=False))


def render_docx(case_study, template_path, out_path):
    """
    Fill the template's {{PLACEHOLDERS}} from the case study.

    TODO(Ahmet) L1:
        from docx import Document
        doc = Document(template_path)
        for para in doc.paragraphs:
            for key, value in values.items():
                if key in para.text:
                    para.text = para.text.replace(key, value)
        doc.save(out_path)

    TODO(Ahmet) L2:
        - a missing field writes "[MISSING]" — it does NOT crash
        - NEVER print the real client name unless the record allows it.
          The case study already did the anonymising for you: use
          case_study["title"] and the sections as they are.
    """
    sections = case_study.get("sections", {})

    values = {
        "{{TITLE}}":      case_study.get("title", "[MISSING]"),
        "{{CLIENT}}":     sections.get("context", "[MISSING]"),
        "{{DOMAIN}}":     "",
        "{{REGION}}":     "",
        "{{CHALLENGE}}":  sections.get("challenge", "[MISSING]"),
        "{{APPROACH}}":   sections.get("approach", "[MISSING]"),
        "{{TECHNOLOGY}}": sections.get("technology", "[MISSING]"),
        "{{OUTCOMES}}":   sections.get("outcomes", "[MISSING]"),
    }

    # --- STUB: writes a plain text file so the pipeline runs. -------------
    # Replace this with real python-docx code. That is your L1 ticket.
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    stub = Path(out_path).with_suffix(".txt")
    with open(stub, "w", encoding="utf-8") as f:
        for key, value in values.items():
            if value:
                f.write(f"{key.strip('{}')}\n{value}\n\n")
    print(f"[publisher] STUB: wrote {stub} (should be a branded .docx!)",
          file=sys.stderr)
    return stub
    # ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Case study -> branded document")
    parser.add_argument("case_study")
    parser.add_argument("--out", default="out/case_study.docx")
    parser.add_argument("--template", default=TEMPLATE)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    try:
        with open(args.case_study, encoding="utf-8") as f:
            case_study = json.load(f)
    except FileNotFoundError:
        die(f"no such file: {args.case_study}")
    except json.JSONDecodeError as e:
        die(f"{args.case_study} is not valid JSON: {e}")

    if args.print_json:
        print_case_study(case_study)
        return

    written = render_docx(case_study, args.template, args.out)
    print(f"[publisher] wrote {written}", file=sys.stderr)


if __name__ == "__main__":
    main()
