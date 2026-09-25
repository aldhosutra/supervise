#!/usr/bin/env bash
# Watch one or more supervised panes and emit a line whenever one changes state.
# Works for Claude Code and opencode alike - sv-state.sh handles the difference.
# Designed as the command of a persistent monitor: quiet while work proceeds,
# one event per transition worth acting on.
#
#   sv-watch.sh work:0.0 work:0.1 api:0.0
#
# Portable to bash 3.2 (the version macOS ships) - no associative arrays.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
INTERVAL="${SV_POLL_SECONDS:-30}"
IDLE_CONFIRM="${SV_IDLE_CONFIRM:-2}"        # consecutive idle polls before reporting
UNKNOWN_CONFIRM="${SV_UNKNOWN_CONFIRM:-4}"
# Optional nudge target: the supervisor's own tmux pane (e.g. SV_NUDGE_PANE=sup:0.0).
# On opencode there is no harness primitive that wakes a dormant supervisor the way
# Claude Code's monitor shell does, so the watcher delivers the wake-up itself: on
# every emitted transition it types a protocol line into the supervisor pane and
# submits it, which arrives as a new message and starts a supervision turn.
# Empty (default) means log-only: transitions go to stdout and the supervisor is
# expected to be running its synchronous wait loop (see SKILL.md).

nudge() { # nudge <watched-pane> <STATE>
  [ -n "${SV_NUDGE_PANE:-}" ] || return 0
  [ "${SV_NUDGE_PANE}" != "$1" ] || return 0   # never nudge a pane about itself
  screen="$(tmux capture-pane -p -t "$SV_NUDGE_PANE" -S -15 2>/dev/null)" || return 0
  flat="$(printf '%s' "$screen" | tr '\n' ' ' | tr -s ' ')"
  case "$flat" in
    *"esc interrupt"*|*"esc to interrupt"*) return 0 ;;  # supervisor mid-turn: awake already
    *"Permission required"*|*"Allow once"*) return 0 ;;  # dialog showing: never inject
    *"ctrl+p"*) ;;                                       # opencode prompt chrome, idle
    *) return 0 ;;                                       # unknown chrome: stay out
  esac
  tmux send-keys -t "$SV_NUDGE_PANE" \
    "[sv-wake $1 $2 $(date +%H:%M:%S)] supervised pane $1 -> $2; read its turn and continue." Enter
}

(( $# )) || { echo "usage: sv-watch.sh <pane> [pane...]" >&2; exit 64; }

panes=("$@")
n=${#panes[@]}
prev=(); idle=(); unk=()
for ((i = 0; i < n; i++)); do prev[$i]=INIT; idle[$i]=0; unk[$i]=0; done

while true; do
  for ((i = 0; i < n; i++)); do
    p="${panes[$i]}"
    s="$("$HERE/sv-state.sh" "$p" 2>/dev/null)" || true
    [ -n "$s" ] || s=GONE
    case "$s" in
      IDLE)
        idle[$i]=$(( idle[$i] + 1 )); unk[$i]=0
        if [ "${idle[$i]}" -eq "$IDLE_CONFIRM" ]; then
          echo "IDLE $p — finished a turn, ready for the next instruction"
          nudge "$p" "IDLE"
        fi ;;
      PROMPT)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != PROMPT ]; then
          echo "PROMPT $p — stopped on a dialog, needs a human decision"
          nudge "$p" "PROMPT"
        fi ;;
      GONE)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != GONE ]; then
          echo "GONE $p — pane has disappeared"
          nudge "$p" "GONE"
        fi ;;
      UNKNOWN)
        idle[$i]=0; unk[$i]=$(( unk[$i] + 1 ))
        if [ "${unk[$i]}" -eq "$UNKNOWN_CONFIRM" ]; then
          echo "UNKNOWN $p — screen cannot be classified, look at it"
          nudge "$p" "UNKNOWN"
        fi ;;
      *)
        idle[$i]=0; unk[$i]=0 ;;
    esac
    prev[$i]="$s"
  done
  sleep "$INTERVAL"
done
