#!/usr/bin/env python3
"""Executable editorial contract for Gopnik's public README pages."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
README_RU = ROOT / "README.ru.md"
HOW = ROOT / "docs/how-it-works.md"
HOW_RU = ROOT / "docs/how-it-works.ru.md"


def section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    rest = text[start:]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def fenced(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    language = ""
    body: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("```"):
            if inside:
                blocks.append((language, "\n".join(body).strip()))
                language, body, inside = "", [], False
            else:
                language, inside = line[3:].strip(), True
            continue
        if inside:
            body.append(line)
    return blocks


def headings(path: pathlib.Path) -> list[int]:
    return [len(match.group(1)) for match in re.finditer(r"^(#+)\s+", path.read_text(), re.M)]


def test_readme_is_a_short_front_door() -> None:
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        nonblank = [line for line in text.splitlines() if line.strip()]
        assert len(nonblank) <= 105, f"{path.name}: {len(nonblank)} nonblank lines"
        assert text.count("\n## ") == 7, f"{path.name}: the front door grew new sections"


def test_both_languages_have_the_same_shape() -> None:
    assert headings(README) == headings(README_RU)
    assert len(fenced(README.read_text())) == len(fenced(README_RU.read_text()))
    assert "README.ru.md" in README.read_text()
    assert "README.md" in README_RU.read_text()


def test_hero_and_brand_assets_are_real() -> None:
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        assert 'src="docs/assets/hero-gopnik.png"' in text
    for asset in ("hero-gopnik.png", "logo.svg", "mark-16.svg", "wordmark.svg"):
        target = ROOT / "docs/assets" / asset
        assert target.is_file() and target.stat().st_size > 100, asset


def test_install_is_one_agent_prompt_not_a_platform_matrix() -> None:
    expected = {
        README: [
            "Before anything else, read this complete raw guide via stdout only—do not save it—then follow it exactly:",
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md",
        ],
        README_RU: [
            "Прежде чем что-либо делать, прочитай эту полную raw-инструкцию только через stdout — не сохраняй её в файл — и точно следуй ей:",
            "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md",
        ],
    }
    for path, lines in expected.items():
        heading = "## Install" if path == README else "## Установка"
        body = section(path.read_text(encoding="utf-8"), heading)
        blocks = [block for language, block in fenced(body) if language == "text"]
        assert blocks == ["\n".join(lines)], (path.name, blocks)
        for internal in ("claude plugin", "codex plugin", "install.sh", "gopnik.json"):
            assert internal not in body.lower(), (path.name, internal)


def test_run_prompt_names_the_discoverable_skill() -> None:
    for path, heading, command in (
        (README, "## Run it", "Run the gopnik skill on this change."),
        (README_RU, "## Запуск", "Прогони навык gopnik по этому изменению."),
    ):
        blocks = fenced(section(path.read_text(encoding="utf-8"), heading))
        assert ("text", command) in blocks


def test_front_door_explains_all_three_stages_without_redefining_them() -> None:
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        for stage in ("Stage 0", "Stage 1", "Stage 2"):
            assert text.count(stage) >= 1, (path.name, stage)
        assert "Scope / Attack / Reality" not in text


def test_verdict_is_scoped_and_shows_failure() -> None:
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        assert "Verdict: NOT READY" in text
        assert "READY" in text
        lowered = text.lower()
        assert ("scope" in lowered or "област" in lowered), path.name
        assert ("revision" in lowered or "ревизи" in lowered), path.name
        assert ("not proven" in lowered or "недоказ" in lowered), path.name


def test_recommendation_and_tracker_example_are_not_commands() -> None:
    en = section(README.read_text(), "## Three skills, one development loop")
    ru = section(README_RU.read_text(), "## Три навыка, один цикл разработки")
    en_flat, ru_flat = " ".join(en.split()), " ".join(ru.split())
    assert "We recommend" in en_flat and "For example" in en_flat
    assert "Мы рекомендуем" in ru_flat and "Например" in ru_flat
    assert "task from your tracker" in en_flat
    assert "задачи из трекера" in ru_flat
    assert not fenced(en) and not fenced(ru)


def test_technical_details_live_in_the_reference() -> None:
    for readme in (README, README_RU):
        text = readme.read_text(encoding="utf-8")
        assert "how-it-works" in text
        assert "artifact_kind" not in text
        assert "stage2_unreachable" not in text
    for path in (HOW, HOW_RU):
        text = path.read_text(encoding="utf-8")
        for token in ("Stage 0", "Stage 1", "Stage 2", "gopnik.json", "artifact_kind"):
            assert token in text, (path.name, token)
        assert ("authority" in text.lower() or "полномочи" in text.lower()), path.name


def test_every_documentation_link_resolves() -> None:
    for path in (README, README_RU):
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            assert (ROOT / target).exists(), f"{path.name}: missing {target}"


def test_russian_page_avoids_old_english_calques() -> None:
    text = README_RU.read_text(encoding="utf-8").lower()
    for banned in ("адверсариальн", "гейт", "оракул", "артефакт"):
        assert banned not in text, banned


def test_readme_does_not_claim_automatic_enforcement() -> None:
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8").lower()
        assert "not a daemon" in text or "не фоновая служба" in text
        assert "release authority" in text or "источник полномочий" in text


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
