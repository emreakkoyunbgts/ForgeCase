"""Live retrieval and analytics assertions against real, isolated Vault data."""
from contextlib import contextmanager
from copy import deepcopy
import math
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from contract.fixtures.cases import DOMAINS, EVALUATION_IDS, SOURCE_01


def _records(mesh):
    response = mesh.request("vault", "GET", "/engagements").json()
    assert set(response) == {"items", "total", "limit", "offset"}
    assert response["total"] == len(response["items"])
    return response["items"]


def _delete(mesh, record_id):
    path = "/engagements/" + record_id
    current = mesh.request("vault", "GET", path)
    result = mesh.request("vault", "DELETE", path, expected=204,
                          headers={"If-Match": current.headers["ETag"]})
    assert result.content == b""


def _cleanup(mesh, ids):
    for record in _records(mesh):
        if record["id"] in ids:
            _delete(mesh, record["id"])


@contextmanager
def _corpus(mesh, desired):
    """Replace only this run's private Vault corpus and restore original facts."""
    original = _records(mesh)
    removed = []
    added_ids = {record["id"] for record in desired}
    try:
        for record in original:
            _delete(mesh, record["id"])
            removed.append(record)
        for record in desired:
            created = mesh.request("vault", "POST", "/engagements", expected=201, json=record)
            assert created.json() == record
        yield
    finally:
        _cleanup(mesh, added_ids)
        for record in removed:
            restored = mesh.request("vault", "POST", "/engagements", expected=201, json=record)
            assert restored.json() == record
        assert {record["id"]: record for record in _records(mesh)} == {
            record["id"]: record for record in original}


def _assert_match(match, allowed_ids):
    assert set(match) == {"engagement_id", "score", "why"}
    assert match["engagement_id"] in allowed_ids
    assert type(match["score"]) in {int, float} and math.isfinite(match["score"])
    assert isinstance(match["why"], str) and match["why"].strip()
    assert "Synthetic Example Bank" not in match["why"]


def _vault_reads(mesh, trace):
    calls = [call for call in mesh.boundary_calls(trace) if call["target"] == "vault"]
    assert calls and all(call["method"] == "GET" and call["status"] == 200 for call in calls)
    assert all(call["authorization_matches"] and call["trace"] == trace for call in calls)
    assert all(not call.get("injected", False) for call in calls)
    return calls


@pytest.mark.contract(owner="Arda", requirement="CF-92", boundary="Librarian->Vault")
@pytest.mark.parametrize("strategy", ["dense", "hybrid"])
def test_search_uses_real_nonempty_embeddings(mesh, sources, strategy):
    """/search ranks real stored records with finite scores and deterministic repeat results."""
    trace = "retrieval-" + uuid4().hex
    result = mesh.request("librarian", "GET", "/search", trace=trace,
                          params={"q": "payments Python", "top": 3, "strategy": strategy}).json()
    assert set(result) == {"query", "strategy", "matches"}
    assert result["query"] == "payments Python" and result["strategy"] == strategy
    assert len(result["matches"]) == 3
    assert len({match["engagement_id"] for match in result["matches"]}) == 3
    for match in result["matches"]:
        _assert_match(match, set(EVALUATION_IDS))
    scores = [match["score"] for match in result["matches"]]
    assert scores == sorted(scores, reverse=True)
    _vault_reads(mesh, trace)
    repeated = mesh.request("librarian", "GET", "/search",
                            params={"q": "payments Python", "top": 3, "strategy": strategy}).json()
    assert repeated == result


