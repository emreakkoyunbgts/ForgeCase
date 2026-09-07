"""CF-100: verify drafts against authoritative Vault records over HTTP."""

import logging
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from verifier.models import (
    LegacyVerifyRequest,
    VerificationReport,
    VerifyRequest,
    validate_draft_identity,
    validate_record_id,
)
from verifier.service import get_record_from_vault, get_vault_client
from verifier.verifier import verify

logger = logging.getLogger(__name__)
app = FastAPI(title="CaseForge Verifier", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Preserve FastAPI's error envelope without echoing drafts or deeply nested input.
    errors = [
        {key: error[key] for key in ("loc", "msg", "type")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    invalid_headers = [
        name for name in ("X-Correlation-ID", "Authorization")
        if any(not 32 <= ord(char) < 127 for char in request.headers.get(name, ""))
    ]
    incoming_id = request.headers.get("X-Correlation-ID")
    request.state.correlation_id = (
        incoming_id if incoming_id and "X-Correlation-ID" not in invalid_headers
        else str(uuid.uuid4())
    )
    if invalid_headers:
        response = JSONResponse(
            status_code=400,
            content={"detail": "Invalid HTTP tracing or authorization header"},
        )
    else:
        response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


async def _verify_draft(record_id, draft, request, client):
    record = await get_record_from_vault(
        record_id,
        client,
        request.state.correlation_id,
        request.headers.get("Authorization"),
    )
    report = verify(draft, record)
    logger.info(
        "Verification completed for record ID %s with verdict %s (correlation_id=%s)",
        record["id"], report["verdict"], request.state.correlation_id,
    )
    return report


@app.post("/verify", response_model=VerificationReport)
async def verify_draft(
    payload: VerifyRequest,
    request: Request,
    client: httpx.AsyncClient = Depends(get_vault_client),
):
    """Return PASS/BLOCK and problems using the requested source from Vault."""
    return await _verify_draft(payload.record_id, payload.draft, request, client)


@app.post("/verify/{record_id}", response_model=VerificationReport, deprecated=True)
async def verify_record_id(
    record_id: str,
    payload: LegacyVerifyRequest,
    request: Request,
    client: httpx.AsyncClient = Depends(get_vault_client),
):
    """Compatibility for Console/Publisher; submitted record facts are never trusted."""
    try:
        validate_record_id(record_id)
        validate_draft_identity(payload.mcs, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if payload.record.get("id") != record_id:
        raise HTTPException(status_code=422, detail="record.id must match the path record_id")
    return await _verify_draft(record_id, payload.mcs, request, client)


@app.get("/health")
async def health_check():
    """Liveness only; source availability is checked by each verification request."""
    return {"status": "ok"}
