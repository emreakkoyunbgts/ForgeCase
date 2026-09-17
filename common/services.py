"""HTTP service discovery, bounded calls and request tracing for the mesh."""
import logging
import os
import random
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from requests.structures import CaseInsensitiveDict

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

READER_URL = os.getenv("READER_URL", "http://127.0.0.1:8003").rstrip("/")
VAULT_URL = os.getenv("VAULT_URL", "http://127.0.0.1:8000").rstrip("/")
GENERATOR_URL = os.getenv("GENERATOR_URL", "http://127.0.0.1:8001").rstrip("/")
VERIFIER_URL = os.getenv("VERIFIER_URL", "http://127.0.0.1:8004").rstrip("/")
PUBLISHER_URL = os.getenv("PUBLISHER_URL", "http://127.0.0.1:8005").rstrip("/")
LIBRARIAN_URL = os.getenv("LIBRARIAN_URL", "http://127.0.0.1:8002").rstrip("/")
ANALYST_URL = os.getenv("ANALYST_URL", "http://127.0.0.1:8007").rstrip("/")
ALL_SERVICES = {
    "reader": READER_URL, "vault": VAULT_URL, "generator": GENERATOR_URL,
    "verifier": VERIFIER_URL, "publisher": PUBLISHER_URL,
    "librarian": LIBRARIAN_URL, "analyst": ANALYST_URL,
}
_request_headers = ContextVar("caseforge_request_headers", default=None)
logger = logging.getLogger(__name__)

# CF-105 keeps every outbound call bounded. Retries widen that bound on purpose,
# so they stay small, jittered, and reserved for requests that can be repeated
# without changing state. A breaker then stops us hammering a dependency that is
# already down; it counts transport failures and 5xx, never a 4xx answer.
RETRY_ATTEMPTS = int(os.getenv("CASEFORGE_HTTP_RETRIES", "2"))
RETRY_BACKOFF = float(os.getenv("CASEFORGE_HTTP_BACKOFF", "0.2"))
RETRY_BACKOFF_MAX = float(os.getenv("CASEFORGE_HTTP_BACKOFF_MAX", "2"))
BREAKER_THRESHOLD = int(os.getenv("CASEFORGE_BREAKER_THRESHOLD", "5"))
BREAKER_RECOVERY = float(os.getenv("CASEFORGE_BREAKER_RECOVERY", "30"))
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
REPEATABLE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ServiceError(Exception):
    """A public dependency error carrying its HTTP status and trace."""

    def __init__(self, detail, status_code=503, correlation_id=None):
        super().__init__(str(detail))
        self.detail = detail
        self.status_code = status_code
        self.correlation_id = correlation_id


class _CircuitBreaker:
    """Consecutive-failure breaker for one dependency origin.

    Handlers run in a thread pool, so every transition takes the lock. An open
    breaker rejects immediately; once the recovery window elapses it lets a
    single probe through and one more failure re-opens it.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = None

    def retry_after(self, now):
        """Seconds left before the next probe, or None while calls may pass."""
        with self._lock:
            if self._opened_at is None:
                return None
            remaining = BREAKER_RECOVERY - (now - self._opened_at)
            if remaining > 0:
                return remaining
            self._opened_at = None
            self._failures = max(BREAKER_THRESHOLD - 1, 0)
            return None

    def succeeded(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def failed(self, now):
        with self._lock:
            self._failures += 1
            if BREAKER_THRESHOLD > 0 and self._failures >= BREAKER_THRESHOLD:
                self._opened_at = now


_breakers = {}
_breakers_lock = threading.Lock()


def _breaker_for(url):
    """One breaker per scheme://host:port, shared by every route on it."""
    parts = urlsplit(url)
    origin = parts.scheme + "://" + parts.netloc
    with _breakers_lock:
        if origin not in _breakers:
            _breakers[origin] = _CircuitBreaker()
        return _breakers[origin]


def reset_circuit_breakers():
    """Drop all breaker state. For tests and long-lived interactive sessions."""
    with _breakers_lock:
        _breakers.clear()


def _backoff_delay(attempt, retry_after):
    """Exponential backoff with full jitter, capped so a call stays bounded."""
    delay = min(RETRY_BACKOFF * (2 ** attempt), RETRY_BACKOFF_MAX)
    if retry_after:
        try:
            # Honour a numeric Retry-After, but never past our own ceiling: the
            # caller is waiting on a bounded request, not on the dependency.
            delay = min(max(delay, float(retry_after)), RETRY_BACKOFF_MAX)
        except (TypeError, ValueError):
            pass  # HTTP-date form: keep the computed backoff.
    return delay * (0.5 + random.random() / 2)


