"""
CF-42 — Generator faithfulness evaluation.

This module prepares a manually labelled evaluation set and calculates:

    faithfulness = supported generated claims / all generated claims

Usage:

    python -m evaluation.faithfulness prepare

    python -m evaluation.faithfulness score \
        evaluation/faithfulness_cases.json \
        --output evaluation/faithfulness_report.json
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from common.contract import load_corpus
from generator.generator import generate


DEFAULT_ENGAGEMENT_IDS = (
    "eng-01",
    "eng-02",
    "eng-03",
    "eng-04",
    "eng-05",
    "eng-06",
    "eng-07",
    "eng-08",
    "eng-09",
    "eng-12",
)

REQUIRED_SECTIONS = (
    "context",
    "challenge",
    "approach",
    "technology",
    "outcomes",
)

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class EvaluationError(ValueError):
    """Raised when the evaluation data is missing or malformed."""


def clean_claim_text(text: str) -> str:
    """Normalize surrounding whitespace without changing claim wording."""
    return " ".join(text.strip().split())


def split_sentences(text: str) -> list[str]:
    """Split ordinary prose into non-empty sentence-level claims."""
    cleaned = clean_claim_text(text)

    if not cleaned:
        return []

    return [
        clean_claim_text(part)
        for part in SENTENCE_BOUNDARY.split(cleaned)
        if clean_claim_text(part)
    ]


def split_section_claims(section: str, text: str) -> list[str]:
    """
    Split one case-study section into reasonably atomic claims.

    Technology entries and outcomes are separated because one unsupported
    item should not make an entire list impossible to label accurately.
    """
    if not isinstance(text, str):
        raise EvaluationError(
            f"section {section!r} must contain text"
        )

    cleaned = clean_claim_text(text)

    if not cleaned:
        return []

    if section == "technology":
        return [
            clean_claim_text(part)
            for part in cleaned.split(",")
            if clean_claim_text(part)
        ]

    if section == "outcomes":
        return [
            clean_claim_text(part)
            for part in re.split(r"\s*;\s*", cleaned)
            if clean_claim_text(part)
        ]

    return split_sentences(cleaned)


def suggested_evidence_fields(section: str) -> list[str]:
    """
    Suggest source fields for the human reviewer.

    These suggestions are not labels and do not count as evidence until
    the reviewer checks the source record.
    """
    mapping = {
        "title": [
            "domain",
            "client_type or client when may_be_named is true",
        ],
        "context": [
            "client_type or client when may_be_named is true",
            "region",
        ],
        "challenge": ["challenge"],
        "approach": ["solution"],
        "technology": ["technologies"],
        "outcomes": [
            "outcomes[].metric",
            "outcomes[].source_ref",
            "outcome_missing",
        ],
    }

    return mapping.get(section, [])


def extract_claims(case_study: dict) -> list[dict]:
    """
    Extract reviewable claims from a generated case study.

    The title and all five required sections are included because they are
    all statements produced by the Generator.
    """
    engagement_id = case_study.get("engagement_id")

    if not isinstance(engagement_id, str) or not engagement_id:
        raise EvaluationError(
            "generated case study has no engagement_id"
        )

    title = case_study.get("title")

    if not isinstance(title, str) or not title.strip():
        raise EvaluationError(
            f"{engagement_id} has no generated title"
        )

    sections = case_study.get("sections")

    if not isinstance(sections, dict):
        raise EvaluationError(
            f"{engagement_id} has no sections object"
        )

    missing_sections = [
        section
        for section in REQUIRED_SECTIONS
        if section not in sections
    ]

    if missing_sections:
        raise EvaluationError(
            f"{engagement_id} is missing section(s): "
            f"{', '.join(missing_sections)}"
        )

    claims = []

    def add_claim(section: str, text: str, position: int) -> None:
        claims.append({
            "claim_id": (
                f"{engagement_id}-{section}-{position:02d}"
            ),
            "section": section,
            "text": text,
            "supported": None,
            "evidence": [],
            "notes": "",
            "suggested_evidence_fields": (
                suggested_evidence_fields(section)
            ),
        })

    add_claim(
        section="title",
        text=clean_claim_text(title),
        position=1,
    )

    for section in REQUIRED_SECTIONS:
        section_claims = split_section_claims(
            section,
            sections[section],
        )

        if not section_claims:
            raise EvaluationError(
                f"{engagement_id} section {section!r} "
                "contains no reviewable claim"
            )

        for position, text in enumerate(
            section_claims,
            start=1,
        ):
            add_claim(
                section=section,
                text=text,
                position=position,
            )

    return claims


def generate_without_pdf(record: dict) -> dict:
    """
    Run the real Generator without creating ten evaluation PDFs.

    CF-42 evaluates the generated JSON. It does not need the PDF side effect.
    """
    hidden_stderr = io.StringIO()

    with patch(
        "generator.generator.save_case_study_to_pdf",
        return_value="evaluation-pdf-disabled.pdf",
    ):
        with redirect_stderr(hidden_stderr):
            return generate(record)


def prepare_evaluation_set(
    corpus: list[dict],
    engagement_ids: list[str] | tuple[str, ...],
) -> dict:
    """Generate and prepare the ten cases for manual review."""
    if not corpus:
        raise EvaluationError("engagement corpus is empty")

    if not engagement_ids:
        raise EvaluationError(
            "at least one engagement id is required"
        )

    if len(engagement_ids) != len(set(engagement_ids)):
        raise EvaluationError(
            "engagement ids must not contain duplicates"
        )

    records_by_id = {
        record.get("id"): record
        for record in corpus
        if isinstance(record, dict)
    }

    missing_ids = [
        engagement_id
        for engagement_id in engagement_ids
        if engagement_id not in records_by_id
    ]

    if missing_ids:
        raise EvaluationError(
            "corpus does not contain: "
            + ", ".join(missing_ids)
        )

    cases = []

    for engagement_id in engagement_ids:
        record = records_by_id[engagement_id]
        case_study = generate_without_pdf(record)
        claims = extract_claims(case_study)

        cases.append({
            "case_id": engagement_id,
            "engagement_id": engagement_id,
            "source_record": record,
            "generated_case_study": case_study,
            "claims": claims,
        })

    return {
        "schema_version": 1,
        "metric": "faithfulness",
        "metric_definition": (
            "supported generated claims / "
            "all generated claims"
        ),
        "review_instructions": [
            (
                "Compare every claim with the included "
                "source_record."
            ),
            (
                "Set supported to true only when the source "
                "record supports the complete claim."
            ),
            (
                "For a supported claim, add one or more source "
                "field paths to evidence."
            ),
            (
                "For an unsupported claim, explain the problem "
                "in notes."
            ),
            (
                "Do not use the suggested evidence fields "
                "without manually checking the source."
            ),
        ],
        "case_count": len(cases),
        "cases": cases,
    }


def safe_rate(supported: int, total: int) -> float:
    """Calculate a rounded ratio without dividing by zero."""
    if total == 0:
        return 0.0

    return round(supported / total, 4)


def calculate_faithfulness(evaluation_set: dict) -> dict:
    """
    Validate completed manual labels and calculate the score.
    """
    cases = evaluation_set.get("cases")

    if not isinstance(cases, list) or not cases:
        raise EvaluationError(
            "evaluation set contains no cases"
        )

    total_claims = 0
    supported_claims = 0
    unsupported_claims = []
    seen_claim_ids = set()

    engagement_counts = defaultdict(
        lambda: {
            "supported": 0,
            "total": 0,
        }
    )

    section_counts = defaultdict(
        lambda: {
            "supported": 0,
            "total": 0,
        }
    )

    for case in cases:
        engagement_id = case.get("engagement_id")
        claims = case.get("claims")

        if not isinstance(engagement_id, str):
            raise EvaluationError(
                "case has no engagement_id"
            )

        if not isinstance(claims, list) or not claims:
            raise EvaluationError(
                f"{engagement_id} contains no claims"
            )

        for claim in claims:
            claim_id = claim.get("claim_id")
            section = claim.get("section")
            text = claim.get("text")
            supported = claim.get("supported")
            evidence = claim.get("evidence")
            notes = claim.get("notes")

            if not isinstance(claim_id, str) or not claim_id:
                raise EvaluationError(
                    f"{engagement_id} contains a claim "
                    "without claim_id"
                )

            if claim_id in seen_claim_ids:
                raise EvaluationError(
                    f"duplicate claim_id: {claim_id}"
                )

            seen_claim_ids.add(claim_id)

            if not isinstance(section, str) or not section:
                raise EvaluationError(
                    f"{claim_id} has no section"
                )

            if not isinstance(text, str) or not text.strip():
                raise EvaluationError(
                    f"{claim_id} has no claim text"
                )

            if type(supported) is not bool:
                raise EvaluationError(
                    f"{claim_id} has not been reviewed; "
                    "supported must be true or false"
                )

            if not isinstance(evidence, list):
                raise EvaluationError(
                    f"{claim_id} evidence must be a list"
                )

            if not all(
                isinstance(item, str) and item.strip()
                for item in evidence
            ):
                raise EvaluationError(
                    f"{claim_id} contains invalid evidence"
                )

            if not isinstance(notes, str):
                raise EvaluationError(
                    f"{claim_id} notes must be text"
                )

            if supported and not evidence:
                raise EvaluationError(
                    f"{claim_id} is marked supported but "
                    "has no evidence"
                )

            if not supported and not notes.strip():
                raise EvaluationError(
                    f"{claim_id} is marked unsupported but "
                    "has no explanatory note"
                )

            total_claims += 1
            engagement_counts[engagement_id]["total"] += 1
            section_counts[section]["total"] += 1

            if supported:
                supported_claims += 1
                engagement_counts[
                    engagement_id
                ]["supported"] += 1
                section_counts[section]["supported"] += 1
            else:
                unsupported_claims.append({
                    "engagement_id": engagement_id,
                    "claim_id": claim_id,
                    "section": section,
                    "text": text,
                    "notes": notes,
                })

    per_engagement = []

    for engagement_id, counts in sorted(
        engagement_counts.items()
    ):
        per_engagement.append({
            "engagement_id": engagement_id,
            "supported_claims": counts["supported"],
            "total_claims": counts["total"],
            "faithfulness": safe_rate(
                counts["supported"],
                counts["total"],
            ),
        })

    section_order = {
        "title": 0,
        "context": 1,
        "challenge": 2,
        "approach": 3,
        "technology": 4,
        "outcomes": 5,
    }

    per_section = []

    for section, counts in sorted(
        section_counts.items(),
        key=lambda item: (
            section_order.get(item[0], 100),
            item[0],
        ),
    ):
        per_section.append({
            "section": section,
            "supported_claims": counts["supported"],
            "total_claims": counts["total"],
            "faithfulness": safe_rate(
                counts["supported"],
                counts["total"],
            ),
        })

    score = safe_rate(
        supported_claims,
        total_claims,
    )

    return {
        "metric": "faithfulness",
        "definition": (
            "supported generated claims / "
            "all generated claims"
        ),
        "faithfulness": score,
        "faithfulness_percent": round(
            score * 100,
            2,
        ),
        "supported_claims": supported_claims,
        "total_claims": total_claims,
        "unsupported_claim_count": len(
            unsupported_claims
        ),
        "case_count": len(cases),
        "per_engagement": per_engagement,
        "per_section": per_section,
        "unsupported_claims": unsupported_claims,
        "limitations": [
            (
                "Faithfulness measures whether generated "
                "claims are supported."
            ),
            (
                "It does not measure whether every useful "
                "source fact was included."
            ),
            (
                "Labels are manually reviewed and should "
                "be spot-checked by another reviewer."
            ),
        ],
    }


def load_json(path: Path) -> dict:
    """Read a JSON file with clear errors."""
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise EvaluationError(
            f"no such file: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise EvaluationError(
            f"{path} is not valid JSON: {error}"
        ) from error

    if not isinstance(data, dict):
        raise EvaluationError(
            f"{path} must contain a JSON object"
        )

    return data


def write_json(data: dict, path: Path) -> None:
    """Write formatted UTF-8 JSON."""
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the CF-42 command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and score the CF-42 "
            "faithfulness evaluation."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help=(
            "Generate the ten-case manual "
            "evaluation set."
        ),
    )

    prepare_parser.add_argument(
        "--output",
        default=(
            "evaluation/faithfulness_cases.json"
        ),
        help="path for the generated review file",
    )

    prepare_parser.add_argument(
        "--engagement-id",
        action="append",
        dest="engagement_ids",
        help=(
            "engagement to include; repeat for "
            "multiple ids"
        ),
    )

    prepare_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "overwrite an existing evaluation set"
        ),
    )

    score_parser = subparsers.add_parser(
        "score",
        help=(
            "Validate manual labels and calculate "
            "faithfulness."
        ),
    )

    score_parser.add_argument(
        "evaluation_set",
        help="path to the reviewed evaluation set",
    )

    score_parser.add_argument(
        "--output",
        help=(
            "optional path for the JSON score report; "
            "otherwise JSON is printed to stdout"
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "prepare":
            output_path = Path(args.output)

            if output_path.exists() and not args.force:
                raise EvaluationError(
                    f"{output_path} already exists; "
                    "use --force only if you intend to "
                    "discard its labels"
                )

            engagement_ids = (
                args.engagement_ids
                if args.engagement_ids
                else list(DEFAULT_ENGAGEMENT_IDS)
            )

            evaluation_set = prepare_evaluation_set(
                corpus=load_corpus(),
                engagement_ids=engagement_ids,
            )

            write_json(
                evaluation_set,
                output_path,
            )

            claim_count = sum(
                len(case["claims"])
                for case in evaluation_set["cases"]
            )

            print(
                f"Prepared "
                f"{evaluation_set['case_count']} cases "
                f"and {claim_count} claims."
            )
            print(f"Review file: {output_path}")
            print(
                "Next: replace every supported:null "
                "with a manually checked label."
            )
            return

        if args.command == "score":
            evaluation_path = Path(
                args.evaluation_set
            )

            evaluation_set = load_json(
                evaluation_path
            )

            report = calculate_faithfulness(
                evaluation_set
            )

            if args.output:
                output_path = Path(args.output)

                write_json(
                    report,
                    output_path,
                )

                print(
                    f"Faithfulness: "
                    f"{report['faithfulness_percent']}%"
                )
                print(
                    f"Supported claims: "
                    f"{report['supported_claims']}/"
                    f"{report['total_claims']}"
                )
                print(f"Report: {output_path}")
            else:
                json.dump(
                    report,
                    sys.stdout,
                    indent=2,
                    ensure_ascii=False,
                )
                print()

    except EvaluationError as error:
        print(
            f"error: {error}",
            file=sys.stderr,
        )
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()