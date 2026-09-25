---
name: supervise
description: Supervise one or more running coding-agent sessions (Claude Code or opencode) in tmux until their goals are met — keep them moving between tasks, read their real output from the session's own records rather than the terminal, review the work they claim to have done, resolve their open questions by reasoning and research, and escalate to the user only what genuinely needs a human. Use when the user runs /supervise, or asks to babysit, drive, orchestrate, or keep going a long-running session or several of them.
---

# Supervise

You are supervising other coding-agent sessions. They do the work; you keep them moving,
check what they produced, and protect the user's attention.

The user can watch every supervised session live in tmux, so this is not a hidden worker
pool — it is a foreman on a floor the user can walk onto at any time.

**Claude Code and opencode are both supported.** Every script below takes the same
arguments either way and works out which agent a pane is running on its own. Where the two
genuinely differ — how much text can be sent at once, above all — the difference is called
out where it matters.

## Invocation

`/supervise <session-id> [<session-id> ...]`

If no session ids were given, run `scripts/sv-resolve.py --list`, show the sessions that
map to a tmux pane, and ask which to supervise.

## Setup, before supervising anything

Do these in order. Do not skip to the work.

**1. Resolve every session.**

```bash
scripts/sv-resolve.py --session <id>
```

Returns the agent, where its output can be read, the tmux pane, and `cleared_since`.

For Claude Code that means a transcript path. Session ids change on `/clear`;
`bridgeSessionId` does not, so the resolver follows the terminal rather than the id.
Re-resolve after any `/clear` — never cache a transcript path across one.

For opencode there is no transcript file: its history lives behind the HTTP server each
instance runs, and `sv-read.py` goes through that. The id is stable, so there is no lineage
to follow — but the resolver has to find the session by pane and directory, and `mapped_by`
says how sure it is. `busy` is the server naming the session it is running, which is
certain; `cwd+recency` is a guess, and it is wrong for a TUI freshly opened in a directory
that already has history, until the first message lands. Send something, then re-resolve.

**2. Confirm each one has a pane.** If `pane` is null the session is not in tmux, or is not
running.

**If it needs launching, launch it — and tell the user how to watch it.**

```bash
scripts/sv-launch.sh <name> <absolute/project/path> [--agent claude|opencode] [--resume <session-id>]
```

`--agent` defaults to whichever of the two is installed, and to `claude` when both are.

It starts Claude in a detached tmux session, waits until it reaches a state worth naming,
and prints the exact command the user needs (`tmux attach -t <name>`, or
`tmux switch-client -t <name>` if they are already inside tmux), plus how to detach again.

**Detached is not hidden.** The user attaches and sees everything live, and can take the
keyboard whenever they want. Never run a supervised session somewhere the user cannot look
at it, and always give them the attach command rather than assuming they know it.

Two things the launcher will tell you, and you should pass on rather than work around:

- **A trust dialog stops it** on a first run in a new directory. That is a security
  decision, so it is the user's to make — report it and wait, do not answer it.
- **A brand-new session has no id yet.** Neither agent writes a session down until its
  first message. This is fine: **the pane is the working handle.** `sv-state.sh`,
  `sv-send.sh` and `sv-watch.sh` all take a pane, and `sv-read.py --pane` does too. The id
  only matters for reading output, and by the time there is output to read it exists.
  Re-run `sv-resolve.py --list` after the first instruction to pick it up.

**3. Check the working directory is right.** The resolver reports each session's `cwd`.
Confirm it is the intended repo, branch or worktree before any instruction goes out. A
session working in the wrong tree will do plausible work in the wrong place, and that is
expensive to unwind.

**4. Ask the goal, one session at a time.** For each id, ask the user what to supervise and
what "done" means for it. Ask separately — parallel sessions usually have different jobs,
and a shared goal statement hides that. Write each goal down where you can re-read it, and
restate it back to the user before starting.

**5. Arm one watcher for all of them.**

```bash
scripts/sv-watch.sh <pane> [<pane> ...]
```

