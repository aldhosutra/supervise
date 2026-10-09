#!/usr/bin/env bash
# Arm the wake channel in one command. This is the default move for every async
# supervisor; there is no reason to hand-roll sv-watch.sh or to poll.
#
#   sv-arm.sh <pane> [pane...]
#
# What it does depends on how this supervisor can be woken (sv-capability.py):
#
#   monitor     Claude Code — the harness wakes you; there is nothing to arm.
#   tmux-nudge  opencode in tmux — starts sv-watch.sh in its own tmux session,
#               watching every pane you list, and registers it for the guard.
#   sync        nothing can wake you — tells you how to restore the channel, or
#               how to acknowledge the degraded synchronous path (SV_SYNC_OK=1).
#
# After this returns in an async mode: END YOUR TURN. The watcher starts your
# next one on a transition.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CAP="$HERE/sv-capability.py"
GUARD="$HERE/lib/sv_guard.py"

(( $# )) || { echo "usage: sv-arm.sh <pane> [pane...]" >&2; exit 64; }

caps="$(python3 "$CAP")"
mode="$(python3 -c 'import json,sys;print(json.load(sys.stdin).get("mode",""))' <<<"$caps")"
own="$(python3  -c 'import json,sys;print(json.load(sys.stdin).get("pane") or "")' <<<"$caps")"
url="$(python3  -c 'import json,sys;print(json.load(sys.stdin).get("supervisor_url") or "")' <<<"$caps")"

case "$mode" in
  monitor)
    echo "mode: monitor — Claude Code wakes you through its own monitor."
    echo "Nothing to arm. When you are waiting, END YOUR TURN; the monitor re-invokes you."
    exit 0 ;;

  sync)
    echo "mode: sync — nothing can wake this supervisor, so a watcher would be log-only." >&2
    echo "Restore the wake channel instead of polling:" >&2
    echo "  * relaunch the supervisor inside tmux (sv-launch.sh pins the port):" >&2
    echo "      scripts/sv-launch.sh <name> <dir> --agent opencode" >&2
    echo "  * or, if you must run the degraded synchronous path, acknowledge it out loud:" >&2
    echo "      export SV_SYNC_OK=1" >&2
    exit 2 ;;

  *)
    session="${SV_WATCH_SESSION:-sv-watch}"
    log="${SV_WATCH_LOG:-$PWD/sv-watch.log}"
    panes="$*"

    if [ -z "$own" ]; then
      echo "WARNING: no supervisor pane found (\$TMUX_PANE unset); wakes cannot be delivered." >&2
    fi

    tmux kill-session -t "$session" 2>/dev/null || true
    env_part="SV_NUDGE_PANE=$own"
    [ -n "$url" ] && env_part="$env_part SV_NUDGE_URL=$url"
    cmd="$env_part SV_WATCH_SESSION=$session $HERE/sv-watch.sh $panes 2>&1 | tee -a '$log'"
    tmux new-session -d -s "$session" -c "$PWD" "$cmd"

    sleep 1
    live="$(python3 "$GUARD" status 2>/dev/null \
            | python3 -c 'import json,sys;print(json.load(sys.stdin).get("watchers_live",0))' 2>/dev/null || echo '?')"

    echo "mode: tmux-nudge"
    echo "armed: $session watching: $panes"
    echo "wake target: ${own:-<none>}"
    if [ -n "$url" ]; then
      echo "delivery: confirmed via $url"
    else
      echo "delivery: unconfirmed (no server) — optionally relaunch with 'sv-launch.sh ... --agent opencode'"
    fi
    echo "registered watchers: $live"
    echo
    echo "Watch it:  tmux attach -t $session     (or: tmux switch-client -t $session)"
    echo "NOW END YOUR TURN — the watcher wakes you on the next transition."
    ;;
esac
