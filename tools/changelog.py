# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing changelog: changelog.json is the single source, CHANGELOG.md is generated.

    python tools/changelog.py            write CHANGELOG.md from changelog.json
    python tools/changelog.py --check    validate, and fail if CHANGELOG.md is out of date
    python tools/changelog.py notes 0.2.0  print the English notes of one version

The test suite runs validate() and the freshness check: no version reaches main without an entry.
"""
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "changelog.json"
TARGET = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"

TAGS = {"new": "New", "fix": "Fixed"}
VERSION = re.compile(r"\d+\.\d+\.\d+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def load(path=SOURCE):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path.name} must be UTF-8 without BOM")
    return json.loads(raw.decode("utf-8"))


def current_version(path=PYPROJECT):
    with path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _key(version):
    return tuple(int(part) for part in version.split("."))


def validate(entries, version):
    """Return a list of problems (empty when the changelog is sound)."""
    if not isinstance(entries, list) or not entries:
        return ["changelog must be a non-empty array"]
    errors = []
    seen = []
    for i, entry in enumerate(entries):
        where = f"entry {i}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: not an object")
            continue
        v = entry.get("version")
        if not isinstance(v, str) or not VERSION.fullmatch(v):
            errors.append(f"{where}: bad version {v!r}")
            continue
        where = v
        if v in seen:
            errors.append(f"{where}: duplicate version")
        elif seen and _key(v) >= _key(seen[-1]):
            errors.append(f"{where}: not newest first (after {seen[-1]})")
        seen.append(v)
        if not isinstance(entry.get("date"), str) or not DATE.fullmatch(entry["date"]):
            errors.append(f"{where}: bad date {entry.get('date')!r}")
        unknown = set(entry) - {"version", "date", "first", "quiet", "items"}
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        items = entry.get("items")
        if not isinstance(items, list):
            errors.append(f"{where}: items must be an array")
            continue
        if not items and entry.get("quiet") is not True:
            errors.append(f'{where}: no items (write "quiet": true if nothing is visible)')
        for j, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{where} item {j}: not an object")
                continue
            for lang in ("en", "fr"):
                text = item.get(lang)
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"{where} item {j}: missing {lang}")
            if "tag" in item and item["tag"] not in TAGS:
                errors.append(f"{where} item {j}: bad tag {item['tag']!r}")
    if sum(1 for e in entries if isinstance(e, dict) and e.get("first")) > 1:
        errors.append('only one entry may be "first"')
    if version not in seen:
        errors.append(f"version {version} (pyproject.toml) has no changelog entry")
    return errors


def _item(item):
    tag = TAGS.get(item.get("tag"))
    return f"- **{tag}** · {item['en']}" if tag else f"- {item['en']}"


def notes(entry):
    """English release notes of one entry, as Markdown bullet lines."""
    if not entry["items"]:
        return "- Small changes under the hood, nothing you'd notice.\n"
    return "".join(_item(item) + "\n" for item in entry["items"])


def render(entries):
    parts = ["# Changelog\n\nWhat changed for you in each version of Mini Monitor, newest first.\n"]
    for entry in entries:
        parts.append(f"\n## {entry['version']} · {entry['date']}\n\n{notes(entry)}")
    return "".join(parts)


def is_fresh(entries, path=TARGET):
    """True when CHANGELOG.md matches changelog.json (line endings ignored)."""
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8").replace("\r\n", "\n") == render(entries)


def main(argv):
    entries = load()
    errors = validate(entries, current_version())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if argv[:1] == ["notes"] and len(argv) == 2:
        entry = next((e for e in entries if e["version"] == argv[1]), None)
        if entry is None:
            print(f"no entry for {argv[1]}", file=sys.stderr)
            return 1
        sys.stdout.buffer.write(notes(entry).encode("utf-8"))
        return 0
    if argv == ["--check"]:
        if not is_fresh(entries):
            print("CHANGELOG.md is out of date: run python tools/changelog.py", file=sys.stderr)
            return 1
        return 0
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    TARGET.write_text(render(entries), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
