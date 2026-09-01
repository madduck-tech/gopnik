#!/usr/bin/env python3
"""Fail closed on the user-visible checkpoints in the live setup conversation."""

from __future__ import annotations

import json
import pathlib
import re
import shlex
import sys


LANGUAGE_QUESTION = "Which language would you like me to use: English or Russian?"
SCOPE_QUESTION = (
    "Where should I install Gopnik: for this agent across your projects, "
    "or only in this repository so the team receives it with the project?"
)
SCOPE_QUESTION_RU = (
    "Куда установить Gopnik: для этого агента во всех ваших проектах или "
    "только в этот репозиторий, чтобы команда получала его вместе с проектом?"
)
STAND_QUESTION = (
    "Is there a test or staging environment where Gopnik can verify the "
    "deployed version?"
)
ACCESS_QUESTION = (
    "How does a new version get there, and how can the agent obtain access? "
    "Do not send secrets; just name the existing access method."
)
STAND_QUESTION_RU = (
    "Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?"
)
STAND_RESPONSE = (
    "Stage 2 checks the built or deployed result where people actually use it. "
    + STAND_QUESTION
)
STAND_RESPONSE_RU = (
    "Stage 2 проверяет собранный или развёрнутый результат там, где им реально пользуются. "
    + STAND_QUESTION_RU
)
ACCESS_QUESTION_RU = (
    "Как новая версия попадает на стенд и как агенту получить к нему доступ? "
    "Секреты присылать не нужно — достаточно назвать существующий способ доступа."
)
OVERRIDE_QUESTION = (
    "Stage 2 here needs values that belong to this machine, so they go into a "
    "separate local file. May I add that file to .gitignore, so it stays out of "
    "commits for everyone working on this repository?"
)
OVERRIDE_QUESTION_RU = (
    "Stage 2 здесь нужны значения, привязанные к этой машине, поэтому они уйдут "
    "в отдельный локальный файл. Можно добавить этот файл в .gitignore, чтобы он "
    "не попадал в коммиты ни у кого, кто работает с этим репозиторием?"
)
#: The two ignore files, kept apart on purpose: which one receives the rule is
#: the entire difference between protecting a team and protecting one machine.
#: The exclude file is matched by its tail rather than by `.git/info/exclude`,
#: because in a linked worktree or a submodule `.git` is a file and the real
#: path is whatever `git rev-parse --git-dir` prints.
GITIGNORE = ".gitignore"
EXCLUDE = "info/exclude"
#: Session state that belongs to the person running the check. #80 removed a
#: Stage 2 route that borrowed it; a turn that reaches for it here is the same
#: defect in a different place, so these modes refuse rather than ignore it.
OPERATOR_STATE = (
    ".credentials.json",
    ".claude.json",
    "/.codex",
    ".config/gcloud",
    ".kube/config",
)
CRITIC_COMPLETE_MARKER = "GOPNIK_CRITIC_STATUS: complete"
CRITIC_BLOCKED_MARKER = "GOPNIK_CRITIC_STATUS: blocked"
CRITIC_SURFACES_MARKER = "GOPNIK_CRITIC_SURFACES:"
RAW_INSTALL_URL = (
    "https://raw.githubusercontent.com/madduck-tech/gopnik/main/docs/install.md"
)
#: Where the fixture facts live when the caller names no fixture. This is a
#: path rather than a table of literals on purpose: the strings below used to be
#: spelled out in this file, which is what made a second fixture impossible.
DEFAULT_FIXTURE = (
    pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "hybrid"
)

#: Keys a setup fixture owes. Absent, each one would weaken a check rather than
#: fail it.
REQUIRED = ("role", "stage1", "artifact_kind", "surfaces", "marker", "internal_details")


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def expectations(directory: pathlib.Path) -> dict:
    """What this fixture, rather than this script, says about itself."""
    body = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    if body.get("role") != "setup":
        raise ValueError(f"{directory}: expected.json is not a setup fixture")
    missing = [key for key in REQUIRED if key not in body]
    if missing:
        raise ValueError(f"{directory}: expected.json is missing {missing}")
    if not body["stage1"]:
        raise ValueError(f"{directory}: expected.json records no Stage 1 command")
    gap = body.get("gap")
    if gap is not None and not (
        isinstance(gap, dict) and gap.get("named") and gap.get("command")
    ):
        raise ValueError(f"{directory}: gap needs `named` and `command`")
    return body


def records(path: pathlib.Path) -> list[object]:
    raw = path.read_text(encoding="utf-8")
    try:
        return [json.loads(raw)]
    except json.JSONDecodeError:
        parsed = []
        for number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {number} is not JSON: {exc}") from exc
        return parsed


def final_result(items: list[object]) -> tuple[int, str]:
    found = [
        (index, " ".join(item["result"].split()))
        for index, item in enumerate(items)
        if isinstance(item, dict) and isinstance(item.get("result"), str)
    ]
    if len(found) != 1 or found[0][0] != len(items) - 1:
        raise ValueError("the transcript must end with exactly one final result event")
    return found[0]


def one_question(result: str) -> bool:
    return result.count("?") == 1


def nested_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from nested_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_dicts(item)


def text_values(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)


def tool_results(items: list[object], tool_use_id: str) -> list[tuple[int, dict]]:
    found = []
    for index, item in enumerate(items):
        for value in nested_dicts(item):
            if (
                value.get("type") == "tool_result"
                and value.get("tool_use_id") == tool_use_id
            ):
                found.append((index, value))
    return found


