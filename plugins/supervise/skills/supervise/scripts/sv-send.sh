#!/usr/bin/env bash
# Give a supervised pane its next instruction, whichever agent is running in it.
#
#   sv-send.sh <pane> "<text>"
#   sv-send.sh <pane> --file <path>     (opencode only)
#
# What arrives intact differs by agent, so the limits do too:
#
#   Claude Code - typed in with tmux send-keys, which silently truncates. The
#     adapter refuses anything over 120 characters; put long instructions in a
#     file inside the supervised project and send a one-line pointer to it.
#   opencode - submitted through its HTTP API, so length is not a constraint
#     and --file sends a whole instruction in one go.
#
# Both refuse to type into a pane that is waiting on a dialog.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PANE="${1:?usage: sv-send.sh <pane> <text> | sv-send.sh <pane> --file <path>}"
shift

agent="$(python3 "$HERE/lib/sv_detect.py" --pane "$PANE" --field agent 2>/dev/null)" || agent=""

case "$agent" in
  claude)
    if [ "${1:-}" = "--file" ]; then
      echo "REFUSED: --file is not available for Claude Code - send-keys truncates." >&2
      echo "Write the instruction into the supervised project and send a pointer:" >&2
      echo "  sv-send.sh $PANE 'Read tmp/supervisor/NEXT.md and follow it.'" >&2
      exit 64
    fi
    exec "$HERE/adapters/claude/send.sh" "$PANE" "${1:?usage: sv-send.sh <pane> <text>}" ;;
  opencode)
    exec python3 "$HERE/adapters/opencode/send.py" "$PANE" "$@" ;;
  "")
    echo "REFUSED: no supervisable agent is running in pane $PANE" >&2; exit 3 ;;
  *)
    echo "unsupported agent: $agent" >&2; exit 64 ;;
esac
