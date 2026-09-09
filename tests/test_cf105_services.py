from unittest.mock import Mock
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from common.services import ServiceError, call_service, install_http_middleware, request_headers


def test_headers_are_copied_and_caller_auth_and_trace_survive(monkeypatch):
    monkeypatch.setenv('CASEFORGE_TOKEN', 'test-service-token')
    original = {'x-correlation-id': 'trace-105', 'authorization': 'Bearer caller'}
    assert request_headers(original) == original
    assert request_headers(original) is not original
    assert request_headers()['Authorization'] == 'Bearer test-service-token'


@pytest.mark.parametrize('error,status', [(requests.Timeout(), 504), (requests.ConnectionError(), 503)])
def test_requests_never_retry_silently(monkeypatch, error, status):
    transport = Mock(side_effect=error)
    monkeypatch.setattr(requests, 'request', transport)
    with pytest.raises(ServiceError) as caught:
        call_service('POST', 'http://test.invalid/engagements', json={})
    assert caught.value.status_code == status
    assert transport.call_count == 1
    assert transport.call_args.kwargs['headers']['Idempotency-Key']
    assert transport.call_args.kwargs['allow_redirects'] is False


def test_context_and_failures_keep_trace_without_leaking_between_requests(monkeypatch):
    monkeypatch.delenv('CASEFORGE_TOKEN', raising=False)
    app = FastAPI()
    install_http_middleware(app)
    @app.get('/headers')
    def headers():
        return request_headers()
    @app.get('/error')
    def error():
        raise ServiceError('Unavailable', 503)
    client = TestClient(app)
    provided = {'X-Correlation-ID': 'trace', 'Authorization': 'Bearer caller'}
    assert client.get('/headers', headers=provided).json() == provided
    result = client.get('/error', headers=provided)
    assert result.status_code == 503
    assert result.headers['X-Correlation-ID'] == 'trace'
    assert client.get('/headers').json().get('Authorization') is None