@pytest.mark.contract(owner="Arda", requirement="CF-92", boundary="Librarian->Vault")
@pytest.mark.parametrize("strategy", ["dense", "hybrid"])
def test_match_reports_finite_evidence_and_consistent_coverage(mesh, sources, strategy):
    """/match evidences each requirement with a real record and a consistent coverage summary."""
    trace = "match-" + uuid4().hex
    text = "1. Payments processing using Python.\n2. Cloud processing using Python."
    result = mesh.request("librarian", "POST", "/match", trace=trace, json={
        "rfp_text": text, "top_k": 3, "strategy": strategy, "min_dense_score": 0.0}).json()
    assert set(result) == {"requirements", "coverage", "configuration"}
    assert len(result["requirements"]) == 2
    for index, requirement in enumerate(result["requirements"], 1):
        assert set(requirement) == {"requirement_id", "text", "status", "best_match", "gap_reason"}
        assert requirement["requirement_id"] == f"REQ-{index:03d}"
        assert requirement["text"] in {"Payments processing using Python.", "Cloud processing using Python."}
        assert requirement["status"] == "EVIDENCED" and requirement["gap_reason"] is None
        match = requirement["best_match"]
        assert set(match) == {"engagement_id", "retrieval_strategy", "retrieval_score", "evidence_score", "why"}
        assert match["engagement_id"] in EVALUATION_IDS and match["retrieval_strategy"] == strategy
        for name in ("retrieval_score", "evidence_score"):
            assert type(match[name]) in {int, float} and math.isfinite(match[name])
        assert match["evidence_score"] >= 0.0
        assert isinstance(match["why"], str) and match["why"]
    assert result["coverage"] == {"evidenced": 2, "gaps": 0, "total": 2, "ratio": 1.0,
                                   "summary": "We can evidence 2 of 2 requirements."}
    config = result["configuration"]
    assert set(config) == {"retrieval_strategy", "top_k", "min_dense_score", "threshold_note"}
    assert config["retrieval_strategy"] == strategy and config["top_k"] == 3
    assert config["min_dense_score"] == 0.0 and isinstance(config["threshold_note"], str)
    _vault_reads(mesh, trace)


@pytest.mark.contract(owner="Arda", requirement="CF-95", boundary="Analyst->Vault")
def test_analytics_matches_all_twelve_source_facts(mesh, sources):
    """/coverage and /gaps equal the counts implied by the twelve fixture sources."""
    trace = "analytics-" + uuid4().hex
    coverage = mesh.request("analyst", "GET", "/coverage", trace=trace).json()
    assert coverage == {
        "total_engagements": 12,
        "by_domain": {domain[0]: 1 for domain in DOMAINS},
        "by_region": {"TR": 12},
        "by_client_type": {domain[0] + " operator": 1 for domain in DOMAINS},
        "no_outcome": [EVALUATION_IDS[-1]],
    }
    assert mesh.request("analyst", "GET", "/gaps").json() == {"total_gaps": 0, "gaps": []}
    _vault_reads(mesh, trace)


@pytest.mark.contract(owner="Arda", requirement="CF-95", boundary="Analyst/Librarian->Vault")
def test_empty_real_corpus_has_no_fabricated_statistics_or_matches(mesh, sources):
    """An empty Vault yields no statistics, matches or evidenced requirements."""
    with _corpus(mesh, []):
        assert mesh.request("analyst", "GET", "/coverage").json() == {
            "error": "No engagements found in corpus."}
        assert mesh.request("analyst", "GET", "/gaps").json() == {"total_gaps": 0, "gaps": []}
        found = mesh.request("librarian", "GET", "/search", params={"q": "payments"}).json()
        assert found == {"query": "payments", "strategy": "hybrid", "matches": []}
        matched = mesh.request("librarian", "POST", "/match", json={"rfp_text": "Payments processing."}).json()
        assert matched["coverage"] == {"evidenced": 0, "gaps": 1, "total": 1, "ratio": 0.0,
                                       "summary": "We can evidence 0 of 1 requirements."}
        requirement = matched["requirements"][0]
        assert requirement["status"] == "GAP" and requirement["best_match"] is None
        assert isinstance(requirement["gap_reason"], str) and requirement["gap_reason"]


@pytest.mark.contract(owner="Arda", requirement="CF-95", boundary="Analyst->Vault")
def test_gap_counts_come_from_real_domain_region_cross_product(mesh, sources):
    """Gaps are exactly the missing domain/region pairs of an isolated corpus."""
    records = []
    for index, (domain, region) in enumerate((("core banking", "TR"), ("core banking", "DE"), ("cloud", "TR"))):
        record = deepcopy(SOURCE_01)
        record.update(id="eng-cf120-gap-" + uuid4().hex, domain=domain, region=region,
                      client_type="synthetic operator")
        if index == 2:
            record.update(outcomes=[], outcome_missing=True)
        records.append(record)
    with _corpus(mesh, records):
        coverage = mesh.request("analyst", "GET", "/coverage").json()
        assert coverage == {"total_engagements": 3, "by_domain": {"core banking": 2, "cloud": 1},
                            "by_region": {"TR": 2, "DE": 1}, "by_client_type": {"synthetic operator": 3},
                            "no_outcome": [records[2]["id"]]}
        assert mesh.request("analyst", "GET", "/gaps").json() == {
            "total_gaps": 1, "gaps": [{"domain": "cloud", "region": "DE"}]}


