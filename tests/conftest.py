# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from minimonitor import usage


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """No test may read the real credentials nor call the real usage endpoint."""
    monkeypatch.setattr(usage, "CREDENTIALS", tmp_path / "credentials.json")
    monkeypatch.setattr(usage, "USAGE_URL", "http://127.0.0.1:9/blocked")
    return tmp_path