def tool_uses(items: list[object]) -> list[dict]:
    return [
        value
        for item in items
        for value in nested_dicts(item)
        if value.get("type") == "tool_use"
    ]


def assistant_text_before(items: list[object], limit: int) -> str:
    blocks = []
    for index, item in enumerate(items):
        if index >= limit or not isinstance(item, dict) or item.get("type") != "assistant":
            continue
        message = item.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                blocks.append(block["text"])
    return " ".join(blocks)


def assistant_text_between(items: list[object], start: int, end: int) -> str:
    blocks = []
    for index, item in enumerate(items):
        if index <= start or index >= end or not isinstance(item, dict) or item.get("type") != "assistant":
            continue
        message = item.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                blocks.append(block["text"])
    return " ".join(blocks)


def raw_guide_fetch(value: dict) -> bool:
    name = str(value.get("name") or "").lower()
    payload = value.get("input")
    serialized = json.dumps(payload, ensure_ascii=False)
    if serialized.count(RAW_INSTALL_URL) != 1:
        return False
    if name in {"webfetch", "web_fetch"}:
        return (
            isinstance(payload, dict)
            and payload.get("url") == RAW_INSTALL_URL
            and set(payload) <= {"url", "prompt"}
        )
    if name != "bash" or not isinstance(payload, dict):
        return False
    command = payload.get("command")
    if not isinstance(command, str) or re.search(r"[;#|&<>\n\r`]", command) or "$(" in command:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv or argv[-1] != RAW_INSTALL_URL:
        return False
    if argv[0] == "curl":
        allowed = {
            "-f", "-s", "-S", "-L", "-fsSL", "-sSL", "-sSfL",
            "--fail", "--silent", "--show-error", "--location",
        }
        options = argv[1:-1]
        index = 0
        while index < len(options):
            item = options[index]
            if item in allowed:
                index += 1
                continue
            if re.fullmatch(r"-[fsSL]+", item):
                index += 1
                continue
            if item in {"-m", "--max-time", "--connect-timeout"}:
                if index + 1 >= len(options):
                    return False
                value = options[index + 1]
                if not value.isdigit() or not 1 <= int(value) <= 120:
                    return False
                index += 2
                continue
            return False
        return True
    if argv[0] == "wget":
        options = argv[1:-1]
        return options in (
            ["-qO-"],
            ["-O", "-"],
            ["-q", "-O", "-"],
            ["--output-document=-"],
            ["--quiet", "--output-document=-"],
        )
    return False


def raw_guide_tool_discovery(value: dict) -> bool:
    payload = value.get("input")
    return (
        str(value.get("name") or "").lower() == "toolsearch"
        and isinstance(payload, dict)
        and payload.get("query") == "select:WebFetch"
        and set(payload) <= {"query", "max_results"}
    )


def safe_raw_guide_bootstrap(calls: list[dict]) -> bool:
    return (
        not calls
        or (len(calls) == 1 and raw_guide_fetch(calls[0]))
        or (
            len(calls) == 2
            and (
                (
                    raw_guide_tool_discovery(calls[0])
                    and raw_guide_fetch(calls[1])
                )
                or (
                    raw_guide_fetch(calls[0])
                    and raw_guide_tool_discovery(calls[1])
                )
            )
        )
    )


def ignore_questions(result: str, russian: bool | None) -> list[str]:
    """The question sentences in a turn that ask about ignoring a file.

    Prose that mentions an ignore file is not the defect; a question is, and a
    turn that explains what it did should not be red for saying so. Three
    things this got wrong and now does not: `\bignor` does not match inside
    `.gitignore`, because the word boundary falls after `git`; "add it to the
    project's exclude list" is the same question without the word "ignore" in
    it; and a question does not have to be the last character of its sentence —
    `(should I add it to .gitignore instead?)` ends with a bracket. `None` asks
    in both languages, for the cell whose answer is that no such question was
    asked in any language.
    """
    english = r"\bignor\w*|\bexclu\w*|\.gitignore"
    russian_terms = r"игнор|исключ|\.gitignore"
    if russian is None:
        asking = english + "|" + russian_terms
    else:
        asking = russian_terms if russian else english
    return [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", result)
        if "?" in sentence and re.search(asking, sentence.lower())
    ]


def operator_state_reads(calls: list[dict]) -> list[str]:
    """Tool calls in this turn that reach for the operator's own session state.

    Not a proof of safety — a tripwire. The stand and access turns already
    bound what may happen inside them; these turns bounded nothing, so a run
    could ask the ignore question and read `~/.claude/.credentials.json` in the
    same breath and come back green.
    """
    found = []
    for call in calls:
        serialized = json.dumps(call.get("input"), ensure_ascii=False).lower()
        for needle in OPERATOR_STATE:
            if needle in serialized:
                found.append(needle)
        if "kubectl" in serialized and "secret" in serialized:
            found.append("kubectl secrets")
    return found


def _names_path(command: str, tail: str, *, filename: bool) -> str:
    """Regex for a shell token that is this ignore file.

    `filename` distinguishes `.gitignore` from `templates/node.gitignore`: the
    first is the file, the second is a template that happens to end the same
    way, and flagging it was a false alarm on work that has nothing to do with
    this.
    """
    quoted = re.escape(tail)
    return (r"(?<![\w.-])" + quoted) if filename else (r"[^\s'\";|&]*" + quoted)


