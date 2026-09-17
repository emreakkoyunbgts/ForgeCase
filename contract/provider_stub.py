"""Deterministic synthetic provider for the CF-120 live mesh.

Only the external LLM boundary is synthetic. Generator and Verifier run their
real production code and reach this app because the contract runner sets
OPENAI_BASE_URL for those two subprocesses only; the OpenAI SDK resolves an
unset base_url from that variable.

Two rules keep this honest:

* Nothing here imports generator, verifier or common. If the double computed
  its answer with the code under test, a grounding assertion built on it would
  prove nothing.
* Unknown content raises instead of guessing, and armed-but-unused faults are
  reported, so a silently skipped stage cannot look like a pass.

This is NOT model acceptance evidence. See scripts/live_acceptance.py.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from contract.fixtures.cases import (
    LANGUAGES, SOURCES, SPANS, UnknownFixture, evidence_for, expected_span_text,
    record_id_for_english_spans,
)

TRANSLATION_SCHEMA = 'Translation'
ASSESSMENT_SCHEMA = 'Assessment'
MARKER = re.compile(r'\[MISSING[^\]]*\]', re.I)
DELAY_SECONDS = 65
CALL_LIMIT = 10000

FAULTS = (
    'incomplete_spans', 'fabricated_evidence', 'empty_translation',
    'changed_quantity', 'changed_marker', 'unsupported_verdict',
    'incomplete_status', 'server_error', 'unparsable',
    'unauthorized', 'rate_limited', 'timeout', 'invalid_schema', 'empty_output',
    'language_mismatch', 'duplicate_spans', 'omitted_evidence',
)


def same_json(left, right):
    """JSON equality that does not confuse false/0 or true/1."""
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False)


def source_matches_fixture(source, record_id):
    expected = SOURCES[record_id]
    # Reader supplies this derived flag; it is not an extra factual assertion.
    actual = dict(source)
    if 'outcome_missing' in actual:
        missing = actual.pop('outcome_missing')
        if type(missing) is not bool or missing != (not expected['outcomes']):
            return False
    return same_json(actual, expected)


def envelope(model, payload, status='completed'):
    """The minimal Response shape the installed SDK parser accepts."""
    return {
        'id': 'resp_cf120_' + uuid4().hex,
        'object': 'response',
        'created_at': 0,
        'model': model,
        'status': status,
        'output': [{
            'type': 'message',
            'id': 'msg_' + uuid4().hex,
            'role': 'assistant',
            'status': 'completed',
            'content': [{
                'type': 'output_text',
                'text': json.dumps(payload, ensure_ascii=False),
                'annotations': [],
            }],
        }],
        'parallel_tool_calls': False,
        'tool_choice': 'auto',
        'tools': [],
        'error': None,
        'incomplete_details': None,
        'instructions': None,
        'metadata': {},
    }


def translation_response(payload, fault=None):
    """Answer generator/translation.py from fixture text only."""
    language = payload['language']
    spans = payload['spans']
    if language not in LANGUAGES:
        raise UnknownFixture('unsupported language %r' % (language,))
    record_id = record_id_for_english_spans(spans)
    original = {span['id']: span['text'] for span in spans}
    if len(original) != len(spans) or original != SPANS[record_id]['en']:
        raise UnknownFixture('translation input differs from the approved English fixture')
    source = SOURCES[record_id]
    if (not same_json(payload.get('may_be_named'), source['may_be_named'])
            or not same_json(payload.get('technologies'), source['technologies'])):
        raise UnknownFixture('translation source metadata differs from the approved fixture')
    out = []
    for span in spans:
        out.append({'id': span['id'],
                    'text': expected_span_text(record_id, span['id'], language)})
    if fault == 'incomplete_spans' and out:
        out.pop()
    elif fault == 'duplicate_spans' and out:
        out.append(dict(out[0]))
    elif fault == 'empty_translation' and out:
        out[0] = {**out[0], 'text': ''}
    elif fault == 'changed_quantity':
        for i, item in enumerate(out):
            if re.search(r'\d+', item['text']):
                changed = re.sub(r'\d+', lambda match: str(int(match.group()) + 1), item['text'], count=1)
                out[i] = {**item, 'text': changed}
                break
    elif fault == 'changed_marker' and out:
        marker_index = next((i for i, item in enumerate(out) if MARKER.search(item['text'])), None)
        if marker_index is None:
            out[0] = {**out[0], 'text': out[0]['text'] + ' [MISSING: injected]'}
        else:
            out[marker_index] = {**out[marker_index], 'text': 'No measured outcome.'}
    return {'spans': out}, record_id


def assessment_response(payload, fault=None):
    """Answer verifier/semantic.py from fixture evidence only.

    A span whose prose differs from the fixture is reported as unsupported.
    That is what turns an edited or poisoned draft into a real BLOCK through
    the production Verifier, instead of the stub deciding the verdict itself.
    """
    language = payload['language']
    spans = payload['spans']
    source = payload['source']
    record_id = source.get('id')
    if record_id not in SOURCES:
        raise UnknownFixture('no fixture source for record %r' % (record_id,))
    if language not in LANGUAGES:
        raise UnknownFixture('unsupported language %r' % (language,))
    source_valid = source_matches_fixture(source, record_id)
    out = []
    for span in spans:
        grounded = source_valid and span['text'] == SPANS[record_id][language].get(span['id'])
        if fault == 'unsupported_verdict':
            grounded = False
        if not grounded:
            out.append({'id': span['id'], 'verdict': 'unsupported', 'evidence': [],
                        'reason': ('fixture: source differs from the approved source'
                                   if not source_valid else 'fixture: span prose is not the grounded fixture text')})
            continue
        pairs = evidence_for(record_id, span['id'])
        if fault == 'fabricated_evidence':
            pairs = [('/not/a/real/pointer', 'fabricated')]
        evidence = [{'pointer': pointer, 'quote': quote} for pointer, quote in pairs]
        if MARKER.sub('', span['text']).strip(' .;\n') == '':
            evidence = []
        if fault == 'omitted_evidence':
            evidence = []
        out.append({'id': span['id'], 'verdict': 'entailed', 'evidence': evidence,
                    'reason': 'fixture: grounded in the cited source scalars'})
    if fault == 'incomplete_spans' and out:
        out.pop()
    elif fault == 'duplicate_spans' and out:
        out.append(deepcopy(out[0]))
    return {'language_matches': fault != 'language_mismatch', 'spans': out}, record_id


def create_app():
    app = FastAPI(title='CF-120 synthetic provider (NOT a model)', version='0.1.0')
    app.state.calls = []
    app.state.armed = []
    app.state.dropped_calls = 0

    def take_fault(stage, correlation_id):
        for entry in app.state.armed:
            if entry['used'] or entry['stage'] not in (stage, 'any'):
                continue
            if entry['correlation_id'] is not None and entry['correlation_id'] != correlation_id:
                continue
            entry['used'] = True
            return entry['fault']
        return None

    @app.middleware('http')
    async def synthetic_header(request, call_next):
        response = await call_next(request)
        response.headers['X-CaseForge-Provider'] = 'synthetic-stub'
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'cf120-provider-stub', 'real_model': False}

    @app.get('/__calls')
    def calls():
        unused = [item['fault'] for item in app.state.armed if not item['used']]
        return {'calls': app.state.calls, 'armed_unused': unused,
                'armed': app.state.armed, 'dropped_calls': app.state.dropped_calls}

    @app.post('/__control')
    async def control(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({'detail': 'control requires JSON'}, status_code=422)
        if not isinstance(body, dict):
            return JSONResponse({'detail': 'control requires an object'}, status_code=422)
        fault = body.get('fault')
        if fault not in FAULTS:
            return JSONResponse({'detail': 'unknown fault %r' % (fault,)}, status_code=422)
        stage = body.get('stage', 'any')
        trace = body.get('correlation_id')
        if stage not in ('translation', 'assessment', 'any') or (trace is not None and (
                not isinstance(trace, str) or not trace or len(trace) > 4096)):
            return JSONResponse({'detail': 'invalid fault stage or correlation id'}, status_code=422)
        entry = {'fault': fault, 'stage': stage, 'correlation_id': trace,
                 'fault_id': uuid4().hex, 'used': False}
        app.state.armed.append(entry)
        return {'armed': fault, 'stage': stage, 'correlation_id': trace, 'fault_id': entry['fault_id']}

    @app.post('/__reset')
    def reset():
        app.state.calls.clear()
        app.state.armed.clear()
        app.state.dropped_calls = 0
        return {'reset': True}

    @app.post('/v1/responses')
    @app.post('/responses')
    async def responses(request: Request):
        try:
            body = await request.json()
            schema = (body.get('text') or {}).get('format', {}).get('name')
        except (ValueError, AttributeError):
            return JSONResponse({'detail': 'stub requires a JSON request object'}, status_code=400)
        model = body.get('model', 'cf120-stub')
        correlation_id = request.headers.get('X-Correlation-ID')
        try:
            content = body['input'][1]['content']
            payload = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError):
            return JSONResponse({'detail': 'stub could not read the request payload'},
                                status_code=400)
        if schema == TRANSLATION_SCHEMA:
            stage = 'translation'
        elif schema == ASSESSMENT_SCHEMA:
            stage = 'assessment'
        else:
            return JSONResponse({'detail': 'unsupported schema %r' % (schema,)},
                                status_code=422)
        if not isinstance(payload, dict) or not isinstance(payload.get('spans'), list):
            return JSONResponse({'detail': 'stub requires a spans array'}, status_code=400)
        fault = take_fault(stage, correlation_id)
        source = payload.get('source')
        record_id = source.get('id') if isinstance(source, dict) else None
        if stage == 'translation':
            try:
                record_id = record_id_for_english_spans(payload['spans'])
            except (UnknownFixture, AttributeError):
                pass
        call = {
            'stage': stage, 'model': model, 'record_id': record_id,
            'language': payload.get('language'), 'correlation_id': correlation_id,
            'span_ids': [span.get('id') for span in payload['spans'] if isinstance(span, dict)],
            'spans': deepcopy(payload['spans']), 'source': deepcopy(source),
            'payload_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
            'fault': fault, 'status': 200,
        }
        if len(app.state.calls) >= CALL_LIMIT:
            app.state.calls.pop(0)
            app.state.dropped_calls += 1
        app.state.calls.append(call)
        if fault in ('server_error', 'unauthorized', 'rate_limited'):
            call['status'] = {'server_error': 500, 'unauthorized': 401, 'rate_limited': 429}[fault]
            return JSONResponse({'error': {'message': 'synthetic provider failure',
                                         'type': 'synthetic_fault'}}, status_code=call['status'])
        if fault == 'unparsable':
            return PlainTextResponse('not a response object', status_code=200)
        if fault == 'timeout':
            await asyncio.sleep(DELAY_SECONDS)
        try:
            if stage == 'translation':
                result, record_id = translation_response(payload, fault)
            else:
                result, record_id = assessment_response(payload, fault)
        except (UnknownFixture, KeyError, TypeError, AttributeError) as exc:
            call['status'] = 422
            return JSONResponse({'detail': str(exc)}, status_code=422)
        if fault == 'invalid_schema':
            result = {'unexpected_field': 'not the requested schema'}
        status = 'incomplete' if fault == 'incomplete_status' else 'completed'
        response = envelope(model, result, status)
        if fault == 'empty_output':
            response['output'] = []
        return response

    return app


app = create_app()
