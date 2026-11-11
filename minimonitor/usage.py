# SPDX-License-Identifier: GPL-3.0-or-later
"""Claude plan usage, read from the OAuth usage endpoint used by Claude Code.

The endpoint is undocumented: any failure yields None so the screen shows '?',
never a stale number. Tokens are never printed nor logged.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from .auth import TokenSource

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


@dataclass(frozen=True)
class Window:
    percent: float
    resets_at: datetime | None


@dataclass(frozen=True)
class Usage:
    session: Window | None
    week: Window | None
    # The weekly limit of the one model that has its own (plans without a session limit).
    model: Window | None = None
    model_name: str | None = None


def _date(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _window(percent, resets_at) -> Window | None:
    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        return None
    return Window(float(percent), _date(resets_at))


def _model_name(item: dict) -> str | None:
    """The display name of the model a scoped limit applies to, as the server spells it."""
    scope = item.get("scope")
    model = scope.get("model") if isinstance(scope, dict) else None
    name = model.get("display_name") if isinstance(model, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def parse(body: dict) -> Usage:
    """Accept both response shapes: the `limits` list, then the legacy windows.

    The model limit is the first `weekly_scoped` entry that names a model: its name comes from
    the server, so the ring follows whichever model is limited next.
    """
    session = week = model = model_name = None
    for item in body.get("limits") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "weekly_scoped" and model is None:
            name = _model_name(item)
            window = _window(item.get("percent"), item.get("resets_at")) if name else None
            if window:
                model, model_name = window, name
            continue
        if item.get("kind") == "session" and session is None:
            session = _window(item.get("percent"), item.get("resets_at"))
        elif item.get("kind") == "weekly_all" and week is None:
            week = _window(item.get("percent"), item.get("resets_at"))
    if session is None:
        five = body.get("five_hour") or {}
        session = _window(five.get("utilization"), five.get("resets_at"))
    if week is None:
        seven = body.get("seven_day") or {}
        week = _window(seven.get("utilization"), seven.get("resets_at"))
    return Usage(session, week, model, model_name)


def _get(token: str, timeout: float) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "mini-monitor",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch(tokens: TokenSource | None = None, timeout: float = 10) -> Usage | None:
    tokens = tokens or TokenSource()
    token = tokens.access_token()
    if not token:
        return None
    try:
        try:
            return parse(_get(token, timeout))
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
            # Rejected before its expiry date (revoked, or renewed elsewhere): renew once.
            token = tokens.access_token(rejected=token)
            return parse(_get(token, timeout)) if token else None
    except Exception:  # network, HTTP or JSON error: the screen shows '?'
        return None
