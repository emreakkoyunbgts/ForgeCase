"""Authoritative Vault reads shared by service adapters."""
import os
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from common.contract import REQUIRED_FIELDS

VAULT_TIMEOUT_SECONDS = 5.0


async def get_vault_client():
    async with httpx.AsyncClient() as client:
        yield client


def validate_source(record, record_id):
    valid = isinstance(record, dict) and all(field in record for field in REQUIRED_FIELDS)
    if valid:
        valid = (
            record['id'] == record_id
            and all(isinstance(record[key], str) and bool(record[key].strip())
                    for key in ('client', 'client_type', 'domain', 'region'))
            and all(isinstance(record[key], str) for key in ('challenge', 'solution'))
            and isinstance(record['may_be_named'], bool)
            and isinstance(record['technologies'], list)
            and all(isinstance(item, str) for item in record['technologies'])
            and isinstance(record['outcomes'], list)
        )
    if valid:
        valid = all(isinstance(item, dict)
                    and all(isinstance(item.get(key), str) and bool(item[key].strip())
                            for key in ('metric', 'source_ref'))
                    for item in record['outcomes'])
    if valid and 'supports_qualitative_claims' in record:
        valid = isinstance(record['supports_qualitative_claims'], bool)
    if not valid:
        raise HTTPException(502, 'Vault returned an invalid source record')
    return record


async def get_record_from_vault(record_id, client, correlation_id, authorization=None):
    headers = {'X-Correlation-ID': correlation_id}
    if authorization is not None:
        headers['Authorization'] = authorization
    elif token := os.environ.get('CASEFORGE_TOKEN'):
        if any(not 32 <= ord(char) < 127 for char in token):
            raise HTTPException(503, 'Vault authentication is not configured correctly')
        headers['Authorization'] = f'Bearer {token}'
    url = os.getenv('VAULT_URL', 'http://127.0.0.1:8000').rstrip('/')
    try:
        response = await client.get(
            f'{url}/engagements/{quote(record_id, safe="")}', headers=headers,
            timeout=VAULT_TIMEOUT_SECONDS, follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise HTTPException(504, 'Vault request timed out') from None
    except httpx.RequestError:
        raise HTTPException(503, 'Vault is unavailable') from None
    if response.status_code == 404:
        raise HTTPException(404, 'Source record was not found in Vault')
    if response.status_code in {401, 403}:
        raise HTTPException(response.status_code, 'Vault denied access to the source record',
                            headers={'WWW-Authenticate': 'Bearer'} if response.status_code == 401 else None)
    if response.status_code != 200:
        raise HTTPException(502, 'Vault returned an unsuccessful response')
    try:
        record = response.json()
    except ValueError:
        raise HTTPException(502, 'Vault returned invalid JSON') from None
    return validate_source(record, record_id)
