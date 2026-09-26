---
name: supervise
description: Supervise one or more running coding-agent sessions (Claude Code or opencode) in tmux until their goals are met — keep them moving between tasks, read their real output from the session's own records rather than the terminal, review the work they claim to have done, resolve their open questions by reasoning and research, and escalate to the user only what genuinely needs a human. Use when the user runs /supervise, or asks to babysit, drive, orchestrate, or keep going a long-running session or several of them.
---

# Supervise

You are supervising other coding-agent sessions. They do the work; you keep them moving,
check what they produced, and protect the user's attention.

The user can watch every supervised session live in tmux, so this is not a hidden worker
pool — it is a foreman on a floor the user can walk onto at any time.

**Claude Code and opencode are both supported.** Every script takes the same arguments
either way and works out which agent a pane runs on its own. Where the two genuinely
differ — how much text can be sent at once, above all — the difference is called out.

## Invocation

`/supervise <session-id> [<session-id> ...]`

If no ids were given, run `scripts/sv-floor.py` — one call listing every agent pane with
its harness, state and session — and ask which to supervise. Do not go spelunking through
the process tree or the agent's database to work that out; that is the whole discovery step.

## Setup, before supervising anything

Do these in order. Do not skip to the work.

**1. Resolve every session.** `scripts/sv-resolve.py --session <id>` returns the agent,
where its output can be read, the tmux pane, and `cleared_since`.

- *Claude Code:* a transcript path. Session ids change on `/clear` but `bridgeSessionId`
  does not, so the resolver follows the terminal. Re-resolve after any `/clear` — never
  cache a transcript path across one.
- *opencode:* no transcript file — history lives behind its HTTP server (a TUI serves one
  only when started with `--port`), and `sv-read.py` reads it. The id is stable, but the
  resolver finds it by pane and directory, and `mapped_by` says how sure it is: `busy` is
  the server naming the session it is running, which is certain; `cwd+recency` is a guess,
  wrong for a TUI opened in a directory that already has history until the first message
  lands. Send something, then re-resolve.

A fresh pane in a directory that already has history can resolve as `-` or a `db-guess`,
because several sessions then look identical. Sending it one line fixes that: `sv-send.sh`
binds the pane to the session it created, so afterwards `sv-resolve.py --pane` is exact and
`sv-read.py --pane <pane> --wait` reads the next reply without guessing or hand-polling.

Each pane's harness is detected from the process it runs (`scripts/sv_detect.py --all`):
`claude`, `opencode`, or `other`. Claude Code and opencode get full support — a pinned-port
opencode reads over its server, a hand-opened one over its SQLite database, and a mixed
floor works with one watcher. An `other` agent (codex, aider, gemini, …) is best-effort over
the pane only: `UNKNOWN` state, unverified sends, lossy reads. See `references/troubleshooting.md`.

**2. Confirm each one has a pane.** A null `pane` means it is not in tmux, or not running.

**If it needs launching, launch it — and tell the user how to watch it.**
`scripts/sv-launch.sh <name> <absolute/project/path> [--agent claude|opencode]
[--resume <session-id>]`. `--agent` defaults to whichever is installed, and to `claude`
when both are. It starts the session detached, waits for a state worth naming, and prints
the exact attach command (`tmux attach -t <name>`, or `tmux switch-client -t <name>` if
they are already inside tmux) plus how to detach.

**Detached is not hidden.** The user attaches and sees everything live, and can take the
keyboard at any moment. Never run a supervised session somewhere the user cannot look at
it, and always give them the attach command rather than assuming they know it.

Two things to pass on rather than work around:

- **A trust dialog stops it** on a first run in a new directory. That is a security
  decision: report it and wait, do not answer it.
- **A brand-new session has no id yet** — neither agent writes one down until the first
  message. **The pane is the working handle:** `sv-state.sh`, `sv-send.sh`, `sv-watch.sh`
  and `sv-read.py --pane` all take a pane. Re-run `sv-resolve.py --list` after the first
  instruction to pick the id up.

**3. Check the working directory is right.** The resolver reports each session's `cwd`;
confirm it is the intended repo, branch or worktree before any instruction goes out. A
session working in the wrong tree does plausible work in the wrong place, and that is
expensive to unwind.

**4. Ask the goal, one session at a time.** For each id, ask what to supervise and what
"done" means. Ask separately — parallel sessions usually have different jobs, and a shared
goal hides that. Write each down where you can re-read it, and restate it back before
starting.

**5. Decide how you will be woken, then arm one watcher for all of them.**

`scripts/sv-capability.py` reports the wake mode, and that is the whole algorithm:

- **`monitor`** — a Claude Code supervisor. The harness wakes you.
- **`tmux-nudge`** — an opencode supervisor inside tmux. The watcher wakes you by typing
  into your own pane.