def request_headers(headers=None, correlation_id=None, idempotency_key=None):
    """Copy headers and inherit tracing/auth without logging credentials."""
    inherited = CaseInsensitiveDict(_request_headers.get() or {})
    result = CaseInsensitiveDict(headers or {})
    for name in ("X-Correlation-ID", "Authorization", "Idempotency-Key"):
        if name not in result and inherited.get(name):
            result[name] = inherited[name]
    if correlation_id is not None:
        result["X-Correlation-ID"] = correlation_id
    if not result.get("X-Correlation-ID"):
        result["X-Correlation-ID"] = str(uuid.uuid4())
    if "Authorization" not in result and os.getenv("CASEFORGE_TOKEN"):
        result["Authorization"] = "Bearer " + os.environ["CASEFORGE_TOKEN"]
    if idempotency_key is not None:
        result["Idempotency-Key"] = idempotency_key
    for name in ("X-Correlation-ID", "Authorization", "Idempotency-Key"):
        if name in result and (
            not isinstance(result[name], str)
            or len(result[name]) > 4096
            or any(not 32 <= ord(char) < 127 for char in result[name])
        ):
            raise ServiceError("Invalid HTTP tracing or authorization header", 400)
    return dict(result)


def call_service(method, url, timeout=10, retries=None, **kwargs):
    """A bounded call, guarded by a per-origin breaker.

    Stateful requests are still never automatically retried: repeating a POST
    the dependency may already have applied is worse than surfacing the error.
    Pass retries=0 to opt a read out too, as health probes do.
    """
    headers = request_headers(kwargs.pop("headers", None))
    stateful = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    if stateful and "Idempotency-Key" not in CaseInsensitiveDict(headers):
        headers["Idempotency-Key"] = str(uuid.uuid4())
    trace = CaseInsensitiveDict(headers)["X-Correlation-ID"]
    kwargs.setdefault("allow_redirects", False)
    if retries is None:
        retries = RETRY_ATTEMPTS if method.upper() in REPEATABLE_METHODS else 0
    attempts = max(retries, 0) + 1
    breaker = _breaker_for(url)
    for attempt in range(attempts):
        remaining = breaker.retry_after(time.monotonic())
        if remaining is not None:
            logger.warning("circuit open for %s retry_after=%.1fs correlation_id=%s",
                           urlsplit(url).netloc, remaining, trace)
            raise ServiceError("Dependency is unavailable", 503, trace)
        last = attempt + 1 == attempts
        try:
            response = requests.request(method, url, timeout=timeout, headers=headers, **kwargs)
        except (requests.Timeout, requests.RequestException) as exc:
            breaker.failed(time.monotonic())
            timed_out = isinstance(exc, requests.Timeout)
            if last:
                if timed_out:
                    raise ServiceError("Dependency timed out", 504, trace) from None
                raise ServiceError("Dependency is unavailable", 503, trace) from None
            time.sleep(_backoff_delay(attempt, None))
            continue
        if 200 <= response.status_code < 300:
            breaker.succeeded()
            return response
        status = response.status_code
        if status >= 500 or status == 429:
            breaker.failed(time.monotonic())
            if status in RETRYABLE_STATUS and not last:
                logger.warning("retrying %s %s after status=%s correlation_id=%s",
                               method.upper(), urlsplit(url).path, status, trace)
                time.sleep(_backoff_delay(attempt, response.headers.get("Retry-After")))
                continue
        else:
            breaker.succeeded()  # A 4xx is an answer: the dependency is healthy.
        detail = "Dependency returned an invalid response"
        if 400 <= status < 500:
            try:
                detail = response.json().get("detail", "Request rejected by dependency")
            except (ValueError, AttributeError):
                detail = "Request rejected by dependency"
        elif status not in {502, 503, 504}:
            status = 502
        raise ServiceError(detail, status, trace)


def response_json(response):
    """Parse HTTP JSON without a local data fallback."""
    try:
        return response.json()
    except ValueError:
        raise ServiceError("Dependency returned invalid JSON", 502) from None


def install_http_middleware(app):
    """Trace outcomes and expose request context to synchronous handlers."""
    from fastapi.responses import JSONResponse

    if getattr(app.state, "caseforge_http_installed", False):
        return
    app.state.caseforge_http_installed = True

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.middleware("http")
    async def trace_request(request, call_next):
        try:
            selected = {
                name: request.headers[name]
                for name in ("X-Correlation-ID", "Authorization", "Idempotency-Key")
                if name in request.headers
            }
            headers = request_headers(selected)
        except ServiceError as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail},
                headers={"X-Correlation-ID": str(uuid.uuid4())},
            )
        trace = CaseInsensitiveDict(headers)["X-Correlation-ID"]
        request.state.correlation_id = trace
        token = _request_headers.set(headers)
        try:
            response = await call_next(request)
        finally:
            _request_headers.reset(token)
        response.headers["X-Correlation-ID"] = trace
        logger.info("%s %s status=%s correlation_id=%s", request.method,
                    request.url.path, response.status_code, trace)
        return response
