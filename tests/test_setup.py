#!/usr/bin/env python3
"""Tests for gopnik_setup.py and for what install.sh leaves behind.

Three kinds of assertion here, and the last two are the unusual ones.

The ordinary kind: it detects what it should, writes only what it may, and
refuses when it cannot tell.

The second kind: **what the installer does NOT do**. Since #33 the whole
argument for this tool is that it takes no decisions on the user's behalf, and
"takes no decisions" is only a requirement if something fails when it does. So
the tests assert the absence of wiring, of hook files, and of any edit to a file
the project owns.

The third kind: **what the user reads is tested**. "Friendly" is normally a
matter of taste and therefore un-gateable, so it is pinned to things a machine
can check — a list of words that must not appear, a line count, and the
statements the closing message owes the reader. A requirement that cannot fail
is not a requirement.

Run with: python3 tests/test_setup.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "gopnik" / "skills"
SETUP = SKILLS / "gopnik-setup" / "gopnik_setup.py"
INSTALL = ROOT / "install.sh"
LIVE_SETUP_ORACLE = ROOT / "scripts" / "check_live_setup_turn.py"

# Load-bearing internally, meaningless to someone being set up. The whole point
# of the amendment on #13 is that this list is checked rather than intended.
# Matched with word boundaries and with hyphens and underscores treated as
# spaces: a plain substring list was defeated by writing "Stage-1",
# "artifact kind" and "Blast-radius", which read exactly as badly.
JARGON = [
    "oracle", "delivery boundary", "stage 0", "stage 1", "stage 2",
    "counterexample", "counter example", "blast radius", "artifact kind",
    "adversary", "marker", "cartesian", "sentinel", "predicate", "idempotent",
    "topology", "semantics", "verdict", "gopnik_", "falsifier", "adjudicate",
    "persisted", "vector", "contract",
]


def jargon_in(text: str) -> list[str]:
    """Words from the list, with hyphens folded and plurals stemmed.

    Honest about what this is: a smoke check, not a proof. A denylist of
    surface forms cannot carry "write like a person" — the first version was
    defeated by a hyphen, the second by an `s`, and a third evasion certainly
    exists. It catches the drift that happens by accident, which is the drift
    that actually happens. The requirement is carried by the line count, the
    closing statements, and by somebody reading it.
    """
    flat = re.sub(r"[-_/]+", " ", text.lower())
    flat = re.sub(r"\s+", " ", flat)
    words = [re.sub(r"(ies|es|s)$", "", w) for w in flat.split()]
    flat = " ".join(words)
    found = []
    for term in JARGON:
        stem = " ".join(re.sub(r"(ies|es|s)$", "", w) for w in term.split())
        if re.search(r"\b" + re.escape(stem) + r"\b", flat):
            found.append(term)
    return found


# Keys that no longer have any reader. A config key nobody reads is a lie with a
# schema, so writing one is a failure rather than a harmless leftover.
DEAD_KEYS = [
    "enforce", "claim_patterns", "ignore_patterns", "source_extensions",
    "watch_paths", "marker",
]

#: What actually consults a configuration at runtime. The gate is the file a
#: session reads before it judges anything, so a key it never names is a key no
#: run will ever act on. Deliberately not `gopnik_setup.py`: grepping the writer
#: for the key it just wrote is how a check of this shape passes vacuously.
CONFIG_READERS = (
    SKILLS / "gopnik" / "SKILL.md",
    SKILLS / "gopnik" / "SKILL.ru.md",
)


def project(files: dict[str, str]) -> pathlib.Path:
    """Build a throwaway project with the setup script beside its skill."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    target = tmp / ".claude" / "skills" / "gopnik-setup"
    target.mkdir(parents=True)
    (target / "gopnik_setup.py").write_text(SETUP.read_text(encoding="utf-8"), encoding="utf-8")
    # `_write` rather than a loop here: some fixtures need a directory, which a
    # signal like `charts` or `k8s` actually is, and writing it as a file made
    # those kinds untestable through this helper.
    _write(tmp, files)
    return tmp


def run_setup(root: pathlib.Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(root / ".claude" / "skills" / "gopnik-setup" / "gopnik_setup.py"), *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"},
    )
    return proc.returncode, proc.stdout + proc.stderr


def run_install(target: pathlib.Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["sh", str(INSTALL), *args],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def config_of(root: pathlib.Path) -> dict:
    for relative in (".claude/gopnik.json", ".codex/gopnik.json", "gopnik.json"):
        if (root / relative).exists():
            return json.loads((root / relative).read_text(encoding="utf-8"))
    raise AssertionError(f"no configuration anywhere under {root}")


PY_PROJECT = {
    "pyproject.toml": '[project]\nname = "demo"\nversion = "0.1"\n',
    "tests/test_demo.py": "def test_ok():\n    assert True\n",
}

# A mutant got through every round by being wrong only for projects the tests
# never built. The "never" rules are checked against these too.
MAKE_PROJECT = {"Makefile": "test:\n\t@true\n"}
DOCKER_PROJECT = {"Dockerfile": "FROM scratch\n"}


def _every_runner() -> dict:
    """One fixture per entry in RUNNERS, built from RUNNERS itself.

    A hand-listed subset is why the fourth mutant died and the fifth did not:
    the list said Node and Go, the code also supports Rust, and the mutant was
    wrong only there. Deriving the fixtures from the code means adding a runner
    cannot leave a hole.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    seeds = {
        "pyproject.toml": '[project]\nname = "d"\nversion = "1"\n',
        "package.json": json.dumps({"name": "d", "scripts": {"test": "exit 0"}}),
        "Cargo.toml": '[package]\nname = "d"\nversion = "0.1.0"\nedition = "2021"\n',
        "go.mod": "module example.com/d\n\ngo 1.21\n",
    }
    out = {}
    for runner in gopnik_setup.RUNNERS:
        marker = next((f for f in runner["files"] if f in seeds), None)
        assert marker, f"no fixture seed for runner {runner['name']} — add one"
        out[runner["name"]] = {marker: seeds[marker]}
    return out


OTHER_PROJECTS = {k: v for k, v in _every_runner().items() if k != "Python"}


# --------------------------------------------------------------- behaviour


def test_sets_up_a_python_project():
    root = project(PY_PROJECT)
    code, out = run_setup(root)
    assert code == 0, out
    cfg = config_of(root)["verification"]
    assert cfg["artifact_kind"] == "library", cfg
    assert cfg["stage1"], "no checks were written at all"
    assert not any("replace with" in c for c in cfg["stage1"]), cfg["stage1"]


def test_setup_persists_the_selected_operator_language():
    root = project(PY_PROJECT)
    code, out = run_setup(root, "--language", "ru")
    assert code == 0, out
    assert config_of(root)["language"] == "ru"


def test_an_explicit_language_update_preserves_a_hand_written_verification_block():
    hand = {
        "verification": {
            "artifact_kind": "migration",
            "stage1": ["true"],
            "stage2": ["true"],
            "notes": "keep me",
        },
        "something_else": {"kept": True},
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    code, out = run_setup(root, "--language", "ru")
    assert code == 0, out
    body = config_of(root)
    assert body["language"] == "ru"
    assert body["verification"] == hand["verification"]
    assert body["something_else"] == hand["something_else"]


def test_check_mode_does_not_persist_a_language_update():
    hand = {"verification": {"artifact_kind": "library", "stage1": ["true"], "stage2": []}}
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--check", "--language", "ru")
    assert code == 0, out
    assert (root / "gopnik.json").read_bytes() == before


def test_each_skill_reuses_the_persisted_operator_language():
    for skill in ("gopnik", "gopnik-critic", "gopnik-setup"):
        for suffix in ("SKILL.md", "SKILL.ru.md"):
            text = (SKILLS / skill / suffix).read_text(encoding="utf-8")
            assert "`language`" in text, (skill, suffix)
            assert "`gopnik.json`" in text, (skill, suffix)


def test_never_writes_a_check_it_did_not_run():
    root = project(PY_PROJECT)
    run_setup(root)
    for cmd in config_of(root)["verification"]["stage1"]:
        assert subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True).returncode == 0, cmd


def test_never_writes_a_check_it_did_not_run_in_any_language():
    for name, files in OTHER_PROJECTS.items():
        root = project(files)
        code, _ = run_setup(root)
        if code != 0:
            continue  # the toolchain is absent here; nothing was written
        for cmd in config_of(root)["verification"]["stage1"]:
            got = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True)
            assert got.returncode == 0, f"{name}: wrote {cmd!r}, which exits {got.returncode}"


def _every_key_the_writer_can_produce(gopnik_setup, root: pathlib.Path) -> set[str]:
    """Drive every writing path there is and collect the keys it leaves."""
    keys: set[str] = set()

    def collect(path: pathlib.Path) -> None:
        body = json.loads(path.read_text(encoding="utf-8"))
        keys.update(body)
        keys.update(body.get("verification") or {})

    for kind in list(gopnik_setup.STAGE2_HINT_BY_KIND) + ["library"]:
        for language in (None, "en", "ru"):
            collect(gopnik_setup.write_config(
                root, kind, ["true"], dry=False, language=language,
            ))
    collect(gopnik_setup.write_config(
        root, None, ["true"], dry=False, defer_artifact_kind=True,
    ))
    collect(gopnik_setup.confirm_artifact_kind(
        root, "service", surfaces=["service", "chart"],
    ))
    return keys


def test_never_writes_a_key_that_nothing_reads():
    """#33: the hooks are gone, so their keys are no longer configuration.

    Asserted at write_config rather than end-to-end, because a project where
    detection fails writes nothing at all and would pass this vacuously.

    #77 turned the list into a rule. A fixed denylist only catches the keys that
    were already known to be dead, so a *new* key with no reader passed this
    silently — which is how the surviving-surface set could have been recorded
    for a year without a single run ever consulting it. Now every key the writer
    can produce is checked against what actually reads a configuration, in both
    languages: a reader that exists only in English leaves a Russian session
    holding a key it has never been told about.

    Named *as a key*, not merely present as a word. The first version of this
    asked whether the key's name appeared anywhere in the prose, and an
    adversary walked straight through it: `scope` occurs five times in the gate
    skill, every one inside the verdict phrase `READY scope`, so a dead
    `verification.scope` would have passed the check that exists to forbid
    exactly that. A one-letter `e` passed the same way. `boundary` did not, and
    only by luck — it is in the English skill and absent from the Russian one,
    and this reads both.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        for kind in list(gopnik_setup.STAGE2_HINT_BY_KIND) + ["library"]:
            path = gopnik_setup.write_config(root, kind, ["true"], dry=False)
            body = json.loads(path.read_text(encoding="utf-8"))
            for key in DEAD_KEYS:
                assert key not in body, f"{kind}: wrote dead key {key}"
                assert key not in body["verification"], f"{kind}: wrote dead key {key}"

    with tempfile.TemporaryDirectory() as d:
        written = _every_key_the_writer_can_produce(gopnik_setup, pathlib.Path(d))
        assert "surfaces" in written, "the writer stopped recording the confirmed set"
        for key in sorted(written):
            if key.startswith("//"):
                continue  # a comment is addressed to a person, not to a reader
            for reader in CONFIG_READERS:
                prose = reader.read_text(encoding="utf-8")
                assert f'"{key}"' in prose or f"`{key}`" in prose, (
                    f"{key!r} is written and {reader.name} never names it as a key"
                )


def test_confirmation_records_every_surface_that_was_confirmed():
    """#77. `artifact_kind` is one word; a hybrid project delivers through more.

    The negative this closes: the critic's surviving set used to phrase one
    question and then be dropped, so a project with four delivery surfaces and a
    project with one produced byte-identical configurations, and the rule that
    Stage 2 covers every confirmed surface had nothing to read.
    """
    root = project(PY_PROJECT)
    assert run_setup(root, "--defer-artifact-kind", "--language", "en")[0] == 0
    code, out = run_setup(
        root, "--confirm-artifact-kind", "service", "--surfaces", "service, chart",
    )
    assert code == 0, out
    verification = config_of(root)["verification"]
    assert verification["artifact_kind"] == "service", verification
    assert verification["surfaces"] == ["service", "chart"], verification
    assert "chart" in out, out


def test_a_confirmed_set_keeps_its_order_and_loses_its_repeats():
    root = project(PY_PROJECT)
    assert run_setup(root, "--defer-artifact-kind", "--language", "en")[0] == 0
    code, out = run_setup(
        root, "--confirm-artifact-kind", "cli", "--surfaces", " cli , web ,cli,, ",
    )
    assert code == 0, out
    assert config_of(root)["verification"]["surfaces"] == ["cli", "web"], out


def test_surfaces_are_refused_outside_the_confirmation_step():
    """Nothing else in this script asked a person what the surfaces are."""
    root = project(PY_PROJECT)
    code, out = run_setup(root, "--surfaces", "cli,web")
    assert code == 2, out
    assert "--confirm-artifact-kind" in out, out
    assert not (root / "gopnik.json").exists(), out


def test_an_empty_confirmed_set_is_refused_rather_than_recorded():
    """An empty set would read as `no surfaces`, which no project has."""
    root = project(PY_PROJECT)
    assert run_setup(root, "--defer-artifact-kind", "--language", "en")[0] == 0
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--confirm-artifact-kind", "cli", "--surfaces", " , ")
    assert code == 2, out
    assert (root / "gopnik.json").read_bytes() == before, out


def test_a_confirmation_that_asks_nothing_leaves_a_recorded_set_alone():
    """The key this writes is also a key it must never remove.

    A person who edited the set by hand, and a run that finalizes a kind without
    being told about surfaces, must not cancel each other out.
    """
    hand = {
        "language": "en",
        "//": "kept",
        "verification": {
            "//artifact_kind": "Pending confirmation of how people use this project after delivery.",
            "stage1": ["true"],
            "stage2": [],
            "surfaces": ["cli", "web", "job"],
            "notes": "hand written",
        },
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand, indent=2)})
    code, out = run_setup(root, "--confirm-artifact-kind", "service")
    assert code == 0, out
    verification = config_of(root)["verification"]
    assert verification["surfaces"] == ["cli", "web", "job"], verification
    assert verification["artifact_kind"] == "service", verification
    assert verification["notes"] == "hand written", verification


def test_a_configuration_from_before_the_key_never_grows_one_by_itself():
    """The far side of the boundary: every `gopnik.json` already on disk.

    4.0.x and 5.0 wrote no surfaces. Reading one of those files must not produce
    an inferred set, because a surface nobody confirmed is worse than a missing
    one — it is a hole that reads as covered.
    """
    old = {
        "language": "en",
        "verification": {
            "artifact_kind": "cli",
            "stage1": ["true"],
            "stage2": ["true"],
            "notes": "written by 4.0.19",
        },
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(old, indent=2)})
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root)
    assert code == 0, out
    assert (root / "gopnik.json").read_bytes() == before, out
    assert "surfaces" not in config_of(root)["verification"], out


def test_a_configured_project_is_told_which_surfaces_stage2_must_cover():
    """The second reader, at the one other moment the set is actionable.

    A verdict reads `surfaces` to decide what is `Not proven`. This run reads it
    where somebody is about to write the steps, which is the moment the record
    can still change the outcome rather than only describe it.
    """
    config = {
        "language": "en",
        "verification": {
            "artifact_kind": "cli",
            "surfaces": ["command", "chart"],
            "stage1": ["true"],
            "stage2": [],
        },
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(config, indent=2)})
    code, out = run_setup(root)
    assert code == 0, out
    assert "command" in out and "chart" in out, out

    # One surface is what the kind already said, so saying it again is noise.
    config["verification"]["surfaces"] = ["command"]
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(config, indent=2)})
    code, out = run_setup(root)
    assert code == 0, out
    assert "has to cover" not in out, out

    # This file is hand-editable. A string where a list belongs is read as no
    # set at all, rather than as one surface per character.
    config["verification"]["surfaces"] = "command"
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(config, indent=2)})
    code, out = run_setup(root)
    assert code == 0, out
    assert "has to cover" not in out, out
    assert "c, o, m" not in out, out


def test_refuses_every_unsupported_build_system_rather_than_guessing():
    for files in (MAKE_PROJECT, DOCKER_PROJECT):
        root = project(files)
        code, out = run_setup(root)
        assert code == 2, out
        assert "could not find" in out.lower(), out
        assert "Stage 1 check" in out, out
        assert not (root / "gopnik.json").exists(), "wrote a config for a project it did not recognise"


def test_refuses_a_project_it_cannot_recognise():
    root = project({"README.md": "hello\n"})
    code, out = run_setup(root)
    assert code == 2, out
    assert "Nothing was changed" in out, out


