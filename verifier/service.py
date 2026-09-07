"""Fetch authoritative source records over HTTP, without a local fallback."""

import os
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from common.contract import REQUIRED_FIELDS

VAULT_TIMEOUT_SECONDS = 5.0


async def get_vault_client():
    async with httpx.AsyncClient() as client:
        yield client


def _validate_source(record, record_id):
    valid = (
        isinstance(record, dict)
        and all(field in record for field in REQUIRED_FIELDS)
        and record["id"] == record_id
        and isinstance(record["client"], str)
        and bool(record["client"].strip())
        and isinstance(record["client_type"], str)
        and bool(record["client_type"].strip())
        and isinstance(record["may_be_named"], bool)
        and isinstance(record["technologies"], list)
        and isinstance(record["outcomes"], list)
    )
    if valid:
        valid = all(
            isinstance(outcome, dict)
            and isinstance(outcome.get("metric"), str)
            and bool(outcome["metric"].strip())
            and isinstance(outcome.get("source_ref"), str)
            and bool(outcome["source_ref"].strip())
            for outcome in record["outcomes"]
        )
    if valid and "supports_qualitative_claims" in record:
        valid = isinstance(record["supports_qualitative_claims"], bool)
    if not valid:
        raise HTTPException(status_code=502, detail="Vault returned an invalid source record")
    return record


async def get_record_from_vault(record_id, client, correlation_id, authorization=None):
    headers = {"X-Correlation-ID": correlation_id}
    if authorization is not None:
        headers["Authorization"] = authorization
    elif token := os.environ.get("CASEFORGE_TOKEN"):
        if any(not 32 <= ord(char) < 127 for char in token):
            raise HTTPException(
                status_code=503, detail="Vault authentication is not configured correctly"
            )
        headers["Authorization"] = f"Bearer {token}"

    vault_url = os.environ.get("VAULT_URL", "http://localhost:8000").rstrip("/")
    url = f"{vault_url}/engagements/{quote(record_id, safe='')}"
    try:
        response = await client.get(
            url, headers=headers, timeout=VAULT_TIMEOUT_SECONDS, follow_redirects=False
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Vault request timed out") from None
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Vault is unavailable") from None

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Source record was not found in Vault")
    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=response.status_code,
            detail="Vault denied access to the source record",
            headers={"WWW-Authenticate": "Bearer"} if response.status_code == 401 else None,
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Vault returned an unsuccessful response")
    try:
        record = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Vault returned invalid JSON") from None
    return _validate_source(record, record_id)
