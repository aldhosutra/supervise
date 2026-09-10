#!/usr/bin/env bash
# Classify what a Claude Code pane is doing. State only - never read content here.
#   sv-state.sh <pane>            e.g. sv-state.sh work:0.1
# Prints one of: BUSY IDLE PROMPT UNKNOWN GONE
set -uo pipefail
PANE="${1:?usage: sv-state.sh <tmux-pane>}"
LINES="${SV_CAPTURE_LINES:--45}"

text="$(tmux capture-pane -p -t "$PANE" -S "$LINES" 2>/dev/null)" || { echo GONE; exit 3; }

# PROMPT is tested first: a dialog can be on screen while a spinner still shows,
# and the reverse order hides the thing that actually needs a human.
if grep -qE 'Do you want|Would you like|❯ +[0-9]+\.|Yes, and switch to|Enter to confirm' <<<"$text"; then
  echo PROMPT; exit 2
fi
if grep -qF 'esc to interrupt' <<<"$text"; then echo BUSY; exit 1; fi
if grep -qE 'auto mode on|manual mode on|accept edits on|bypass permissions|plan mode on|for shortcuts' <<<"$text"; then
  echo IDLE; exit 0
fi
# Never silently treat an unclassifiable screen as idle or busy - a supervisor that
# cannot tell what it is looking at must say so rather than guess.
echo UNKNOWN; exit 4
