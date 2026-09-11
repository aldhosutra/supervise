---
description: Supervise running Claude Code or opencode sessions in tmux until their goals are met
agent: build
---

Use the `supervise` skill: call `skill({ name: "supervise" })` and follow it.

Sessions or panes to supervise (may be empty):

$ARGUMENTS

If nothing was given, run the skill's `scripts/sv-resolve.py --list`, show the sessions
that map to a tmux pane, and ask which of them to supervise.