def ignore_writes(calls: list[dict]) -> list[tuple[dict, str]]:
    """Tool calls that would change an ignore file, and which file they change.

    Reading one is legitimate — a run has to know whether a rule already covers
    the override. Writing one is the decision #78 is about, so only writes
    count, and the team's file and this machine's file are reported apart.

    What this deliberately does not model: `core.excludesFile` and
    `~/.config/git/ignore`, a third ignore file that is neither the team's nor
    this repository's. A run that puts the rule there is not caught here.
    """
    targets = ((EXCLUDE, "exclude", False), (GITIGNORE, "gitignore", True))
    found: list[tuple[dict, str]] = []
    for call in calls:
        payload = call.get("input")
        if not isinstance(payload, dict):
            continue
        name = str(call.get("name") or "").lower()
        if name in {"write", "edit", "multiedit", "notebookedit"}:
            destination = str(
                payload.get("file_path")
                or payload.get("path")
                or payload.get("notebook_path")
                or ""
            )
            if destination.endswith(EXCLUDE):
                found.append((call, "exclude"))
            elif pathlib.PurePosixPath(destination).name == GITIGNORE:
                found.append((call, "gitignore"))
            continue
        if name != "bash":
            continue
        command = payload.get("command")
        if not isinstance(command, str):
            continue
        tokens = command.split()
        for tail, label, filename in targets:
            path = _names_path(command, tail, filename=filename)
            # Anything but a pipeline separator may sit between the redirect
            # and the path, because the path a run should actually use is
            # `"$(git rev-parse --git-dir)/info/exclude"` — the literal
            # `.git/info/exclude` does not exist in a linked worktree or a
            # submodule, where `.git` is a file. Requiring an unbroken token
            # after `>>` missed exactly the correct spelling.
            redirected = re.search(rf"(?:>>?\|?|>\|)[^|;&]*{path}", command)
            through_a_verb = re.search(
                rf"\b(?:tee|install|touch|sed\s+-i\S*|perl\s+-\S*i\S*|ed|ex|dd)\b"
                rf"[^|;&]*{path}",
                command,
            )
            in_python = re.search(
                rf"open\(\s*['\"]{path}['\"]\s*,\s*['\"][aw]", command
            )
            # `cp`/`mv` only when the file is the destination: copying it out to
            # a backup is a read, and reddening that would be noise.
            copied_onto = bool(
                re.match(r"\s*(?:sudo\s+)?(?:cp|mv|install)\b", command)
                and tokens
                and re.search(rf"^['\"]?{path}['\"]?$", tokens[-1])
            )
            if redirected or through_a_verb or in_python or copied_onto:
                found.append((call, label))
                break
    return found


def pure_python_helper_argv(command: object) -> list[str] | None:
    if not isinstance(command, str):
        return None
    if re.search(r"[;#|&<>\n\r`]", command) or "$(" in command:
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if (
        len(argv) < 2
        or argv[0] != "python3"
        or pathlib.PurePosixPath(argv[1]).name != "gopnik_setup.py"
    ):
        return None
    return argv


def helper_records_stage1(items: list[object]) -> bool:
    """Whether any call already committed a Stage 1 command to the record.

    The coverage question is owed *before* anything is recorded, so this is how
    that ordering is proven from outside the prose: a run that asks the question
    and has already written Stage 1 asked it too late to matter.

    This deliberately does not go through `pure_python_helper_argv`. That parser
    refuses any command containing `&&`, which made `cd repo && python3
    gopnik_setup.py --stage1 …` invisible — the exact bypass this check exists
    to catch, and one a run reaches by writing the most ordinary shell there is.
    Recognising one command shape is not an ordering proof. `--check` is
    excluded for the opposite reason: SKILL.md documents it as a dry run that
    writes nothing, so rejecting it would fail a run for looking before it
    recorded.
    """
    for item in items:
        for value in nested_dicts(item):
            if value.get("type") != "tool_use":
                continue
            name = str(value.get("name") or "").lower()
            blob = json.dumps(value.get("input"), ensure_ascii=False)
            if name == "bash":
                if (
                    "gopnik_setup.py" in blob
                    and "--stage1" in blob
                    and "--check" not in blob
                ):
                    return True
            elif name in ("write", "edit", "multiedit", "notebookedit"):
                # Writing the file by hand records Stage 1 just as effectively.
                if "gopnik.json" in blob and "stage1" in blob:
                    return True
    return False


