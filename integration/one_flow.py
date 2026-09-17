"""The supported end-to-end pipeline: HTTP only, with explicit human approval."""
import argparse
import json
from pathlib import Path

from console.workflow import Workflow
from common.services import ServiceError


def run_pipeline(record_id=None, document=None, language="en", publish=False, format="docx", layout="full-case-study"):
    workflow = Workflow(language=language)
    if document:
        path = Path(document)
        workflow.extract(path.name, path.read_bytes())
    elif record_id:
        workflow.select(record_id, language)
    else:
        raise ValueError("Provide a document or a Vault record ID")
    workflow.generate()
    workflow.verify()
    if workflow.verified and publish:
        workflow.approve(True)
        workflow.publish(format, layout)
    return workflow


def main():
    parser = argparse.ArgumentParser(description="Run the CaseForge HTTP pipeline")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--record-id")
    source.add_argument("--document")
    parser.add_argument("--language", choices=["en", "de", "tr"], default="en")
    parser.add_argument("--format", choices=["docx", "pdf"], default="docx")
    parser.add_argument("--layout", choices=["full-case-study", "one-pager", "single-slide"], default="full-case-study")
    parser.add_argument("--approve", action="store_true", help="Explicitly approve publication after PASS")
    parser.add_argument("--out", help="Save the HTTP download to this user-selected output path")
    args = parser.parse_args()
    if args.out and not args.approve:
        parser.error("--out requires --approve")
    try:
        workflow = run_pipeline(args.record_id, args.document, args.language, args.approve, args.format, args.layout)
        output = {"correlation_id": workflow.trace, "draft": workflow.draft,
                  "report": workflow.report, "artifact": workflow.artifact}
        if workflow.artifact and args.out:
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(workflow.download())
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if not workflow.verified:
            raise SystemExit(1)
    except (ServiceError, ValueError, OSError) as exc:
        parser.exit(2, f"Pipeline failed: {exc}\n")


if __name__ == "__main__":
    main()

