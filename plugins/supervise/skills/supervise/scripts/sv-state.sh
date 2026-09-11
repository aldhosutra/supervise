#!/usr/bin/env bash
# Classify what a supervised pane is doing, whichever agent is running in it.
# State only - never read content here.
#   sv-state.sh <pane>            e.g. sv-state.sh work:0.1
# Prints one of: BUSY IDLE PROMPT UNKNOWN GONE
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PANE="${1:?usage: sv-state.sh <tmux-pane>}"

agent="$(python3 "$HERE/lib/sv_detect.py" --pane "$PANE" --field agent 2>/dev/null)" || agent=""

case "$agent" in
  claude)   exec "$HERE/adapters/claude/state.sh" "$PANE" ;;
  opencode) exec python3 "$HERE/adapters/opencode/state.py" "$PANE" ;;
  "")
    # No agent process under the pane. Either the pane is gone, or something
    # else is running there - both mean there is nothing to supervise.
    tmux capture-pane -p -t "$PANE" >/dev/null 2>&1 || { echo GONE; exit 3; }
    echo GONE; exit 3 ;;
  *) echo "unsupported agent: $agent" >&2; echo UNKNOWN; exit 4 ;;
esac