@pytest.mark.contract(owner="Arda", requirement="CF-93", boundary="Librarian/Analyst->Vault")
def test_all_101_records_cross_both_consumers_pagination_boundaries(mesh, sources):
    """Analyst (100/page) and Librarian (50/page) read all 101 records across page boundaries."""
    original = _records(mesh)
    assert len(original) == 12
    prefix = "eng-zz-cf120-page-" + uuid4().hex
    additional = []
    for index in range(89):
        record = deepcopy(SOURCE_01)
        record.update(id=f"{prefix}-{index:03d}", client="Synthetic Pagination Bank")
        additional.append(record)
    sentinel = additional[-1]
    sentinel.update(domain="ultraviolet telemetry", client_type="ultraviolet telemetry operator",
                    challenge="Ultraviolet telemetry processing.", solution="Ultraviolet telemetry using Python.")
    ids = {record["id"] for record in additional}
    try:
        for record in additional:
            mesh.request("vault", "POST", "/engagements", expected=201, json=record)
        all_records = _records(mesh)
        assert len(all_records) == 101 and {record["id"] for record in all_records} == {
            record["id"] for record in original} | ids
        trace = "pages-analyst-" + uuid4().hex
        coverage = mesh.request("analyst", "GET", "/coverage", trace=trace).json()
        assert coverage["total_engagements"] == 101
        assert coverage["by_region"] == {"TR": 101}
        assert coverage["by_domain"] == {**{domain[0]: 1 for domain in DOMAINS},
                                         "payments": 89, "ultraviolet telemetry": 1}
        assert coverage["no_outcome"] == [EVALUATION_IDS[-1]]
        calls = _vault_reads(mesh, trace)
        assert [parse_qs(urlsplit(call["path"]).query)["offset"] for call in calls] == [["0"], ["100"]]
        trace = "pages-librarian-" + uuid4().hex
        result = mesh.request("librarian", "GET", "/search", trace=trace, params={
            "q": "ultraviolet telemetry", "top": 20, "strategy": "hybrid"}).json()
        assert len(result["matches"]) == 20
        assert sentinel["id"] in {match["engagement_id"] for match in result["matches"]}
        for match in result["matches"]:
            _assert_match(match, set(EVALUATION_IDS) | ids)
        calls = _vault_reads(mesh, trace)
        assert [parse_qs(urlsplit(call["path"]).query)["offset"] for call in calls] == [["0"], ["50"], ["100"]]
    finally:
        _cleanup(mesh, ids)
        assert {record["id"]: record for record in _records(mesh)} == {record["id"]: record for record in original}


@pytest.mark.contract(owner="Arda", requirement="CF-103", boundary="Analyst->Vault")
def test_analyst_trailing_slash_startup_keeps_vault_request_canonical(mesh, sources):
    """A VAULT_URL ending in '/' at Analyst startup still produces canonical Vault paths (F-04)."""
    try:
        mesh.restart("analyst", env={"VAULT_URL": mesh.relay_url + "/vault/"})
        trace = "slash-" + uuid4().hex
        assert mesh.request("analyst", "GET", "/coverage", trace=trace).json()["total_engagements"] == 12
        calls = _vault_reads(mesh, trace)
        assert len(calls) == 1 and calls[0]["path"].startswith("/engagements?")
        assert not calls[0]["path"].startswith("//")
    finally:
        mesh.restart("analyst")


@pytest.mark.contract(owner='Arda', requirement='CF-93', boundary='Librarian/Analyst->Vault')
@pytest.mark.parametrize('service,route', [('librarian', '/search?q=Python'), ('analyst', '/coverage')])
def test_incomplete_vault_page_is_not_accepted_as_complete_corpus(mesh, sources, service, route):
    """An empty page before the declared corpus end returns 502, never incomplete success."""
    trace = 'incomplete-page-' + uuid4().hex
    mesh.fault('vault', trace, method='GET', status=200,
               body={'items': [sources[0]], 'total': 2, 'limit': 100, 'offset': 0})
    mesh.fault('vault', trace, method='GET', status=200,
               body={'items': [], 'total': 2, 'limit': 100, 'offset': 1})
    response = mesh.request(service, 'GET', route, trace=trace, expected=502)
    assert response.json()['detail']['error'] == 'incomplete_vault_response'
    calls = mesh.boundary_calls(trace)
    assert len(calls) == 2 and all(call['injected'] for call in calls)
    assert [parse_qs(urlsplit(call['path']).query)['offset'] for call in calls] == [['0'], ['1']]
