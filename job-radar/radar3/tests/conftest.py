import pytest

from radar3 import config


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """No waiting between a source's retries in tests."""
    monkeypatch.setattr(config, "RETRY_WAIT_SEC", 0)
