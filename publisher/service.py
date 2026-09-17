"""Publish only the exact independently verified draft; deliver artifacts by HTTP."""
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, ValidationError

from common.drafts import Language, display_case_study, normalize_draft, validate_record_id
from common.services import call_service, install_http_middleware, request_headers, response_json
from common.source import validate_source
from common.quantities import name_key
from publisher.assets import TEMPLATE, ensure_assets
from publisher.publisher import PDF_LAYOUTS, prepare_display_values, render_docx, render_pdf


@asynccontextmanager
async def lifespan(app):
    ensure_assets()
    yield


app = FastAPI(title="CaseForge Publisher", version="1.1.0", lifespan=lifespan)
install_http_middleware(app)


def artifact_root():
    return Path(os.getenv("CASEFORGE_ARTIFACT_DIR", "out/artifacts")).resolve()


def authorized(request: Request):
    token = os.getenv("CASEFORGE_TOKEN")
    if token and not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + token):
        raise HTTPException(401, "Publisher requires a valid service token",
                            headers={"WWW-Authenticate": "Bearer"})


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1, max_length=200)
    draft: dict
    language: Language = "en"
    format: Literal["docx", "pdf"] = "docx"
    layout: Literal["full-case-study", "one-pager", "single-slide"] = "full-case-study"
    _record_id = field_validator("record_id")(validate_record_id)

    @model_validator(mode="after")
    def validate_content(self):
        self.draft = normalize_draft(self.draft, self.record_id, self.language)
        if self.format == "docx" and self.layout != "full-case-study":
            raise ValueError("DOCX supports only full-case-study layout")
        return self


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engagement_id: str
    verdict: Literal["PASS", "BLOCK"]
    problems: list[dict]


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=422, content={"detail": [
        {key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()
    ]})


@app.get("/health")
def health():
    ensure_assets()
    return {"status": "ok", "service": "publisher"}


@app.post("/publish", status_code=201, dependencies=[Depends(authorized)])
def publish(req: PublishRequest):
    vault_url = os.getenv("VAULT_URL", "http://127.0.0.1:8000").rstrip("/")
    verifier_url = os.getenv("VERIFIER_URL", "http://127.0.0.1:8004").rstrip("/")
    headers = request_headers()
    record = validate_source(response_json(call_service(
        "GET", f"{vault_url}/engagements/{quote(req.record_id, safe='')}",
        headers=headers, timeout=5,
    )), req.record_id)
    flat = display_case_study(req.draft, req.record_id, req.language)
    if record['may_be_named'] is not True:
        visible_metadata = [req.record_id, str(record.get('completed_at') or ''),
                            *(item['source_ref'] for item in req.draft['citations'])]
        if any(name_key(record['client']) in name_key(value) for value in visible_metadata):
            raise HTTPException(422, 'Publication blocked: visible provenance discloses an unnamed client')
    prepared = prepare_display_values(flat, record)
    # Include formatting defaults before the final gate, never after it.
    final = {
        **flat, "title": prepared["title"],
        "sections": {"context": prepared["client_type"],
                     **{name: prepared[name] for name in ("challenge", "approach", "technology", "outcomes")}},
    }
    result = response_json(call_service(
        "POST", verifier_url + "/verify",
        json={"record_id": req.record_id, "draft": final, "language": req.language},
        headers=headers, timeout=75,
    ))
    try:
        report = Report.model_validate(result)
    except ValidationError:
        raise HTTPException(502, "Verifier returned an invalid gate response") from None
    if report.engagement_id != req.record_id or (report.verdict == "PASS" and report.problems):
        raise HTTPException(502, "Verifier response does not authorize this draft")
    if report.verdict != "PASS":
        raise HTTPException(422, {"message": "Publication blocked by Verifier", "problems": report.problems})
    ensure_assets()
    artifact_id = str(uuid4())
    directory = artifact_root() / artifact_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise HTTPException(503, 'Publisher artifact storage is unavailable') from None
    output = directory / ("document." + req.format)
    try:
        if req.format == "docx":
            render_docx(final, TEMPLATE, output, source_record=record,
                        prepared_display=prepared, language=req.language)
        else:
            render_pdf(final, output, layout=req.layout, source_record=record,
                       prepared_display=prepared, language=req.language)
        metadata = {
            "artifact_id": artifact_id, "filename": req.record_id + "." + req.format,
            "media_type": ("application/pdf" if req.format == "pdf" else
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "download_url": f"/artifacts/{artifact_id}/download",
            "provenance_url": f"/artifacts/{artifact_id}/provenance",
        }
        (directory / "metadata.json").write_text(
            json.dumps({**metadata, "format": req.format}, ensure_ascii=False), encoding="utf-8")
        return metadata
    except Exception:
        for name in (output.name, output.name + ".provenance.json", "metadata.json"):
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
        raise HTTPException(503, "Publisher could not render this document") from None


def find_artifact(artifact_id):
    try:
        canonical = str(UUID(artifact_id))
    except ValueError:
        raise HTTPException(404, "Artifact not found") from None
    directory = artifact_root() / canonical
    try:
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if metadata["format"] not in {"pdf", "docx"}:
            raise ValueError()
    except (OSError, ValueError, KeyError):
        raise HTTPException(404, "Artifact not found") from None
    return directory, metadata


@app.get("/artifacts/{artifact_id}/download", dependencies=[Depends(authorized)])
def download(artifact_id: str):
    directory, metadata = find_artifact(artifact_id)
    path = directory / ("document." + metadata["format"])
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, media_type=metadata["media_type"], filename=metadata["filename"])


@app.get("/artifacts/{artifact_id}/provenance", dependencies=[Depends(authorized)])
def provenance(artifact_id: str):
    directory, metadata = find_artifact(artifact_id)
    path = directory / ("document." + metadata["format"] + ".provenance.json")
    if not path.is_file():
        raise HTTPException(404, "Artifact provenance not found")
    return FileResponse(path, media_type="application/json", filename="provenance.json")
