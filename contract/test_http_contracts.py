"""Shared HTTP rules on the wire: health, OpenAPI, trace/auth/idempotency, headers, redirects."""
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from contract.fixtures.cases import LANGUAGES, RECORD_01_ID, SOURCE_01, fixture_draft
from contract.mesh import SERVICES
from tests.support import closeout_pdf

ROOT = Path(__file__).resolve().parents[1]
INVALID_HEADER = {'detail': 'Invalid HTTP tracing or authorization header'}


def expected_health(service, mesh, body):
    return {
        'vault': {'status': 'ok', 'service': 'vault', 'version': '0.7.0', 'records': body.get('records')},
        'reader': {'status': 'ok', 'service': 'reader', 'version': '1.0.0', 'ocr_available': False,
                   'supported_input': 'structured-text-layer-pdf', 'vault_url': mesh.relay_url + '/vault'},
        'generator': {'status': 'ok', 'service': 'generator', 'languages': ['en', 'de', 'tr']},
        # Verifier's documented liveness body has no service field (plan F-07).
        'verifier': {'status': 'ok'},
        'publisher': {'status': 'ok', 'service': 'publisher'},
        'librarian': {'status': 'ok', 'service': 'librarian'},
        'analyst': {'status': 'ok', 'service': 'analyst'},
    }[service]


@pytest.mark.contract(owner='CF-120 (all service owners)', requirement='CF-103/CF-105', boundary='Client->each API')
@pytest.mark.parametrize('service', SERVICES)
def test_health_docs_and_live_openapi_match_the_frozen_contract(mesh, service):
    """Each API answers its documented health body and serves exactly its versioned OpenAPI."""
    health = mesh.request(service, 'GET', '/health', headers={'Authorization': None}).json()
    assert health == expected_health(service, mesh, health)
    if service == 'vault':
        assert type(health['records']) is int and health['records'] >= 0
    docs = mesh.request(service, 'GET', '/docs', headers={'Authorization': None})
    assert docs.headers['Content-Type'].startswith('text/html')
    live = mesh.request(service, 'GET', '/openapi.json', headers={'Authorization': None}).json()
    frozen = json.loads((ROOT / 'docs' / 'openapi' / f'{service}.json').read_text(encoding='utf-8'))
    assert live == frozen


@pytest.mark.contract(owner='CF-120 (all service owners)', requirement='CF-103', boundary='Client->each API')
@pytest.mark.parametrize('service', SERVICES)
def test_trace_is_created_or_echoed_and_invalid_shared_headers_are_400(mesh, service):
    """Every API creates or echoes X-Correlation-ID and bounds all three shared headers at 4096."""
    created = mesh.request(service, 'GET', '/health', headers={'X-Correlation-ID': None})
    UUID(created.headers['X-Correlation-ID'])
    for name in ('X-Correlation-ID', 'Authorization', 'Idempotency-Key'):
        accepted = mesh.request(service, 'GET', '/health', headers={name: 'x' * 4096})
        if name == 'X-Correlation-ID':
            assert accepted.headers[name] == 'x' * 4096
        own_trace = {} if name == 'X-Correlation-ID' else {'X-Correlation-ID': None}
        for invalid in ('x' * 4097, 'invalid\xffvalue'):
            response = mesh.request(service, 'GET', '/health', expected=400, headers={name: invalid, **own_trace})
            assert response.json() == INVALID_HEADER
            UUID(response.headers['X-Correlation-ID'])
        # A control character never reaches the application: the HTTP parser refuses it.
        refused = mesh.request(service, 'GET', '/health', expected=400,
                               headers={name: 'invalid\x1fvalue', **own_trace})
        assert 'X-Correlation-ID' not in refused.headers


@pytest.mark.contract(owner='Taha', requirement='CF-103',
                      boundary='Client->Generator/Publisher->Vault/Verifier/provider')