def stage1_events(
    items: list[object], expected_language: str, stage1: list[str]
) -> list[tuple[int, str]]:
    found = []
    for index, item in enumerate(items):
        for value in nested_dicts(item):
            if value.get("type") != "tool_use":
                continue
            name = str(value.get("name") or "").lower()
            payload = value.get("input")
            command = payload.get("command") if isinstance(payload, dict) else None
            argv = pure_python_helper_argv(command)
            if argv is None:
                continue
            flags: dict[str, str | bool] = {}
            recorded: list[str] = []
            cursor = 2
            valid = True
            while cursor < len(argv):
                option = argv[cursor]
                if option == "--defer-artifact-kind":
                    if option in flags:
                        valid = False
                        break
                    flags[option] = True
                    cursor += 1
                    continue
                if option == "--stage1":
                    if cursor + 1 >= len(argv):
                        valid = False
                        break
                    recorded.append(argv[cursor + 1])
                    cursor += 2
                    continue
                if option in {"--language", "--timeout-seconds"}:
                    if option in flags or cursor + 1 >= len(argv):
                        valid = False
                        break
                    flags[option] = argv[cursor + 1]
                    cursor += 2
                    continue
                valid = False
                break
            if (
                name == "bash"
                and valid
                and flags.get("--defer-artifact-kind") is True
                and flags.get("--language") == expected_language
                and recorded == list(stage1)
                and flags.get("--timeout-seconds", "120") == "120"
                and set(flags) <= {
                    "--defer-artifact-kind",
                    "--language",
                    "--timeout-seconds",
                }
                and isinstance(value.get("id"), str)
            ):
                found.append((index, value["id"]))
    return found


def confirmation_events(
    items: list[object], kind: str, surfaces: list[str]
) -> list[tuple[int, str]]:
    """Confirmations that record the kind *and* the surfaces behind it.

    #77: `artifact_kind` is one word for the farthest boundary, and the
    critic's surviving set was used to phrase one question and then dropped.
    A confirmation that does not carry a set leaves the rule "Stage 2 covers
    every confirmed surface" with no data and no reader, so this oracle does
    not count it as a confirmation.

    What it compares against is the fixture's own `surfaces`: the answer a
    truthful person gives about that project. A person confirming a real
    project may narrow the critic's set, and the helper records whatever it is
    handed — the fixture is simply the case where the right answer is known
    before the run. The comparison goes through the same canonicaliser as the
    question, or a critic's `web-ui` would be accepted in one place and
    rejected in the other.
    """
    wanted = {canonical_surface(name) for name in surfaces}
    found = []
    for index, item in enumerate(items):
        for value in nested_dicts(item):
            if value.get("type") != "tool_use":
                continue
            name = str(value.get("name") or "").lower()
            payload = value.get("input")
            command = payload.get("command") if isinstance(payload, dict) else None
            argv = pure_python_helper_argv(command)
            if (
                name != "bash"
                or argv is None
                or len(argv) != 6
                or argv[2:5] != ["--confirm-artifact-kind", kind, "--surfaces"]
                or not isinstance(value.get("id"), str)
            ):
                continue
            spelled = [part.strip() for part in argv[5].split(",") if part.strip()]
            # Length first: a set comparison alone accepts an inflated list,
            # because `command, cli, command-line` collapses onto one surface
            # and looks like agreement with a set of one.
            if len(spelled) != len(wanted):
                continue
            if not all(known_surface_spelling(name) for name in spelled):
                continue
            if {canonical_surface(name) for name in spelled} == wanted:
                found.append((index, value["id"]))
    return found


def critic_agent_events(items: list[object]) -> list[tuple[int, str]]:
    found = []
    for index, item in enumerate(items):
        for value in nested_dicts(item):
            if value.get("type") != "tool_use":
                continue
            name = str(value.get("name") or "").lower()
            payload = value.get("input")
            serialized = json.dumps(payload, ensure_ascii=False).lower()
            if (
                name in ("agent", "task")
                and "gopnik-critic" in serialized
                and CRITIC_COMPLETE_MARKER.lower() in serialized
                and CRITIC_BLOCKED_MARKER.lower() in serialized
                and CRITIC_SURFACES_MARKER.lower() in serialized
                and isinstance(value.get("id"), str)
            ):
                found.append((index, value["id"]))
    return found


def successful_result(value: dict, required: str | None = None) -> bool:
    if value.get("is_error") is True:
        return False
    payload = value.get("content")
    if payload in (None, "", [], {}):
        return False
    content = json.dumps(payload, ensure_ascii=False).lower()
    return (
        required is None or required.lower() in content
    )


#: One entry per surface a project can have, with how each is worded. The rule
#: that reads it is "never name a surface the critic refuted"; which surfaces
#: survived is a fact about the fixture, so the two are combined rather than
#: written out as one list. Before #73 this was a fixed denylist, which was only
#: correct for the one fixture that existed: it banned `library` and `migration`
#: outright, so a project whose real surface is a library could not be checked.
SURFACE_TERMS = {
    "command": (r"command\w*|command-line|cli", r"команд\w*|cli"),
    "web": (r"web interface|web ui|web page|dashboard", r"веб-\w*|дашборд\w*"),
    "migration": (r"migration\w*", r"миграц\w*"),
    "package": (r"package\w*", r"пакет\w*"),
    "library": (r"librar\w*", r"библиотек\w*"),
    "plugin": (r"plugin\w*", r"плагин\w*"),
    "service": (r"service\w*|api|http", r"сервис\w*|api|http"),
    "mobile": (r"mobile\w*", r"мобильн\w*"),
    "job": (r"background\w*|job\w*", r"фонов\w*|задач\w*"),
    "chart": (r"chart\w*", r"чарт\w*"),
    "release": (r"release\w*|deploy\w*", r"релиз\w*|разв[её]рт\w*"),
}

#: The spellings a critic may use for the same surface.
SURFACE_ALIASES = {
    "command-line": "command",
    "cli": "command",
    "web-ui": "web",
    "web-interface": "web",
    "dashboard": "web",
    "ui": "web",
    "mobile-ui": "mobile",
}


