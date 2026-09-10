# /supervise

[![version](https://img.shields.io/github/v/tag/aldhosutra/supervise?label=version&color=1f6feb)](https://github.com/aldhosutra/supervise/releases)
[![license](https://img.shields.io/github/license/aldhosutra/supervise?color=2da44e)](LICENSE)
![requires Claude Code](https://img.shields.io/badge/requires-Claude%20Code-1f6feb)
![platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)

You give it a goal and walk away. `/supervise` turns one Claude Code session into a foreman
for your others, as many as your machine will hold, running in tmux where you can watch every
keystroke.

The reason you can walk away is that it resolves their questions instead of forwarding them.
When a session gets stuck on something undecided, the supervisor digs through the project's
own documents, searches the web, and measures the real answer where the system can be asked
directly. It comes back to you only for the things a human has to settle.

## Installation

With the Skills CLI:

```bash
npx skills add aldhosutra/supervise --global
```

Leave off `--global` to install into the current project only. The skill answers to
`/supervise`.

Claude Code can install it as a plugin instead, which `/plugin update` then keeps current:

```text
/plugin marketplace add aldhosutra/supervise
/plugin install supervise@aldhosutra
```

Or in one line, without either:

```bash
curl -fsSL https://raw.githubusercontent.com/aldhosutra/supervise/main/install.sh | bash
```

Needs `tmux`, `python3`, and Claude Code. macOS and Linux. The supervisor reads Claude Code
transcripts and drives Claude Code panes, so the sessions it supervises have to be Claude
Code; a different agent can run the scripts, but there would be nothing for them to read.

## Usage

Give it the session IDs you want supervised:

```text
/supervise 9513c215 4f2b1a08
```

It asks what each session's job is and what finished looks like, then keeps them at it. If a
session is not running yet it starts one and tells you how to attach.

## How it works

```mermaid
flowchart LR
    U([you]) -->|"one goal per session"| S
    S -->|"only what a human can settle:<br/>money, vendors, publishing,<br/>taste, permission dialogs"| U

    S["supervisor<br/>(this skill)"]

    subgraph tmux["tmux, attachable at any time"]
        P1["session A"]
        P2["session B"]
    end

    S -->|"reads state,<br/>sends verified instructions"| P1
    S -->|"reads state,<br/>sends verified instructions"| P2
    P1 -.-> T
    P2 -.-> T
    T[("transcripts<br/>.jsonl on disk")]
    T -->|"reads what they actually said"| S

    classDef me fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef disk fill:#2da44e,stroke:#2da44e,color:#fff
    class S me
    class T disk
```

The terminal is read for signals and never for content. A pane scrolls, so a long reply read
that way arrives as its tail; the transcript on disk has all of it.

When a session hits something undecided, the supervisor does not pass it to you. It works
down a ladder and stops at the first rung that settles the question:

```mermaid
flowchart LR
    Q["a session hits<br/>an open question"] --> A["the project's<br/>own specs"]
    A -->|"not decided there"| B["web search"]
    B -->|"no clear convention"| C["measure the<br/>live system"]
    C -->|"a person has<br/>to choose"| U([you, with the<br/>findings attached])

    A -.->|answered| D([back to work])
    B -.->|answered| D
    C -.->|answered| D

    classDef out fill:#2da44e,stroke:#2da44e,color:#fff
    classDef human fill:#1f6feb,stroke:#1f6feb,color:#fff
    class D out
    class U human
```

Most questions are settled on the first or second rung and you never see them.

## What a supervisor does

It keeps the sessions working. They stall between tasks, so it picks the next one and sends
it, which saves you eight hours of typing "continue".

It checks the work. It reads the diff, runs the tests, renders the page. "All tests pass" is
a claim; a green run you triggered is evidence. A supervisor that forwards claims adds
latency and nothing else.

It answers their questions rather than passing them along, which is the part that decides
whether you can actually leave. A session that stops on every unstated decision is a session
you are still babysitting. So the supervisor works a ladder, and stops at the first rung that
settles it:

1. The project's own specs and principles. A surprising number of "open questions" were
   already decided by something the project wrote down and the session had not connected.
2. Web search, for a convention or a published standard.
3. A measurement, when the system can be asked directly. A number you measured beats a
   number you cited.

Only after all three does it come to you, and then with the findings and a recommendation
attached rather than a bare question.

Some things it will not decide, and escalates immediately without working the ladder: money,
vendors, publishing, matters of taste, and permission dialogs. Ten hours of unattended work
should cost you four decisions rather than four hundred.

## Why not just use subagents?

Use them. For short parallel fan-out, like searching six directories or reviewing four
files, native subagents are simpler and cheaper.

A subagent is a function call. A supervised session is a process. You call a subagent, it
computes, it returns, and its context is destroyed; that isolation is the whole reason it
exists.

`/clear` shows the difference. You cannot `/clear` a subagent, because there is nothing left
to continue. So context lifecycle becomes something a supervisor decides: when should this
session forget, and what has to survive the forgetting?

Reach for `/supervise` when the work is long, when you want to watch it happen, and when the
session should still be around tomorrow.

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

`sv-launch.sh` starts sessions detached rather than hidden. It hands you
`tmux attach -t work`, so you can watch live and take the keyboard whenever you like.

A session's ID changes every time you run `/clear`, so `sv-resolve.py` tracks the
`bridgeSessionId` that stays constant for the terminal instead. Hand it any ID a session has
ever had and it finds the live one.

## It will never

Answer a permission dialog for you, spend your money, commit you to a vendor, publish
anything, decide a matter of your taste, or relay a claim it has not checked.

## Read more

[SKILL.md](plugins/supervise/skills/supervise/SKILL.md) covers what the supervisor does,
step by step.

[policy.md](plugins/supervise/skills/supervise/references/policy.md) explains why each rule
exists, including the failure this kind of work keeps producing: code that is correct and
never reached. Seven variants turned up in one project, every one passing its own tests.

[troubleshooting.md](plugins/supervise/skills/supervise/references/troubleshooting.md) is
for when the mapping, the dialogs, or the silence go wrong.

MIT.