def test_one_trace_reaches_every_hop_and_its_logs_without_credentials(mesh, sources):
    """A caller trace crosses Vault, Verifier and provider hops and appears in each service log."""
    trace = 'trace-hops-' + uuid4().hex
    key = 'idempotency-' + uuid4().hex
    draft = mesh.request('generator', 'POST', '/generate', trace=trace, json={'record_id': RECORD_01_ID}).json()
    assert draft == fixture_draft(RECORD_01_ID, 'en')
    mesh.request('publisher', 'POST', '/publish', expected=201, trace=trace,
                 headers={'Idempotency-Key': key},
                 json={'record_id': RECORD_01_ID, 'draft': draft, 'format': 'docx'})
    hops = mesh.boundary_calls(trace)
    assert [(call['target'], call['method']) for call in hops] == [
        ('vault', 'GET'), ('vault', 'GET'), ('verifier', 'POST'), ('vault', 'GET')]
    assert all(call['trace'] == trace and call['authorization_matches'] for call in hops)
    # The caller's write key is inherited by the server-side write it causes.
    assert hops[2]['idempotency_key'] == key
    assert [call['correlation_id'] for call in mesh.provider_calls(trace)] == [trace] * 2
    logs = Path(mesh.config['run_directory']) / 'logs'
    for service in ('generator', 'vault', 'verifier', 'publisher'):
        text = (logs / f'{service}.log').read_text(encoding='utf-8', errors='replace')
        assert f'correlation_id={trace}' in text, service
    for path in logs.glob('*.log'):
        assert mesh.config['token'] not in path.read_text(encoding='utf-8', errors='replace'), path.name


AUTH_CONSUMERS = [
    pytest.param('generator', 'POST', '/generate', {'json': {'record_id': RECORD_01_ID}}, id='generator'),
    pytest.param('verifier', 'POST', '/verify',
                 {'json': {'record_id': RECORD_01_ID, 'draft': fixture_draft(RECORD_01_ID, 'en')}}, id='verifier'),
    pytest.param('librarian', 'GET', '/search', {'params': {'q': 'payments'}}, id='librarian'),
    pytest.param('analyst', 'GET', '/coverage', {}, id='analyst'),
]


@pytest.mark.contract(owner='Kaan', requirement='CF-85/CF-103', boundary='consumer->Vault (caller credential)')
@pytest.mark.parametrize('service,method,path,kwargs', AUTH_CONSUMERS)
def test_caller_credential_is_forwarded_and_a_wrong_one_is_denied(mesh, sources, service, method, path, kwargs):
    """Incoming authorization takes precedence over the service token and Vault denies a wrong one."""
    trace = 'wrong-token-' + uuid4().hex
    denied = mesh.request(service, method, path, expected=401, trace=trace,
                          headers={'Authorization': 'Bearer wrong-synthetic-token'}, **kwargs)
    assert denied.json()['detail']
    calls = mesh.boundary_calls(trace)
    assert len(calls) == 1 and calls[0]['status'] == 401 and calls[0]['authorization_matches'] is False
    assert mesh.provider_calls(trace) == []
    # Without a caller credential the configured service token authenticates the hop.
    trace = 'service-token-' + uuid4().hex
    mesh.request(service, method, path, trace=trace, headers={'Authorization': None}, **kwargs)
    calls = mesh.boundary_calls(trace)
    assert calls and all(call['authorization_matches'] and call['status'] == 200 for call in calls)


@pytest.mark.contract(owner='Kaan', requirement='CF-82/CF-85', boundary='Reader->Vault, Client->Publisher')
def test_wrong_credential_never_stores_or_publishes(mesh, sources):
    """Reader reports a denied write as unstored; Publisher rejects before any dependency call."""
    trace = 'reader-wrong-token-' + uuid4().hex
    response = mesh.request('reader', 'POST', '/extract', trace=trace,
                            headers={'Authorization': 'Bearer wrong-synthetic-token'},
                            files={'document': ('cf105-1.pdf', closeout_pdf(SOURCE_01), 'application/pdf')})
    assert response.headers['X-Vault-Stored'] == 'false'
    assert response.headers['X-Vault-Detail'] == 'vault rejected authorization'
    assert [(call['method'], call['status']) for call in mesh.boundary_calls(trace)] == [('POST', 401)]
    trace = 'publisher-wrong-token-' + uuid4().hex
    before = mesh.artifact_snapshot()
    mesh.request('publisher', 'POST', '/publish', expected=401, trace=trace,
                 headers={'Authorization': 'Bearer wrong-synthetic-token'},
                 json={'record_id': RECORD_01_ID, 'draft': fixture_draft(RECORD_01_ID, 'en')})
    assert mesh.boundary_calls(trace) == [] and mesh.artifact_snapshot() == before


