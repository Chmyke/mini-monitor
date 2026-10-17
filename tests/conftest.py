# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from minimonitor import __main__ as entry
from minimonitor import auth, usage


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """No test may touch the real credentials, log or lock, nor call a real endpoint."""
    monkeypatch.setattr(auth, "CREDENTIALS", tmp_path / "credentials.json")
    monkeypatch.setattr(auth, "TOKEN_URL", "http://127.0.0.1:9/blocked")
    monkeypatch.setattr(usage, "USAGE_URL", "http://127.0.0.1:9/blocked")
    monkeypatch.setattr(entry, "DATA_DIR", tmp_path)
    return tmp_path
