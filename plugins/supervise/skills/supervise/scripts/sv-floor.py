#!/usr/bin/env python3
"""The whole floor in one call: every agent pane, its harness, state and session.

This exists to keep discovery to a single command. A supervisor that has to run
the resolver, the detector, `ps`, the state classifier and then open the agent's
private database itself spends a long warm-up before it can send the first
instruction. One call answers everything it needs to start.

  sv-floor.py              a table
  sv-floor.py --json       the same rows as JSON

`session` is only as certain as `how` says: `binding` is exact (a message to that
pane created it), `resume-flag`/`id` come from the agent itself, `db`/`db-guess`
is the newest session in the pane's directory, and `-` means not yet known — send
the pane something and it will be.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_detect  # noqa: E402


def state_of(pane):
    out = subprocess.run([os.path.join(HERE, "sv-state.sh"), pane],
                         capture_output=True, text=True)
    return out.stdout.strip() or "GONE"


def resolve(pane):
    out = subprocess.run([sys.executable, os.path.join(HERE, "sv-resolve.py"),
                          "--pane", pane], capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = []
    for pane in sv_detect.all_agent_panes():
        info = resolve(pane["pane"])
        rows.append({
            "pane": pane["pane"],
            "harness": pane["harness"],
            "name": pane["name"],
            "state": state_of(pane["pane"]),
            "session_id": info.get("active_session_id"),
            "how": info.get("mapped_by"),
            "server": pane.get("base_url"),
            "cwd": pane["cwd"],
        })

    if args.json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'PANE':12} {'HARNESS':9} {'STATE':7} {'SESSION':36} {'HOW':12} CWD")
    for r in rows:
        print(f"{r['pane']:12} {r['harness']:9} {r['state']:7} "
              f"{str(r['session_id'] or '-'):36} {str(r['how'] or '-'):12} {r['cwd']}")
    print(f"\n# {len(rows)} agent pane(s) — state and session are included above, so there is")
    print("# nothing more to resolve. Send to a pane to bind a fresh session, then read with --wait.")


if __name__ == "__main__":
    main()
