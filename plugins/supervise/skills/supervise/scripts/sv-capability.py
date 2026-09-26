#!/usr/bin/env python3
"""Report how — or whether — this supervisor can be woken while it waits.

A supervisor that ends its turn is only useful if something can start the next
one. Two things can:

  monitor     the harness watches on your behalf and re-invokes you. Claude Code
              has this (its monitor shell); opencode does not.
  tmux-nudge  a poller runs beside the supervised panes and, on a transition,
              types a wake-up into the supervisor's *own* tmux pane. This is the
              opencode path, and it needs the supervisor to be inside tmux.

A supervisor with neither can only run the synchronous loop in SKILL.md, which
holds its turn open and therefore does not scale past one worker.

  sv-capability.py                  JSON
  sv-capability.py --field mode
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_detect  # noqa: E402


def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def agent_from_env():
    if os.environ.get("OPENCODE"):
        return "opencode"
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    return None


def agent_from_ancestry():
    """Nearest Claude Code / opencode process above us, if the env was stripped."""
    table = sv_detect.process_table()
    pid = os.getpid()
    for _ in range(40):
        entry = table.get(pid)
        if not entry:
            return None
        ppid, cmd = entry
        base = sv_detect.basename_of(cmd)
        if base in sv_detect.AGENT_BINARIES:
            return sv_detect.AGENT_BINARIES[base]
        if ppid <= 1 or ppid == pid:
            return None
        pid = ppid
    return None


def harness():
    return agent_from_env() or agent_from_ancestry() or "unknown"


def own_pane():
    """This session's tmux pane, or None.

    Gated on $TMUX on purpose: without a client, `tmux display-message` does not
    fail — it answers about some other session's active pane, and a supervisor
    that trusted that would record a pane belonging to a supervised worker.
    """
    if not os.environ.get("TMUX"):
        return None
    target = os.environ.get("TMUX_PANE")
    if not target:
        return None
    return run(["tmux", "display-message", "-p", "-t", target,
                "#{session_name}:#{window_index}.#{pane_index}"]) or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--field")
    args = ap.parse_args()

    agent = harness()
    pane = own_pane()
    in_tmux = bool(os.environ.get("TMUX"))

    monitor = agent == "claude"
    url = None
    if agent == "opencode" and pane:
        info = sv_detect.for_pane(pane)
        if info:
            url = info.get("base_url")

    notes = []
    if agent == "opencode" and in_tmux and not url:
        notes.append("own opencode pane has no reachable server (no --port); "
                     "wakes are sent without delivery confirmation")

    if monitor:
        mode = "monitor"
        async_ok = True
    elif agent == "opencode" and in_tmux and pane:
        mode = "tmux-nudge"
        async_ok = True
    else:
        mode = "sync"
        async_ok = False
        if agent == "opencode":
            notes.append("opencode has no monitor shell and this session is not in "
                         "tmux, so nothing can wake it. Relaunch the supervisor inside "
                         "tmux for async supervision, or continue with the synchronous "
                         "loop (it holds the turn and does not scale past one worker).")
        else:
            notes.append("unknown harness and not in tmux: no wake-up channel. Use the "
                         "synchronous loop, or run the supervisor inside tmux.")

    result = {
        "harness": agent,
        "monitor": monitor,
        "in_tmux": in_tmux,
        "pane": pane,
        "supervisor_url": url,
        "async_capable": async_ok,
        "mode": mode,
        "notes": notes,
    }

    if args.field:
        value = result.get(args.field)
        if value is None:
            sys.exit(f"{args.field} is not known")
        print(value if not isinstance(value, (list, dict)) else json.dumps(value))
        return
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
