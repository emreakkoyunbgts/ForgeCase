import os

import requests
from fastapi import FastAPI, HTTPException

from analyst.analyst import profile, coverage_gaps


app = FastAPI(
    title="CaseForge Analyst API",
    version="1.0.0",
)

VAULT_URL = os.getenv(
    "VAULT_URL",
    "http://127.0.0.1:8001",
)


def fetch_records():
    """
    Fetch all engagement records from the Vault service.
    """

    try:
        response = requests.get(
            f"{VAULT_URL}/records",
            timeout=5,
        )

        response.raise_for_status()

    except (requests.ConnectionError, requests.Timeout) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "vault_unavailable",
                "message": str(exc),
            },
        )

    except requests.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "vault_error",
                "message": str(exc),
            },
        )

    try:
        records = response.json()

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "invalid_vault_response",
                "message": "Vault did not return valid JSON.",
            },
        )

    if not isinstance(records, list):
        raise HTTPException(
            status_code=502,
            detail={
                "error": "invalid_vault_response",
                "message": "Vault response must be a list of records.",
            },
        )

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