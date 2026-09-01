# Install and configure Gopnik

You are the installation agent. Complete installation and project setup as a
short, guided conversation. The person should always understand what is being
set up now, why it matters, and what you need from them next.

## 1. Ask for the conversation language

Before any other onboarding text, always ask this exact question in English:

> Which language would you like me to use: English or Russian?

Your response must end after that question. Do not inspect, fetch another
resource, install, explain the stages, or announce a plan before the user
answers. Then use the selected language for every explanation, question, and
the final report. Carry the choice into setup as `--language en` or
`--language ru`; it is selected once and retained for future skills and
uninstall.

## 2. Ask where to install Gopnik

Immediately after the language answer, ask one installation-scope question in
the selected language. In English:

> Where should I install Gopnik: for this agent across your projects, or only in this repository so the team receives it with the project?

In Russian:

> Куда установить Gopnik: для этого агента во всех ваших проектах или только в этот репозиторий, чтобы команда получала его вместе с проектом?

This question is a hard turn boundary. End the response with it and wait. Do
not inspect the repository, explain the stages, or install anything before the
answer. Do not call the first option `global`: it applies to the current agent
host, not every agent on the machine. Infer the current host yourself; do not
turn this into a second platform question.

The first option means the current host's user-scoped native plugin or skill
mechanism, available to the person across projects. The second means a copy
inside the current repository, installed only for the current host so the team
can receive and version it with the project. Install in exactly the selected
scope, never both. Keep that choice for the rest of this setup conversation;
it does not belong in project verification data.

## 3. Orient the person before doing internal work

The first visible response after the installation-scope answer must explain
the process in three short, plain-language points:

- **Stage 0** decides what could break for each future change.
- **Stage 1** checks the code inside the repository. This is what you will set
  up first.
- **Stage 2** checks the built or deployed result where people actually use it.
  You will discuss it only after Stage 1 works.

Then say that you will install Gopnik and find the project's own fast Stage 1
check. Do not turn this orientation into a lecture.

Keep the internal work internal. In normal onboarding messages, do not narrate
tool or skill selection, raw-guide fetching, marketplace refreshes, version
comparisons, installation paths, configuration files, JSON, configuration
keys, or internal CLI syntax. If the host requires an action announcement,
combine it into one short sentence. Mention a technical detail only when the
person must act on it or explicitly asks for it.

After the orientation, use one short progress update only when the human-facing
state changes, for example: "Gopnik is installed. Now I am checking how this
project verifies code locally."

During setup, one user decision should normally produce one substantive
response. Do not emit repeated still-working updates for the same state. Tool
selection, guide reads, downloads, checksum parsing, shell filters, retries,
process polling, and alternative diagnostic commands are internal work. A
retry or a different diagnostic command is not a human-facing state change.
If the host requires a periodic update during a long operation, give one plain
sentence about the current goal and omit the mechanics.

## 4. Inspect the repository silently

Confirm the project root. Read repository instructions such as `AGENTS.md`,
`CLAUDE.md`, contribution docs, package scripts, build wrappers, CI workflows,
deployment manifests, and the existing project configuration. Inspect the
working tree and preserve unrelated changes.

Infer the agent host, the selected scope's installation route, toolchain, and Stage 1 commands from
repository evidence. Do not classify delivery surfaces yet, even when files
make candidates visible. Do not ask the user for facts the repository already
answers. Never bypass a project-owned wrapper with generic commands such as
`go test`, `npm test`, or `pytest` when the project tells agents to use
something else.

Do not inspect or discuss the Stage 2 route yet. Finish Stage 1 first.

## 5. Install all three skills

One installation must provide this complete bundle:

- `gopnik` attacks a completed change;
- `gopnik-critic` attacks an important claim;
- `gopnik-setup` records this project's verification mechanics.

For an agent-wide installation, use the current host's user-scoped native
plugin or skill mechanism. For a repository installation, use the
repository-local route below for the current host. Do not silently fall back to
the other scope, install into both scopes, or install into every detected agent
merely because several CLIs exist. If the selected scope is unsupported, state
that limitation plainly and ask whether the person wants the available scope
instead; wait before changing scope.

### Claude Code

```sh
claude plugin marketplace add madduck-tech/gopnik
claude plugin marketplace update madduck-tech
claude plugin install gopnik@madduck-tech
claude plugin update gopnik@madduck-tech
```

