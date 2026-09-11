#!/usr/bin/env bash
# Start a supervised session in a detached tmux session, then print exactly what
# the user must run to watch it.
#
#   sv-launch.sh <name> <project-path> [--agent claude|opencode]
#                                      [--resume <session-id>] [--agent-args "..."]
#
# Detached does not mean hidden: the user attaches and sees everything live, and can
# take the keyboard at any moment. Never run a supervised session somewhere the user
# cannot look at it.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

NAME="${1:?usage: sv-launch.sh <name> <project-path> [--agent claude|opencode] [--resume <id>] [--agent-args \"...\"]}"
PATH_ARG="${2:?usage: sv-launch.sh <name> <project-path> [--agent claude|opencode] [--resume <id>] [--agent-args \"...\"]}"
shift 2

AGENT=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --agent)       AGENT="${2:?--agent needs claude or opencode}"; shift 2 ;;
    --resume)      PASS+=(--resume "${2:?--resume needs a session id}"); shift 2 ;;
    --agent-args)  PASS+=(--agent-args "${2:?--agent-args needs a value}"); shift 2 ;;
    --claude-args) PASS+=(--agent-args "${2:?--claude-args needs a value}"); shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

# Default to whichever agent is actually installed, so a machine with only one
# of them needs no flag. When both are present, ask rather than guess - the
# choice belongs to whoever is being supervised.
if [ -z "$AGENT" ]; then
  has_claude=0; has_opencode=0
  command -v claude   >/dev/null 2>&1 && has_claude=1
  command -v opencode >/dev/null 2>&1 && has_opencode=1
  if [ "$has_claude" = 1 ] && [ "$has_opencode" = 1 ]; then
    AGENT=claude
  elif [ "$has_opencode" = 1 ]; then
    AGENT=opencode
  else
    AGENT=claude
  fi
fi

case "$AGENT" in
  claude)   exec "$HERE/adapters/claude/launch.sh" "$NAME" "$PATH_ARG" "${PASS[@]+"${PASS[@]}"}" ;;
  opencode) exec "$HERE/adapters/opencode/launch.sh" "$NAME" "$PATH_ARG" "${PASS[@]+"${PASS[@]}"}" ;;
  *) echo "unknown agent: $AGENT (expected claude or opencode)" >&2; exit 64 ;;
esac
