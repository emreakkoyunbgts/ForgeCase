"""Live Vault representation/concurrency and Reader document boundaries."""
from copy import deepcopy
from io import BytesIO
import json
from uuid import uuid4

import pytest

from contract.fixtures.cases import SOURCE_01


def _source():
    source = deepcopy(SOURCE_01)
    source.update(id="eng-cf120-boundary-" + uuid4().hex, client="Synthetic Boundary Bank")
    return source


def _remove_if_present(mesh, record_id):
    items = mesh.request("vault", "GET", "/engagements").json()["items"]
    if any(record["id"] == record_id for record in items):
        path = "/engagements/" + record_id
        current = mesh.request("vault", "GET", path)
        deleted = mesh.request("vault", "DELETE", path, expected=204,
                               headers={"If-Match": current.headers["ETag"]})
        assert deleted.content == b""


def _pdf(source=None):
    # Synthetic input construction; no Reader/Generator code supplies the oracle.
    from reportlab.pdfgen import canvas
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    if source is None:
        pdf.showPage()
    else:
        lines = [f"Engagement ID: {source['id']}", f"Client: {source['client']}",
                 f"Client profile: {source['client_type']}", f"Domain: {source['domain']}",
                 f"Region: {source['region']}", "Duration: 11 months",
                 "1. The Challenge", source["challenge"], "2. Our Approach", source["solution"],
                 "3. Technology", ", ".join(source["technologies"]), "4. Outcomes",
                 *["- " + outcome["metric"] for outcome in source["outcomes"]]]
        pdf.setFont("Helvetica", 10)
        for index, line in enumerate(lines):
            pdf.drawString(40, 790 - index * 22, line)
    pdf.save()
    return stream.getvalue()


@pytest.mark.contract(owner="Kaan", requirement="CF-84", boundary="Client->Vault")
def test_vault_roundtrip_optional_fields_etags_history_and_delete(mesh):
    """Accepted fields survive; POST/GET/PUT ETags agree; If-Match, history and delete behave (F-01)."""
    source = _source()
    source.update(completed_at="2026-09-01", supports_qualitative_claims=True, team_size=7,
                  outcome_missing=False, extension={"unicode": "Ödeme", "review": [None, False, 1.5]})
    source["outcomes"][0]["evidence"] = {"approved": True, "page": 1}
    path = "/engagements/" + source["id"]
    try:
        created = mesh.request("vault", "POST", "/engagements", expected=201, json=source)
        assert created.json() == source and created.headers["Location"] == path
        fetched = mesh.request("vault", "GET", path)
        assert fetched.json() == source and fetched.headers["ETag"] == created.headers["ETag"]
        listed = mesh.request("vault", "GET", "/engagements", params={"domain": "payments", "limit": 100}).json()
        assert source in listed["items"] and listed["limit"] == 100 and listed["offset"] == 0
        mesh.request("vault", "POST", "/engagements", expected=409, json=source)
        updated = deepcopy(source)
        updated.update(completed_at="2026-09-02", challenge="Updated source challenge.")
        updated.pop("extension")
        mesh.request("vault", "PUT", path, expected=428, json=updated)
        mesh.request("vault", "PUT", path, expected=412, json=updated, headers={"If-Match": '"stale"'})
        replaced = mesh.request("vault", "PUT", path, json=updated,
                                headers={"If-Match": created.headers["ETag"]})
        assert replaced.json() == updated and replaced.headers["ETag"] != created.headers["ETag"]
        current = mesh.request("vault", "GET", path)
        assert current.json() == updated and current.headers["ETag"] == replaced.headers["ETag"]
        mesh.request("vault", "PUT", path, expected=412, json=source,
                     headers={"If-Match": created.headers["ETag"]})
        versions = mesh.request("vault", "GET", path + "/versions").json()["versions"]
        assert len(versions) == 2
        assert [entry["etag"] for entry in versions] == [created.headers["ETag"].strip('"'), replaced.headers["ETag"].strip('"')]
        previous = mesh.request("vault", "GET", path, params={"as_of": versions[0]["recorded_at"]})
        assert previous.json() == source and previous.headers["ETag"] == created.headers["ETag"]
        mesh.request("vault", "DELETE", path, expected=428)
        mesh.request("vault", "DELETE", path, expected=412, headers={"If-Match": created.headers["ETag"]})
        result = mesh.request("vault", "DELETE", path, expected=204, headers={"If-Match": current.headers["ETag"]})
        assert result.content == b""
        mesh.request("vault", "GET", path, expected=404)
        assert mesh.request("vault", "GET", path + "/versions").json()["versions"] == versions
        assert mesh.request("vault", "GET", path, params={"as_of": versions[-1]["recorded_at"]}).json() == updated
    finally:
        _remove_if_present(mesh, source["id"])


