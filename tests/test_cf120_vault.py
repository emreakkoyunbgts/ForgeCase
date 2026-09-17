"""CF-120 source integrity across the Vault's HTTP and legacy storage boundary."""
from copy import deepcopy
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from vault import vault


def source():
    return {
        "id": "cf120-vault-source", "client": "Example Bank",
        "client_type": "retail bank", "may_be_named": False,
        "domain": "payments", "region": "TR", "challenge": "Manual processing.",
        "solution": "Automated processing.", "technologies": ["Python", "SQLite"],
        "outcomes": [{"metric": "Latency reduced by 45%", "source_ref": "source.pdf#page=1"}],
    }


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "vault.db"
    monkeypatch.setattr(vault, "DB_PATH", str(path))
    monkeypatch.setenv("CASEFORGE_TOKEN", "cf120-vault-test")
    return path


@pytest.fixture
def client(database):
    with TestClient(vault.create_app(), raise_server_exceptions=False) as connection:
        connection.headers["Authorization"] = "Bearer cf120-vault-test"
        yield connection


def extended_source():
    record = source()
    record.update(
        completed_at="2026-09-01", supports_qualitative_claims=True,
        team_size=7, duration_months=11, outcome_missing=False,
        extension={"note": "Ödeme", "review": [None, False, 1.5, {"ready": True}]},
    )
    record["outcomes"][0]["evidence"] = {"page": 1, "approved": True}
    return record


@pytest.mark.parametrize("record_factory", [source, extended_source])
def test_http_representation_etag_list_and_history_roundtrip(client, record_factory):
    record = record_factory()
    created = client.post("/engagements", json=record)
    assert created.status_code == 201
    assert created.json() == record
    fetched = client.get(f"/engagements/{record['id']}")
    assert fetched.json() == record
    assert created.headers["ETag"] == fetched.headers["ETag"]
    assert client.get("/engagements", params={"domain": "payments", "limit": 1}).json()["items"] == [record]

    updated = deepcopy(record)
    updated["challenge"] = "Updated source facts."
    updated.pop("extension", None)
    updated["completed_at"] = "2026-09-02"
    replaced = client.put(
        f"/engagements/{record['id']}", json=updated,
        headers={"If-Match": created.headers["ETag"]},
    )
    assert replaced.status_code == 200
    assert replaced.json() == updated
    fetched = client.get(f"/engagements/{record['id']}")
    assert fetched.json() == updated
    assert replaced.headers["ETag"] == fetched.headers["ETag"]
    assert replaced.headers["ETag"] != created.headers["ETag"]
    versions = client.get(f"/engagements/{record['id']}/versions").json()["versions"]
    assert [item["etag"] for item in versions] == [vault.etag_for(record), vault.etag_for(updated)]
    past = client.get(f"/engagements/{record['id']}", params={"as_of": versions[0]["recorded_at"]})
    assert past.json() == record
    assert past.headers["ETag"] == created.headers["ETag"]

    deleted = client.delete(f"/engagements/{record['id']}", headers={"If-Match": replaced.headers["ETag"]})
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"/engagements/{record['id']}").status_code == 404
    assert client.get(f"/engagements/{record['id']}/versions").json()["versions"] == versions
    assert client.get(f"/engagements/{record['id']}", params={"as_of": versions[-1]["recorded_at"]}).json() == updated


INVALID_FIELDS = [
    {"id": 987654}, {"id": "../source"}, {"id": "x" * 201},
    {"client": []}, {"client": " "}, {"client_type": 4}, {"domain": None},
    {"region": []}, {"region": "EU"}, {"challenge": {}}, {"solution": False},
    {"may_be_named": 1}, {"may_be_named": "false"},
    {"technologies": "Python"}, {"technologies": [{"name": "Python"}]},
    {"technologies": [123]}, {"outcomes": {}}, {"outcomes": ["metric"]},
    {"outcomes": [{"metric": 123, "source_ref": "source.pdf"}]},
    {"outcomes": [{"metric": "Latency reduced", "source_ref": []}]},
    {"outcomes": [{"metric": " ", "source_ref": "source.pdf"}]},
    {"outcomes": [{"source_ref": "source.pdf"}]},
    {"outcome_missing": "false"}, {"supports_qualitative_claims": 1},
    {"team_size": True}, {"team_size": 1.5}, {"duration_months": "11"},
    {"duration_months": 2**63}, {"completed_at": 20260901},
]


