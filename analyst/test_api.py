import requests

from fastapi.testclient import TestClient

from analyst import api


client = TestClient(api.app)


SAMPLE_RECORDS = [
    {
        "id": "eng-01",
        "domain": "core banking",
        "region": "GCC",
        "client_type": "GCC bank",
        "outcomes": [
            {
                "metric": "latency reduced",
                "source_ref": "test.pdf#page=1",
            }
        ],
    },
    {
        "id": "eng-02",
        "domain": "core banking",
        "region": "DE",
        "client_type": "German bank",
        "outcomes": [
            {
                "metric": "processing improved",
                "source_ref": "test.pdf#page=2",
            }
        ],
    },
    {
        "id": "eng-03",
        "domain": "cloud",
        "region": "GCC",
        "client_type": "GCC bank",
        "outcomes": [],
    },
]


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def fake_vault_get(*args, **kwargs):
    return FakeResponse(SAMPLE_RECORDS)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "analyst",
    }


def test_coverage_uses_vault_records(monkeypatch):
    monkeypatch.setattr(
        api.requests,
        "get",
        fake_vault_get,
    )

    response = client.get("/coverage")

    assert response.status_code == 200

    data = response.json()

    assert data["total_engagements"] == 3
    assert data["by_domain"]["core banking"] == 2
    assert data["by_domain"]["cloud"] == 1
    assert data["no_outcome"] == ["eng-03"]


def test_gaps_uses_vault_records(monkeypatch):
    monkeypatch.setattr(
        api.requests,
        "get",
        fake_vault_get,
    )

    response = client.get("/gaps")

    assert response.status_code == 200

    data = response.json()

    assert data["total_gaps"] == 1

    assert data["gaps"] == [
        {
            "domain": "cloud",
            "region": "DE",
        }
    ]


def test_vault_unavailable_returns_503(monkeypatch):
    def fail_get(*args, **kwargs):
        raise requests.ConnectionError(
            "Vault is unavailable"
        )

    monkeypatch.setattr(
        api.requests,
        "get",
        fail_get,
    )

    response = client.get("/coverage")

    assert response.status_code == 503

    data = response.json()

    assert (
        data["detail"]["error"]
        == "vault_unavailable"
    )