"""Actual service stops/restarts and real production timeout budgets."""
import time
from copy import deepcopy
from uuid import uuid4

import pytest


@pytest.mark.contract(owner='ALL', requirement='CF-105/120', boundary='vault-outage')
def test_vault_outage_fails_closed_and_recovers(mesh, sources, draft):
    """A real Vault outage fails dependent consumers, reports Reader storage failure, and recovers intact."""
    before = mesh.artifact_snapshot()
    with mesh.down('vault'):
        for service, method, path, payload in [
            ('generator', 'POST', '/generate', {'record_id': sources[0]['id']}),
            ('verifier', 'POST', '/verify', {'record_id': sources[0]['id'], 'draft': draft}),
            ('publisher', 'POST', '/publish', {'record_id': sources[0]['id'], 'draft': draft}),
            ('librarian', 'GET', '/search?q=Python', None),
            ('librarian', 'POST', '/match', {'rfp_text': 'Python payment processing'}),
            ('analyst', 'GET', '/coverage', None), ('analyst', 'GET', '/gaps', None),
        ]:
            started = time.monotonic()
            result = mesh.request(service, method, path, expected=503, json=payload)
            assert 'detail' in result.json()
            assert time.monotonic() - started < 20
        from tests.support import closeout_pdf
        extracted = mesh.request('reader', 'POST', '/extract', files={
            'document': ('cf105-1.pdf', closeout_pdf(sources[0]), 'application/pdf')})
        assert extracted.headers['X-Vault-Stored'] == 'false'
        assert mesh.artifact_snapshot() == before
    assert mesh.request('vault', 'GET', '/engagements').json()['total'] == 12
    assert mesh.request('verifier', 'POST', '/verify',
                         json={'record_id': sources[0]['id'], 'draft': draft}).json()['verdict'] == 'PASS'


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-91/105', boundary='verifier-outage')
def test_verifier_outage_does_not_block_generation_but_blocks_publication(mesh, sources, draft):
    """Stopping Verifier leaves generation available and prevents publication until recovery."""
    before = mesh.artifact_snapshot()
    with mesh.down('verifier'):
        mesh.request('generator', 'POST', '/generate', json={'record_id': sources[0]['id']})
        mesh.request('publisher', 'POST', '/publish', expected=503,
                     json={'record_id': sources[0]['id'], 'draft': draft})
        assert mesh.artifact_snapshot() == before
    mesh.request('verifier', 'POST', '/verify', json={'record_id': sources[0]['id'], 'draft': draft})