@pytest.mark.parametrize("invalid", INVALID_FIELDS)
@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_invalid_known_types_are_json_422_without_writing(client, invalid, method):
    record = source()
    original = client.post("/engagements", json=record)
    bad = {**record, "id": "cf120-invalid-new", **invalid}
    headers = {}
    path = "/engagements"
    if method == "PUT":
        bad = {**record, **invalid}
        path += "/" + record["id"]
        headers["If-Match"] = original.headers["ETag"]
    result = client.request(method, path, json=bad, headers=headers)
    assert result.status_code == 422
    assert result.headers["content-type"].startswith("application/json")
    assert isinstance(result.json()["detail"], str)
    assert client.get("/engagements").json()["items"] == [record]
    assert len(client.get(f"/engagements/{record['id']}/versions").json()["versions"]) == 1
    assert client.get(f"/engagements/{record['id']}").headers["ETag"] == original.headers["ETag"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_extension_value_is_rejected_before_write(client, value):
    record = {**source(), "extension": {"value": value}}
    result = client.post("/engagements", content=json.dumps(record), headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    assert isinstance(result.json()["detail"], str)
    assert client.get("/engagements").json()["total"] == 0
    assert client.get(f"/engagements/{record['id']}/versions").status_code == 404


def test_empty_outcomes_and_optional_absence_are_preserved(client):
    record = {**source(), "outcomes": [], "outcome_missing": True, "extension": None}
    posted = client.post("/engagements", json=record)
    assert posted.status_code == 201
    fetched = client.get(f"/engagements/{record['id']}")
    assert fetched.json() == record
    assert fetched.headers["ETag"] == posted.headers["ETag"]


def test_legacy_schema_migration_restores_latest_snapshot_without_resurrecting_deletes(database):
    # Independent pre-CF120 schema: no complete-current-payload table exists.
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE engagements (
                id TEXT PRIMARY KEY, client TEXT NOT NULL, client_type TEXT NOT NULL,
                may_be_named INTEGER NOT NULL, domain TEXT NOT NULL, region TEXT NOT NULL,
                challenge TEXT NOT NULL, solution TEXT NOT NULL, outcome_missing INTEGER,
                team_size INTEGER, duration_months INTEGER
            );
            CREATE TABLE outcomes (engagement_id TEXT, position INTEGER, metric TEXT, source_ref TEXT,
                PRIMARY KEY (engagement_id, position),
                FOREIGN KEY (engagement_id) REFERENCES engagements(id) ON DELETE CASCADE);
            CREATE TABLE technologies (engagement_id TEXT, position INTEGER, name TEXT,
                PRIMARY KEY (engagement_id, position),
                FOREIGN KEY (engagement_id) REFERENCES engagements(id) ON DELETE CASCADE);
            CREATE TABLE engagement_versions (engagement_id TEXT, version INTEGER, recorded_at TEXT, data TEXT,
                PRIMARY KEY (engagement_id, version));
        """)
        old = source()
        current = extended_source()
        unversioned = {**source(), "id": "legacy-unversioned", "outcomes": [], "technologies": []}
        for record in (current, unversioned):
            connection.execute(
                "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record["id"], record["client"], record["client_type"], int(record["may_be_named"]),
                 record["domain"], record["region"], record["challenge"], record["solution"],
                 int(record["outcome_missing"]) if "outcome_missing" in record else None,
                 record.get("team_size"), record.get("duration_months")),
            )
            for position, outcome in enumerate(record["outcomes"]):
                connection.execute("INSERT INTO outcomes VALUES (?, ?, ?, ?)",
                                   (record["id"], position, outcome["metric"], outcome["source_ref"]))
            for position, technology in enumerate(record["technologies"]):
                connection.execute("INSERT INTO technologies VALUES (?, ?, ?)", (record["id"], position, technology))
        deleted = {**source(), "id": "legacy-deleted"}
        snapshots = [(old["id"], 1, "2026-01-01T00:00:00Z", json.dumps(old)),
                     (current["id"], 2, "2026-02-01T00:00:00Z", json.dumps(current)),
                     (deleted["id"], 1, "2026-01-01T00:00:00Z", json.dumps(deleted))]
        connection.executemany("INSERT INTO engagement_versions VALUES (?, ?, ?, ?)", snapshots)

    assert vault.get(current["id"]) == current
    assert vault.get(unversioned["id"]) == unversioned
    assert vault.get(deleted["id"]) is None
    assert vault.get(old["id"], as_of="2026-01-15") == old
    assert vault.get(deleted["id"], as_of="2026-01-15") == deleted
    items, total = vault.list_all()
    assert total == 2
    assert {item["id"]: item for item in items} == {current["id"]: current, unversioned["id"]: unversioned}
    assert [entry["etag"] for entry in vault.list_versions(current["id"])] == [vault.etag_for(old), vault.etag_for(current)]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM engagement_versions ORDER BY engagement_id, version").fetchall() == sorted(snapshots)
        assert connection.execute("SELECT COUNT(*) FROM engagement_payloads").fetchone()[0] == 1

    # Initialization is repeatable; a new write upgrades an unversioned row.
    vault.store({**unversioned, "completed_at": "2026-09-01"})
    assert vault.get(unversioned["id"])["completed_at"] == "2026-09-01"
    assert vault.delete(current["id"]) is True
    assert vault.get(current["id"]) is None
    assert vault.get(current["id"], as_of="2026-03-01") == current
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT engagement_id FROM engagement_payloads").fetchall() == [(unversioned["id"],)]


def test_interrupted_payload_migration_rolls_back_and_can_retry(database, monkeypatch):
    record = extended_source()
    vault.store(record)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE engagement_payloads")

    original_connect = sqlite3.connect

    class InterruptedMigration(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if "INSERT OR IGNORE INTO engagement_payloads" in statement:
                raise sqlite3.OperationalError("simulated interrupted migration")
            return super().execute(statement, *args, **kwargs)

    monkeypatch.setattr(vault.sqlite3, "connect", lambda *args, **kwargs: original_connect(
        *args, factory=InterruptedMigration, **kwargs,
    ))
    with pytest.raises(sqlite3.OperationalError, match="simulated interrupted migration"):
        vault.init_db()
    with original_connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='engagement_payloads'"
        ).fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM engagement_versions").fetchone()[0] == 1
    monkeypatch.setattr(vault.sqlite3, "connect", original_connect)
    assert vault.get(record["id"]) == record
