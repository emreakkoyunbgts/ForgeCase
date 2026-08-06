"""
CF-72 — Multi-requirement RFP coverage.

Split a full RFP into individual requirements, retrieve the best
engagement for each requirement, and report evidenced requirements
and gaps.

Usage:

    python -m librarian.multi_requirement <rfp.txt> \
        --top 3 \
        --strategy hybrid \
        --min-dense-score 0.45
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

from common.contract import load_corpus
from common.errors import die
from librarian.librarian import search


DEFAULT_MIN_DENSE_SCORE = 0.45

LIST_ITEM = re.compile(
    r"""
    ^\s*
    (?:
        [-*•]
        |
        \d+[.)]
        |
        [A-Za-z][.)]
    )
    \s+
    (?P<text>.+?)
    \s*$
    """,
    re.VERBOSE,
)

HEADING = re.compile(
    r"""
    ^\s*
    (?:
        requirements?
        |
        mandatory\ requirements?
        |
        functional\ requirements?
        |
        technical\ requirements?
        |
        scope
        |
        scope\ of\ work
    )
    \s*:?\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    """Collapse repeated whitespace while preserving wording."""
    return " ".join(text.strip().split())


def deduplicate_requirements(requirements: list[str]) -> list[str]:
    """Remove duplicate requirements while preserving their order."""
    result = []
    seen = set()

    for requirement in requirements:
        cleaned = normalize_text(requirement)

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


def split_requirements(rfp_text: str) -> list[str]:
    """
    Split an RFP into individual requirements.

    Preferred format:
        1. First requirement
        2. Second requirement

    Also supports:
        - bullet lists
        * bullet lists
        • bullet lists

    When no list markers exist, paragraphs and sentences are used as
    a conservative fallback.
    """
    if not isinstance(rfp_text, str) or not rfp_text.strip():
        raise ValueError("RFP text is empty")

    list_items = []
    current_item = None
    saw_list_marker = False

    prose_blocks = []
    prose_lines = []

    for raw_line in rfp_text.splitlines():
        line = normalize_text(raw_line)

        if not line:
            if not saw_list_marker and prose_lines:
                prose_blocks.append(
                    normalize_text(" ".join(prose_lines))
                )
                prose_lines = []
            continue

        if HEADING.fullmatch(line):
            continue

        match = LIST_ITEM.match(line)

        if match:
            saw_list_marker = True

            if current_item:
                list_items.append(
                    normalize_text(current_item)
                )

            current_item = match.group("text")
            continue

        if saw_list_marker:
            # Treat an unmarked line following a list item as a
            # continuation of that requirement.
            if current_item:
                current_item = (
                    f"{current_item} {line}"
                )
        else:
            prose_lines.append(line)

    if current_item:
        list_items.append(
            normalize_text(current_item)
        )

    if prose_lines:
        prose_blocks.append(
            normalize_text(" ".join(prose_lines))
        )

    if saw_list_marker:
        requirements = list_items
    else:
        requirements = []

        for block in prose_blocks:
            sentences = [
                normalize_text(sentence)
                for sentence in SENTENCE_BOUNDARY.split(block)
                if normalize_text(sentence)
            ]

            requirements.extend(sentences)

    requirements = deduplicate_requirements(
        requirements
    )

    if not requirements:
        raise ValueError(
            "No RFP requirements could be extracted"
        )

    return requirements


def run_search(
    search_fn: Callable,
    requirement: str,
    corpus: list[dict],
    top_k: int,
    strategy: str,
) -> list[dict]:
    """
    Call the existing Librarian and produce a clearer error when
    CF-71 is missing.
    """
    try:
        return search_fn(
            requirement,
            corpus,
            top_k=top_k,
            strategy=strategy,
        )
    except TypeError as error:
        if "strategy" in str(error):
            raise RuntimeError(
                "CF-72 requires the CF-71 search interface "
                "with strategy='dense' and strategy='hybrid'"
            ) from error

        raise


