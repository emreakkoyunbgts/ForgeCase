import pytest

from librarian.cache import (
    TTLCache,
    corpus_fingerprint,
)


def test_cache_returns_value_before_ttl():
    current_time = [100.0]

    cache = TTLCache(
        ttl_seconds=10,
        time_fn=lambda: current_time[0],
    )

    cache.set(
        "payments",
        [{"id": "eng-01"}],
    )

    current_time[0] = 105.0

    assert cache.get("payments") == [
        {"id": "eng-01"}
    ]


def test_cache_expires_after_ttl():
    current_time = [100.0]

    cache = TTLCache(
        ttl_seconds=10,
        time_fn=lambda: current_time[0],
    )

    cache.set(
        "payments",
        [{"id": "eng-01"}],
    )

    current_time[0] = 111.0

    assert cache.get("payments") is None


def test_cache_invalidation_removes_entries():
    cache = TTLCache(
        ttl_seconds=60,
    )

    cache.set(
        "payments",
        [{"id": "eng-01"}],
    )

    assert cache.get("payments") is not None

    cache.invalidate()

    assert cache.get("payments") is None
    assert len(cache) == 0


def test_invalid_ttl_is_rejected():
    with pytest.raises(ValueError):
        TTLCache(ttl_seconds=0)


def test_corpus_fingerprint_is_order_independent():
    corpus_a = [
        {
            "id": "eng-01",
            "domain": "payments",
        },
        {
            "id": "eng-02",
            "domain": "reporting",
        },
    ]

    corpus_b = [
        {
            "id": "eng-02",
            "domain": "reporting",
        },
        {
            "id": "eng-01",
            "domain": "payments",
        },
    ]

    assert (
        corpus_fingerprint(corpus_a)
        == corpus_fingerprint(corpus_b)
    )


def test_corpus_change_changes_fingerprint():
    original = [
        {
            "id": "eng-01",
            "domain": "payments",
        }
    ]

    changed = [
        {
            "id": "eng-01",
            "domain": "core banking",
        }
    ]

    assert (
        corpus_fingerprint(original)
        != corpus_fingerprint(changed)
    )