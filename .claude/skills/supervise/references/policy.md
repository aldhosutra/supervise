# Why the rules are the rules

Every rule in `SKILL.md` came from something going wrong across a long supervised run. This
file is the reasoning, so a future reader can tell which rules are load-bearing.

## The pane lies twice

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
something nobody typed. `sv-send.sh` clears with `C-u` first.

## Session ids are not stable; terminals are

`/clear` starts a new session id. A supervisor holding the old id reads a transcript that
has stopped moving and concludes the session has gone quiet. Every transcript line carries a
`bridgeSessionId` that is constant for the terminal's life, so the resolver tracks that and
returns whichever session is currently live in that lineage.

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
