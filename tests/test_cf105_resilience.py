"""Retry and circuit-breaker behaviour of the shared HTTP layer."""
from unittest.mock import Mock
import pytest
import requests
from common import services
from common.services import ServiceError, call_service, reset_circuit_breakers

URL = "http://dependency.invalid/engagements"


class Reply:
    """The slice of requests.Response that call_service actually reads."""

    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture(autouse=True)
def isolated_breakers(monkeypatch):
    """Every test starts with a closed circuit and instant, recorded backoff."""
    reset_circuit_breakers()
    slept = []
    monkeypatch.setattr(services.time, "sleep", slept.append)
    yield slept
    reset_circuit_breakers()


def test_a_read_retries_a_transient_failure_and_returns_the_recovered_response(monkeypatch, isolated_breakers):
    transport = Mock(side_effect=[Reply(503), requests.ConnectionError(), Reply(200, {"items": []})])
    monkeypatch.setattr(requests, "request", transport)
    assert call_service("GET", URL).status_code == 200
    assert transport.call_count == 3
    assert len(isolated_breakers) == 2
    assert all(0 < delay <= services.RETRY_BACKOFF_MAX for delay in isolated_breakers)


def test_a_write_is_never_retried_even_when_the_dependency_reports_it_can_be(monkeypatch):
    transport = Mock(return_value=Reply(503, {"detail": "Model unavailable"}))
    monkeypatch.setattr(requests, "request", transport)
    with pytest.raises(ServiceError) as caught:
        call_service("POST", URL, json={})
    assert caught.value.status_code == 503
    assert transport.call_count == 1


def test_an_exhausted_read_surfaces_the_last_failure_kind(monkeypatch):
    monkeypatch.setattr(requests, "request", Mock(side_effect=requests.Timeout()))
    with pytest.raises(ServiceError) as caught:
        call_service("GET", URL)
    assert caught.value.status_code == 504


def test_a_read_can_opt_out_of_retries_the_way_health_probes_do(monkeypatch):
    transport = Mock(side_effect=requests.ConnectionError())
    monkeypatch.setattr(requests, "request", transport)
    with pytest.raises(ServiceError):
        call_service("GET", URL, retries=0)
    assert transport.call_count == 1


def test_a_client_error_is_an_answer_so_it_neither_retries_nor_opens_the_circuit(monkeypatch):
    transport = Mock(return_value=Reply(422, {"detail": "as_of must be ISO-8601"}))
    monkeypatch.setattr(requests, "request", transport)
    for _ in range(services.BREAKER_THRESHOLD + 2):
        with pytest.raises(ServiceError) as caught:
            call_service("GET", URL)
        assert caught.value.status_code == 422
        assert caught.value.detail == "as_of must be ISO-8601"
    assert transport.call_count == services.BREAKER_THRESHOLD + 2


def test_the_circuit_opens_on_sustained_failure_and_then_stops_calling_the_dependency(monkeypatch):
    transport = Mock(return_value=Reply(503))
    monkeypatch.setattr(requests, "request", transport)
    while transport.call_count < services.BREAKER_THRESHOLD:
        with pytest.raises(ServiceError):
            call_service("GET", URL, retries=0)
    calls_before = transport.call_count
    with pytest.raises(ServiceError) as caught:
        call_service("GET", URL)
    assert caught.value.status_code == 503
    assert transport.call_count == calls_before, "an open circuit must not reach the dependency"


def test_the_circuit_lets_one_probe_through_once_the_recovery_window_passes(monkeypatch):
    clock = iter([0.0] * 200)
    monkeypatch.setattr(services.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(requests, "request", Mock(return_value=Reply(503)))
    for _ in range(services.BREAKER_THRESHOLD):
        with pytest.raises(ServiceError):
            call_service("GET", URL, retries=0)
    recovered = Mock(return_value=Reply(200, {"items": []}))
    monkeypatch.setattr(requests, "request", recovered)
    monkeypatch.setattr(services.time, "monotonic", lambda: services.BREAKER_RECOVERY + 1)
    assert call_service("GET", URL, retries=0).status_code == 200
    assert recovered.call_count == 1


def test_a_numeric_retry_after_is_honoured_but_capped_by_our_own_ceiling(monkeypatch, isolated_breakers):
    monkeypatch.setattr(services.random, "random", lambda: 1.0)
    transport = Mock(side_effect=[Reply(429, headers={"Retry-After": "600"}), Reply(200, {})])
    monkeypatch.setattr(requests, "request", transport)
    assert call_service("GET", URL).status_code == 200
    assert isolated_breakers == [services.RETRY_BACKOFF_MAX]


def test_an_http_date_retry_after_falls_back_to_the_computed_backoff(monkeypatch, isolated_breakers):
    monkeypatch.setattr(services.random, "random", lambda: 1.0)
    transport = Mock(side_effect=[
        Reply(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), Reply(200, {}),
    ])
    monkeypatch.setattr(requests, "request", transport)
    call_service("GET", URL)
    assert isolated_breakers == [min(services.RETRY_BACKOFF, services.RETRY_BACKOFF_MAX)]


def test_breakers_are_scoped_to_one_origin_so_a_sick_service_cannot_block_another(monkeypatch):
    monkeypatch.setattr(requests, "request", Mock(return_value=Reply(503)))
    for _ in range(services.BREAKER_THRESHOLD):
        with pytest.raises(ServiceError):
            call_service("GET", URL, retries=0)
    healthy = Mock(return_value=Reply(200, {"status": "ok"}))
    monkeypatch.setattr(requests, "request", healthy)
    assert call_service("GET", "http://other.invalid/health", retries=0).status_code == 200
    assert healthy.call_count == 1
