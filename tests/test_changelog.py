# SPDX-License-Identifier: GPL-3.0-or-later
# The lock: there is no release script (main is the release), so these tests are what refuse a
# version bump without its changelog entry, or a CHANGELOG.md left behind its source.
import pytest

from tools import changelog


def entry(version, **extra):
    return {"version": version, "date": "2026-10-17",
            "items": [{"tag": "new", "en": "Hello.", "fr": "Bonjour."}], **extra}


def test_the_real_changelog_is_sound_and_covers_the_current_version():
    assert changelog.validate(changelog.load(), changelog.current_version()) == []


def test_changelog_md_is_generated_from_the_json():
    assert changelog.is_fresh(changelog.load()), "run: python tools/changelog.py"


def test_a_sound_changelog_passes():
    assert changelog.validate([entry("0.2.0"), entry("0.1.0", first=True)], "0.2.0") == []


@pytest.mark.parametrize("entries, problem", [
    ([entry("0.1.0")], "0.2.0 (pyproject.toml) has no changelog entry"),
    ([entry("0.1.0"), entry("0.2.0")], "not newest first"),
    ([entry("0.2.0"), entry("0.2.0")], "duplicate"),
    ([{**entry("0.2.0"), "items": []}], "no items"),
    ([{**entry("0.2.0"), "items": [{"en": "Hello.", "fr": " "}]}], "missing fr"),
    ([{**entry("0.2.0"), "items": [{"fr": "Bonjour."}]}], "missing en"),
    ([{**entry("0.2.0"), "items": [{"tag": "perf", "en": "a", "fr": "b"}]}], "bad tag"),
    ([{**entry("0.2.0"), "date": "17/10/2026"}], "bad date"),
    ([entry("0.2"), entry("0.2.0")], "bad version"),
    ([entry("0.2.0", first=True), entry("0.1.0", first=True)], "first"),
])
def test_problems_are_reported(entries, problem):
    assert any(problem in e for e in changelog.validate(entries, "0.2.0"))


def test_a_quiet_release_may_have_no_items():
    quiet = {**entry("0.2.0"), "items": [], "quiet": True}
    assert changelog.validate([quiet], "0.2.0") == []
    assert changelog.notes(quiet).startswith("- ")


def test_render_prefixes_tagged_items():
    fix = {**entry("0.1.1"), "items": [{"tag": "fix", "en": "Fixed it.", "fr": "Corrigé."},
                                       {"en": "Plain.", "fr": "Simple."}]}
    md = changelog.render([fix])
    assert "## 0.1.1 · 2026-10-17\n\n- **Fixed** · Fixed it.\n- Plain.\n" in md


def test_a_bom_is_refused(tmp_path):
    path = tmp_path / "changelog.json"
    path.write_bytes(b"\xef\xbb\xbf[]")
    with pytest.raises(ValueError, match="BOM"):
        changelog.load(path)
