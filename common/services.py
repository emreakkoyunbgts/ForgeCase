"""HTTP service discovery, bounded calls and request tracing for the mesh."""
import logging
import os
import uuid
from contextvars import ContextVar
from pathlib import Path

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


class ServiceError(Exception):
    """A public dependency error carrying its HTTP status and trace."""

    def __init__(self, detail, status_code=503, correlation_id=None):
        super().__init__(str(detail))
        self.detail = detail
        self.status_code = status_code
        self.correlation_id = correlation_id


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


def call_service(method, url, timeout=10, **kwargs):
    """One bounded attempt. Stateful requests are never automatically retried."""
    headers = request_headers(kwargs.pop("headers", None))
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        if "Idempotency-Key" not in CaseInsensitiveDict(headers):
            headers["Idempotency-Key"] = str(uuid.uuid4())
    trace = CaseInsensitiveDict(headers)["X-Correlation-ID"]
    kwargs.setdefault("allow_redirects", False)
    try:
        response = requests.request(method, url, timeout=timeout, headers=headers, **kwargs)
    except requests.Timeout:
        raise ServiceError("Dependency timed out", 504, trace) from None
    except requests.RequestException:
        raise ServiceError("Dependency is unavailable", 503, trace) from None
    if 200 <= response.status_code < 300:
        return response
    status = response.status_code
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


def install_request_validation_handler(app):
    """Keep FastAPI's validation envelope without reflecting submitted content."""
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        errors = [{key: error[key] for key in ("loc", "msg", "type")}
                  for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})


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