def test_unknown_guided_project_asks_only_for_stage1():
    root = project({"README.md": "hello\n"})
    code, out = run_setup(root, "--defer-artifact-kind", "--language", "en")
    assert code == 2, out
    assert "Stage 1 check" in out, out
    for premature in ("service", "package", "command they type", "delivery surface"):
        assert premature not in out.lower(), out
    assert not (root / "gopnik.json").exists()


def test_project_instructions_block_generic_toolchain_guesses():
    root = project({
        "go.mod": "module example.com/wrapped-project\n\ngo 1.25\n",
        "AGENTS.md": (
            "Always use `app.sh` for build and test - never run `go build` "
            "or `go test` directly.\n"
        ),
        "app.sh": "#!/bin/sh\nprintf 'wrapper ran\\n' >> wrapper.log\n",
    })
    code, out = run_setup(root)
    assert code == 2, out
    assert "Project instructions found: AGENTS.md" in out, out
    assert "--stage1 COMMAND" in out, out
    assert "--artifact-kind" not in out, out
    assert not (root / "wrapper.log").exists(), "ran a command before reading project rules"
    assert not (root / "gopnik.json").exists(), "configured from a forbidden generic guess"


def test_explicit_project_owned_checks_replace_generic_go_commands():
    root = project({
        "go.mod": "module example.com/wrapped-project\n\ngo 1.25\n",
        "Dockerfile": "FROM scratch\n",
        "AGENTS.md": "Always use `app.sh` for build and test.\n",
        "app.sh": "#!/bin/sh\nprintf '%s\\n' \"$1\" >> wrapper.log\n",
    })
    (root / "app.sh").chmod(0o755)
    code, out = run_setup(
        root,
        "--stage1", "./app.sh --smoke",
        "--artifact-kind", "service",
    )
    assert code == 0, out
    assert (root / "wrapper.log").read_text(encoding="utf-8") == "--smoke\n"
    stage1 = config_of(root)["verification"]["stage1"]
    assert stage1 == ["./app.sh --smoke"], stage1
    assert not any(command.startswith("go ") for command in stage1), stage1


def test_guided_setup_defers_artifact_kind_until_user_confirmation():
    root = project({
        "go.mod": "module example.com/hybrid\n\ngo 1.25\n",
        "AGENTS.md": "Always use `app.sh` for the fast check.\n",
        "app.sh": "#!/bin/sh\nprintf '%s\\n' \"$1\" >> wrapper.log\n",
    })
    (root / "app.sh").chmod(0o755)

    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--language", "ru",
        "--stage1", "./app.sh --smoke",
    )
    assert code == 0, out
    verification = config_of(root)["verification"]
    assert "artifact_kind" not in verification, verification
    assert verification["//artifact_kind"], verification
    assert verification["stage1"] == ["./app.sh --smoke"], verification
    assert verification["stage2"] == [], verification
    assert (root / "wrapper.log").read_text(encoding="utf-8") == "--smoke\n"

    code, out = run_setup(root, "--confirm-artifact-kind", "service")
    assert code == 0, out
    verification = config_of(root)["verification"]
    assert verification["artifact_kind"] == "service", verification
    assert "//artifact_kind" not in verification, verification
    assert verification["stage1"] == ["./app.sh --smoke"], verification
    assert (root / "wrapper.log").read_text(encoding="utf-8") == "--smoke\n", (
        "confirmation reran Stage 1 instead of preserving its evidence"
    )


def test_generic_guided_setup_cannot_skip_surface_confirmation():
    root = project(PY_PROJECT)
    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--language", "en",
    )
    assert code == 0, out
    verification = config_of(root)["verification"]
    assert verification["stage1"], verification
    assert "artifact_kind" not in verification, verification
    assert verification["stage2"] == [], verification
    assert "Still missing" not in out, out
    assert "Delivery surfaces still need confirmation" in out, out


def test_artifact_kind_confirmation_refuses_non_provisional_configuration():
    hand = {
        "verification": {
            "artifact_kind": "cli",
            "stage1": ["true"],
            "stage2": [],
            "notes": "hand written",
        }
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--confirm-artifact-kind", "service")
    assert code == 2, out
    assert "only be confirmed" in out, out
    assert (root / "gopnik.json").read_bytes() == before


def test_existing_configuration_is_marked_then_reconfirmed_without_data_loss():
    hand = {
        "language": "en",
        "team": {"owner": "platform"},
        "verification": {
            "artifact_kind": "cli",
            "stage1": ["./check.sh"],
            "stage2": ["./deployed-check.sh"],
            "notes": "Keep the existing operational note.",
            "custom": {"preserve": True},
        },
    }
    root = project({
        "gopnik.json": json.dumps(hand),
        "check.sh": "#!/bin/sh\nprintf 'run\\n' >> check.log\n",
    })
    (root / "check.sh").chmod(0o755)

    code, out = run_setup(root, "--defer-artifact-kind", "--language", "ru")
    assert code == 0, out
    pending = config_of(root)
    assert pending["language"] == "ru", pending
    assert pending["team"] == hand["team"], pending
    assert pending["verification"]["artifact_kind"] == "cli", pending
    assert pending["verification"]["//artifact_kind"], pending
    assert pending["verification"]["stage2"] == ["./deployed-check.sh"], pending
    assert pending["verification"]["notes"] == hand["verification"]["notes"], pending
    assert pending["verification"]["custom"] == {"preserve": True}, pending

    code, out = run_setup(root, "--confirm-artifact-kind", "service")
    assert code == 0, out
    confirmed = config_of(root)
    assert confirmed["verification"]["artifact_kind"] == "service", confirmed
    assert "//artifact_kind" not in confirmed["verification"], confirmed
    assert confirmed["verification"]["stage1"] == ["./check.sh"], confirmed
    assert confirmed["verification"]["stage2"] == ["./deployed-check.sh"], confirmed
    assert confirmed["verification"]["notes"] == hand["verification"]["notes"], confirmed
    assert confirmed["verification"]["custom"] == {"preserve": True}, confirmed
    assert (root / "check.log").read_text(encoding="utf-8") == "run\n"


def test_rerunning_a_provisional_setup_does_not_rerun_or_misclassify_it():
    root = project({
        "AGENTS.md": "Always use `app.sh` for the fast check.\n",
        "app.sh": "#!/bin/sh\nprintf 'run\\n' >> wrapper.log\n",
    })
    (root / "app.sh").chmod(0o755)

    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--language", "en",
        "--stage1", "./app.sh --smoke",
    )
    assert code == 0, out
    before = (root / "gopnik.json").read_bytes()

    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--check",
        "--stage1", "./app.sh --smoke",
    )
    assert code == 0, out
    assert "Delivery surfaces still need confirmation" in out, out
    assert "package" not in out.lower(), out
    assert "Stage 2:" not in out, out
    assert (root / "wrapper.log").read_text(encoding="utf-8") == "run\n"
    assert (root / "gopnik.json").read_bytes() == before


def test_pending_surface_confirmation_blocks_stage2_drafts():
    root = project({
        "Dockerfile": "FROM scratch\n",
        "check.sh": "#!/bin/sh\nexit 0\n",
    })
    (root / "check.sh").chmod(0o755)
    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--language", "en",
        "--stage1", "./check.sh",
    )
    assert code == 0, out

    code, out = run_setup(root, "--draft-stage2")
    assert code == 2, out
    assert "Delivery surfaces still need confirmation" in out, out
    for leaked in ("gopnik.json", "YOUR_URL", "A draft", "verification.stage2"):
        assert leaked not in out, out


def test_defer_and_explicit_artifact_kind_are_mutually_exclusive():
    root = project(PY_PROJECT)
    code, out = run_setup(
        root,
        "--defer-artifact-kind",
        "--artifact-kind", "library",
    )
    assert code == 2, out
    assert "mutually exclusive" in out, out
    assert not (root / "gopnik.json").exists()


def test_one_red_project_owned_check_blocks_setup_instead_of_writing_a_subset():
    root = project({
        "go.mod": "module example.com/wrapped-project\n\ngo 1.25\n",
        "Dockerfile": "FROM scratch\n",
        "AGENTS.md": "Always use `app.sh` for build and test.\n",
        "app.sh": "#!/bin/sh\n[ \"$1\" = --smoke ]\n",
    })
    (root / "app.sh").chmod(0o755)
    code, out = run_setup(
        root,
        "--stage1", "./app.sh --smoke",
        "--stage1", "./app.sh --test",
        "--artifact-kind", "service",
    )
    assert code == 2, out
    assert "setup is blocked" in out, out
    assert "ok       ./app.sh --smoke" in out, out
    assert "FAILING  ./app.sh --test" in out, out
    assert not (root / "gopnik.json").exists(), "wrote a partial required baseline"


def test_a_red_smoke_check_stops_before_the_long_project_owned_suite():
    root = project({
        "go.mod": "module example.com/wrapped-project\n\ngo 1.25\n",
        "Dockerfile": "FROM scratch\n",
        "AGENTS.md": "Always use `app.sh`; smoke before the full suite.\n",
        "app.sh": (
            "#!/bin/sh\n"
            "if [ \"$1\" = --smoke ]; then exit 1; fi\n"
            "touch long-suite-ran\n"
        ),
    })
    (root / "app.sh").chmod(0o755)
    code, out = run_setup(
        root,
        "--stage1", "./app.sh --smoke",
        "--stage1", "./app.sh --test",
        "--artifact-kind", "service",
    )
    assert code == 2, out
    assert "FAILING  ./app.sh --smoke" in out, out
    assert "./app.sh --test" not in out, out
    assert not (root / "long-suite-ran").exists(), "ran the full suite after red smoke"


def test_a_configured_project_runs_its_own_checks():
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(
        {"verification": {"artifact_kind": "service", "stage1": ["true"], "stage2": ["true"]}})})
    code, out = run_setup(root)
    assert code == 0, out
    assert "ok       true" in out, out


def test_a_configured_project_reachable_only_by_hand_still_gets_an_answer():
    root = project({**MAKE_PROJECT, "gopnik.json": json.dumps(
        {"verification": {"artifact_kind": "cli", "stage1": ["true"], "stage2": ["true"]}})})
    code, out = run_setup(root)
    assert code == 0, out
    assert "Already configured" in out, out


def test_a_hand_written_step_is_not_mistaken_for_the_placeholder():
    hand = {"//": "mine", "verification": {"artifact_kind": "migration", "stage1": ["true"], "stage2": ["true"],
                                           "notes": "prod account 1234"}}
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    run_setup(root)
    assert config_of(root) == hand, "rewrote a hand-written configuration"


def test_leaves_a_hand_written_configuration_alone():
    hand = {"verification": {"artifact_kind": "migration", "stage1": ["true"], "stage2": ["true"]},
            "something_else": {"kept": True}}
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    before = (root / "gopnik.json").read_bytes()
    run_setup(root)
    assert (root / "gopnik.json").read_bytes() == before


def test_replaces_the_example_placeholders():
    example = (ROOT / "gopnik.example.json").read_text(encoding="utf-8")
    root = project({**PY_PROJECT, "gopnik.json": example})
    code, out = run_setup(root)
    assert code == 0, out
    stage1 = config_of(root)["verification"]["stage1"]
    assert not any("replace with" in c for c in stage1), stage1


def test_the_example_markers_still_match_the_shipped_file():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    example = json.loads((ROOT / "gopnik.example.json").read_text(encoding="utf-8"))
    assert gopnik_setup.is_the_installers_copy(example), (
        "gopnik.example.json drifted from the strings setup recognises it by, "
        "so a fresh install would be treated as hand-configured and left with placeholders"
    )


def test_an_existing_configuration_is_never_modified_where_it_was_not_asked():
    example = json.loads((ROOT / "gopnik.example.json").read_text(encoding="utf-8"))
    example["mine"] = {"keep": "this"}
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(example)})
    run_setup(root)
    assert config_of(root)["mine"] == {"keep": "this"}


def test_stage2_never_holds_something_that_was_not_run():
    root = project(PY_PROJECT)
    run_setup(root)
    assert config_of(root)["verification"]["stage2"] == []


def test_check_mode_changes_nothing():
    root = project(PY_PROJECT)
    code, out = run_setup(root, "--check")
    assert code == 0, out
    assert not (root / "gopnik.json").exists(), "wrote a config in --check mode"


def test_check_names_the_file_the_real_run_would_write():
    root = project(PY_PROJECT)
    _, out = run_setup(root, "--check")
    assert "gopnik.json" in out, out
    _, _ = run_setup(root)
    assert (root / "gopnik.json").exists(), "the real run wrote somewhere else"


def test_a_failing_check_is_called_failing_not_absent():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    passing, missing, timed_out, broken = gopnik_setup.sort_results(
        [("a", 0, ""), ("b", 1, "boom"), ("c", 127, ""), ("d", 124, "")])
    assert passing == ["a"] and missing == ["c"] and timed_out == ["d"]
    assert broken == [("b", "boom")]


def test_an_explicit_wrapper_exit_127_reports_its_nested_dependency_failure():
    """A wrapper can exist while one of its nested dependencies is missing.

    Setup used to call the wrapper "not installed here", hiding the actual
    failure and sending onboarding into an unrelated infrastructure discussion.
    """
    root = project({
        "AGENTS.md": "Use ./app.sh --smoke for the fast check.\n",
        "go.mod": "module example.com/wrapped-project\n\ngo 1.24\n",
        "app.sh": "#!/bin/sh\nmissing-project-tool\n",
    })
    (root / "app.sh").chmod(0o755)

    code, out = run_setup(
        root,
        "--artifact-kind", "service",
        "--stage1", "./app.sh --smoke",
    )

    assert code == 2, out
    assert "FAILING  ./app.sh --smoke" in out, out
    assert "missing-project-tool" in out, out
    assert "not installed here" not in out, out


def test_a_failing_check_is_reported_as_failing_end_to_end():
    root = project({**PY_PROJECT, "tests/test_demo.py": "def test_bad():\n    assert False\n"})
    code, out = run_setup(root)
    written = config_of(root)["verification"]["stage1"] if code == 0 else []
    assert "pytest -q" not in written, "wrote a check that fails here"


def test_only_a_passing_check_is_ever_written():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        passing, _, _, _ = gopnik_setup.sort_results(
            [("ok", 0, ""), ("fails", 1, ""), ("slow", 124, ""), ("gone", 127, "")])
        path = gopnik_setup.write_config(root, "library", passing, dry=False)
        assert json.loads(path.read_text(encoding="utf-8"))["verification"]["stage1"] == ["ok"]


def test_a_timed_out_check_is_never_written():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        code, _ = gopnik_setup.run("sleep 5", pathlib.Path(d), timeout=1)
        assert code == 124


def test_cli_timeout_budget_applies_to_project_owned_checks():
    root = project({
        "AGENTS.md": "Use ./slow-check for Stage 1.\n",
        "Dockerfile": "FROM scratch\n",
        "slow-check": "#!/bin/sh\nsleep 5\n",
    })
    (root / "slow-check").chmod(0o755)

    code, out = run_setup(
        root,
        "--artifact-kind", "service",
        "--stage1", "./slow-check",
        "--timeout-seconds", "1",
    )

    assert code == 2, out
    assert "too slow ./slow-check" in out, out
    assert not (root / "gopnik.json").exists(), "a timed-out baseline was persisted"


def test_a_timed_out_check_does_not_leave_the_tree_running():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        stamp = root / "still-alive"
        gopnik_setup.run(f"sh -c 'sleep 3; touch {stamp}' &  sleep 5", root, timeout=1)
        subprocess.run(["sleep", "4"])
        assert not stamp.exists(), "a grandchild outlived the timeout"


def test_a_check_never_inherits_stdin():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        code, out = gopnik_setup.run("cat", pathlib.Path(d), timeout=5)
        assert code == 0 and out == "", f"a check read from stdin: {code} {out!r}"


def test_a_project_path_with_a_space_is_still_recognised():
    tmp = pathlib.Path(tempfile.mkdtemp()) / "a project"
    tmp.mkdir()
    target = tmp / ".claude" / "skills" / "gopnik-setup"
    target.mkdir(parents=True)
    (target / "gopnik_setup.py").write_text(SETUP.read_text(encoding="utf-8"), encoding="utf-8")
    for name, text in PY_PROJECT.items():
        path = tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    code, out = run_setup(tmp)
    assert code == 0, out
    assert (tmp / "gopnik.json").exists(), out


# --------------------------------------------------------- where it writes


