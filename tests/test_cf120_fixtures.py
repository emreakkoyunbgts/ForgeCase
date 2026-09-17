"""Fixture drift and adversarial checks, independent of a running mesh."""
from copy import deepcopy

import pytest

from contract.fixtures.cases import (
    EVALUATION_IDS, EVIDENCE, LANGUAGES, MISSING_OUTCOME, NAMED_RECORD_ID,
    NAMED_SOURCE, RECORD_01_ID, SOURCE_01, SOURCES, SPANS, UnknownFixture,
)
from contract.provider_stub import assessment_response, translation_response
from evaluation.cf105_cases import sources


def spans_for(record_id=RECORD_01_ID, language='en'):
    return [{'id': span_id, 'text': text} for span_id, text in SPANS[record_id][language].items()]


def assessment_payload(source=SOURCE_01, language='en'):
    return {'language': language, 'source': deepcopy(source), 'spans': spans_for(source['id'], language)}


def translation_payload():
    return {'language': 'de', 'spans': spans_for(), 'may_be_named': False, 'technologies': ['Python']}


def test_independent_source_facts_match_the_evaluation_corpus():
    expected = {source['id']: source for source in sources()}
    assert len(EVALUATION_IDS) == 12
    assert {key: SOURCES[key] for key in EVALUATION_IDS} == expected
    assert set(SOURCES) == set(EVALUATION_IDS) | {NAMED_RECORD_ID}
    assert len({SPANS[key]['en']['/titles/0/title'] for key in SOURCES}) == len(SOURCES)


@pytest.mark.parametrize('record_id', (*EVALUATION_IDS, NAMED_RECORD_ID))
def test_every_declared_evidence_quote_resolves_to_the_actual_source(record_id):
    source = SOURCES[record_id]
    for span_id, pairs in EVIDENCE[record_id].items():
        assert span_id in SPANS[record_id]['en']
        for pointer, quote in pairs:
            value = source
            assert pointer.startswith('/')
            for component in pointer[1:].split('/'):
                component = component.replace('~1', '/').replace('~0', '~')
                value = value[int(component)] if isinstance(value, list) else value[component]
            assert isinstance(value, str)
            assert quote and quote in value
    assert set(EVIDENCE[record_id]) == set(SPANS[record_id]['en'])


@pytest.mark.parametrize('language', LANGUAGES)
def test_empty_outcomes_preserve_marker_and_have_no_invented_evidence(language):
    record_id = EVALUATION_IDS[-1]
    payload = assessment_payload(SOURCES[record_id], language)
    answer, actual_id = assessment_response(payload)
    assert actual_id == record_id
    assert not SOURCES[record_id]['outcomes']
    assert SPANS[record_id][language]['/sections/outcomes/0/outcomes'] == MISSING_OUTCOME
    assert not any(span_id.startswith('/citations/') for span_id in SPANS[record_id][language])
    outcome = next(item for item in answer['spans'] if item['id'] == '/sections/outcomes/0/outcomes')
    assert outcome['verdict'] == 'entailed' and outcome['evidence'] == []


@pytest.mark.parametrize('field,value', [
    ('client', 'An entirely different client'), ('client_type', 'unrelated operator'),
    ('domain', 'unrelated domain'), ('region', 'DE'), ('may_be_named', True),
    ('challenge', 'No processing problem existed.'), ('solution', 'Python was not used.'),
    ('technologies', ['Java']), ('outcomes', []), ('duration_months', 12),
    ('completed_at', '2026-01-01'), ('outcome_missing', True),
    ('may_be_named', 0), ('duration_months', 11.0),
])
def test_a_familiar_id_cannot_authorize_changed_source_facts(field, value):
    payload = assessment_payload()
    payload['source'][field] = value
    answer, _ = assessment_response(payload)
    assert answer['spans']
    assert {span['verdict'] for span in answer['spans']} == {'unsupported'}
    assert all(span['evidence'] == [] for span in answer['spans'])


def test_changed_reference_cannot_reuse_approved_fixture_evidence():
    payload = assessment_payload()
    payload['source']['outcomes'][0]['source_ref'] = 'unreviewed.pdf#page=1'
    answer, _ = assessment_response(payload)
    assert all(span['verdict'] == 'unsupported' for span in answer['spans'])


@pytest.mark.parametrize('record_id', EVALUATION_IDS)
def test_readers_derived_missing_flag_does_not_change_source_identity(record_id):
    payload = assessment_payload(SOURCES[record_id])
    payload['source']['outcome_missing'] = not payload['source']['outcomes']
    answer, _ = assessment_response(payload)
    assert all(span['verdict'] == 'entailed' for span in answer['spans'])


def test_unknown_submitted_span_is_returned_as_unsupported():
    payload = assessment_payload()
    payload['spans'].append({'id': '/titles/1/title', 'text': 'Invented second title'})
    answer, _ = assessment_response(payload)
    assert len(answer['spans']) == len(payload['spans'])
    assert answer['spans'][-1]['id'] == '/titles/1/title'
    assert answer['spans'][-1]['verdict'] == 'unsupported'
    assert answer['spans'][-1]['evidence'] == []


@pytest.mark.parametrize('mutation', ['prose', 'unknown_span', 'missing_span', 'duplicate_span',
                                      'consent', 'technology'])
def test_translation_refuses_to_repair_unreviewed_input(mutation):
    payload = translation_payload()
    if mutation == 'prose':
        payload['spans'][2]['text'] = 'An unreviewed assertion.'
    elif mutation == 'unknown_span':
        payload['spans'].append({'id': '/titles/1/title', 'text': 'Extra title'})
    elif mutation == 'missing_span':
        payload['spans'].pop()
    elif mutation == 'duplicate_span':
        payload['spans'].append(dict(payload['spans'][0]))
    elif mutation == 'consent':
        payload['may_be_named'] = True
    else:
        payload['technologies'] = ['Java']
    with pytest.raises(UnknownFixture):
        translation_response(payload)


def test_named_fixture_requires_the_same_explicit_consent():
    payload = assessment_payload(NAMED_SOURCE)
    answer, _ = assessment_response(payload)
    assert all(span['verdict'] == 'entailed' for span in answer['spans'])
    payload['source']['may_be_named'] = False
    rejected, _ = assessment_response(payload)
    assert all(span['verdict'] == 'unsupported' for span in rejected['spans'])
