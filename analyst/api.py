import os

import requests
from common.services import request_headers, install_http_middleware
from fastapi import FastAPI, HTTPException

from analyst.analyst import profile, coverage_gaps


app = FastAPI(
    title="CaseForge Analyst API",
    version="1.0.0",
)
install_http_middleware(app)

VAULT_URL = os.getenv(
    "VAULT_URL",
    "http://127.0.0.1:8000",
)


def fetch_records(offset=0):
    """
    Fetch engagement records from the Vault service.
    """

    headers = request_headers()

    vault_token = os.getenv("CASEFORGE_TOKEN")

    if vault_token and not headers.get("Authorization"):
        headers["Authorization"] = f"Bearer {vault_token}"

    try:
        response = requests.get(
            f"{VAULT_URL}/engagements",
            headers=headers,
            params={"limit": 100, "offset": offset},
            timeout=5,
            allow_redirects=False,
        )

        response.raise_for_status()

    except requests.Timeout:
        raise HTTPException(504, {"error": "vault_timeout"}) from None
    except requests.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "vault_unavailable",
                "message": str(exc),
            },
        )

    except requests.HTTPError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None and exc.response.status_code in {401,403,404,503,504} else 502,
            detail={
                "error": "vault_error",
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
                "message": "Vault did not return valid JSON.",
            },
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "error": "invalid_vault_response",
                "message": "Vault response must be an object.",
            },
        )

    records = data.get("items")

    if not isinstance(records, list):
        raise HTTPException(
            status_code=502,
            detail={
                "error": "invalid_vault_response",
                "message": "Vault response must contain an items list.",
            },
        )

    total = data.get("total")
    if type(total) is not int or total < offset + len(records):
        raise HTTPException(502, {"error": "invalid_vault_response"})
    if offset + len(records) < total:
        if not records:
            raise HTTPException(502, {"error": "incomplete_vault_response"})
        records = records + fetch_records(offset + len(records))
    return records


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "analyst",
    }


@app.get("/coverage")
def coverage():
    corpus = fetch_records()

    return profile(corpus)


@app.get("/gaps")
def gaps():
    corpus = fetch_records()

    gap_list = coverage_gaps(
        corpus,
        show_chart=False,
    )

    return {
        "total_gaps": len(gap_list),
        "gaps": gap_list,
    }
