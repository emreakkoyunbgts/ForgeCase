import re

import pytest

from common.contract import load_corpus
from evaluation.faithfulness import (
    DEFAULT_ENGAGEMENT_IDS,
    EvaluationError,
    calculate_faithfulness,
    extract_claims,
    generate_without_pdf,
    prepare_evaluation_set,
)


def sample_case_study():
    return {
        "engagement_id": "eng-01",
        "title": (
            "Core banking for a Tier-1 GCC bank"
        ),
        "sections": {
            "context": (
                "A Tier-1 GCC bank in GCC."
            ),
            "challenge": (
                "The legacy platform was slow. "
                "It could not support real-time payments."
            ),
            "approach": (
                "BGTS used a phased migration."
            ),
            "technology": "Java, Kafka",
            "outcomes": (
                "payment latency reduced 45%; "
                "batch window reduced to 90 minutes"
            ),
        },
        "citations": [],
        "client_named": False,
    }


def labelled_claim(
    claim_id,
    supported,
    section="challenge",
):
    return {
        "claim_id": claim_id,
        "section": section,
        "text": f"Claim {claim_id}",
        "supported": supported,
        "evidence": (
            ["challenge"]
            if supported
            else []
        ),
        "notes": (
            ""
            if supported
            else "No supporting source fact."
        ),
    }


def test_extract_claims_splits_lists_and_sentences():
    claims = extract_claims(
        sample_case_study()
    )

    technology_claims = [
        claim["text"]
        for claim in claims
        if claim["section"] == "technology"
    ]

    outcome_claims = [
        claim["text"]
        for claim in claims
        if claim["section"] == "outcomes"
    ]

    challenge_claims = [
        claim["text"]
        for claim in claims
        if claim["section"] == "challenge"
    ]

    assert technology_claims == [
        "Java",
        "Kafka",
    ]

    assert outcome_claims == [
        "payment latency reduced 45%",
        "batch window reduced to 90 minutes",
    ]

    assert len(challenge_claims) == 2


def test_calculate_faithfulness():
    evaluation_set = {
        "cases": [
            {
                "engagement_id": "eng-01",
                "claims": [
                    labelled_claim(
                        "eng-01-claim-1",
                        True,
                    ),
                    labelled_claim(
                        "eng-01-claim-2",
                        True,
                    ),
                    labelled_claim(
                        "eng-01-claim-3",
                        False,
                    ),
                ],
            }
        ]
    }

    report = calculate_faithfulness(
        evaluation_set
    )

    assert report["supported_claims"] == 2
    assert report["total_claims"] == 3
    assert report["faithfulness"] == 0.6667
    assert report[
        "unsupported_claim_count"
    ] == 1


def test_unreviewed_claim_is_rejected():
    evaluation_set = {
        "cases": [
            {
                "engagement_id": "eng-01",
                "claims": [
                    {
                        "claim_id": (
                            "eng-01-challenge-01"
                        ),
                        "section": "challenge",
                        "text": "A generated claim.",
                        "supported": None,
                        "evidence": [],
                        "notes": "",
                    }
                ],
            }
        ]
    }

    with pytest.raises(
        EvaluationError,
        match="has not been reviewed",
    ):
        calculate_faithfulness(
            evaluation_set
        )


def test_supported_claim_requires_evidence():
    evaluation_set = {
        "cases": [
            {
                "engagement_id": "eng-01",
                "claims": [
                    {
                        "claim_id": (
                            "eng-01-challenge-01"
                        ),
                        "section": "challenge",
                        "text": "A generated claim.",
                        "supported": True,
                        "evidence": [],
                        "notes": "",
                    }
                ],
            }
        ]
    }

    with pytest.raises(
        EvaluationError,
        match="has no evidence",
    ):
        calculate_faithfulness(
            evaluation_set
        )


def test_default_set_has_ten_cases_and_eng12(
    monkeypatch,
):
    records = []

    for number in range(1, 13):
        engagement_id = f"eng-{number:02d}"

        records.append({
            "id": engagement_id,
            "client": f"Client {number}",
            "client_type": "Anonymous bank",
            "may_be_named": False,
            "domain": "banking",
            "region": "UK",
            "challenge": "A source challenge.",
            "solution": "A source solution.",
            "technologies": ["Python"],
            "outcomes": [],
            "outcome_missing": True,
        })

    def fake_generate(record):
        return {
            "engagement_id": record["id"],
            "title": "Banking for an anonymous bank",
            "sections": {
                "context": "An anonymous bank in UK.",
                "challenge": record["challenge"],
                "approach": record["solution"],
                "technology": "Python",
                "outcomes": (
                    "[MISSING: no measurable outcome "
                    "was recorded for this engagement]"
                ),
            },
            "citations": [],
            "client_named": False,
        }

    monkeypatch.setattr(
        "evaluation.faithfulness.generate_without_pdf",
        fake_generate,
    )

    result = prepare_evaluation_set(
        records,
        DEFAULT_ENGAGEMENT_IDS,
    )

    ids = {
        case["engagement_id"]
        for case in result["cases"]
    }

    assert result["case_count"] == 10
    assert "eng-12" in ids


def test_eng12_does_not_generate_numeric_outcome():
    record = next(
        record
        for record in load_corpus()
        if record["id"] == "eng-12"
    )

    case_study = generate_without_pdf(
        record
    )

    outcome_text = case_study[
        "sections"
    ]["outcomes"]

    assert outcome_text.startswith("[MISSING:")
    assert re.search(r"\d", outcome_text) is None