def canonical_surface(name: str) -> str:
    """The identifier a critic meant, whichever spelling it reached for.

    A live run returned `web-dashboard, cli` for the pair this fixture calls
    `web, command`. `cli` was already an alias; `web-dashboard` was not, and the
    turn was rejected for vocabulary rather than for anything it did. Compound
    spellings are common precisely because a critic describes what it found, so
    a name that is not itself an alias is retried part by part before being
    taken literally.
    """
    name = name.strip().lower().replace("_", "-")
    if name in SURFACE_ALIASES:
        return SURFACE_ALIASES[name]
    if name in SURFACE_TERMS:
        return name
    for part in name.split("-"):
        if part in SURFACE_ALIASES:
            return SURFACE_ALIASES[part]
        if part in SURFACE_TERMS:
            return part
    return name


def known_surface_spelling(name: str) -> bool:
    """Is this a spelling of a surface, rather than a word wrapped around one?

    `canonical_surface` answers "which surface does this look like", and answers
    it generously on purpose: a critic writing `web-ui` must not be misread. Read
    as a membership test that generosity is a hole — it splits on `-` and returns
    the first part it recognises, so `refuted-command` and `no-command` both
    canonicalise to `command`. A confirmation naming nothing that survived then
    passes for one that named everything.

    Exact spellings first, so every alias the table already blesses keeps
    working; otherwise every hyphen part has to be a spelling in its own right.
    """
    lowered = name.strip().lower()
    if not lowered:
        return False
    if lowered in SURFACE_TERMS or lowered in SURFACE_ALIASES:
        return True
    parts = lowered.split("-")
    return len(parts) > 1 and all(
        part in SURFACE_TERMS or part in SURFACE_ALIASES for part in parts
    )


def refuted_surface_shape(surfaces: set[str], russian: bool) -> str:
    """Every surface this fixture does not have, as one alternation."""
    survived = {canonical_surface(name) for name in surfaces}
    terms = [
        pair[1 if russian else 0]
        for name, pair in SURFACE_TERMS.items()
        if name not in survived
    ]
    return r"\b(?:" + "|".join(terms) + r")\b"


def candidate_is_named(candidate: str, result: str, russian: bool) -> bool:
    # Through the same canonicaliser as the set comparison, or a critic's
    # `web-dashboard` is accepted as a surface and then not recognised in the
    # question that names it `the dashboard`.
    candidate = canonical_surface(candidate)
    patterns = {
        "command": r"\b(?:command|command-line|cli)\b" if not russian else r"\b(?:команд\w*|cli)\b",
        "command-line": r"\b(?:command|command-line|cli)\b" if not russian else r"\b(?:команд\w*|cli)\b",
        "cli": r"\b(?:command|command-line|cli)\b" if not russian else r"\b(?:команд\w*|cli)\b",
        "web": r"\b(?:web interface|web ui|web page|dashboard)\b" if not russian else r"\b(?:веб-(?:интерфейс|страниц)\w*|интерфейс\w*|web ui|dashboard)\b",
        "web-ui": r"\b(?:web interface|web ui|web page|dashboard)\b" if not russian else r"\b(?:веб-(?:интерфейс|страниц)\w*|интерфейс\w*|web ui|dashboard)\b",
        "web-interface": r"\b(?:web interface|web ui|web page|dashboard)\b" if not russian else r"\b(?:веб-(?:интерфейс|страниц)\w*|интерфейс\w*|web ui|dashboard)\b",
        "dashboard": r"\b(?:web interface|web ui|web page|dashboard)\b" if not russian else r"\b(?:веб-(?:интерфейс|страниц)\w*|интерфейс\w*|web ui|dashboard)\b",
        "ui": r"\b(?:web interface|web ui|web page|dashboard|ui)\b" if not russian else r"\b(?:веб-(?:интерфейс|страниц)\w*|интерфейс\w*|web ui|dashboard|ui)\b",
        "migration": r"\bmigration\w*\b" if not russian else r"\bмиграц\w*\b",
        "package": r"\bpackage\w*\b" if not russian else r"\bпакет\w*\b",
        "library": r"\blibrar\w*\b" if not russian else r"\bбиблиотек\w*\b",
        "plugin": r"\bplugin\w*\b" if not russian else r"\bплагин\w*\b",
        "service": r"\bservice\w*\b" if not russian else r"\bсервис\w*\b",
        "api": r"\bapi\b",
        "mobile-ui": r"\bmobile\b" if not russian else r"\bмобильн\w*\b",
        "job": r"\b(?:job|background)\b" if not russian else r"\b(?:задач\w*|фонов\w*)\b",
        "chart": r"\bchart\w*\b" if not russian else r"\bчарт\w*\b",
        "release": r"\brelease\w*\b" if not russian else r"\bрелиз\w*\b",
    }
    pattern = patterns.get(candidate)
    if pattern is not None:
        return re.search(pattern, result.lower()) is not None
    return candidate.replace("-", " ") in result.lower()


