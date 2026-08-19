"""
READER API — CF-81 (Week 5 "expose", taken over from Çağrı)

Wraps the existing Reader logic in a small HTTP service. The logic itself
is untouched (the migration plan says: "logic unchanged — just callable").

    python -m reader.api                     # serve on :8001 — docs at /docs

    POST /extract   multipart PDF -> Engagement Record JSON
    GET  /health    liveness + which extraction paths are available

Vault owns :8000, so the Reader takes :8001.
"""
import os
import shutil
import tempfile

from reader.reader import (
    ExtractionError, extract_record, extract_text, _locate_tesseract,
)

READER_VERSION = "0.1.0"


def _ocr_available():
    """Can the OCR fallback actually run on this machine?"""
    tesseract = _locate_tesseract() is not None or shutil.which("tesseract")
    poppler = (shutil.which("pdftoppm") or shutil.which("pdfinfo")
               or os.environ.get("POPPLER_PATH"))
    return bool(tesseract) and bool(poppler)


def create_app():
    from fastapi import FastAPI, HTTPException, UploadFile

    app = FastAPI(
        title="Reader — document extraction service",
        description=(
            "Turns an engagement document (PDF) into an Engagement Record. "
            "CF-81: the Reader prototype exposed as an HTTP service."
        ),
        version=READER_VERSION,
    )

    @app.get("/health")
    def health():
        """
        Liveness for the service mesh (CF-81).

        Also reports whether the OCR fallback is usable here, because a
        Reader without OCR can still handle text-layer PDFs — degraded,
        not dead.
        """
        return {
            "status": "ok",
            "service": "reader",
            "version": READER_VERSION,
            "ocr_available": _ocr_available(),
        }

    @app.post("/extract")
    def extract(document: UploadFile):
        """
        Document -> Engagement Record.

        The uploaded PDF is written to a temp file because the extraction
        stack (pdfplumber / Poppler) works on paths, not byte streams.
        Bad input (empty, corrupt, blank scan) is the caller's problem and
        comes back as a clear 422 — never a 500. See spec section 6.
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
