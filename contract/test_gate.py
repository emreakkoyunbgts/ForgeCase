"""Negative and malformed dependencies must never create a publication."""
from copy import deepcopy
from uuid import uuid4

import pytest

from contract.fixtures.cases import LANGUAGES, RECORD_01_ID, fixture_draft
from evaluation.cf105_cases import poisoned

LABELS = ('metric_swap', 'wrong_duration', 'negation', 'date', 'unsupported', 'percentage_points', 'name_disclosure')
OUTCOME_SPAN = '/sections/outcomes/0/outcomes'
SEMANTIC_POISONS = {'metric_swap', 'negation', 'unsupported'}


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-91/100', boundary='verifier-publisher-negative')
@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('label', LABELS)
def test_poison_blocks_without_artifact(mesh, sources, language, label):
    """Each language/poison blocks both verification and publication without writing artifacts."""
    source = sources[0]
    trace = str(uuid4())
    clean = mesh.request('generator', 'POST', '/generate', trace=trace,
                         json={'record_id': source['id'], 'language': language}).json()
    altered = dict(poisoned(clean, source, language))[label]
    before = mesh.artifact_snapshot()
    payload = {'record_id': source['id'], 'draft': altered, 'language': language}
    report = mesh.request('verifier', 'POST', '/verify', trace=trace, json=payload).json()
    assert report['engagement_id'] == source['id'] and report['verdict'] == 'BLOCK' and report['problems']
    expected_type = ('unsupported_claim' if label in SEMANTIC_POISONS else
                     'client_named_without_consent' if label == 'name_disclosure' else 'ungrounded_number')
    assert {(problem['type'], problem['span']) for problem in report['problems']} == {(expected_type, OUTCOME_SPAN)}
    blocked = mesh.request('publisher', 'POST', '/publish', expected=422, trace=trace, json=payload).json()
    assert blocked['detail']['message'] == 'Publication blocked by Verifier'
    assert blocked['detail']['problems'] == report['problems']
    assert mesh.artifact_snapshot() == before
    assessments = [call for call in mesh.provider_calls(trace) if call['stage'] == 'assessment']
    assert len(assessments) == (2 if label in SEMANTIC_POISONS else 0)
    for call in assessments:
        assert call['record_id'] == source['id'] and call['language'] == language
        assert call['fault'] is None and call['status'] == 200
        assert next(item['text'] for item in call['spans'] if item['id'] == OUTCOME_SPAN) == altered['sections']['outcomes'][0]['outcomes']
    assert [call['stage'] for call in mesh.provider_calls(trace)] == ['translation'] + ['assessment'] * len(assessments)


@pytest.mark.contract(owner='Serhat', requirement='CF-91', boundary='publisher-verifier-invalid-report')
@pytest.mark.parametrize('answer,expected', [
    pytest.param({'body': {'engagement_id': RECORD_01_ID, 'verdict': 'PASS', 'problems': [{'type': 'unsupported'}]}}, 502, id='pass-with-problems'),
    pytest.param({'body': {'engagement_id': 'another', 'verdict': 'PASS', 'problems': []}}, 502, id='wrong-source'),
    pytest.param({'body': {'engagement_id': RECORD_01_ID, 'verdict': 'MAYBE', 'problems': []}}, 502, id='unknown-verdict'),
    pytest.param({'body': {'engagement_id': RECORD_01_ID, 'verdict': 'BLOCK', 'problems': [{'type': 'unsupported'}]}}, 422, id='block'),
    pytest.param({'body': {'verdict': 'PASS'}}, 502, id='missing-fields'),
    pytest.param({'body': {'engagement_id': RECORD_01_ID, 'verdict': 'PASS', 'problems': [], 'unexpected': 'value'}}, 502, id='extra-field'),
    pytest.param({'body': 'not json'}, 502, id='not-json'),
    pytest.param({'status': 302, 'body': {'engagement_id': RECORD_01_ID, 'verdict': 'PASS', 'problems': []}}, 502, id='redirect-with-pass-body'),
    pytest.param({'status': 500, 'body': {'engagement_id': RECORD_01_ID, 'verdict': 'PASS', 'problems': []}}, 502, id='server-error-with-pass-body'),
])
def test_invalid_gate_response_cannot_publish(mesh, draft, answer, expected):
    """Malformed/blocking/error/redirect Verifier responses cannot authorize publication or trigger a redirect hop."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    fault = {'status': 200, **deepcopy(answer)}
    if fault['status'] == 302:
        fault['headers'] = {'Content-Type': 'application/json', 'Location': mesh.relay_url + '/verifier/health'}
    mesh.fault('verifier', trace, method='POST', **fault)
    response = mesh.request('publisher', 'POST', '/publish', expected=expected, trace=trace,
                            json={'record_id': RECORD_01_ID, 'draft': draft})
    assert response.headers['Content-Type'].startswith('application/json') and response.json()['detail']
    assert mesh.artifact_snapshot() == before
    assert not mesh.provider_calls(trace), 'Injected verifier boundary should bypass only this semantic hop'
    gates = [call for call in mesh.boundary_calls(trace) if call['target'] == 'verifier']
    assert len(gates) == 1 and gates[0]['method'] == 'POST' and gates[0]['path'] == '/verify'
    assert gates[0]['injected'] is True and gates[0]['status'] == fault['status']


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-91/100', boundary='provider-errors-through-publication')
@pytest.mark.parametrize('fault,status', [
    ('incomplete_spans', 502), ('duplicate_spans', 502), ('fabricated_evidence', 502), ('omitted_evidence', 502),
    ('invalid_schema', 502), ('empty_output', 502), ('incomplete_status', 502),
    ('server_error', 502), ('unparsable', 502), ('unauthorized', 503), ('rate_limited', 503),
    ('language_mismatch', 422), ('unsupported_verdict', 422),
])
def test_provider_failure_cannot_publish(mesh, draft, fault, status):
    """Provider transport/schema/evidence failures surface controlled status without publication."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    mesh.arm_provider(fault, 'assessment', trace)
    result = mesh.request('publisher', 'POST', '/publish', expected=status, trace=trace,
                          json={'record_id': 'eng-cf105-01', 'draft': draft})
    assert 'detail' in result.json()
    assert mesh.artifact_snapshot() == before
    assert [call['fault'] for call in mesh.provider_calls(trace)] == [fault]