### Codex

```sh
codex plugin marketplace add madduck-tech/gopnik
codex plugin marketplace upgrade madduck-tech
codex plugin add gopnik@madduck-tech
```

### An installation from before the rename

This marketplace was published as `concordloom` before the organization was
renamed. When the host still lists it under that name, add the marketplace
again with the commands above and install `gopnik@madduck-tech`. Remove the
old registration only through the uninstall guide, after the new selector
works.

### Any other agent

Use that host's documented plugin or skills mechanism. Install the three
directories under `plugins/gopnik/skills/` together, including every file in
them. Verify that the host discovers all three skills; do not assume it reads a
Claude- or Codex-specific directory.

### Repository-local installation

When the person selected the repository scope, run the matching command from
the project root. For Claude Code:

```sh
curl -fsSL https://raw.githubusercontent.com/madduck-tech/gopnik/main/install.sh | sh -s -- --claude
```

For Codex:

```sh
curl -fsSL https://raw.githubusercontent.com/madduck-tech/gopnik/main/install.sh | sh -s -- --codex
```

This needs Python 3.10+, `sh`, `tar`, and `curl` or `wget`. It installs under
`.claude/skills/` for Claude Code or `.agents/skills/` for Codex. For another
host, use its documented repository-local skills directory and copy the same
three skill directories together. Re-running updates the skills and preserves
existing configuration.

An existing installation is not proof that it is current. Refresh the
marketplace snapshot, update or reinstall the plugin, and verify that its
reported version matches the current marketplace entry. Then verify that
`gopnik`, `gopnik-critic`, and `gopnik-setup` are present.

If you detect an installation from before Gopnik 4, follow
[`migration-v4.md`](migration-v4.md) after the new bundle is verified. Do not
silently merge configuration files or remove the earlier installation during
ordinary setup.

If the host needs a restart to load an update, remember it for the final report
and continue setup by reading the newly installed files directly. Never pretend
the current session loaded a new skill or keep following an older cached copy.

## 6. Set up Stage 1, and stop there if it is blocked

Read and follow the installed `gopnik-setup` skill. Use its script only after
reading the repository's instructions.

When the repository defines its own commands, pass exactly those commands to
the script instead of letting it guess. Repeat `--stage1` for each command:

```sh
python3 PATH/gopnik_setup.py --defer-artifact-kind \
  --language en \
  --stage1 './app.sh --smoke' \
  --stage1 './app.sh --test'
```

Run the setup helper as the complete shell command. Do not append a pipe,
redirect, `tail`, `tee`, `|| true`, or another wrapper: its tool result must
carry the helper's real exit status.

Use the actual installed path. Guided setup must defer the delivery kind until
Stage 1 passes, a critic challenges the candidate surfaces, and the person
confirms how the project is used. When no authoritative project instructions
exist, the script may detect and run candidates itself. It must record only
Stage 1 commands that actually passed.

Before recording anything, compare the commands you are about to write with
what this project actually runs: read what CI invokes job by job, and look for
check or test directories the documented route never reaches. Nothing running a
suite is the strongest case for recording it, not the weakest — Stage 1 would
be the only place it ever executes. When such a check exists, ask one question
about it and wait, in the selected language. In English:

> The project also has <check>, which <command> never runs. Should Stage 1 run it too?

Ask nothing when the documented route already runs everything executable in the
tree. The installed skill carries the rest of this step, including what to do
with each answer.

Run fast, read-only checks without making the user supervise them. Ask before a
lengthy suite or a command that mutates shared state. Order explicit checks from
fastest to slowest; the setup script stops at the first failure.

The request to install and configure Gopnik authorizes one continuous local
setup goal. Approval attaches to the goal, not to each command. Within that
goal, continue autonomously through local, reversible diagnostics, including:

- user-scoped dependency installation that needs no elevated privileges;
- temporary environments, caches, and diagnostic output;
- bounded reruns of the same project-owned check with safer environment,
  parallelism, cache, or tracing settings;
- read-only inspection that narrows a failure to a dependency, phase, package,
  test, or process.

