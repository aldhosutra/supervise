#!/usr/bin/env bash
# Type a SHORT line into a Claude pane, verify it arrived intact, then press Enter.
#   sv-send.sh <pane> "<text>"
# Long instructions must go in a file; send a pointer to it instead. tmux send-keys
# silently truncates long strings, so this refuses anything over the limit.
set -uo pipefail
PANE="${1:?usage: sv-send.sh <pane> <text>}"
TEXT="${2:?usage: sv-send.sh <pane> <text>}"
LIMIT="${SV_SEND_LIMIT:-120}"

if (( ${#TEXT} > LIMIT )); then
  echo "REFUSED: ${#TEXT} chars exceeds ${LIMIT}. send-keys truncates long input --" >&2
  echo "put the instruction in a file and send a one-line pointer to it." >&2
  exit 4
fi

state="$("$(dirname "$0")/sv-state.sh" "$PANE")" || true
if [[ "$state" == "GONE" ]]; then echo "REFUSED: pane $PANE is gone" >&2; exit 3; fi
if [[ "$state" == "PROMPT" ]]; then
  echo "REFUSED: $PANE is waiting on a dialog. Answering it is a human decision." >&2
  exit 2
fi

# Clear the input first: Claude Code renders suggested prompts there, and Enter
# without clearing would submit a suggestion nobody wrote.
tmux send-keys -t "$PANE" C-u; sleep 0.4
tmux send-keys -t "$PANE" -l "$TEXT"; sleep 1.2

got="$(tmux capture-pane -p -t "$PANE" -S -12 | tr -d '\n')"
if [[ "$got" != *"$TEXT"* ]]; then
  echo "VERIFY FAILED - the pane does not contain the full text. Enter NOT pressed." >&2
  tmux capture-pane -p -t "$PANE" -S -12 >&2
  exit 5
fi
echo "VERIFIED (${#TEXT} chars) -> $PANE"
tmux send-keys -t "$PANE" Enter
