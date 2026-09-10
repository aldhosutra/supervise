#!/usr/bin/env bash
# Install the supervise skill for the current user.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/.claude/skills/supervise"
DEST="${1:-$HOME/.claude/skills}/supervise"

[ -d "$SRC" ] || { echo "cannot find $SRC — run this from the repo root" >&2; exit 1; }

for tool in tmux python3; do
  command -v "$tool" >/dev/null 2>&1 || echo "warning: $tool not found; the skill needs it" >&2
done

mkdir -p "$(dirname "$DEST")"
if [ -e "$DEST" ]; then
  echo "replacing the existing install at $DEST"
  rm -rf "$DEST"
fi
cp -R "$SRC" "$DEST"
chmod +x "$DEST"/scripts/* 2>/dev/null || true

echo "installed to $DEST"
echo
echo "Start a new Claude Code session, then:  /supervise <session-id> [<session-id> ...]"
echo "To see your sessions and their panes:   $DEST/scripts/sv-resolve.py --list"