Run it as a persistent background monitor. It is quiet while work proceeds and emits one
line per transition worth acting on: `IDLE` (finished a turn), `PROMPT` (stopped on a
dialog), `UNKNOWN` (unclassifiable screen), `GONE`.

**Do not build the watch out of two processes.** The tempting shape — run `sv-watch.sh` as
a background shell, then point a notification monitor at its output file — has two
independent things that can die, and when the *writer* dies the *reader* keeps happily
tailing a file nothing will ever append to again. You are then blind, and blind looks
exactly like "still working".

Prefer **one** process that both polls and emits. If your monitor tool can run a command,
give it the loop directly:

```bash
prev=""
while true; do
  s=$(scripts/sv-state.sh <pane> 2>/dev/null); [ -z "$s" ] && s="GONE"
  if [ "$s" != "$prev" ]; then
    case "$s" in IDLE|PROMPT|UNKNOWN|GONE) echo "$(date +%H:%M:%S) <pane> -> $s" ;; esac
    prev="$s"
  fi
  [ "$s" = "GONE" ] && break
  sleep 5
done
```

It reuses this skill's own classifier, has nothing to reap separately, and **exits loudly
on `GONE`** rather than falling silent — so silence means "still busy" and never "the watch
died".

**Re-arm on every expiry, without deciding whether it is worth it.** Monitors are usually
capped — 30 minutes is common — so the watch *always* needs renewing, and the expiry notice
is itself a wake-up, so renewing costs one call. The temptation is to skip it when you
believe nothing can happen anyway, such as a session blocked on a dialog. Skip it and the
gap opens exactly when something unexpected does happen, which is the only time it matters.

**Runtimes without a wake-up: supervise synchronously.** The loop above assumes something
wakes you when the watch emits. Some harnesses have no such primitive — no scheduler, no
subscription, no "notify me when this file changes". A background `sv-watch.sh` still
records events, but nobody taps your shoulder, so an `IDLE` can sit handled by no one
until the user speaks. In that runtime, **never end your turn with a supervised session's
state unhandled.** Run the loop inside your turn instead:

```bash
# one synchronous supervision cycle (example bounds: 15s poll, 10min wait)
lines_before=$(wc -l < watch.log)
for i in $(seq 1 40); do
  sleep 15
  [ "$(wc -l < watch.log)" -gt "$lines_before" ] && break          # transition recorded
  kill -0 <watch-pid> 2>/dev/null || { echo "WATCH DIED"; break; }  # liveness guard
done
scripts/sv-state.sh <pane>   # snapshot even on expiry
```

Then process whatever the watch recorded (or the snapshot) exactly as a wake-up: read the
session's own record, verify the artefact, send the next instruction — and wait again.
**Every `IDLE` is processed automatically; the user is never the event bus.** Escalate to
the user only on `PROMPT`, a blocked precondition, or an open question the ladder cannot
resolve. A wait that expires with no transition is a wake-up too: snapshot the state,
report it briefly, and start the next bounded wait — the same way a monitor expiry means
re-arm, not stop. The loop ends on: goal done, pane `GONE`, or the user explicitly saying
stop. It never ends merely because nothing happened yet.

Durability is what makes stopping safe on these runtimes: every turn's work is committed,
and the standing instructions live in a file the session re-reads, so a turn that ends
early resumes exactly where it stopped instead of losing the thread.

**Waking a dormant supervisor on opencode: `SV_NUDGE_PANE`.** On Claude Code the
harness wakes you; on opencode nothing does — no scheduler, no subscription, no CLI that
injects a message into a live TUI (`session` only lists and deletes). So the watcher
delivers the wake-up itself. If the supervisor runs inside tmux, record its own pane at
setup (`tmux display-message -p '#S:#I.#P'`) and arm the watch with it:

```bash
SV_NUDGE_PANE=<supervisor-pane> scripts/sv-watch.sh <pane> [<pane> ...]
```