LIST_BODY = {'items': [SOURCE_01], 'total': 1, 'limit': 100, 'offset': 0}
SOURCE_CONSUMERS = [
    pytest.param('generator', 'POST', '/generate', {'json': {'record_id': RECORD_01_ID}}, 'record', id='generator'),
    pytest.param('verifier', 'POST', '/verify',
                 {'json': {'record_id': RECORD_01_ID, 'draft': fixture_draft(RECORD_01_ID, 'en')}}, 'record',
                 id='verifier'),
    pytest.param('publisher', 'POST', '/publish',
                 {'json': {'record_id': RECORD_01_ID, 'draft': fixture_draft(RECORD_01_ID, 'en')}}, 'record',
                 id='publisher'),
    pytest.param('librarian', 'GET', '/search', {'params': {'q': 'payments'}}, 'list', id='librarian'),
    pytest.param('analyst', 'GET', '/coverage', {}, 'list', id='analyst'),
]


@pytest.mark.contract(owner='Arda/Taha/Serhat', requirement='CF-103/CF-104', boundary='consumer->Vault (malformed)')
@pytest.mark.parametrize('answer', ['302-with-valid-json', '200-not-json', '200-wrong-shape'])
@pytest.mark.parametrize('service,method,path,kwargs,shape', SOURCE_CONSUMERS)
def test_redirected_or_malformed_vault_answer_is_502_and_never_followed(mesh, sources, service, method, path,
                                                                        kwargs, shape, answer):
    """A redirect, non-JSON or wrongly shaped Vault answer is a 502, even with a plausible body."""
    trace = f'vault-{answer}-{service}-' + uuid4().hex
    valid = SOURCE_01 if shape == 'record' else LIST_BODY
    fault = {
        '302-with-valid-json': {'status': 302, 'body': valid,
                                'headers': {'Content-Type': 'application/json', 'Location': '/engagements'}},
        '200-not-json': {'status': 200, 'body': 'not json', 'headers': {'Content-Type': 'application/json'}},
        '200-wrong-shape': {'status': 200, 'body': {'items': 'not-a-list'} if shape == 'list' else ['not-a-record']},
    }[answer]
    mesh.fault('vault', trace, method='GET', **fault)
    before = mesh.artifact_snapshot()
    response = mesh.request(service, method, path, expected=502, trace=trace, **kwargs)
    assert response.headers['Content-Type'].startswith('application/json') and response.json()['detail']
    calls = mesh.boundary_calls(trace)
    assert len(calls) == 1 and calls[0].get('injected') is True
    assert mesh.provider_calls(trace) == [] and mesh.artifact_snapshot() == before


@pytest.mark.contract(owner='Taha', requirement='CF-105', boundary='legacy Generator adapters->Vault')
@pytest.mark.parametrize('route,language', [('/generator/mcs', 'en'), ('/generator/mcs/eng', 'en'),
                                            ('/generator/mcs/german', 'de'), ('/generator/mcs/turkish', 'tr')])
def test_deprecated_generator_adapters_use_vault_facts_not_submitted_facts(mesh, sources, route, language):
    """Legacy record-body routes keep only the id; every fact comes from Vault."""
    forged = {**SOURCE_01, 'client': 'Forged Client', 'challenge': 'Forged challenge.', 'may_be_named': True}
    trace = 'legacy-generator-' + uuid4().hex
    draft = mesh.request('generator', 'POST', route, trace=trace, json=forged).json()
    assert draft == fixture_draft(RECORD_01_ID, language)
    assert [(call['target'], call['method']) for call in mesh.boundary_calls(trace)] == [('vault', 'GET')]
    assert mesh.provider_calls(trace)[0]['spans'][2]['text'] == SOURCE_01['challenge']
    mesh.request('generator', 'POST', route, expected=422, json={**forged, 'id': 'bad/id'})