Do not ask permission to change diagnostic strategy while it stays inside this
scope. Ask only before a system-wide installation or elevated privileges,
editing tracked project files, a lengthy suite outside the agreed budget,
raising a resource limit beyond the current safety envelope, accessing a secret,
or changing shared or external state.

Every first Stage 1 command needs a wall-clock budget. Use the setup script's
120 seconds by default, or a smaller repository-defined limit. Use memory as a
host-relative safety signal: watch available memory, sustained swap pressure,
host responsiveness, and repository evidence instead of enforcing one universal
RSS number. A runtime memory objective is not a compiler memory limit. Stop
before the check threatens the host, and diagnose under an equivalent or safer
envelope. Do not rerun a timed-out command directly without an equivalent limit.
Ask before raising either limit for a check the repository documents as
legitimately expensive.

When a required Stage 1 check fails, diagnose it inside the autonomy budget
before presenting a blocker. Each retry must test a materially different
hypothesis and preserve or tighten the current safety envelope. Continue while
the evidence narrows the cause. If two consecutive attempts reproduce the same
blocker twice without materially new evidence, stop rather than churn.

A Stage 1 failure becomes a hard turn boundary only when the next useful action
crosses an authority boundary above, requires a product or workflow choice, or
the bounded diagnostic loop has stopped making progress. Then:

1. Explain in plain language what Stage 1 was trying to prove.
2. State the concrete cause and its impact. Diagnose the useful underlying
   error; an exit code or a missing program inside a project wrapper does not
   mean the wrapper itself is absent.
3. Offer one recommended next action grounded in the repository. Give one
   alternative only if it is genuinely useful.
4. End with exactly one short question about that next action.

Do not inspect, infer, present, or ask about Stage 2 while Stage 1 is blocked.
Do not give a setup summary, infrastructure questionnaire, raw command chain,
large terminal excerpt, configuration path, JSON, or internal state. Resume
only after the person answers.

For a project wrapper with a missing nested dependency, good behaviour is:

> Stage 1 needs a tool that is not available here. The system route requires
> elevated privileges, so I will first try a user-local or project-declared
> route and repeat the project check. Those steps are local and reversible, so
> I will continue without another question. If the only remaining route
> requires elevated privileges, I will stop and ask.

After Stage 1 succeeds, report that result in one short sentence. A build,
package smoke test, or `--version` check is only a Stage 2 prerequisite, not
Stage 2 itself.

## 7. Confirm how the project is used after delivery

Only after Stage 1 passes, inspect the candidate delivery surfaces. Treat an
old configuration, previous conversation, and memory as leads, never as
confirmation. Enumerate the product-facing things a person or another system
can consume after delivery: installed commands, packages, libraries, plugins,
HTTP services and APIs, web or mobile interfaces, background jobs, charts, and
migrations. Inspect deployment and release routes as evidence for how those
surfaces arrive, not as product-use choices of their own; the exception is a
reusable workflow or action that consumers invoke directly.

Require a concrete consumption boundary. A declared console entry point,
published package API, protocol/server entry point, renderable UI artifact, or
runnable job can support a candidate even when its route is broken. A filename,
function name, or string such as `server`, `serve`, or `web service` alone does
not prove a service exists.

Do not let the packaging label end the search. One binary can also run a
service and UI; one repository can ship several artifacts. A clean installed
CLI check proves only the CLI surface, not a service deployed from the same
binary.

