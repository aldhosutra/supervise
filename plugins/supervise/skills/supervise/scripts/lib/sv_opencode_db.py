#!/usr/bin/env python3
"""Read an opencode session from its database, for when the TUI has no server.

opencode stores every session in one SQLite database, whether or not the TUI was
started with `--port`. So a pane that serves no HTTP can still be read properly:
its message and part rows carry the same JSON the API would have returned. This
is the non-lossy channel for an opencode instance the HTTP adapter cannot reach.

Read-only, and best-effort: if the database cannot be opened (locked, moved,
schema changed), the caller falls back to the pane.
"""
import json
import os
import sqlite3
import subprocess


def db_path():
    override = os.environ.get("SV_OPENCODE_DB")
    if override:
        return override
    try:
        out = subprocess.run(["opencode", "db", "path"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.path.expanduser("~/.local/share/opencode/opencode.db")


def _connect():
    return sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)


def latest_session(directory):
    """The newest session whose directory is this one, or None.

    Session rows store the directory opencode was started in, which may or may
    not be canonicalised, so match on the basename in SQL and confirm with
    realpath in Python.
    """
    if not directory:
        return None
    want = os.path.realpath(directory)
    base = os.path.basename(want.rstrip("/")) or want
    with _connect() as conn:
        rows = conn.execute(
            "select id, directory from session where directory like ? "
            "order by rowid desc limit 300", ("%" + base,)).fetchall()
    for session_id, stored in rows:
        try:
            if os.path.realpath(stored or "") == want:
                return session_id
        except Exception:
            continue
    return None


def messages(session_id):
    """Messages shaped like the API's: [{"info": {...}, "parts": [...]}, ...]."""
    with _connect() as conn:
        rows = conn.execute(
            "select id, data from message where session_id=? order by time_created",
            (session_id,)).fetchall()
        parts = conn.execute(
            "select message_id, data from part where session_id=? order by time_created",
            (session_id,)).fetchall()
    by_message = {}
    for message_id, data in parts:
        try:
            by_message.setdefault(message_id, []).append(json.loads(data))
        except ValueError:
            continue
    out = []
    for message_id, data in rows:
        try:
            info = json.loads(data)
        except ValueError:
            info = {}
        out.append({"info": info, "parts": by_message.get(message_id, [])})
    return out


def last_user_text(session_id):
    """The text of the most recent user message, or ''."""
    for message in reversed(messages(session_id)):
        if (message.get("info", {}) or {}).get("role") != "user":
            continue
        return "".join(p.get("text", "") for p in message.get("parts", [])
                       if p.get("type") == "text")
    return ""
