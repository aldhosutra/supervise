---
description: Supervise running Claude Code or opencode sessions in tmux until their goals are met
agent: build
---

Use the `supervise` skill: call `skill({ name: "supervise" })` and follow it.

Sessions or panes to supervise (may be empty):

$ARGUMENTS

If nothing was given, run the skill's one-call discovery, `scripts/sv-floor.py`, show the
agent panes it lists, and ask which of them to supervise.