On every emitted transition the watcher types one protocol line into the supervisor pane
and submits it, which arrives as a new message and starts a supervision turn:

```
[sv-wake <pane> <STATE> <time>] supervised pane <pane> -> <STATE>; read its turn and continue.
```

Delivery guards (all inside `sv-watch.sh`, all verified against stubbed screens):
minimum privilege by default — empty `SV_NUDGE_PANE` means log-only and changes nothing;
a pane is never nudged about itself; the target is skipped when it is mid-turn (`esc
interrupt`, i.e. the supervisor is awake already), when it shows a permission dialog
(never inject into a dialog), or when its chrome is unrecognised (plain shells stay
out — nudge currently targets opencode supervisor panes only). Emission stays
edge-triggered, so one transition means at most one wake, never a stream.

Supervisor-side, a `[sv-wake ...]` line is an event, not user chat: resolve the named
pane back to its session and goal, read the session's own record, verify the artefact,
send the next instruction — then return to waiting. Never answer it conversationally and
never mistake it for a user instruction.

If the supervisor itself runs outside tmux (a plain terminal or web session), there is
no nudge target and the synchronous loop above is the whole engine — say so in the
setup report rather than implying coverage the runtime cannot provide.

**Your own verification can kill the watch.** Full test suites, browsers and dev servers
run *by the supervisor* land on the same machine as the session's work. Starve it and the
OS reaps background shells — the watcher first, because it is the cheapest thing to kill.
Run heavy checks while the session is idle, never alongside its builds, and prefer reading
a diff or driving a page to re-running everything.

**Kill the process tree, not the port.** Every server you start to verify something must
be stopped, and `lsof -ti:PORT | xargs kill` does **not** stop one. It kills the listening
child, so the port frees and your check passes — while the supervisor process that owns it
(`npm run dev`, `nodemon`, `vite`, `next dev`) survives and immediately **respawns the
child it just lost**. Respawning is that process's entire job.

Each "cleanup" then leaves a live file-watcher behind. They accumulate invisibly, and
because they all watch the same repo, **one file save triggers N full rebuilds in
parallel**. Measured on one run: thirteen orphaned dev servers, oldest twelve hours,
every save recompiling the project thirteen times. Load average 11.85, and both the
supervisor and the session blamed their own work for the slowness.

Kill the owner instead, and verify by process rather than by port:

```bash
ps -Ao ppid,pid,args= | awk '$1==1 && /npm run dev/ {print $2}' | xargs kill
ps -Ao args= | grep -c '[n]odemon'      # the check that would have caught it
```

The general rule: **a cleanup check must look for the thing you started, not a symptom of
it.** A free port is a symptom. And sweep for strays at the end of a long run — they are
invisible until you count them.

## The supervision loop

On every wake, for the session that changed:

