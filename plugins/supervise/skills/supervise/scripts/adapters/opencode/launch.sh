#!/usr/bin/env bash
# Start a supervised opencode session in a detached tmux session, then print
# exactly what the user must run to watch it.
#
#   launch.sh <name> <project-path> [--resume <session-id>] [--agent-args "..."]
#
# Detached does not mean hidden: the user attaches and sees everything live, and
# can take the keyboard at any moment.
#
# The port is pinned rather than left random. opencode picks a free port for its
# server on startup and never announces it; pinning it here means every later
# call can find the session without hunting through lsof.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LIB="$HERE/../../lib"

NAME="${1:?usage: launch.sh <name> <project-path> [--resume <id>] [--agent-args \"...\"]}"
PATH_ARG="${2:?usage: launch.sh <name> <project-path> [--resume <id>] [--agent-args \"...\"]}"
shift 2
RESUME=""; EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume)     RESUME="${2:?--resume needs a session id}"; shift 2 ;;
    --agent-args) EXTRA="${2:?--agent-args needs a value}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

command -v tmux >/dev/null 2>&1 || { echo "tmux is not installed" >&2; exit 127; }
command -v opencode >/dev/null 2>&1 || { echo "opencode is not installed" >&2; exit 127; }
[ -d "$PATH_ARG" ] || { echo "no such directory: $PATH_ARG" >&2; exit 66; }
DIR="$(cd "$PATH_ARG" && pwd)"

if tmux has-session -t "$NAME" 2>/dev/null; then
  echo "A tmux session named '$NAME' already exists. Pick another name, or attach to it:"
  echo "  tmux attach -t $NAME"
  exit 65
fi

PORT="${SV_OPENCODE_PORT:-}"
if [ -z "$PORT" ]; then
  PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
fi

# Note which sessions this directory already has. opencode opens an empty new
# session that it does not write down until the first message, so "the newest
# session here" would name the previous run - and reporting a stale id is worse
# than reporting none.
BEFORE="$(python3 - "$DIR" <<'PYEOF' 2>/dev/null || true
import os, subprocess, sys
raw = subprocess.run(["opencode", "session", "list", "--format", "json"],
                     capture_output=True, text=True, cwd=sys.argv[1]).stdout
import json
try:
    data = json.loads(raw or "[]")
except ValueError:
    data = []
print("\n".join(sorted(s["id"] for s in data if isinstance(s, dict) and "id" in s)))
PYEOF
)"

CMD="opencode --port $PORT"
[ -n "$RESUME" ] && CMD="$CMD --session $RESUME"
[ -n "$EXTRA" ] && CMD="$CMD $EXTRA"

tmux new-session -d -s "$NAME" -x "${SV_COLS:-200}" -y "${SV_ROWS:-50}" -c "$DIR"
tmux send-keys -t "$NAME:0.0" "cd $(printf '%q' "$DIR") && $CMD" Enter

# Wait for it to reach a state we can name, rather than guessing at a fixed sleep.
state=UNKNOWN
for _ in $(seq 1 40); do
  sleep 2
  state="$(python3 "$HERE/state.py" "$NAME:0.0" 2>/dev/null)" || true
  [ -n "$state" ] || state=UNKNOWN
  [ "$state" = IDLE ] || [ "$state" = PROMPT ] && break
done

echo
echo "tmux session '$NAME' is running opencode in:"
echo "  $DIR"
echo "  server: http://127.0.0.1:$PORT"
echo
echo "To watch it live:"
if [ -n "${TMUX:-}" ]; then
  echo "  tmux switch-client -t $NAME     # you are already inside tmux"
else
  echo "  tmux attach -t $NAME"
fi
echo "  (detach again with ctrl-b then d — the session keeps running)"
echo

if [ "$state" = PROMPT ]; then
  cat <<'MSG'
It is waiting on a dialog and cannot start until someone answers it — a provider
login or a permission request.

That is the user's decision rather than mine — attach with the command above and
answer it. Tell me once you have, and I will pick up supervising.
MSG
  exit 2
fi

if [ "$state" != IDLE ]; then
  echo "It has not reached a ready state yet (currently: $state). Attach and look at it"
  echo "before assuming it is working."
  exit 4
fi

# opencode creates a session on the first message, not at startup, so a brand-new
# pane has no id to report yet. The pane is the working handle until it does:
# sv-state.sh, sv-send.sh and sv-watch.sh all take a pane, and sv-read.py takes
# one too.
sid="$(python3 "$HERE/resolve.py" --pane "$NAME:0.0" --field active_session_id 2>/dev/null)" || sid=""
if [ -n "$sid" ] && printf '%s\n' "$BEFORE" | grep -qx "$sid"; then
  sid=""   # that id was already here before we started - not this session's
fi

if [ -n "$sid" ]; then
  echo "Ready. Session id: $sid"
else
  echo "Ready. It has no session id yet — opencode creates one on the first message."
  echo "Use the pane ($NAME:0.0) as the handle until then; the id appears in:"
  echo "  sv-resolve.py --list"
fi