def test_an_earlier_installs_config_is_kept_where_it_is():
    """Both older locations, and .claude wins when a project has both.

    Reversing the search order passed the whole suite until a project was built
    with both, because setup then wrote to a file the reader would not find.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for present, expected in (
        ([".claude"], ".claude"),
        ([".codex"], ".codex"),
        ([".claude", ".codex"], ".claude"),
    ):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for agent in present:
                (root / agent).mkdir()
                (root / agent / "gopnik.json").write_text("{}", encoding="utf-8")
            got = gopnik_setup.resolve_config(root)
            assert got.parent.name == expected, f"{present} resolved to {got}"


def test_a_project_with_no_earlier_config_gets_one_in_its_root():
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / ".claude").mkdir()  # an agent directory is not a config location
        got = gopnik_setup.resolve_config(root)
        assert got == root / "gopnik.json", got


# --------------------------------------------------------- which kind it is


def _kind_fixtures() -> list[tuple[str, str, dict]]:
    """One project per kind the code can return, derived from the code.

    Hand-listing is why a mutant survived once already: the list named Node and
    Go, the code also supported Rust, and the mutant was wrong only there. Here
    the denominator is KIND_SIGNALS plus the two branches of
    _looks_like_a_command, so adding a signal without a fixture fails the test
    below rather than quietly widening the gap.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    base = {"pyproject.toml": '[project]\nname = "d"\nversion = "1"\n'}
    # A seed per signal file, chosen so the file is the ONLY thing that differs.
    seeds = {
        "Chart.yaml": "name: d\nversion: 0.1.0\n",
        "charts": None,          # a directory
        "main.tf": 'resource "null_resource" "d" {}\n',
        "Dockerfile": "FROM scratch\n",
        "docker-compose.yml": "services: {}\n",
        "k8s": None,
        "deploy": None,
    }
    out = []
    for kind, signals in gopnik_setup.KIND_SIGNALS:
        for signal in signals:
            assert signal in seeds, f"no fixture seed for KIND_SIGNALS entry {signal!r} — add one"
            files = dict(base)
            files[signal] = seeds[signal]
            out.append((f"{kind} via {signal}", kind, files))
    # The two branches that make a project a command. Not in KIND_SIGNALS —
    # its "cli" row is deliberately empty and decided from the manifests.
    out.append(("cli via [project.scripts]", "cli", {
        "pyproject.toml": '[project]\nname = "d"\nversion = "1"\n\n[project.scripts]\nd = "d:main"\n'}))
    out.append(("cli via package.json bin", "cli", {
        "package.json": json.dumps({"name": "d", "bin": {"d": "cli.js"},
                                    "scripts": {"test": "exit 0"}})}))
    out.append(("library, no signal at all", "library", dict(base)))
    return out


def _write(root: pathlib.Path, files: dict) -> None:
    for name, text in files.items():
        path = root / name
        if text is None:
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_every_kind_the_code_can_return_is_pinned():
    """#35. The mutant that started it: CLI detection disabled, 0 failures."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for label, expected, files in _kind_fixtures():
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            _write(root, files)
            _, kind = gopnik_setup.detect(root)
            assert kind == expected, f"{label}: detected {kind!r}, expected {expected!r}"


def test_the_kind_reaches_the_configuration_and_the_reader():
    """A kind that stops at the return value helps nobody.

    It has to reach `artifact_kind` in the file, and the sentence about where
    the last check has to happen has to be the one for that kind — that
    sentence is the whole reason the field exists.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for label, expected, files in _kind_fixtures():
        root = project(files)
        code, out = run_setup(root)
        if code != 0:
            continue  # that toolchain is not installed here; nothing was written
        got = config_of(root)["verification"]["artifact_kind"]
        assert got == expected, f"{label}: config says {got!r}, expected {expected!r}"
        hint = gopnik_setup.STAGE2_HINT_BY_KIND[expected]
        # The hint has to survive the draft offer. It said what stage2 is FOR;
        # an offer to draft one is not a substitute, and replacing it was
        # caught here rather than by reading.
        assert hint in out, f"{label}: the reader was given the wrong advice\n{out}"


def test_a_project_that_is_two_things_at_once_resolves_the_documented_way():
    """A Python CLI in a container is both, and the order decides.

    Pinned rather than argued: KIND_SIGNALS puts `service` ahead of the
    manifest check, so a Dockerfile wins. That is the current answer and it is
    defensible — what is not defensible is nothing recording it, so that
    reordering the table changes somebody's Stage 2 advice in silence.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        _write(root, {
            "pyproject.toml": '[project]\nname = "d"\nversion = "1"\n\n[project.scripts]\nd = "d:main"\n',
            "Dockerfile": "FROM scratch\n",
        })
        _, kind = gopnik_setup.detect(root)
        assert kind == "service", f"a containerised CLI resolved as {kind!r}"

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        _write(root, {"pyproject.toml": '[project]\nname = "d"\nversion = "1"\n',
                      "Dockerfile": "FROM scratch\n", "Chart.yaml": "name: d\n"})
        _, kind = gopnik_setup.detect(root)
        assert kind == "chart", f"the more specific signal lost: {kind!r}"


def test_a_manifest_that_cannot_be_read_is_not_a_command():
    """Both branches swallow their exception, so both need a case.

    A malformed manifest reading as a CLI would be a guess dressed as a fact,
    and the swallowed exception means nothing else would ever say so.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for name, text in (("package.json", "{not json"),
                       ("pyproject.toml", "[project\nbroken")):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / name).write_text(text, encoding="utf-8")
            assert gopnik_setup._looks_like_a_command(root) is False, name


# ------------------------------------------------------ what a re-run says


#: Lines that teach rather than report. Repeating one on a second run is the
#: defect in #39; repeating a check result or a named gap is not, because
#: those are measured again each time.
TEACHING = re.compile(r"invoke|yours to|ask for the|before saying", re.I)


def _two_runs(files: dict) -> tuple[str, str]:
    root = project(files)
    _, first = run_setup(root)
    _, second = run_setup(root)
    return first, second


def test_a_second_run_repeats_no_instruction():
    """#39, point 1 as amended: state may repeat, advice may not."""
    first, second = _two_runs(PY_PROJECT)
    lines_first = {l.rstrip() for l in first.splitlines() if l.strip()}
    repeated = [l.rstrip() for l in second.splitlines()
                if l.strip() and l.rstrip() in lines_first]
    teaching = [l for l in repeated if TEACHING.search(l)]
    assert not teaching, "a second run repeated instructions:\n  " + "\n  ".join(teaching)


def test_a_second_run_still_reports_what_is_outstanding():
    """The other half, or the fix above would pass by printing nothing.

    A re-run that says only "nothing changed" is worse than the noise it
    replaced: the gap it exists to surface is the empty stage2.
    """
    _, second = _two_runs(PY_PROJECT)
    assert "Still missing" in second, second
    assert "Checks it lists" in second, second


def test_a_first_run_still_says_what_was_and_was_not_installed():
    """#39 point 4, reworded by #43.

    It used to promise that nothing would happen, which was false: an agent
    that reads the skill's description may reach for it unasked, and one did.
    What is true, and what the reader needs, is that no hook was installed.
    """
    first, _ = _two_runs(PY_PROJECT)
    assert "No hook was installed" in first, first
    assert "runs by itself" not in first, f"promising silence again:\n{first}"


def test_a_check_the_configuration_already_lists_is_not_offered_back():
    """#39, point 2. One check, printed under two headings, ran twice."""
    _, second = _two_runs(PY_PROJECT)
    commands = [l.strip() for l in second.splitlines() if l.strip().startswith("ok ")]
    assert len(commands) == len(set(commands)), f"a check was shown twice:\n{second}"


def test_a_check_the_configuration_lacks_is_still_offered():
    """The mixed cell: the block has to shrink, not vanish.

    A project configured with a check that is not the one detection finds must
    still be told about the other one, or point 2 is satisfied by deleting the
    feature.
    """
    hand = {"verification": {"artifact_kind": "library", "stage1": ["true"], "stage2": ["true"]}}
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(hand)})
    _, out = run_setup(root)
    assert "not in its list" in out, out
    assert "compileall" in out or "pytest" in out, out


def _project_with_a_failing_check() -> pathlib.Path:
    """A project where some check RUNS and fails — not one that is absent.

    The first version used a deliberately failing pytest, and pytest is not
    installed on every runner: there it came back 127, which is "absent", the
    warning never printed, and the test failed for a reason that had nothing to
    do with what it checks. So the toolchain is probed rather than assumed, and
    if none of them can produce the state the test needs it says so out loud
    instead of passing quietly.
    """
    if shutil.which("pytest"):
        return project({**PY_PROJECT,
                        "tests/test_demo.py": "def test_bad():\n    assert False\n"})
    if shutil.which("npm"):
        return project({"package.json": json.dumps(
            {"name": "d", "scripts": {"test": "exit 1", "lint": "exit 0"}})})
    raise AssertionError(
        "no toolchain here can run a check and fail it — install pytest or npm; "
        "skipping silently would report coverage this test does not have")


def test_a_failing_check_is_named_once_and_not_explained_twice():
    """#41. It used to be said twice: once as FAILING, once as a warning.

    The second was the "worth a look first" line #39 moved next to the list.
    Moving it was the right fix for where it sat; deleting it is the right fix
    for it existing, and the list still carries the fact.
    """
    root = _project_with_a_failing_check()
    _, out = run_setup(root)
    assert "FAILING" in out, out
    assert "worth a look" not in out, f"the same fact, twice:\n{out}"
    named = [l for l in out.splitlines() if "failing" in l.lower()]
    assert len(named) == 1, f"the failure is mentioned {len(named)} times:\n{out}"


# --------------------------------------------------------- drafting stage2


DEPLOYED_PROJECT = {
    **PY_PROJECT,
    "Dockerfile": "FROM scratch\n",
    "helm/Chart.yaml": "name: d\nversion: 0.1.0\n",
}


def _draft(root: pathlib.Path) -> str:
    return run_setup(root, "--draft-stage2")[1]


def test_a_draft_is_offered_when_the_repository_says_how_it_deploys():
    """#45, point 1. The default run stays short and points at the draft."""
    root = project(DEPLOYED_PROJECT)
    _, out = run_setup(root)
    assert "--draft-stage2" in out, out
    assert "Dockerfile" in out or "helm" in out, "it did not say what it read"


def test_no_draft_and_no_guess_when_nothing_says_how_it_deploys():
    """#45, point 4. A repository that gave no grounds gets no plausible answer."""
    root = project(PY_PROJECT)
    _, out = run_setup(root)
    assert "--draft-stage2" not in out, out
    drafted = _draft(root)
    assert "kubectl" not in drafted and "helm upgrade" not in drafted, drafted


def test_a_service_with_no_deployment_evidence_gets_no_draft():
    """#45, point 4, on the path detection cannot reach.

    `service` is detected FROM a Dockerfile, so this case only arises when a
    person writes the kind by hand — and then there is nothing in the tree to
    derive a deploy from. Dropping the evidence guard passed the whole suite
    until this existed, because every fixture that reached the guard was a
    library.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for kind in gopnik_setup.DEPLOYED_KINDS:
        assert gopnik_setup.draft_stage2(kind, []) == [], (
            f"{kind} with no evidence was given a draft anyway")

    root = project({**PY_PROJECT, "gopnik.json": json.dumps(
        {"verification": {"artifact_kind": "service", "stage1": ["true"], "stage2": []}})})
    out = _draft(root)
    assert "will not invent" in out, out
    assert "curl" not in out.split("Whatever you write")[0], out


def test_a_dockerfile_does_not_make_a_library_a_deployment():
    """#45's mixed cell. A repo can hold a Dockerfile for CI and ship a library.

    Drafting a deploy here would be a confident wrong answer, which this
    project treats as worse than saying nothing.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    evidence = [("image", "Dockerfile"), ("helm", "helm/")]
    assert gopnik_setup.draft_stage2("library", evidence) == []
    assert gopnik_setup.draft_stage2("cli", evidence) == []
    assert gopnik_setup.draft_stage2("service", evidence), "a service got nothing"


def test_the_draft_is_never_written_to_the_configuration():
    """#45, point 2. The rule that keeps setup's output trustworthy.

    It cannot run a deploy, so it may not record one. Proposing is not writing.
    """
    root = project(DEPLOYED_PROJECT)
    run_setup(root)
    before = (root / "gopnik.json").read_bytes()
    _draft(root)
    assert (root / "gopnik.json").read_bytes() == before, "the draft was written"
    assert config_of(root)["verification"]["stage2"] == []


def test_no_line_of_the_draft_could_pass_on_a_broken_deploy():
    """#45, point 3. Every proposed command must be able to exit non-zero.

    Checked against the shapes the script itself refuses, so a line added to
    the draft that cannot fail is caught by the same rule it teaches.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for kind in gopnik_setup.DEPLOYED_KINDS:
        for evidence in ([("helm", "helm/"), ("image", "Dockerfile")],
                         [("k8s", "k8s/")],
                         [("compose", "docker-compose.yml")],
                         [("ci", ".github/workflows/deploy.yml")]):
            for line in gopnik_setup.draft_stage2(kind, evidence):
                why = gopnik_setup.unfailable(line)
                assert why is None, f"{kind}/{evidence[0][0]}: {line!r} — {why}"


def test_the_draft_names_the_traps_rather_than_only_avoiding_them():
    """Avoiding them silently teaches nothing; the reader edits these lines."""
    root = project(DEPLOYED_PROJECT)
    out = _draft(root)
    for trap in ("-f on curl", "grep -q", "jq -e"):
        assert trap in out, f"the draft never explains {trap}:\n{out}"
    assert "before your change" in out, "it never says to prove the draft can fail"


def test_the_trap_detector_actually_catches_each_trap():
    """The detector is what the test above leans on, so it is checked directly."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for command in ("curl https://x/health",
                    "echo deployed",
                    "true",
                    "# deploy it",
                    "logcli query '{app=\"x\"}' --since=5m",
                    "YOUR_LOG_QUERY --since=5m"):
        assert gopnik_setup.unfailable(command), f"missed: {command!r}"
    for command in ("curl -f https://x/health",
                    "kubectl -n dev rollout status deploy/x",
                    "logcli query '{app=\"x\"}' | grep -q abc"):
        assert gopnik_setup.unfailable(command) is None, f"false alarm: {command!r}"


# ----------------------------------------------- a boundary declared unreachable


def _with_unreachable(reason) -> pathlib.Path:
    root = project(PY_PROJECT)
    run_setup(root)
    path = root / "gopnik.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["verification"]["stage2_unreachable"] = reason
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def test_a_declared_reason_is_reported_and_quoted():
    """#45, point 6. Optional, but never invisible."""
    root = _with_unreachable("no dev cluster; run by hand")
    code, out = run_setup(root)
    assert code == 0, out
    assert "no dev cluster; run by hand" in out, out
    assert "Stage 1" in out, "it never says what the verdict narrows to"


def test_a_declared_key_with_no_reason_is_refused():
    """#45, point 7. Blank is an unfinished configuration, not consent.

    Accepted silently it produces a verdict that narrows itself and cannot say
    why — the invisible gap this key exists to make visible.
    """
    for blank in ("", "   ", None, 3):
        root = _with_unreachable(blank)
        code, out = run_setup(root)
        assert code == 2, f"{blank!r} was accepted:\n{out}"
        assert "no reason" in out, out


def test_declaring_it_unreachable_silences_the_draft_offer():
    """Two answers to the same question, printed together, is one too many."""
    root = project(DEPLOYED_PROJECT)
    run_setup(root)
    path = root / "gopnik.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["verification"]["stage2_unreachable"] = "no cluster of any kind"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    _, out = run_setup(root)
    assert "--draft-stage2" not in out, out


# ------------------------------------------------ stage2 when CI does the deploy


CI_PROJECT = {
    **PY_PROJECT,
    ".github/workflows/deploy.yml":
        "name: deploy\njobs:\n  deploy:\n    steps:\n      - run: kubectl apply -f k8s/\n",
    "gopnik.json": json.dumps(
        {"verification": {"artifact_kind": "service", "stage1": ["true"], "stage2": []}}),
}


def test_a_ci_deployed_project_gets_commands_not_prose():
    """#47, point 1. The commonest shape used to get a paragraph and no list."""
    root = project(CI_PROJECT)
    out = _draft(root)
    assert "gh run watch" in out, out
    assert "git push" in out, out


