#!/usr/bin/env python3
"""Resolve opencode sessions to their server and tmux pane.

opencode has no /clear lineage problem: its session ids are stable, and a new
session is simply a new id. What it has instead is a discovery problem — a
session is only readable through the server of the TUI that owns it, and that
server's port is random unless someone pinned it. So the pane is the anchor
here: find the panes running opencode, ask each one's server what it is working
on, and match sessions to panes by directory.

  resolve.py --list                    every opencode session with a pane
  resolve.py --session ses_...         resolve one (JSON)
  resolve.py --pane work:0.1           resolve by pane instead
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_detect  # noqa: E402
import sv_opencode as oc  # noqa: E402


def live_panes():
    return [p for p in sv_detect.all_agent_panes() if p["agent"] == "opencode"]


def rows():
    """One row per opencode pane, carrying the session it is working in."""
    out = []
    for pane in live_panes():
        row = {"agent": "opencode", "pane": pane["pane"], "cwd": pane["cwd"],
               "port": pane["port"], "base_url": pane["base_url"],
               "pid": pane["pid"], "session_id": None, "title": None,
               "reachable": False, "how": None}
        if not pane["base_url"]:
            row["how"] = "no-server"
            out.append(row)
            continue
        try:
            session, how = oc.current_session(pane["base_url"], pane["cwd"])
            row["reachable"] = True
        except oc.OpencodeError:
            row["how"] = "unreachable"
            out.append(row)
            continue
        row["how"] = how
        if session:
            row["session_id"] = session["id"]
            row["title"] = session.get("title")
            row["updated"] = (session.get("time", {}) or {}).get("updated", 0)
        out.append(row)
    return out


def find(session_id=None, pane_id=None):
    """The pane and server that own a session, or that a pane is running."""
    for pane in live_panes():
        if pane_id and pane["pane"] != pane_id:
            continue
        if not pane["base_url"]:
            if pane_id:
                return pane, None, "no-server"
            continue
        try:
            if session_id:
                match = next((s for s in oc.sessions(pane["base_url"])
                              if s["id"] == session_id), None)
                how = "id" if match else None
            else:
                match, how = oc.current_session(pane["base_url"], pane["cwd"])
        except oc.OpencodeError:
            continue
        if match or pane_id:
            return pane, match, how
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--field")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list:
        data = rows()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"{'SESSION':32} {'PANE':12} {'HOW':14} CWD")
            for r in data:
                print(f"{str(r['session_id'] or '(none yet)'):32} "
                      f"{str(r['pane'] or '-'):12} {str(r['how'] or '-'):14} {r['cwd']}")
        return

    if not (args.session or args.pane):
        sys.exit("give --list, --session <id> or --pane <pane>")

    pane, session, how = find(args.session, args.pane)
    if pane is None:
        sys.exit(f"no opencode pane owns {args.session or args.pane}. "
                 "Is it running, and is it inside tmux?")
    if args.session and session is None:
        sys.exit(f"no opencode session {args.session} on any running instance")

    result = {
        "agent": "opencode",
        "asked_for": args.session or args.pane,
        "active_session_id": session["id"] if session else None,
        # opencode keeps its history in a database behind the server rather
        # than a file, so there is no transcript path to hand out. Read it with
        # sv-read.py, which goes through the API.
        "transcript": None,
        "base_url": pane["base_url"],
        "port": pane["port"],
        "cwd": session.get("directory") if session else pane["cwd"],
        "pane": pane["pane"],
        "pid": pane["pid"],
        "title": session.get("title") if session else None,
        "mapped_by": how,
        # There is no /clear lineage to follow: a reset in opencode starts a
        # session with a new id, and resolving by pane finds it.
        "cleared_since": False,
    }
    if args.field:
        value = result.get(args.field)
        if value is None:
            sys.exit(f"{args.field} is not known for this session")
        print(value)
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
