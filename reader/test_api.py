"""Tests for the Reader HTTP service (CF-81). Bad input must be a clear 422."""
import io
import os

from fastapi.testclient import TestClient

from reader.api import create_app

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
EDGE = os.path.join(REPO, "caseforge-testdata", "documents", "edge_cases")


def _post_pdf(client, path):
    with open(path, "rb") as f:
        return client.post(
            "/extract",
            files={"document": (os.path.basename(path), f, "application/pdf")},
        )


def test_health_reports_service_and_ocr_flag():
    """/health says who it is and whether the OCR fallback is usable."""
    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "reader"
    assert isinstance(body["ocr_available"], bool)


def test_extract_returns_a_record_from_a_real_pdf():
    """A text-layer PDF comes back as a record with the required fields."""
    client = TestClient(create_app())
    response = _post_pdf(
        client, os.path.join(FIXTURES, "two_column_closeout.pdf")
    )
    assert response.status_code == 200
    record = response.json()
    for field in ["id", "client", "client_type", "may_be_named", "outcomes"]:
        assert field in record


def test_extract_empty_file_returns_422():
    """An empty upload is the caller's problem — 422, not a 500."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_extract_corrupt_file_returns_422():
    """Garbage bytes that are not a PDF get a clear 422."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("corrupt.pdf",
                            io.BytesIO(b"this is not a pdf at all"),
                            "application/pdf")},
    )
    assert response.status_code == 422


def test_error_message_names_the_uploaded_file_not_a_temp_path():
    """The caller sent 'empty.pdf'; the error must talk about that name,
    not about whatever temp file the server used internally."""
    client = TestClient(create_app())
    response = client.post(
        "/extract",
        files={"document": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    detail = response.json()["detail"]
    assert "empty.pdf" in detail
    assert "Temp" not in detail and "tmp" not in detail
