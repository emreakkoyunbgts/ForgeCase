"""Tests for the Librarian."""
from common.contract import load_corpus
from librarian.librarian import search


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
        
# TODO(Arda): rfp_02 (DORA, German lender) should surface eng-07. Test it.
# TODO(Arda): make eng-01 rank FIRST, not just top-3.