BAD_FIELDS = [
    pytest.param({"id": 123}, id="numeric-id"),
    pytest.param({"client_type": 17}, id="numeric-client-type"),
    pytest.param({"may_be_named": "false"}, id="string-consent"),
    pytest.param({"technologies": [{"name": "Python"}]}, id="nested-technology"),
    pytest.param({"technologies": [123]}, id="numeric-technology"),
    pytest.param({"outcomes": [{"metric": 123, "source_ref": "source.pdf"}]}, id="numeric-metric"),
    pytest.param({"outcomes": [{"metric": "Reduced latency", "source_ref": []}]}, id="invalid-citation"),
    pytest.param({"supports_qualitative_claims": 1}, id="numeric-qualitative-permission"),
    pytest.param({"team_size": True}, id="boolean-team-size"),
    pytest.param({"completed_at": 20260901}, id="numeric-completed-at"),
]


@pytest.mark.contract(owner="Kaan", requirement="CF-84", boundary="Client->Vault")
@pytest.mark.parametrize("invalid", BAD_FIELDS)
@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_invalid_vault_types_return_json_422_without_writing(mesh, invalid, method):
    """Wrongly typed known fields are a JSON 422 and change nothing (F-02)."""
    source = _source()
    path = "/engagements/" + source["id"]
    try:
        created = mesh.request("vault", "POST", "/engagements", expected=201, json=source)
        total = mesh.request("vault", "GET", "/engagements").json()["total"]
        invalid_record = {**source, **invalid}
        target = path if method == "PUT" else "/engagements"
        headers = {"If-Match": created.headers["ETag"]} if method == "PUT" else {}
        if method == "POST" and "id" not in invalid:
            invalid_record["id"] += "-rejected"
        rejected = mesh.request("vault", method, target, expected=422, json=invalid_record, headers=headers)
        assert rejected.headers["Content-Type"].startswith("application/json")
        assert isinstance(rejected.json()["detail"], str) and rejected.json()["detail"]
        current = mesh.request("vault", "GET", path)
        assert current.json() == source and current.headers["ETag"] == created.headers["ETag"]
        assert mesh.request("vault", "GET", "/engagements").json()["total"] == total
        assert len(mesh.request("vault", "GET", path + "/versions").json()["versions"]) == 1
    finally:
        _remove_if_present(mesh, source["id"])
        _remove_if_present(mesh, source["id"] + "-rejected")


@pytest.mark.contract(owner="Kaan", requirement="CF-84", boundary="Client->Vault")
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_extension_is_rejected_before_persistence(mesh, literal):
    """NaN/Infinity JSON literals are refused before anything is stored."""
    source = _source()
    body = json.dumps(source)[:-1] + ', "extension": {"value": ' + literal + "}}"
    try:
        response = mesh.request("vault", "POST", "/engagements", expected=422, data=body,
                                headers={"Content-Type": "application/json"})
        assert isinstance(response.json()["detail"], str)
        mesh.request("vault", "GET", "/engagements/" + source["id"], expected=404)
        mesh.request("vault", "GET", "/engagements/" + source["id"] + "/versions", expected=404)
    finally:
        _remove_if_present(mesh, source["id"])


