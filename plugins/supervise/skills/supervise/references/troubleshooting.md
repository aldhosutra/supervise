# Troubleshooting

## A session resolves but `pane` is null

The session is not running inside tmux, or its process has exited. Check with
`sv-resolve.py --list`: sessions without a pane are transcripts on disk, not live terminals.

If the session *is* running in tmux but is not being matched, the resolver's two routes both
failed. It matches on `claude --resume <id>` in the process command line first, then on the
pane's working directory. A session started plainly as `claude` in a directory that holds
several sessions can be ambiguous — the fix is to give the pane a distinct working directory
(a git worktree per session is good practice anyway), or to restart it with `--resume`.

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
non-Claude program in the pane. Look at it rather than guessing — `UNKNOWN` exists precisely
so the supervisor cannot silently treat it as idle.

## A pane reports PROMPT and stays there

A permission dialog is waiting. `sv-send.sh` refuses to type into it by design. Tell the
user what is being asked and let them answer. If dialogs are stalling a long unattended run,
propose a specific allowlist in the supervised project's `.claude/settings.local.json`
(git-ignored, per-machine) — with the denies for destructive commands kept.

Note that a broad deny rule can catch more than intended: `Bash(rm -rf /*)` also matches
`rm -rf /tmp/anything`, which looks like a refusal of a harmless command.

## `sv-send.sh` says VERIFY FAILED

The typed text did not appear intact. Almost always the string is near the length limit, or
contains characters the pane renders differently. Shorten it, or put the content in a file
and send a pointer. Do not raise `SV_SEND_LIMIT` to force it through — the limit is the
protection.

## The session says it is continuing but nothing happens

Normal. A Claude turn ends when it stops calling tools, even if its last sentence said
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
