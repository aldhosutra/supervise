#!/usr/bin/env bash
# Watch one or more supervised panes and emit a line whenever one changes state.
# Works for Claude Code and opencode alike - sv-state.sh handles the difference.
# Designed as the command of a persistent monitor: quiet while work proceeds,
# one event per transition worth acting on.
#
#   sv-watch.sh work:0.0 work:0.1 api:0.0
#
# On opencode the supervisor is woken by this process, which types a wake-up into
# the supervisor's own tmux pane. Give it that pane (and, when known, the
# supervisor's server) and it delivers:
#
#   SV_NUDGE_PANE=sup:0.0 SV_NUDGE_URL=http://127.0.0.1:4601 \
#     sv-watch.sh work:0.0 work:0.1
#
# Delivery is not fire-and-forget. Each transition is queued and only cleared
# once sv-nudge.py confirms the wake landed in the supervisor's own message
# history, so a dropped insert is retried next cycle instead of vanishing.
# opencode queues a submitted prompt even mid-turn, so the supervisor does not
# have to be idle to be woken; a dialog is the one state that holds delivery,
# because there the keystrokes would go to the dialog rather than the prompt.
#
# Portable to bash 3.2 (the version macOS ships) - no associative arrays.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
INTERVAL="${SV_POLL_SECONDS:-30}"
IDLE_CONFIRM="${SV_IDLE_CONFIRM:-2}"        # consecutive idle polls before reporting
UNKNOWN_CONFIRM="${SV_UNKNOWN_CONFIRM:-4}"
NUDGE_PANE="${SV_NUDGE_PANE:-}"             # supervisor's own tmux pane; empty = log-only
NUDGE_URL="${SV_NUDGE_URL:-}"               # supervisor's opencode server; empty = no confirm
NUDGE_CONFIRM="${SV_NUDGE_CONFIRM:-8}"
if [ -n "${SV_NUDGE_URL:-}" ]; then export SV_NUDGE_URL; fi

(( $# )) || { echo "usage: sv-watch.sh <pane> [pane...]" >&2; exit 64; }

panes=("$@")
n=${#panes[@]}
prev=(); idle=(); unk=()
pend_on=(); pend_state=(); pend_token=()
for ((i = 0; i < n; i++)); do
  prev[$i]=INIT; idle[$i]=0; unk[$i]=0
  pend_on[$i]=0; pend_state[$i]=""; pend_token[$i]=""
done
sup_prev=""
sup_ready=1
seq=0

queue() { # queue <index> <STATE> — remember the latest transition for delivery
  [ -n "$NUDGE_PANE" ] || return 0
  [ "${panes[$1]}" != "$NUDGE_PANE" ] || return 0   # never nudge a pane about itself
  seq=$(( seq + 1 ))
  pend_on[$1]=1
  pend_state[$1]="$2"
  pend_token[$1]="svw-$(date +%s)-$1-$seq"
}

deliver() { # deliver <index> — one attempt; keep the event queued unless confirmed
  [ "${pend_on[$1]}" = 1 ] || return 0
  [ -n "$NUDGE_PANE" ] || return 0
  [ "$sup_ready" = 1 ] || return 0
  p="${panes[$1]}"
  text="[sv-wake $p ${pend_state[$1]} $(date +%H:%M:%S) ${pend_token[$1]}] supervised pane $p -> ${pend_state[$1]}; read its turn and continue."
  if [ -n "$NUDGE_URL" ]; then
    python3 "$HERE/sv-nudge.py" --pane "$NUDGE_PANE" --token "${pend_token[$1]}" \
      --text "$text" --url "$NUDGE_URL" --confirm "$NUDGE_CONFIRM" >/dev/null 2>&1
  else
    python3 "$HERE/sv-nudge.py" --pane "$NUDGE_PANE" --token "${pend_token[$1]}" \
      --text "$text" --confirm "$NUDGE_CONFIRM" >/dev/null 2>&1
  fi
  rc=$?
  case "$rc" in
    0) pend_on[$1]=0 ;;            # delivered (confirmed when a URL was given)
    3) : ;;                        # supervisor on a dialog: hold the event
    4) pend_on[$1]=0 ;;            # supervisor pane gone; the loop stops below
    5) : ;;                        # unconfirmed: try again next cycle
    *) pend_on[$1]=0 ;;
  esac
}

while true; do
  # Watch the supervisor itself first. Its state decides whether wakes may be
  # delivered at all, and a supervisor stuck on a dialog is worth saying out loud
  # rather than leaving the queue silently held.
  if [ -n "$NUDGE_PANE" ]; then
    ss="$("$HERE/sv-state.sh" "$NUDGE_PANE" 2>/dev/null)" || true
    [ -n "$ss" ] || ss=GONE
    case "$ss" in
      PROMPT)
        if [ "$sup_prev" != PROMPT ]; then
          echo "SUPERVISOR-PROMPT $NUDGE_PANE — supervisor paused on a dialog; wakes held until it is answered"
        fi
        sup_ready=0 ;;
      GONE)
        echo "SUPERVISOR-GONE $NUDGE_PANE — supervisor pane is gone; stopping"
        exit 7 ;;
      *) sup_ready=1 ;;
    esac
    sup_prev="$ss"
  fi

  for ((i = 0; i < n; i++)); do
    p="${panes[$i]}"
    s="$("$HERE/sv-state.sh" "$p" 2>/dev/null)" || true
    [ -n "$s" ] || s=GONE
    case "$s" in
      IDLE)
        idle[$i]=$(( idle[$i] + 1 )); unk[$i]=0
        if [ "${idle[$i]}" -eq "$IDLE_CONFIRM" ]; then
          echo "IDLE $p — finished a turn, ready for the next instruction"
          queue "$i" "IDLE"
        fi ;;
      PROMPT)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != PROMPT ]; then
          echo "PROMPT $p — stopped on a dialog, needs a human decision"
          queue "$i" "PROMPT"
        fi ;;
      GONE)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != GONE ]; then
          echo "GONE $p — pane has disappeared"
          queue "$i" "GONE"
        fi ;;
      UNKNOWN)
        idle[$i]=0; unk[$i]=$(( unk[$i] + 1 ))
        if [ "${unk[$i]}" -eq "$UNKNOWN_CONFIRM" ]; then
          echo "UNKNOWN $p — screen cannot be classified, look at it"
          queue "$i" "UNKNOWN"
        fi ;;
      *)
        idle[$i]=0; unk[$i]=0 ;;
    esac
    prev[$i]="$s"
  done

  for ((i = 0; i < n; i++)); do deliver "$i"; done

  sleep "$INTERVAL"
done
