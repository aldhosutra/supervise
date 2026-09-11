#!/usr/bin/env python3
"""Read what an opencode session actually said, from the server.

Same rule as the Claude adapter: never read a session's output from the pane. A
pane is a lossy render and long replies scroll out of it. Here the ground truth
is the message history the server holds, which is complete whatever the
terminal happened to show.

  read.py --session ses_...              last assistant turn
  read.py --pane work:0.1 --turns 3
  read.py --session ses_... --tools      include tool-call names
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_opencode as oc  # noqa: E402


def resolve(session_id=None, pane=None):
    cmd = [sys.executable, os.path.join(HERE, "resolve.py")]
    cmd += ["--session", session_id] if session_id else ["--pane", pane]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stderr.strip() or "cannot resolve that opencode session")
    return json.loads(out.stdout)


def text_of(message, with_tools):
    """Flatten one message's parts into readable text.

    opencode splits a message into parts: text, reasoning, tool calls, and
    step markers. Only text is the answer; the rest is machinery, and the
    caller opts into seeing which tools ran.
    """
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
            current = {"user": body, "assistant": [], "ts": (info.get("time", {}) or {}).get("created", 0),
                       "running": False}
        elif role == "assistant" and current is not None:
            if body.strip():
                current["assistant"].append(body)
            # No completion timestamp means this turn is still being written.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--sentinel", action="store_true")
    args = ap.parse_args()

    if not (args.session or args.pane):
        sys.exit("give --session <id> or --pane <pane>")

    info = resolve(args.session, args.pane)
    session_id = info["active_session_id"]
    if not session_id:
        sys.exit(f"pane {info['pane']} has no opencode session yet — "
                 "send it something first")
    try:
        history = oc.messages(info["base_url"], session_id)
    except oc.OpencodeError as exc:
        sys.exit(f"cannot read the session: {exc}")

    turns = turns_of(history, args.tools)
    if not turns:
        sys.exit("no turns found in that session")

    if args.sentinel:
        import re
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
    print(f"[{session_id}, {len(turns)} turns, via {info['base_url']}]")


if __name__ == "__main__":
    main()
