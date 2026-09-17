"""
CF-73 — RFP Response Builder.

Turns CF-72 multi-requirement retrieval results into a structured,
verified RFP response.

Flow:
    Librarian / CF-72
    -> Generator for evidenced requirements
    -> Verifier gate
    -> SUPPORTED or GAP

Generated content never ships unless it passes Verifier.
"""

from __future__ import annotations

import os
import uuid
from typing import Callable

import requests

from librarian.multi_requirement import (
    DEFAULT_MIN_DENSE_SCORE,
    evaluate_rfp_requirements,
)


GENERATOR_URL = os.getenv(
    "GENERATOR_URL",
    "http://127.0.0.1:8001",
).rstrip("/")

VERIFIER_URL = os.getenv(
    "VERIFIER_URL",
    "http://127.0.0.1:8003",
).rstrip("/")

RFP_RESPONSE_TIMEOUT_SECONDS = float(
    os.getenv(
        "RFP_RESPONSE_TIMEOUT_SECONDS",
        "10",
    )
)


class RFPResponseDependencyError(RuntimeError):
    """Raised when Generator or Verifier cannot be used safely."""


def service_headers(correlation_id: str) -> dict[str, str]:
    """
    Build shared service-to-service headers.

    Carry one correlation ID through Generator and Verifier.
    Forward the CaseForge token when configured.
    """
    headers = {
        "X-Correlation-ID": correlation_id,
    }

    token = os.getenv("CASEFORGE_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def _post_json(
    url: str,
    payload: dict,
    correlation_id: str,
) -> dict:
    """
    POST JSON to another CaseForge service.

    Dependency failures are converted to a clean application error so
    the RFP builder can degrade to GAP instead of crashing.
    """
    try:
        response = requests.post(
            url,
            json=payload,
            headers=service_headers(correlation_id),
            timeout=RFP_RESPONSE_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

    except (
        requests.ConnectionError,
        requests.Timeout,
        requests.HTTPError,
    ) as error:
        raise RFPResponseDependencyError(
            f"{url} unavailable: {error}"
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise RFPResponseDependencyError(
            f"{url} returned invalid JSON"
        ) from error

    if not isinstance(data, dict):
        raise RFPResponseDependencyError(
            f"{url} response must be a JSON object"
        )

    return data


def call_generator(
    record: dict,
    correlation_id: str,
) -> dict:
    """
    Call Taha's English Generator endpoint.

    Contract:
        POST /generator/mcs/eng
        body = Engagement Record
        response = multi-source case study
    """
    return _post_json(
        f"{GENERATOR_URL}/generator/mcs/eng",
        record,
        correlation_id,
    )


def call_verifier(
    record: dict,
    mcs: dict,
    correlation_id: str,
) -> dict:
    """
    Send the generated case study through the Verifier gate.

    Current merged integration contract:
        POST /verify/{engagement_id}
        {
            "record": {...},
            "mcs": {...}
        }
    """
    engagement_id = record["id"]

    return _post_json(
        f"{VERIFIER_URL}/verify/{engagement_id}",
        {
            "record": record,
            "mcs": mcs,
        },
        correlation_id,
    )


def proof_text_from_mcs(mcs: dict) -> str:
    """
    Flatten Generator section output into one proof block.

    No new claims are created here. This only joins text already
    returned by Generator.
    """
    sections = mcs.get("sections")

    if not isinstance(sections, dict):
        return ""

    parts = []

    for section_name in (
        "context",
        "challenge",
        "approach",
        "technology",
        "outcomes",
    ):
        value = sections.get(section_name)

        if isinstance(value, str):
            if value.strip():
                parts.append(value.strip())

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())

    return " ".join(parts)


def build_rfp_response(
    rfp_text: str,
    corpus: list[dict],
    generate_proof: Callable = call_generator,
    verify_proof: Callable = call_verifier,
    top_k: int = 3,
    strategy: str = "hybrid",
    min_dense_score: float = DEFAULT_MIN_DENSE_SCORE,
    evaluate_fn: Callable = evaluate_rfp_requirements,
) -> dict:
    """
    Build a verified first-draft response for a multi-requirement RFP.

    A requirement becomes SUPPORTED only when:
        1. CF-72 marks it EVIDENCED.
        2. The matching Engagement Record exists.
        3. Generator returns cited content.
        4. Verifier returns PASS.

    Everything else remains visible as a GAP.
    """
    evaluation = evaluate_fn(
        rfp_text=rfp_text,
        corpus=corpus,
        top_k=top_k,
        strategy=strategy,
        min_dense_score=min_dense_score,
    )

    records_by_id = {
        record["id"]: record
        for record in corpus
        if isinstance(record, dict)
        and isinstance(record.get("id"), str)
    }

    response_items = []

    for requirement in evaluation["requirements"]:
        requirement_id = requirement["requirement_id"]
        requirement_text = requirement["text"]

        if requirement["status"] != "EVIDENCED":
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": None,
                "proof": None,
                "citations": [],
                "gap_reason": requirement.get("gap_reason"),
                "retrieval": requirement.get("best_match"),
            })
            continue

        best_match = requirement["best_match"]
        engagement_id = best_match["engagement_id"]
        record = records_by_id.get(engagement_id)

        if record is None:
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    f"Matched engagement {engagement_id} "
                    "was not present in the corpus."
                ),
                "retrieval": best_match,
            })
            continue

        correlation_id = str(uuid.uuid4())

        try:
            mcs = generate_proof(
                record,
                correlation_id,
            )
        except RFPResponseDependencyError as error:
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    f"Generator unavailable: {error}"
                ),
                "retrieval": best_match,
            })
            continue

        citations = mcs.get("citations", [])

        if not isinstance(citations, list) or not citations:
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    "Generated proof did not contain citations."
                ),
                "retrieval": best_match,
            })
            continue

        proof_text = proof_text_from_mcs(mcs)

        if not proof_text:
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    "Generator returned no usable proof text."
                ),
                "retrieval": best_match,
            })
            continue

        try:
            verification = verify_proof(
                record,
                mcs,
                correlation_id,
            )
        except RFPResponseDependencyError as error:
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    f"Verifier unavailable: {error}"
                ),
                "retrieval": best_match,
            })
            continue

        if verification.get("verdict") != "PASS":
            response_items.append({
                "requirement_id": requirement_id,
                "text": requirement_text,
                "status": "GAP",
                "engagement_id": engagement_id,
                "proof": None,
                "citations": [],
                "gap_reason": (
                    "Generated proof did not pass verification."
                ),
                "retrieval": best_match,
                "verification": verification,
            })
            continue

        response_items.append({
            "requirement_id": requirement_id,
            "text": requirement_text,
            "status": "SUPPORTED",
            "engagement_id": engagement_id,
            "proof": proof_text,
            "citations": citations,
            "retrieval": best_match,
            "verification": verification,
            "correlation_id": correlation_id,
        })

    supported = sum(
        item["status"] == "SUPPORTED"
        for item in response_items
    )

    gaps = sum(
        item["status"] == "GAP"
        for item in response_items
    )

    return {
        "requirements": response_items,
        "summary": {
            "total_requirements": len(response_items),
            "supported": supported,
            "gaps": gaps,
        },
        "retrieval_configuration": evaluation.get(
            "configuration",
            {},
        ),
    }