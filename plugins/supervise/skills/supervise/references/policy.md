# Why the rules are the rules

Every rule in `SKILL.md` came from something going wrong across a long supervised run. This
file is the reasoning, so a future reader can tell which rules are load-bearing.

## Two agents, one model of supervision

The skill supports Claude Code and opencode. That is not two skills sharing a name: the
model — a pane the user can attach to, content read from the agent's own records rather
than the screen, a BUSY/IDLE/PROMPT state machine, dialogs left to the human — holds for
both, because it is a model of *watching someone work*, not of one program's terminal.

What differs is how much of that the agent tells you, and the adapters differ accordingly.
Claude Code offers a transcript file and a screen, so state has to be read off the screen.
opencode runs an HTTP server that publishes its state, its message history and its pending
permission queue, so nothing about it has to be inferred from pixels — but only when the
TUI was started with an explicit `--port`. A hand-opened TUI takes port `0` and listens on
no TCP socket at all, so its state falls back to the screen like Claude Code's. The
opencode adapter says UNKNOWN rather than guessing when neither the server nor the fallback
can answer.

Where an agent removes a constraint, the constraint goes — opencode has no 120-character
send limit because nothing truncates. Where an agent removes a *protection*, it stays:
opencode's API can answer a permission dialog, and the adapter still refuses to, because
that rule was never about what was technically possible.

## Who wakes the supervisor

A supervisor that yields its turn is only useful if something starts the next one. The two
agents differ here, and it is not a small difference. Claude Code has a monitor shell: you
hand it a command and its completion re-invokes you. opencode has nothing of the kind — no
scheduler, no subscription, no CLI that puts a message into a running TUI. So on opencode
the wake is delivered the way a person would deliver it: by typing into the supervisor's
own terminal.

That makes tmux part of the mechanism rather than a viewing convenience. An opencode
supervisor outside tmux has no pane to type into and, in 1.18.x, no server to post to
either, so it cannot be woken at all. Hence the capability probe, and hence refusing to
pretend: `sync` mode says out loud that the loop has to stay open.

Two things make a delivered wake trustworthy rather than hopeful.

**opencode queues a submitted prompt while it is busy.** Verified on 1.18.32 over both
`tmux send-keys` and the HTTP API. A wake sent mid-turn is therefore not lost; it waits its
turn. This is why the old guard that skipped a busy supervisor was a bug wearing the
costume of a protection — four panes transitioned, one wake arrived. The one state worth
refusing is a dialog, where the keystrokes land on the dialog and not the prompt; a
supervisor mid-dialog is a human's decision anyway.

**A keystroke is not a delivery.** The same lesson as `sv-send.sh`. The wake carries a
token, and the watcher looks for that token in the supervisor's own history before calling
it done. Unconfirmed means queued for retry, never reported as success. An edge-triggered
event that is silently dropped is unrecoverable — that transition will not fire again — so
this is exactly where guessing is not allowed.

## The pane lies twice

This is the Claude Code adapter's problem specifically, and it is why the opencode adapter
was built on the API instead.

**Outbound.** `tmux send-keys -l` with a long string silently delivers only part of it. A
~1,200-character instruction arrived as its last 232 characters, starting mid-word. The
receiving session did something reasonable with the fragment, and nothing anywhere reported
an error. Hence: a hard length limit, verify the typed text before Enter, and put long
content in a file.

**Inbound.** `capture-pane` returns what is in the scrollback, which for a long reply is its
tail. A supervisor reading the pane relayed a summary that was missing its first half — and
the missing half contained a correction to the supervisor's own work. Hence: the transcript
is the only source for content.

The pane is still the best signal for *state*, because a transcript cannot tell you a dialog
is on screen waiting for a keypress. So: pane for state, transcript for content.

## Suggested text in the input box is not input

Claude Code renders suggestions at the prompt. Pressing Enter without clearing submits
something nobody typed. The Claude adapter clears with `C-u` first; the opencode adapter
clears the prompt box over the API for the same reason.

## Send through the front door, not around it

opencode's API could post a message straight into a session, bypassing the TUI entirely.
The adapter instead types into the TUI's own prompt box and submits it, because the whole
premise of this skill is that the user can attach and see what happened. An instruction
that never appears on screen is a hidden worker pool with extra steps.

## Session ids are not stable; terminals are

`/clear` starts a new session id. A supervisor holding the old id reads a transcript that
has stopped moving and concludes the session has gone quiet. Every transcript line carries a
`bridgeSessionId` that is constant for the terminal's life, so the resolver tracks that and
returns whichever session is currently live in that lineage.

opencode has no such lineage — a reset there is simply a new session with a new id — but it
has the same failure in a different shape. Its sessions are only visible through the server
of the instance that owns them, and a freshly opened TUI holds a session that has not been
written down yet, so "the newest session in this directory" names the *previous* run. A
supervisor that trusted that would read a conversation that stopped moving yesterday and
conclude the session had gone quiet: the same wrong conclusion, reached by another route.
Hence `mapped_by`, which distinguishes the server naming a running session from the
resolver guessing, and hence `sv-send.sh` reporting the id its prompt actually reached
rather than the one it expected.

## The failure this kind of work keeps producing

Across one long run, the same defect appeared again and again in different clothes:

- a guard that could never fire, so it never reported anything
- a scoring component that saturated, so it always contributed full marks
- a database call that failed on every invocation for six work packages, silently
- a formatter written, tested, and never handed to the thing it formatted
- a drawing engine no mouse could actually draw with
- an accessibility setting honoured for exactly one render
- an endpoint that existed for four packages with no caller, so nothing was ever saved

In each case a unit test asserted the function's output and nothing asserted that anything
called it. **Assert on what the collaborator was handed, not on what the function returns.**
That single check would have caught all seven.

The supervisor's version of the same mistake is accepting a report because it is
well-written. A confident summary and a working system are independent variables.

## Anything a person looks at needs a person to look at it

Twice, a session reported a screen as working when it was not: an axis showing dates that
was supposed to show relative offsets, and a toolbar rendering at correct coordinates in the
DOM while being invisible on screen. Both passed their tests. Both were caught in seconds by
looking.

If the supervised session cannot render its own work — no browser, no display — the
supervisor should render it. Headless Chromium over the DevTools protocol is enough, and
"the environment cannot do this" deserves one check before it is believed. Once, that claim
turned out to be a stale process of the supervisor's own holding the debugging port.

## Tests that cannot fail

A leak check with an exception list has stopped being a leak check. Two real examples: a
scan for category names matched ordinary prose (`"Nothing in Lumenory is financial advice"`
contains a category called `nothing`), and a whole-word scan missed a real occurrence
because rendering concatenated it with the word before it. The fix is to make the check
precise, never to reword the product so the check passes.

The supervisor's job is to ask, of any guard: *what would make this fail?* If there is no
answer, it is decoration.

## Flakes are not weather

A test that fails once and passes afterwards will fail again at the worst moment, and the
tempting response is to re-run rather than diagnose. That is how a suite starts being
negotiated with. Every flake found in that run had a real cause — a wall-clock assertion in
a parallel suite, a timeout that hid a lost keystroke caused by an event listener
reattaching on every render. Diagnose within a bounded budget; if it resists, record the
exact failure and what was ruled out, so the next occurrence starts from evidence.

## Whose decision is it

The supervisor decides engineering questions and researches product ones. It does not decide
anything that spends the user's money, commits them to a vendor, publishes something, or is
a matter of their taste. It never answers a permission dialog on their behalf.

The test is not "am I able to decide this" but "would the user be annoyed to discover I
decided it". Getting that boundary right is most of what makes an unattended run tolerable.
