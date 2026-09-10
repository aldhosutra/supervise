# /supervise

**Give it a goal. Walk away. Come back to finished work.**

`/supervise` turns a Claude Code session into a foreman for your other Claude Code sessions
— one, or a dozen — running in tmux where you can watch every keystroke.

```text
/plugin marketplace add aldhosutra/supervise
/plugin install supervise@aldhosutra
```

```text
/supervise 9513c215 4f2b1a08
```

It asks what each session's job is and what *done* means, then runs until it's done.

---

## What a supervisor actually does

Not a task queue. A supervisor.

**It keeps them working.** Sessions stall between tasks; it picks the next one and sends it.
No more sitting there typing "continue" for eight hours.

**It checks the work.** It reads the diff, runs the tests, renders the page — because
"all tests pass" is a claim, and a green run you triggered is evidence. A supervisor that
forwards claims adds latency and nothing else.

**It answers their questions instead of forwarding them.** When a session hits an open
question, it works the ladder: answer it from the project's own docs → research it, or
*measure* it → and only then bring it to you, with the findings and a recommendation.

**It wakes you for exactly what's yours.** Money, vendors, publishing, taste, permission
dialogs. Everything else it handles.

That last part is the whole point. Ten hours of unattended work should cost you four
decisions, not four hundred.

---

## How many at once?

The scripts aren't the bottleneck: polling 100 panes takes 0.62s, so a thousand would cost
about six seconds per cycle. Two other things bind first.

**Memory.** A Claude session holds 275–390 MB. That's ~8 on an 8 GB laptop, ~20 on 16 GB,
100+ on a real workstation.

**Review doesn't parallelize** — and this is the one that matters. Past a certain point a
supervisor stops reading diffs and starts sampling, and a sampling supervisor is just a
dispatcher. That's the thing native subagents already do better.

So run as many as your machine holds, but know what you're trading. Six sessions genuinely
reviewed beat sixty glanced at.

---

## Why not just use subagents?

Use them! For short parallel fan-out — search six directories, review four files — native
subagents are simpler, cheaper and better.

But **a subagent is a function call. A supervised session is a process.**

You call a subagent, it computes, it returns, its context is destroyed. That isolation is
the entire point.

The clearest proof is `/clear`. **You can't `/clear` a subagent** — not because the feature
is missing, but because it's incoherent. There's nothing to continue. Which makes context
lifecycle a *supervisory decision*: when should this session forget, and what must survive
the forgetting?

Reach for `/supervise` when the work is long, when you want to watch it, and when the
session should still be there tomorrow.

---

## Built the hard way

Three decisions, each from something that actually broke:

**The terminal lies — so it's only used for signals.** `tmux send-keys` silently truncated a
1,200-character instruction to its last 232 characters, mid-word, with no error anywhere.
And `capture-pane` returns only what's left in the scrollback — reading a long report that
way once lost its first half, which happened to contain a correction to the supervisor's own
work. **State comes from the terminal. Content always comes from the transcript on disk.**

**Session IDs move; terminals don't.** Every `/clear` mints a new session ID, so a
supervisor holding the old one watches a dead file and concludes all is quiet. Every
transcript also carries a `bridgeSessionId` that never changes:

```text
cse_01Pn48ur…  →  b47163fa → d8c95e98 → 2a11f9a9 → 9513c215
                  one terminal, three /clears, four session IDs
```

Hand it any ID in that chain and it finds the live one.

**Nothing is sent unverified.** Instructions over 120 characters are refused outright. The
input is cleared first — Claude Code renders *suggestions* there, and a bare Enter would
submit one nobody wrote. The text is checked character-for-character before Enter is pressed.

---

## The toolkit

Six scripts, useful on their own:

```bash
sv-launch.sh work ~/code/myproject     # start a session, print how to attach
sv-resolve.py --list                   # every session ↔ its tmux pane
sv-state.sh work:0.0                   # BUSY | IDLE | PROMPT | UNKNOWN | GONE
sv-read.py --session <id> --turns 2    # what it really said, from the transcript
sv-send.sh work:0.0 "Continue."        # types it, verifies it, then hits Enter
sv-watch.sh work:0.0 work:0.1 api:0.0  # one line per state change worth acting on
```

`sv-launch.sh` starts sessions **detached, not hidden** — it hands you `tmux attach -t work`
so you can watch live and grab the keyboard whenever you like.

---

## Install

**As a plugin** (recommended — `/plugin update` keeps it current):

```text
/plugin marketplace add aldhosutra/supervise
/plugin install supervise@aldhosutra
```

**Or one line:**

```bash
curl -fsSL https://raw.githubusercontent.com/aldhosutra/supervise/main/install.sh | bash
```

**Or from a clone:** `./install.sh` for every project, `./install.sh --project` for this one.

Needs `tmux`, `python3`, Claude Code. macOS and Linux. Nothing else.

---

## It will never

Answer a permission dialog for you · spend your money · commit you to a vendor · publish
anything · decide a matter of your taste · relay a claim it hasn't checked.

---

## Read more

[**SKILL.md**](plugins/supervise/skills/supervise/SKILL.md) — what the supervisor does, step
by step.
[**policy.md**](plugins/supervise/skills/supervise/references/policy.md) — why each rule
exists, and the failure this work keeps producing: *code that is correct and never reached.*
Seven variants in one project, every one passing its own tests.
[**troubleshooting.md**](plugins/supervise/skills/supervise/references/troubleshooting.md) —
when the mapping, the dialogs, or the silence go wrong.

MIT.
