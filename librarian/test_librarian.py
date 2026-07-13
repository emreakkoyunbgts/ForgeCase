"""Tests for the Librarian."""
from common.contract import load_corpus
from librarian.librarian import search


def test_payments_rfp_finds_the_right_engagement():
    """
    The payments RFP is about GCC + Kafka + core banking + batch windows.
    That is eng-01. If eng-01 is not in the top 3, the search is not working.
    """
    query = open("caseforge-testdata/rfp/rfp_01_realtime_payments.txt").read()
    matches = search(query, load_corpus(), top_k=3)
    ids = [m["engagement_id"] for m in matches]

    assert "eng-01" in ids, f"expected eng-01 in the top 3, got {ids}"


# TODO(Arda): rfp_02 (DORA, German lender) should surface eng-07. Test it.
# TODO(Arda): make eng-01 rank FIRST, not just top-3.
