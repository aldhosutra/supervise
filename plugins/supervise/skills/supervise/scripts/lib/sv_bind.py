#!/usr/bin/env python3
"""A pane -> session binding, for when cwd+recency cannot tell sessions apart.

Several fresh sessions in one working directory all look like "the newest session
in that directory", so the resolver names the same one for every pane. The thing
that is certain is the session a message to a pane actually landed in, so
whichever command learns that writes it here and later commands read it first.
Once a pane is bound, its resolution is exact rather than a guess.

Stored at ${SV_STATE_DIR:-~/.local/state/supervise}/bindings.json.

  sv-bind.py --get --pane 2:0.0
  sv-bind.py --put --pane 2:0.0 --session ses_... --agent opencode
  sv-bind.py --forget --pane 2:0.0
  sv-bind.py --discover-claude --pane 8:0.0 --text 'the prompt we just sent'
"""
import argparse
import glob
import json
import os
import sys
import time

PROJECTS = os.path.expanduser("~/.claude/projects")


def _path():
    directory = os.environ.get("SV_STATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".local", "state", "supervise")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "bindings.json")


def _load():
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data):
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, _path())


def get(pane):
    return _load().get(pane)


def put(pane, session_id, agent, how="send"):
    data = _load()
    data[pane] = {"session_id": session_id, "agent": agent, "how": how,
                  "ts": int(time.time() * 1000)}
    _save(data)


def forget(pane):
    data = _load()
    if data.pop(pane, None) is not None:
        _save(data)


def discover_claude(cwd, text):
    """The newest Claude transcript in `cwd` whose text contains `text`.

    Used right after a fresh pane is sent its first line: nothing links the pane
    to a session id on disk, but the line we just typed is now in exactly one
    transcript, and the newest match is the pane we typed it into.
    """
    if not text.strip():
        return None
    needle = text.strip()[:60]
    project = cwd.rstrip("/").replace("/", "-")
    candidates = sorted(glob.glob(os.path.join(PROJECTS, project, "*.jsonl")),
                        key=os.path.getmtime, reverse=True)
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                if needle in fh.read():
                    return os.path.basename(path)[:-6]
        except OSError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--get", action="store_true")
    ap.add_argument("--put", action="store_true")
    ap.add_argument("--forget", action="store_true")
    ap.add_argument("--discover-claude", action="store_true")
    ap.add_argument("--pane")
    ap.add_argument("--session")
    ap.add_argument("--agent", default="claude")
    ap.add_argument("--how", default="send")
    ap.add_argument("--cwd")
    ap.add_argument("--text")
    args = ap.parse_args()

    if args.get:
        row = get(args.pane)
        if not row:
            sys.exit(1)
        print(json.dumps(row))
    elif args.put:
        if not (args.pane and args.session):
            sys.exit("--put needs --pane and --session")
        put(args.pane, args.session, args.agent, args.how)
    elif args.forget:
        forget(args.pane)
    elif args.discover_claude:
        session_id = discover_claude(args.cwd or os.getcwd(), args.text or "")
        if not session_id:
            sys.exit(1)
        put(args.pane, session_id, "claude", "discover")
        print(session_id)
    else:
        sys.exit("give --get, --put, --forget or --discover-claude")


if __name__ == "__main__":
    main()