@pytest.mark.contract(owner='Taha', requirement='CF-68/69', boundary='translation-guards')
@pytest.mark.parametrize('fault,status', [('incomplete_spans', 502), ('duplicate_spans', 502), ('empty_translation', 502),
    ('changed_quantity', 502), ('changed_marker', 502), ('unparsable', 502), ('unauthorized', 503)])
def test_translation_failure_is_controlled(mesh, sources, fault, status):
    """Malformed translation or unavailable provider returns controlled JSON rather than a draft."""
    trace = str(uuid4())
    mesh.arm_provider(fault, 'translation', trace)
    response = mesh.request('generator', 'POST', '/generate', expected=status, trace=trace,
                            json={'record_id': sources[0]['id']})
    assert 'detail' in response.json()
    assert [call['fault'] for call in mesh.provider_calls(trace)] == [fault]


@pytest.mark.contract(owner='Serhat', requirement='CF-91', boundary='publish-request-validation')
@pytest.mark.parametrize('format,layout', [('docx', 'one-pager'), ('docx', 'single-slide'),
                                         ('pptx', 'full-case-study'), ('pdf', 'poster')])
def test_invalid_format_layout_has_no_side_effect(mesh, draft, format, layout):
    """Unsupported format/layout is rejected before dependencies or artifact writes."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    mesh.request('publisher', 'POST', '/publish', expected=422, trace=trace,
                 json={'record_id': 'eng-cf105-01', 'draft': draft, 'format': format, 'layout': layout})
    assert mesh.artifact_snapshot() == before
    assert mesh.boundary_calls(trace) == []


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-91/100', boundary='visible-provenance-consent')
def test_private_name_in_reference_blocks_before_provider(mesh, sources, draft):
    """Private client names in visible provenance block before semantic assessment and artifact writes."""
    original = mesh.request('vault', 'GET', '/engagements/eng-cf105-01').json()
    altered = deepcopy(original)
    private_ref = original['client'] + '.pdf#page=1'
    for item in altered['outcomes']:
        item['source_ref'] = private_ref
    response = mesh.request('vault', 'GET', '/engagements/eng-cf105-01')
    mesh.request('vault', 'PUT', '/engagements/eng-cf105-01',
                 headers={'If-Match': response.headers['ETag']}, json=altered)
    try:
        for item in draft['citations']:
            item['source_ref'] = private_ref
        trace, before = str(uuid4()), mesh.artifact_snapshot()
        payload = {'record_id': original['id'], 'draft': draft}
        assert mesh.request('verifier', 'POST', '/verify', trace=trace, json=payload).json()['verdict'] == 'BLOCK'
        mesh.request('publisher', 'POST', '/publish', expected=422, trace=trace, json=payload)
        assert not mesh.provider_calls(trace)
        assert mesh.artifact_snapshot() == before
    finally:
        current = mesh.request('vault', 'GET', '/engagements/eng-cf105-01')
        mesh.request('vault', 'PUT', '/engagements/eng-cf105-01',
                     headers={'If-Match': current.headers['ETag']}, json=original)


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-89/91/100', boundary='missing-Vault-source')
@pytest.mark.parametrize('service,route', [('generator', '/generate'), ('verifier', '/verify'),
                                         ('publisher', '/publish')])
def test_missing_source_is_404_without_model_or_artifact(mesh, sources, service, route):
    """All three source consumers preserve Vault's 404 and cannot use a local source fallback."""
    missing_id = 'eng-cf120-absent-' + uuid4().hex
    draft = fixture_draft(RECORD_01_ID, 'en')
    draft['engagement_ids'] = [missing_id]
    for title in draft['titles']:
        title['page'] = missing_id
    for entries in draft['sections'].values():
        for entry in entries:
            entry['page'] = missing_id
    for citation in draft['citations']:
        citation['page_ref'] = missing_id
    payload = {'record_id': missing_id}
    if service != 'generator':
        payload['draft'] = draft
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    response = mesh.request(service, 'POST', route, expected=404, trace=trace, json=payload)
    assert response.headers['Content-Type'].startswith('application/json') and response.json()['detail']
    calls = mesh.boundary_calls(trace)
    assert [(call['target'], call['method'], call['path'], call['status']) for call in calls] == [
        ('vault', 'GET', '/engagements/' + missing_id, 404)]
    assert mesh.provider_calls(trace) == [] and mesh.artifact_snapshot() == before


