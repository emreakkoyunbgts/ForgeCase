"""CF-120 step 2: the synthetic provider over the real SDK wire.

Needs no seven-service mesh or external network, so it belongs in the default suite. Calling the
pure responder functions would not prove wire compatibility, so every case here
drives a real socket: uvicorn serves the stub, the production
common/structured_llm.py builds a real AsyncOpenAI client against it, and the
real guards in generator/translation.py and verifier/semantic.py judge the
answer.
"""
import asyncio
import ast
from copy import deepcopy
import hashlib
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn
from fastapi import HTTPException

from contract.provider_stub import create_app
from contract.fixtures.cases import (
    EVALUATION_IDS, LANGUAGES, NAMED_SOURCE, RECORD_01_ID, SOURCE_01, SOURCES, SPANS,
)
from common.drafts import display_case_study, normalize_draft, rendered_spans
from generator.core import generate_mcs
from generator.translation import translate_draft
from publisher.publisher import prepare_display_values
from verifier.semantic import check_semantics, deterministic_problems

TRACE = 'cf120-selftest-trace'


@pytest.fixture(scope='module')
def stub():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    # Pass the owned socket to uvicorn; releasing and rebinding would race.
    server = uvicorn.Server(uvicorn.Config(create_app(), host='127.0.0.1', port=port,
                                           log_level='warning', timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [probe]}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 30
        while not server.started and time.monotonic() < deadline:
            if not thread.is_alive():
                raise RuntimeError('stub provider thread died during startup')
            time.sleep(0.05)
        assert server.started, 'stub provider did not start'
        base = 'http://127.0.0.1:%d' % port
        assert requests.get(base + '/health', timeout=5).json()['real_model'] is False
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        probe.close()
        assert not thread.is_alive(), 'stub provider thread survived cleanup'


@pytest.fixture(autouse=True)
def provider_env(stub, monkeypatch):
    """Point the production provider wrapper at the stub, exactly as the runner does."""
    monkeypatch.setenv('OPENAI_API_KEY', 'cf120-synthetic-provider-key')
    monkeypatch.setenv('OPENAI_BASE_URL', stub + '/v1')
    monkeypatch.setenv('OPENAI_CUSTOM_HEADERS', '')
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    monkeypatch.setenv('GENERATOR_TRANSLATION_MODEL', 'cf120-stub-translation')
    monkeypatch.setenv('VERIFIER_SEMANTIC_MODEL', 'cf120-stub-assessment')
    assert requests.post(stub + '/__reset', timeout=5).status_code == 200
    yield
    assert requests.post(stub + '/__reset', timeout=5).status_code == 200


def arm(stub, fault, stage='any', correlation_id=TRACE):
    response = requests.post(stub + '/__control', json={
        'fault': fault, 'stage': stage, 'correlation_id': correlation_id},
                             timeout=5)
    assert response.status_code == 200, response.text
    return response


def translate(language, source=SOURCE_01, trace=TRACE):
    return asyncio.run(translate_draft(generate_mcs(source), source, language, trace))


def test_stub_never_imports_the_code_under_test():
    """A double that computed its answer with the real code would prove nothing."""
    root = Path(__file__).resolve().parents[1]
    allowed = {'asyncio', 'copy', 'hashlib', 'json', 're', 'uuid', 'fastapi',
               'fastapi.responses', 'contract.fixtures.cases'}
    for relative in ('contract/provider_stub.py', 'contract/fixtures/cases.py'):
        tree = ast.parse((root / relative).read_text(encoding='utf-8'))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, 'relative imports obscure fixture dependencies'
                imports.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {'__import__', 'eval', 'exec'}, 'dynamic code obscures fixture dependencies'
        assert imports <= (allowed if 'provider_stub' in relative else set()), (relative, imports)


@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('record_id', EVALUATION_IDS)
def test_clean_draft_passes_both_real_guards(stub, language, record_id):
    source = SOURCES[record_id]
    translated = translate(language, source)
    assert translated['language'] == language
    assert {span['id']: span['text'] for span in rendered_spans(translated)} == SPANS[record_id][language]
    assert deterministic_problems(translated, source, language) == []
    assert asyncio.run(check_semantics(translated, source, language, TRACE)) == []
    stages = [call['stage'] for call in requests.get(stub + '/__calls', timeout=5).json()['calls']]
    assert stages == ['translation', 'assessment']


@pytest.mark.parametrize('language', LANGUAGES)
def test_translated_prose_matches_the_reviewed_fixture(language):
    spans = {span['id']: span['text'] for span in rendered_spans(translate(language))}
    assert spans == SPANS[RECORD_01_ID][language]


@pytest.mark.parametrize('language', ['de', 'tr'])
def test_non_english_output_is_not_english(language):
    translated = {span['id']: span['text'] for span in rendered_spans(translate(language))}
    english = SPANS[RECORD_01_ID]['en']
    differing = [key for key in english if translated[key] != english[key]]
    # 'Python' is a proper noun and legitimately identical in all three languages.
    assert len(differing) >= len(english) - 1


@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('record_id', EVALUATION_IDS)
def test_publisher_final_display_reaches_the_same_spans(stub, language, record_id):
    """Publisher re-verifies its prepared display content, not the submitted draft.

    If these span ids or texts diverged, the fixture would have to cover a
    second shape. publisher/service.py builds its gate payload this way before
    calling the Verifier, so the suite pins the equality instead of assuming it.
    """
    source = SOURCES[record_id]
    draft = translate(language, source)
    flat = display_case_study(draft, record_id, language)
    prepared = prepare_display_values(flat, source)
    final = {**flat, 'title': prepared['title'], 'sections': {
        'context': prepared['client_type'],
        **{name: prepared[name] for name in ('challenge', 'approach', 'technology', 'outcomes')},
    }}
    canonical = normalize_draft(final, record_id, language)
    assert rendered_spans(canonical) == rendered_spans(draft)
    assert asyncio.run(check_semantics(canonical, source, language, TRACE)) == []


@pytest.mark.parametrize('fault', [
    'incomplete_spans', 'empty_translation', 'changed_quantity', 'changed_marker',
    'incomplete_status', 'server_error', 'unparsable',
    'duplicate_spans', 'invalid_schema', 'empty_output',
])
def test_translation_faults_are_rejected(stub, fault):
    arm(stub, fault, 'translation')
    with pytest.raises(HTTPException) as caught:
        translate('en')
    assert caught.value.status_code == 502
    assert requests.get(stub + '/__calls', timeout=5).json()['armed_unused'] == []


@pytest.mark.parametrize('fault', [
    'incomplete_spans', 'fabricated_evidence', 'incomplete_status', 'server_error',
    'unparsable',
    'duplicate_spans', 'omitted_evidence', 'invalid_schema', 'empty_output',
])
def test_assessment_faults_are_rejected(stub, fault):
    translated = translate('en')
    arm(stub, fault, 'assessment')
    with pytest.raises(HTTPException) as caught:
        asyncio.run(check_semantics(translated, SOURCE_01, 'en', TRACE))
    assert caught.value.status_code == 502


def test_unsupported_verdict_blocks_rather_than_errors(stub):
    """A negative provider decision must surface as problems, not as an HTTP error.

    HTTP errors are not verdicts and cannot authorize or deny publication, so
    the BLOCK path has to come back as a normal result carrying problems.
    """
    translated = translate('en')
    arm(stub, 'unsupported_verdict', 'assessment')
    problems = asyncio.run(check_semantics(translated, SOURCE_01, 'en', TRACE))
    assert problems
    assert {problem['type'] for problem in problems} == {'unsupported_claim'}


def test_edited_prose_is_not_entailed(stub):
    """The stub grounds against fixture text, so an edit becomes a real BLOCK."""
    translated = translate('en')
    poisoned = json.loads(json.dumps(translated))
    poisoned['sections']['outcomes'][0]['outcomes'] = 'Operating cost reduced by 45%.'
    problems = deterministic_problems(poisoned, SOURCE_01, 'en')
    problems.extend(asyncio.run(check_semantics(poisoned, SOURCE_01, 'en', TRACE)))
    assert problems, 'a swapped metric must not be reported as grounded'


def test_unknown_fixture_content_is_refused(stub):
    """Silence on unknown content would let an unreviewed expectation pass."""
    stranger = {**SOURCE_01, 'id': 'eng-not-in-fixtures'}
    draft = normalize_draft(generate_mcs(stranger), stranger['id'], 'en')
    with pytest.raises(HTTPException) as caught:
        asyncio.run(check_semantics(draft, stranger, 'en', TRACE))
    assert caught.value.status_code == 502


def test_correlation_id_reaches_the_provider_hop(stub):
    """The provider call is the one hop no existing test covers."""
    translate('en')
    calls = requests.get(stub + '/__calls', timeout=5).json()['calls']
    assert calls and all(call['correlation_id'] == TRACE for call in calls)


@pytest.mark.parametrize('language', LANGUAGES)
def test_named_source_preserves_explicit_consent(stub, language):
    draft = translate(language, NAMED_SOURCE)
    assert NAMED_SOURCE['client'] in draft['titles'][0]['title']
    assert draft['client_named'] is True
    assert deterministic_problems(draft, NAMED_SOURCE, language) == []
    assert asyncio.run(check_semantics(draft, NAMED_SOURCE, language, TRACE)) == []


@pytest.mark.parametrize('fault', ['unauthorized', 'rate_limited'])
@pytest.mark.parametrize('stage', ['translation', 'assessment'])
def test_provider_unavailability_is_recorded_without_retries(stub, fault, stage):
    draft = translate('en') if stage == 'assessment' else None
    arm(stub, fault, stage)
    with pytest.raises(HTTPException) as caught:
        if draft is None:
            translate('en')
        else:
            asyncio.run(check_semantics(draft, SOURCE_01, 'en', TRACE))
    assert caught.value.status_code == 503
    matching = [call for call in requests.get(stub + '/__calls', timeout=5).json()['calls']
                if call['fault'] == fault]
    assert len(matching) == 1
    assert matching[0]['status'] == (401 if fault == 'unauthorized' else 429)


def test_fault_matches_trace_and_stage_and_is_consumed_once(stub):
    arm(stub, 'server_error', 'assessment', correlation_id='selected-trace')
    draft = translate('en', trace='selected-trace')
    assert asyncio.run(check_semantics(draft, SOURCE_01, 'en', 'other-trace')) == []
    assert requests.get(stub + '/__calls', timeout=5).json()['armed_unused'] == ['server_error']
    with pytest.raises(HTTPException) as caught:
        asyncio.run(check_semantics(draft, SOURCE_01, 'en', 'selected-trace'))
    assert caught.value.status_code == 502
    assert asyncio.run(check_semantics(draft, SOURCE_01, 'en', 'selected-trace')) == []
    log = requests.get(stub + '/__calls', timeout=5).json()
    assert log['armed_unused'] == []
    assert [call['fault'] for call in log['calls']] == [None, None, 'server_error', None]


def test_assessment_telemetry_captures_submitted_source_and_spans(stub):
    draft = translate('en')
    assert asyncio.run(check_semantics(draft, SOURCE_01, 'en', TRACE)) == []
    log = requests.get(stub + '/__calls', timeout=5).json()
    call = log['calls'][-1]
    payload = {'language': 'en', 'source': SOURCE_01, 'spans': rendered_spans(draft)}
    expected_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
    assert call['source'] == SOURCE_01
    assert call['spans'] == rendered_spans(draft)
    assert call['payload_sha256'] == expected_hash
    assert log['dropped_calls'] == 0


def test_changed_source_never_reuses_a_clean_fixture_assessment(stub):
    draft = translate('en')
    changed = deepcopy(SOURCE_01)
    changed['solution'] = 'Python was considered but was not used.'
    problems = asyncio.run(check_semantics(draft, changed, 'en', TRACE))
    assert problems and all(item['type'] == 'unsupported_claim' for item in problems)


def test_language_mismatch_is_a_block_problem(stub):
    draft = translate('en')
    arm(stub, 'language_mismatch', 'assessment')
    problems = asyncio.run(check_semantics(draft, SOURCE_01, 'en', TRACE))
    assert [item['type'] for item in problems] == ['language_mismatch']


def test_delay_fault_exercises_real_sdk_timeout_and_leaves_server_responsive(stub, monkeypatch):
    from common import structured_llm
    from contract import provider_stub
    # Full mesh acceptance waits the actual 60-second production limit. This
    # unit case uses the same socket/SDK path with shorter test-only budgets.
    monkeypatch.setattr(structured_llm, 'PROVIDER_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(provider_stub, 'DELAY_SECONDS', 0.6)
    arm(stub, 'timeout', 'translation')
    with pytest.raises(HTTPException) as caught:
        translate('en')
    assert caught.value.status_code == 504
    monkeypatch.setattr(structured_llm, 'PROVIDER_TIMEOUT_SECONDS', 5)
    assert translate('en')['language'] == 'en'
    calls = requests.get(stub + '/__calls', timeout=5).json()['calls']
    assert [call['fault'] for call in calls] == ['timeout', None]


@pytest.mark.parametrize('body', [None, [], {'fault': 'unknown'}, {'fault': 'timeout', 'stage': 'publish'},
                                      {'fault': 'timeout', 'correlation_id': 1}])
def test_invalid_control_is_rejected_without_arming(stub, body):
    response = requests.post(stub + '/__control', json=body, timeout=5)
    assert response.status_code == 422
    assert requests.get(stub + '/__calls', timeout=5).json()['armed'] == []
