"""Contract suite is opt-in and can only attach to its runner's manifest."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from contract.client import Client, capture_request_traces
from contract.evidence import save_json

STATE = {'collected': [], 'results': [], 'errors': [], 'session_finished': False}
REPORTS = {}
REQUEST_TRACES = {}
METADATA_KEYS = ('owner', 'requirement', 'boundary', 'assertion')


def pytest_configure(config):
    config.addinivalue_line('markers', 'contract(owner, requirement, boundary): CF-120 boundary metadata')
    if not config.option.collectonly and not os.getenv('CF120_MANIFEST'):
        raise pytest.UsageError('Use python scripts/contract_mesh.py; no owned CF120_MANIFEST was supplied')


def case_metadata(item):
    marker = item.get_closest_marker('contract')
    metadata = dict(marker.kwargs) if marker else {}
    doc = (getattr(item.function, '__doc__', None) or '').strip()
    if doc:
        metadata['assertion'] = doc.splitlines()[0]
    return metadata


def pytest_collection_finish(session):
    STATE['collected'] = [item.nodeid for item in session.items]
    STATE['metadata'] = {item.nodeid: case_metadata(item) for item in session.items}
    unowned = [nodeid for nodeid, metadata in STATE['metadata'].items()
               if any(not metadata.get(key) for key in METADATA_KEYS)]
    if unowned:
        # An inventory entry without owner/requirement/boundary cannot be triaged.
        raise pytest.UsageError('Contract cases need @pytest.mark.contract(owner, requirement, '
                                'boundary): ' + ', '.join(unowned))
    target = os.getenv('CF120_INVENTORY_OUT')
    if target and session.config.option.collectonly:
        save_json(target, {'kind': 'cf120-contract-inventory', 'version': 1,
                           'cases': STATE['metadata']})


def pytest_collectreport(report):
    if report.failed:
        STATE['errors'].append({'phase': 'collection', 'nodeid': report.nodeid,
                                'reason': str(report.longrepr), 'owner': 'CF-120 harness'})


def capture_phase(item, phase):
    with capture_request_traces() as entries:
        try:
            yield
        finally:
            REQUEST_TRACES.setdefault(item.nodeid, {})[phase] = list(entries)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    yield from capture_phase(item, 'setup')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    yield from capture_phase(item, 'call')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    yield from capture_phase(item, 'teardown')


def pytest_runtest_logreport(report):
    result = REPORTS.setdefault(report.nodeid, {'nodeid': report.nodeid, 'outcome': 'passed',
                                               'duration': 0, 'phases': {}})
    metadata = STATE.get('metadata', {}).get(report.nodeid, {})
    result.update({key: metadata[key] for key in METADATA_KEYS if key in metadata})
    result['request_traces'] = [
        {'phase': phase, **entry}
        for phase, entries in REQUEST_TRACES.get(report.nodeid, {}).items() for entry in entries
    ]
    result['trace_ids'] = sorted({entry['trace_id'] for entry in result['request_traces']})
    result['services'] = sorted({entry['service'] for entry in result['request_traces']})
    outcome = report.outcome
    if hasattr(report, 'wasxfail'):
        outcome = 'xpassed' if report.passed else 'xfailed'
    result['duration'] += report.duration
    result['phases'][report.when] = outcome
    if outcome != 'passed':
        result.update(outcome=outcome, phase=report.when, reason=str(report.longrepr))
    STATE['results'] = list(REPORTS.values())
    path = os.getenv('CF120_SESSION_REPORT')
    # Once per test (or at once on a failure) so an aborted session still leaves a report.
    if path and (report.when == 'teardown' or outcome != 'passed'):
        save_json(path, STATE)


def pytest_sessionfinish(session, exitstatus):
    STATE['session_finished'] = True
    STATE['exit_code'] = int(exitstatus)
    path = os.getenv('CF120_SESSION_REPORT')
    if path:
        save_json(path, STATE)


@pytest.fixture(scope='session')
def mesh():
    config = json.loads(Path(os.environ['CF120_MANIFEST']).read_text(encoding='utf-8'))
    for name, url in config['addresses'].items():
        if name != 'provider':
            assert os.environ[name.upper() + '_URL'] == url, 'Service environment drift'
    client = Client(config)
    yield client
    client.close()


@pytest.fixture(scope='session')
def sources(mesh):
    """The twelve evaluation sources, uploaded once through the real Reader."""
    from contract.fixtures.cases import SOURCES
    from tests.support import closeout_pdf
    records = [deepcopy(SOURCES[f'eng-cf105-{i:02d}']) for i in range(1, 13)]
    for i, source in enumerate(records, 1):
        result = mesh.request('reader', 'POST', '/extract', files={
            'document': (f'cf105-{i}.pdf', closeout_pdf(source), 'application/pdf')})
        assert result.headers['X-Vault-Stored'] == 'true'
        assert result.headers['X-Vault-Detail'] == 'created'
        # Reader derives outcome_missing; every other stored fact is the fixture.
        assert result.json() == {**source, 'outcome_missing': not source['outcomes']}
        stored = mesh.request('vault', 'GET', '/engagements/' + source['id']).json()
        assert stored == {**source, 'outcome_missing': not source['outcomes']}
    return records


@pytest.fixture
def draft(mesh, sources):
    """A fresh draft per test prevents one poison from contaminating another case."""
    return mesh.request('generator', 'POST', '/generate',
                        json={'record_id': sources[0]['id'], 'language': 'en'}).json()