def evaluate_requirement(
    requirement_id: str,
    requirement_text: str,
    corpus: list[dict],
    top_k: int = 3,
    strategy: str = "hybrid",
    min_dense_score: float = DEFAULT_MIN_DENSE_SCORE,
    search_fn: Callable | None = None,
) -> dict:
    """
    Retrieve the best engagement for one requirement.

    Hybrid scores are relative normalized reranking scores, so they
    must not be used as confidence values. A raw dense cosine score
    is therefore used as the initial evidence threshold.
    """
    if search_fn is None:
        search_fn = search

    if not corpus:
        return {
            "requirement_id": requirement_id,
            "text": requirement_text,
            "status": "GAP",
            "best_match": None,
            "gap_reason": "The engagement corpus is empty.",
        }

    # Retrieve all dense results so the raw cosine score for the
    # hybrid-selected engagement can be found.
    dense_results = run_search(
        search_fn=search_fn,
        requirement=requirement_text,
        corpus=corpus,
        top_k=len(corpus),
        strategy="dense",
    )

    dense_scores = {
        match["engagement_id"]: match["score"]
        for match in dense_results
    }

    if strategy == "dense":
        ranked_matches = dense_results[:top_k]
    else:
        ranked_matches = run_search(
            search_fn=search_fn,
            requirement=requirement_text,
            corpus=corpus,
            top_k=top_k,
            strategy=strategy,
        )

    if not ranked_matches:
        return {
            "requirement_id": requirement_id,
            "text": requirement_text,
            "status": "GAP",
            "best_match": None,
            "gap_reason": (
                "The Librarian returned no matching engagements."
            ),
        }

    best = ranked_matches[0]
    engagement_id = best["engagement_id"]
    dense_score = dense_scores.get(engagement_id)

    evidenced = (
        dense_score is not None
        and dense_score >= min_dense_score
    )

    best_match = {
        "engagement_id": engagement_id,
        "retrieval_strategy": strategy,
        "retrieval_score": best.get("score"),
        "evidence_score": dense_score,
        "why": best.get("why", ""),
    }

    if evidenced:
        return {
            "requirement_id": requirement_id,
            "text": requirement_text,
            "status": "EVIDENCED",
            "best_match": best_match,
            "gap_reason": None,
        }

    return {
        "requirement_id": requirement_id,
        "text": requirement_text,
        "status": "GAP",
        "best_match": best_match,
        "gap_reason": (
            "The best candidate's dense similarity "
            f"({dense_score}) is below the configured "
            f"evidence threshold ({min_dense_score})."
        ),
    }


def evaluate_rfp_requirements(
    rfp_text: str,
    corpus: list[dict],
    top_k: int = 3,
    strategy: str = "hybrid",
    min_dense_score: float = DEFAULT_MIN_DENSE_SCORE,
    search_fn: Callable | None = None,
) -> dict:
    """Evaluate every extracted requirement and aggregate coverage."""
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    if strategy not in {"dense", "hybrid"}:
        raise ValueError(
            "strategy must be 'dense' or 'hybrid'"
        )

    if not 0.0 <= min_dense_score <= 1.0:
        raise ValueError(
            "min_dense_score must be between 0 and 1"
        )

    requirements = split_requirements(rfp_text)

    results = []

    for index, requirement in enumerate(
        requirements,
        start=1,
    ):
        results.append(
            evaluate_requirement(
                requirement_id=f"REQ-{index:03d}",
                requirement_text=requirement,
                corpus=corpus,
                top_k=top_k,
                strategy=strategy,
                min_dense_score=min_dense_score,
                search_fn=search_fn,
            )
        )

    evidenced_count = sum(
        result["status"] == "EVIDENCED"
        for result in results
    )

    total_count = len(results)
    gap_count = total_count - evidenced_count

    coverage_ratio = (
        round(evidenced_count / total_count, 4)
        if total_count
        else 0.0
    )

    return {
        "requirements": results,
        "coverage": {
            "evidenced": evidenced_count,
            "gaps": gap_count,
            "total": total_count,
            "ratio": coverage_ratio,
            "summary": (
                f"We can evidence {evidenced_count} "
                f"of {total_count} requirements."
            ),
        },
        "configuration": {
            "retrieval_strategy": strategy,
            "top_k": top_k,
            "min_dense_score": min_dense_score,
            "threshold_note": (
                "The dense score threshold is a retrieval "
                "heuristic, not a probability or guarantee."
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Split a full RFP into requirements and "
            "report evidence coverage."
        )
    )

    parser.add_argument(
        "rfp",
        help="path to a multi-requirement RFP text file",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="number of retrieval candidates per requirement",
    )

    parser.add_argument(
        "--strategy",
        choices=("dense", "hybrid"),
        default="hybrid",
    )

    parser.add_argument(
        "--min-dense-score",
        type=float,
        default=DEFAULT_MIN_DENSE_SCORE,
        help=(
            "minimum raw dense cosine score required "
            "to mark a requirement as evidenced"
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    path = Path(args.rfp)

    try:
        rfp_text = path.read_text(
            encoding="utf-8"
        )
    except FileNotFoundError:
        die(f"no such file: {path}")
    except OSError as error:
        die(f"could not read {path}: {error}")

    try:
        result = evaluate_rfp_requirements(
            rfp_text=rfp_text,
            corpus=load_corpus(),
            top_k=args.top,
            strategy=args.strategy,
            min_dense_score=args.min_dense_score,
        )
    except (ValueError, RuntimeError) as error:
        die(str(error))

    json.dump(
        result,
        sys.stdout,
        indent=2,
        ensure_ascii=False,
    )
    print()


if __name__ == "__main__":
    main()