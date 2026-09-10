#!/usr/bin/env bash
# Watch one or more Claude panes and emit a line whenever one changes state.
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
        fi ;;
      PROMPT)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != PROMPT ]; then
          echo "PROMPT $p — stopped on a dialog, needs a human decision"
        fi ;;
      GONE)
        idle[$i]=0; unk[$i]=0
        if [ "${prev[$i]}" != GONE ]; then
          echo "GONE $p — pane has disappeared"
        fi ;;
      UNKNOWN)
        idle[$i]=0; unk[$i]=$(( unk[$i] + 1 ))
        if [ "${unk[$i]}" -eq "$UNKNOWN_CONFIRM" ]; then
          echo "UNKNOWN $p — screen cannot be classified, look at it"
        fi ;;
      *)
        idle[$i]=0; unk[$i]=0 ;;
    esac
    prev[$i]="$s"
  done
  sleep "$INTERVAL"
done
