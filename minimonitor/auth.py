# SPDX-License-Identifier: GPL-3.0-or-later
"""Claude OAuth token, read from Claude Code's credentials file and renewed when needed.

The refresh token changes at every renewal, so the file is re-read just before
renewing and rewritten atomically right after; every other key in it is kept as is.
No token ever appears in a message, an exception or a log.
"""

from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


def credentials_path() -> Path:
    """Where Claude Code keeps its sign-in: ~/.claude, or $CLAUDE_CONFIG_DIR when set."""
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / ".credentials.json"


CREDENTIALS = credentials_path()
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's public OAuth client
REFRESH_MARGIN_MS = 10 * 60 * 1000  # renew 10 minutes before expiry
UNKNOWN_LIFETIME_MS = 60 * 60 * 1000  # if the server omits expires_in, renew again within the hour

Post = Callable[[str, dict, float], dict]


class RefreshError(Exception):
    """Renewal failed. The message never contains a token."""


def now_ms() -> int:
    return int(time.time() * 1000)


def load(path: Path | None = None) -> dict | None:
    try:
        data = json.loads((path or CREDENTIALS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    if not isinstance(oauth, dict) or not isinstance(oauth.get("accessToken"), str):
        return None
    return data


def needs_refresh(oauth: dict, now: int, margin: int = REFRESH_MARGIN_MS) -> bool:
    expires = oauth.get("expiresAt")
    return not isinstance(expires, (int, float)) or expires - now < margin


def refresh_body(oauth: dict) -> dict:
    return {
        "grant_type": "refresh_token",
        "refresh_token": oauth["refreshToken"],
        "client_id": CLIENT_ID,
        "scope": " ".join(oauth.get("scopes") or []),
    }


def apply_response(data: dict, response: dict, now: int) -> dict:
    """New credentials file content after a successful renewal (input left untouched)."""
    access = response.get("access_token")
    if not isinstance(access, str) or not access:
        raise RefreshError("response without access_token")
    new = copy.deepcopy(data)
    oauth = new["claudeAiOauth"]
    oauth["accessToken"] = access
    refresh = response.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        oauth["refreshToken"] = refresh
    expires_in = response.get("expires_in")
    if isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool):
        oauth["expiresAt"] = now + int(expires_in * 1000)
    else:
        oauth["expiresAt"] = now + UNKNOWN_LIFETIME_MS
    refresh_expires_in = response.get("refresh_token_expires_in")
    if isinstance(refresh_expires_in, (int, float)) and not isinstance(refresh_expires_in, bool):
        oauth["refreshTokenExpiresAt"] = now + int(refresh_expires_in * 1000)
    scope = response.get("scope")
    if isinstance(scope, str) and scope.strip():
        oauth["scopes"] = scope.split()
    return new


def write_atomic(path: Path, data: dict) -> None:
    """Same compact format as Claude Code; a crash mid-write never leaves a broken file.

    The file holds secrets: on Linux and macOS it is readable by its owner only (0600).
    """
    tmp = path.with_name(path.name + ".minimonitor.tmp")
    tmp.unlink(missing_ok=True)  # a leftover would keep its old permissions
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def post_json(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": "mini-monitor",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        raise RefreshError(f"HTTP {e.code} {_oauth_error(e)}".strip()) from None
    except (OSError, ValueError) as e:
        raise RefreshError(type(e).__name__) from None
    if not isinstance(result, dict):
        raise RefreshError("unexpected response")
    return result


def _oauth_error(error: urllib.error.HTTPError) -> str:
    """The standard OAuth 'error' code (e.g. invalid_grant): safe to show, carries no token."""
    try:
        code = json.load(error).get("error")
    except Exception:
        return ""
    return code if isinstance(code, str) and code.isascii() and len(code) < 64 else ""


class TokenSource:
    def __init__(self, path: Path | None = None, post: Post = post_json,
                 clock: Callable[[], int] = now_ms, timeout: float = 15):
        self._path = path
        self._post = post
        self._clock = clock
        self._timeout = timeout
        self.last_error: str | None = None

    @property
    def path(self) -> Path:
        return self._path or CREDENTIALS

    def access_token(self, rejected: str | None = None) -> str | None:
        """A usable access token, renewed first if it is about to expire or was just rejected."""
        data = load(self.path)  # re-read every time: another program may have renewed it
        if data is None:
            self.last_error = "no credentials"
            return None
        oauth = data["claudeAiOauth"]
        now = self._clock()
        if oauth["accessToken"] != rejected and not needs_refresh(oauth, now):
            return oauth["accessToken"]
        if not isinstance(oauth.get("refreshToken"), str):
            self.last_error = "no refresh token"
            return None
        try:
            response = self._post(TOKEN_URL, refresh_body(oauth), self._timeout)
            new = apply_response(data, response, self._clock())
            write_atomic(self.path, new)
        except (RefreshError, OSError) as e:
            self.last_error = f"refresh failed: {e if isinstance(e, RefreshError) else type(e).__name__}"
            # The current token may still have a few minutes left; an expired one is useless.
            still_valid = oauth["accessToken"] != rejected and not needs_refresh(oauth, now, margin=0)
            return oauth["accessToken"] if still_valid else None
        self.last_error = None
        return new["claudeAiOauth"]["accessToken"]
