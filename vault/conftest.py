"""All Vault tests use a private database, never a developer's records."""
import pytest
from vault import vault


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, 'DB_PATH', str(tmp_path / 'engagements.db'))