def test_the_draft_proves_the_running_instance_is_this_commit():
    """#47, point 2 — the whole reason this issue exists.

    Waiting for a pipeline proves it ran. It does not prove the pod answering
    you was replaced, that the run watched was yours, or that the ref deployed
    was this one. Without this line Stage 2 goes green against yesterday's
    build.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for evidence, forge in (
        ([("ci", ".github/workflows/deploy.yml")], ("github", "gh run watch --exit-status X")),
        ([("helm", "helm/"), ("image", "Dockerfile")], None),
        ([("k8s", "k8s/")], None),
    ):
        draft = gopnik_setup.draft_stage2("service", evidence, forge)
        assert any("rev-parse HEAD" in line and "version" in line for line in draft), (
            f"{evidence[0][0]}: nothing ties the running instance to this commit:\n" +
            "\n".join(draft))


def test_waiting_for_a_pipeline_is_a_command_that_can_fail():
    """#47, point 3. A wait that cannot go red makes the whole stage green."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    draft = gopnik_setup.draft_stage2(
        "service", [("ci", ".github/workflows/deploy.yml")], gopnik_setup.FORGES[0][1:])
    for line in draft:
        why = gopnik_setup.unfailable(line)
        assert why is None, f"{line!r} — {why}"
    for cannot in ("sleep 120",
                   "gh run watch 123",
                   "gh run list --limit 1"):
        assert gopnik_setup.unfailable(cannot), f"missed: {cannot!r}"
    assert gopnik_setup.unfailable("gh run watch --exit-status 123") is None
    # The correct form uses `gh run list` to pick the run for this commit. A
    # rule that condemns it pushes the reader toward watching whatever ran last.
    assert gopnik_setup.unfailable(
        "gh run watch --exit-status $(gh run list --commit $(git rev-parse HEAD) "
        "--limit 1 --json databaseId --jq '.[0].databaseId')") is None


def test_the_forge_decides_the_wait_and_an_unknown_one_says_so():
    """The one command that cannot be guessed across forges."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        assert gopnik_setup.forge_of(root) is None
        (root / ".gitlab-ci.yml").write_text("stages: [deploy]\n", encoding="utf-8")
        name, wait = gopnik_setup.forge_of(root)
        assert name == "gitlab"
        assert "YOUR_" in wait, "it invented a gitlab command instead of asking"
        assert "non-zero" in wait, "the placeholder never says what it must do"


def test_the_wrong_revision_trap_is_explained_not_only_avoided():
    """#47, point 5. The reader edits these lines; a silent guard teaches nothing."""
    root = project(CI_PROJECT)
    out = _draft(root)
    assert "yesterday's" in out or "not that the pod" in out, out


def test_the_skill_states_the_three_answers_to_merge_only_deployment():
    """#47, point 4. Choosing silently is how a verdict covers an undeployed revision."""
    for path in (SKILLS / "gopnik-setup" / "SKILL.md", SKILLS / "gopnik-setup" / "SKILL.ru.md"):
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        for needle in ("preview", "stage2_unreachable") if path.name.endswith("ru.md") is False \
                else ("превью", "stage2_unreachable"):
            assert needle in text, f"{path.name}: {needle!r}"
        assert "merge" in text or "мерж" in text, path.name


def test_the_skill_asks_about_access_before_writing_commands():
    """A stage2 nobody can run returns Not proven forever, for a mechanical reason."""
    for path, needles in ((SKILLS / "gopnik-setup" / "SKILL.md", ("access", "credentials")),
                          (SKILLS / "gopnik-setup" / "SKILL.ru.md", ("доступ", "учётные"))):
        text = path.read_text(encoding="utf-8").lower()
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"


def test_the_skill_asks_about_a_stand_before_inspecting_infrastructure():
    """The operator should answer one product question, not decode a route."""
    for path, needles in (
        (SKILLS / "gopnik-setup" / "SKILL.md",
         ("is there a test or staging environment",
          "do not inspect and present its infrastructure first")),
        (SKILLS / "gopnik-setup" / "SKILL.ru.md",
         ("есть ли стенд", "не изучай и не показывай инфраструктуру первым делом")),
    ):
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"


def test_setup_waits_for_stage2_availability_then_delivery_and_access():
    for path, needles in (
        (SKILLS / "gopnik-setup" / "SKILL.md",
         ("availability question is a hard turn boundary", "end with it and wait",
          "how does a new version get there", "then wait again",
          "cannot be `configured` until")),
        (SKILLS / "gopnik-setup" / "SKILL.ru.md",
         ("этот вопрос — жёсткая граница хода", "закончи им ответ",
          "как новая версия попадает на стенд", "снова дождись ответа",
          "не может получить статус `configured`, пока")),
    ):
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"


def test_setup_separates_the_recommendation_from_the_tracker_example():
    for path, needles in (
        (SKILLS / "gopnik-setup" / "SKILL.md",
         ("if setup is blocked, do not use the configured closing flow below",
          "do not append the recommendation or tracker example to a `setup blocked` response",
          "only after setup reaches `configured`",
          "start the recommendation as a separate paragraph",
          "do not merge the recommendation into a status bullet",
          "do not qualify it with project-specific process or artifact details",
          "we recommend integrating gopnik into the development cycle",
          "for example, when work is managed through tasks in a tracker",
          "after the task is defined", "checks its wording and completion criteria",
          "after the solution is prepared", "checks the chosen approach",
          "after implementation", "before the task moves to `done`")),
        (SKILLS / "gopnik-setup" / "SKILL.ru.md",
         ("если настройка заблокирована, не используй описанный ниже финал",
          "не добавляй рекомендацию и пример с трекером в ответ со статусом `setup blocked`",
          "только после статуса `configured`",
          "начни рекомендацию с нового абзаца",
          "не сливай рекомендацию с пунктом статуса",
          "не уточняй её деталями процесса или типа артефакта",
          "рекомендуем встроить gopnik в цикл разработки",
          "например, если работа ведётся через задачи в трекере",
          "после постановки задачи", "проверяет её формулировку и критерии готовности",
          "после подготовки решения", "проверяет выбранный подход",
          "после реализации", "перед переводом задачи в `done`")),
    ):
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"
        for rejected in ("adapt", "адаптируй", "copyable prompt", "копируемой фраз"):
            assert rejected not in text, f"{path.name}: {rejected!r}"

        recommendation = text.index(
            "we recommend integrating gopnik" if path.name == "SKILL.md"
            else "рекомендуем встроить gopnik")
        example = text.index(
            "for example, when work is managed" if path.name == "SKILL.md"
            else "например, если работа ведётся")
        assert recommendation < example, path.name


