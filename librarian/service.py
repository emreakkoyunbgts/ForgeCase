import os
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from librarian.librarian import search as librarian_search
from librarian.multi_requirement import evaluate_rfp_requirements

import threading
from librarian.cache import (
    TTLCache,
    corpus_fingerprint,
)

VAULT_URL = os.getenv(
    "VAULT_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

VAULT_PAGE_SIZE = 50
VAULT_MAX_RETRIES = 2
VAULT_TIMEOUT_SECONDS = 5

SEARCH_CACHE_TTL_SECONDS = float(
    os.getenv(
        "LIBRARIAN_SEARCH_CACHE_TTL_SECONDS",
        "60",
    )
)

SEARCH_CACHE = TTLCache(
    ttl_seconds=SEARCH_CACHE_TTL_SECONDS,
)

_CACHE_STATE_LOCK = threading.Lock()
_LAST_CORPUS_FINGERPRINT = None


class MatchRequest(BaseModel):
    rfp_text: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    strategy: Literal["dense", "hybrid"] = "hybrid"
    min_dense_score: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
    )


def vault_headers():
    """
    Add Vault authentication when CASEFORGE_TOKEN is configured.
    """
    token = os.getenv("CASEFORGE_TOKEN")

    if not token:
        return {}

    return {
        "Authorization": f"Bearer {token}",
    }


def fetch_vault_page(offset: int):
    """
    Fetch one page from Vault.

    A failed page is retried before an error is returned.
    """

    last_error = None

    for _ in range(VAULT_MAX_RETRIES + 1):
        try:
            response = requests.get(
                f"{VAULT_URL}/engagements",
                params={
                    "limit": VAULT_PAGE_SIZE,
                    "offset": offset,
                },
                headers=vault_headers(),
                timeout=VAULT_TIMEOUT_SECONDS,
            )

            response.raise_for_status()

        except (
            requests.ConnectionError,
            requests.Timeout,
        ) as exc:
            last_error = exc
            continue

        except requests.HTTPError as exc:
            # Retry server-side Vault failures.
            if (
                exc.response is not None
                and exc.response.status_code >= 500
            ):
                last_error = exc
                continue

            # A 4xx is not likely to succeed simply by retrying.
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "vault_error",
                    "offset": offset,
                    "message": str(exc),
                },
            )

        try:
            data = response.json()

        except ValueError:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "invalid_vault_response",
                    "offset": offset,
                    "message": "Vault did not return valid JSON.",
                },
            )

        if not isinstance(data, dict):
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "invalid_vault_response",
                    "offset": offset,
                    "message": "Vault response must be an object.",
                },
            )

        items = data.get("items")
        total = data.get("total")

        if not isinstance(items, list):
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "invalid_vault_response",
                    "offset": offset,
                    "message": "Vault response must contain an items list.",
                },
            )

        if not isinstance(total, int) or total < 0:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "invalid_vault_response",
                    "offset": offset,
                    "message": "Vault response must contain a valid total.",
                },
            )

        return data

    raise HTTPException(
        status_code=503,
        detail={
            "error": "vault_page_failed",
            "offset": offset,
            "message": str(last_error),
        },
    )


def fetch_all_records_from_vault():
    """
    Fetch every engagement from Vault using limit/offset pagination.
    """

    records = []
    offset = 0

    while True:
        page = fetch_vault_page(offset)

        items = page["items"]
        total = page["total"]

        records.extend(items)

        if len(records) >= total:
            break

        if not items:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "incomplete_vault_response",
                    "offset": offset,
                    "message": (
                        "Vault returned an empty page "
                        "before all records were fetched."
                    ),
                },
            )

        offset += len(items)

    return records

def sync_search_cache_with_corpus(
    corpus: list[dict],
) -> str:
    """
    Invalidate cached search results when the Vault
    corpus changes.

    Returns the current corpus fingerprint.
    """

    global _LAST_CORPUS_FINGERPRINT

    fingerprint = corpus_fingerprint(corpus)

    with _CACHE_STATE_LOCK:
        if _LAST_CORPUS_FINGERPRINT is None:
            _LAST_CORPUS_FINGERPRINT = fingerprint

        elif (
            fingerprint
            != _LAST_CORPUS_FINGERPRINT
        ):
            SEARCH_CACHE.invalidate()

            _LAST_CORPUS_FINGERPRINT = (
                fingerprint
            )

    return fingerprint

def create_app() -> FastAPI:
    app = FastAPI(
        title="CaseForge Librarian",
        version="0.1.0",
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "librarian",
        }

    @app.get("/search")
    def search_endpoint(
        q: str = Query(..., min_length=1),
        top: int = Query(3, ge=1, le=20),
        strategy: Literal["dense", "hybrid"] = "hybrid",
    ):
        corpus = fetch_all_records_from_vault()

        fingerprint = (
            sync_search_cache_with_corpus(
                corpus
            )
        )

        cache_key = (
            q,
            top,
            strategy,
            fingerprint,
        )

        cached_matches = SEARCH_CACHE.get(
            cache_key
        )

        if cached_matches is not None:
            matches = cached_matches

        else:
            matches = librarian_search(
                q,
                corpus,
                top_k=top,
                strategy=strategy,
            )

            SEARCH_CACHE.set(
                cache_key,
                matches,
            )

        return {
            "query": q,
            "strategy": strategy,
            "matches": matches,
        }

    @app.post("/match")
    def match_endpoint(body: MatchRequest):
        corpus = fetch_all_records_from_vault()

        return evaluate_rfp_requirements(
            rfp_text=body.rfp_text,
            corpus=corpus,
            top_k=body.top_k,
            strategy=body.strategy,
            min_dense_score=body.min_dense_score,
        )

    return app


app = create_app()