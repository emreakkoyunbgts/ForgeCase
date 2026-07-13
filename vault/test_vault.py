"""Tests for the Vault."""
from common.contract import load_seed
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


# TODO(Kaan): test that eng-12 (EMPTY outcomes list) stores and reloads fine
# TODO(Kaan): once serve() exists, test GET /engagements/nope returns 404
