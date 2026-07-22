"""Tests for the Vault."""
from common.contract import load_corpus, load_seed
from vault.vault import store, get


def test_round_trip_is_identical():
    """Save a record, read it back. Nothing lost, nothing changed."""
    original = load_seed("eng-01")
    store(original)
    reloaded = get("eng-01")
    assert reloaded == original, "the record changed on its way through the store"


def test_missing_record_returns_none():
    """A record that isn't there must return None, not explode."""
    assert get("eng-does-not-exist") is None


def test_eng12_empty_outcomes_round_trip():
    """eng-12 has an empty outcomes list — it must survive untouched."""
    eng12 = next(r for r in load_corpus() if r["id"] == "eng-12")
    store(eng12)
    reloaded = get("eng-12")
    assert reloaded == eng12
    assert reloaded["outcomes"] == []


def test_eng02_keeps_may_be_named_flag():
    """eng-02 is the only record with may_be_named: true. Don't lose it."""
    store(load_seed("eng-02"))
    assert get("eng-02")["may_be_named"] is True


# TODO(Kaan): once serve() exists, test GET /engagements/nope returns 404