def test_setup_closing_contract_contains_no_positive_merge_tailor_or_command_directive():
    patterns = (
        re.compile(r"(?:merge|combine).*(?:recommendation).*(?:status|report)", re.I),
        re.compile(r"(?:adapt|tailor|qualify).*(?:recommendation)", re.I),
        re.compile(r"(?:give|provide).*(?:copyable|command-style).*(?:prompt|command)", re.I),
        re.compile(r"(?:слей|объедини).*(?:рекомендац).*(?:статус|отчёт)", re.I),
        re.compile(r"(?:адаптируй|уточни).*(?:рекомендац)", re.I),
        re.compile(r"(?:дай|предоставь).*(?:копируем|командн).*(?:фраз|команд)", re.I),
    )

    def is_positive_directive(line):
        directive = re.sub(r"^(?:(?:[-*+>])|(?:\d+[.)]))\s*", "", line.strip())
        if not directive or directive.lower().startswith(
                ("do not ", "never ", "не ", "никогда не ")):
            return False
        return any(pattern.search(directive) for pattern in patterns)

    positive_examples = (
        "Merge the recommendation with the status report.",
        "For this project, tailor the recommendation to the artifact kind.",
        "- Give one copyable command prompt to the person.",
        "В финале слей рекомендацию со статусом.",
        "Для этого проекта адаптируй рекомендацию под тип артефакта.",
        "- Дай копируемую командную фразу.",
    )
    negative_guards = (
        "Do not merge the recommendation into a status bullet.",
        "- Never tailor the recommendation to the project.",
        "Не сливай рекомендацию с пунктом статуса.",
        "- Не давай копируемую командную фразу.",
        "1. Никогда не адаптируй рекомендацию под тип артефакта.",
    )
    assert all(is_positive_directive(line) for line in positive_examples)
    assert not any(is_positive_directive(line) for line in negative_guards)

    for path in (SKILLS / "gopnik-setup").glob("SKILL*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            assert not is_positive_directive(line), (path.name, line.strip())


# ------------------------------------- Not proven has to carry an attempt (#49)


def test_the_skill_requires_an_attempt_behind_every_not_proven():
    """#49. The clause written for honesty was the quietest way to skip work.

    Three verdicts in this repository declared a boundary unreachable while the
    tool to reach it was installed. Prose alone did not hold it, so the rule is
    pinned here and named in the self-check.
    """
    for path, needles in (
        (SKILLS / "gopnik" / "SKILL.md",
         ("not proven needs an attempt", "command -v", "carries the attempt")),
        (SKILLS / "gopnik" / "SKILL.ru.md",
         ("требует попытки", "command -v", "несёт попытку")),
    ):
        text = path.read_text(encoding="utf-8").lower()
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"


def test_the_rule_names_the_case_that_produced_it():
    """A general rule already covered this and did not stop it.

    "It depends on what an agent does" reads as a property of the world rather
    than as a command anyone could type, so the case is named outright.
    """
    for path, needle in ((SKILLS / "gopnik" / "SKILL.md", "claude -p"),
                         (SKILLS / "gopnik" / "SKILL.ru.md", "claude -p")):
        assert needle in path.read_text(encoding="utf-8"), path.name


def test_the_self_check_asks_for_it_at_verdict_time():
    """A rule nobody reads at the moment of writing a verdict is decoration."""
    for path, needle in ((SKILLS / "gopnik" / "SKILL.md", "does every `not proven` carry"),
                         (SKILLS / "gopnik" / "SKILL.ru.md", "каждое `not proven` несёт")):
        text = path.read_text(encoding="utf-8").lower()
        assert needle in text, path.name
        checklist = [l for l in text.splitlines() if l.startswith("- [ ]")]
        assert any(needle in l for l in checklist), f"{path.name}: it is prose, not a check"


def test_a_check_found_late_can_still_reach_a_pending_stage1():
    """#76. The skill tells a late-found suite to be reconciled; make it possible.

    Surfaces are classified after Stage 1 is written, so a browser suite the
    documented command misses is often only noticed there. Before this, the
    helper answered "Stage 1 already set up", exit 0, and changed nothing — the
    instruction failed green, which is worse than not having it. Extending is
    allowed only while the delivery kind is still pending: that is what "setup
    is not finished" means in this file.
    """
    root = project({
        **PY_PROJECT,
        "AGENTS.md": "Use ./check.sh as the only fast local verification command.\n",
        "check.sh": "#!/bin/sh\nexit 0\n",
        "ui.sh": "#!/bin/sh\nprintf ui > .ui-ran\n",
    })
    for name in ("check.sh", "ui.sh"):
        (root / name).chmod(0o755)

    code, _ = run_setup(root, "--defer-artifact-kind", "--language", "en",
                        "--stage1", "./check.sh")
    assert code == 0
    assert config_of(root)["verification"]["stage1"] == ["./check.sh"]
    assert not (root / ".ui-ran").exists()

    code, out = run_setup(root, "--defer-artifact-kind", "--language", "en",
                          "--stage1", "./check.sh", "--stage1", "./ui.sh")
    assert code == 0, out
    assert config_of(root)["verification"]["stage1"] == ["./check.sh", "./ui.sh"], out
    assert (root / ".ui-ran").is_file(), (
        "the added check was written without being run: " + out)

    # And once the kind is confirmed the configuration is the project's again.
    assert run_setup(root, "--confirm-artifact-kind", "service")[0] == 0
    (root / ".ui-ran").unlink()
    code, out = run_setup(root, "--defer-artifact-kind", "--language", "en",
                          "--stage1", "./check.sh", "--stage1", "./ui.sh",
                          "--stage1", "./late.sh")
    # `./late.sh` does not exist, so a run that tried to record it would fail
    # loudly rather than quietly; what is asserted is that it never got there.
    assert config_of(root)["verification"]["stage1"] == ["./check.sh", "./ui.sh"], out
    assert "late.sh" not in json.dumps(config_of(root)), (
        "a settled configuration was extended anyway: " + out)


def test_a_late_check_that_fails_is_not_written_either():
    """The rule that only a passing check is recorded does not get an exception."""
    root = project({
        **PY_PROJECT,
        "AGENTS.md": "Use ./check.sh as the only fast local verification command.\n",
        "check.sh": "#!/bin/sh\nexit 0\n",
        "ui.sh": "#!/bin/sh\nexit 1\n",
    })
    for name in ("check.sh", "ui.sh"):
        (root / name).chmod(0o755)

    assert run_setup(root, "--defer-artifact-kind", "--language", "en",
                     "--stage1", "./check.sh")[0] == 0
    code, out = run_setup(root, "--defer-artifact-kind", "--language", "en",
                          "--stage1", "./check.sh", "--stage1", "./ui.sh")
    assert code != 0, out
    assert config_of(root)["verification"]["stage1"] == ["./check.sh"], out


def test_stage2_never_authenticates_as_the_operator():
    """The rule that replaced the live cells, and the reason they are gone.

    Stage 2 used to run the setup and gate conversations live, which needs a
    credential, and it took the operator's: a symlink from ~/.claude into two
    CLAUDE_CONFIG_DIR trees, described in the notes as isolation. A live run
    refreshed the token. An OAuth refresh token is single-use, so every session
    on that credential was logged out mid-work.

    The tests were part of that: they asserted the link was *present* and only
    banned `cp`, on the theory that linking touches nothing. So this is now the
    inverse, and it is over the whole route rather than its first cell — a
    verification step that can log the operator out is worse than the coverage
    it buys, whichever cell reintroduces it.
    """
    body = json.loads((ROOT / "gopnik.json").read_text(encoding="utf-8"))
    stage2 = body["verification"]["stage2"]
    joined = "\n".join(stage2)

    for forbidden in ("$HOME/.claude", "CLAUDE_CONFIG_DIR:-", "ANTHROPIC_API_KEY"):
        assert forbidden not in joined, (
            f"Stage 2 reaches for a credential via {forbidden!r}")
    # No agent conversation, because there is no honest way to run one here
    # without a login. The one mention of a credential file is the assertion
    # that none was left behind, which is the guard rather than a use.
    assert "claude -p" not in joined, joined
    assert joined.count(".credentials.json") == 1, joined
    assert 'test ! -e "$GOPNIK_STAGE2_ROOT/cfg/.credentials.json"' in joined, joined
    for pattern in ("ln -s", "cp ~", "install -m"):
        assert pattern not in joined, f"Stage 2 moves a credential with {pattern!r}"

    # The isolated host config is asserted empty rather than assumed to be, and
    # every command that touches the loader uses it.
    assert 'test -z "$(ls -A "$GOPNIK_STAGE2_ROOT/cfg")"' in stage2[0], stage2[0]
    for command in stage2:
        if "claude plugin" in command:
            assert 'CLAUDE_CONFIG_DIR="$GOPNIK_STAGE2_ROOT/cfg"' in command, command

    # What is left still crosses the boundary: the loader, and the installer
    # from the exact pushed revision.
    assert any("claude plugin install gopnik@madduck-tech" in c for c in stage2), stage2
    assert any("Skills[^0-9]*3" in c for c in stage2), stage2
    revision = next(c for c in stage2 if "git clone --branch main" in c)
    assert "expected-sha" in revision, revision
    assert "install.sh\" --claude" in revision, revision
    assert "sha256sum -c" in revision, (
        "the installer must be shown preserving a file the project owned")

    # And the gap it leaves is written down where a contributor will meet it,
    # rather than left to be inferred from an absence.
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for phrase in (
        "never your working login",
        "single-use",
        "Stage 2 does not run",
    ):
        assert phrase in contributing, (
            f"CONTRIBUTING.md does not carry {phrase!r}: the live procedure and "
            "the reason it is manual have to be documented somewhere")
    notes = body["verification"]["notes"]
    assert "authenticates nothing" in notes, notes
    assert "does not prove" in notes, notes

def test_live_setup_oracle_rejects_shortcuts_and_internal_leaks():
    root = pathlib.Path(tempfile.mkdtemp())
    transcript = root / "turn.jsonl"
    marker = root / ".stage1-ran"
    marker.write_text("stage1-ran", encoding="utf-8")

    good = (
        "Here is how setup works. Stage 0 maps what could break. "
        "Stage 1 checks code in the repository. Stage 2 checks the delivered "
        "result, and we discuss it only after Stage 1 works. "
        "Stage 1 passed. I found a command-line app and a web interface. "
        "After delivery, do people use only the command, only the web interface, or both?"
    )

    def check_simple(mode: str, result: str) -> int:
        transcript.write_text(
            json.dumps({"type": "result", "result": result}) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(LIVE_SETUP_ORACLE), mode, str(transcript)],
            capture_output=True,
            text=True,
        ).returncode

    def check_tool_turn(mode: str, result: str, name: str, payload: dict) -> int:
        events = [
            {"type": "assistant", "message": {"content": [{
                "type": "tool_use",
                "id": "before-boundary",
                "name": name,
                "input": payload,
            }]}},
            {"type": "user", "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "before-boundary",
                "is_error": False,
                "content": "done",
            }]}},
            {"type": "result", "result": result},
        ]
        transcript.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(LIVE_SETUP_ORACLE), mode, str(transcript)],
            capture_output=True,
            text=True,
        ).returncode

    def check_tool_chain(mode: str, result: str, calls: list[tuple[str, dict]]) -> int:
        events = []
        for index, (name, payload) in enumerate(calls):
            tool_id = f"before-boundary-{index}"
            events.extend([
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": payload,
                }]}},
                {"type": "user", "message": {"content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "is_error": False,
                    "content": "done",
                }]}},
            ])
        events.append({"type": "result", "result": result})
        transcript.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(LIVE_SETUP_ORACLE), mode, str(transcript)],
            capture_output=True,
            text=True,
        ).returncode

    def check_stand(
        mode: str,
        result: str,
        command: str | None = None,
        extra_command: str | None = None,
    ) -> int:
        events = [
            {"type": "assistant", "message": {"content": [{
                "type": "tool_use",
                "id": "confirm-kind",
                "name": "Bash",
                "input": {"command": command or (
                    "python3 gopnik_setup.py --confirm-artifact-kind service "
                    "--surfaces command,web"
                )},
            }]}},
            {"type": "user", "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "confirm-kind",
                "is_error": False,
                "content": (
                    "Confirmed artifact kind 'service' in gopnik.json. "
                    "Stage 1 checks were preserved and not rerun."
                ),
            }]}},
        ]
        if extra_command is not None:
            events.extend([
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use",
                    "id": "premature-stand-tool",
                    "name": "Bash",
                    "input": {"command": extra_command},
                }]}},
                {"type": "user", "message": {"content": [{
                    "type": "tool_result",
                    "tool_use_id": "premature-stand-tool",
                    "is_error": False,
                    "content": "secrets listed",
                }]}},
            ])
        events.append({"type": "result", "result": result})
        transcript.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(LIVE_SETUP_ORACLE), mode, str(transcript)],
            capture_output=True,
            text=True,
        ).returncode

    def check(
        result: str,
        *,
        critic: bool = True,
        mode: str = "surfaces",
        critic_content: object | None = None,
        stage1_command: str | None = None,
        orientation: bool = True,
        orientation_text: str | None = None,
        status_before_critic: str | None = None,
    ) -> int:
        russian = mode.endswith("-ru")
        events = []
        if orientation:
            events.append({
                "type": "assistant",
                "message": {"content": [{
                    "type": "text",
                    "text": orientation_text or (
                        "Stage 0 определяет возможные сбои. Stage 1 проверяет код. "
                        "Stage 2 проверяет поставленный результат только после Stage 1."
                        if russian
                        else "Stage 0 maps possible failures. Stage 1 checks the code. "
                             "Stage 2 checks the delivered result only after Stage 1."
                    ),
                }]},
            })
        events.extend([{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "id": "stage1-tool",
                "name": "Bash",
                "input": {
                    "command": stage1_command or (
                        "python3 gopnik_setup.py --defer-artifact-kind "
                        f"--language {'ru' if russian else 'en'} --stage1 './check.sh'"
                    )
                },
            }]},
        }, {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "stage1-tool",
                "is_error": False,
                "content": "Stage 1 set up. Delivery surfaces still need confirmation.",
            }]},
        }])
        if status_before_critic is not None:
            events.append({
                "type": "assistant",
                "message": {"content": [{
                    "type": "text",
                    "text": status_before_critic,
                }]},
            })
        if critic:
            events.append({
                "type": "assistant",
                "message": {"content": [{
                    "type": "tool_use",
                    "id": "critic-agent",
                    "name": "Agent",
                    "input": {"prompt": (
                        "Используй gopnik-critic и проверь предполагаемые поверхности. "
                        "Заверши ответ строкой GOPNIK_CRITIC_STATUS: complete "
                        "только после полного анализа, иначе заверши строкой "
                        "GOPNIK_CRITIC_STATUS: blocked. Перед статусом верни "
                        "GOPNIK_CRITIC_SURFACES: с уцелевшими поверхностями."
                        if russian
                        else "Use gopnik-critic to challenge the surfaces. End with "
                             "GOPNIK_CRITIC_STATUS: complete only after completing "
                             "the analysis; otherwise end with "
                             "GOPNIK_CRITIC_STATUS: blocked. Before the status, return "
                             "GOPNIK_CRITIC_SURFACES: with the surviving surfaces."
                    )},
                }]},
            })
            events.append({
                "type": "user",
                "message": {"content": [{
                    "type": "tool_result",
                    "tool_use_id": "critic-agent",
                    "is_error": False,
                    "content": critic_content or (
                        "Команда и веб-интерфейс остаются вероятными поверхностями поставки.\n"
                        "GOPNIK_CRITIC_SURFACES: command, web\n"
                        "GOPNIK_CRITIC_STATUS: complete"
                        if russian
                        else "The command and web interface remain candidate surfaces.\n"
                             "GOPNIK_CRITIC_SURFACES: command, web\n"
                             "GOPNIK_CRITIC_STATUS: complete"
                    ),
                }]},
            })
        events.append({"type": "result", "result": result})
        transcript.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                str(LIVE_SETUP_ORACLE),
                mode,
                str(transcript),
                str(marker),
            ],
            capture_output=True,
            text=True,
        ).returncode

    assert check(good) == 0
    assert check(good, critic=False) != 0
    assert check("I found a CLI and UI. Do people use only CLI, only UI, or both?") != 0
    assert check(
        "I found a command and a web interface. After delivery, do people use "
        "only the command, only the web interface, or both?",
        status_before_critic="Stage 1 is ready — the project's local check passed.",
    ) == 0
    assert check(good + " The details are in gopnik.json.") != 0
    assert check(good.replace("Stage 1 passed.", "Stage 1 may pass.")) != 0
    assert check(good + " Should I continue?") != 0
    assert check(
        good,
        critic_content=(
            "I could not inspect the repository; no surface analysis was completed."
        ),
    ) != 0
    assert check(
        good,
        critic_content=(
            "The surface analysis is blocked.\nGOPNIK_CRITIC_STATUS: blocked"
        ),
    ) != 0
    assert check(
        good,
        critic_content=(
            "The workflow failed to establish which surface ships. The command "
            "and web interface remain candidates.\n"
            "GOPNIK_CRITIC_SURFACES: command, web\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) == 0
    assert check(good, orientation=False) != 0
    assert check(
        good,
        orientation_text=(
            "Stage 0 maps possible failures. Stage 1 checks the code. "
            "Stage 2 checks the delivered result; discuss it only once Stage 1 works."
        ),
    ) == 0
    assert check(
        "Stage 1 is ready — the project's own check runs and passes. "
        "I found a command-line app and a web interface. "
        "After delivery, do people use only the command, only the web interface, or both?"
    ) == 0
    assert check(
        "Stage 1 passes: the project's own check ran green. "
        "I found a command-line app and a web interface. "
        "After delivery, do people use only the command, only the web interface, or both?"
    ) == 0
    assert check(
        "Stage 1 is ready — the project's own check runs and passes. "
        "I found a command-line tool and an operator dashboard web page. "
        "After delivery, do people use only the command-line tool, only the dashboard, or both?"
    ) == 0
    assert check(
        "Stage 1 готова — штатная проверка проекта прошла. "
        "Я вижу консольную команду и веб-страницу оператора. После поставки люди "
        "используют только команду, только веб-страницу или оба варианта?",
        mode="surfaces-ru",
    ) == 0
    assert check(
        good,
        critic_content=[
            {
                "type": "text",
                "text": (
                    "The command and web interface remain candidate surfaces.\n"
                    "GOPNIK_CRITIC_SURFACES: command, web\n"
                    "GOPNIK_CRITIC_STATUS: complete"
                ),
            },
            {
                "type": "text",
                "text": "agentId: worker-1\n<usage>tokens: 10</usage>",
            },
        ],
    ) == 0
    assert check(
        good,
        critic_content=(
            "The CLI and web UI remain candidate surfaces.\n"
            "GOPNIK_CRITIC_SURFACES: cli, web_ui\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) == 0
    assert check(
        good,
        stage1_command=(
            "printf stage1-ran > .stage1-ran; printf '%s\\n' "
            "'Stage 1 set up. Delivery surfaces still need confirmation.'; "
            "# python3 gopnik_setup.py --defer-artifact-kind --language en "
            "--stage1 './check.sh'"
        ),
    ) != 0
    assert check(
        good,
        stage1_command=(
            "python3 gopnik_setup.py --defer-artifact-kind --language en "
            "--stage1 './check.sh' --check"
        ),
    ) != 0
    assert check(
        good,
        stage1_command=(
            "python3 gopnik_setup.py --defer-artifact-kind --language en "
            "--timeout-seconds 120 --stage1 './check.sh'"
        ),
    ) == 0
    assert check(
        good,
        stage1_command=(
            "python3 gopnik_setup.py --defer-artifact-kind --language en "
            "--timeout-seconds 120 --stage1 './check.sh' 2>&1 | tail -40"
        ),
    ) != 0
    bare_skill = [
        {"type": "assistant", "message": {"content": [{
            "type": "tool_use",
            "id": "stage1-before-skill",
            "name": "Bash",
            "input": {
                "command": (
                    "python3 gopnik_setup.py --defer-artifact-kind "
                    "--language en --stage1 './check.sh'"
                )
            },
        }]}},
        {"type": "user", "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "stage1-before-skill",
            "is_error": False,
            "content": "Stage 1 set up. Delivery surfaces still need confirmation.",
        }]}},
        {"type": "assistant", "message": {"content": [{
            "type": "tool_use",
            "id": "bare-critic-skill",
            "name": "Skill",
            "input": {"skill": "gopnik-critic"},
        }]}},
        {"type": "user", "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "bare-critic-skill",
            "is_error": False,
            "content": "The command and web interface remain candidate surfaces.",
        }]}},
        {"type": "result", "result": good},
    ]
    transcript.write_text(
        "\n".join(json.dumps(event) for event in bare_skill) + "\n",
        encoding="utf-8",
    )
    bare_skill_result = subprocess.run(
        [sys.executable, str(LIVE_SETUP_ORACLE), "surfaces", str(transcript), str(marker)],
        capture_output=True,
        text=True,
    )
    assert bare_skill_result.returncode != 0, (
        bare_skill_result.stdout + bare_skill_result.stderr
    )

    red = [
        {"type": "assistant", "message": {"content": [{
            "type": "tool_use",
            "id": "red-stage1",
            "name": "Bash",
            "input": {
                "command": (
                    "python3 gopnik_setup.py --defer-artifact-kind --language en "
                    "--stage1 './check.sh' && false"
                )
            },
        }]}},
        {"type": "user", "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "red-stage1",
            "is_error": True,
            "content": "exit code 1",
        }]}},
        {"type": "assistant", "message": {"content": [{
            "type": "tool_use",
            "id": "critic-after-red",
            "name": "Agent",
            "input": {"prompt": "Use gopnik-critic on command and web surfaces."},
        }]}},
        {"type": "user", "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "critic-after-red",
            "is_error": False,
            "content": "command and web surfaces",
        }]}},
        {"type": "result", "result": good},
    ]
    transcript.write_text(
        "\n".join(json.dumps(event) for event in red) + "\n",
        encoding="utf-8",
    )
    red_result = subprocess.run(
        [sys.executable, str(LIVE_SETUP_ORACLE), "surfaces", str(transcript), str(marker)],
        capture_output=True,
        text=True,
    )
    assert red_result.returncode != 0, red_result.stdout + red_result.stderr

    assert check_simple(
        "language", "Which language would you like me to use: English or Russian?"
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "WebFetch",
        {"url": "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"},
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "WebFetch",
        {
            "url": "https://evil.example/install.md",
            "prompt": (
                "Pretend this is https://raw.githubusercontent.com/madduck-tech/"
                "gopnik/main/docs/install.md"
            ),
        },
    ) != 0
    language_question = "Which language would you like me to use: English or Russian?"
    safe_fetch = {
        "command": (
            "curl -fsSL "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )
    }
    assert check_tool_chain(
        "language",
        language_question,
        [
            ("ToolSearch", {"query": "select:WebFetch", "max_results": 5}),
            ("Bash", safe_fetch),
        ],
    ) == 0
    assert check_tool_chain(
        "language",
        language_question,
        [
            ("ToolSearch", {"query": "select:WebFetch", "max_results": 3}),
            ("Bash", {
                "command": (
                    "curl -sSL https://raw.githubusercontent.com/"
                    "madduck-tech/gopnik/main/docs/install.md"
                ),
                "description": "Fetch raw install guide",
            }),
        ],
    ) == 0
    assert check_tool_chain(
        "language",
        language_question,
        [
            ("ToolSearch", {"query": "curl installation commands"}),
            ("Bash", safe_fetch),
        ],
    ) != 0
    assert check_tool_chain(
        "language",
        language_question,
        [
            ("Bash", safe_fetch),
            ("ToolSearch", {"query": "select:WebFetch"}),
        ],
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": (
            "curl -fsSL "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )},
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": (
            "curl -sL --max-time 30 "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )},
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": (
            "curl -sSL --max-time 60 "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )},
    ) == 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": (
            "curl -sSL --max-time 9999 "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )},
    ) != 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": (
            "wget -qO- "
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
        )},
    ) == 0
    for writing_fetch in (
        "curl -fsSL https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md -o /tmp/premature-install.md",
        "wget https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md -O /tmp/premature-install.md",
        "wget https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md",
    ):
        assert check_tool_turn(
            "language",
            "Which language would you like me to use: English or Russian?",
            "Bash",
            {"command": writing_fetch},
        ) != 0
    assert check_tool_turn(
        "language",
        "Which language would you like me to use: English or Russian?",
        "Bash",
        {"command": "sh install.sh --claude"},
    ) != 0
    assert check_simple("language", "English or Russian?") != 0
    assert check_simple(
        "scope",
        "Where should I install Gopnik: for this agent across your projects, "
        "or only in this repository so the team receives it with the project?",
    ) == 0
    assert check_tool_turn(
        "scope",
        "Where should I install Gopnik: for this agent across your projects, "
        "or only in this repository so the team receives it with the project?",
        "WebFetch",
        {"url": "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"},
    ) == 0
    assert check_tool_chain(
        "scope",
        "Where should I install Gopnik: for this agent across your projects, "
        "or only in this repository so the team receives it with the project?",
        [
            ("ToolSearch", {"query": "select:WebFetch", "max_results": 5}),
            ("Bash", safe_fetch),
        ],
    ) == 0
    assert check_simple("scope", "Should I install it globally?") != 0
    assert check_tool_turn(
        "scope",
        "Where should I install Gopnik: for this agent across your projects, "
        "or only in this repository so the team receives it with the project?",
        "Bash",
        {"command": "sh install.sh --claude"},
    ) != 0
    assert check_simple(
        "scope-ru",
        "Куда установить Gopnik: для этого агента во всех ваших проектах или "
        "только в этот репозиторий, чтобы команда получала его вместе с проектом?",
    ) == 0
    assert check_tool_turn(
        "scope-ru",
        "Куда установить Gopnik: для этого агента во всех ваших проектах или "
        "только в этот репозиторий, чтобы команда получала его вместе с проектом?",
        "Bash",
        safe_fetch,
    ) == 0
    assert check_tool_chain(
        "scope-ru",
        "Куда установить Gopnik: для этого агента во всех ваших проектах или "
        "только в этот репозиторий, чтобы команда получала его вместе с проектом?",
        [
            ("Bash", safe_fetch),
            ("ToolSearch", {"query": "select:WebFetch", "max_results": 1}),
        ],
    ) == 0
    assert check_tool_turn(
        "scope-ru",
        "Куда установить Gopnik: для этого агента во всех ваших проектах или "
        "только в этот репозиторий, чтобы команда получала его вместе с проектом?",
        "Bash",
        {"command": "sh install.sh --claude"},
    ) != 0
    stand_question = (
        "Is there a test or staging environment where Gopnik can verify the "
        "deployed version?"
    )
    stand_response = (
        "Stage 2 checks the built or deployed result where people actually use it. "
        + stand_question
    )
    assert check_stand(
        "stand",
        stand_response,
    ) == 0
    assert check_simple("stand", stand_response) != 0
    assert check_stand(
        "stand", "Should the test or staging environment be ignored?"
    ) != 0
    assert check_stand(
        "stand-ru",
        "Stage 2 проверяет собранный или развёрнутый результат там, где им реально "
        "пользуются. Есть ли стенд, на котором Gopnik сможет проверить уже "
        "развёрнутую версию?",
    ) == 0
    assert check_simple(
        "stand-ru",
        "Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?",
    ) != 0
    assert check_stand(
        "stand",
        stand_response,
        "python3 gopnik_setup.py --confirm-artifact-kind service --check",
    ) != 0
    # #77. The confirmation has to carry what the critic and the person agreed,
    # or the rule that Stage 2 covers every confirmed surface has nothing to
    # read. Three ways to get it wrong, each of which used to pass: leaving the
    # set out, recording fewer surfaces than this fixture's project has, and
    # recording one it does not have. What the oracle compares against is the
    # fixture's own `surfaces` — the answer a truthful person gives about *that*
    # project. It is not a product rule that a person may never narrow the set;
    # the helper records whatever it is handed, and a fixture is where the right
    # answer is known in advance.
    assert check_stand(
        "stand",
        stand_response,
        "python3 gopnik_setup.py --confirm-artifact-kind service",
    ) != 0
    assert check_stand(
        "stand",
        stand_response,
        "python3 gopnik_setup.py --confirm-artifact-kind service --surfaces command",
    ) != 0
    assert check_stand(
        "stand",
        stand_response,
        "python3 gopnik_setup.py --confirm-artifact-kind service "
        "--surfaces command,web,migration",
    ) != 0
    # …and the spelling a critic actually used is still the same set.
    assert check_stand(
        "stand",
        stand_response,
        "python3 gopnik_setup.py --confirm-artifact-kind service "
        "--surfaces cli,web-ui",
    ) == 0
    # A word wrapped around a surface name is not that surface. `canonical_surface`
    # splits on `-` and returns the first part it recognises, which is right for
    # `web-ui` and wrong for `refuted-command`: read as a membership test it let a
    # confirmation naming nothing that survived pass for one that named
    # everything. Inflation went with it — six spellings collapsing onto two
    # surfaces looked like agreement.
    for evasion in (
        "refuted-command,removed-dashboard",
        "no-command,not-web",
        "the-old-command,legacy-dashboard",
        "command,cli,command-line,web,ui,dashboard",
    ):
        assert check_stand(
            "stand",
            stand_response,
            f"python3 gopnik_setup.py --confirm-artifact-kind service --surfaces {evasion}",
        ) != 0, evasion
    assert check_stand(
        "stand", stand_response, extra_command="kubectl get secrets -A"
    ) != 0
    assert check_stand(
        "stand-ru",
        "Stage 2 проверяет собранный или развёрнутый результат там, где им реально "
        "пользуются. Есть ли стенд, на котором Gopnik сможет проверить уже "
        "развёрнутую версию?",
        extra_command="kubectl get secrets -A",
    ) != 0
    assert check_simple(
        "access",
        "How does a new version get there, and how can the agent obtain access? "
        "Do not send secrets; just name the existing access method.",
    ) == 0
    assert check_simple(
        "access",
        "Do not worry. How does a new version get there, and how can the agent "
        "obtain access? Please send secrets.",
    ) != 0
    assert check_simple(
        "access-ru",
        "Как новая версия попадает на стенд и как агенту получить к нему доступ? "
        "Секреты присылать не нужно — достаточно назвать существующий способ доступа.",
    ) == 0
    assert check_tool_turn(
        "access",
        "How does a new version get there, and how can the agent obtain access? "
        "Do not send secrets; just name the existing access method.",
        "Bash",
        {"command": "kubectl get secrets -A"},
    ) != 0
    assert check_tool_turn(
        "access-ru",
        "Как новая версия попадает на стенд и как агенту получить к нему доступ? "
        "Секреты присылать не нужно — достаточно назвать существующий способ доступа.",
        "Bash",
        {"command": "kubectl get secrets -A"},
    ) != 0

    deceptive = (
        "Here is how setup works. Stage 0 maps what could break. Stage 1 checks "
        "code in the repository. Stage 2 comes only after Stage 1 works. "
        "Stage 1 passed. No gopnik-critic ran. I found moonlight and paperwork. "
        "Do people use only moonlight, only paperwork, or both?"
    )
    assert check(deceptive, critic=False) != 0

    good_ru = (
        "Вот как проходит настройка. Stage 0 определяет, что может сломаться. "
        "Stage 1 проверяет код в репозитории. Stage 2 проверяет поставленный "
        "результат после того, как Stage 1 заработает. Stage 1 готова: штатная "
        "проверка прошла. Я вижу команду и веб-интерфейс. После поставки люди "
        "используют только команду, только веб-интерфейс или оба варианта?"
    )
    assert check(good_ru, mode="surfaces-ru") == 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        stage1_command=(
            "python3 gopnik_setup.py --defer-artifact-kind --language ru "
            "--stage1 './check.sh' --check"
        ),
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content="Не удалось изучить репозиторий; анализ поверхностей не завершён.",
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content=(
            "Проверка поверхностей заблокирована.\nGOPNIK_CRITIC_STATUS: blocked"
        ),
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content=(
            "Проверка выявила ошибку маршрута поставки; команда и веб-интерфейс "
            "остаются кандидатами.\n"
            "GOPNIK_CRITIC_SURFACES: command, web\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) == 0
    assert check(
        good,
        critic_content=(
            "The migration is the sole actual delivery surface; the command and web "
            "candidates are refuted.\nGOPNIK_CRITIC_SURFACES: migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good + " Migration.",
        critic_content=(
            "The command, web interface, and migration remain actual surfaces.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good_ru + " Миграция.",
        mode="surfaces-ru",
        critic_content=(
            "Команда, веб-интерфейс и миграция остаются реальными поверхностями.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good.replace("or both?", "or both, with no migration?"),
        critic_content=(
            "The command, web interface, and migration remain actual surfaces.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good_ru.replace("или оба варианта?", "или оба варианта, но не миграцию?"),
        mode="surfaces-ru",
        critic_content=(
            "Команда, веб-интерфейс и миграция остаются реальными поверхностями.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good.replace(
            "only the command, only the web interface",
            "only something other than the command, only something other than the web interface",
        )
    ) != 0
    assert check(
        good_ru.replace(
            "только команду, только веб-интерфейс",
            "только не команду, только не веб-интерфейс",
        ),
        mode="surfaces-ru",
    ) != 0
    assert check(
        good.replace(
            "After delivery,",
            "I also found an API. After delivery,",
        )
    ) != 0
    assert check(
        good_ru.replace(
            "После поставки",
            "Я также вижу API. После поставки",
        ),
        mode="surfaces-ru",
    ) != 0
    assert check(
        good.replace(
            "After delivery,",
            "I found a migration too: After delivery,",
        )
    ) != 0
    assert check(
        good_ru.replace(
            "После поставки",
            "Я также вижу миграцию: После поставки",
        ),
        mode="surfaces-ru",
    ) != 0
    assert check(
        good,
        critic_content=(
            "The command, web interface, and migration remain actual surfaces.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content=(
            "Команда, веб-интерфейс и миграция остаются реальными поверхностями.\n"
            "GOPNIK_CRITIC_SURFACES: command, web, migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good,
        critic_content=(
            "GOPNIK_CRITIC_SURFACES: command, web\n"
            "Further analysis found migration is the sole actual surface; command "
            "and web are refuted.\nGOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content=(
            "GOPNIK_CRITIC_SURFACES: command, web\n"
            "Дальнейший анализ показал, что единственная реальная поверхность — "
            "миграция; команда и веб-интерфейс опровергнуты.\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    assert check(
        good_ru,
        mode="surfaces-ru",
        critic_content=(
            "Единственная реальная поверхность поставки — миграция; команда и "
            "веб-интерфейс опровергнуты.\nGOPNIK_CRITIC_SURFACES: migration\n"
            "GOPNIK_CRITIC_STATUS: complete"
        ),
    ) != 0
    mixed_ru = (
        "Here is how setup works. Stage 0 maps failures. Stage 1 checks the "
        "repository. Stage 2 идёт после Stage 1. Stage 1 готова: check passed. "
        "Я вижу команду и веб-интерфейс. Люди используют только команду, "
        "только веб-интерфейс или оба варианта?"
    )
    assert check(mixed_ru, mode="surfaces-ru") != 0

    marker.write_text("forged-marker", encoding="utf-8")
    forged = [
        {"type": "result", "result": good},
        {"type": "assistant", "message": {"content": [{
            "type": "tool_use",
            "name": "Bash",
            "input": {"command": "echo gopnik-critic"},
        }]}},
    ]
    transcript.write_text(
        "\n".join(json.dumps(event) for event in forged) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(LIVE_SETUP_ORACLE),
            "surfaces",
            str(transcript),
            str(marker),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stdout + result.stderr


# ------------------------------------- a filled stage2 has to be ready (#51)


def _with_stage2(commands: list) -> pathlib.Path:
    return project({**PY_PROJECT, "gopnik.json": json.dumps(
        {"verification": {"artifact_kind": "service", "stage1": ["true"],
                          "stage2": commands}})})


def test_a_stage2_still_holding_the_drafts_blanks_is_refused():
    """#51, point 1. Pasted verbatim, a draft reads as configuration.

    It then fails on a hostname nobody set, at the moment a verdict was due —
    and the tempting way to write that up is the honest-looking `Not proven`
    #49 was about.
    """
    root = _with_stage2(["curl -fsS YOUR_URL/version | jq -e .",
                         "YOUR_LOG_QUERY --since=5m | grep -q x"])
    code, out = run_setup(root)
    assert code == 2, out
    assert "YOUR_URL" in out and "YOUR_LOG_QUERY" in out, "it did not name the blanks"


def test_a_finished_stage2_is_not_called_unfinished():
    """The other side, or the rule is satisfied by refusing everything."""
    root = _with_stage2(["curl -fsS https://svc.dev/version | jq -e .revision"])
    code, out = run_setup(root)
    assert code == 0, out
    assert "blanks" not in out, out


def test_the_blank_detector_does_not_fire_on_ordinary_shell():
    """Env vars and real hosts are uppercase too; a loose rule would refuse them."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    assert gopnik_setup.unfinished([
        "PYTHONPATH=src python3 -m pytest -q",
        "RID=cerb-$(git rev-parse --short HEAD)",
        "curl -fsS https://API.EXAMPLE.COM/v1 | jq -e .",
        "kubectl -n prod rollout status deploy/svc",
    ]) == []
    assert gopnik_setup.unfinished(["helm upgrade YOUR_APP ./charts"]) == ["YOUR_APP"]


def test_every_blank_the_draft_emits_is_one_the_detector_catches():
    """The rule has to cover what this script itself prints.

    Twice now a guard has been written for other people's commands and missed
    its own: the log-query placeholder, and the `gh run list` form. Derived
    from the draft rather than hand-listed so it cannot happen a third time.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for kind in gopnik_setup.DEPLOYED_KINDS:
        for evidence, forge in (([("helm", "helm/"), ("image", "Dockerfile")], None),
                                ([("k8s", "k8s/")], None),
                                ([("ci", ".github/workflows/deploy.yml")],
                                 gopnik_setup.FORGES[0][1:])):
            draft = gopnik_setup.draft_stage2(kind, evidence, forge)
            blanks = [w for line in draft for w in line.split()
                      if w.isupper() and len(w) > 3 and w.strip("'\"$(){}|") == w]
            missed = [b for b in blanks if not gopnik_setup.unfinished([b])]
            assert not missed, f"the draft emits blanks the detector misses: {missed}"


def test_the_skill_states_that_a_filled_stage2_is_not_optional():
    """#51, point 2. Implied everywhere, written nowhere."""
    for path, needles in (
        (SKILLS / "gopnik" / "SKILL.md",
         ("three states of stage2", "removed the choice", "**run it**")),
        (SKILLS / "gopnik" / "SKILL.ru.md",
         ("три состояния stage2", "снял выбор", "**выполнить**")),
    ):
        text = path.read_text(encoding="utf-8").lower()
        for needle in needles:
            assert needle.lower() in text, f"{path.name}: {needle!r}"


def test_the_skill_calls_missing_access_a_blocker_not_a_narrowing():
    """#51, point 3. "We could not log in today" must not lower the bar for good."""
    for path, needles in ((SKILLS / "gopnik" / "SKILL.md",
                           ("no access to run it", "not a narrowing")),
                          (SKILLS / "gopnik" / "SKILL.ru.md",
                           ("нет доступа выполнить", "не сужение"))):
        text = path.read_text(encoding="utf-8").lower()
        for needle in needles:
            assert needle in text, f"{path.name}: {needle!r}"


def test_the_three_states_are_named_in_one_place():
    """#51, point 4. Scattered across three sections, nobody sees which they are in."""
    for path in (SKILLS / "gopnik" / "SKILL.md", SKILLS / "gopnik" / "SKILL.ru.md"):
        text = path.read_text(encoding="utf-8")
        section = re.search(r"^### .*(?:three states|Три состояния).*?(?=^### )",
                            text, re.M | re.S)
        assert section, f"{path.name}: no single section naming the states"
        body = section.group(0)
        for needle in ("stage2_unreachable", "`Not proven`"):
            assert needle in body, f"{path.name}: the section never mentions {needle}"
        assert body.count("|") > 8, f"{path.name}: the three are not set out together"


def test_the_self_check_asks_whether_a_filled_stage2_was_run():
    for path, needle in ((SKILLS / "gopnik" / "SKILL.md", "if `stage2` was filled in, was it run"),
                         (SKILLS / "gopnik" / "SKILL.ru.md", "если `stage2` был заполнен")):
        checklist = [l for l in path.read_text(encoding="utf-8").lower().splitlines()
                     if l.startswith("- [ ]")]
        assert any(needle in l for l in checklist), f"{path.name}: not in the checklist"


# ------------------------------------------------- what installing does NOT do


def test_installing_writes_no_file_the_project_owns():
    """#33, item 1. The absence is the feature, so it is the assertion."""
    for flag in ("--claude", "--codex"):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / ".claude").mkdir()
            settings = root / ".claude" / "settings.json"
            mine = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}})
            settings.write_text(mine, encoding="utf-8")
            code, out = run_install(root, flag)
            assert code == 0, out
            assert settings.read_text(encoding="utf-8") == mine, f"{flag} edited settings.json"
            assert not (root / ".codex" / "hooks.json").exists(), f"{flag} wrote codex wiring"
            for stray in (".claude/hooks", ".codex/hooks"):
                assert not (root / stray).exists(), f"{flag} installed {stray}"


def test_installing_leaves_no_hook_script_anywhere():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        code, out = run_install(root, "--claude")
        assert code == 0, out
        strays = [p for p in root.rglob("*.py") if p.name in ("gopnik_gate.py", "gopnik_mark.py",
                                                              "gopnik_config.py")]
        assert not strays, strays


def test_installing_brings_every_skill_and_the_script_beside_its_own():
    for flag, where in (("--claude", ".claude/skills"), ("--codex", ".agents/skills")):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            code, out = run_install(root, flag)
            assert code == 0, out
            installed = {p.name for p in (root / where).iterdir()} if (root / where).is_dir() else set()
            expected = {p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists()}
            assert installed == expected, f"{flag}: installed {installed}, expected {expected}"
            script = root / where / "gopnik-setup" / "gopnik_setup.py"
            assert script.exists(), f"{flag}: the gopnik-setup skill describes a script that was not installed"
            # `cp -R` of a source tree that has been run carries its byte cache,
            # stamped with this machine's Python version, into the user's repo.
            junk = [str(p.relative_to(root)) for p in root.rglob("__pycache__")]
            junk += [str(p.relative_to(root)) for p in root.rglob("*.pyc")]
            assert not junk, f"{flag}: installed this machine's leftovers: {junk}"


def test_installing_leaves_a_config_and_setup_completes_it():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        for name, text in PY_PROJECT.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        code, out = run_install(root, "--claude", "--setup")
        assert code == 0, out
        body = config_of(root)
        assert body["verification"]["stage1"], out
        assert not any("replace with" in c for c in body["verification"]["stage1"]), body
        # An allowlist, because the named list missed `//verification` — a
        # comment key carried over from the example — and CI caught what this
        # test did not. Comment keys are allowed; DEAD_KEYS are named too, so a
        # failure says which one came back rather than only that one did.
        for key in DEAD_KEYS:
            assert key not in body, f"install left a dead key: {key}"
        extra = {k for k in body if k not in {"language", "verification"} and not k.startswith("//")}
        assert not extra, f"install left keys nothing reads: {extra}"


def test_an_existing_config_from_an_earlier_version_is_not_duplicated():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / ".claude").mkdir()
        (root / ".claude" / "gopnik.json").write_text('{"verification": {"stage1": ["true"]}}',
                                                        encoding="utf-8")
        code, out = run_install(root, "--claude")
        assert code == 0, out
        assert not (root / "gopnik.json").exists(), "wrote a second config beside the existing one"


# ------------------------------------------------------------ repository state


#: A line naming dead machinery in order to assert it is absent is the opposite
#: of the failure this looks for, and CI is full of them on purpose. Matched on
#: the line rather than the file, so a genuine description sitting next to an
#: assertion is still caught.
DENIES = re.compile(r"test !|test -z|not in |assert not|must not|no longer|-name '")


def test_nothing_in_the_repository_still_describes_the_hooks():
    """#33, item 4. Documentation that describes machinery that is gone ships.

    "Describes" is the requirement, not "mentions": the check below skips lines
    that name the machinery in order to assert its absence.
    """
    dead = re.compile(r"gopnik_gate|gopnik_mark|gopnik_config|gopnik-pending"
                      r"|PostToolUse|\benforce\b|claim_patterns|watch_paths")
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv"}
    # CHANGELOG is generated history and describes versions where these existed.
    # tests/ names them on purpose — this test is in it.
    skip_files = {"CHANGELOG.md"}
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in (".md", ".json", ".py", ".sh", ".yml", ".yaml"):
            continue
        if set(path.relative_to(ROOT).parts) & skip_dirs or path.name in skip_files:
            continue
        if path.relative_to(ROOT).parts[0] == "tests":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if DENIES.search(line):
                continue
            if dead.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:70]}")
    assert not offenders, "still describing machinery that was removed:\n  " + "\n  ".join(offenders)


# ------------------------------------------------------------ what it reads like


def test_the_output_uses_no_internal_vocabulary():
    root = project(PY_PROJECT)
    _, out = run_setup(root)
    found = jargon_in(out)
    assert not found, f"jargon reached the user: {found}\n{out}"


#: Non-empty lines the longest output may take — a first install with a check
#: that ran and failed. Set AT the current output rather than above it: the
#: previous bound was 24 against an actual 13, which no drift could ever reach,
#: so it read as a limit while being decoration.
MAX_LINES = 8


def test_the_output_fits_in_a_glance():
    """Measured on the longest case there is, not on the tidiest."""
    root = _project_with_a_failing_check()
    _, out = run_setup(root)
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) <= MAX_LINES, f"{len(lines)} lines of output:\n{out}"