@pytest.mark.contract(owner='Taha / Arda', requirement='CF-115/117', boundary='librarian-outage')
def test_librarian_outage_has_route_specific_behavior(mesh, sources):
    """Stopping Librarian fails the query adapter while canonical single-source generation remains available."""
    with mesh.down('librarian'):
        mesh.request('generator', 'POST', '/generate', json={'record_id': sources[0]['id']})
        mesh.request('generator', 'POST', '/generator/mcs/query', expected=503,
                     params={'query': 'Python payment processing'})
    assert mesh.request('librarian', 'GET', '/search?q=Python&top=1').json()['matches']


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-89/91', boundary='production-provider-timeout')
@pytest.mark.parametrize('service,stage', [('generator', 'translation'), ('publisher', 'assessment')])
def test_real_provider_deadline_returns_504_without_late_artifact(mesh, sources, draft, service, stage):
    """The real provider deadline returns 504 and a late response cannot create an artifact."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    mesh.arm_provider('timeout', stage, trace)
    payload = {'record_id': sources[0]['id']}
    if service == 'publisher':
        payload['draft'] = draft
    started = time.monotonic()
    mesh.request(service, 'POST', '/generate' if service == 'generator' else '/publish',
                 expected=504, trace=trace, json=payload, timeout=85)
    elapsed = time.monotonic() - started
    assert 55 <= elapsed < 80, elapsed
    # Wait past the injected 65s response: it must not resume a timed-out publication.
    remaining = 66 - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)
    assert mesh.artifact_snapshot() == before
    assert [call['fault'] for call in mesh.provider_calls(trace)] == ['timeout']


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-89', boundary='vault-timeout')
@pytest.mark.parametrize('service', ['generator', 'verifier', 'publisher', 'librarian', 'analyst'])
def test_slow_vault_is_504(mesh, sources, draft, service):
    """A slow Vault triggers the production timeout without writing artifacts."""
    trace, before = str(uuid4()), mesh.artifact_snapshot()
    attempts = 3 if service == 'librarian' else 1
    for _ in range(attempts):
        mesh.fault('vault', trace, method='GET', delay=6, body=sources[0])
    payload = {'record_id': sources[0]['id']}
    route = '/generate' if service == 'generator' else '/verify' if service == 'verifier' else '/publish'
    if service != 'generator':
        payload['draft'] = draft
    if service in {'librarian', 'analyst'}:
        route = '/search?q=Python' if service == 'librarian' else '/coverage'
    started = time.monotonic()
    mesh.request(service, 'GET' if service in {'librarian', 'analyst'} else 'POST', route,
                 expected=504, trace=trace, json=payload, timeout=25)
    assert 4 * attempts <= time.monotonic() - started < 8 * attempts + 4
    time.sleep(max(0, attempts * 5 + 1.2 - (time.monotonic() - started)))
    assert len(mesh.boundary_calls(trace)) == attempts
    assert not mesh.provider_calls(trace)
    assert mesh.artifact_snapshot() == before


@pytest.mark.contract(owner='Taha / Serhat', requirement='CF-89/91', boundary='provider-outage')
def test_stopped_provider_cannot_generate_verify_or_publish(mesh, sources, draft):
    """A real provider outage returns bounded 503 for every consumer and creates no artifact."""
    before = mesh.artifact_snapshot()
    with mesh.down('provider'):
        for service, route in [('generator', '/generate'), ('verifier', '/verify'), ('publisher', '/publish')]:
            payload = {'record_id': sources[0]['id']}
            if service != 'generator':
                payload['draft'] = draft
            started = time.monotonic()
            response = mesh.request(service, 'POST', route, expected=503, json=payload)
            assert 'detail' in response.json()
            assert time.monotonic() - started < 15
            assert mesh.artifact_snapshot() == before
    trace = str(uuid4())
    recovered = mesh.request('verifier', 'POST', '/verify', trace=trace,
                             json={'record_id': sources[0]['id'], 'draft': draft}).json()
    assert recovered['verdict'] == 'PASS'
    assert [call['stage'] for call in mesh.provider_calls(trace)] == ['assessment']


@pytest.mark.contract(owner='Taha', requirement='CF-89/100', boundary='provider-auth-rate-limit')
@pytest.mark.parametrize('service,stage,route', [('generator', 'translation', '/generate'),
                                               ('verifier', 'assessment', '/verify')])
@pytest.mark.parametrize('fault', ['unauthorized', 'rate_limited'])
def test_provider_auth_and_rate_failures_never_return_draft_or_pass(mesh, sources, draft, service, stage, route, fault):
    """Provider 401/429 become controlled 503 in both translation and direct verification."""
    trace = str(uuid4())
    mesh.arm_provider(fault, stage, trace)
    payload = {'record_id': sources[0]['id']}
    if service == 'verifier':
        payload['draft'] = draft
    response = mesh.request(service, 'POST', route, trace=trace, expected=503, json=payload)
    assert set(response.json()) == {'detail'}
    assert [call['fault'] for call in mesh.provider_calls(trace)] == [fault]


@pytest.mark.contract(owner='Kaan', requirement='CF-82/105', boundary='reader-storage-confirmation')
def test_reader_never_reports_conflicting_or_uncertain_storage_as_stored(mesh, sources):
    """Reader returns extracted facts but never reports conflicting or unconfirmed storage as successful."""
    from tests.support import closeout_pdf
    source = sources[0]
    path = '/engagements/' + source['id']
    original = mesh.request('vault', 'GET', path)
    changed = deepcopy(source)
    changed['challenge'] = 'Different source facts must not overwrite the existing engagement.'
    trace = str(uuid4())
    conflict = mesh.request('reader', 'POST', '/extract', trace=trace, files={
        'document': ('cf105-1.pdf', closeout_pdf(changed), 'application/pdf')})
    assert conflict.json()['challenge'] == changed['challenge']
    assert conflict.headers['X-Vault-Stored'] == 'false'
    assert conflict.headers['X-Vault-Detail'].startswith('conflict:')
    assert [call['status'] for call in mesh.boundary_calls(trace)] == [409, 200]
    trace = str(uuid4())
    mesh.fault('vault', trace, method='POST', status=503, body={'detail': 'synthetic unavailable'})
    mesh.fault('vault', trace, method='GET', status=503, body={'detail': 'synthetic unavailable'})
    uncertain = mesh.request('reader', 'POST', '/extract', trace=trace, files={
        'document': ('cf105-1.pdf', closeout_pdf(source), 'application/pdf')})
    assert uncertain.headers['X-Vault-Stored'] == 'false'
    assert 'could not be confirmed' in uncertain.headers['X-Vault-Detail']
    assert [call['status'] for call in mesh.boundary_calls(trace)] == [503, 503]
    current = mesh.request('vault', 'GET', path)
    assert current.json() == original.json() and current.headers['ETag'] == original.headers['ETag']
