# Troubleshooting

## A session resolves but `pane` is null

The session is not running inside tmux, or its process has exited. Check with
`sv-resolve.py --list`: sessions without a pane are transcripts on disk, not live terminals.

If the session *is* running in tmux but is not being matched, the resolver's routes all
failed. For Claude Code it matches on `claude --resume <id>` in the process command line
first, then on the pane's working directory. A session started plainly as `claude` in a
directory that holds several sessions can be ambiguous — the fix is to give the pane a
distinct working directory (a git worktree per session is good practice anyway), or to
restart it with `--resume`.

## An opencode pane resolves but `base_url` is null

Every opencode TUI runs an HTTP server, and that is how this skill reads and drives it. The
port is random unless the process was started with `--port`, and the fallback is to find it
with `lsof`. If both fail there is nothing to talk to: restart the session with
`sv-launch.sh`, which always pins a port.

The same symptom appears when opencode is running somewhere the `lsof` call cannot see the
process — inside a container, say, or under a different user.

## An opencode session is resolved as `cwd+recency` and reads the wrong conversation

`mapped_by` says how the session was identified. `busy` is the server naming the session it
is running right now, which is certain. `cwd+recency` is the fallback: the most recently
updated session in that directory.

The fallback is wrong in one specific case. A TUI opened in a directory that already has
history shows an *empty new* session, which opencode does not write down until its first
message — so the newest stored session is the previous run. Until you send something, the
resolver names that older session. Send an instruction and re-resolve; `sv-send.sh` handles
this itself and reports the id the prompt actually landed in.

The same applies if someone switches session by hand inside the TUI. Re-resolve rather than
trusting an id you cached earlier.

## Two sessions in the same repo

They will collide over the git index, the branch, and any dev server port. Give each a git
worktree:

```bash
git worktree add ../<name> -b <branch>
tmux new-session -d -s <name> -c "$(cd ../<name> && pwd)"
```

This also makes the resolver's directory-matching unambiguous.

## The watcher keeps dying

Background shells get reaped under memory pressure, and a per-session watcher is an easy
target. Run **one** watcher for all panes, as a persistent monitor rather than a detached
shell, and check it is still alive when a session has been quiet for longer than its work
should take. Silence and "still running" look identical; that is the failure to design
against.

## A pane reports UNKNOWN

The screen matches none of the known states. Usual causes: a first-run trust dialog
("Do you trust the files in this folder?"), a crash, a full-screen diff or editor, or a
program in the pane that is not a supervisable agent. Look at it rather than guessing —
`UNKNOWN` exists precisely so the supervisor cannot silently treat it as idle.

For opencode, `UNKNOWN` additionally means the server could not be reached *and* the screen
could not be classified. State normally comes from the API there, so an `UNKNOWN` is a sign
the instance is wedged or the port moved, not that the screen is unusual.

## A pane reports PROMPT and stays there

A permission dialog is waiting. `sv-send.sh` refuses to type into it by design. Tell the
user what is being asked and let them answer.

opencode also exposes the pending request over its API, including an endpoint that would
answer it. That does not make it yours to answer — the rule is about who decides.

If dialogs are stalling a long unattended run, propose a specific allowlist — Claude Code's
`.claude/settings.local.json` (git-ignored, per-machine), or the `permission` block in the
project's `opencode.json` — with the denies for destructive commands kept. Never reach for
opencode's `--auto`, which approves everything not explicitly denied.

Note that a broad deny rule can catch more than intended: `Bash(rm -rf /*)` also matches
`rm -rf /tmp/anything`, which looks like a refusal of a harmless command.

## `sv-send.sh` says VERIFY FAILED

**Claude Code.** The typed text did not appear intact. Almost always the string is near the
length limit, or contains characters the pane renders differently. Shorten it, or put the
content in a file and send a pointer. Do not raise `SV_SEND_LIMIT` to force it through —
the limit is the protection.

**opencode.** The prompt was submitted but no matching message appeared in any session
within the confirmation window. Either the TUI was on a modal that swallowed it, or the
session is slower to register than `SV_SEND_CONFIRM_SECONDS` allows. Look at the pane
before resending: a duplicated instruction is worse than a late one.

## The session says it is continuing but nothing happens

Normal. A turn ends when the agent stops calling tools, even if its last sentence said
"continuing to the next task". Nudge it. This is not a stall and does not need escalating.

## Headless browser checks fail to start

Only one process can hold a DevTools debugging port. Check nothing already holds it before
concluding the environment cannot render:

```bash
lsof -ti:9222
```

A stale instance — possibly the supervisor's own from an earlier check — is the usual cause.
Use a distinct `--user-data-dir` per run.

## A file edit silently did nothing

Exact-string replacement against a formatted file (Prettier, gofmt, black) matches nothing
once the formatter has re-padded a table or rewrapped a block, and most replace functions do
not error when the pattern is absent. Verify every edit landed rather than trusting the
call. This one recurs often enough to be worth a habit rather than a rule.

## How many sessions can I supervise at once?

Nothing in the tool caps it. Polling 100 panes takes about 0.62s, so a thousand would cost
roughly six seconds per cycle. Two things outside it bind first.

**Memory.** A Claude Code session holds 275 to 390 MB resident. That works out to about 8 on
an 8 GB laptop, 20 on 16 GB, and 100 or more on a workstation. Past that the machine swaps
and everything slows down together, including the supervisor.

**Review capacity**, which matters more. Past some number the supervisor stops reading diffs
and starts sampling, and it will not announce the moment it crossed over. A sampling
supervisor is doing dispatch, which native subagents already handle better and more cheaply.
Six sessions genuinely reviewed are worth more than sixty glanced at.
