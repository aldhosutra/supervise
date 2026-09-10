# /supervise

A Claude Code skill for supervising other Claude Code sessions — one of them or six — until
their goals are met.

You launch the sessions in tmux and can watch them work. `/supervise` keeps them moving
between tasks, reviews what they actually produced, answers their questions by reasoning and
research, and interrupts you only for what genuinely needs a human.

```bash
/supervise 9513c215-a113-4847-b516-465f807b3465 4f2b1a08-6c31-4d90-b7e2-1a5c9e3f8d02
```

It asks what each session's job is and what "done" means for it, checks each one is in the
right working directory, then runs until those goals are met.

---

## A subagent is a function call. A supervised session is a process.

You call a subagent, it computes, it returns, and its context is discarded. That isolation
is not a side effect — it is the entire point. The parent specifically does not want the
intermediate work.

A supervised session is something else: it persists, it learns the codebase over days, and
its lifecycle is yours to manage.

The sharpest illustration is `/clear`. **You cannot `/clear` a subagent** — not because the
feature is missing, but because it is incoherent. There is nothing to continue. A
subagent's context is not cleared, it is destroyed along with the thing that owned it.
`/clear` only means anything for an entity that survives the reset.

Which makes **context lifecycle a supervisory decision**: when should this session forget,
and what must survive the forgetting? That question does not exist for a function call.

Use native subagents for short parallel fan-out — search six directories, review four files.
They are simpler, cheaper and better at it. Reach for `/supervise` when the work is long,
when you want to watch it, and when the session should still be there tomorrow.

---

## Install

### As a plugin (recommended)

```text
/plugin marketplace add aldhosutra/supervise
/plugin install supervise@aldhosutra
```

Two lines inside Claude Code, no clone, and `/plugin update` keeps it current. The skill
arrives as `/supervise`.

### One line, no plugin

```bash
curl -fsSL https://raw.githubusercontent.com/aldhosutra/supervise/main/install.sh | bash
```

Fetches the repo and copies the skill to `~/.claude/skills/supervise`, making `/supervise`
available in every project. Start a new Claude Code session to pick it up.

### From a clone

```bash
git clone https://github.com/aldhosutra/supervise.git
cd supervise
./install.sh              # ~/.claude/skills — every project
./install.sh --project    # ./.claude/skills — this repo only, commit it for your team
```

Needs `tmux`, `python3`, and Claude Code. macOS and Linux. Nothing else to install.

To remove it: delete `~/.claude/skills/supervise`, or `/plugin uninstall supervise@aldhosutra`.

---

## The design, and why

Every rule here came from something going wrong during a long supervised run, not from
theory.

### The terminal lies in both directions

**Outbound.** `tmux send-keys` silently truncates. A 1,200-character instruction arrived as
its last 232 characters, starting mid-word, with no error anywhere. The receiving session
did something reasonable with the fragment.

→ `sv-send.sh` refuses anything over 120 characters, verifies the text landed in the input
before pressing Enter, and clears first — Claude Code renders *suggestions* at the prompt,
and Enter without clearing submits one nobody wrote. Longer instructions go in a file, sent
as a one-line pointer.

**Inbound.** `capture-pane` returns what is still in the scrollback, which for a long reply
is its tail. Reading a report that way once cost the first half of it — and the missing half
contained a correction to the supervisor's own work.

→ Content **always** comes from the session's transcript on disk. The terminal is used for
state and nothing else.

**So: the terminal is the signal, the transcript is the content.**

### Session ids move; terminals do not

A session id changes every time you run `/clear`. A supervisor holding the old id reads a
transcript that has stopped growing and concludes the session went quiet.

Every transcript line also carries a `bridgeSessionId`, constant for the life of the
terminal:

```
cse_01Pn48ur…  →  b47163fa → d8c95e98 → 2a11f9a9 → 9513c215
                  one terminal, three /clears, four session ids
```

