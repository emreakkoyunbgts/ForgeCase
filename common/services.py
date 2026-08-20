"""
SERVICES — shared config for calling other prototypes over HTTP.
Base URLs are read from environment variables so each teammate can
run their service on their own port without editing code.
"""

import os
import uuid
import requests

READER_URL = os.environ.get("READER_URL", "http://localhost:8001")
VAULT_URL = os.environ.get("VAULT_URL", "http://localhost:8000")
GENERATOR_URL = os.environ.get("GENERATOR_URL", "http://localhost:8003")
VERIFIER_URL = os.environ.get("VERIFIER_URL", "http://localhost:8004")
PUBLISHER_URL = os.environ.get("PUBLISHER_URL", "http://localhost:8005")
LIBRARIAN_URL = os.environ.get("LIBRARIAN_URL", "http://localhost:8006")
ANALYST_URL = os.environ.get("ANALYST_URL", "http://localhost:8007")

ALL_SERVICES = {
    "reader": READER_URL,
    "vault": VAULT_URL,
    "generator": GENERATOR_URL,
    "verifier": VERIFIER_URL,
    "publisher": PUBLISHER_URL,
    "librarian": LIBRARIAN_URL,
    "analyst": ANALYST_URL,
}


class ServiceError(Exception):
    pass


def call_service(method, url, timeout=10, **kwargs):
    correlation_id = str(uuid.uuid4())
    headers = kwargs.pop("headers", {})
    headers["X-Correlation-ID"] = correlation_id

    try:
        response = requests.request(
            method, url, timeout=timeout, headers=headers, **kwargs
        )
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        raise ServiceError(f"{url} timed out after {timeout}s (correlation_id={correlation_id})")
    except requests.exceptions.ConnectionError:
        raise ServiceError(f"{url} is unreachable (correlation_id={correlation_id})")
    except requests.exceptions.HTTPError as e:
        raise ServiceError(f"{url} returned {response.status_code}: {e} (correlation_id={correlation_id})")