#!/usr/bin/env bash
# Classify what a supervised pane is doing, whichever agent is running in it.
# State only - never read content here.
#   sv-state.sh <pane>            e.g. sv-state.sh work:0.1
# Prints one of: BUSY IDLE PROMPT UNKNOWN GONE
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PANE="${1:?usage: sv-state.sh <tmux-pane>}"

# Policy guard. sv-state.sh is the primitive a supervisor is tempted to hand-poll
# with; refuse that instead of enabling it. The watcher sets SV_WATCHER=1 and
# internal tools (sv-floor, tests) set SV_GUARD=off, so neither pays this cost.
if [ "${SV_WATCHER:-}" != "1" ] && [ "${SV_GUARD:-}" != "off" ] \
   && [ -f "$HERE/lib/sv_guard.py" ]; then
  _guard_msg="$(python3 "$HERE/lib/sv_guard.py" check --primitive sv-state.sh 2>&1)"; _guard_rc=$?
  if [ "$_guard_rc" -ne 0 ]; then printf '%s\n' "$_guard_msg" >&2; exit 9; fi
fi

agent="$(python3 "$HERE/lib/sv_detect.py" --pane "$PANE" --field agent 2>/dev/null)" || agent=""

case "$agent" in
  claude)   exec "$HERE/adapters/claude/state.sh" "$PANE" ;;
  opencode) exec python3 "$HERE/adapters/opencode/state.py" "$PANE" ;;
  other)
    # A live agent we can see but cannot classify. UNKNOWN, never GONE: a pane
    # that is running something is not a pane that has disappeared.
    tmux capture-pane -p -t "$PANE" >/dev/null 2>&1 || { echo GONE; exit 3; }
    echo UNKNOWN; exit 4 ;;
  "")
    # No agent process under the pane. Either the pane is gone, or something
    # else is running there - both mean there is nothing to supervise.
    tmux capture-pane -p -t "$PANE" >/dev/null 2>&1 || { echo GONE; exit 3; }
    echo GONE; exit 3 ;;
  *) echo "unsupported agent: $agent" >&2; echo UNKNOWN; exit 4 ;;
esac