Form a provisional classification and compact evidence inventory. Give both to
an independent agent using `gopnik-critic`, with the mandate to refute the
classification by finding omitted delivery surfaces or conflicting evidence.
The critic brief must carry the same product-facing boundary: a CI, deployment,
or release route that only transports another artifact is evidence, not a
surviving surface; a reusable workflow/action or a product background job that
a consumer invokes is a surface. Do not leave the critic to infer this split
from the word `job`.
Explicitly tell that spawned agent it already is the independent adversary and
must use `gopnik-critic` in independent adversary mode without spawning another
agent.
Give that agent an explicit completion contract: only after it has inspected
the evidence and completed the challenge, its penultimate line must be
`GOPNIK_CRITIC_SURFACES: <comma-separated surviving surface identifiers>` and
its last line must be exactly `GOPNIK_CRITIC_STATUS: complete`; if it cannot
complete the analysis, its last line must instead be
`GOPNIK_CRITIC_STATUS: blocked`. Do not continue to the user question unless
the correlated agent result carries the surfaces line and the complete marker.
Verify every load-bearing inclusion or exclusion against the repository before
using that set. If it does not survive this check, do not silently edit the
critic's set; return a corrected brief to one independent critic or report the
classification as blocked.
Use the surviving surfaces from that line in the question; do not restore a
candidate the critic refuted.
The critic does not decide how the product is really operated and does not
question the person directly. Fold its surviving candidates into one short
question. Keep the critic's technical findings internal: this is a product-use
confirmation, not a defect report. Keep that product-use confirmation to at
most two short sentences; the brief stage orientation and Stage 1 status may
precede it. Before the product-use question, give one plain status sentence in
the selected language that names `Stage 1` and says its local check passed or
is ready, for example: `Stage 1 is ready — the project's local check passed.`
In Russian: `Stage 1 готова — штатная проверка проекта прошла.` Name the
plausible surfaces in plain language and, when necessary, add only one brief
uncertainty such as `the delivery route does not prove which one ships`. Do not
list packaging errors, missing files, workflow defects, or implementation
details here. Handle a finding separately only when it blocks Stage 1 or leaves
no plausible surface to confirm.

Do not ask the person to choose an internal `artifact_kind`. Name only the
concrete surfaces found in this repository. When several are plausible, ask:

> I found <A> and <B>. After delivery, do people use only <A>, only <B>, or both?

In Russian, ask:

> Я вижу <A> и <B>. После поставки люди используют только <A>, только <B> или оба варианта?

When only one is visible, ask whether it is the only way people use the project
after delivery or whether another deployed or consumed surface must be included.

This confirmation question is a hard turn boundary. End with it and wait.
Until the answer arrives, do not finalize the delivery kind, inspect or present
infrastructure, draft or run Stage 2, or ask about a stand, access, or browser
tooling.

After the answer, finalize the primary kind with
`--confirm-artifact-kind KIND`, and record what was confirmed with
`--surfaces <the confirmed surfaces, comma separated>`. Invoke the setup helper
exactly once in this step, with those two options and nothing else: do not probe
`--help`, repeat `--language`, or combine it with any setup option. The selected
language and Stage 1 evidence are already stored. For a hybrid project, choose
the kind at the farthest confirmed delivery boundary, then cover every confirmed
surface in Stage 2 and the operational notes. Never discard the other surfaces
because the internal record has one primary kind: `artifact_kind` holds one
word, `--surfaces` holds the set, and a verdict that has to decide whether
Stage 2 covered every surface has nowhere else to read it.

Choose that kind from this complete mapping without inspecting the helper or
rediscovering its choices: a deployed web UI, API, or always-on application is
`service`; an installed command is `cli`; an imported package or SDK is
`library`; a cluster or infrastructure bundle is `chart`; a host-loaded
extension is `plugin`; a schema or data transition is `migration`; and a
production model-call boundary is `model-boundary`. For several confirmed
surfaces, select the farthest delivery boundary; for example, a deployed web UI
plus an installed command has primary kind `service`. Reuse the exact helper
path that succeeded for Stage 1 and run the confirmation immediately.

## 8. Ask whether Stage 2 has somewhere real to run

After the person confirms the delivery surfaces, explain Stage 2 in one
sentence: it checks the built or deployed result where people actually use it.

For a service or application that is deployed, do not infer and present its
infrastructure first. Ask only:

> Is there a test or staging environment where Gopnik can verify the deployed version?

In Russian, prefer the natural equivalent:

> Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?

The visible response must combine the explanation and question exactly:

> Stage 2 checks the built or deployed result where people actually use it. Is there a test or staging environment where Gopnik can verify the deployed version?

In Russian:

> Stage 2 проверяет собранный или развёрнутый результат там, где им реально пользуются. Есть ли стенд, на котором Gopnik сможет проверить уже развёрнутую версию?

This availability question is a hard turn boundary. End the response with it
and wait.

If the answer is yes, ask one related follow-up:

> How does a new version get there, and how can the agent obtain access? Do not send secrets; just name the existing access method.

In Russian, use the natural equivalent:

> Как новая версия попадает на стенд и как агенту получить к нему доступ? Секреты присылать не нужно — достаточно назвать существующий способ доступа.

Then wait again. Do not ask for infrastructure fields or present a proposed
command route before the person answers.

