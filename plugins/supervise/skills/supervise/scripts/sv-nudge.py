#!/usr/bin/env python3
"""Deliver one supervision wake-up into the supervisor's own pane, proven.

The supervisor is an opencode TUI in a tmux pane. When a supervised pane
transitions, the poller calls this to type a protocol line into that pane and
press Enter. Two things make it more than a keystroke:

  * opencode queues a submitted prompt even while it is mid-turn, so the wake is
    delivered whether the supervisor is idle or busy. The one state that must be
    refused is a dialog, where the keystrokes would go to the dialog, not the
    prompt box.
  * the wake carries a unique token which is checked against the supervisor's own
    message history. "Typed" is not "delivered" — a modal can swallow it — so the
    caller is told to retry rather than being told it succeeded.

  sv-nudge.py --pane <sup-pane> --token <tok> --text "<wake>" [--url <base>]

Exit codes:
  0  delivered (and confirmed, when a URL is available)
  3  held: the supervisor is on a dialog; injecting would type into it
  4  gone: the supervisor pane no longer exists
  5  unconfirmed: sent but not seen in the session; retry next cycle
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_detect  # noqa: E402
import sv_opencode as oc  # noqa: E402


def pane_text(pane):
    try:
        out = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane, "-S", "-15"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def dialog_state(pane, url):
    """True if a dialog is up, False if clear, None if the pane is gone.

    With a server, the pending queue is authoritative and the screen is not
    consulted at all: a session that *discusses* a permission dialog leaves
    "Allow once / Allow always / Reject" in its scrollback, and matching that
    prose would hold every wake forever.
    """
    if url:
        try:
            return bool(oc.pending_permissions(url) or oc.pending_questions(url))
        except oc.OpencodeError:
            pass  # server unreachable: fall back to the screen below
    text = pane_text(pane)
    if text is None:
        return None
    flat = " ".join(text.split())
    # "enter confirm" is the dialog's own chrome; prose that merely names the
    # options does not carry it.
    return ("Permission required" in flat or "Allow once" in flat) and "enter confirm" in flat


def send(pane, text):
    # -l keeps the text literal (no key-name parsing); Enter is a separate call so
    # a trailing newline in the text can never submit a half-typed line.
    first = subprocess.run(["tmux", "send-keys", "-t", pane, "-l", "--", text],
                           capture_output=True, text=True)
    if first.returncode != 0:
        return False
    time.sleep(0.3)
    second = subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"],
                            capture_output=True, text=True)
    return second.returncode == 0


def confirmed(url, cwd, token):
    try:
        session, _ = oc.current_session(url, cwd)
        if not session:
            return False
        for message in oc.messages(url, session["id"]):
            if (message.get("info", {}) or {}).get("role") != "user":
                continue
            text = "".join(p.get("text", "") for p in message.get("parts", [])
                           if p.get("type") == "text")
            if token in text:
                return True
    except oc.OpencodeError:
        return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pane", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--url", default=os.environ.get("SV_NUDGE_URL") or None)
    ap.add_argument("--confirm", type=float,
                    default=float(os.environ.get("SV_NUDGE_CONFIRM", "8")))
    args = ap.parse_args()

    dialog = dialog_state(args.pane, args.url)
    if dialog is None:
        print(f"GONE: pane {args.pane} no longer exists", file=sys.stderr)
        sys.exit(4)
    if dialog:
        print(f"HOLD: {args.pane} is on a dialog; not injecting", file=sys.stderr)
        sys.exit(3)

    if not send(args.pane, args.text):
        print(f"FAILED: could not type into {args.pane}", file=sys.stderr)
        sys.exit(5)

    if not args.url:
        # No server to confirm against. Best effort: the keystroke reached a pane
        # that was not showing a dialog, which is as much as can be known here.
        sys.exit(0)

    info = sv_detect.for_pane(args.pane)
    cwd = info["cwd"] if info else ""
    deadline = time.time() + args.confirm
    while time.time() < deadline:
        if confirmed(args.url, cwd, args.token):
            sys.exit(0)
        time.sleep(1.5)
    print(f"UNCONFIRMED: {args.token} not found in the session for {args.pane}",
          file=sys.stderr)
    sys.exit(5)


if __name__ == "__main__":
    main()
