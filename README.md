# /supervise

A Claude Code skill for supervising other Claude Code sessions running in tmux — one of
them or six — until their goals are met.

You launch the sessions in tmux and can watch them work. `/supervise` keeps them moving
between tasks, reviews what they actually produced, resolves their open questions by
reasoning and research, and interrupts you only for the things that genuinely need a human.

```
/supervise 9513c215-a113-4847-b516-465f807b3465 4f2b1a08-...
```

It asks what each session's job is and what "done" means for it, checks each one is in the
right working directory, then runs until those goals are met.

## What makes it different from spawning workers

Most tmux orchestration for Claude Code spawns hidden background workers, reads their
output by scraping the terminal, and reports whether they are alive. This does the opposite
on all three counts.

| | Typical orchestrator | `/supervise` |
| --- | --- | --- |
| Sessions | Spawns its own, hidden | Attaches to ones you launched and can watch |
| Reading output | `capture-pane`, scraped | The session's transcript on disk |
| Terminal | Used for content and state | State only — content never comes from it |
| Identity | The session id you were given | `bridgeSessionId`, so it survives `/clear` |
| Its job | Dispatch and liveness | Review the work, unblock, escalate |
| Questions | Passed to you | Answered, then researched, then asked |

The pane lies in both directions, and both were observed rather than theorised.
`send-keys` silently truncated a 1,200-character instruction to its last 232 characters,
mid-word. `capture-pane` returned the tail of a long reply whose missing first half held a
correction to the supervisor's own work. So: **the terminal is the signal, the transcript is
the content.**

## Install

```bash
git clone https://github.com/aldhosutra/supervise.git
cd supervise && ./install.sh
```

That copies the skill to `~/.claude/skills/supervise`, making `/supervise` available in
every project. Restart Claude Code, or start a new session, to pick it up.

To install for one project only, copy `.claude/skills/supervise` into that project's
`.claude/skills/`.

## Requirements

`tmux`, `python3`, and Claude Code. macOS and Linux. No dependencies to install.

## The tools

The skill drives four scripts, which are also useful on their own.

```bash
# Start a session in tmux and print how to watch it
scripts/sv-launch.sh work ~/code/myproject

# Every Claude session, with the tmux pane it maps to
scripts/sv-resolve.py --list

# Resolve one session to its live transcript and pane (follows /clear)
scripts/sv-resolve.py --session <id>

# What is that pane doing?  BUSY | IDLE | PROMPT | UNKNOWN | GONE
scripts/sv-state.sh work:0.0

# What did it actually say?  (from the transcript, not the screen)
scripts/sv-read.py --session <id> --turns 2

# Type an instruction, verified, and press Enter only if it arrived intact
scripts/sv-send.sh work:0.0 "Continue with the next task."

# Watch several panes; one line per state change worth acting on
scripts/sv-watch.sh work:0.0 work:0.1 api:0.0
```

`sv-launch.sh` starts the session detached and tells you exactly how to attach — detached
is not hidden, and you can take the keyboard at any point. If a trust dialog is waiting it
says so and stops, because that is your decision to make rather than the supervisor's.

`sv-send.sh` refuses strings over 120 characters, refuses to type into a pane showing a
permission dialog, and clears the input first so a rendered *suggestion* is never submitted
as if you had written it.

## How sessions are identified

A session's id changes every time you run `/clear`. Every transcript line also carries a
`bridgeSessionId`, which is stable for the life of the terminal. `sv-resolve.py` reads that,
so you can hand it any id from a lineage and it finds whichever session is live now:

```
cse_01Pn48ur...  →  b47163fa → d8c95e98 → 2a11f9a9 → 9513c215
                    (one terminal, three /clears, four session ids)
```

Panes are matched to sessions by `claude --resume <id>` on the process command line, falling
back to the pane's working directory. Give each session its own git worktree and the match
is unambiguous.

## What it will not do

- Answer a permission dialog for you.
- Spend your money, commit you to a vendor, or publish anything.
- Decide a question that is a matter of your taste.
- Relay a claim it has not checked.

## Licence

MIT. See [LICENSE](LICENSE).
