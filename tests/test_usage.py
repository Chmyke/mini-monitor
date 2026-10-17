# SPDX-License-Identifier: GPL-3.0-or-later
import json
from datetime import datetime, timezone

from minimonitor import usage

LIMITS_BODY = {
    "five_hour": {"utilization": 11.0, "resets_at": "2026-10-17T00:00:00+00:00"},
    "seven_day": {"utilization": 22.0, "resets_at": "2026-10-20T00:00:00+00:00"},
    "limits": [
        {"kind": "session", "percent": 58, "severity": "normal", "resets_at": "2026-10-17T00:59:59.957113+00:00"},
        {"kind": "weekly_all", "percent": 19, "severity": "normal", "resets_at": "2026-10-20T21:59:59+00:00"},
        {"kind": "weekly_scoped", "percent": 0, "severity": "normal", "resets_at": "2026-10-20T22:00:00+00:00"},
    ],
}


def test_limits_list_wins_over_legacy_windows():
    u = usage.parse(LIMITS_BODY)
    assert u.session.percent == 58
    assert u.session.resets_at == datetime(2026, 10, 17, 0, 59, 59, 957113, tzinfo=timezone.utc)
    assert u.week.percent == 19


def test_legacy_windows_only():
    body = {k: v for k, v in LIMITS_BODY.items() if k != "limits"}
    u = usage.parse(body)
    assert (u.session.percent, u.week.percent) == (11, 22)


def test_garbage_gives_unknown_not_crash():
    u = usage.parse({"limits": ["x", {"kind": "session", "percent": "high"}], "five_hour": None})
    assert u.session is None and u.week is None


def test_bad_date_keeps_percent():
    u = usage.parse({"five_hour": {"utilization": 5, "resets_at": "soon"}})
    assert u.session.percent == 5 and u.session.resets_at is None


def test_fetch_without_credentials_is_unknown():
    assert usage.fetch(timeout=1) is None


def test_fetch_failure_is_unknown(isolated_state):
    usage.CREDENTIALS.write_text(json.dumps({"claudeAiOauth": {"accessToken": "fake"}}), encoding="utf-8")
    assert usage.read_access_token() == "fake"
    assert usage.fetch(timeout=1) is None  # endpoint redirected to a closed local port
