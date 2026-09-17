import asyncio
from copy import deepcopy
import pytest
from fastapi import HTTPException
from common.drafts import rendered_spans
from generator.core import generate_mcs
from generator import translation
from tests.support import record, translated


@pytest.mark.parametrize('language', ['en', 'de', 'tr'])
def test_translation_preserves_metadata_and_every_span(monkeypatch, language):
    source=record(); draft=generate_mcs(source)
    expected=translated(source,language)
    async def provider(*args, **kwargs):
        return translation.Translation(spans=rendered_spans(expected))
    monkeypatch.setattr(translation, 'request_structured', provider)
    output=asyncio.run(translation.translate_draft(draft,source,language,'test-trace'))
    assert output['engagement_ids']==draft['engagement_ids']
    assert output['citations'][0]['source_ref']==draft['citations'][0]['source_ref']
    assert output['language']==language
    assert [s['text'] for s in rendered_spans(output)]==[s['text'] for s in rendered_spans(expected)]


@pytest.mark.parametrize('damage', ['missing','duplicate','empty','quantity','technology','name'])
def test_translation_rejects_invalid_provider_output(monkeypatch, damage):
    source=record(); draft=generate_mcs(source)
    spans=deepcopy(rendered_spans(draft))
    if damage=='missing':spans.pop()
    elif damage=='duplicate':spans.append(spans[0])
    elif damage=='empty':spans[0]['text']=''
    elif damage=='quantity':spans[-1]['text']='Latency fell by 99%.'
    elif damage=='name':spans[0]['text']=source['client']
    elif damage=='technology':
        next(s for s in spans if s['id'].startswith('/sections/technology/'))['text']='Java'
    async def provider(*args, **kwargs):return translation.Translation(spans=spans)
    monkeypatch.setattr(translation, 'request_structured', provider)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft,source,'en','test-trace'))
    assert exc.value.status_code==502


def provider_returning(monkeypatch, spans):
    async def provider(*args, **kwargs):
        return translation.Translation(spans=spans)
    monkeypatch.setattr(translation, 'request_structured', provider)


@pytest.mark.parametrize('replacement', [
    'Payment latency reduced.',
    'Payment latency reduced by forty-five percent.',
    'Payment latency reduced by 45%; payment latency reduced by 45%.',
    'Payment latency reduced by 45 percentage points.',
])
def test_translation_preserves_each_quantity_and_its_multiplicity(monkeypatch, replacement):
    source = record()
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    next(item for item in spans if item['id'].startswith('/sections/outcomes/'))['text'] = replacement
    provider_returning(monkeypatch, spans)
    with pytest.raises(HTTPException, match='quantity') as exc:
        asyncio.run(translation.translate_draft(draft, source, 'en', 'test-trace'))
    assert exc.value.status_code == 502


def test_a_quantity_from_another_source_metric_cannot_replace_this_span(monkeypatch):
    source = record()
    source['outcomes'].append({'metric': 'Queue length reduced by 30%',
                               'source_ref': 'synthetic.pdf#page=2'})
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    # Both values exist in the source and both are retained in the document,
    # but each individual citation is now bound to the other metric's value.
    spans_by_id = {item['id']: item for item in spans}
    spans_by_id['/citations/0/claim']['text'] = 'Payment latency reduced by 30%'
    spans_by_id['/citations/1/claim']['text'] = 'Queue length reduced by 45%'
    provider_returning(monkeypatch, spans)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft, source, 'en', 'test-trace'))
    assert exc.value.status_code == 502


@pytest.mark.parametrize('language,text', [
    ('en', 'Payment latency fell by 45 percent; processing lasted 1.5 hours.'),
    ('de', 'Die Zahlungslatenz sank um 45 Prozent; die Verarbeitung dauerte 1,5 Stunden.'),
    ('tr', 'Ödeme gecikmesi yüzde 45 azaldı; işlem 1,5 saat sürdü.'),
    ('tr', 'Ödeme gecikmesi %45 azaldı; işlem 90 dakika sürdü.'),
])
def test_equivalent_localized_quantities_and_duration_units_are_preserved(monkeypatch, language, text):
    source = record()
    source['outcomes'][0]['metric'] = 'Payment latency fell by 45%; processing lasted 90 minutes.'
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    for item in spans:
        if item['id'].startswith(('/sections/outcomes/', '/citations/')):
            item['text'] = text
    provider_returning(monkeypatch, spans)
    actual = asyncio.run(translation.translate_draft(draft, source, language, 'test-trace'))
    assert actual['sections']['outcomes'][0]['outcomes'] == text
    assert actual['citations'][0]['claim'] == text


def test_ambiguous_quantity_cannot_be_returned_as_a_successful_translation(monkeypatch):
    source = record()
    source['outcomes'][0]['metric'] = 'Processed 1234 payments.'
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    next(item for item in spans if item['id'].startswith('/sections/outcomes/'))['text'] = 'Processed 1,23 payments.'
    provider_returning(monkeypatch, spans)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft, source, 'en', 'test-trace'))
    assert exc.value.status_code == 502


def test_missing_outcome_marker_is_kept_verbatim(monkeypatch):
    source = record()
    source['outcomes'] = []
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    provider_returning(monkeypatch, spans)
    actual = asyncio.run(translation.translate_draft(draft, source, 'tr', 'test-trace'))
    assert actual['sections']['outcomes'] == draft['sections']['outcomes']
    next(item for item in spans if item['id'].startswith('/sections/outcomes/'))['text'] = '[MISSING: translated marker]'
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft, source, 'tr', 'test-trace'))
    assert exc.value.status_code == 502


def test_an_authorized_client_name_cannot_be_omitted(monkeypatch):
    source = record()
    source['client'] = 'Example Bank'
    source['may_be_named'] = True
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    provider_returning(monkeypatch, spans)
    actual = asyncio.run(translation.translate_draft(draft, source, 'en', 'test-trace'))
    assert 'Example Bank' in actual['titles'][0]['title']
    spans[0]['text'] = spans[0]['text'].replace('Example Bank', 'a bank')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft, source, 'en', 'test-trace'))
    assert exc.value.status_code == 502


@pytest.mark.parametrize('text', ['yüzde 45 puan', '%45 puan', 'yüzde 45 puanlık'])
def test_turkish_percentage_points_are_not_relative_percentages(monkeypatch, text):
    source = record()
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    next(item for item in spans if item['id'].startswith('/sections/outcomes/'))['text'] = text
    provider_returning(monkeypatch, spans)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(translation.translate_draft(draft, source, 'tr', 'test-trace'))
    assert exc.value.status_code == 502

    source['outcomes'][0]['metric'] = 'Payment success rate improved by 45 percentage points.'
    draft = generate_mcs(source)
    spans = deepcopy(rendered_spans(draft))
    for item in spans:
        if item['id'].startswith(('/sections/outcomes/', '/citations/')):
            item['text'] = text
    provider_returning(monkeypatch, spans)
    actual = asyncio.run(translation.translate_draft(draft, source, 'tr', 'test-trace'))
    assert actual['sections']['outcomes'][0]['outcomes'] == text