- **`sync`** — nothing can wake you: opencode outside tmux, or an unknown harness.
  **Warn the user and offer the synchronous loop** below. For opencode the fix is to
  relaunch the supervisor inside tmux, where `sv-launch.sh` pins the port that makes wakes
  verifiable.

```bash
SV_NUDGE_PANE=<your-own-pane> SV_NUDGE_URL=<your-server> \
  scripts/sv-watch.sh <pane> [<pane> ...]
```

`sv-capability.py` prints both `pane` (yours, from `$TMUX_PANE`) and `supervisor_url`, so
the two arguments are usually a copy-paste. Leave them off and the watch records
transitions but wakes no one — log-only, the safe default.

Run it as a persistent background monitor. It is quiet while work proceeds and emits one
line per transition worth acting on: `IDLE`, `PROMPT`, `UNKNOWN`, `GONE`, plus
`SUPERVISOR-PROMPT` and `SUPERVISOR-GONE` about your own pane.

**Do not build the watch out of two processes.** A background `sv-watch.sh` plus a
separate monitor tailing its output is two things that can die, and when the *writer* dies
the *reader* tails a dead file forever. You are then blind, and blind looks exactly like
"still working". Prefer **one** process that both polls and emits; if your monitor tool can
run a command, give it the loop directly:

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

**Re-arm on every expiry, without deciding whether it is worth it.** Monitors are usually
capped (30 minutes is common). The temptation is to skip renewal when nothing can happen
anyway, such as a session blocked on a dialog; skip it and the gap opens exactly when
something unexpected does.

**Runtimes without a wake-up: supervise synchronously.** This is `sync` mode. A background
`sv-watch.sh` still records events, but nobody taps your shoulder. Here, **never end your
turn with a supervised session's state unhandled.** Run the loop inside your turn:

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

Then process what the watch recorded, or the snapshot, exactly as a wake-up. **Every
`IDLE` is processed automatically; the user is never the event bus.** Escalate only on
`PROMPT`, a blocked precondition, or an open question the ladder cannot resolve. A wait
that expires with no transition is a wake-up too: snapshot and start the next bounded
wait. The loop ends on goal done, pane `GONE`, or the user saying stop — never merely
because nothing happened yet.

**Progress reports are not a reason to end your turn.** Ending your turn IS pausing
supervision: the next event sits unhandled until the user speaks. Do not yield to say work
is proceeding. The only yields are: goal done, `PROMPT` or a blocked precondition, an open
question the ladder cannot resolve, or the user addressing you directly — and after
answering, resume the wait loop in the same run. A silent supervisor with a live watch is
working; a chatty one that keeps yielding is stalled.

Durability makes stopping safe: every turn's work is committed, and the standing
instructions live in a file the session re-reads, so an early end resumes where it stopped.

**Waking a dormant supervisor on opencode.** On Claude Code the harness wakes you. On
opencode nothing does — no scheduler, no subscription, no CLI that injects a message into
a live TUI (`session` only lists and deletes). So the watcher delivers the wake itself,
into your own tmux pane. That is why **an opencode supervisor has to be inside tmux**: the
pane is the only channel that reaches it. Outside tmux there is no pane and, in 1.18.x, no
discoverable server either — only a TUI started with `--port` listens on TCP, which
`sv-launch.sh` sets and a hand-opened TUI does not.

On a transition the watcher types one line into your pane and submits it:

```
[sv-wake <pane> <STATE> <time> <token>] supervised pane <pane> -> <STATE>; read its turn and continue.
```

**Deliver while busy; confirm, don't assume.** opencode queues a submitted prompt even
mid-turn (verified on 1.18.32 over both `send-keys` and the API), so a busy supervisor
still receives the wake, in order, once its turn ends. A guard that skips a busy supervisor
is therefore a bug, not a safety net: it drops the event silently, and emission is
edge-triggered so it never fires again. What is fatal to inject into is a dialog, where the
keystrokes land on the dialog and not the prompt. That is the one state delivery holds for.

Delivery is queued and confirmed, not fire-and-forget:

- each transition is queued with a unique token in the line;
- the watcher sends it, then looks for the token in your message history (`SV_NUDGE_URL`).
  Not found means it stays queued and is retried next cycle;
- the watcher also watches **your** pane: `SUPERVISOR-PROMPT` holds every wake while you
  are on a dialog (and says so, once); `SUPERVISOR-GONE` stops it loudly instead of
  guessing.

Without `SV_NUDGE_URL` the wake is still sent, just unconfirmed — best effort, and
`sv-capability.py` flags it. Prefer a pinned port so wakes are provable rather than
hoped-for.

**Run the watcher in its own tmux session, not your shell**, so a supervisor restart or a
heavy turn cannot take it down:

