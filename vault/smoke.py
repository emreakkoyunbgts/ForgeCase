"""
CF-114 cutover smoke.

Proves the live engagement store is Vault over HTTP — not a JSON file.
Fixtures in caseforge-testdata/ stay as seed; after load, every read
goes through /engagements.
"""
from common.contract import REQUIRED_FIELDS, load_corpus


class SmokeFailed(Exception):
    """One cutover check failed."""


def _same_contract(got, expected):
    """Compare the fields Vault actually stores, not leftover file keys."""
    for field in REQUIRED_FIELDS:
        if got.get(field) != expected.get(field):
            return False, field
    return True, None


def seed_via_http(client, corpus):
    """POST each corpus record. 201 = new, 409 = already in Vault."""
    created = 0
    existed = 0
    for record in corpus:
        response = client.post("/engagements", json=record)
        if response.status_code == 201:
            created += 1
        elif response.status_code == 409:
            existed += 1
        else:
            raise SmokeFailed(
                f"POST {record['id']} → {response.status_code} "
                f"{response.json()}"
            )
    return created, existed


def assert_store_over_http(client, corpus):
    """Health, list, every id, and a duplicate POST (409)."""
    health = client.get("/health")
    if health.status_code != 200 or health.json().get("status") != "ok":
        raise SmokeFailed(f"/health not ok: {health.status_code} {health.text}")
    if health.json().get("records", 0) < len(corpus):
        raise SmokeFailed(
            f"/health records={health.json().get('records')} "
            f"< corpus {len(corpus)}"
        )

    listed = client.get("/engagements")
    if listed.status_code != 200:
        raise SmokeFailed(f"GET /engagements → {listed.status_code}")
    body = listed.json()
    if body.get("total", 0) < len(corpus):
        raise SmokeFailed(f"list total={body.get('total')} < {len(corpus)}")
    got_ids = {item["id"] for item in body["items"]}
    missing = {record["id"] for record in corpus} - got_ids
    if missing:
        raise SmokeFailed(f"list missing ids: {sorted(missing)}")

    for record in corpus:
        response = client.get(f"/engagements/{record['id']}")
        if response.status_code != 200:
            raise SmokeFailed(
                f"GET {record['id']} → {response.status_code}"
            )
        ok, field = _same_contract(response.json(), record)
        if not ok:
            raise SmokeFailed(
                f"{record['id']} field {field} does not match corpus"
            )

    again = client.post("/engagements", json=corpus[0])
    if again.status_code != 409:
        raise SmokeFailed(
            f"duplicate POST should be 409, got {again.status_code}"
        )


def run_smoke(client):
    """Load corpus over HTTP if needed, then prove Vault is the store."""
    corpus = load_corpus()
    created, existed = seed_via_http(client, corpus)
    assert_store_over_http(client, corpus)
    return {
        "records": len(corpus),
        "created": created,
        "already_stored": existed,
    }
