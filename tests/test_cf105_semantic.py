import asyncio
from copy import deepcopy
from decimal import Decimal
import pytest
from fastapi import HTTPException
from common.drafts import normalize_draft, rendered_spans
from generator.core import generate_mcs
from verifier import semantic
from verifier.quantities import quantities, decimal_value
from tests.support import record, translated


@pytest.mark.parametrize('text,language', [('45%', 'en'), ('45 percent','en'), ('45 Prozent','de'), ('%45','tr'), ('yüzde 45','tr')])
def test_percent_formats_are_equivalent(text, language):
    quantity, = quantities(text, language)
    assert (quantity.value, quantity.unit) == (Decimal('45'), 'percent')


def test_units_and_ambiguity_are_conservative():
    assert quantities('90 minutes','en')[0].value == quantities('1,5 Stunden','de')[0].value
    assert quantities('11 months','en')[0].unit != quantities('11 days','en')[0].unit
    assert quantities('45 percentage points','en')[0].unit != quantities('45%','en')[0].unit
    with pytest.raises(ValueError): decimal_value('1.234')


@pytest.mark.parametrize('language', ['en','de','tr'])
def test_clean_quantities_and_consent_in_all_languages(language):
    source = record()
    assert semantic.deterministic_problems(translated(source,language), source, language) == []


@pytest.mark.parametrize('name', ['Synthetic  Example Bank 1', 'Synthetic-Example-Bank-1', 'SYNTHETIC EXAMPLE BANK 1'])
def test_name_variants_cannot_bypass_consent(name):
    source = record(); draft = generate_mcs(source)
    draft['titles'][0]['title'] = name
    assert any(p['type'] == 'client_named_without_consent' for p in semantic.deterministic_problems(draft,source,'en'))


def simple_draft():
    return normalize_draft({'sections': {'outcomes': 'Payment latency reduced by 45%'}}, record()['id'])


def assessment(draft):
    return semantic.Assessment(language_matches=True, spans=[semantic.SpanAssessment(
        id=item['id'], verdict='entailed', reason='',
        evidence=[semantic.Evidence(pointer='/outcomes/0/metric', quote='Payment latency reduced by 45%')])
        for item in rendered_spans(draft)])


def test_complete_evidence_is_required(monkeypatch):
    source=record(); draft=simple_draft()
    async def provider(*a, **k): return assessment(draft)
    monkeypatch.setattr(semantic, 'request_structured', provider)
    assert asyncio.run(semantic.check_semantics(draft,source,'en','trace')) == []


@pytest.mark.parametrize('kind', ['missing','duplicate','quote','whitespace','pointer','evidence'])
def test_invalid_model_evidence_never_authorizes(monkeypatch, kind):
    source=record(); draft=simple_draft(); result=assessment(draft)
    if kind=='missing': result.spans=[]
    if kind=='duplicate': result.spans.append(deepcopy(result.spans[0]))
    if kind=='quote': result.spans[0].evidence[0].quote='invented evidence'
    if kind=='whitespace': result.spans[0].evidence[0].quote=' '
    if kind=='pointer': result.spans[0].evidence[0].pointer='/absent'
    if kind=='evidence': result.spans[0].evidence=[]
    async def provider(*a, **k): return result
    monkeypatch.setattr(semantic, 'request_structured', provider)
    with pytest.raises(HTTPException) as caught: asyncio.run(semantic.check_semantics(draft,source,'en','trace'))
    assert caught.value.status_code == 502


def test_uncertain_or_wrong_language_blocks(monkeypatch):
    source=record(); draft=simple_draft(); result=assessment(draft)
    result.language_matches=False; result.spans[0].verdict='uncertain'
    async def provider(*a, **k): return result
    monkeypatch.setattr(semantic, 'request_structured', provider)
    problems=asyncio.run(semantic.check_semantics(draft,source,'en','trace'))
    assert {p['type'] for p in problems} == {'language_mismatch','unsupported_claim'}


def test_missing_model_key_is_an_error_not_a_verdict(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(semantic.check_semantics(simple_draft(),record(),'en','trace'))
    assert caught.value.status_code == 503
