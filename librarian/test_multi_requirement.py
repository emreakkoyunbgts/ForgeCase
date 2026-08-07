import pytest

from librarian.multi_requirement import (
    evaluate_rfp_requirements,
    split_requirements,
)


def test_split_numbered_requirements():
    text = """
    Requirements:
    1. Support real-time payments.
    2. Provide DORA evidence collection.
    3. Extract data from scanned documents.
    """

    assert split_requirements(text) == [
        "Support real-time payments.",
        "Provide DORA evidence collection.",
        "Extract data from scanned documents.",
    ]


def test_split_bullets_and_continuation_lines():
    text = """
    Technical Requirements:
    - Implement event-driven integration using Kafka.
      The implementation must support parallel processing.
    - Provide PostgreSQL-based reporting.
    """

    assert split_requirements(text) == [
        (
            "Implement event-driven integration using Kafka. "
            "The implementation must support parallel processing."
        ),
        "Provide PostgreSQL-based reporting.",
    ]


def test_split_plain_sentences_as_fallback():
    text = (
        "Support real-time payment processing. "
        "Provide operational-resilience evidence. "
        "Support scanned-document extraction."
    )

    assert split_requirements(text) == [
        "Support real-time payment processing.",
        "Provide operational-resilience evidence.",
        "Support scanned-document extraction.",
    ]


def test_empty_rfp_is_rejected():
    with pytest.raises(
        ValueError,
        match="RFP text is empty",
    ):
        split_requirements("   ")


def make_corpus():
    return [
        {"id": f"eng-{number:02d}"}
        for number in range(1, 7)
    ]


def fake_search(
    query,
    corpus,
    top_k=3,
    strategy="hybrid",
):
    """
    Four requirements have strong dense support.
    Two requirements deliberately fall below the threshold.
    """
    query_lower = query.casefold()

    mapping = {
        "real-time": ("eng-01", 0.81),
        "dora": ("eng-02", 0.73),
        "scanned": ("eng-03", 0.68),
        "observability": ("eng-04", 0.64),
        "blockchain": ("eng-05", 0.21),
        "manufacturing": ("eng-06", 0.18),
    }

    selected_id = "eng-06"
    dense_score = 0.10

    for keyword, values in mapping.items():
        if keyword in query_lower:
            selected_id, dense_score = values
            break

    if strategy == "dense":
        results = [
            {
                "engagement_id": selected_id,
                "score": dense_score,
                "why": "Dense semantic candidate.",
            }
        ]

        results.extend(
            {
                "engagement_id": record["id"],
                "score": 0.05,
                "why": "Lower-ranked dense candidate.",
            }
            for record in corpus
            if record["id"] != selected_id
        )

        return results[:top_k]

    return [{
        "engagement_id": selected_id,
        "score": 1.0,
        "why": "Hybrid top-ranked candidate.",
    }]


def test_coverage_reports_four_of_six():
    rfp = """
    Requirements:
    1. Support real-time payment processing.
    2. Provide DORA control-evidence collection.
    3. Extract data from scanned insurance documents.
    4. Improve payment observability and incident detection.
    5. Provide blockchain custody operations.
    6. Migrate a manufacturing SAP ERP platform.
    """

    result = evaluate_rfp_requirements(
        rfp_text=rfp,
        corpus=make_corpus(),
        top_k=3,
        strategy="hybrid",
        min_dense_score=0.45,
        search_fn=fake_search,
    )

    assert result["coverage"] == {
        "evidenced": 4,
        "gaps": 2,
        "total": 6,
        "ratio": 0.6667,
        "summary": (
            "We can evidence 4 of 6 requirements."
        ),
    }

    statuses = [
        requirement["status"]
        for requirement in result["requirements"]
    ]

    assert statuses == [
        "EVIDENCED",
        "EVIDENCED",
        "EVIDENCED",
        "EVIDENCED",
        "GAP",
        "GAP",
    ]


def test_gap_keeps_best_candidate_for_review():
    result = evaluate_rfp_requirements(
        rfp_text=(
            "1. Provide blockchain custody operations."
        ),
        corpus=make_corpus(),
        min_dense_score=0.45,
        search_fn=fake_search,
    )

    requirement = result["requirements"][0]

    assert requirement["status"] == "GAP"
    assert requirement["best_match"][
        "engagement_id"
    ] == "eng-05"
    assert requirement["best_match"][
        "evidence_score"
    ] == 0.21
    assert requirement["gap_reason"]