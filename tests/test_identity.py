#!/usr/bin/env python3
"""Keep the published organization, the marketplace name and the selector one fact.

The organization rename to madduck-tech moved three things that only look like
one: the URLs people fetch from, the marketplace `name` the loader reads out of
the manifest, and the `gopnik@<marketplace>` selector every guide teaches. They
have to agree, and nothing here noticed when they did not — a manifest renamed
to anything at all left the whole suite green while every guide still named the
old marketplace, and an installer left pointing at the old organization was seen
by no check in the tree.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKETPLACE = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
PLUGIN = json.loads((ROOT / "plugins/gopnik/.claude-plugin/plugin.json").read_text())

RETIRED_OWNER = "concord" + "loom"

# The old name is a fact about installations that already exist, so it survives
# where a user still carries it: the pre-4.0 selector in the migration table,
# and the notes that tell someone who installed before the rename what to look
# for. Everywhere else it is drift.
ALLOWED_RETIRED = {
    "CONTRIBUTING.md",
    "docs/install.md",
    "docs/migration-v4.md",
    "docs/migration-v4.ru.md",
    "docs/uninstall.md",
    "tests/test_identity.py",
}

GITHUB_HOST = re.compile(
    r"(?:github\.com|raw\.githubusercontent\.com|codeload\.github\.com)"
    r"[:/]([A-Za-z0-9._-]+)"
)
SELECTOR = re.compile(r"gopnik@([A-Za-z0-9._-]+)")


def owner_of(url: str) -> str:
    match = GITHUB_HOST.search(url)
    assert match, f"not a GitHub URL: {url}"
    return match.group(1)


def repository_files() -> list[pathlib.Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [ROOT / raw.decode() for raw in proc.stdout.split(b"\0") if raw]


def readable_files() -> list[tuple[str, str]]:
    out = []
    for path in repository_files():
        if not path.exists() or path.is_symlink() or path.is_dir():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        out.append((path.relative_to(ROOT).as_posix(), data.decode("utf-8", "ignore")))
    return out


ORGANIZATION = owner_of(MARKETPLACE["owner"]["url"])


def test_the_marketplace_name_is_the_organization() -> None:
    # The loader builds the selector out of this string, so a manifest that
    # publishes one name while the guides teach another installs nothing.
    assert MARKETPLACE["name"] == ORGANIZATION, MARKETPLACE["name"]


def test_both_manifests_point_at_the_same_organization() -> None:
    entry = MARKETPLACE["plugins"][0]
    urls = {
        "marketplace owner": MARKETPLACE["owner"]["url"],
        "entry author": entry["author"]["url"],
        "entry homepage": entry["homepage"],
        "entry repository": entry["repository"],
        "plugin author": PLUGIN["author"]["url"],
        "plugin homepage": PLUGIN["homepage"],
        "plugin repository": PLUGIN["repository"],
    }
    wrong = {
        where: url for where, url in urls.items() if owner_of(url) != ORGANIZATION
    }
    assert not wrong, f"these name another organization: {wrong}"


def test_every_published_url_names_the_current_organization() -> None:
    # install.sh fetches its own payload over these, and no other check in the
    # tree reads them: an installer left on the old organization was invisible
    # to every test until this one.
    strays: list[str] = []
    for relative, text in readable_files():
        if relative in ALLOWED_RETIRED:
            continue
        for owner in set(GITHUB_HOST.findall(text)):
            if owner != ORGANIZATION:
                strays.append(f"{relative}: {owner}")
    assert not strays, f"URLs naming another organization: {sorted(strays)}"


def test_every_selector_names_the_published_marketplace() -> None:
    strays: list[str] = []
    for relative, text in readable_files():
        if relative in ALLOWED_RETIRED:
            continue
        for name in set(SELECTOR.findall(text)):
            if name != MARKETPLACE["name"]:
                strays.append(f"{relative}: gopnik@{name}")
    assert not strays, f"selectors naming another marketplace: {sorted(strays)}"


def test_the_retired_organization_is_confined_to_the_pre_rename_notes() -> None:
    leaks = [
        relative
        for relative, text in readable_files()
        if relative not in ALLOWED_RETIRED and RETIRED_OWNER in text.lower()
    ]
    assert not leaks, f"retired organization leaked outside the notes: {leaks}"


def _main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL {name}: {exc}")
    print(f"\n{'FAILED' if failures else 'all tests passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
