"""
CF-94 — Librarian search cache.

Provides:
- in-memory TTL caching
- thread-safe access
- explicit invalidation
- deterministic corpus fingerprinting
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any


class TTLCache:
    """
    Small thread-safe in-memory TTL cache.

    Cache entries automatically expire after ttl_seconds.
    """

    def __init__(
        self,
        ttl_seconds: float,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be greater than 0"
            )

        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn
        self._entries: dict[
            Hashable,
            tuple[float, Any],
        ] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable):
        """
        Return a cached value when it exists and has
        not expired.

        Returns None for a miss or expired entry.
        """

        now = self._time_fn()

        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                return None

            expires_at, value = entry

            if now >= expires_at:
                del self._entries[key]
                return None

            # Avoid callers mutating the cached object.
            return copy.deepcopy(value)

    def set(
        self,
        key: Hashable,
        value: Any,
    ) -> None:
        expires_at = (
            self._time_fn()
            + self.ttl_seconds
        )

        with self._lock:
            self._entries[key] = (
                expires_at,
                copy.deepcopy(value),
            )

    def invalidate(self) -> None:
        """Remove every cached search result."""

        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def corpus_fingerprint(
    records: list[dict],
) -> str:
    """
    Produce a stable hash representing the Vault corpus.

    If any engagement data changes, the fingerprint changes
    and Librarian can invalidate stale search results.
    """

    normalized = sorted(
        records,
        key=lambda record: str(
            record.get("id", "")
        ),
    )

    serialized = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()