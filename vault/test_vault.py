"""Tests for the Vault (L1 storage + L2/L4/L5 REST API)."""
from fastapi.testclient import TestClient

from common.contract import load_corpus, load_seed
from vault.vault import (
    create_app, store, get, delete, etag_for, init_db, list_versions,
)


def _clear(engagement_id):
    """Remove current row and version history — keeps tests independent."""
    delete(engagement_id)
    conn = init_db()
    with conn:
        conn.execute(
            "DELETE FROM engagement_versions WHERE engagement_id = ?",
            (engagement_id,),
        )


# ---------------------------------------------------------------------------
# L1 — storage round-trips
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# L2 / L4 — REST API
# ---------------------------------------------------------------------------

def test_api_post_then_get_round_trip():
    """Happy path: POST a record, GET it back identically over HTTP."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    response = client.post("/engagements", json=original)
    assert response.status_code == 201
    assert "ETag" in response.headers
    response = client.get("/engagements/eng-01")
    assert response.status_code == 200
    assert response.json() == original


def test_api_missing_record_returns_404():
    """An unknown id must 404, not 500 or 200."""
    client = TestClient(create_app())
    response = client.get("/engagements/eng-does-not-exist")
    assert response.status_code == 404


def test_api_list_contains_stored_records():
    """GET /engagements returns items + total."""
    client = TestClient(create_app())
    _clear("eng-01")
    _clear("eng-02")
    client.post("/engagements", json=load_seed("eng-01"))
    client.post("/engagements", json=load_seed("eng-02"))
    body = client.get("/engagements").json()
    ids = [r["id"] for r in body["items"]]
    assert "eng-01" in ids and "eng-02" in ids
    assert body["total"] >= 2


def test_api_post_duplicate_returns_409():
    """POST of an existing id must conflict — use PUT to update."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    assert client.post("/engagements", json=original).status_code == 201
    again = client.post("/engagements", json=original)
    assert again.status_code == 409


def test_api_put_updates_with_matching_etag():
    """PUT with the current ETag replaces the record."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    client.post("/engagements", json=original)
    etag = client.get("/engagements/eng-01").headers["ETag"]

    updated = dict(original)
    updated["challenge"] = "Updated challenge for L4 PUT test"
    response = client.put(
        "/engagements/eng-01",
        json=updated,
        headers={"If-Match": etag},
    )
    assert response.status_code == 200
    assert response.json()["challenge"] == updated["challenge"]


def test_api_put_stale_etag_returns_412():
    """PUT with an old ETag must fail — someone else changed the record."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    client.post("/engagements", json=original)

    updated = dict(original)
    updated["challenge"] = "stale write"
    response = client.put(
        "/engagements/eng-01",
        json=updated,
        headers={"If-Match": '"not-the-real-etag"'},
    )
    assert response.status_code == 412


