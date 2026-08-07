"""Tests for the Librarian."""
from common.contract import load_corpus
from librarian.librarian import build_capability_statement, search


def load_rfp(filename):
    """Load one sample RFP as UTF-8 text."""
    path = f"caseforge-testdata/rfp/{filename}"

    with open(path, encoding="utf-8") as file:
        return file.read()


def test_payments_rfp_ranks_eng01_first():
    """
    The payments RFP is about GCC, Kafka, core banking, and batch windows.
    eng-01 should be the strongest match.
    """
    query = load_rfp("rfp_01_realtime_payments.txt")
    matches = search(query, load_corpus(), top_k=3)

    assert len(matches) == 3
    assert matches[0]["engagement_id"] == "eng-01", (
        f"expected eng-01 first, got "
        f"{[match['engagement_id'] for match in matches]}"
    )


def test_dora_rfp_ranks_eng07_first():
    """
    The DORA RFP concerns regulatory resilience for a German lender.
    eng-07 should be the strongest match.
    """
    query = load_rfp("rfp_02_regulatory_dora.txt")
    matches = search(query, load_corpus(), top_k=3)

    assert len(matches) == 3
    assert matches[0]["engagement_id"] == "eng-07", (
        f"expected eng-07 first, got "
        f"{[match['engagement_id'] for match in matches]}"
    )


def test_matches_include_l2_explanations():
    """
    Every retrieved engagement should explain why it matched.

    Do not assert the exact ordering of reasons because the embedding model
    determines their similarity scores.
    """
    query = load_rfp("rfp_01_realtime_payments.txt")
    matches = search(query, load_corpus(), top_k=3)

    for match in matches:
        why = match["why"]

        assert why, (
            f"{match['engagement_id']} has an empty explanation"
        )
        assert why.startswith("Matched on "), (
            f"unexpected explanation format: {why}"
        )
        assert "TODO" not in why, (
            f"{match['engagement_id']} still contains a TODO"
        )
        
def test_capability_statement_is_grounded():
    """
    The statement should use facts from the selected engagement and should
    attach source references to measurable outcomes.
    """
    corpus = load_corpus()

    eng01 = next(
        record
        for record in corpus
        if record["id"] == "eng-01"
    )

    matches = [{
        "engagement_id": "eng-01",
        "score": 1.0,
        "why": "Matched on domain: core banking",
    }]

    result = build_capability_statement(matches, corpus)

    assert result["text"]
    assert result["evidence"]

    assert eng01["domain"] in result["text"]
    assert eng01["region"] in result["text"]

    # The confidential real client name must not appear.
    assert eng01["client"] not in result["text"]

    valid_outcomes = {
        (
            outcome["metric"],
            outcome["source_ref"],
        )
        for outcome in eng01.get("outcomes", [])
    }

    outcome_evidence = [
        item
        for item in result["evidence"]
        if item["field"] == "outcome"
    ]

    assert outcome_evidence

    for item in outcome_evidence:
        assert (
            item["value"],
            item["source_ref"],
        ) in valid_outcomes

def test_capability_statement_does_not_invent_missing_outcomes():
    """
    eng-12 has no measurable outcomes. L3 must not manufacture one.
    """
    corpus = load_corpus()

    matches = [{
        "engagement_id": "eng-12",
        "score": 1.0,
        "why": "Matched on structured engagement fields",
    }]

    result = build_capability_statement(matches, corpus)

    outcome_evidence = [
        item
        for item in result["evidence"]
        if item["field"] == "outcome"
    ]

    assert outcome_evidence == []
    assert "Documented outcomes include:" not in result["text"]

def test_capability_statement_handles_no_matches():
    """No matches should produce a clear, non-invented response."""
    result = build_capability_statement(
        matches=[],
        corpus=load_corpus(),
    )

    assert result == {
        "text": "No relevant engagement evidence was found.",
        "evidence": [],
    }