For a package, CLI, plugin, or another artifact used only through a clean
consumer environment, create that environment yourself instead of asking an
irrelevant staging question. If any confirmed surface is deployed, ask the
stand question; a clean consumer check may remain another Stage 2 cell, but it
does not cover the deployment.

After the answer, inspect CI triggers, deploy jobs, manifests, release scripts,
service endpoints, and version metadata. Combine repository evidence with what
the person said. Verify the access method and every read-only prerequisite you
can, then silently record only a route a future Gopnik run can execute.

The stable, portable verification mechanics belong to the project;
machine-specific paths, private targets, and credentials stay in an ignored
local override. The local override must be separate from the shared project
record and the shared route must refer to local values through environment
variables or another project-owned indirection. Never put the shared project
configuration in `.git/info/exclude`. Never copy a private target or an
absolute home-directory path into a file intended for the team.

Where that override's ignore rule belongs depends on the installation scope
chosen in step 2, and the two scopes must diverge. In the repository scope the
rule has to travel with the repository — the project's `.gitignore`, or the
nearest tracked ignore file that already governs the override's directory.
`.git/info/exclude` is never committed, so a rule left only there protects this
machine while the skills and the configuration reach the whole team, and the
next person to create their own override has nothing stopping them committing
private infrastructure paths and a secret-store read command. A tracked ignore
file is a tracked project file, so ask once before editing it, in the selected
language, and wait. In English:

> Stage 2 here needs values that belong to this machine, so they go into a separate local file. May I add that file to .gitignore, so it stays out of commits for everyone working on this repository?

In Russian:

> Stage 2 здесь нужны значения, привязанные к этой машине, поэтому они уйдут в отдельный локальный файл. Можно добавить этот файл в .gitignore, чтобы он не попадал в коммиты ни у кого, кто работает с этим репозиторием?

This ignore question is a hard turn boundary too. The visible response is that
question and nothing else.