def test_api_put_without_if_match_returns_428():
    """PUT without If-Match is rejected — concurrency requires the tag."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    client.post("/engagements", json=original)
    response = client.put("/engagements/eng-01", json=original)
    assert response.status_code == 428


def test_api_delete_with_etag():
    """DELETE with matching ETag removes the record (204)."""
    client = TestClient(create_app())
    original = load_seed("eng-01")
    _clear("eng-01")
    client.post("/engagements", json=original)
    etag = client.get("/engagements/eng-01").headers["ETag"]

    response = client.delete(
        "/engagements/eng-01", headers={"If-Match": etag}
    )
    assert response.status_code == 204
    assert client.get("/engagements/eng-01").status_code == 404


def test_api_list_filter_by_region():
    """GET /engagements?region=DE returns only DE records."""
    client = TestClient(create_app())
    _clear("eng-01")
    _clear("eng-02")
    client.post("/engagements", json=load_seed("eng-01"))  # GCC
    client.post("/engagements", json=load_seed("eng-02"))  # DE
    body = client.get("/engagements", params={"region": "DE"}).json()
    assert body["total"] >= 1
    assert all(r["region"] == "DE" for r in body["items"])
    assert any(r["id"] == "eng-02" for r in body["items"])


def test_api_list_pagination():
    """limit/offset slice the list; total stays the full count."""
    client = TestClient(create_app())
    for record in load_corpus()[:5]:
        store(record)
    body = client.get(
        "/engagements", params={"limit": 2, "offset": 0}
    ).json()
    assert len(body["items"]) == 2
    assert body["total"] >= 5
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_etag_changes_when_record_changes():
    """Any content change must produce a different ETag."""
    a = load_seed("eng-01")
    b = dict(a)
    b["challenge"] = a["challenge"] + "!"
    assert etag_for(a) != etag_for(b)


# ---------------------------------------------------------------------------
# L5 / CF-63 — record versioning (as-of)
# ---------------------------------------------------------------------------

def test_as_of_returns_older_snapshot():
    """After an update, as_of before the change returns the old content."""
    _clear("eng-01")
    original = load_seed("eng-01")
    store(original, recorded_at="2026-01-01T10:00:00Z")

    updated = dict(original)
    updated["challenge"] = "Changed for versioning test"
    store(updated, recorded_at="2026-01-01T12:00:00Z")

    assert get("eng-01")["challenge"] == updated["challenge"]
    past = get("eng-01", as_of="2026-01-01T11:00:00Z")
    assert past is not None
    assert past["challenge"] == original["challenge"]


def test_as_of_before_any_version_returns_none():
    """as_of earlier than the first snapshot finds nothing."""
    _clear("eng-01")
    store(load_seed("eng-01"), recorded_at="2026-06-01T00:00:00Z")
    assert get("eng-01", as_of="2026-01-01T00:00:00Z") is None


def test_versions_list_grows_on_each_store():
    """Each store appends one immutable version."""
    _clear("eng-01")
    original = load_seed("eng-01")
    store(original, recorded_at="2026-01-01T10:00:00Z")
    updated = dict(original)
    updated["challenge"] = "v2"
    store(updated, recorded_at="2026-01-01T11:00:00Z")
    versions = list_versions("eng-01")
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2


def test_api_as_of_query_param():
    """GET /engagements/{id}?as_of=... returns the historical snapshot."""
    client = TestClient(create_app())
    _clear("eng-01")
    original = load_seed("eng-01")
    store(original, recorded_at="2026-02-01T08:00:00Z")
    updated = dict(original)
    updated["challenge"] = "API as-of challenge"
    store(updated, recorded_at="2026-02-01T10:00:00Z")

    past = client.get(
        "/engagements/eng-01",
        params={"as_of": "2026-02-01T09:00:00Z"},
    )
    assert past.status_code == 200
    assert past.json()["challenge"] == original["challenge"]

    current = client.get("/engagements/eng-01")
    assert current.json()["challenge"] == updated["challenge"]


def test_api_versions_endpoint():
    """GET /engagements/{id}/versions lists snapshots."""
    client = TestClient(create_app())
    _clear("eng-01")
    store(load_seed("eng-01"), recorded_at="2026-03-01T00:00:00Z")
    body = client.get("/engagements/eng-01/versions").json()
    assert body["id"] == "eng-01"
    assert len(body["versions"]) == 1
    assert "recorded_at" in body["versions"][0]
    assert "etag" in body["versions"][0]


def test_delete_keeps_version_history_for_as_of():
    """Deleting the current row must not erase as-of history."""
    client = TestClient(create_app())
    _clear("eng-01")
    original = load_seed("eng-01")
    store(original, recorded_at="2026-04-01T00:00:00Z")
    etag = client.get("/engagements/eng-01").headers["ETag"]
    assert client.delete(
        "/engagements/eng-01", headers={"If-Match": etag}
    ).status_code == 204
    assert client.get("/engagements/eng-01").status_code == 404
    past = client.get(
        "/engagements/eng-01",
        params={"as_of": "2026-04-01T12:00:00Z"},
    )
    assert past.status_code == 200
    assert past.json()["id"] == "eng-01"
