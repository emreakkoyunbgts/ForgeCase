"""CF-100: verify drafts against authoritative Vault records over HTTP."""

import logging

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
from verifier.semantic import deterministic_problems, get_semantic_checker
from common.drafts import normalize_draft
from common.services import install_http_middleware

logger = logging.getLogger(__name__)
app = FastAPI(title="CaseForge Verifier", version="1.0.0")
install_http_middleware(app)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Preserve FastAPI's error envelope without echoing drafts or deeply nested input.
    errors = [
        {key: error[key] for key in ("loc", "msg", "type")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


async def _verify_draft(record_id, draft, request, client, checker, language="en"):
    record = await get_record_from_vault(
        record_id,
        client,
        request.state.correlation_id,
        request.headers.get("Authorization"),
    )
    draft = normalize_draft(draft, record_id, language)
    problems = deterministic_problems(draft, record, language)
    if not problems:
        problems.extend(await checker(draft, record, language, request.state.correlation_id))
    report = {"engagement_id": record_id, "verdict": "BLOCK" if problems else "PASS", "problems": problems}
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
    checker=Depends(get_semantic_checker),
):
    """Return PASS/BLOCK and problems using the requested source from Vault."""
    return await _verify_draft(payload.record_id, payload.draft, request, client, checker, payload.language)


@app.post("/verify/{record_id}", response_model=VerificationReport, deprecated=True)
async def verify_record_id(
    record_id: str,
    payload: LegacyVerifyRequest,
    request: Request,
    client: httpx.AsyncClient = Depends(get_vault_client),
    checker=Depends(get_semantic_checker),
):
    """Compatibility for Console/Publisher; submitted record facts are never trusted."""
    try:
        validate_record_id(record_id)
        validate_draft_identity(payload.mcs, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if payload.record.get("id") != record_id:
        raise HTTPException(status_code=422, detail="record.id must match the path record_id")
    language = payload.mcs.get("language", "en")
    try:
        canonical = normalize_draft(payload.mcs, record_id, language)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return await _verify_draft(record_id, canonical, request, client, checker, language)


@app.get("/health")
async def health_check():
    """Liveness only; source availability is checked by each verification request."""
    return {"status": "ok"}
