#!/usr/bin/env bash
# Install the supervise skill, for Claude Code and opencode.
#
#   ./install.sh                     from a clone
#   curl -fsSL <raw-url> | bash      from anywhere (clones itself)
#   ./install.sh --project           into ./.claude/skills of the current repo
#
# The skill goes to ~/.claude/skills either way. opencode reads that directory too,
# so one install serves both agents; when opencode is present its /supervise command
# is added as well.
#
# Claude Code users may prefer the plugin route instead, which handles updates:
#   /plugin marketplace add aldhosutra/supervise
#   /plugin install supervise@aldhosutra
set -euo pipefail

REPO_URL="https://github.com/aldhosutra/supervise.git"
SKILL_SUBPATH="plugins/supervise/skills/supervise"
COMMAND_SUBPATH="plugins/supervise/opencode/command/supervise.md"
SCOPE="user"
[ "${1:-}" = "--project" ] && SCOPE="project"

for tool in git python3 tmux; do
  command -v "$tool" >/dev/null 2>&1 || echo "warning: $tool not found — the skill needs it" >&2
done
if ! command -v claude >/dev/null 2>&1 && ! command -v opencode >/dev/null 2>&1; then
  echo "warning: neither claude nor opencode found — there will be nothing to supervise" >&2
fi

# Work out where the skill is coming from. When piped through bash there is no
# script on disk to locate, so fetch a copy.
ROOT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ -d "$HERE/$SKILL_SUBPATH" ] && ROOT="$HERE"
fi
CLONE=""
if [ -z "$ROOT" ]; then
  CLONE="$(mktemp -d)"
  trap 'rm -rf "$CLONE"' EXIT
  echo "fetching $REPO_URL"
  git clone --depth 1 -q "$REPO_URL" "$CLONE/supervise"
  ROOT="$CLONE/supervise"
fi
SRC="$ROOT/$SKILL_SUBPATH"
[ -d "$SRC" ] || { echo "cannot find the skill at $SRC" >&2; exit 1; }

if [ "$SCOPE" = "project" ]; then
  DEST="$PWD/.claude/skills/supervise"
else
  DEST="$HOME/.claude/skills/supervise"
fi

mkdir -p "$(dirname "$DEST")"
[ -e "$DEST" ] && { echo "replacing the existing install at $DEST"; rm -rf "$DEST"; }
cp -R "$SRC" "$DEST"
find "$DEST/scripts" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} + 2>/dev/null || true

echo
echo "installed to $DEST"

# opencode discovers skills in ~/.claude/skills as well as its own directories, so
# the copy above is all it needs. Its slash commands live elsewhere.
if command -v opencode >/dev/null 2>&1; then
  if [ "$SCOPE" = "project" ]; then
    CMD_DEST="$PWD/.opencode/command/supervise.md"
  else
    CMD_DEST="$HOME/.config/opencode/command/supervise.md"
  fi
  if [ -f "$ROOT/$COMMAND_SUBPATH" ]; then
    mkdir -p "$(dirname "$CMD_DEST")"
    cp "$ROOT/$COMMAND_SUBPATH" "$CMD_DEST"
    echo "installed the opencode command to $CMD_DEST"
  fi
fi

echo
echo "Start a new session, then:"
echo "  /supervise <session-id> [<session-id> ...]"
echo
echo "To see your sessions and the tmux panes they map to:"
echo "  $DEST/scripts/sv-resolve.py --list"