@pytest.mark.contract(owner="Kaan", requirement="CF-85", boundary="Client->Vault")
@pytest.mark.parametrize("authorization", ["", "Bearer incorrect-synthetic-token"])
def test_vault_denies_missing_or_invalid_authentication(mesh, authorization):
    """Vault data routes require the configured bearer token."""
    response = mesh.request("vault", "GET", "/engagements", expected=401,
                            headers={"Authorization": authorization})
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert isinstance(response.json()["detail"], str)


@pytest.mark.contract(owner="Kaan", requirement="CF-82", boundary="Reader->Vault")
def test_reader_extracts_document_and_replay_confirms_same_record(mesh):
    """Reader stores an uploaded PDF once over HTTP; a replay confirms instead of rewriting."""
    source = _source()
    for outcome in source["outcomes"]:
        outcome["source_ref"] = "cf120-boundary.pdf#page=1"
    upload = _pdf(source)
    # Reader derives this flag from the extracted outcomes section.
    source["outcome_missing"] = False
    path = "/engagements/" + source["id"]
    try:
        trace = "reader-create-" + uuid4().hex
        first = mesh.request("reader", "POST", "/extract", trace=trace,
                             files={"document": ("cf120-boundary.pdf", upload, "application/pdf")})
        assert first.json() == source and first.headers["X-Vault-Stored"] == "true"
        saved = mesh.request("vault", "GET", path)
        assert saved.json() == source
        calls = mesh.boundary_calls(trace)
        assert len(calls) == 1
        assert calls[0]["target"] == "vault" and calls[0]["method"] == "POST" and calls[0]["status"] == 201
        assert calls[0]["payload"] == source and calls[0]["authorization_matches"]
        assert calls[0]["idempotency_key"]
        replay = mesh.request("reader", "POST", "/extract",
                              files={"document": ("cf120-boundary.pdf", upload, "application/pdf")})
        assert replay.json() == source and replay.headers["X-Vault-Stored"] == "true"
        assert "confirmed" in replay.headers["X-Vault-Detail"]
        assert mesh.request("vault", "GET", path).headers["ETag"] == saved.headers["ETag"]
        assert len(mesh.request("vault", "GET", path + "/versions").json()["versions"]) == 1
    finally:
        _remove_if_present(mesh, source["id"])


@pytest.mark.contract(owner="Kaan", requirement="CF-81", boundary="Client->Reader")
def test_reader_missing_outcomes_are_explicit_without_storage(mesh):
    """Absent outcomes stay empty and flagged; store=false never calls Vault."""
    source = _source()
    source.update(outcomes=[], outcome_missing=True)
    trace = "reader-no-store-" + uuid4().hex
    response = mesh.request("reader", "POST", "/extract", trace=trace, params={"store": "false"},
                            files={"document": ("no-outcomes.pdf", _pdf(source), "application/pdf")})
    assert response.json() == source
    assert response.headers["X-Vault-Stored"] == "false"
    assert mesh.boundary_calls(trace) == []
    mesh.request("vault", "GET", "/engagements/" + source["id"], expected=404)


@pytest.mark.contract(owner="Kaan", requirement="CF-81", boundary="Client->Reader")
@pytest.mark.parametrize("kind,status", [("missing", 422), ("empty", 422), ("corrupt", 422),
                                          ("blank", 422), ("oversized", 413)])
def test_reader_rejects_invalid_upload_without_calling_vault(mesh, kind, status):
    """Missing, empty, corrupt, blank or oversized uploads are rejected before any Vault call."""
    trace = "reader-invalid-" + uuid4().hex
    kwargs = {}
    if kind != "missing":
        content = {"empty": b"", "corrupt": b"not-a-pdf"}.get(kind)
        if kind == "blank":
            content = _pdf()
        elif kind == "oversized":
            content = b"x" * (20 * 1024 * 1024 + 1)
        kwargs["files"] = {"document": ("invalid.pdf", content, "application/pdf")}
    response = mesh.request("reader", "POST", "/extract", expected=status, trace=trace, **kwargs)
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json()["detail"]
    assert mesh.boundary_calls(trace) == []
