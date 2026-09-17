"""Real HTTP publication in all three languages; fixture expectations are independent."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from contract.documents import MEDIA_TYPES, assert_document
from contract.fixtures.cases import (
    EVALUATION_IDS, LANGUAGES, SPANS, NAMED_RECORD_ID, NAMED_SOURCE,
    PUBLICATIONS, display_values, fixture_draft,
)

FORMATS = PUBLICATIONS


def expected_display(record_id, language):
    return display_values(record_id, language)


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-104/120', boundary='full-pipeline')
@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('record_id', EVALUATION_IDS)
def test_clean_pipeline(mesh, sources, record_id, language):
    """Each source/language publishes grounded text and matching provenance through the real gate."""
    trace = str(uuid4())
    source = next(source for source in sources if source['id'] == record_id)
    draft = mesh.request('generator', 'POST', '/generate', trace=trace,
                         json={'record_id': record_id, 'language': language}).json()
    expected_draft = fixture_draft(record_id, language)
    assert draft == expected_draft
    payload = {'record_id': record_id, 'language': language, 'draft': draft}
    report = mesh.request('verifier', 'POST', '/verify', trace=trace, json=payload).json()
    assert report == {'engagement_id': record_id, 'verdict': 'PASS', 'problems': []}
    format, layout = FORMATS[EVALUATION_IDS.index(record_id) % len(FORMATS)]
    artifact = mesh.request('publisher', 'POST', '/publish', expected=201, trace=trace,
                            json={**payload, 'format': format, 'layout': layout}).json()
    assert set(artifact) == {'artifact_id', 'filename', 'media_type', 'download_url', 'provenance_url'}
    assert str(UUID(artifact['artifact_id'])) == artifact['artifact_id']
    assert artifact['filename'] == record_id + '.' + format
    assert artifact['media_type'] == MEDIA_TYPES[format]
    for key, suffix in [('download_url', 'download'), ('provenance_url', 'provenance')]:
        assert artifact[key] == f'/artifacts/{artifact["artifact_id"]}/{suffix}'
    downloaded = mesh.request('publisher', 'GET', artifact['download_url'], trace=trace)
    assert downloaded.headers['content-type'] == MEDIA_TYPES[format]
    assert_document(downloaded.content, format, layout, SPANS[record_id][language],
                    forbidden=[source['client']])
    provenance = mesh.request('publisher', 'GET', artifact['provenance_url'], trace=trace).json()
    assert provenance['source_records'] == [record_id]
    assert provenance['source_references'] == sorted({item['source_ref'] for item in source['outcomes']})
    assert provenance['citation_claims'] == [item['claim'] for item in expected_draft['citations']]
    assert provenance['language'] == language
    assert provenance['completed_at'] is None
    assert (provenance['freshness_status'], provenance['freshness_reason']) == ('UNKNOWN', 'DATE_MISSING')
    canonical = json.dumps(expected_display(record_id, language), sort_keys=True,
                           separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    assert provenance['content_hash'] == hashlib.sha256(canonical).hexdigest()
    calls = mesh.provider_calls(trace)
    assert [call['stage'] for call in calls] == ['translation', 'assessment', 'assessment']
    assert all(call['record_id'] == record_id and call['language'] == language for call in calls)
    assert all(call['status'] == 200 and call['fault'] is None for call in calls)
    for index, call in enumerate(calls):
        expected_spans = SPANS[record_id]['en' if index == 0 else language]
        assert len(call['spans']) == len(expected_spans)
        assert {span['id']: span['text'] for span in call['spans']} == expected_spans
        if index:
            assert call['source'] == {**source, 'outcome_missing': not source['outcomes']}
    gates = [call for call in mesh.boundary_calls(trace) if call['target'] == 'verifier']
    assert len(gates) == 1
    display = expected_display(record_id, language)
    assert gates[0]['payload'] == {'record_id': record_id, 'language': language, 'draft': {
        'engagement_id': record_id, 'title': display['title'],
        'sections': {'context': display['client_type'],
                     **{key: value for key, value in display.items() if key not in {'title', 'client_type'}}},
        'citations': expected_draft['citations'], 'client_named': False, 'language': language,
    }}
    assert all(call['authorization_matches'] for call in mesh.boundary_calls(trace))
    # Retain rendered samples as review artifacts after private service stores are removed.
    target = Path(mesh.config['run_directory']) / 'documents'
    target.mkdir(exist_ok=True)
    (target / f'{record_id}-{language}.{format}').write_bytes(downloaded.content)


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-104', boundary='Workflow HTTP client')
@pytest.mark.parametrize('language', LANGUAGES)
def test_workflow_approval_is_bound_to_content(mesh, sources, language):
    """Workflow caches one approved publication and invalidates approval after content/source/language edits."""
    from console.workflow import Workflow
    from tests.support import closeout_pdf
    flow = Workflow(language=language)
    flow.extract('cf105-1.pdf', closeout_pdf(sources[0]))
    flow.generate()
    assert flow.verify()['verdict'] == 'PASS'
    flow.approve(True)
    first = flow.publish()
    assert flow.publish() == first
    assert flow.download().startswith(b'PK')
    assert json.loads(flow.download(True))['language'] == language
    assert len([call for call in mesh.boundary_calls(flow.trace) if call['target'] == 'verifier']) == 1
    changed = deepcopy(flow.draft)
    changed['sections']['outcomes'][0]['outcomes'] = 'Unsupported 99999%'
    flow.edit(changed)
    assert not flow.verified and not flow.approved and flow.report is None
    with pytest.raises(ValueError):
        flow.publish()
    flow.select(sources[0]['id'], 'de' if language != 'de' else 'tr')
    assert flow.draft is None and not flow.approved
    flow.select(sources[1]['id'])
    assert flow.draft is None and not flow.verified


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-68/69', boundary='consent-positive-publish')
@pytest.mark.parametrize('language', LANGUAGES)
def test_named_consent_publishes(mesh, sources, language):
    """Every language publishes the explicitly permitted name, then blocks the same draft after revocation."""
    mesh.request('vault', 'POST', '/engagements', expected=201, json=NAMED_SOURCE)
    try:
        trace = str(uuid4())
        draft = mesh.request('generator', 'POST', '/generate', trace=trace,
                             json={'record_id': NAMED_RECORD_ID, 'language': language}).json()
        assert draft == fixture_draft(NAMED_RECORD_ID, language)
        payload = {'record_id': NAMED_RECORD_ID, 'draft': draft, 'language': language}
        report = mesh.request('verifier', 'POST', '/verify', trace=trace, json=payload).json()
        assert report == {'engagement_id': NAMED_RECORD_ID, 'verdict': 'PASS', 'problems': []}
        result = mesh.request('publisher', 'POST', '/publish', expected=201, trace=trace,
                              json=payload).json()
        assert result['media_type'] == MEDIA_TYPES['docx']
        body = mesh.request('publisher', 'GET', result['download_url']).content
        assert NAMED_SOURCE['client'] in assert_document(body, 'docx', 'full-case-study',
                                                        SPANS[NAMED_RECORD_ID][language])
        assert [call['stage'] for call in mesh.provider_calls(trace)] == ['translation', 'assessment', 'assessment']
        current = mesh.request('vault', 'GET', '/engagements/' + NAMED_RECORD_ID)
        mesh.request('vault', 'PUT', '/engagements/' + NAMED_RECORD_ID,
                     headers={'If-Match': current.headers['ETag']},
                     json={**current.json(), 'may_be_named': False})
        revoked_trace, before = str(uuid4()), mesh.artifact_snapshot()
        blocked = mesh.request('verifier', 'POST', '/verify', trace=revoked_trace, json=payload).json()
        assert blocked['engagement_id'] == NAMED_RECORD_ID and blocked['verdict'] == 'BLOCK'
        assert {item['type'] for item in blocked['problems']} == {'client_named_without_consent'}
        publication = mesh.request('publisher', 'POST', '/publish', expected=422,
                                   trace=revoked_trace, json=payload).json()
        assert publication['detail']['problems'] == blocked['problems']
        assert mesh.provider_calls(revoked_trace) == []
        assert mesh.artifact_snapshot() == before
    finally:
        mesh.delete_source(NAMED_RECORD_ID)
