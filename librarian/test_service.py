import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

import librarian.service as service


client = TestClient(service.app)


def make_record(number):
    return {
        "id": f"eng-{number:02d}",
    }


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )

    def json(self):
        return self._data


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_returns_matches(monkeypatch):
    """
    Existing CF-92 behavior:
    /search still returns Librarian matches,
    but corpus now comes from Vault instead of load_corpus().
    """

    records = [
        {"id": "eng-01"},
    ]

    monkeypatch.setattr(
        service,
        "fetch_all_records_from_vault",
        lambda: records,
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
    assert (
        response.json()["matches"][0]["engagement_id"]
        == "eng-01"
    )


def test_search_uses_vault_records(monkeypatch):
    """
    Verify that /search passes the records fetched
    from Vault into the existing Librarian search logic.
    """

    records = [
        {"id": "eng-01"},
        {"id": "eng-02"},
    ]

    monkeypatch.setattr(
        service,
        "fetch_all_records_from_vault",
        lambda: records,
    )

    seen = {}

    def fake_search(
        query,
        corpus,
        top_k,
        strategy,
    ):
        seen["corpus"] = corpus

        return []

    monkeypatch.setattr(
        service,
        "librarian_search",
        fake_search,
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
    assert seen["corpus"] == records


def test_fetches_all_vault_pages(monkeypatch):
    """
    Vault has 12 records.
    With page size 5 Librarian should request:
    offset 0 -> 5 records
    offset 5 -> 5 records
    offset 10 -> 2 records
    """

    monkeypatch.setattr(
        service,
        "VAULT_PAGE_SIZE",
        5,
    )

    calls = []

    pages = {
        0: {
            "items": [
                make_record(i)
                for i in range(1, 6)
            ],
            "total": 12,
            "limit": 5,
            "offset": 0,
        },
        5: {
            "items": [
                make_record(i)
                for i in range(6, 11)
            ],
            "total": 12,
            "limit": 5,
            "offset": 5,
        },
        10: {
            "items": [
                make_record(11),
                make_record(12),
            ],
            "total": 12,
            "limit": 5,
            "offset": 10,
        },
    }

    def fake_get(
        url,
        params,
        headers,
        timeout,
    ):
        offset = params["offset"]
        calls.append(offset)

        return FakeResponse(
            pages[offset]
        )

    monkeypatch.setattr(
        service.requests,
        "get",
        fake_get,
    )

    records = (
        service.fetch_all_records_from_vault()
    )

    assert len(records) == 12

    assert [
        record["id"]
        for record in records
    ] == [
        f"eng-{i:02d}"
        for i in range(1, 13)
    ]

    assert calls == [
        0,
        5,
        10,
    ]


def test_failed_page_is_retried_not_skipped(
    monkeypatch,
):
    """
    If offset 5 fails once, Librarian must retry
    offset 5 before moving to offset 10.
    """

    monkeypatch.setattr(
        service,
        "VAULT_PAGE_SIZE",
        5,
    )

    calls = []
    page_2_attempts = 0

    def fake_get(
        url,
        params,
        headers,
        timeout,
    ):
        nonlocal page_2_attempts

        offset = params["offset"]
        calls.append(offset)

        if offset == 0:
            return FakeResponse({
                "items": [
                    make_record(i)
                    for i in range(1, 6)
                ],
                "total": 12,
                "limit": 5,
                "offset": 0,
            })

        if offset == 5:
            page_2_attempts += 1

            if page_2_attempts == 1:
                raise requests.ConnectionError(
                    "temporary Vault failure"
                )

            return FakeResponse({
                "items": [
                    make_record(i)
                    for i in range(6, 11)
                ],
                "total": 12,
                "limit": 5,
                "offset": 5,
            })

        if offset == 10:
            return FakeResponse({
                "items": [
                    make_record(11),
                    make_record(12),
                ],
                "total": 12,
                "limit": 5,
                "offset": 10,
            })

        raise AssertionError(
            f"Unexpected offset: {offset}"
        )

    monkeypatch.setattr(
        service.requests,
        "get",
        fake_get,
    )

    records = (
        service.fetch_all_records_from_vault()
    )

    assert len(records) == 12

    assert calls == [
        0,
        5,
        5,
        10,
    ]


def test_permanent_page_failure_returns_503(
    monkeypatch,
):
    """
    A page that keeps failing must stop the operation.
    Librarian must not silently skip the page.
    """

    monkeypatch.setattr(
        service,
        "VAULT_PAGE_SIZE",
        5,
    )

    monkeypatch.setattr(
        service,
        "VAULT_MAX_RETRIES",
        2,
    )

    calls = []

    def fake_get(
        url,
        params,
        headers,
        timeout,
    ):
        offset = params["offset"]
        calls.append(offset)

        if offset == 0:
            return FakeResponse({
                "items": [
                    make_record(i)
                    for i in range(1, 6)
                ],
                "total": 12,
                "limit": 5,
                "offset": 0,
            })

        if offset == 5:
            raise requests.ConnectionError(
                "Vault unavailable"
            )

        raise AssertionError(
            "Failed page was skipped"
        )

    monkeypatch.setattr(
        service.requests,
        "get",
        fake_get,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.fetch_all_records_from_vault()

    assert exc_info.value.status_code == 503

    assert (
        exc_info.value.detail["error"]
        == "vault_page_failed"
    )

    # Initial call + 2 retries
    assert calls == [
        0,
        5,
        5,
        5,
    ]

    assert 10 not in calls


def test_caseforge_token_is_sent(
    monkeypatch,
):
    """
    When CASEFORGE_TOKEN is configured,
    Librarian sends it to Vault as a Bearer token.
    """

    monkeypatch.setenv(
        "CASEFORGE_TOKEN",
        "test-token",
    )

    captured_headers = {}

    def fake_get(
        url,
        params,
        headers,
        timeout,
    ):
        captured_headers.update(headers)

        return FakeResponse({
            "items": [
                make_record(1),
            ],
            "total": 1,
            "limit": 50,
            "offset": 0,
        })

    monkeypatch.setattr(
        service.requests,
        "get",
        fake_get,
    )

    service.fetch_all_records_from_vault()

    assert captured_headers == {
        "Authorization": "Bearer test-token",
    }


def test_match_uses_vault_records(
    monkeypatch,
):
    """
    /match must also use the Vault corpus,
    not load_corpus().
    """

    records = [
        {"id": "eng-01"},
        {"id": "eng-02"},
    ]

    monkeypatch.setattr(
        service,
        "fetch_all_records_from_vault",
        lambda: records,
    )

    seen = {}

    def fake_evaluate(
        rfp_text,
        corpus,
        top_k,
        strategy,
        min_dense_score,
    ):
        seen["corpus"] = corpus

        return {
            "requirements": [],
        }

    monkeypatch.setattr(
        service,
        "evaluate_rfp_requirements",
        fake_evaluate,
    )

    response = client.post(
        "/match",
        json={
            "rfp_text": "Need real-time payments",
            "top_k": 3,
            "strategy": "hybrid",
            "min_dense_score": 0.45,
        },
    )

    assert response.status_code == 200
    assert seen["corpus"] == records