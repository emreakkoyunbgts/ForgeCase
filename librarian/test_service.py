from fastapi.testclient import TestClient

import librarian.service as service


client = TestClient(service.app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_returns_matches(monkeypatch):
    monkeypatch.setattr(
        service,
        "load_corpus",
        lambda: [{"id": "eng-01"}],
    )

    monkeypatch.setattr(
        service,
        "librarian_search",
        lambda query, corpus, top_k, strategy: [
            {
                "engagement_id": "eng-01",
                "score": 0.91,
                "why": "matched test evidence",
            }
        ],
    )

    response = client.get(
        "/search",
        params={
            "q": "payments",
            "top": 3,
            "strategy": "hybrid",
        },
    )

    assert response.status_code == 200
    assert response.json()["matches"][0]["engagement_id"] == "eng-01"