def test_the_bound_is_one_the_output_could_actually_cross():
    """A limit nothing can reach is not a limit.

    This is the guard on the guard: raising MAX_LINES back out of reach is the
    cheapest way to pass the test above, and it would leave the suite green
    while the requirement was gone.
    """
    root = _project_with_a_failing_check()
    _, out = run_setup(root)
    lines = len([l for l in out.splitlines() if l.strip()])
    assert MAX_LINES - lines <= 2, (
        f"the bound is {MAX_LINES} and the output is {lines} — "
        "slack that wide means nothing will ever fail this")


def test_shortening_did_not_drop_any_of_the_facts():
    """#41, point 1. The cheapest way to pass a length test is to say less.

    Each of the six is asserted separately, against the longest output, so a
    fact removed fails by name rather than by a count nobody reads.
    """
    root = _project_with_a_failing_check()
    _, out = run_setup(root)
    facts = {
        "which toolchain": r"Python|Node|Rust|Go",
        "which kind": r"\b(cli|library|service|chart|migration|model-boundary|plugin)\b",
        "what was written": r"^  ok ",
        "what failed": r"FAILING",
        "what was not installed": r"[Nn]o hook was installed",
        "what is still missing": r"[Ss]till missing",
    }
    absent = [name for name, shape in facts.items() if not re.search(shape, out, re.M)]
    assert not absent, f"shortening dropped: {absent}\n{out}"


