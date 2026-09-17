"""Real HTTP route contracts with explicitly injected offline model providers."""
import asyncio
from contextlib import ExitStack
from copy import deepcopy
from io import BytesIO
from urllib.parse import urlsplit

import httpx
import pdfplumber
import pytest
import requests
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient

from common.drafts import SECTION_FIELDS, rendered_spans
from console.workflow import Workflow
from generator import GeneratorController as generator
from generator.translation import get_translator
from publisher import service as publisher
from reader import api as reader
from vault import vault
from verifier import VerifierController as verifier
from verifier.semantic import get_semantic_checker
from common.source import get_vault_client
from tests.support import closeout_pdf, record, translated


@pytest.fixture
def mesh(monkeypatch, tmp_path):
    monkeypatch.setattr(vault, 'DB_PATH', str(tmp_path/'vault.db'))
    monkeypatch.setenv('CASEFORGE_ARTIFACT_DIR', str(tmp_path/'artifacts'))
    monkeypatch.setenv('CASEFORGE_TOKEN', 'synthetic-test-token')
    import common.services
    for name in common.services.ALL_SERVICES:
        url='http://' + name + '.test.invalid'
        monkeypatch.setenv(name.upper() + '_URL', url)
        monkeypatch.setitem(common.services.ALL_SERVICES, name, url)
    monkeypatch.setattr(reader, 'VAULT_URL', common.services.ALL_SERVICES['vault'])
    source=record()
    observed=[]

    async def translator(draft, original, language, trace):
        observed.append(('translation', language, trace))
        return translated(original, language)

    async def checker(draft, original, language, trace):
        observed.append(('semantic', language, trace))
        expected = {item['text'] for item in rendered_spans(translated(original,language))}
        return [{'type':'unsupported_claim','value':span['text'],'why':'Synthetic labelled fixture rejects this claim'}
                for span in rendered_spans(draft) if span['text'] not in expected]

    vault_app=vault.create_app()
    async def source_client():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=vault_app)) as connection:
            yield connection
    previous_generator=generator.app.dependency_overrides.copy()
    previous_verifier=verifier.app.dependency_overrides.copy()
    generator.app.dependency_overrides[get_vault_client]=source_client
    generator.app.dependency_overrides[get_translator]=lambda:translator
    verifier.app.dependency_overrides[get_vault_client]=source_client
    verifier.app.dependency_overrides[get_semantic_checker]=lambda:checker
    apps={'vault':vault_app, 'reader':reader.create_app(), 'generator':generator.app,
          'verifier':verifier.app,'publisher':publisher.app}
    with ExitStack() as stack:
        clients={name:stack.enter_context(TestClient(app)) for name,app in apps.items()}
        def transport(method,url,**kwargs):
            address=urlsplit(url); name=address.hostname.split('.')[0]
            observed.append((name, method.upper(), kwargs.get('headers',{}).get('X-Correlation-ID')))
            kwargs.pop('timeout',None)
            kwargs.pop('allow_redirects',None)
            return clients[name].request(method,address.path,**kwargs)
        monkeypatch.setattr(requests,'request',transport)
        monkeypatch.setattr(requests,'post',lambda url,**kw:transport('POST',url,**kw))
        monkeypatch.setattr(requests,'get',lambda url,**kw:transport('GET',url,**kw))
        import common.contract
        def no_file(*a,**k):pytest.fail('Runtime attempted seed/corpus access')
        monkeypatch.setattr(common.contract,'load_seed',no_file)
        monkeypatch.setattr(common.contract,'load_corpus',no_file)
        try:
            yield clients, source, observed, tmp_path
        finally:
            generator.app.dependency_overrides.clear();generator.app.dependency_overrides.update(previous_generator)
            verifier.app.dependency_overrides.clear();verifier.app.dependency_overrides.update(previous_verifier)


def test_private_client_name_in_source_filename_blocks_artifact(mesh):
    clients, source, _, directory = mesh
    source['outcomes'][0]['source_ref'] = source['client'] + '.pdf#page=1'
    headers={'Authorization':'Bearer synthetic-test-token'}
    clients['vault'].post('/engagements',json=source,headers=headers)
    draft=translated(source,'en')
    payload={'record_id':source['id'],'draft':draft,'language':'en'}
    result=clients['verifier'].post('/verify',json=payload,headers=headers)
    assert result.json()['verdict']=='BLOCK'
    assert clients['publisher'].post('/publish',json=payload,headers=headers).status_code==422
    assert not (directory/'artifacts').exists()


