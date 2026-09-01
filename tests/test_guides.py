#!/usr/bin/env python3
"""Contract tests for the agent-led installation and removal guides."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALL = ROOT / "docs" / "install.md"
UNINSTALL = ROOT / "docs" / "uninstall.md"
README = ROOT / "README.md"
README_RU = ROOT / "README.ru.md"
SETUP_SKILLS = (
    ROOT / "plugins" / "gopnik" / "skills" / "gopnik-setup" / "SKILL.md",
    ROOT / "plugins" / "gopnik" / "skills" / "gopnik-setup" / "SKILL.ru.md",
)
RUNNER_SKILLS = (
    ROOT / "plugins" / "gopnik" / "skills" / "gopnik" / "SKILL.md",
    ROOT / "plugins" / "gopnik" / "skills" / "gopnik" / "SKILL.ru.md",
)
LANGUAGE_QUESTION = "Which language would you like me to use: English or Russian?"


def _flat(path: pathlib.Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_readme_urls_resolve_to_the_guides_in_this_tree():
    for page in (README, README_RU):
        text = page.read_text(encoding="utf-8")
        urls = re.findall(
            r"https://raw\.githubusercontent\.com/madduck-tech/gopnik/main/(docs/(?:install|uninstall)\.md)",
            text,
        )
        assert urls == ["docs/install.md", "docs/uninstall.md"], (page.name, urls)
        for relative in urls:
            assert (ROOT / relative).is_file(), f"{page.name}: missing {relative}"


def test_install_opens_with_the_exact_english_language_question():
    text = INSTALL.read_text(encoding="utf-8")
    first_step = text[: text.index("## 2.")]
    assert "always ask this exact question in English" in first_step
    assert first_step.count(LANGUAGE_QUESTION) == 1
    assert "response must end after that question" in first_step
    assert "Unless" not in first_step


def test_install_asks_for_scope_immediately_after_language():
    text = _flat(INSTALL)
    phrases = (
        "Immediately after the language answer",
        "Where should I install Gopnik: for this agent across your projects, or only in this repository",
        "Куда установить Gopnik: для этого агента во всех ваших проектах или только в этот репозиторий",
        "question is a hard turn boundary",
        "Do not call the first option `global`",
        "Install in exactly the selected scope, never both",
        "does not belong in project verification data",
        "first visible response after the installation-scope answer",
    )
    for phrase in phrases:
        assert phrase in text, phrase
    language = text.index(LANGUAGE_QUESTION)
    scope = text.index("Where should I install Gopnik")
    orient = text.index("**Stage 0** decides")
    install = text.index("claude plugin marketplace add")
    assert language < scope < orient < install
    assert "first visible response after the language answer" not in text


def test_uninstall_reuses_the_saved_language_without_asking_again():
    text = _flat(UNINSTALL)
    assert LANGUAGE_QUESTION not in text
    for phrase in (
        "top-level `language` is `ru`",
        "English when it is `en`",
        "language of the current conversation",
        "Never ask a dedicated language question during uninstall",
    ):
        assert phrase in text, phrase


def test_install_is_agent_agnostic_and_brings_the_complete_bundle():
    text = _flat(INSTALL)
    for skill in ("`gopnik`", "`gopnik-critic`", "`gopnik-setup`"):
        assert skill in text, skill
    for route in (
        "claude plugin marketplace update madduck-tech",
        "claude plugin install gopnik@madduck-tech",
        "claude plugin update gopnik@madduck-tech",
        "codex plugin marketplace upgrade madduck-tech",
        "codex plugin add gopnik@madduck-tech",
        "Any other agent",
        "install.sh | sh",
        "agent-wide installation",
        "repository installation",
        "Do not silently fall back to the other scope",
    ):
        assert route in text, route
    assert "Do not install them one at a time" not in text


def test_install_refreshes_an_existing_plugin_instead_of_accepting_stale_presence():
    text = _flat(INSTALL)
    for phrase in (
        "existing installation is not proof that it is current",
        "reported version matches the current marketplace entry",
        "reading the newly installed files directly",
        "older cached copy",
    ):
        assert phrase in text, phrase


def test_install_reads_repository_rules_before_running_checks():
    text = _flat(INSTALL)
    for phrase in (
        "Do not ask the user for facts the repository already answers",
        "project-owned wrapper",
        "--stage1 './app.sh --smoke'",
        "--language en",
        "record only Stage 1 commands that actually passed",
        "Ask before a lengthy suite",
        "Do not inspect or discuss the Stage 2 route yet",
    ):
        assert phrase in text, phrase


def test_stage2_access_question_is_natural_and_matches_each_localized_skill():
    english = (
        "How does a new version get there, and how can the agent obtain access? "
        "Do not send secrets; just name the existing access method."
    )
    russian = (
        "Как новая версия попадает на стенд и как агенту получить к нему доступ? "
        "Секреты присылать не нужно — достаточно назвать существующий способ доступа."
    )
    install = _flat(INSTALL)
    assert english in install
    assert russian in install
    assert english in _flat(SETUP_SKILLS[0])
    assert russian in _flat(SETUP_SKILLS[1])


def test_stand_turn_explains_stage2_before_the_localized_question():
    english = (
        "Stage 2 checks the built or deployed result where people actually use it. "
        "Is there a test or staging environment where Gopnik can verify the deployed version?"
    )
    russian = (
        "Stage 2 проверяет собранный или развёрнутый результат там, где им реально пользуются. "
        "Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?"
    )
    install = _flat(INSTALL)
    assert english in install
    assert russian in install
    assert english in _flat(SETUP_SKILLS[0])
    assert russian in _flat(SETUP_SKILLS[1])


def test_surface_turn_names_the_green_stage1_status_before_the_question():
    for path, phrases in (
        (INSTALL, (
            "the brief stage orientation and Stage 1 status may precede it",
            "Stage 1 is ready — the project's local check passed.",
            "Stage 1 готова — штатная проверка проекта прошла.",
        )),
        (SETUP_SKILLS[0], (
            "the brief stage orientation and Stage 1 status may precede it",
            "Stage 1 is ready — the project's local check passed.",
        )),
        (SETUP_SKILLS[1], (
            "перед ними могут стоять краткое объяснение стадий и статус Stage 1",
            "Stage 1 готова — штатная проверка проекта прошла.",
        )),
    ):
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_kind_confirmation_is_one_exact_helper_call():
    for path, phrases in (
        (INSTALL, ("Invoke the setup helper exactly once", "do not probe `--help`", "repeat `--language`")),
        (SETUP_SKILLS[0], ("Invoke the setup helper exactly once", "do not probe `--help`", "repeat `--language`")),
        (SETUP_SKILLS[1], ("вызови setup-helper ровно один раз", "не проверяй `--help`", "не повторяй `--language`")),
    ):
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_surface_to_kind_mapping_is_complete_and_localized():
    expected = ("service", "cli", "library", "chart", "plugin", "migration", "model-boundary")
    for path, anchor in (
        (INSTALL, "without inspecting the helper or rediscovering its choices"),
        (SETUP_SKILLS[0], "without inspecting the helper or rediscovering its choices"),
        (SETUP_SKILLS[1], "не изучая helper и не выясняя его варианты заново"),
    ):
        text = _flat(path)
        assert anchor in text, (path.name, anchor)
        for kind in expected:
            assert f"`{kind}`" in text, (path.name, kind)
        assert "deployed web UI plus an installed command has primary kind `service`" in text or (
            "развёрнутого веб-интерфейса вместе с установленной командой основной тип — `service`" in text
        )


def test_install_persists_the_language_once_for_future_runs_and_uninstall():
    text = _flat(INSTALL)
    for phrase in (
        "`--language en` or `--language ru`",
        "selected once and retained",
        "Record the stable mechanics and selected language",
    ):
        assert phrase in text, phrase


def test_install_explains_stages_without_mislabeling_prerequisites():
    text = _flat(INSTALL)
    for phrase in (
        "**Stage 0** decides what could break",
        "**Stage 1** checks the code inside the repository",
        "**Stage 2** checks the built or deployed result",
        "This is what you will set up first",
        "Stage 2 prerequisite, not Stage 2 itself",
    ):
        assert phrase in text, phrase


def test_install_asks_about_a_stand_before_inferring_stage2():
    text = _flat(INSTALL)
    for phrase in (
        "do not infer and present its infrastructure first",
        "Is there a test or staging environment where Gopnik can verify the deployed version?",
        "Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?",
        "How does a new version get there, and how can the agent obtain access?",
        "Do not send secrets",
        "After the answer, inspect CI triggers",
        "trigger or observe delivery for the exact revision",
        "prove the running artifact is that revision",
        "prove the check can fail",
    ):
        assert phrase in text, phrase


def test_stage2_confirmation_is_a_hard_turn_boundary():
    text = _flat(INSTALL)
    for phrase in (
        "confirmation question is a hard turn boundary",
        "do not finalize the delivery kind",
        "draft or run Stage 2",
        "availability question is a hard turn boundary",
        "End the response with it and wait",
        "Then wait again",
        "before the person answers",
    ):
        assert phrase in text, phrase


def test_delivery_surfaces_are_criticized_then_confirmed_after_stage1():
    expected = {
        INSTALL: (
            "Only after Stage 1 passes, inspect the candidate delivery surfaces",
            "old configuration, previous conversation, and memory as leads, never as confirmation",
            "One binary can also run a service and UI",
            "deployment and release routes as evidence",
            "not as product-use choices of their own",
            "Require a concrete consumption boundary",
            "alone does not prove a service exists",
            "critic brief must carry the same product-facing boundary",
            "evidence, not a surviving surface",
            "Do not leave the critic to infer this split",
            "already is the independent adversary",
            "without spawning another agent",
            "Verify every load-bearing inclusion or exclusion",
            "do not silently edit the critic's set",
            "independent agent using `gopnik-critic`",
            "mandate to refute the classification",
            "`GOPNIK_CRITIC_STATUS: complete`",
            "`GOPNIK_CRITIC_STATUS: blocked`",
            "`GOPNIK_CRITIC_SURFACES:",
            "correlated agent result carries the surfaces line and the complete marker",
            "product-use confirmation, not a defect report",
            "Do not list packaging errors, missing files, workflow defects",
            "I found <A> and <B>",
            "only <A>, only <B>, or both?",
            "Never discard the other surfaces",
        ),
        SETUP_SKILLS[0]: (
            "Only after Stage 1 passes, inspect the candidate delivery surfaces",
            "old configuration, previous conversation, and memory as leads, never as confirmation",
            "One binary can also run a service and UI",
            "deployment and release routes as evidence",
            "not as product-use choices of their own",
            "Require a concrete consumption boundary",
            "alone does not prove a service exists",
            "critic brief must carry the same product-facing boundary",
            "evidence, not a surviving surface",
            "Do not leave the critic to infer this split",
            "already is the independent adversary",
            "without spawning another agent",
            "Verify every load-bearing inclusion or exclusion",
            "do not silently edit the critic's set",
            "independent agent using `gopnik-critic`",
            "mandate to refute the classification",
            "`GOPNIK_CRITIC_STATUS: complete`",
            "`GOPNIK_CRITIC_STATUS: blocked`",
            "`GOPNIK_CRITIC_SURFACES:",
            "correlated agent result carries the surfaces line and the complete marker",
            "product-use confirmation, not a defect report",
            "Do not list packaging errors, missing files, workflow defects",
            "I found <A> and <B>",
            "only <A>, only <B>, or both?",
            "Never discard the other surfaces",
        ),
        SETUP_SKILLS[1]: (
            "Только после зелёной Stage 1 изучи возможные поверхности поставки",
            "старую конфигурацию, прежний диалог и память подсказками, а не подтверждением",
            "Один бинарник может одновременно запускать сервис и UI",
            "как доказательства доставки этих поверхностей",
            "не как отдельные варианты использования продукта",
            "Требуй конкретную границу использования",
            "не доказывает существование сервиса",
            "В prompt критика явно перенеси ту же продуктовую границу",
            "доказательство, а не уцелевшая поверхность",
            "Не оставляй критику выводить это различие",
            "уже является независимым адверсарием",
            "не порождая ещё одного агента",
            "Проверь по репозиторию каждое опорное включение и исключение",
            "не исправляй набор критика молча",
            "независимому агенту с `gopnik-critic`",
            "поручением опровергнуть классификацию",
            "`GOPNIK_CRITIC_STATUS: complete`",
            "`GOPNIK_CRITIC_STATUS: blocked`",
            "`GOPNIK_CRITIC_SURFACES:",
            "связанный результат агента не содержит строку поверхностей и маркер `complete`",
            "подтверждение способа использования продукта, а не отчёт о дефектах",
            "Не перечисляй здесь ошибки упаковки, отсутствующие файлы, дефекты workflow",
            "Я вижу <A> и <B>",
            "только <A>, только <B> или оба варианта?",
            "Не отбрасывай остальные поверхности",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)

        stage1 = text.index(
            "Only after Stage 1 passes" if path.name != "SKILL.ru.md"
            else "Только после зелёной Stage 1"
        )
        critic = text.index("`gopnik-critic`", stage1)
        question = text.index("<A>", critic)
        stand = text.index(
            "Is there a test or staging environment" if path.name != "SKILL.ru.md"
            else "Есть ли стенд",
            question,
        )
        assert stage1 < critic < question < stand, path.name


def test_default_branch_delivery_becomes_an_explicit_post_merge_gate():
    text = _flat(INSTALL)
    for phrase in (
        "full Gopnik run is post-merge",
        "gate moving the task to Done or releasing it",
        "cannot honestly gate that merge",
        "Combine repository evidence with what the person said",
        "ask one question about it",
    ):
        assert phrase in text, phrase


def test_install_keeps_setup_status_separate_from_product_verdicts():
    text = _flat(INSTALL)
    for phrase in (
        "Installation and setup do not receive a product verdict",
        "belong only to a Gopnik run against a concrete product change",
    ):
        assert phrase in text, phrase


def test_stage1_failure_is_autonomous_until_authority_changes():
    text = _flat(INSTALL)
    for phrase in (
        "Approval attaches to the goal, not to each command",
        "continue autonomously through local, reversible diagnostics",
        "Do not ask permission to change diagnostic strategy",
        "same blocker twice without materially new evidence",
        "A Stage 1 failure becomes a hard turn boundary only when",
        "Do not inspect, infer, present, or ask about Stage 2 while Stage 1 is blocked",
        "Offer one recommended next action",
        "End with exactly one short question",
    ):
        assert phrase in text, phrase


def test_normal_onboarding_hides_internal_configuration_and_tool_theatre():
    text = _flat(INSTALL)
    for phrase in (
        "Keep the internal work internal",
        "do not narrate tool or skill selection",
        "configuration files, JSON",
        "Never expose its filename, format, keys, or contents",
        "Do not report the configuration path",
        "marketplace mechanics",
        "Never say that a configuration file was created, changed, is untracked, or should be committed",
        "do not append notes about files, Git status, cleanup, or what the person should commit",
    ):
        assert phrase in text, phrase


def test_onboarding_progress_reports_state_not_a_terminal_transcript():
    expected = {
        INSTALL: (
            "one user decision should normally produce one substantive response",
            "Do not emit repeated still-working updates for the same state",
            "checksum parsing, shell filters, retries, process polling",
            "A retry or a different diagnostic command is not a human-facing state change",
        ),
        SETUP_SKILLS[0]: (
            "one user decision should normally produce one substantive response",
            "Do not emit repeated still-working updates for the same state",
            "checksum parsing, shell filters, retries, process polling",
            "A retry or a different diagnostic command is not a human-facing state change",
        ),
        SETUP_SKILLS[1]: (
            "на один выбор человека должен приходиться один содержательный ответ",
            "Не отправляй повторные сообщения «ещё работаю» для одного состояния",
            "разбор контрольной суммы, фильтры оболочки, повторы, опрос процессов",
            "Повтор или другая диагностическая команда не меняют состояние для человека",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_first_stage1_run_has_a_resource_envelope():
    expected = {
        INSTALL: (
            "Every first Stage 1 command needs a wall-clock budget",
            "120 seconds",
            "Do not append a pipe",
            "helper's real exit status",
            "Do not rerun a timed-out command directly without an equivalent limit",
            "host-relative safety signal",
            "runtime memory objective is not a compiler memory limit",
        ),
        SETUP_SKILLS[0]: (
            "Every first Stage 1 command needs a wall-clock budget",
            "120 seconds",
            "Do not append a pipe",
            "helper's real exit status",
            "Do not rerun a timed-out command directly without an equivalent limit",
            "host-relative safety signal",
            "runtime memory objective is not a compiler memory limit",
        ),
        SETUP_SKILLS[1]: (
            "Первый запуск каждой команды Stage 1 должен иметь ограничение по времени",
            "120 секунд",
            "Не добавляй pipe",
            "настоящий код выхода helper",
            "Не перезапускай команду после тайм-аута напрямую без равноценного ограничения",
            "относительный к машине сигнал безопасности",
            "Ограничение памяти готового продукта не становится лимитом памяти компилятора",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_critic_has_bounded_private_diagnostics():
    expected = {
        ROOT / "plugins/gopnik/skills/gopnik-critic/SKILL.md": (
            "mktemp -d /tmp/gopnik-critic.XXXXXX",
            "Never use a fixed generic path",
            "agent/subagent wait mechanism",
            "exact child PID with a bounded timeout",
            "exact agent identifier returned at spawn",
            "report the critique as blocked",
            "once they stop producing new evidence",
        ),
        ROOT / "plugins/gopnik/skills/gopnik-critic/SKILL.ru.md": (
            "mktemp -d /tmp/gopnik-critic.XXXXXX",
            "Не используйте фиксированный общий путь",
            "механизм",
            "точный дочерний PID с ограниченным тайм-аутом",
            "точный идентификатор, который вернул spawn",
            "верните статус `blocked`",
            "перестали давать новые доказательства",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_spawned_critic_does_not_recurse():
    expected = {
        ROOT / "plugins/gopnik/skills/gopnik-critic/SKILL.md": (
            "Independent adversary mode",
            "already is the independent adversary in step 2",
            "Do not spawn another adversary",
            "second nested closure loop",
        ),
        ROOT / "plugins/gopnik/skills/gopnik-critic/SKILL.ru.md": (
            "Режим независимого адверсария",
            "уже является независимым адверсарием из шага 2",
            "Не порождайте ещё одного адверсария",
            "второй вложенный контур подтверждения",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_authenticated_production_read_requires_specific_confirmation():
    runner_skills = {
        RUNNER_SKILLS[0]: (
            "Describing an access method is context, not approval",
            "authenticated production read",
            "reading a secret",
            "one exact read-only probe",
        ),
        RUNNER_SKILLS[1]: (
            "Описание способа доступа — это контекст, а не разрешение",
            "авторизованным чтением production",
            "чтением секрета",
            "одну конкретную проверку только для чтения",
        ),
    }
    setup_surfaces = {
        INSTALL: runner_skills[RUNNER_SKILLS[0]],
        SETUP_SKILLS[0]: runner_skills[RUNNER_SKILLS[0]],
        SETUP_SKILLS[1]: runner_skills[RUNNER_SKILLS[1]],
        **runner_skills,
    }
    for path, phrases in setup_surfaces.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_shared_mechanics_and_local_access_are_two_distinct_layers():
    expected = {
        INSTALL: (
            "stable, portable verification mechanics belong to the project",
            "machine-specific paths, private targets, and credentials stay in an ignored local override",
            "Never put the shared project configuration in `.git/info/exclude`",
            "The local override must be separate from the shared project record",
        ),
        SETUP_SKILLS[0]: (
            "stable, portable verification mechanics belong to the project",
            "machine-specific paths, private targets, and credentials stay in an ignored local override",
            "Never put the shared project configuration in `.git/info/exclude`",
            "The local override must be separate from the shared project record",
        ),
        SETUP_SKILLS[1]: (
            "Устойчивая переносимая механика проверки принадлежит проекту",
            "локальные пути, приватные цели и учётные данные остаются в игнорируемом локальном дополнении",
            "Никогда не добавляй общую конфигурацию проекта в `.git/info/exclude`",
            "Локальное дополнение должно быть отделено от общей записи проекта",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_setup_final_report_never_surfaces_internal_record_as_repo_work():
    expected = {
        SETUP_SKILLS[0]: (
            "Never say that a configuration file was created, changed, is untracked, or should be committed",
            "Do not include it in a working-tree summary",
            "Did I omit internal files, Git status, and commit advice from the final response?",
        ),
        SETUP_SKILLS[1]: (
            "Никогда не говори, что конфигурационный файл создан, изменён, не отслеживается (`untracked`) или его нужно закоммитить",
            "Не включай его в обзор рабочего дерева",
            "Не упомянул ли я в финале внутренние файлы, статус Git и советы о коммите?",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_stage2_is_a_progressive_conversation_not_a_batched_questionnaire():
    text = _flat(INSTALL)
    for phrase in (
        "After the person confirms the delivery surfaces, explain Stage 2",
        "do not infer and present its infrastructure first",
        "ask one related follow-up",
        "ask one question about it",
        "Wait for the answer before asking the next one",
        "Never batch a URL, cluster, namespace, credentials, revision proof",
    ):
        assert phrase in text, phrase


def test_ui_browser_question_appears_only_after_stage2_surface_discovery():
    text = _flat(INSTALL)
    phrases = (
        "Do not ask about browser tooling merely because frontend files exist",
        "hard-coded to loopback proves local UI coverage, not a browser route against",
        "local UI coverage is what Stage 1 is for",
        "Should Stage 1 run it too?",
        "Only when the deployed UI is real and neither route exists",
        "may I connect Playwright MCP?",
        "This is another hard turn boundary",
        "Do not combine it with the stand, delivery, access, URL, or credentials questions",
    )
    for phrase in phrases:
        assert phrase in text, phrase

    stand_question = text.index("Is there a test or staging environment")
    access_question = text.index("How does a new version get there")
    surface_discovery = text.index("inspect the product surfaces")
    playwright_question = text.index("may I connect Playwright MCP?")
    assert stand_question < access_question < surface_discovery < playwright_question


def test_new_mcp_never_pretends_to_be_loaded_before_restart():
    expected = {
        INSTALL: (
            "Never claim that the current session can use a newly added MCP server",
            "fresh agent session, application restart, or extension restart",
            "tell the person explicitly",
            "Resume Stage 2 setup only after the restarted session can see the browser tool",
        ),
        SETUP_SKILLS[0]: (
            "Never claim that the current session can use a newly added MCP server",
            "fresh agent session, application restart, or extension restart",
            "tell the person explicitly",
            "Resume setup only after the restarted session can see the browser tool",
        ),
        SETUP_SKILLS[1]: (
            "Никогда не утверждай, что текущая сессия уже видит только что добавленный MCP",
            "нужна новая сессия агента, перезапуск приложения или расширения",
            "явно скажи об этом человеку",
            "Продолжай настройку только после того, как перезапущенная сессия увидит браузерный инструмент",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_the_gate_reads_the_confirmed_surfaces_rather_than_only_the_kind():
    """#77. The other half of the same rule, and the load-bearing one.

    `gopnik-setup` was told to cover every confirmed surface in Stage 2, and the
    gate had no way to tell a project with one surface from a project with four:
    `artifact_kind` is one word, and after a successful setup `stage2` is filled,
    which takes the `run it` row of the three-state table and stops consulting
    the record at all. A key with no reader is dead data, so this pins the
    reader.
    """
    for path, phrases in (
        (RUNNER_SKILLS[0], (
            "`verification.surfaces`",
            "Publication is not crossing",
            "A surface with no such step is `Not proven`",
            "An absent `surfaces` changes nothing",
        )),
        (RUNNER_SKILLS[1], (
            "`verification.surfaces`",
            "Публикация — не пересечение",
            "Отсутствующий `surfaces` не меняет ничего",
        )),
    ):
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_the_confirmation_step_records_the_surfaces_it_confirmed():
    """The writing half: without it the reader above has nothing to read."""
    for path, phrase in (
        (INSTALL, "`--surfaces <the confirmed surfaces, comma separated>`"),
        (SETUP_SKILLS[0], "`--surfaces <the confirmed surfaces, comma separated>`"),
        (SETUP_SKILLS[1], "`--surfaces <подтверждённые поверхности через запятую>`"),
    ):
        assert phrase in _flat(path), (path.name, phrase)


def test_ui_changes_require_real_browser_evidence_or_not_ready():
    expected = {
        RUNNER_SKILLS[0]: (
            "ask to connect Playwright MCP",
            "do not substitute HTTP calls or source inspection",
            "mark the UI cells `GAP` and return `NOT READY` for a UI change",
            "A backend-only change does not require browser evidence",
        ),
        RUNNER_SKILLS[1]: (
            "предложить подключить Playwright MCP",
            "не заменять его HTTP-вызовами или чтением исходников",
            "отметить UI-клетки как `GAP` и вернуть `NOT READY` для UI-изменения",
            "Backend-изменению не нужны браузерные доказательства",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_missing_nested_dependency_uses_safe_local_routes_before_asking():
    text = INSTALL.read_text(encoding="utf-8")
    example = " ".join(text[
        text.index("For a project wrapper with a missing nested dependency"):
        text.index("After Stage 1 succeeds")
    ].replace("> ", "").split())
    assert "user-local or project-declared route" in example
    assert "continue without another question" in example
    assert "only remaining route requires elevated privileges" in example
    for leaked in ("LoomWatch", "onWatch", "Go", "GOMAXPROCS", "GOMEMLIMIT",
                   "gopnik.json", "Kubernetes", "namespace", "token", "Helm"):
        assert leaked not in example, (leaked, example)


def test_autonomy_contract_is_project_and_toolchain_agnostic():
    surfaces = (INSTALL, *SETUP_SKILLS, *RUNNER_SKILLS)
    for path in surfaces:
        low = path.read_text(encoding="utf-8").lower()
        for project_name in ("loomwatch", "onwatch"):
            assert project_name not in low, (path.name, project_name)

    expected = {
        INSTALL: (
            "user-scoped dependency installation that needs no elevated privileges",
            "temporary environments, caches, and diagnostic output",
            "tracked project files",
            "system-wide installation",
        ),
        SETUP_SKILLS[0]: (
            "user-scoped dependency installation that needs no elevated privileges",
            "temporary environments, caches, and diagnostic output",
            "tracked project files",
            "system-wide installation",
        ),
        SETUP_SKILLS[1]: (
            "установку зависимости в пользовательское окружение без повышенных прав",
            "временные окружения, кеши и диагностический вывод",
            "отслеживаемых файлов проекта",
            "системной установкой",
        ),
        RUNNER_SKILLS[0]: (
            "Approval attaches to the verification goal, not to each command",
            "local, read-only or reversible diagnostics",
            "user-scoped dependency installation that needs no elevated privileges",
            "temporary environments, caches, and diagnostic output",
            "tracked project files",
            "system-wide installation",
        ),
        RUNNER_SKILLS[1]: (
            "Согласие относится к цели проверки, а не к каждой команде",
            "локальную диагностику только для чтения или с обратимым эффектом",
            "установку зависимости в пользовательское окружение без повышенных прав",
            "временные окружения, кеши и диагностический вывод",
            "отслеживаемых файлов проекта",
            "системной установкой",
        ),
    }
    for path, phrases in expected.items():
        text = _flat(path)
        for phrase in phrases:
            assert phrase in text, (path.name, phrase)


def test_install_separates_the_universal_recommendation_from_the_tracker_example():
    text = _flat(INSTALL)
    for phrase in (
        "If setup is blocked, do not use the configured closing flow below",
        "Do not append the recommendation or tracker example to a `setup blocked` response",
        "Only after setup reaches `configured`",
        "finish the status report first, then start the recommendation as a separate paragraph",
        "Do not merge the recommendation into a status bullet",
        "Do not qualify it with project-specific process or artifact details",
        "We recommend integrating Gopnik into the development cycle.",
        "Рекомендуем встроить Gopnik в цикл разработки.",
        "For example, when work is managed through tasks in a tracker:",
        "Например, если работа ведётся через задачи в трекере:",
        "After the task is defined, `gopnik-critic` checks its wording and completion criteria",
        "После постановки задачи `gopnik-critic` проверяет её формулировку и критерии готовности",
        "After implementation, `gopnik` checks the completed change before the task moves to `Done`",
        "После реализации `gopnik` проверяет готовое изменение перед переводом задачи в `Done`",
    ):
        assert phrase in text, phrase

    for rejected in (
        "End with one universal recommendation",
        "adapted to the project's existing workflow",
        "Give one short copyable prompt for each gate",
        "Offer to add the loop to the repository or tracker workflow",
    ):
        assert rejected not in text, rejected

    blocked = text.index("If setup is blocked")
    configured = text.index("Only after setup reaches `configured`")
    recommendation = text.index("We recommend integrating Gopnik")
    example = text.index("For example, when work is managed through tasks in a tracker")
    assert blocked < configured < recommendation < example


def test_installed_setup_skills_enforce_the_same_progressive_flow():
    for path in SETUP_SKILLS:
        text = _flat(path)
        required = (
            "Stage 2" in text,
            "Stage 1" in text,
            "JSON" in text,
            "one question" in text or "один вопрос" in text,
            "configuration files" in text or "конфигурационные файлы" in text,
        )
        assert all(required), (path.name, required)
        stage1_gate = text.index("Stage 1")
        stage2_intro = text.rindex("Stage 2")
        assert stage1_gate < stage2_intro, path.name


def test_every_guided_setup_entry_defers_surface_classification():
    expected_language = {
        SETUP_SKILLS[0]: "--language en",
        SETUP_SKILLS[1]: "--language ru",
    }
    for skill, language in expected_language.items():
        text = skill.read_text(encoding="utf-8")
        # `--confirm-artifact-kind` finalizes a kind that was already deferred,
        # and `--refresh`/`--add-stage1` revisit a record that was written in
        # some earlier session. None of the three is guided setup, so none of
        # them owes the deferral this rule is about.
        not_guided_setup = ("--confirm-artifact-kind", "--refresh", "--add-stage1")
        invocations = [
            line for line in text.splitlines()
            if "gopnik_setup.py" in line
            and not any(flag in line for flag in not_guided_setup)
        ]
        assert invocations, skill.name
        for invocation in invocations:
            assert "--defer-artifact-kind" in invocation, (skill.name, invocation)
            if "PATH/gopnik_setup.py" not in invocation:
                assert language in invocation, (skill.name, invocation)


def test_uninstall_preserves_configuration_unless_separately_confirmed():
    text = _flat(UNINSTALL)
    for phrase in (
        "preserve project verification knowledge by default",
        "Configuration is preserved by default",
        "separate explicit confirmation",
        "gopnik.json",
        ".claude/gopnik.json",
        ".codex/gopnik.json",
    ):
        assert phrase in text, phrase


def test_uninstall_is_narrow_and_verifiable():
    text = UNINSTALL.read_text(encoding="utf-8")
    for command in (
        "claude plugin uninstall gopnik@madduck-tech",
        "codex plugin remove gopnik@madduck-tech",
    ):
        assert command in text, command
    for root in (".claude/skills", ".agents/skills"):
        for skill in ("gopnik", "gopnik-critic", "gopnik-setup"):
            assert f"{root}/{skill}/" in text, (root, skill)
    for phrase in (
        "remove only the link",
        "Do not use broad globs",
        "Verify that each selected plugin entry",
        "what was preserved",
    ):
        assert phrase in text, phrase
    assert "rm -rf" not in text
    assert "docs/install.md" in text


def test_uninstall_confirmation_is_a_hard_turn_boundary():
    text = _flat(UNINSTALL)
    for phrase in (
        "initial request to follow this guide authorizes discovery, not deletion",
        "Confirmation is a hard turn boundary",
        "end the discovery response with a short question naming the exact targets",
        "do not run any removal command in that turn",
        "only after the user explicitly confirms those targets",
    ):
        assert phrase in text, phrase


def test_the_override_ignore_rule_travels_at_repository_scope():
    """#78. `.git/info/exclude` is not committed, and the team is the point.

    A repository-scope install exists so the team receives Gopnik with the
    project. An ignore rule left only in `.git/info/exclude` reaches nobody
    else, and the next person's own override — private hosts, an IaC directory,
    a secret-store read command — has nothing stopping them committing it.
    Editing a tracked project file still requires a question, so the rule is one
    question plus a file that travels, not a silent edit. The user scope keeps
    the current behaviour: asking there would be noise in someone else's
    repository, and a change that asks in both places has moved the defect
    rather than fixed it.
    """
    question = (
        "Stage 2 here needs values that belong to this machine, so they go into "
        "a separate local file. May I add that file to .gitignore, so it stays "
        "out of commits for everyone working on this repository?"
    )
    question_ru = (
        "Stage 2 здесь нужны значения, привязанные к этой машине, поэтому они "
        "уйдут в отдельный локальный файл. Можно добавить этот файл в "
        ".gitignore, чтобы он не попадал в коммиты ни у кого, кто работает с "
        "этим репозиторием?"
    )
    guide = _flat(INSTALL)
    english = _flat(SETUP_SKILLS[0])
    russian = _flat(SETUP_SKILLS[1])

    for phrase in (
        "the rule has to travel with the repository",
        "`.git/info/exclude` is never committed",
        "ask once before editing it",
        question,
        question_ru,
        "In the user scope, keep the current behaviour",
        "Ask nothing in either scope when the run needs no override at all",
        # A linked worktree and a submodule keep `.git` as a file, so the
        # literal `.git/info/exclude` is a path that does not exist there.
        "git rev-parse --git-path info/exclude",
        "the repository decides",
    ):
        assert phrase in guide, f"install.md: {phrase}"

    for phrase in (
        "At repository scope the ignore rule has to end up in a file that travels with the repository",
        "`.git/info/exclude` is not committed",
        "ask before editing it, exactly once",
        question,
        "Do not ask the `.gitignore` question there",
        "Ask nothing at either scope when the run needs no override at all",
        "git rev-parse --git-path info/exclude",
        "in a linked worktree or a submodule `.git` is a file",
    ):
        assert phrase in english, f"SKILL.md: {phrase}"

    for phrase in (
        "В области репозитория правило игнорирования обязано оказаться в файле, который уезжает вместе с репозиторием",
        "`.git/info/exclude` не коммитится",
        "спроси перед его правкой ровно один раз",
        question_ru,
        "Не задавай там вопрос про `.gitignore`",
        "Не спрашивай ни в одной области, когда дополнение вообще не нужно",
        "git rev-parse --git-path info/exclude",
        "в подключённом рабочем дереве и в подмодуле `.git` — это файл",
    ):
        assert phrase in russian, f"SKILL.ru.md: {phrase}"


def _main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {name}: {exc}")
    print(f"\n{'FAILED' if failures else 'all tests passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