def test_the_closing_message_says_what_it_owes_the_reader():
    root = project(PY_PROJECT)
    _, out = run_setup(root)
    low = out.lower()
    assert "no hook was installed" in low, out
    assert "gopnik skill" in low, out
    assert "gopnik.json" in low, out


def test_unknown_project_asks_for_one_concrete_stage1_fact():
    root = project(MAKE_PROJECT)
    _, out = run_setup(root)
    assert "project-owned fast local check command" in out, out
    assert "1." not in out and "2." not in out, out


#: Words another plugin will also use for a skill. Skill names are one flat
#: namespace across everything a person has installed, and a collision is
#: silent: two directories answer to the name, both load, and the agent picks
#: by description. Reproduced on #69 with a foreign `setup`.
GENERIC_NAMES = {
    "setup", "critic", "review", "test", "tests", "check", "verify", "docs",
    "build", "deploy", "release", "lint", "format", "install", "config",
    "gate", "audit", "plan", "commit", "debug",
}


def test_no_skill_is_named_something_another_plugin_would_use():
    """#69, point 5. Fixed once and left to judgement is fixed until the next skill.

    `gopnik` keeps its name: it is the product, and a distinctive one. The
    other two were named for their role inside this repository, as though this
    repository were the only thing installed.
    """
    for skill in sorted(SKILLS.iterdir()):
        if not (skill / "SKILL.md").exists():
            continue
        head = (skill / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        declared = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
        assert declared == skill.name, (
            f"{skill.name}: frontmatter says {declared!r}")
        if declared == "gopnik":
            continue
        assert declared not in GENERIC_NAMES, (
            f"{declared!r} is a name another plugin will use — prefix it")
        assert declared.startswith("gopnik-"), (
            f"{declared!r} does not say whose it is")


def test_the_product_keeps_its_own_name():
    """#69, point 4. Renaming everything for symmetry helps nobody."""
    names = {p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists()}
    assert "gopnik" in names, f"the product lost its name: {names}"
    assert "gopnik-gopnik" not in names


def test_both_languages_declare_the_same_skill_name():
    """A rename that touches one file of a pair is a skill with two names."""
    for skill in sorted(SKILLS.iterdir()):
        ru = skill / "SKILL.ru.md"
        if not ru.exists():
            continue
        head = ru.read_text(encoding="utf-8").split("---")[1]
        declared = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
        assert declared == skill.name, f"{skill.name}: SKILL.ru.md says {declared!r}"


def test_skill_trigger_contract_lives_in_description_not_custom_frontmatter():
    for skill in sorted(SKILLS.iterdir()):
        for path in (skill / "SKILL.md", skill / "SKILL.ru.md"):
            if not path.exists():
                continue
            head = path.read_text(encoding="utf-8").split("---")[1]
            assert "when_to_use:" not in head, (
                f"{path.relative_to(ROOT)} uses unsupported when_to_use frontmatter"
            )


# --------------------------------- refreshing a record already written (#81)
#
# The order of these tests is the order the issue asks for. The destructive
# case comes first: a refresh that eats an operator's hand-written `stage2`,
# `stage2_unreachable` or `notes` is a worse product than one that never
# refreshes, so it has to be pinned before the constructive case is worth
# having.

FIXTURES = ROOT / "tests" / "fixtures"
STALE = FIXTURES / "stage1-stale"


def _stale_project() -> pathlib.Path:
    """The #81 fixture, materialised where the setup script can be run on it."""
    root = project({})
    shutil.copytree(STALE / "repo", root, dirs_exist_ok=True)
    return root


def _refresh_expectations() -> dict:
    return json.loads((STALE / "expected.json").read_text(encoding="utf-8"))["refresh"]


def _run_setup_in_place(root: pathlib.Path, *args: str) -> tuple[int, str]:
    """Run the shipped script against a tree that is not a scratch project."""
    proc = subprocess.run(
        [sys.executable, str(SETUP), *args, "--dir", str(root)],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"},
    )
    return proc.returncode, proc.stdout + proc.stderr


def _pure_insertion(before: str, after: str) -> str:
    """What was inserted, asserting that nothing at all was removed.

    Deliberately not a JSON comparison. `json.dumps` escapes non-ASCII and
    reindents, so a round-trip can hand back a file that compares equal as a
    value while every byte of an operator's note has moved. The oracle for this
    mode is the bytes: the edit has to be an insertion and nothing else.
    """
    head = len(os.path.commonprefix([before, after]))
    tail = len(os.path.commonprefix([before[head:][::-1], after[head:][::-1]]))
    removed = before[head:len(before) - tail]
    assert removed == "", f"the refresh deleted {removed!r}"
    return after[head:len(after) - tail]


def test_a_refresh_answer_leaves_every_hand_written_byte_alone():
    """The destructive negative, tested before the constructive case.

    The fixture's record carries a hand-written `stage2`, an operational note,
    and a local-override indirection inside both. Stage 1 grows; nothing else
    in that file may move by a single byte.
    """
    expected = _refresh_expectations()
    added = expected["unnamed"][0]
    root = _stale_project()
    config = root / "gopnik.json"
    before = config.read_text(encoding="utf-8")

    code, out = run_setup(root, "--add-stage1", added)
    assert code == 0, out
    after = config.read_text(encoding="utf-8")

    inserted = _pure_insertion(before, after)
    assert added in inserted, f"the insertion does not carry the check: {inserted!r}"

    body_before, body_after = json.loads(before), json.loads(after)
    assert body_after["verification"]["stage1"] == expected["after"], after
    for key in expected["hand_written"]:
        assert body_after["verification"][key] == body_before["verification"][key], (
            f"the refresh changed the hand-written {key!r}")
    assert "$DASHBOARD_STAGING_URL" in after, "the local indirection was rewritten"


def test_a_refresh_answer_keeps_an_unreachable_declaration_and_its_reason():
    """`stage2_unreachable` is a key this script would never write itself.

    It is also the one whose loss is silent: a verdict that should have
    narrowed itself stops saying why, and nobody notices until it matters.
    """
    root = _stale_project()
    config = root / "gopnik.json"
    body = json.loads(config.read_text(encoding="utf-8"))
    body["verification"]["stage2"] = []
    body["verification"]["stage2_unreachable"] = (
        "No stand exists: the dashboard is deployed straight from main by an "
        "account this project does not own."
    )
    body["verification"]["migration_notes"] = {"kept": "a key nothing here writes"}
    config.write_text(json.dumps(body, indent=4, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    before = config.read_text(encoding="utf-8")

    code, out = run_setup(root, "--add-stage1", "./ui-tests/run.sh")
    assert code == 0, out
    after = config.read_text(encoding="utf-8")

    inserted = _pure_insertion(before, after)
    assert "./ui-tests/run.sh" in inserted, inserted
    kept = json.loads(after)["verification"]
    assert kept["stage2_unreachable"] == body["verification"]["stage2_unreachable"]
    assert kept["migration_notes"] == {"kept": "a key nothing here writes"}
    # Four-space indentation is somebody's choice about their own file.
    assert '    "verification"' in after, "the refresh reindented the document"


def test_a_russian_note_comes_back_as_russian():
    """The exact way a value-level comparison passes and the file is ruined.

    `json.dumps` escapes non-ASCII by default. A refresh that round-tripped the
    document would leave `notes` deep-equal and unreadable.
    """
    note = "Стенд за периметром — адрес берётся из локального переопределения."
    root = _stale_project()
    config = root / "gopnik.json"
    body = json.loads(config.read_text(encoding="utf-8"))
    body["verification"]["notes"] = note
    config.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    code, out = run_setup(root, "--add-stage1", "./ui-tests/run.sh")
    assert code == 0, out
    after = config.read_text(encoding="utf-8")
    assert note in after, f"the note was re-encoded:\n{after}"
    assert "\\u0421" not in after, "the note came back as escapes"


def test_a_refresh_names_the_check_the_record_never_learned_about():
    """The constructive case: what is recorded, against what the tree has."""
    expected = _refresh_expectations()
    root = _stale_project()
    code, out = run_setup(root, "--refresh")
    assert code == 0, out
    for command in expected["unnamed"]:
        assert command in out, f"{command} was not reported:\n{out}"
    assert "--add-stage1" in out, f"nothing was offered:\n{out}"


def test_a_refresh_with_nothing_to_say_says_nothing():
    """A mode that finds something on every project is one people stop reading.

    Run against this repository, whose own record is current. If someone adds
    an executable check here that nothing in `stage1` names, this fails — and
    that is the correct outcome, not a brittle test.
    """
    code, out = _run_setup_in_place(ROOT, "--refresh")
    assert code == 0, out
    assert "still matches" in out, out
    assert "--add-stage1" not in out, f"cried wolf on its own repository:\n{out}"
    assert "named by no recorded command" not in out, out
    assert "no longer here" not in out, out


def test_a_refresh_names_a_recorded_command_that_is_no_longer_here():
    """The staleness half: a route can rot with no release involved."""
    root = _stale_project()
    (root / "check.sh").unlink()
    code, out = run_setup(root, "--refresh")
    assert code == 0, out
    assert "gone" in out, out
    assert "./check.sh" in out, out


def test_a_gone_command_and_an_unaccounted_check_are_reported_together():
    """The mixed cell. Two things changed since the record; both get said."""
    root = _stale_project()
    (root / "check.sh").unlink()
    code, out = run_setup(root, "--refresh")
    assert code == 0, out
    assert "./check.sh" in out, f"the gone command is hidden:\n{out}"
    assert "./ui-tests/run.sh" in out, f"the unnamed check is hidden:\n{out}"


def test_a_refresh_writes_nothing_at_all():
    root = _stale_project()
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--refresh")
    assert code == 0, out
    assert (root / "gopnik.json").read_bytes() == before


def test_a_refresh_without_a_configuration_refuses_to_become_a_setup():
    root = project(PY_PROJECT)
    code, out = run_setup(root, "--refresh")
    assert code == 2, out
    assert not (root / "gopnik.json").exists(), (
        "refresh silently turned into a first-time setup")


def test_a_check_that_does_not_pass_here_is_never_recorded():
    """The offer is not a licence to write a red command.

    This is how the destructive case would arrive by the back door: the report
    names a check, the person says add it, and a refresh that trusted the
    answer instead of the exit status would record something that fails.
    """
    root = _stale_project()
    suite = root / "ui-tests" / "run.sh"
    suite.write_text("#!/bin/sh\necho 'the dashboard never rendered'\nexit 1\n",
                     encoding="utf-8")
    os.chmod(suite, 0o755)
    before = (root / "gopnik.json").read_bytes()

    code, out = run_setup(root, "--add-stage1", "./ui-tests/run.sh")
    assert code == 2, out
    assert "FAILING" in out, out
    assert (root / "gopnik.json").read_bytes() == before


def test_a_command_the_record_already_has_is_not_added_twice():
    root = _stale_project()
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--add-stage1", "./check.sh")
    assert code == 0, out
    assert (root / "gopnik.json").read_bytes() == before
    assert config_of(root)["verification"]["stage1"].count("./check.sh") == 1


def test_the_answer_can_be_rehearsed_without_writing():
    root = _stale_project()
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root, "--add-stage1", "./ui-tests/run.sh", "--check")
    assert code == 0, out
    assert (root / "gopnik.json").read_bytes() == before
    assert "Nothing was written" in out, out


def test_a_record_the_edit_cannot_locate_is_refused_rather_than_rewritten():
    """Failing closed is the only acceptable failure for this write."""
    for broken in ({"verification": {"stage1": "./check.sh"}},
                   {"verification": {}},
                   {"nothing": "here"}):
        root = project({**PY_PROJECT, "gopnik.json": json.dumps(broken)})
        before = (root / "gopnik.json").read_bytes()
        code, out = run_setup(root, "--add-stage1", "true")
        assert code == 2, out
        assert (root / "gopnik.json").read_bytes() == before, (
            f"a record it could not read was rewritten anyway: {broken}")


def test_a_plain_rerun_still_refuses_to_touch_a_record_it_did_not_write():
    """Today's behaviour has to survive. The refresh is a mode you ask for."""
    root = _stale_project()
    before = (root / "gopnik.json").read_bytes()
    code, out = run_setup(root)
    assert (root / "gopnik.json").read_bytes() == before, out
    assert "--add-stage1" not in out, (
        f"a plain re-run started offering to edit the record:\n{out}")


def test_a_refresh_cannot_be_combined_with_a_setup_run():
    root = _stale_project()
    for extra in (("--stage1", "true"),
                  ("--defer-artifact-kind",),
                  ("--language", "ru"),
                  ("--draft-stage2",),
                  ("--confirm-artifact-kind", "cli"),
                  ("--add-stage1", "true")):
        code, out = run_setup(root, "--refresh", *extra)
        assert code == 2, f"--refresh {extra} was accepted:\n{out}"


def test_an_ordinary_command_is_never_called_a_deleted_file():
    """The false alarm that would make this mode noise.

    Every entry below was reported as a deleted file by the first version. The
    first three are the ones that mattered: `go test ./...` is the commonest
    Stage 1 command in the Go ecosystem, and every Go project would have been
    told its recorded check had vanished.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    for quiet in (
        "go test ./...", "go vet ./...", "go build ./cmd/...",
        "cd frontend && ./test.sh",          # a path relative to somewhere else
        "sh -c './check.sh && ./lint.sh'",   # one token, not a filename
        "docker run --rm -v /tmp/cache:/cache img pytest",  # a mount, not a path
        "sh -n install.sh", "git status", "make check",
        "python3 -m pytest tests/ -q", "npm run test",
    ):
        assert gopnik_setup.recorded_path_token(quiet) is None, (
            f"{quiet!r} would be reported as a deleted file")

    # Still detected: the documented-wrapper shape this mode is actually for.
    assert gopnik_setup.recorded_path_token("./check.sh") == "./check.sh"
    assert gopnik_setup.recorded_path_token("sh ./ui-tests/run.sh") == "./ui-tests/run.sh"
    assert gopnik_setup.recorded_path_token("./app.sh --test") == "./app.sh"


def test_nothing_is_offered_back_on_this_project_whatever_its_stage1_said():
    """The silence has to be a property, not a coincidence.

    It was a coincidence. This project's `stage1` happens to carry the bare
    word `tests` inside a `compileall` line; that resolved to a real directory
    and covered the whole fixture pack. Under any other ordinary Stage 1 the
    same tree produced ten candidates — every fixture repository in the pack,
    including one that fails on purpose, offered as a check to record and run.
    """
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    recorded = json.loads((ROOT / "gopnik.json").read_text(encoding="utf-8"))
    for stage1 in (recorded["verification"]["stage1"],
                   recorded["verification"]["stage1"][1:],   # no compileall line
                   ["python3 -m pytest"], ["make test"], ["npm test"],
                   ["./check.sh"], []):
        found = gopnik_setup.unnamed_checks(stage1, ROOT)
        assert found == [], (
            f"with stage1={stage1!r} this project offers back {found}")


def test_a_configuration_with_windows_line_endings_keeps_them():
    """The blocker a critic found: the guarantee was in the wrong function.

    `splice_stage1` is a pure insertion, but `add_stage1` read and wrote with
    universal newlines, so a CRLF file — every Windows working tree with
    `core.autocrlf=true` — had every line ending in it silently rewritten,
    under a message saying nothing else had been touched. The re-parse guard
    cannot see it: the values are equal, and it is the file that is mangled.
    """
    crlf = b"\r\n"
    root = _stale_project()
    config = root / "gopnik.json"
    config.write_bytes(
        config.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    before = config.read_bytes()
    assert before.count(crlf) > 5, "the fixture is not actually CRLF"

    code, out = run_setup(root, "--add-stage1", "./ui-tests/run.sh")
    assert code == 0, out
    after = config.read_bytes()

    assert after.count(crlf) == before.count(crlf) + 1, (
        f"line endings were rewritten: {before.count(crlf)} -> {after.count(crlf)}")
    inserted = _pure_insertion(before.decode("utf-8"), after.decode("utf-8"))
    assert "./ui-tests/run.sh" in inserted, inserted


def test_the_edit_refuses_when_another_stage1_comes_first():
    """The guard that had no test, on the case it exists for.

    Deleting the re-parse guard left the whole suite green. It is the only
    thing standing between the splice finding the wrong array and a silent
    corrupt write, so it needs the input that actually reaches it — a
    `verification.stage1` belonging to somebody else, earlier in the document.
    """
    decoy = {
        "local": {"verification": {"stage1": ["someone else's block"]}},
        "verification": {"stage1": ["true"], "notes": "mine"},
    }
    root = project({**PY_PROJECT, "gopnik.json": json.dumps(decoy, indent=2)})
    # The command has to PASS. The first version of this test used a command
    # that did not exist, so it exited 2 at the run-the-check stage and never
    # reached the guard at all — it asserted the right number for the wrong
    # reason, and the mutant with the guard deleted sailed straight through it.
    passing = root / "ok.sh"
    passing.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(passing, 0o755)
    before = (root / "gopnik.json").read_bytes()

    code, out = run_setup(root, "--add-stage1", "./ok.sh")
    assert code == 2, f"the guard did not refuse:\n{out}"
    assert "changed more than stage1" in out, (
        f"it refused, but not at the guard:\n{out}")
    assert (root / "gopnik.json").read_bytes() == before, (
        "somebody else's stage1 was edited")
    assert config_of(root)["local"]["verification"]["stage1"] == ["someone else's block"]


def test_a_non_ascii_command_is_recorded_as_itself():
    """`ensure_ascii=False` on the inserted element had nothing checking it."""
    root = _stale_project()
    command = "./проверка.sh"
    suite = root / "проверка.sh"
    suite.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(suite, 0o755)

    code, out = run_setup(root, "--add-stage1", command)
    assert code == 0, out
    after = (root / "gopnik.json").read_text(encoding="utf-8")
    assert command in after, f"the command was escaped:\n{after}"
    assert "\\u043f" not in after, "the command came back as escapes"


def test_a_check_that_cannot_go_red_is_not_recorded():
    """An answer is not a licence to record something that always passes."""
    root = _stale_project()
    before = (root / "gopnik.json").read_bytes()
    for green in ("", "   ", "echo fine", "true", "# not a check"):
        code, out = run_setup(root, "--add-stage1", green)
        assert code == 2, f"{green!r} was accepted:\n{out}"
        assert "cannot fail" in out, out
        assert (root / "gopnik.json").read_bytes() == before


def test_the_splice_edits_one_key_and_reformats_nothing():
    """Unit-level, because the traps are in the text rather than the values."""
    sys.path.insert(0, str(SETUP.parent))
    import gopnik_setup

    # `//stage1` is a real key in this project's own configuration. A scanner
    # that matched on substrings would edit the comment instead of the list.
    text = (
        '{\n  "verification": {\n    "//stage1": "not this one",\n'
        '    "stage1": [\n      "a"\n    ],\n    "notes": "кириллица"\n  }\n}\n'
    )
    out = gopnik_setup.splice_stage1(text, ["b"])
    assert json.loads(out)["verification"]["stage1"] == ["a", "b"], out
    assert '"//stage1": "not this one"' in out, out
    assert "кириллица" in out, out
    assert out.replace(',\n      "b"', "", 1) == text, out

    # A bracket inside a string is not the end of the list.
    packed = '{"verification": {"stage1": ["echo ]", "x"], "notes": "["}}'
    grown = gopnik_setup.splice_stage1(packed, ["y"])
    assert json.loads(grown)["verification"]["stage1"] == ["echo ]", "x", "y"], grown
    assert json.loads(grown)["verification"]["notes"] == "[", grown

    # An empty list is still a list.
    empty = gopnik_setup.splice_stage1('{"verification": {"stage1": []}}', ["a"])
    assert json.loads(empty)["verification"]["stage1"] == ["a"], empty


def test_the_setup_skill_documents_the_refresh_in_both_languages():
    en = (SKILLS / "gopnik-setup" / "SKILL.md").read_text(encoding="utf-8")
    ru = (SKILLS / "gopnik-setup" / "SKILL.ru.md").read_text(encoding="utf-8")
    for text, where in ((en, "SKILL.md"), (ru, "SKILL.ru.md")):
        assert "--refresh" in text, f"{where} never names the refresh mode"
        assert "--add-stage1" in text, f"{where} never names how an answer is recorded"

def _live_setup_oracle_module():
    spec = importlib.util.spec_from_file_location(
        "live_setup_oracle", LIVE_SETUP_ORACLE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flat_text(path: pathlib.Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_ignore_question_is_one_string_in_the_skills_and_the_oracle():
    """#78. The oracle holds the question; the skills tell the agent to say it.

    Every question literal in the oracle already lives in a skill file too, and
    nothing compares them, so a reworded skill and an untouched oracle would
    both keep passing while the live procedure checked a sentence nobody is
    told to say any more.
    The ignore question is the first pair that is actually compared. The
    Russian skill writes non-breaking spaces after single-letter prepositions,
    which `str.split()` treats as whitespace, so the comparison is on the
    flattened text rather than on the bytes.
    """
    module = _live_setup_oracle_module()
    english = _flat_text(SKILLS / "gopnik-setup" / "SKILL.md")
    russian = _flat_text(SKILLS / "gopnik-setup" / "SKILL.ru.md")
    guide = _flat_text(ROOT / "docs" / "install.md")

    assert module.OVERRIDE_QUESTION in english, "SKILL.md lost the ignore question"
    assert module.OVERRIDE_QUESTION in guide, "install.md lost the ignore question"
    assert module.OVERRIDE_QUESTION_RU in russian, "SKILL.ru.md lost the ignore question"
    assert module.OVERRIDE_QUESTION_RU in guide, "install.md lost the Russian ignore question"


def test_the_skill_reads_the_install_scope_off_the_repository():
    """#78. Nothing passes setup the install scope, and it needs it.

    `docs/install.md` asks the scope question and keeps the answer "for the rest
    of this setup conversation", but a standalone setup run has no such
    conversation and only `--language` is passed on. The substitute has to
    answer the question the scope stands for — does the team receive Gopnik with
    this project — so it is the repository that is read, not the path the
    running copy happens to have: a project can carry a committed skills
    directory while a user-level copy executes, and a skills directory the
    repository ignores travels to nobody however local it looks.
    """
    english = _flat_text(SKILLS / "gopnik-setup" / "SKILL.md")
    russian = _flat_text(SKILLS / "gopnik-setup" / "SKILL.ru.md")

    for phrase in (
        "read it off the repository instead",
        "`.claude/skills/gopnik-setup` or `.agents/skills/gopnik-setup` inside the working tree that git does not ignore",
        "`git ls-files` and `git check-ignore` answer the second",
        "The copy you are running is a signal, not the answer",
        "the repository decides",
    ):
        assert phrase in english, f"SKILL.md: {phrase}"

    for phrase in (
        "определи её по самому репозиторию",
        "в рабочем дереве, который git не игнорирует",
        "на вторую отвечают `git ls-files` и `git check-ignore`",
        "это признак, а не ответ",
        "решает репозиторий",
    ):
        assert phrase in russian, f"SKILL.ru.md: {phrase}"


def test_live_setup_oracle_separates_repository_scope_from_user_scope():
    """#78, and the control is half of it.

    A field install at repository scope put the override — a private host, a
    namespace, an IaC directory and a secret-store read command — in
    `.git/info/exclude`, which is not committed. The protection stayed on one
    machine while the skills and `gopnik.json` travelled to the team. The fix is
    not "ask about `.gitignore`": a run that asks at user scope too has moved
    the defect into someone else's repository. Both polarities are checked here,
    and so is the third case, where no override is needed and nothing should be
    asked at all.
    """
    module = _live_setup_oracle_module()
    root = pathlib.Path(tempfile.mkdtemp())
    transcript = root / "turn.jsonl"

    def run(mode: str, result: str, calls: tuple = ()) -> int:
        events = []
        for index, (name, payload) in enumerate(calls):
            tool_id = f"call-{index}"
            events.append({"type": "assistant", "message": {"content": [{
                "type": "tool_use",
                "id": tool_id,
                "name": name,
                "input": payload,
            }]}})
            events.append({"type": "user", "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": tool_id,
                "is_error": False,
                "content": "done",
            }]}})
        events.append({"type": "result", "result": result})
        transcript.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(LIVE_SETUP_ORACLE), mode, str(transcript)],
            capture_output=True,
            text=True,
        ).returncode

    ask = module.OVERRIDE_QUESTION
    ask_ru = module.OVERRIDE_QUESTION_RU
    silent = "Stage 1 passed. I will look at the deployed version next."
    silent_ru = "Stage 1 прошла. Дальше посмотрю на развёрнутую версию."
    write_override = ("Write", {"file_path": "gopnik.local.json", "content": "{}"})
    write_exclude = ("Bash", {"command": "printf 'gopnik.local.json' >> .git/info/exclude"})
    write_gitignore = ("Bash", {"command": "printf 'gopnik.local.json' >> .gitignore"})
    read_exclude = ("Bash", {"command": "cat .git/info/exclude"})
    read_rules = ("Bash", {"command": "git check-ignore -v gopnik.local.json"})

    # Repository scope: the question is the whole turn, and it precedes any
    # ignore rule. Reading the existing rules first is how you find out whether
    # one is needed, so reading is not writing.
    assert run("override", ask, (write_override,)) == 0
    assert run("override", ask, (write_override, read_exclude, read_rules)) == 0
    assert run("override-ru", ask_ru, (write_override,)) == 0

    # The defect itself: the machine-local route taken because it needs no
    # question. It must not pass at repository scope.
    assert run("override", silent, (write_override, write_exclude)) != 0, (
        "an override ignored only in .git/info/exclude passed at repository scope"
    )
    assert run("override", ask, (write_override, write_exclude)) != 0, (
        "the question passed while the rule had already been written elsewhere"
    )
    assert run("override", ask, (write_override, write_gitignore)) != 0, (
        "a tracked project file was edited before the question was answered"
    )
    assert run("override", ask_ru, (write_override,)) != 0
    assert run("override-ru", ask, (write_override,)) != 0

    # The control. At user scope the override is personal: `.git/info/exclude`
    # is right, and the question is noise in someone else's repository.
    assert run("override-user", silent, (write_override, write_exclude)) == 0
    assert run("override-user-ru", silent_ru, (write_override, write_exclude)) == 0
    assert run("override-user", ask, (write_override, write_exclude)) != 0, (
        "the repository-scope question passed at user scope: the defect moved"
    )
    assert run(
        "override-user",
        "Should I ignore that file for you?",
        (write_override, write_exclude),
    ) != 0
    assert run(
        "override-user-ru",
        "Добавить этот файл в игнорируемые?",
        (write_override, write_exclude),
    ) != 0
    assert run("override-user", silent, (write_override, write_gitignore)) != 0, (
        "a personal override was ignored in a file the whole team receives"
    )
    assert run("override-user", silent, (write_override,)) != 0, (
        "an override nobody ignored passed at user scope"
    )

    # Prose is not a question. A user-scope turn that names the file while
    # explaining what it did is not the defect, and reddening it would only
    # teach the next author to say less.
    assert run(
        "override-user",
        "Your .gitignore is untouched; the override is ignored locally.",
        (write_override, write_exclude),
    ) == 0

    # The turn after consent, which is where the defect actually lands. Asking
    # the question proves nothing about which file then received the rule, and
    # the field install asked nobody anything.
    assert run("override-applied", "Added it to .gitignore.", (write_gitignore,)) == 0
    assert run("override-applied", "Ignored it locally.", (write_exclude,)) != 0, (
        "a rule that reached only this machine passed the applied cell"
    )
    assert run("override-applied", "All set.", ()) != 0

    # The decline branch: still ignored here, and reported as machine-local.
    declined = (
        "Understood — I have kept it out of commits on this machine only, "
        "so the next person will not receive that protection."
    )
    assert run("override-declined", declined, (write_exclude,)) == 0
    assert run("override-declined", "Understood, done.", (write_exclude,)) != 0, (
        "a silent downgrade passed the decline cell"
    )
    assert run("override-declined", declined, (write_gitignore,)) != 0
    assert run("override-declined", declined, ()) != 0
    assert run(
        "override-declined-ru",
        "Понял — защита теперь распространяется только на эту машину.",
        (write_exclude,),
    ) == 0

    # #80 removed a Stage 2 route that borrowed the operator's login. These
    # turns bounded nothing, so the same reach passed them.
    assert run("override", ask, (("Read", {"file_path": "/home/u/.claude/.credentials.json"}),)) != 0
    assert run("override", ask, (("Bash", {"command": "kubectl get secrets -A"}),)) != 0
    assert run("override-user", silent, (write_exclude, ("Read", {"file_path": "~/.claude/.claude.json"}))) != 0

    # The exclude file is not at `.git/info/exclude` in a linked worktree or a
    # submodule, where `.git` is a file. The correct spelling has to count.
    worktree_exclude = ("Bash", {
        "command": 'printf "gopnik.local.json\n" >> "$(git rev-parse --git-dir)/info/exclude"',
    })
    assert run("override-user", silent, (write_override, worktree_exclude)) == 0, (
        "the worktree-correct exclude path was not recognised as ignoring anything"
    )
    assert run("override", ask, (write_override, worktree_exclude)) != 0, (
        "a machine-local write hid behind the worktree-correct spelling"
    )

    # No override, no question, in either scope and either language.
    assert run("override-none", silent, ()) == 0
    assert run("override-none", silent_ru, ()) == 0
    assert run("override-none", ask, ()) != 0
    assert run("override-none", silent, (write_exclude,)) != 0
    assert run("override-none", silent, (write_gitignore,)) != 0

    shutil.rmtree(root, ignore_errors=True)


def _main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as exc:
                print(f"  FAIL {name}: {exc}")
                failures += 1
            except Exception as exc:  # a broken test is a failing test
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures += 1
    print("all tests passed" if not failures else f"{failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
