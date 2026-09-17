"""Offline checks for the real provider adapter and its failure boundary.

Only the SDK client is substituted: request_structured's timeout, schema
validation and HTTP error mapping execute unchanged. No model calls occur.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import openai
import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from common import structured_llm


class ProviderAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: str


MODEL_ENV = 'CF105_TEST_PROVIDER_MODEL'


@pytest.fixture
def sdk(monkeypatch):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.responses.parse = AsyncMock(return_value=SimpleNamespace(
        status='completed', output_parsed={'summary': 'Supported by the source.'}))
    constructor = Mock(return_value=client)
    monkeypatch.setattr(openai, 'AsyncOpenAI', constructor)
    monkeypatch.setenv('OPENAI_API_KEY', 'cf105-synthetic-provider-key')
    monkeypatch.delenv(MODEL_ENV, raising=False)
    return SimpleNamespace(client=client, constructor=constructor)


def request(payload=None, correlation_id='cf105-provider-trace'):
    return asyncio.run(structured_llm.request_structured(
        'Verify the supplied data.', {'text': 'Synthetic source.'} if payload is None else payload,
        ProviderAnswer, model_env=MODEL_ENV, correlation_id=correlation_id,
    ))


def test_provider_uses_bounded_no_retry_structured_request(sdk, monkeypatch):
    deadlines = []
    real_timeout = asyncio.timeout

    def observed_timeout(seconds):
        deadlines.append(seconds)
        return real_timeout(seconds)

    monkeypatch.setattr(structured_llm.asyncio, 'timeout', observed_timeout)
    result = request()
    assert result == ProviderAnswer(summary='Supported by the source.')
    sdk.constructor.assert_called_once_with(
        api_key='cf105-synthetic-provider-key', timeout=60.0, max_retries=0)
    assert deadlines == [60.0]
    sdk.client.responses.parse.assert_awaited_once()
    parameters = sdk.client.responses.parse.call_args.kwargs
    assert parameters['model'] == 'gpt-5.5'
    assert parameters['text_format'] is ProviderAnswer
    assert parameters['max_output_tokens'] == 16000
    assert parameters['store'] is False
    assert parameters['extra_headers'] == {'X-Correlation-ID': 'cf105-provider-trace'}
    assert parameters['input'] == [
        {'role': 'system', 'content': 'Verify the supplied data.'},
        {'role': 'user', 'content': '{"text": "Synthetic source."}'},
    ]
    sdk.client.__aenter__.assert_awaited_once()
    sdk.client.__aexit__.assert_awaited_once()


def test_model_is_configurable_and_missing_trace_is_omitted(sdk, monkeypatch):
    monkeypatch.setenv(MODEL_ENV, 'configured-test-model')
    request(correlation_id=None)
    parameters = sdk.client.responses.parse.call_args.kwargs
    assert parameters['model'] == 'configured-test-model'
    assert parameters['extra_headers'] == {}


def sdk_error(kind):
    outgoing = httpx.Request('POST', 'https://provider.test.invalid/v1/responses')
    if kind == 'sdk_timeout':
        return openai.APITimeoutError(request=outgoing)
    if kind == 'connection':
        return openai.APIConnectionError(message='private-provider-detail', request=outgoing)
    if kind == 'deadline':
        return TimeoutError('private-provider-detail')
    if kind == 'sdk_invalid':
        return openai.OpenAIError('private-provider-detail')
    if kind == 'json':
        return ValueError('private-provider-detail')
    status, error_type = {
        'authentication': (401, openai.AuthenticationError),
        'rate_limit': (429, openai.RateLimitError),
        'upstream_status': (500, openai.APIStatusError),
    }[kind]
    return error_type('private-provider-detail',
                      response=httpx.Response(status, request=outgoing), body={'private': True})


@pytest.mark.parametrize('kind,status', [
    ('sdk_timeout', 504), ('deadline', 504), ('authentication', 503),
    ('connection', 503), ('rate_limit', 503), ('upstream_status', 502),
    ('sdk_invalid', 502), ('json', 502),
])
def test_provider_errors_preserve_status_without_retry_or_detail_leaks(sdk, kind, status):
    sdk.client.responses.parse.side_effect = sdk_error(kind)
    with pytest.raises(HTTPException) as exc:
        request()
    assert exc.value.status_code == status
    assert 'private-provider-detail' not in str(exc.value.detail)
    assert 'cf105-synthetic-provider-key' not in str(exc.value.detail)
    sdk.constructor.assert_called_once()
    sdk.client.responses.parse.assert_awaited_once()
    sdk.client.__aexit__.assert_awaited_once()


@pytest.mark.parametrize('response', [
    SimpleNamespace(status='incomplete', output_parsed={'summary': 'Partial output.'}),
    SimpleNamespace(status='failed', output_parsed=None),
    SimpleNamespace(status='completed', output_parsed=None,
                    output=[{'type': 'refusal', 'refusal': 'Unable to comply.'}]),
    SimpleNamespace(status='completed', output_parsed={}),
    SimpleNamespace(status='completed', output_parsed={'summary': 123}),
    SimpleNamespace(status='completed', output_parsed={'summary': 'Valid text.', 'invented': True}),
    SimpleNamespace(status='completed', output_parsed='not a schema object'),
])
def test_incomplete_refused_and_schema_invalid_output_never_returns_success(sdk, response):
    sdk.client.responses.parse.return_value = response
    with pytest.raises(HTTPException) as exc:
        request()
    assert exc.value.status_code == 502
    sdk.client.responses.parse.assert_awaited_once()
    sdk.client.__aexit__.assert_awaited_once()


def test_sdk_schema_validation_failure_is_mapped_to_502(sdk):
    with pytest.raises(ValueError) as invalid:
        ProviderAnswer.model_validate({'summary': ['not', 'text']})
    sdk.client.responses.parse.side_effect = invalid.value
    with pytest.raises(HTTPException) as exc:
        request()
    assert exc.value.status_code == 502


def test_outer_deadline_cancels_a_stalled_sdk_call(sdk, monkeypatch):
    cancelled = []

    async def stalled(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    sdk.client.responses.parse.side_effect = stalled
    # Exercise cancellation without making the test wait the production 60 s.
    monkeypatch.setattr(structured_llm, 'PROVIDER_TIMEOUT_SECONDS', 0.01)
    with pytest.raises(HTTPException) as exc:
        request()
    assert exc.value.status_code == 504
    assert cancelled == [True]
    sdk.client.responses.parse.assert_awaited_once()
    sdk.client.__aexit__.assert_awaited_once()


def test_missing_configuration_fails_before_constructing_sdk(sdk, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(HTTPException) as exc:
        request()
    assert exc.value.status_code == 503
    sdk.constructor.assert_not_called()


def test_oversized_input_fails_before_constructing_sdk(sdk):
    with pytest.raises(HTTPException) as exc:
        request({'text': 'x' * structured_llm.MAX_PROVIDER_INPUT_CHARACTERS})
    assert exc.value.status_code == 422
    sdk.constructor.assert_not_called()
