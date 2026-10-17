# SPDX-License-Identifier: GPL-3.0-or-later
import json
import stat
import sys

import pytest

from minimonitor import auth

NOW = 1_800_000_000_000
HOUR = 3_600_000


def write(path, **oauth):
    base = {"accessToken": "old-access", "refreshToken": "old-refresh", "expiresAt": NOW + 8 * HOUR,
            "refreshTokenExpiresAt": NOW + 700 * HOUR, "scopes": ["user:profile", "user:inference"],
            "subscriptionType": "max"}
    base.update(oauth)
    data = {"mcpOAuth": {"other": {"accessToken": "keep-me"}}, "claudeAiOauth": base}
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data


class FakeServer:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response or {"access_token": "new-access", "refresh_token": "new-refresh",
                                     "expires_in": 28800, "scope": "user:profile user:inference"}
        self.error = error

    def __call__(self, url, body, timeout):
        self.calls.append(body)
        if self.error:
            raise self.error
        return self.response


def source(server, path):
    return auth.TokenSource(path=path, post=server, clock=lambda: NOW)


def test_valid_token_is_used_without_renewal(tmp_path):
    path = tmp_path / "c.json"
    write(path)
    server = FakeServer()
    assert source(server, path).access_token() == "old-access"
    assert server.calls == []


def test_renewal_before_expiry_rewrites_file_and_keeps_other_keys(tmp_path):
    path = tmp_path / "c.json"
    before = write(path, expiresAt=NOW + 5 * 60_000)
    server = FakeServer()
    assert source(server, path).access_token() == "new-access"
    assert server.calls == [{"grant_type": "refresh_token", "refresh_token": "old-refresh",
                             "client_id": auth.CLIENT_ID, "scope": "user:profile user:inference"}]
    raw = path.read_text(encoding="utf-8")
    after = json.loads(raw)
    oauth = after["claudeAiOauth"]
    assert (oauth["accessToken"], oauth["refreshToken"]) == ("new-access", "new-refresh")
    assert oauth["expiresAt"] == NOW + 28800 * 1000
    assert oauth["subscriptionType"] == "max"
    assert oauth["refreshTokenExpiresAt"] == before["claudeAiOauth"]["refreshTokenExpiresAt"]
    assert after["mcpOAuth"] == before["mcpOAuth"]
    assert not raw.endswith("\n") and ": " not in raw  # same compact format as Claude Code
    assert list(tmp_path.iterdir()) == [path]  # no temporary file left behind


def test_rejected_token_is_renewed_even_if_not_expired(tmp_path):
    path = tmp_path / "c.json"
    write(path)
    server = FakeServer()
    assert source(server, path).access_token(rejected="old-access") == "new-access"
    assert len(server.calls) == 1


def test_already_renewed_elsewhere_is_not_renewed_again(tmp_path):
    path = tmp_path / "c.json"
    write(path, accessToken="fresh-from-elsewhere")
    server = FakeServer()
    assert source(server, path).access_token(rejected="old-access") == "fresh-from-elsewhere"
    assert server.calls == []


def test_failed_renewal_keeps_file_and_uses_token_while_valid(tmp_path):
    path = tmp_path / "c.json"
    write(path, expiresAt=NOW + 5 * 60_000)
    before = path.read_bytes()
    src = source(FakeServer(error=auth.RefreshError("HTTP 400 invalid_grant")), path)
    assert src.access_token() == "old-access"  # 5 minutes left: still usable
    assert path.read_bytes() == before
    assert src.last_error == "refresh failed: HTTP 400 invalid_grant"


def test_failed_renewal_of_expired_token_gives_nothing(tmp_path):
    path = tmp_path / "c.json"
    write(path, expiresAt=NOW - 1)
    src = source(FakeServer(error=auth.RefreshError("timeout")), path)
    assert src.access_token() is None


def test_response_without_access_token_changes_nothing(tmp_path):
    path = tmp_path / "c.json"
    write(path, expiresAt=NOW - 1)
    before = path.read_bytes()
    assert source(FakeServer(response={"error": "x"}), path).access_token() is None
    assert path.read_bytes() == before


def test_missing_expires_in_renews_again_within_the_hour():
    data = {"claudeAiOauth": {"accessToken": "a", "refreshToken": "r"}}
    new = auth.apply_response(data, {"access_token": "b"}, NOW)
    assert new["claudeAiOauth"]["expiresAt"] == NOW + auth.UNKNOWN_LIFETIME_MS
    assert new["claudeAiOauth"]["refreshToken"] == "r"  # kept when the server does not rotate it
    assert data["claudeAiOauth"]["accessToken"] == "a"  # input untouched


def test_no_credentials(tmp_path):
    src = source(FakeServer(), tmp_path / "missing.json")
    assert src.access_token() is None and src.last_error == "no credentials"


def test_errors_never_contain_tokens(tmp_path):
    path = tmp_path / "c.json"
    write(path, expiresAt=NOW - 1)
    src = auth.TokenSource(path=path, clock=lambda: NOW, timeout=1)  # real POST to a closed port
    assert src.access_token() is None
    assert "old-" not in src.last_error and src.last_error.startswith("refresh failed")


@pytest.mark.parametrize("bad", ["", "{", "[]", '{"claudeAiOauth": {"accessToken": 5}}'])
def test_unreadable_file_is_no_credentials(tmp_path, bad):
    path = tmp_path / "c.json"
    path.write_text(bad, encoding="utf-8")
    assert auth.load(path) is None


def test_claude_config_dir_is_honoured(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert auth.credentials_path() == tmp_path / "elsewhere" / ".credentials.json"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert auth.credentials_path().parent.name == ".claude"


def test_rewritten_credentials_survive_a_leftover_temp_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.with_name(path.name + ".minimonitor.tmp").write_text("stale")
    auth.write_atomic(path, {"a": 1})
    assert json.loads(path.read_text()) == {"a": 1}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_rewritten_credentials_are_private(tmp_path):
    path = tmp_path / "credentials.json"
    auth.write_atomic(path, {"a": 1})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