def completed_fixture_critic_result(
    value: dict, result: str, russian: bool, expected: set[str]
) -> bool:
    if not successful_result(value):
        return False
    payload = value.get("content")
    if isinstance(payload, str):
        primary = payload
    elif (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], dict)
        and payload[0].get("type") == "text"
        and isinstance(payload[0].get("text"), str)
    ):
        primary = payload[0]["text"]
    else:
        return False
    lines = [
        line.strip()
        for line in primary.splitlines()
        if line.strip()
    ]
    if len(lines) < 2 or lines[-1] != CRITIC_COMPLETE_MARKER:
        return False
    if not lines[-2].startswith(CRITIC_SURFACES_MARKER):
        return False
    if any(line.startswith(CRITIC_SURFACES_MARKER) for line in lines[:-2]):
        return False
    surfaces = lines[-2][len(CRITIC_SURFACES_MARKER):].strip().lower()
    candidates = {item.strip() for item in surfaces.split(",") if item.strip()}
    canonical = {canonical_surface(candidate) for candidate in candidates}
    if canonical != {canonical_surface(name) for name in expected}:
        return False
    if not result.endswith("?"):
        return False
    question = re.split(r"(?<=[.!?])\s+", result)[-1]
    return all(
        candidate_is_named(candidate, question, russian) for candidate in candidates
    )


