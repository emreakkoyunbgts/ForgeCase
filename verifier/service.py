"""Compatibility exports for the shared authoritative Vault client."""
from common.source import (
    VAULT_TIMEOUT_SECONDS, get_record_from_vault, get_vault_client,
    validate_source as _validate_source,
)
