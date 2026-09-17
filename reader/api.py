"""Reader HTTP API: structured text-layer PDF -> record -> Vault HTTP."""
import os
import tempfile
import time
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile

from common.services import install_http_middleware, install_request_validation_handler, request_headers
from reader.extraction import extract_document
from reader.reader import ExtractionError

READER_VERSION = "1.0.0"
VAULT_URL = os.getenv("VAULT_URL", "http://127.0.0.1:8000").rstrip("/")
VAULT_TIMEOUT_SECONDS = 5
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _vault_headers():
    return request_headers()


def _confirm_record(record, headers):
    try:
        response = requests.get(
            f"{VAULT_URL}/engagements/{quote(record['id'], safe='')}",
            headers=headers, timeout=VAULT_TIMEOUT_SECONDS, allow_redirects=False,
        )
        if response.status_code == 404:
            return "absent"
        if response.status_code != 200:
            return "unavailable"
        existing = response.json()
        # Vault can add storage metadata. All original submitted facts must match.
        return "same" if isinstance(existing, dict) and all(existing.get(k) == v for k, v in record.items()) else "conflict"
    except (requests.RequestException, ValueError):
        return "unavailable"


def store_in_vault(record):
    headers = _vault_headers()
    headers.setdefault("Idempotency-Key", __import__("uuid").uuid4().hex)
    for attempt in range(2):
        try:
            response = requests.post(f"{VAULT_URL}/engagements", json=record,
                                     headers=headers, timeout=VAULT_TIMEOUT_SECONDS,
                                     allow_redirects=False)
            if response.status_code == 201:
                return True, "created"
            if response.status_code in {401, 403}:
                return False, "vault rejected authorization"
            if response.status_code != 409 and response.status_code < 500:
                return False, f"vault returned {response.status_code}"
        except requests.RequestException:
            pass
        confirmed = _confirm_record(record, headers)
        if confirmed == "same":
            return True, "existing matching record confirmed"
        if confirmed == "conflict":
            return False, "conflict: this engagement ID contains different source facts"
        if confirmed == "absent" and attempt == 0:
            time.sleep(0.5)
            continue
        return False, "vault unreachable or storage could not be confirmed"
    return False, "vault storage could not be confirmed"


def create_app():
    app = FastAPI(title="CaseForge Reader", version=READER_VERSION,
                  description="Extracts labelled text-layer closeout PDFs. Scans and unstructured PDFs return 422.")
    install_http_middleware(app)
    install_request_validation_handler(app)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "reader", "version": READER_VERSION,
                "ocr_available": False, "supported_input": "structured-text-layer-pdf",
                "vault_url": VAULT_URL}

    @app.post("/extract")
    def extract(document: UploadFile, response: Response, store: bool = Query(True)):
        source_name = (document.filename or "upload.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                size = 0
                while chunk := document.file.read(65536):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "PDF exceeds the 20 MiB limit")
                    tmp.write(chunk)
            try:
                record = extract_document(tmp_path, source_name)
            except ExtractionError as exc:
                raise HTTPException(422, str(exc)) from None
            stored, detail = store_in_vault(record) if store else (False, "skipped (store=false)")
            response.headers["X-Vault-Stored"] = str(stored).lower()
            response.headers["X-Vault-Detail"] = detail
            return record
        finally:
            if tmp_path is not None:
                os.unlink(tmp_path)

    return app


def serve():
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8003)


if __name__ == "__main__":
    serve()