INVALID_DRAFTS = ('record-mismatch', 'draft-language', 'unknown-language', 'title-source',
                  'section-source', 'citation-source', 'extra-draft-field', 'nontext-section',
                  'empty-draft', 'invalid-record-id')


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-89/91/100', boundary='request-identity-validation')
@pytest.mark.parametrize('service,route', [('verifier', '/verify'), ('publisher', '/publish')])
@pytest.mark.parametrize('case', INVALID_DRAFTS)
def test_conflicting_or_malformed_draft_is_422_before_dependencies(mesh, sources, service, route, case):
    """Source/language/shape conflicts fail before Vault, Verifier, provider or artifact activity."""
    draft = fixture_draft(RECORD_01_ID, 'en')
    payload = {'record_id': RECORD_01_ID, 'language': 'en', 'draft': draft}
    if case == 'record-mismatch':
        payload['record_id'] = 'eng-cf105-02'
    elif case == 'draft-language':
        payload['language'] = 'de'
    elif case == 'unknown-language':
        payload['language'] = 'xx'
    elif case == 'title-source':
        draft['titles'][0]['page'] = 'eng-cf105-02'
    elif case == 'section-source':
        draft['sections']['outcomes'][0]['page'] = 'eng-cf105-02'
    elif case == 'citation-source':
        draft['citations'][0]['page_ref'] = 'eng-cf105-02'
    elif case == 'extra-draft-field':
        draft['unreviewed_notes'] = 'An unsupported field.'
    elif case == 'nontext-section':
        draft['sections']['outcomes'][0]['outcomes'] = {'unexpected': 'object'}
    elif case == 'empty-draft':
        payload['draft'] = {'sections': {}}
    else:
        payload['record_id'] = '../not-a-record'
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    response = mesh.request(service, 'POST', route, expected=422, trace=trace, json=payload)
    assert response.headers['Content-Type'].startswith('application/json') and response.json()['detail']
    assert mesh.boundary_calls(trace) == [] and mesh.provider_calls(trace) == []
    assert mesh.artifact_snapshot() == before


@pytest.mark.contract(owner='Serhat', requirement='CF-91', boundary='artifact-lookup')
@pytest.mark.parametrize('suffix', ['download', 'provenance'])
@pytest.mark.parametrize('identifier', ['not-a-uuid', '00000000-0000-0000-0000-000000000000'])
def test_unknown_artifact_is_404_without_dependency_activity(mesh, suffix, identifier):
    """Malformed and absent artifact identifiers return 404 for both downloadable assets."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    response = mesh.request('publisher', 'GET', f'/artifacts/{identifier}/{suffix}', expected=404, trace=trace)
    assert response.headers['Content-Type'].startswith('application/json') and response.json()['detail']
    assert mesh.boundary_calls(trace) == [] and mesh.provider_calls(trace) == []
    assert mesh.artifact_snapshot() == before


@pytest.mark.contract(owner='Serhat', requirement='CF-85/91', boundary='artifact-download-authorization')
@pytest.mark.parametrize('suffix', ['download', 'provenance'])
def test_existing_artifact_requires_authorization(mesh, sources, draft, suffix):
    """Existing document/provenance bytes require the correct token and remain accessible after denied attempts."""
    artifact = mesh.request('publisher', 'POST', '/publish', expected=201,
                            json={'record_id': RECORD_01_ID, 'draft': draft}).json()
    path = artifact['download_url' if suffix == 'download' else 'provenance_url']
    before = mesh.artifact_snapshot()
    for credential in (None, 'Bearer wrong-synthetic-token'):
        trace = str(uuid4())
        response = mesh.request('publisher', 'GET', path, expected=401, trace=trace,
                                headers={'Authorization': credential})
        assert response.headers['Content-Type'].startswith('application/json')
        assert response.headers['WWW-Authenticate'] == 'Bearer' and response.json()['detail']
        assert mesh.boundary_calls(trace) == [] and mesh.provider_calls(trace) == []
    valid = mesh.request('publisher', 'GET', path)
    if suffix == 'download':
        assert valid.content.startswith(b'PK')
    else:
        assert valid.json()['source_records'] == [RECORD_01_ID]
    assert mesh.artifact_snapshot() == before
