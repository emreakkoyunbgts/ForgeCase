import io
from pathlib import Path
from copy import deepcopy
import pytest
import requests
from fastapi.testclient import TestClient
from reader import api
from reader.extraction import build_record
from reader.reader import ExtractionError
from tests.support import closeout_pdf, record, response


@pytest.fixture
def client(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Reader attempted a fixture, OCR or model fallback')
    import common.contract
    import reader.reader
    monkeypatch.setattr(common.contract, 'load_seed', forbidden)
    monkeypatch.setattr(common.contract, 'load_corpus', forbidden)
    monkeypatch.setattr(reader.reader, 'extract_text', forbidden)
    monkeypatch.setattr(api.requests, 'post', lambda *a, **k: response(status=201))
    monkeypatch.setattr(api.requests, 'get', lambda *a, **k: response(status=404))
    return TestClient(api.create_app())


@pytest.mark.parametrize('index', [1, 2])
def test_actual_pdf_facts_and_identity_are_extracted(client, index):
    source = record(index)
    result = client.post('/extract', files={'document': ('synthetic.pdf', closeout_pdf(source), 'application/pdf')},
                         headers={'X-Correlation-ID': 'reader-trace'})
    assert result.status_code == 200, result.text
    extracted = result.json()
    for key in source:
        assert extracted[key] == source[key]
    assert result.headers['X-Vault-Stored'] == 'true'
    assert result.headers['X-Correlation-ID'] == 'reader-trace'


def test_missing_outcomes_are_not_invented(client):
    source = record(); source['outcomes'] = []
    result = client.post('/extract?store=false', files={'document': ('no-outcomes.pdf', closeout_pdf(source), 'application/pdf')})
    assert result.status_code == 200
    assert result.json()['outcomes'] == []
    assert result.json()['outcome_missing'] is True


@pytest.mark.parametrize('header', ['Client: Different Client', 'Region: DE', 'Duration: 11 or 12 months'])
def test_same_page_conflicts_and_ambiguous_duration_are_rejected(client, header):
    result=client.post('/extract?store=false', files={'document':
        ('conflict.pdf',closeout_pdf(record(),[header]),'application/pdf')})
    assert result.status_code==422
    assert any(word in result.json()['detail'] for word in ['conflicting', 'ambiguous'])


def test_explicit_duration_is_retained(client):
    source=record(); source['duration_months']=11
    result=client.post('/extract?store=false',files={'document':('duration.pdf',closeout_pdf(source),'application/pdf')})
    assert result.status_code==200
    assert result.json()['duration_months']==11


def test_existing_two_column_closeout_is_supported(client):
    path=Path('reader/fixtures/two_column_closeout.pdf')
    result=client.post('/extract?store=false',files={'document':(path.name,path.read_bytes(),'application/pdf')})
    assert result.status_code==200,result.text
    assert result.json()['duration_months']==11
    assert len(result.json()['outcomes'])==3


@pytest.mark.parametrize('filename',['ruled_table_closeout.pdf','unruled_table_closeout.pdf'])
def test_layout_only_fixtures_cannot_fill_missing_required_sections(client,filename):
    path=Path('reader/fixtures')/filename
    result=client.post('/extract?store=false',files={'document':(filename,path.read_bytes(),'application/pdf')})
    assert result.status_code==422
    assert 'approach' in result.json()['detail']


@pytest.mark.parametrize('content', [b'', b'not a PDF'])
def test_invalid_upload_never_writes_vault(client, monkeypatch, content):
    monkeypatch.setattr(api.requests, 'post', lambda *a, **k: pytest.fail('Invalid record was stored'))
    assert client.post('/extract', files={'document': ('bad.pdf', content, 'application/pdf')}).status_code == 422


def test_scan_is_explicitly_unsupported(client):
    from reportlab.pdfgen import canvas
    data = io.BytesIO(); pdf = canvas.Canvas(data); pdf.showPage(); pdf.save()
    result = client.post('/extract', files={'document': ('scan.pdf', data.getvalue(), 'application/pdf')})
    assert result.status_code == 422
    assert 'text-layer' in result.json()['detail']


def test_timeout_reconciles_before_one_bounded_retry(monkeypatch):
    source = record(); attempts = []
    def send(*args, **kwargs):
        attempts.append(kwargs['headers'])
        if len(attempts) == 1: raise requests.Timeout()
        return response(status=201)
    monkeypatch.setattr(api.requests, 'post', send)
    monkeypatch.setattr(api.requests, 'get', lambda *a, **k: response(status=404))
    delays = []; monkeypatch.setattr(api.time, 'sleep', delays.append)
    assert api.store_in_vault(source) == (True, 'created')
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert delays == [0.5]


@pytest.mark.parametrize('same', [True, False])
def test_duplicate_id_requires_matching_facts(monkeypatch, same):
    source = record(); existing = deepcopy(source)
    if not same: existing['solution'] = 'Different source facts'
    monkeypatch.setattr(api.requests, 'post', lambda *a, **k: response(status=409))
    monkeypatch.setattr(api.requests, 'get', lambda *a, **k: response(existing))
    stored, detail = api.store_in_vault(source)
    assert stored is same
    assert ('confirmed' if same else 'conflict') in detail
