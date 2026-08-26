"""
READER API — CF-81 / CF-82 (Week 5 "expose", Week 6 "wire")

Wraps the existing Reader logic in a small HTTP service. The extraction
logic itself is untouched (the migration plan: "logic unchanged — just
callable"). CF-82 adds the first real service-to-service call: the record
we extract is written straight into the Vault over HTTP.

    python -m reader.api                     # serve on :8001 — docs at /docs

    POST /extract   multipart PDF -> Engagement Record JSON (+ stored in Vault)
    GET  /health    liveness, OCR availability, where the Vault is

Vault owns :8000, so the Reader takes :8001.
"""
import os
import shutil
import sys
import tempfile

import requests

from reader.reader import (
    ExtractionError, extract_record, extract_text, _locate_tesseract,
)

READER_VERSION = "0.2.0"

# Where the Vault lives, and how long we are willing to wait for it. The
# URL is configurable because in the mesh it will not be localhost forever.
VAULT_URL = os.environ.get("VAULT_URL", "http://127.0.0.1:8000")
VAULT_TIMEOUT_SECONDS = 5


def _ocr_available():
    """Can the OCR fallback actually run on this machine?"""
    tesseract = _locate_tesseract() is not None or shutil.which("tesseract")
    poppler = (shutil.which("pdftoppm") or shutil.which("pdfinfo")
               or os.environ.get("POPPLER_PATH"))
    return bool(tesseract) and bool(poppler)


def _vault_headers():
    """Auth header for the Vault, when a service token is configured (CF-85)."""
    token = os.environ.get("CASEFORGE_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def store_in_vault(record):
    """
    Write one record into the Vault over HTTP (CF-82).

    Returns (stored, detail) and never raises: if the Vault is down the
    extraction still succeeded, and the caller should get its record with
    an honest note rather than a failed request. The migration rules say a
    caller must survive its callee being down.

    Deliberately no retry. A POST is not idempotent — a timed-out request
    may well have been stored, so retrying risks a duplicate record. Safe
    retries arrive with the Idempotency-Key work in Week 7.
    """
    try:
        response = requests.post(
            f"{VAULT_URL}/engagements",
            json=record,
            headers=_vault_headers(),
            timeout=VAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"[reader] vault unreachable at {VAULT_URL}: {exc}",
              file=sys.stderr)
        return False, f"vault unreachable: {exc}"

    if response.status_code == 201:
        return True, "created"
    if response.status_code == 409:
        # Already in the Vault. Not our failure, and not worth an error:
        # the record the caller asked about is stored either way.
        return False, "already exists in the vault"
    if response.status_code == 401:
        return False, "vault rejected our token (CASEFORGE_TOKEN)"
    print(f"[reader] vault refused the record: "
          f"{response.status_code} {response.text[:200]}", file=sys.stderr)
    return False, f"vault returned {response.status_code}"


def create_app():
    from fastapi import FastAPI, HTTPException, Query, Response, UploadFile

    app = FastAPI(
        title="Reader — document extraction service",
        description=(
            "Turns an engagement document (PDF) into an Engagement Record. "
            "CF-81: the Reader prototype exposed as an HTTP service. "
            "CF-82: extracted records are written into the Vault over HTTP."
        ),
        version=READER_VERSION,
    )

    @app.get("/health")
    def health():
        """
        Liveness for the service mesh (CF-81).

        Also reports whether the OCR fallback is usable here, because a
        Reader without OCR can still handle text-layer PDFs — degraded,
        not dead. Since CF-82 we depend on the Vault, so we name it here;
        we do not call its health, or one Vault outage would make every
        service in the mesh look unhealthy.
        """
        return {
            "status": "ok",
            "service": "reader",
            "version": READER_VERSION,
            "ocr_available": _ocr_available(),
            "vault_url": VAULT_URL,
        }

    @app.post("/extract")
    def extract(
        document: UploadFile,
        response: Response,
        store: bool = Query(
            True,
            description="CF-82: also write the record into the Vault. "
                        "Set false to extract without storing.",
        ),
    ):
        """
        Document -> Engagement Record, and (CF-82) into the Vault.

        The uploaded PDF is written to a temp file because the extraction
        stack (pdfplumber / Poppler) works on paths, not byte streams.
        Bad input (empty, corrupt, blank scan) is the caller's problem and
        comes back as a clear 422 — never a 500. See spec section 6.

        The response body stays the record itself, so callers written
        against CF-81 keep working. What happened with the Vault is
        reported in the X-Vault-Stored / X-Vault-Detail headers: a Vault
        outage degrades this call, it does not fail it.
        """
        suffix = os.path.splitext(document.filename or "upload.pdf")[1] or ".pdf"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            shutil.copyfileobj(document.file, tmp)
            tmp.close()
            try:
                text = extract_text(tmp.name)
            except ExtractionError as exc:
                # The message contains the temp path, which means nothing
                # to the caller — swap it for the original filename.
                detail = str(exc).replace(tmp.name, document.filename or "upload")
                raise HTTPException(status_code=422, detail=detail)
            record = extract_record(text, document.filename or "upload")
            if record is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"could not extract a record from "
                           f"{document.filename or 'the document'}",
                )
            if store:
                stored, detail = store_in_vault(record)
                response.headers["X-Vault-Stored"] = str(stored).lower()
                response.headers["X-Vault-Detail"] = detail
            else:
                response.headers["X-Vault-Stored"] = "false"
                response.headers["X-Vault-Detail"] = "skipped (store=false)"
            return record
        finally:
            tmp.close()
            os.unlink(tmp.name)

    return app


def serve():
    """Run the Reader API on http://127.0.0.1:8001 (docs at /docs)."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    serve()