def main(argv: list[str]) -> int:
    argv = list(argv)
    fixture_dir = DEFAULT_FIXTURE
    if "--fixture" in argv:
        at = argv.index("--fixture")
        if at + 1 >= len(argv):
            return fail("--fixture needs a directory")
        fixture_dir = pathlib.Path(argv[at + 1])
        del argv[at : at + 2]

    if len(argv) not in (3, 4):
        return fail(
            "usage: check_live_setup_turn.py [--fixture DIR] "
            "LANGUAGE|SCOPE|COVERAGE|SURFACES|STAND|ACCESS|OVERRIDE|"
            "OVERRIDE-APPLIED|OVERRIDE-DECLINED|OVERRIDE-USER|OVERRIDE-NONE "
            "and -RU variants "
            "TRANSCRIPT [STAGE1_MARKER]"
        )

    try:
        fixture = expectations(fixture_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail(str(exc))

    mode = argv[1].lower()
    path = pathlib.Path(argv[2])
    try:
        items = records(path)
        result_index, result = final_result(items)
    except (OSError, ValueError) as exc:
        return fail(str(exc))

    if mode == "language":
        if result != LANGUAGE_QUESTION:
            return fail(result)
        if not safe_raw_guide_bootstrap(tool_uses(items)):
            return fail("activity beyond reading the raw guide occurred before the language question")
        return 0

    if mode == "scope":
        if not safe_raw_guide_bootstrap(tool_uses(items)):
            return fail("activity beyond reading the raw guide occurred before the installation-scope answer")
        return 0 if result == SCOPE_QUESTION else fail(result)

    if mode == "scope-ru":
        if not safe_raw_guide_bootstrap(tool_uses(items)):
            return fail("activity beyond reading the raw guide occurred before the Russian installation-scope answer")
        return 0 if result == SCOPE_QUESTION_RU else fail(result)

    lower = result.lower()
    if mode in ("coverage", "coverage-ru"):
        russian = mode.endswith("-ru")
        gap = fixture.get("gap")
        if gap is None:
            return fail("this fixture declares no Stage 1 gap to ask about")
        # Order is the whole point. A run that asks about the gap after writing
        # Stage 1 has produced the same short configuration and a question that
        # cannot change it, which is the defect wearing the fix as a costume.
        if helper_records_stage1(items):
            return fail("Stage 1 was recorded before the coverage question was asked")
        orientation = assistant_text_before(items, len(items)).lower()
        stages = [orientation.find(label) for label in ("stage 0", "stage 1", "stage 2")]
        if any(index < 0 for index in stages) or stages != sorted(stages):
            return fail("the three-stage orientation is absent or out of order")
        bounded = (
            "после" in orientation
            if russian
            else bool(re.search(
                r"\b(?:after stage 1|only (?:once|when) stage 1 "
                r"(?:works|passes|is ready))\b",
                orientation,
            ))
        )
        if orientation.count("stage 2") != 1 or not bounded:
            return fail("Stage 2 was not bounded behind Stage 1")
        if not one_question(result):
            return fail("the coverage turn must contain exactly one question")
        if not result.endswith("?"):
            return fail("the coverage turn must end with its hard-boundary question")
        # The question itself, not the paragraph around it. Naming the suite in
        # the prose and then asking something else — "shall I continue?", the
        # Stage 2 stand question, anything — satisfied an earlier version of
        # this and is how a run turns a hard boundary into filler.
        question = re.split(r"(?<=[.!?])\s+", result)[-1].lower()
        for needle in gap["named"]:
            if needle.lower() not in lower:
                return fail(f"the coverage turn does not name {needle}")
        asking = (
            r"\b(?:запуска|запусти|включ|добав)\w*"
            if russian
            else r"\b(?:run|runs|include|add)\b"
        )
        if not re.search(asking, question):
            return fail("the coverage question does not ask about running the check")
        if "stage 1" not in question:
            return fail("the coverage question is not about what Stage 1 will run")
        replacing = (
            r"\b(?:вместо|заменит|замени|подменит|отказат)\w*"
            if russian
            else r"\b(?:instead of|rather than|replace|replacing|in place of)\b"
        )
        if re.search(replacing, question):
            return fail("the coverage question proposes replacing the documented command")
        banned_terms = ["gopnik.json", "artifact_kind"] + list(
            fixture["internal_details"]["ru" if russian else "en"]
        )
        for banned in banned_terms:
            if banned in lower:
                return fail(f"internal defect detail leaked: {banned}")
        if len(result.split()) > 140:
            return fail("the coverage turn is too long")
        if russian:
            letters = [character for character in result if character.isalpha()]
            cyrillic = [
                character
                for character in letters
                if ("а" <= character.lower() <= "я") or character.lower() == "ё"
            ]
            if not letters or len(cyrillic) / len(letters) < 0.65:
                return fail("the Russian turn contains too much non-Russian prose")
        return 0

    if mode in ("surfaces", "surfaces-ru"):
        russian = mode.endswith("-ru")
        if len(argv) != 4:
            return fail("Stage 1 marker is absent")
        try:
            marker = pathlib.Path(argv[3]).read_text(encoding="utf-8")
        except OSError:
            return fail("Stage 1 marker is absent")
        if marker != fixture["marker"]["value"]:
            return fail("Stage 1 marker has the wrong value")
        stage1_calls = stage1_events(
            items, "ru" if russian else "en", fixture["stage1"]
        )
        if not stage1_calls:
            return fail("the live trace does not show the Stage 1 setup command")
        stage1_call_index, stage1_id = stage1_calls[0]
        # A fixture with a gap owes the orientation to its coverage turn, which
        # runs before this one. Demanding it again here would require the run to
        # repeat itself, and repeating it is what the skill forbids.
        if fixture.get("gap") is None:
            orientation = assistant_text_before(items, stage1_call_index).lower()
            stages = [orientation.find(label) for label in ("stage 0", "stage 1", "stage 2")]
            if any(index < 0 for index in stages) or stages != sorted(stages):
                return fail("the three-stage orientation is absent or out of order")
            bounded = (
                "после" in orientation
                if russian
                else bool(re.search(
                    r"\b(?:after stage 1|only (?:once|when) stage 1 "
                    r"(?:works|passes|is ready))\b",
                    orientation,
                ))
            )
            if orientation.count("stage 2") != 1 or not bounded:
                return fail("Stage 2 was not bounded behind Stage 1")
        stage1_results = [
            (index, value)
            for index, value in tool_results(items, stage1_id)
            if successful_result(
                value, "Stage 1 set up. Delivery surfaces still need confirmation."
            )
        ]
        if not stage1_results:
            return fail("the Stage 1 helper has no successful result")
        stage1_result_index = stage1_results[0][0]

        critic_calls = critic_agent_events(items)
        if not critic_calls:
            return fail("the live trace does not show an independent gopnik-critic agent")
        critic_call_index, critic_id = critic_calls[0]
        critic_results = [
            (index, value)
            for index, value in tool_results(items, critic_id)
            if completed_fixture_critic_result(
                value, result, russian, set(fixture["surfaces"])
            )
        ]
        if not critic_results:
            return fail("the independent critic has no completed surface analysis")
        critic_result_index = critic_results[0][0]
        if not (
            stage1_call_index
            < stage1_result_index
            < critic_call_index
            < critic_result_index
            < result_index
        ):
            return fail("Stage 1, independent critic, and user question are out of order")
        # The first two are internal vocabulary and belong to the product;
        # the rest are defects of this particular tree and belong to it.
        banned_terms = ["gopnik.json", "artifact_kind"] + list(
            fixture["internal_details"]["ru" if russian else "en"]
        )
        for banned in banned_terms:
            if banned in lower:
                return fail(f"internal defect detail leaked: {banned}")
        status_text = (
            assistant_text_between(items, stage1_result_index, critic_call_index)
            + " "
            + result
        ).strip().lower()
        green = (
            re.search(r"(?:^|[.!?]\s+)stage 1 (?:готова|прошла)\s*(?:[.!?:—–-]|$)", status_text)
            if russian
            else re.search(r"(?:^|[.!?]\s+)stage 1 (?:passed|passes|is ready)\s*(?:[.!?:—–-]|$)", status_text)
        )
        if not green:
            return fail("the response does not report the green Stage 1 result")
        # SKILL.md fixes the wording for two plausible surfaces. A fixture with
        # a different count needs its own rule from the skill, not a guess here.
        if len(fixture["surfaces"]) != 2:
            return fail(
                f"no question shape is defined for {len(fixture['surfaces'])} surfaces"
            )
        question_shape = (
            r"только .+только .+или оба"
            if russian
            else r"only .+only .+(?:or )?both"
        )
        if not re.search(question_shape, lower):
            return fail("the response does not ask one concrete surfaces question")
        for candidate in fixture["surfaces"]:
            if not candidate_is_named(candidate, result, russian):
                return fail(f"the fixture's {candidate} surface is absent")
        if not one_question(result):
            return fail("the surfaces turn must contain exactly one question")
        if not result.endswith("?"):
            return fail("the surfaces turn must end with its hard-boundary question")
        question = re.split(r"(?<=[.!?])\s+", result)[-1]
        expected_opening = "После поставки " if russian else "After delivery, "
        if not question.startswith(expected_opening):
            return fail("the surfaces question does not start at the delivery boundary")
        forbidden_question_terms = (
            r"\b(?:не|без|кроме|исключая|исключить)\b"
            if russian
            else r"\b(?:not|no|without|except|excluding|other than|inverse)\b"
        )
        if re.search(forbidden_question_terms, question.lower()):
            return fail("the surfaces question negates or excludes a surviving candidate")
        if re.search(refuted_surface_shape(set(fixture["surfaces"]), russian), lower):
            return fail("a non-surviving fixture surface leaked into the user turn")
        if len(result.split()) > 140:
            return fail("the surfaces turn is too long")
        if russian:
            letters = [character for character in result if character.isalpha()]
            cyrillic = [
                character
                for character in letters
                if ("а" <= character.lower() <= "я") or character.lower() == "ё"
            ]
            if not letters or len(cyrillic) / len(letters) < 0.65:
                return fail("the Russian turn contains too much non-Russian prose")
            for english in ("here is", "checks the", "after delivery", "i found"):
                if english in lower:
                    return fail(f"English onboarding leaked into the Russian turn: {english}")
        return 0

    if mode in (
        "override",
        "override-ru",
        "override-applied",
        "override-declined",
        "override-declined-ru",
        "override-user",
        "override-user-ru",
        "override-none",
    ):
        russian = mode.endswith("-ru")
        calls = tool_uses(items)
        borrowed = operator_state_reads(calls)
        if borrowed:
            return fail(
                "the turn reached for the operator's own session state: "
                + ", ".join(sorted(set(borrowed)))
            )
        writes = ignore_writes(calls)
        wrote = {label for _, label in writes}
        # A run that needs no override must produce neither the question nor
        # the file. Spelled once for both languages: the two paths are the same
        # string in every locale, and this cell is about their absence.
        if mode == "override-none":
            if writes:
                return fail("an ignore rule was written for a run that needs no override")
            if ignore_questions(result, None):
                return fail("a run needing no override still raised the ignore question")
            return 0

        # The control, and half of the oracle. A personal override belongs in a
        # file only this machine has; a run that asks about `.gitignore` here
        # has moved the defect rather than fixed it.
        if mode.startswith("override-user"):
            if ignore_questions(result, russian):
                return fail("the user-scope turn asked about ignoring the override")
            if "gitignore" in wrote:
                return fail("a personal override was ignored in a tracked project file")
            if "exclude" not in wrote:
                return fail("the user-scope run did not ignore its override at all")
            return 0

        # Repository scope. The rule has to reach a file the team receives, and
        # that file is tracked, so the question comes first — before any write,
        # or the question is decoration on a decision already taken.
        # The turn after the person agrees, and the cell the first version of
        # this could not express: asking the question proves nothing about
        # where the rule then went, and the whole defect is a rule that went to
        # a file nobody else receives.
        if mode == "override-applied":
            if "gitignore" not in wrote:
                return fail(
                    "the ignore rule did not reach a file the repository carries"
                )
            return 0

        # The other branch of the same turn. A decline is a limitation to
        # report, not a silent fall back: the override still has to be ignored
        # here, and the person has to be told the protection stops at this
        # machine.
        if mode.startswith("override-declined"):
            if "gitignore" in wrote:
                return fail("the tracked ignore file was edited after a decline")
            if "exclude" not in wrote:
                return fail("the declined run left its override ignored by nothing")
            said = (assistant_text_before(items, len(items)) + " " + result).lower()
            named = (
                re.search(r"эт(?:у|ой|ой же)?\s*машин", said)
                if russian
                else re.search(r"\bthis machine\b", said)
            )
            if not named:
                return fail("the decline was not reported as a machine-local limitation")
            return 0

        expected_override = OVERRIDE_QUESTION_RU if russian else OVERRIDE_QUESTION
        if result != expected_override:
            return fail("the repository-scope turn is not the one exact ignore question")
        if wrote:
            return fail(
                "an ignore rule was written before the question was asked: "
                + ", ".join(sorted(wrote))
            )
        return 0

    if mode == "stand":
        expected_stand = STAND_RESPONSE
    elif mode == "stand-ru":
        expected_stand = STAND_RESPONSE_RU
    else:
        expected_stand = None

    if expected_stand is not None:
        if result != expected_stand:
            return fail("the stand turn is not the one focused question")
        if len(tool_uses(items)) != 1:
            return fail("the stand turn contains tool activity beyond kind confirmation")
        calls = confirmation_events(
            items, fixture["artifact_kind"], fixture["surfaces"]
        )
        if len(calls) != 1:
            return fail(
                "the stand turn does not show one exact confirmation of the kind "
                "and the confirmed surfaces"
            )
        call_index, tool_id = calls[0]
        completed = [
            (index, value)
            for index, value in tool_results(items, tool_id)
            if successful_result(
                value,
                f"Confirmed artifact kind '{fixture['artifact_kind']}' in "
                "gopnik.json. Stage 1 checks were preserved and not rerun.",
            )
        ]
        if len(completed) != 1 or not (call_index < completed[0][0] < result_index):
            return fail("artifact-kind confirmation did not complete before the stand question")
        return 0

    if mode == "access":
        if tool_uses(items):
            return fail("tool activity occurred before the delivery/access answer")
        return 0 if result == ACCESS_QUESTION else fail(
            "the delivery/access turn is not the safe focused question"
        )

    if mode == "access-ru":
        if tool_uses(items):
            return fail("tool activity occurred before the Russian delivery/access answer")
        return 0 if result == ACCESS_QUESTION_RU else fail(
            "the Russian delivery/access turn is not the safe focused question"
        )

    return fail(f"unknown mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