In the user scope, keep the current behaviour: a personal override belongs in
this repository's own exclude file — the path `git rev-parse --git-path
info/exclude` prints, which in a linked worktree or a submodule is not
`.git/info/exclude` — and asking to edit `.gitignore` in someone else's
repository would be noise. Ask nothing in either scope when the run needs no
override at all. Setup invoked on its own, with no scope carried from this
conversation, reads the scope off the repository instead, and where the answer
carried from here disagrees with what the repository shows, the repository
decides.

As part of that investigation, inspect the product surfaces that Stage 2 must
actually exercise. Do not ask about browser tooling merely because frontend
files exist. If the deployed product has a user interface, first look for a
project-owned browser route such as Playwright or Cypress against the stand,
then for a browser or computer-use tool already available to the agent. A route
counts only when it can target the stand without tracked-file edits. A test
hard-coded to loopback proves local UI coverage, not a browser route against
the stand — and local UI coverage is what Stage 1 is for. When such a suite
exists and Stage 1 does not already run it, reconcile it as in step 6 instead
of discarding it: the loopback rule disqualifies it from this stage, not from
the project.

Only when the deployed UI is real and neither route exists, explain the missing
capability and ask one contextual question in the selected language. In
English:

> The stand has a user interface, but this agent has no browser tool for Stage 2. To open it, exercise the flow, inspect console and network errors, and capture screenshots, may I connect Playwright MCP?

This is another hard turn boundary. Do not combine it with the stand,
delivery, access, URL, or credentials questions. Wait for the answer.

If the person agrees, determine and use the current host's supported MCP setup
route rather than guessing a command for Codex, Claude Code, Cursor, or another
agent. The approval covers only connecting Playwright MCP, not changing the
project or exercising a state-changing UI flow.

Never claim that the current session can use a newly added MCP server. Check
the current host's restart behaviour and visible tool inventory. If a fresh
agent session, application restart, or extension restart is required, tell the
person explicitly, give the exact resume phrase, and stop. Resume Stage 2 setup
only after the restarted session can see the browser tool. Then perform a safe
read-only browser probe against the stand: open the UI, inspect the rendered
state plus console and network errors, and capture a screenshot. Ask separately
before any state-changing browser action.

If the person declines or the host cannot connect a browser tool, continue
setting up reachable non-UI surfaces and record the UI capability as missing.
Do not ask again during normal setup. A future change that affects UI behaviour
cannot receive `READY` until its UI cells have browser evidence; a backend-only
change does not need a browser merely because the service also has a UI.

If one important fact is still missing, explain why it matters and ask one
question about it. Wait for the answer before asking the next one. Never batch a
URL, cluster, namespace, credentials, revision proof, negative test, dependency
installation, and long-suite permission into one message.

Internally, the confirmed route must be able to:

1. trigger or observe delivery for the exact revision;
2. wait for the matching pipeline or rollout with a check that can fail;
3. prove the running artifact is that revision;
4. exercise a real API, UI, consumer, or operational path;
5. prove the check can fail with a safe negative or counterfactual case.

If deployment happens only after a push or merge to the default branch, say
plainly that a full Gopnik run is post-merge. It can gate moving the task to
Done or releasing it, but cannot honestly gate that merge unless the project
adds a preview environment.

If no test or staging environment exists, record that Stage 2 has no reachable
project-level target and finish with an honest Stage 1 scope. If the environment
exists but the agent lacks access, treat access as the one setup blocker. If the
answer is ambiguous, ask one short clarification instead of guessing.

Record the stable mechanics and selected language in the project configuration
silently. Never expose its filename, format, keys, or contents during normal
onboarding. Reveal those details only if the person explicitly asks or a
malformed hand-written file requires manual repair. Never store credentials.

Validate public and anonymous read-only Stage 2 prerequisites without
supervision. Describing an access method is context, not approval. Before an
authenticated production read or reading a secret, name the production target,
explain the intended observation in plain language, and ask for explicit
confirmation for one exact read-only probe. Keep the credential only in process
memory and never print or persist it. That confirmation does not authorize a
second endpoint, a state-changing UI flow, deploy, migration, apply, or another
shared write; ask separately when needed. A missing tool, VPN, token,
permission, URL, or revision proof is a setup blocker; discuss only that
blocker using the same one-problem, one-next-step, one-question pattern.

## 9. Finish with a human-sized summary and recommendation

If setup is blocked, do not use the configured closing flow below. End with the
single blocker question described above. Do not append the recommendation or
tracker example to a `setup blocked` response.

Only after setup reaches `configured`, give the status report and recommendation
below. Keep them as two distinct parts: finish the status report first, then
start the recommendation as a separate paragraph. Do not merge the
recommendation into a status bullet.

Keep the status report to three short points at most:

- whether Gopnik is installed;
- whether the project's local check is ready and what was observed;
- whether the real delivery path is ready for Stage 2, or the one remaining
  blocker.

Do not report the configuration path, saved language, artifact kind, internal
keys, JSON, raw command routes, marketplace mechanics, or every file installed.
Mention an agent restart only if it is actually required.

Treat the internal project record as already handled, not as a user-facing
repository change. Never say that a configuration file was created, changed,
is untracked, or should be committed. Do not include it in a working-tree
summary. After the recommendation and tracker example, stop: do not append notes
about files, Git status, cleanup, or what the person should commit.

Installation and setup do not receive a product verdict. `READY` and
`NOT READY` belong only to a Gopnik run against a concrete product change.

After the configured status report, give one universal recommendation. Keep it
separate from any example. Do not qualify it with project-specific process or
artifact details. Use the exact first sentence for the selected language:

- English: `We recommend integrating Gopnik into the development cycle.`
- Russian: `Рекомендуем встроить Gopnik в цикл разработки.`

Then give the tracker flow separately as an example in the selected language.
Use this content:

English:

> For example, when work is managed through tasks in a tracker:
>
> 1. After the task is defined, `gopnik-critic` checks its wording and completion criteria.
> 2. After the solution is prepared, `gopnik-critic` checks the chosen approach.
> 3. After implementation, `gopnik` checks the completed change before the task moves to `Done`.

Russian:

> Например, если работа ведётся через задачи в трекере:
>
> 1. После постановки задачи `gopnik-critic` проверяет её формулировку и критерии готовности.
> 2. После подготовки решения `gopnik-critic` проверяет выбранный подход.
> 3. После реализации `gopnik` проверяет готовое изменение перед переводом задачи в `Done`.

Do not replace this recommendation with a mandatory workflow. Do not add
command-style prompts for the person to copy.