→ `sv-resolve.py` tracks the bridge id. Hand it *any* id in a lineage and it finds whichever
session is live now.

### Reset is a tool, not an accident

Auto-compaction picks its own moment and summarises lossily. A long-running session's
context accumulates superseded decisions — a plan that changed, a recommendation that was
withdrawn — and a summary can carry the wrong version forward.

→ Reset deliberately, at natural seams. Before clearing, have the session write down
anything living only in its head. Afterwards, hand it nothing but a pointer to its standing
instructions.

**The precondition that makes this safe:** it only works because the state lives in files
the session re-reads. Clear a session whose knowledge existed only in its context and you
have lobotomised it. Which gives you a free diagnostic — if a freshly cleared session cannot
pick the work back up, the project's documentation was insufficient, and you have found that
out at a moment you chose.

### Supervising is reviewing, not relaying

A supervisor that forwards claims adds latency and nothing else.

→ Read the diff, run the tests, render the page, query the database. Re-derive a reported
number once. Watch for work that satisfies its own acceptance criteria and misses the point.
Anything a person looks at needs a person to look at it.

### Questions get worked, not forwarded

→ Answer it from the project's own documents first. Then research or measure it — a measured
number beats a cited one. Only then bring it to the user, with the research and a
recommendation, never as a bare question. Escalating an answerable question spends the
attention this skill exists to protect.

Escalate immediately, without the ladder, when the answer costs money, commits to a vendor,
publishes something, or is a matter of taste the user owns.

---

## The tools

The skill drives six scripts, each useful on its own.

```bash
# Start a session in tmux and print how to watch it
scripts/sv-launch.sh work ~/code/myproject

# Every Claude session, with the tmux pane it maps to
scripts/sv-resolve.py --list

# Resolve one session to its live transcript and pane (follows /clear)
scripts/sv-resolve.py --session <id>

# What is that pane doing?   BUSY | IDLE | PROMPT | UNKNOWN | GONE
scripts/sv-state.sh work:0.0

# What did it actually say?  (from the transcript, not the screen)
scripts/sv-read.py --session <id> --turns 2
scripts/sv-read.py --session <id> --sentinel

# Type an instruction — pressing Enter only if it arrived intact
scripts/sv-send.sh work:0.0 "Continue with the next task."

# Watch many panes; one line per state change worth acting on
scripts/sv-watch.sh work:0.0 work:0.1 api:0.0
```

`sv-launch.sh` starts the session **detached, not hidden** — it prints `tmux attach -t work`
so you can watch it live and take the keyboard whenever you want. If a trust dialog is
waiting it stops and says so, because that is your decision rather than the supervisor's.

`sv-state.sh` reports `UNKNOWN` rather than guessing when a screen matches nothing. Silence
and "still running" look identical; that is the failure this is designed against.

---

## Supervising several at once

One watcher for every pane, not one per session — per-session watchers get reaped under
memory pressure and you will not notice. Keep a table of session, pane, goal and current
task, and re-read it on every wake; confusing two sessions means sending one another's
instructions. Give each session its own git worktree: two sessions in one working tree will
collide over the index and the branch, and separate directories also make pane-to-session
matching unambiguous.

---

## What it will not do

- Answer a permission dialog for you.
- Spend your money, commit you to a vendor, or publish anything.
- Decide a question that is a matter of your taste.
- Relay a claim it has not checked.

---

## Further reading

- [`SKILL.md`](plugins/supervise/skills/supervise/SKILL.md) — what the supervisor actually does.
- [`references/policy.md`](plugins/supervise/skills/supervise/references/policy.md) — the reasoning
  behind each rule, and the recurring failure this kind of work produces: **code that is
  correct and never reached.** Seven variants of it in one project, every one passing its
  own tests.
- [`references/troubleshooting.md`](plugins/supervise/skills/supervise/references/troubleshooting.md)
  — mapping problems, stalls, dialogs, port collisions, silent no-op edits.

## Licence

MIT. See [LICENSE](LICENSE).