def test_repeated_publication_click_reuses_this_sessions_artifact(mesh):
    _, source, observed, _ = mesh
    flow=Workflow()
    flow.extract('synthetic.pdf',closeout_pdf(source))
    flow.generate();flow.verify();flow.approve(True)
    first=flow.publish()
    assert flow.publish()==first
    assert sum(1 for event in observed if event[0:2]==('publisher','POST'))==1
    flow._publish_lock.acquire()
    try:
        from common.services import ServiceError
        with pytest.raises(ServiceError, match='already in progress'):
            flow.publish()
    finally:
        flow._publish_lock.release()


@pytest.mark.parametrize('language',['en','de','tr'])
@pytest.mark.parametrize('format,layout',[('docx','full-case-study'),('pdf','full-case-study'),('pdf','one-pager'),('pdf','single-slide')])
def test_complete_http_workflow_downloads_exact_unicode_content(mesh, language, format, layout):
    clients,source,observed,_=mesh
    flow=Workflow(language=language)
    flow.extract('synthetic.pdf',closeout_pdf(source))
    flow.generate(); assert flow.verify()['verdict']=='PASS'
    flow.approve(True); metadata=flow.publish(format,layout)
    content=flow.download()
    if format=='docx':
        doc=Document(BytesIO(content)); text='\n'.join(p.text for p in doc.paragraphs)
    else:
        with pdfplumber.open(BytesIO(content)) as pdf:
            text='\n'.join(page.extract_text() or '' for page in pdf.pages)
            if layout!='full-case-study':assert len(pdf.pages)==1
    for span in rendered_spans(flow.draft):
        assert ' '.join(span['text'].split()) in ' '.join(text.split())
    assert source['client'] not in text
    assert '{{' not in text
    assert metadata['download_url'].startswith('/artifacts/')
    assert 'path' not in metadata
    assert all(item[2]==flow.trace for item in observed)
    assert len([item for item in observed if item[0]=='semantic'])==2
    assert flow.download(provenance=True)


@pytest.mark.parametrize('language',['en','de','tr'])
def test_edit_and_language_change_clear_pass_and_approval(mesh, language):
    flow=Workflow(language=language);flow.extract('synthetic.pdf',closeout_pdf(record()))
    flow.generate();flow.verify();flow.approve(True)
    changed=deepcopy(flow.draft)
    changed['sections']['outcomes'][0]['outcomes']='Saved 777%'
    flow.edit(changed)
    assert not flow.verified and not flow.approved and flow.artifact is None
    with pytest.raises(ValueError):flow.publish()
    assert flow.verify()['verdict']=='BLOCK'
    flow.select(flow.record_id,'tr' if language!='tr' else 'en')
    assert flow.draft is None and not flow.approved


@pytest.mark.parametrize('bad_report',[
    {'engagement_id':'eng-cf105-01','verdict':'UNKNOWN','problems':[]},
    {'engagement_id':'another-id','verdict':'PASS','problems':[]},
    {'engagement_id':'eng-cf105-01','verdict':'PASS','problems':[{'type':'unsupported'}]},
    {'engagement_id':'eng-cf105-01','verdict':'BLOCK','problems':[{'type':'unsupported'}]},
])
def test_publisher_rejects_invalid_gate_without_artifacts(mesh, monkeypatch, bad_report):
    clients,source,_,root=mesh
    clients['vault'].post('/engagements',json=source,headers={'Authorization':'Bearer synthetic-test-token'})
    original=publisher.call_service
    def call(method,url,**kw):
        if url.endswith('/verify'):
            from tests.support import response
            return response(bad_report)
        return original(method,url,**kw)
    monkeypatch.setattr(publisher,'call_service',call)
    result=clients['publisher'].post('/publish',json={'record_id':source['id'],'draft':translated(source,'en')},
                                     headers={'Authorization':'Bearer synthetic-test-token'})
    assert result.status_code in {422,502}
    assert not (root/'artifacts').exists()


def test_verifier_outage_never_creates_an_artifact(mesh, monkeypatch):
    clients,source,_,root=mesh
    clients['vault'].post('/engagements',json=source,headers={'Authorization':'Bearer synthetic-test-token'})
    async def unavailable(*a,**k):raise HTTPException(503,'Model unavailable')
    verifier.app.dependency_overrides[get_semantic_checker]=lambda:unavailable
    result=clients['publisher'].post('/publish',json={'record_id':source['id'],'draft':translated(source,'en')},
                                     headers={'Authorization':'Bearer synthetic-test-token'})
    assert result.status_code==503
    assert not (root/'artifacts').exists()


def test_client_cannot_submit_a_different_language_or_source(mesh):
    clients,source,_,_=mesh
    draft=translated(source,'tr')
    result=clients['verifier'].post('/verify',json={'record_id':source['id'],'draft':draft,'language':'en'})
    assert result.status_code==422
    assert clients['publisher'].get('/artifacts/not-a-uuid/download',headers={'Authorization':'Bearer synthetic-test-token'}).status_code==404
