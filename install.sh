#!/usr/bin/env bash
# Install the supervise skill.
#
#   ./install.sh                     from a clone
#   curl -fsSL <raw-url> | bash      from anywhere (clones itself)
#   ./install.sh --project           into ./.claude/skills of the current repo
#
# Most people should prefer the plugin route instead, which handles updates:
#   /plugin marketplace add aldhosutra/supervise
#   /plugin install supervise@aldhosutra
set -euo pipefail

REPO_URL="https://github.com/aldhosutra/supervise.git"
SKILL_SUBPATH="plugins/supervise/skills/supervise"
SCOPE="user"
[ "${1:-}" = "--project" ] && SCOPE="project"

for tool in git python3 tmux; do
  command -v "$tool" >/dev/null 2>&1 || echo "warning: $tool not found — the skill needs it" >&2
done

# Work out where the skill is coming from. When piped through bash there is no
# script on disk to locate, so fetch a copy.
SRC=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ -d "$HERE/$SKILL_SUBPATH" ] && SRC="$HERE/$SKILL_SUBPATH"
fi
CLONE=""
if [ -z "$SRC" ]; then
  CLONE="$(mktemp -d)"
  trap 'rm -rf "$CLONE"' EXIT
  echo "fetching $REPO_URL"
  git clone --depth 1 -q "$REPO_URL" "$CLONE/supervise"
  SRC="$CLONE/supervise/$SKILL_SUBPATH"
fi
[ -d "$SRC" ] || { echo "cannot find the skill at $SRC" >&2; exit 1; }

if [ "$SCOPE" = "project" ]; then
  DEST="$PWD/.claude/skills/supervise"
else
  DEST="$HOME/.claude/skills/supervise"
fi

mkdir -p "$(dirname "$DEST")"
[ -e "$DEST" ] && { echo "replacing the existing install at $DEST"; rm -rf "$DEST"; }
cp -R "$SRC" "$DEST"
chmod +x "$DEST"/scripts/* 2>/dev/null || true

echo
echo "installed to $DEST"
echo
echo "Start a new Claude Code session, then:"
echo "  /supervise <session-id> [<session-id> ...]"
echo
echo "To see your sessions and the tmux panes they map to:"
echo "  $DEST/scripts/sv-resolve.py --list"