```bash
tmux new-session -d -s sv-watch -c "$PWD" \
  "SV_NUDGE_PANE=<own> SV_NUDGE_URL=<url> scripts/sv-watch.sh <pane> ... 2>&1 | tee -a sv-watch.log"
```

Supervisor-side, a `[sv-wake ...]` line is an event, not user chat: resolve the named pane
back to its session and goal, read the session's own record, verify the artefact, send the
next instruction — then return to waiting. Never answer it conversationally and never
mistake it for a user instruction; the trailing token is the watcher's delivery receipt.

If the supervisor runs outside tmux, `sv-capability.py` reports `sync`: say so plainly and
offer the synchronous loop rather than implying coverage you do not have.

**Housekeeping.** Run heavy checks (test suites, browsers, dev servers) while the session
is idle, never alongside its builds — a starved machine reaps background shells, the
watcher first. Stop every server you start by **process, not port**
(`lsof -ti:PORT | xargs kill` only frees the port; the owner respawns the child), and sweep
for strays at the end of a long run. Detail in `references/troubleshooting.md`.

## The supervision loop

On every wake, for the session that changed:

1. **Read the session's own record, never the pane.** `scripts/sv-read.py --session <id>
   --turns 1`, or `--pane <pane>`. Add `--wait` to block until the turn's reply is complete
   first — that is the whole "wait for the reply" step, never a hand-written poll loop. The
   pane is a lossy render and long replies scroll out of it; relaying a trimmed tail as the
   whole answer is the worst thing you can do in this role.
2. **Check preconditions** the work depends on — services up, database reachable, disk
   present. A session that cannot commit because Docker is down will blame its own code.
3. **Review what it claims.** See "Verify, don't relay".
4. **Send the next instruction**, or escalate.

### Sending instructions

```bash
scripts/sv-send.sh <pane> "Continue with the next task."
```

The send is verified rather than assumed, and refused outright if the pane is on a dialog.
How much fits depends on the agent:

- **Claude Code — 120 characters.** `tmux send-keys` silently truncates long strings, so a
  long instruction can arrive as its last few words, starting mid-word. The adapter refuses
  anything longer, clears the input first (Claude Code renders *suggestions* there, and
  Enter without clearing submits one nobody wrote), verifies the text landed, and only then
  presses Enter.
- **opencode — no limit.** The instruction goes through the HTTP API into the TUI's own
  prompt box, so nothing is truncated and the user still sees it typed on screen.
  `sv-send.sh <pane> --file <path>` sends a whole file as one instruction.

**For anything longer than a Claude pane will take, write a file and send a pointer.** Put
it inside the supervised project so the session reads it without a permission prompt,
somewhere git-ignored:

```bash
mkdir -p <project>/tmp/supervisor && cat > <project>/tmp/supervisor/NEXT.md <<'EOF'
...the full instruction...
EOF
scripts/sv-send.sh <pane> 'Read tmp/supervisor/NEXT.md and follow it.'
```

Check the path really is ignored (`git check-ignore -v <path>`) before writing there; never
add a `.gitignore` exception to make room for your own notes. Keep the pointer habit on
opencode too, even though it is no longer forced — a standing instruction in a file
survives a context reset; one that exists only in the conversation does not.

### Verify, don't relay

You are not a message bus; a supervisor that forwards claims adds latency and nothing else.

- **Check the artefact, not the summary.** Read the diff, run the tests, open the page,
  query the database. "All tests pass" is a claim; a green run you triggered is evidence.
- **Re-derive a number once.** Independently confirming a coverage figure or row count
  costs one command and catches measured versus remembered.
- **Watch for work that satisfies its own criteria and misses the point** — a feature
  shipped to a demo route rather than the product, a check whose exception list means it
  can no longer fail, a metric that saturates so it always reads full marks.
- **Anything a person looks at needs a person to look at it.** If the session cannot render
  it, render it yourself before accepting it.
- **Load the page cold and do the first thing a new user would do**, before touching
  anything else. A session verifies the feature; nobody verifies the first thirty seconds,
  and a control that works only after an unrelated keystroke passes every test that
  interacts first.
- **When you are wrong, say so plainly and correct it.** The run depends on the session
  feeling able to check you rather than obey.

**Before believing a failure, find out whether it is the session's.** A supervisor who
reports flakes as regressions burns the session's time and its trust.

- **Check which suite failed before reading the numbers under it.** A dead suite drags
  global coverage down with it, so a flake arrives wearing a coverage regression's costume.
- **Re-run once before attributing.** A different suite failing each time means the suite is
  flaky; the same one failing twice means it is the change.
- **Count the runs and tell the user.** "Seven runs, one green, a different unrelated suite
  each time" is actionable; "the tests are flaky" is not.
- **Do not present a workaround you have not reproduced.** Run it yourself before it reaches
  the user, and say plainly when it fails.

### Open questions: answer, then research, then ask

When a supervised session raises a question, stop at the first step that resolves it:

1. **Answer it yourself** from the project's own documents — many "open questions" are
   already decided by a stated principle or an existing spec.
2. **Search the web** for the convention, the published standard, or how the incumbents do
   it. Cite what you find so the decision can be re-examined.
3. **Measure it** wherever the system can be asked directly. A number you measured beats a
   number you cited, and is often faster to get.
4. **Only then bring it to the user**, with findings and a recommendation attached, never
   as a bare question. Escalating an answerable question spends the attention this skill
   exists to protect.

Escalate immediately, without working the ladder, when the answer costs money, commits to a
vendor, publishes something, or is a matter of the user's taste.

### Permission dialogs are not yours to answer

`sv-send.sh` refuses to type into a pane showing a dialog, deliberately. Report it to the
user with what is being asked; approving an unknown action on someone's behalf while they
are away is exactly what should stop the loop.

opencode publishes its pending dialogs over the API, and that API can answer them. Do not.
The rule is about who decides, not about which mechanism is available.

If dialogs are stalling a long run, the fix is a considered allowlist — Claude Code's
`.claude/settings.local.json`, or opencode's `permission` block in the project's
`opencode.json` — proposed to the user, not a blanket bypass. Never start a supervised
opencode session with `--auto`.

## Supervising several sessions at once

- **One watcher, many panes.** One `sv-watch.sh` call listing every pane. A watcher per
  session gets reaped under memory pressure and you will not notice.
- **Keep a small table** of session id, pane, goal, and current task, and re-read it on
  each wake. You will not reliably remember six sessions, and confusing two means sending
  one session another's instructions.
- **Never assume which session woke you.** The event names the pane; resolve it back to a
  session and its goal before acting.
- **Sessions in the same repo need care.** Two sessions in one working tree collide over the
  index and the branch. Prefer a git worktree each, and check `cwd` at setup.
- **Report per session.** Say which session did what; a merged narrative hides which one is
  stuck.

## Long runs

- **Reset context on purpose, before auto-compaction does it for you.** Stale context holds
  superseded decisions, and an auto-compact summary may carry the wrong version forward.
  Reset when any of these is true, whichever comes first:
  - the session just committed a completed unit of work (a task, a card, a milestone) and
    is about to start the next one — the commit is the seam;
  - context pressure is building (roughly past half of the window — the TUI shows the
    percentage in its footer) and a fresh unit of work is ahead;
  - staleness symptoms: it re-asks something already decided, contradicts its own standing
    instructions, or retries a failed approach verbatim.
  Never reset mid-turn or with uncommitted work. The precondition is a clean tree (or a
  commit you just made) plus the open state written down where it survives — the
  standing-instructions file, updated with what is done and what is next.
- **Reset mechanics differ by agent.**
  - *Claude Code:* `/clear` keeps the session id (the transcript path changes, so re-resolve
    afterwards and never cache one).
  - *opencode:* `/new` (alias `/clear`, `ctrl+x n`) starts a genuinely new session with a
    new id — re-run `sv-resolve.py --list` after the first instruction lands, and supervise
    by pane, not by cached session id.
  - *After either reset:* hand the session nothing but a pointer to its standing
    instructions (`Read tmp/supervisor/NEXT.md and follow it.`) and require it to restate
    its goal and next step before touching code. That restatement is the test: if a freshly
    reset session cannot pick the work back up, the project's documentation was
    insufficient, and you found that out at a moment you chose.
- **Keep the standing instructions in a file the session re-reads**, not in the
  conversation — that file is what survives a reset, and it makes resetting safe rather
  than destructive.
- **A session that says "continuing to the next task" has usually ended its turn.** Normal;
  nudge it. Not a stall.
- **Fix your own instructions when a session trips over them.** If it had to work around
  something you told it, the instruction was wrong.

## Reference

- `scripts/sv-capability.py` — how this supervisor can be woken, if at all, and its own pane.
- `scripts/sv-floor.py` — every agent pane with its harness, state and session, in one call.
- `scripts/sv-selftest.py` — a smoke test for the primitives above; run it after any change.
- `scripts/sv-launch.sh` — start a session in tmux and report how to watch it.
- `scripts/sv-nudge.py` — send one wake into the supervisor's pane and confirm it landed.
- `references/policy.md` — the reasoning behind the rules above, and the failure modes this
  skill exists to catch.
- `references/troubleshooting.md` — mapping problems, dialogs, stalls, port collisions.

The scripts are dispatchers: they detect the agent in a pane and hand the work to
`scripts/adapters/claude/` or `scripts/adapters/opencode/`. Read those only when something
agent-specific is misbehaving; day to day everything is in the top-level commands.
