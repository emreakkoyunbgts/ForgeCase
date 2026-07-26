"""Tests for the Vault."""
from fastapi.testclient import TestClient

from common.contract import load_corpus, load_seed
from vault.vault import create_app, store, get


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


def test_api_post_then_get_round_trip():
    """Happy path: POST a record, GET it back identically over HTTP."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    response = client.post("/engagements", json=original)
    assert response.status_code == 201
    response = client.get("/engagements/eng-01")
    assert response.status_code == 200
    assert response.json() == original


def test_api_missing_record_returns_404():
    """The one that matters: an unknown id must 404, not 500 or 200."""
    client = TestClient(create_app())
    response = client.get("/engagements/eng-does-not-exist")
    assert response.status_code == 404


def test_api_list_contains_stored_records():
    """GET /engagements returns everything we stored."""
    client = TestClient(create_app())
    client.post("/engagements", json=load_seed("eng-01"))
    client.post("/engagements", json=load_seed("eng-02"))
    ids = [r["id"] for r in client.get("/engagements").json()]
    assert "eng-01" in ids and "eng-02" in ids
