"""
PUBLISHER SERVICE — exposes publisher.py over HTTP (FastAPI version).

    uvicorn publisher.service:app --port 8005

POST /publish   {"record_id": "eng-01"}  -> branded document path
GET  /health    -> {"status": "ok"}

CF-91: before publishing, calls Verifier's /verify. If it returns BLOCK,
publishing is refused and the reasons are returned to the caller.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.contract import load_corpus
from common.services import VAULT_URL, GENERATOR_URL, VERIFIER_URL, call_service
from publisher.publisher import render_docx, TEMPLATE

app = FastAPI()


class PublishRequest(BaseModel):
    record_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/publish")
def publish(req: PublishRequest):
    record_id = req.record_id

    try:
        response = call_service("GET", f"{VAULT_URL}/records/{record_id}")
        record = response.json()
    except Exception:
        corpus = load_corpus()
        record = next((r for r in corpus if r["id"] == record_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail=f"no such record: {record_id}")

    case_study = {
        "engagement_id": record_id,
        "title": record.get("id", "[MISSING]"),
        "sections": {
            "context": record.get("client", "[MISSING]") if record.get("may_be_named") else "[REDACTED]",
            "challenge": record.get("challenge", "[MISSING]"),
            "approach": record.get("solution", "[MISSING]"),
            "technology": ", ".join(record.get("technologies", [])),
            "outcomes": str(record.get("outcomes", "[MISSING]")),
        },
    }

    # CF-91: the Verifier gate — call it over HTTP before publishing.
    try:
        mcs_response = call_service(
            "POST", f"{GENERATOR_URL}/generator/mcs",
            json=record,
        )
        mcs = mcs_response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"generator unreachable: {e}")

    try:
        verify_response = call_service(
            "POST", f"{VERIFIER_URL}/verify/{record_id}",
            json={"record": record, "mcs": mcs},
        )
        verdict = verify_response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"verifier unreachable: {e}")

    if verdict["verdict"] == "BLOCK":
        raise HTTPException(
            status_code=422,
            detail={
                "message": "publish refused — verifier blocked this draft",
                "problems": verdict["problems"],
            },
        )

    out_path = f"out/{record_id}.docx"
    written = render_docx(case_study, TEMPLATE, out_path)

    return {"path": str(written)}