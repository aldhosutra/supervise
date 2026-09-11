#!/usr/bin/env python3
"""Resolve a supervised session to its transcript and tmux pane, whichever
agent is running it.

Claude Code and opencode keep their history in very different places — one in
JSONL files under ~/.claude/projects, the other behind the HTTP server each
instance runs — so the work happens in adapters/<agent>/resolve.py. This picks
the right one and presents a single table.

  sv-resolve.py --list                 every session, both agents
  sv-resolve.py --session <id>         resolve one (JSON)
  sv-resolve.py --pane work:0.1        resolve by pane
  sv-resolve.py --session <id> --field transcript
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_detect  # noqa: E402

ADAPTERS = {
    "claude": os.path.join(HERE, "adapters", "claude", "resolve.py"),
    "opencode": os.path.join(HERE, "adapters", "opencode", "resolve.py"),
}


def adapter(agent, args, check=True):
    out = subprocess.run([sys.executable, ADAPTERS[agent]] + args,
                         capture_output=True, text=True)
    if out.returncode != 0:
        if check:
            sys.exit(out.stderr.strip() or f"{agent}: cannot resolve that")
        return None
    return out.stdout


def agent_of_session(session_id):
    """opencode ids are prefixed; Claude's are bare uuids."""
    return "opencode" if session_id.startswith("ses_") else "claude"


def merged_list(as_json):
    rows = []
    for agent in ("claude", "opencode"):
        raw = adapter(agent, ["--list", "--json"], check=False)
        if not raw:
            continue
        for row in json.loads(raw):
            rows.append({"agent": agent, **row})
    rows.sort(key=lambda r: (r.get("pane") is None, r.get("agent"),
                             -(r.get("mtime") or r.get("updated") or 0)))
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'AGENT':9} {'SESSION':38} {'PANE':12} {'HOW':14} CWD")
    for r in rows:
        sid = r.get("session_id") or "(no session yet)"
        print(f"{r['agent']:9} {sid:38} {str(r.get('pane') or '-'):12} "
              f"{str(r.get('how') or '-'):14} {r.get('cwd') or '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--field")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list:
        merged_list(args.json)
        return

    if args.pane:
        info = sv_detect.for_pane(args.pane)
        if info is None:
            sys.exit(f"no supervisable agent is running in pane {args.pane}")
        agent = info["agent"]
        passthrough = ["--pane", args.pane]
    elif args.session:
        agent = agent_of_session(args.session)
        passthrough = ["--session", args.session]
    else:
        sys.exit("give --list, --session <id> or --pane <pane>")

    if args.field:
        passthrough += ["--field", args.field]
    sys.stdout.write(adapter(agent, passthrough))


if __name__ == "__main__":
    main()