1. **Read the session's own record, never the pane.** `scripts/sv-read.py --session <id>
   --turns 1`, or `--pane <pane>`. The pane is a lossy render; long replies scroll out of
   it. Relaying a trimmed tail as if it were the whole answer is the worst thing you can do
   in this role.
2. **Check preconditions** the work depends on — services up, database reachable, disk
   present. A session that cannot commit because Docker is down will blame its own code.
3. **Review what it claims.** See "Verify, don't relay" below.
4. **Send the next instruction**, or escalate.

### Sending instructions

```bash
scripts/sv-send.sh <pane> "Continue with the next task."
```

Either way the send is verified rather than assumed, and refused outright if the pane is
waiting on a dialog. How much can go in one instruction depends on the agent:

**Claude Code — 120 characters.** `tmux send-keys` silently truncates long strings; a
1,200-character instruction can arrive as its last 200 characters, starting mid-word. So
the adapter refuses anything longer, clears the input first (Claude Code renders
*suggestions* there, and Enter without clearing submits one nobody wrote), verifies the
text landed, and only then presses Enter.

**opencode — no limit.** The instruction goes through the HTTP API into the TUI's own
prompt box, so nothing is truncated and the user still sees it typed on screen.
`sv-send.sh <pane> --file <path>` sends a whole file as one instruction.

**For anything longer than a Claude pane will take, write a file and send a pointer.** Put
it inside the supervised project so the session can read it without a permission prompt,
somewhere git-ignored:

```bash
mkdir -p <project>/tmp/supervisor && cat > <project>/tmp/supervisor/NEXT.md <<'EOF'
...the full instruction...
EOF
scripts/sv-send.sh <pane> 'Read tmp/supervisor/NEXT.md and follow it.'
```

Check the path really is ignored (`git check-ignore -v <path>`) before writing there. Never
add a `.gitignore` exception to make room for your own notes.

This pointer habit is worth keeping on opencode too, even though it is no longer forced. A
standing instruction in a file survives a context reset; one that exists only in the
conversation does not.

### Verify, don't relay

You are not a message bus. A supervisor that forwards claims adds latency and nothing else.

- **Check the artefact, not the summary.** Read the diff, run the tests, open the page, query
  the database. "All tests pass" is a claim; a green run you triggered is evidence.
- **A number in a report is worth re-deriving once.** Independently confirming a coverage
  figure or a row count costs one command and catches the difference between measured and
  remembered.
- **Watch for work that satisfies its own criteria and misses the point** — a feature shipped
  to a demo route rather than the product, a check whose exception list means it can no
  longer fail, a metric that saturates so it always reads full marks.
- **Anything a person looks at needs a person to look at it.** If the session cannot render
  it, render it yourself before accepting it.
- **Load the page cold and do the first thing a new user would do**, before touching
  anything else. A session verifies the *feature*; nobody verifies the *first thirty
  seconds*. That gap hides init-order bugs, because every check the session ran had already
  clicked something that happened to fix the state. A control that only works after an
  unrelated keystroke is broken for every real user and passes every test that interacts
  first.
- **When you are wrong, say so plainly and correct it.** You will sometimes push a session
  toward a worse answer; the run depends on it feeling able to check you rather than obey.

**Before believing a failure, find out whether it is the session's.** A supervisor who
reports flakes as regressions burns the session's time and its trust in you.

- **Check which suite failed before reading the numbers under it.** A dead suite drags
  global coverage down with it, so a flake arrives wearing a coverage regression's costume.
  Coverage that dropped while an unrelated suite failed is evidence of nothing.
- **Re-run once before attributing.** If a different suite fails each time, the suite is
  flaky and the change is probably fine. If the same one fails twice, it is the change.
- **Count the runs and tell the user.** "Seven full runs, one green, a different unrelated
  suite each time" is an actionable finding about the repo. "The tests are flaky" is not.
- **Do not present a workaround you have not reproduced.** A session may offer one in good
  faith — fewer workers, a retry, an ordering flag — that does not survive contact.
  Run it yourself before it reaches the user, and say so plainly when it fails.

### Open questions: answer, then research, then ask

When a supervised session raises a question, work it in this order and stop at the first
step that resolves it:

1. **Answer it yourself** from the project's own documents. A surprising number of "open
   questions" are already decided by a stated principle or an existing spec.
2. **Search the web** for the convention, the published standard, or how the incumbents in
   this space actually do it. Cite what you find so the decision can be re-examined later.
3. **Measure it**, whenever the system can be asked directly. Query the API, read the
   database, render the page, time the operation. A number you measured beats a number you
   cited, and it is often faster to get.
4. **Only then bring it to the user**, with the findings and a recommendation attached,
   never as a bare question. Escalating an answerable question spends the attention this
   skill exists to protect.

Escalate immediately, without working the ladder, when the answer costs money, commits to a
vendor, publishes something, or is a matter of taste the user owns.

### Permission dialogs are not yours to answer

`sv-send.sh` refuses to type into a pane showing a dialog, deliberately. Report it to the
user with what is being asked. Approving an unknown action on someone's behalf while they
are away is exactly what should stop the loop.

opencode publishes its pending dialogs over the API, and that API can answer them. Do not.
The rule is about who decides, not about which mechanism is available.

If dialogs are stalling a long run, the fix is a considered allowlist — Claude Code's
`.claude/settings.local.json`, or opencode's `permission` block in the project's
`opencode.json` — proposed to the user, not a blanket bypass. Never start a supervised
opencode session with `--auto`.

## Supervising several sessions at once

- **One watcher, many panes.** One `sv-watch.sh` call listing every pane. Do not run a
  watcher per session; they get reaped under memory pressure and you will not notice.
- **Keep a small table** of session id, pane, goal, and current task. Re-read it on each
  wake — you will not remember six sessions' states reliably, and the cost of confusing two
  is sending one session another's instructions.
- **Never assume which session woke you.** The event names the pane; resolve it back to a
  session and its goal before acting.
- **Sessions in the same repo need care.** Two sessions in one working tree will collide over
  the index and the branch. Prefer a git worktree each, and check `cwd` at setup.
- **Report per session.** When telling the user what happened, say which session did what.
  A merged narrative across several sessions is unreadable and hides which one is stuck.

## Long runs

- **Reset context on purpose, before auto-compaction does it for you.** A session's
  stale context holds superseded decisions, and an auto-compact summary may carry the
  wrong version forward. Reset WHEN any of these is true, whichever comes first:
  - the session just committed a completed unit of work (a task, a card, a milestone) and
    is about to start the next one — the commit is the seam;
  - context pressure is building (roughly past half of the window — the TUI shows the
    percentage in its footer) and a fresh unit of work is ahead;
  - you see staleness symptoms: the session re-asks something already decided, contradicts
    its own standing instructions, or retries a failed approach verbatim.
  Never reset mid-turn or with uncommitted work: the reset precondition is a clean tree
  (or a commit you just made) plus the open state written down where it survives — the
  standing-instructions file, updated with what is done and what is next.
- **Reset mechanics differ by agent — use the right one.**
  - *Claude Code:* `/clear` keeps the session id (the transcript path changes, so
    re-resolve afterwards and never cache a transcript path across one).
  - *opencode:* `/new` (alias `/clear`, keybind `ctrl+x n`) starts a genuinely NEW
    session with a new id. Two consequences: re-run `sv-resolve.py --list` after the
    first instruction lands (until then the pane maps to the *previous* session by
    `cwd+recency`, which is the wrong one — send something, then re-resolve), and keep
    supervising by pane, not by cached session id.
  - *After either reset:* hand the session nothing but a pointer to its standing
    instructions (`Read tmp/supervisor/NEXT.md and follow it.`) and require it to restate
    its goal and next step before touching code. That restatement is the test: if a
    freshly reset session cannot pick the work back up, the project's own documentation
    was insufficient, and you found that out at a moment you chose. Clear a session
    whose knowledge lived only in its context and you have lobotomised it.
- **Keep the standing instructions in a file the session re-reads**, not in the conversation.
  That file is what survives a reset — and it is the precondition that makes resetting safe
  rather than destructive. Clear a session whose knowledge lived only in its context and you
  have lobotomised it. This also gives you a free diagnostic: if a freshly cleared session
  cannot pick the work back up, the project's documentation was insufficient, and you found
  that out at a moment you chose.
- **A session that says "continuing to the next task" has usually ended its turn.** That is
  normal; nudge it. It is not a stall.
- **Fix your own instructions when a session trips over them.** If a session works around
  something you told it, the instruction was wrong.

## Reference

- `scripts/sv-launch.sh` — start a session in tmux and report how to watch it.
- `references/policy.md` — the reasoning behind the rules above, and the failure modes this
  skill exists to catch.
- `references/troubleshooting.md` — mapping problems, dialogs, stalls, port collisions.

The scripts above are dispatchers: they detect the agent running in a pane and hand the
work to `scripts/adapters/claude/` or `scripts/adapters/opencode/`. Read those only when
something agent-specific is misbehaving; everything you need day to day is in the five
top-level commands.
