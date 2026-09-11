#!/usr/bin/env python3
"""Classify what an opencode pane is doing. State only — never read content here.

  state.py <pane>        prints one of: BUSY IDLE PROMPT UNKNOWN GONE

The Claude adapter has to grep the screen for this, because that is the only
signal it has. opencode publishes the answer: a pending-permission queue and a
per-session busy flag. We ask the server, and only fall back to reading the
terminal when the server cannot be reached — a fallback that says UNKNOWN
rather than guessing, because a supervisor that cannot tell what it is looking
at must say so.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_detect  # noqa: E402
import sv_opencode as oc  # noqa: E402

EXIT = {"IDLE": 0, "BUSY": 1, "PROMPT": 2, "GONE": 3, "UNKNOWN": 4}


def pane_text(pane):
    try:
        out = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane, "-S", "-45"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def from_screen(text):
    """Last resort, when the server is unreachable but the pane is alive."""
    if "Permission required" in text or "Allow once" in text:
        return "PROMPT"
    if "esc interrupt" in text or "esc to interrupt" in text:
        return "BUSY"
    if "ctrl+p commands" in text:
        return "IDLE"
    return "UNKNOWN"


def classify(pane):
    info = sv_detect.for_pane(pane)
    if info is None or info["agent"] != "opencode":
        return "GONE" if pane_text(pane) is None else "GONE"

    if not info["base_url"]:
        text = pane_text(pane)
        return from_screen(text) if text is not None else "GONE"

    try:
        # PROMPT is tested first, deliberately. A session waiting on a
        # permission dialog still reports itself busy, and the wrong order
        # would hide the one state that needs a human.
        if oc.pending_permissions(info["base_url"]) or oc.pending_questions(info["base_url"]):
            return "PROMPT"
        return "BUSY" if oc.status(info["base_url"]) else "IDLE"
    except oc.OpencodeError:
        text = pane_text(pane)
        return from_screen(text) if text is not None else "GONE"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: state.py <tmux-pane>")
    state = classify(sys.argv[1])
    print(state)
    sys.exit(EXIT[state])


if __name__ == "__main__":
    main()
