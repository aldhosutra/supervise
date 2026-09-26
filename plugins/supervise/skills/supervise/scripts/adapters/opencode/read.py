#!/usr/bin/env python3
"""Read what an opencode session actually said.

Same rule as the Claude adapter: never read a session's output from the pane if a
real record exists. With a server, that record is the message history the server
holds; without one, opencode still wrote the same history into its SQLite
database, so read that. The pane is the last resort, and the only lossy one.

`--wait` blocks until a fresh assistant turn finishes and then prints it, so a
supervisor never hand-rolls a poll loop.

  read.py --session ses_...              last assistant turn (API or DB)
  read.py --pane work:0.1 --turns 3
  read.py --pane work:0.1 --wait         wait for the next completed reply
  read.py --session ses_... --tools      include tool-call names
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_bind as bind  # noqa: E402
import sv_opencode as oc  # noqa: E402
import sv_opencode_db as db  # noqa: E402
import sv_pane  # noqa: E402


def try_resolve(session_id=None, pane=None):
    cmd = [sys.executable, os.path.join(HERE, "resolve.py")]
    cmd += ["--session", session_id] if session_id else ["--pane", pane]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def _role(message):
    return (message.get("info", {}) or {}).get("role")


def _completed(message):
    return bool(((message.get("info", {}) or {}).get("time", {}) or {}).get("completed"))


def wait_for_reply(history_fn, timeout):
    """Block until the latest user message has a completed assistant reply.

    Keyed to the last *user* message, not to a wall-clock mark: by the time a
    sender has confirmed its prompt, the reply may already be finished, and a
    "wait for something new" rule would then block forever.
    """
    deadline = time.time() + timeout
    while True:
        messages = history_fn()
        last_user = None
        for i, message in enumerate(messages):
            if _role(message) == "user":
                last_user = i
        if last_user is not None:
            for message in messages[last_user + 1:]:
                if _role(message) == "assistant" and _completed(message):
                    return messages
        if time.time() >= deadline:
            return messages
        time.sleep(1.0)


def text_of(message, with_tools):
    chunks = []
    for part in message.get("parts", []) or []:
        kind = part.get("type")
        if kind == "text" and part.get("text"):
            chunks.append(part["text"])
        elif kind == "tool" and with_tools:
            name = part.get("tool") or (part.get("state", {}) or {}).get("title") or "tool"
            chunks.append(f"    [tool: {name}]")
    return "\n".join(chunks)


def turns_of(messages, with_tools):
    turns, current = [], None
    for message in messages:
        info = message.get("info", {}) or {}
        role = info.get("role")
        body = text_of(message, with_tools)
        if role == "user":
            if current:
                turns.append(current)
            current = {"user": body, "assistant": [],
                       "ts": (info.get("time", {}) or {}).get("created", 0),
                       "running": False}
        elif role == "assistant" and current is not None:
            if body.strip():
                current["assistant"].append(body)
            if not (info.get("time", {}) or {}).get("completed"):
                current["running"] = True
    if current:
        turns.append(current)
    return turns


def stamp(ms):
    if not ms:
        return ""
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds")


def emit(turns, session_id, source, args):
    if args.sentinel:
        body = "\n".join("\n".join(t["assistant"]) for t in turns[-args.turns:])
        found = re.findall(r"<<<[^>]{0,200}>>>", body)
        print("\n".join(found) if found
              else f"(no sentinel in the last {args.turns} turn(s))")
        return
    for turn in turns[-args.turns:]:
        print("=" * 72)
        print(f"USER [{stamp(turn['ts'])}]: {turn['user'][:400].strip()}")
        print("-" * 72)
        print("\n".join(turn["assistant"]).strip() or "(no assistant text)")
        if turn["running"]:
            print("\n[this turn is still running — the reply is incomplete]")
    print("=" * 72)
    print(f"[{session_id}, {len(turns)} turns, via {source}]")


def lossy_pane(pane):
    try:
        text = sv_pane.read(pane)
    except sv_pane.PaneError as exc:
        sys.exit(str(exc))
    print(f"# LOSSY PANE READ — no server and no database row for {pane} yet.")
    print("# The screen scrolls, so a long reply arrives as its tail.")
    print("-" * 72)
    print(text.rstrip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--sentinel", action="store_true")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--wait-timeout", type=float,
                    default=float(os.environ.get("SV_WAIT_SECONDS", "120")))
    args = ap.parse_args()

    if not (args.session or args.pane):
        sys.exit("give --session <id> or --pane <pane>")

    if args.session:
        info = try_resolve(session_id=args.session)
        if info and info.get("base_url"):
            session_id = info["active_session_id"] or args.session
            base = info["base_url"]
            history_fn = lambda: oc.messages(base, session_id)   # noqa: E731
            source = base
        else:
            session_id = args.session
            history_fn = lambda: db.messages(session_id)          # noqa: E731
            source = "db (no server)"
    else:
        info = try_resolve(pane=args.pane)
        if info and info.get("base_url"):
            session_id = info["active_session_id"]
            if not session_id:
                sys.exit(f"pane {args.pane} has no opencode session yet — "
                         "send it something first")
            base = info["base_url"]
            history_fn = lambda: oc.messages(base, session_id)   # noqa: E731
            source = base
        else:
            cwd = (info or {}).get("cwd") or ""
            bound = (bind.get(args.pane) or {}).get("session_id")
            session_id = bound or db.latest_session(cwd)
            if not session_id:
                lossy_pane(args.pane)
                return
            history_fn = lambda: db.messages(session_id)          # noqa: E731
            source = "db (binding)" if bound else "db (no server)"

    history = wait_for_reply(history_fn, args.wait_timeout) if args.wait else history_fn()
    turns = turns_of(history, args.tools)
    if not turns:
        sys.exit("no turns found in that session")
    emit(turns, session_id, source, args)


if __name__ == "__main__":
    main()
