#!/bin/sh
# Put the gopnik skills into a project.
#
# Most people do not need this script.
#
#   Claude Code: `/plugin marketplace add madduck-tech/gopnik` then
#                `/plugin install gopnik@madduck-tech`
#   Codex:       `codex plugin marketplace add madduck-tech/gopnik` then
#                `codex plugin add gopnik@madduck-tech`
#
# What those do not do is put the files in your repository, or leave you a
# gopnik.json to edit and commit. That is what this is for.
#
# Nothing has to be cloned first. From inside your project:
#
#   curl -fsSL https://raw.githubusercontent.com/madduck-tech/gopnik/main/install.sh | sh
#
# or, from a clone:
#
#   sh install.sh              # detect what the project uses, install for it
#   sh install.sh --claude     # .claude/skills
#   sh install.sh --codex      # .agents/skills
#   sh install.sh --setup      # and work out this project's checks afterwards
#   sh install.sh --dir PATH   # install into PATH instead of the current directory
#
# Piped through sh, arguments go after -s --, e.g. `| sh -s -- --codex`.
# Set GOPNIK_REF to install from a branch or tag other than main.
#
# Nothing here runs by itself afterwards. No hook is installed, no settings file
# is edited, and no file you own is merged into: the skills are yours to invoke
# by name, and when to invoke them is your call.
#
# Re-running is safe: skill files are overwritten, existing configuration is
# left alone.

set -eu

REF=${GOPNIK_REF:-main}
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

resolve() {
  SKILLS_SRC="$SRC/plugins/gopnik/skills"
  SKILL_SRC="$SKILLS_SRC/gopnik"
}

# Every skill under the plugin, not just the gate: the critic is the other half
# of the same cycle, and installing one of them is worse than installing
# neither, because the missing half is the one nobody notices is missing.
#
# Whole directories rather than SKILL.md alone — the gopnik-setup skill ships a script
# beside its text, and copying only the text left it describing a file that was
# never installed.
copy_skills() {
  for dir in "$SKILLS_SRC"/*/; do
    [ -f "$dir/SKILL.md" ] || continue
    name=$(basename "$dir")
    mkdir -p "$1/$name"
    cp -R "$dir." "$1/$name/"
    # cp -R takes everything, and a source tree that has been run has a
    # __pycache__ in it. Shipping one puts this machine's byte code, stamped
    # with its Python version, into somebody else's repository.
    rm -rf "$1/$name/__pycache__"
    say "${1#"$TARGET/"}/$name/"
  done
}
resolve

TARGET=$(pwd)
WANT_CLAUDE=0
WANT_CODEX=0
RUN_SETUP=0

while [ $# -gt 0 ]; do
  case "$1" in
    --claude) WANT_CLAUDE=1 ;;
    --codex)  WANT_CODEX=1 ;;
    --setup)  RUN_SETUP=1 ;;
    --dir)    shift; TARGET=$1 ;;
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$WANT_CLAUDE" -eq 0 ] && [ "$WANT_CODEX" -eq 0 ]; then
  # Nothing asked for explicitly: install for whatever the project already uses,
  # and default to Claude Code when the project uses neither.
  [ -d "$TARGET/.claude" ] && WANT_CLAUDE=1
  [ -d "$TARGET/.agents" ] && WANT_CODEX=1
  if [ "$WANT_CLAUDE" -eq 0 ] && [ "$WANT_CODEX" -eq 0 ]; then
    WANT_CLAUDE=1
  fi
fi

say() { printf '  %s\n' "$1"; }

# Piped straight from the network there is no source tree next to the script, so
# fetch one. This is the whole difference between a two-step install and a
# one-liner, and it is the path most people will take.
if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT INT TERM
  URL="https://codeload.github.com/madduck-tech/gopnik/tar.gz/$REF"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$TMP/src.tar.gz"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP/src.tar.gz" "$URL"
  else
    echo "need curl or wget to fetch the skill, and found neither" >&2
    exit 1
  fi

  tar -xzf "$TMP/src.tar.gz" -C "$TMP"
  # Not `-name 'gopnik-*'`: GitHub names the extracted directory after
  # the repository, so pinning the repository name here means renaming the
  # repository breaks the one-liner — the install path the README puts first —
  # while the redirect works and every static check passes. There is exactly
  # one directory in the extraction; take it.
  SRC=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  resolve

  if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
    echo "fetched $REF but the skill is not in it — report this at" >&2
    echo "https://github.com/madduck-tech/gopnik/issues" >&2
    exit 1
  fi
fi

echo "Installing gopnik into $TARGET"

if [ "$WANT_CLAUDE" -eq 1 ]; then
  mkdir -p "$TARGET/.claude/skills"
  copy_skills "$TARGET/.claude/skills"
  SETUP_SCRIPT=".claude/skills/gopnik-setup/gopnik_setup.py"
fi

if [ "$WANT_CODEX" -eq 1 ]; then
  mkdir -p "$TARGET/.agents/skills"
  copy_skills "$TARGET/.agents/skills"
  SETUP_SCRIPT=".agents/skills/gopnik-setup/gopnik_setup.py"
fi

# One config for the project, not one per agent: nothing reads it but whoever is
# doing the work, so it has no business living in an agent's directory. Existing
# installs keep theirs where it is.
CONFIG=""
for candidate in .claude/gopnik.json .codex/gopnik.json gopnik.json; do
  if [ -f "$TARGET/$candidate" ]; then
    CONFIG=$candidate
    break
  fi
done

if [ -n "$CONFIG" ]; then
  say "$CONFIG  (kept — already present)"
else
  cp "$SRC/gopnik.example.json" "$TARGET/gopnik.json"
  say "gopnik.json  (edit the verification block to describe this project)"
fi

echo

# The example's checks are placeholders, so at this point the skills know
# nothing about this project. Setup runs the candidates here and writes down the
# ones that pass — it is the difference between installed and useful, so it is
# offered as the next step rather than left to be discovered.
if [ "$RUN_SETUP" -eq 1 ] && command -v python3 >/dev/null 2>&1; then
  # Not `|| true`: that turned a refusal into a silent success and left the
  # skills installed knowing nothing, with exit 0.
  if python3 "$TARGET/$SETUP_SCRIPT" --dir "$TARGET"; then
    :
  else
    echo
    echo "Setup did not finish — see above. The skills are installed; what is"
    echo "missing is the part setup reports."
    exit 1
  fi
else
  if [ "$RUN_SETUP" -eq 1 ]; then
    echo "No python3 here, so the setup step was skipped."
    echo
  fi
  echo "One more step — it works out this project's checks and writes them down:"
  echo
  echo "    python3 $SETUP_SCRIPT"
  echo
  echo "Then invoke the gopnik skill by name before claiming a change works."
fi
