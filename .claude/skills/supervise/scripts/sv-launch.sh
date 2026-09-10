#!/usr/bin/env bash
# Start a supervised Claude session in a detached tmux session, then print exactly
# what the user must run to watch it.
#
#   sv-launch.sh <name> <project-path> [--resume <session-id>] [--claude-args "..."]
#
# Detached does not mean hidden: the user attaches and sees everything live, and can
# take the keyboard at any moment. Never run a supervised session somewhere the user
# cannot look at it.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

NAME="${1:?usage: sv-launch.sh <name> <project-path> [--resume <id>] [--claude-args \"...\"]}"
PATH_ARG="${2:?usage: sv-launch.sh <name> <project-path> [--resume <id>] [--claude-args \"...\"]}"
shift 2
RESUME=""; EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume)      RESUME="${2:?--resume needs a session id}"; shift 2 ;;
    --claude-args) EXTRA="${2:?--claude-args needs a value}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

command -v tmux >/dev/null 2>&1 || { echo "tmux is not installed" >&2; exit 127; }
[ -d "$PATH_ARG" ] || { echo "no such directory: $PATH_ARG" >&2; exit 66; }
DIR="$(cd "$PATH_ARG" && pwd)"

if tmux has-session -t "$NAME" 2>/dev/null; then
  echo "A tmux session named '$NAME' already exists. Pick another name, or attach to it:"
  echo "  tmux attach -t $NAME"
  exit 65
fi

CMD="claude"
[ -n "$RESUME" ] && CMD="$CMD --resume $RESUME"
[ -n "$EXTRA" ] && CMD="$CMD $EXTRA"

# Record which transcripts already exist for this project. A fresh session is the
# one that appears afterwards - matching on "most recent in this directory" would
# happily return a session from an earlier run in the same folder.
SLUG="$(printf '%s' "$DIR" | sed 's|/|-|g')"
PROJDIR="$HOME/.claude/projects/$SLUG"
BEFORE="$(ls "$PROJDIR"/*.jsonl 2>/dev/null | xargs -n1 basename 2>/dev/null | sort || true)"

tmux new-session -d -s "$NAME" -x "${SV_COLS:-200}" -y "${SV_ROWS:-50}" -c "$DIR"
tmux send-keys -t "$NAME:0.0" "cd $(printf '%q' "$DIR") && $CMD" Enter

# Wait for it to reach a state we can name, rather than guessing at a fixed sleep.
state=UNKNOWN
for _ in $(seq 1 40); do
  sleep 2
  state="$("$HERE/sv-state.sh" "$NAME:0.0" 2>/dev/null)" || true
  [ -n "$state" ] || state=UNKNOWN
  [ "$state" = IDLE ] || [ "$state" = PROMPT ] && break
done

echo
echo "tmux session '$NAME' is running Claude in:"
echo "  $DIR"
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
It is waiting on a dialog and cannot start until someone answers it. On a first run in
a new directory this is the "do you trust the files in this folder?" prompt.

That is a security decision, so it is yours to make rather than mine — attach with the
command above and answer it. Tell me once you have, and I will pick up supervising.
MSG
  exit 2
fi

if [ "$state" != IDLE ]; then
  echo "It has not reached a ready state yet (currently: $state). Attach and look at it"
  echo "before assuming it is working."
  exit 4
fi

# The new session is whichever transcript was not there before.
sid=""
for _ in $(seq 1 15); do
  AFTER="$(ls "$PROJDIR"/*.jsonl 2>/dev/null | xargs -n1 basename 2>/dev/null | sort || true)"
  sid="$(comm -13 <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER") 2>/dev/null \
        | head -1 | sed 's/\.jsonl$//')"
  [ -n "$sid" ] && break
  sleep 2
done

if [ -n "$sid" ]; then
  echo "Ready. Session id: $sid"
else
  echo "Ready. It has not written a transcript yet, so it has no session id to report."
  echo "Send it something and its id will appear in: sv-resolve.py --list"
fi
