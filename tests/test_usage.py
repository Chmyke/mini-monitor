# SPDX-License-Identifier: GPL-3.0-or-later
import json
from datetime import datetime, timezone

from minimonitor import auth, usage

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


# The answer of a plan without a session limit, as read on 2026-11-11.
MODEL_BODY = {
    "five_hour": None,
    "seven_day": {"utilization": 4.0, "resets_at": "2026-11-17T21:59:59.927950+00:00"},
    "limits": [
        {"kind": "weekly_all", "group": "weekly", "percent": 4, "resets_at": "2026-11-17T21:59:59.927950+00:00",
         "scope": None, "is_active": True},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 7, "resets_at": "2026-11-17T21:59:59.928116+00:00",
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None}, "is_active": False},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 30, "resets_at": "2026-11-17T21:59:59.928116+00:00",
         "scope": {"model": {"id": None, "display_name": "Opus"}, "surface": None}, "is_active": False},
    ],
}


def test_model_limit_is_the_first_scoped_entry_that_names_a_model():
    u = usage.parse(MODEL_BODY)
    assert u.session is None and u.week.percent == 4
    assert (u.model.percent, u.model_name) == (7, "Fable")


def test_scoped_entry_without_a_model_is_not_a_model_limit():
    u = usage.parse(LIMITS_BODY)
    assert u.model is None and u.model_name is None
    u = usage.parse({"limits": [{"kind": "weekly_scoped", "percent": 3, "scope": {"model": {"display_name": 5}}}]})
    assert u.model is None


def test_garbage_gives_unknown_not_crash():
    u = usage.parse({"limits": ["x", {"kind": "session", "percent": "high"}], "five_hour": None})
    assert u.session is None and u.week is None


def test_bad_date_keeps_percent():
    u = usage.parse({"five_hour": {"utilization": 5, "resets_at": "soon"}})
    assert u.session.percent == 5 and u.session.resets_at is None


def test_fetch_without_credentials_is_unknown():
    assert usage.fetch(timeout=1) is None


def test_fetch_failure_is_unknown():
    far = 4_000_000_000_000  # year 2096: no renewal attempted
    oauth = {"accessToken": "fake", "refreshToken": "r", "expiresAt": far}
    auth.CREDENTIALS.write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")
    assert usage.fetch(timeout=1) is None  # endpoint redirected to a closed local port