@pytest.mark.contract(owner='Taha', requirement='CF-100/CF-105', boundary='legacy Verifier adapter->Vault')
@pytest.mark.parametrize('language', LANGUAGES)
def test_deprecated_verifier_adapter_ignores_submitted_record_facts(mesh, sources, language):
    """/verify/{id} verifies against Vault; a forged record body cannot turn a BLOCK into PASS."""
    draft = fixture_draft(RECORD_01_ID, language)
    forged = {**SOURCE_01, 'duration_months': 12}
    report = mesh.request('verifier', 'POST', f'/verify/{RECORD_01_ID}', json={'record': forged, 'mcs': draft}).json()
    assert report == {'engagement_id': RECORD_01_ID, 'verdict': 'PASS', 'problems': []}
    poisoned = json.loads(json.dumps(draft))
    poisoned['sections']['outcomes'][0]['outcomes'] = {'en': 'The project lasted 12 months.',
                                                       'de': 'Das Projekt dauerte 12 Monate.',
                                                       'tr': 'Proje 12 ay sürdü.'}[language]
    blocked = mesh.request('verifier', 'POST', f'/verify/{RECORD_01_ID}',
                           json={'record': forged, 'mcs': poisoned}).json()
    assert blocked['verdict'] == 'BLOCK'
    mesh.request('verifier', 'POST', f'/verify/{RECORD_01_ID}', expected=422,
                 json={'record': {**forged, 'id': 'eng-cf105-02'}, 'mcs': draft})


@pytest.mark.contract(owner='Taha / Kaan / Arda', requirement='CF-103/CF-105',
                      boundary='Client->Generator/Verifier/Publisher/Vault/Reader/Librarian')
@pytest.mark.parametrize('service,path', [('generator', '/generate'), ('verifier', '/verify'),
                                          ('publisher', '/publish'), ('vault', '/engagements'),
                                          ('reader', '/extract'), ('librarian', '/match')])
def test_validation_errors_do_not_reflect_submitted_draft_or_source_text(mesh, sources, service, path):
    """422 envelopes for content-bearing routes list loc/msg/type only, never the submitted prose."""
    secret = 'CF120-PRIVATE-' + uuid4().hex
    if service == 'vault':
        kwargs = {'json': [{'client': secret}]}
    elif service == 'reader':
        kwargs = {'data': {'document': secret}}
    elif service == 'librarian':
        kwargs = {'json': {'rfp_text': {'source': secret}}}
    else:
        body = {'record_id': RECORD_01_ID, 'language': 'xx', 'unexpected': secret}
        if service != 'generator':
            body['draft'] = {'sections': {'challenge': secret}, 'secret': secret}
        kwargs = {'json': body}
    trace = 'privacy-' + uuid4().hex
    before = mesh.artifact_snapshot()
    response = mesh.request(service, 'POST', path, expected=422, trace=trace, **kwargs)
    assert secret not in response.text
    assert all(set(item) == {'loc', 'msg', 'type'} for item in response.json()['detail'])
    assert response.json()['detail']
    assert mesh.boundary_calls(trace) == [] and mesh.provider_calls(trace) == []
    assert mesh.artifact_snapshot() == before


@pytest.mark.contract(owner='Arda', requirement='CF-92', boundary='Client->Librarian')
@pytest.mark.parametrize('method,path,kwargs', [
    ('GET', '/search', {'params': {'q': ''}}), ('GET', '/search', {'params': {'q': 'x', 'top': 21}}),
    ('GET', '/search', {'params': {'q': 'x', 'strategy': 'sparse'}}),
    ('POST', '/match', {'json': {'rfp_text': ''}}), ('POST', '/match', {'json': {'rfp_text': 'x', 'top_k': 0}}),
    ('POST', '/match', {'json': {'rfp_text': 'x', 'min_dense_score': 1.5}}),
], ids=['empty-query', 'top-over-20', 'unknown-strategy', 'empty-rfp', 'top-k-zero', 'score-over-1'])
def test_retrieval_parameter_bounds_are_422_without_vault_calls(mesh, sources, method, path, kwargs):
    """Invalid search/match parameters are rejected before Vault is read."""
    trace = 'retrieval-bounds-' + uuid4().hex
    mesh.request('librarian', method, path, expected=422, trace=trace, **kwargs)
    assert mesh.boundary_calls(trace) == []
