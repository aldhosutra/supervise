#!/usr/bin/env python3
"""Pane-level operations for agents the skill cannot read through an adapter.

Claude Code has a transcript; opencode has its server. Anything else — including
opencode started without `--port`, so it serves no HTTP — can still be driven the
way a person drives it: type into the pane and read the screen back. That channel
is lossy (the screen scrolls, a long reply arrives as its tail), so it is a
fallback, and the caller must say so. It is never how content is read when a real
channel exists.
"""
import os
import subprocess
import time

LINES = int(os.environ.get("SV_PANE_LINES", "45"))
SEND_LIMIT = int(os.environ.get("SV_PANE_SEND_LIMIT", "1000"))


class PaneError(RuntimeError):
    pass


def capture(pane, lines=LINES):
    """The pane's text, or None when the pane is gone."""
    try:
        out = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane, "-S", f"-{lines}"],
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def on_dialog(pane):
    """True/False, or None if the pane is gone.

    Only dialog chrome counts. A session that merely *discusses* a permission
    dialog leaves the option words in its scrollback, and matching those would
    stall every send forever; "enter confirm" is the chrome a real dialog carries
    and prose does not.
    """
    text = capture(pane, 15)
    if text is None:
        return None
    flat = " ".join(text.split())
    if ("Permission required" in flat or "Allow once" in flat) and "enter confirm" in flat:
        return True
    if ("Would you like" in flat or "Do you want" in flat) and "❯" in flat:
        return True
    return False


def send(pane, text, limit=SEND_LIMIT):
    """Type text into the pane and submit it. Returns (ok, note)."""
    dialog = on_dialog(pane)
    if dialog is None:
        return False, "pane is gone"
    if dialog:
        return False, "pane is on a dialog (answering it is a human decision)"
    if len(text) > limit:
        return False, (f"text is {len(text)} chars, over the {limit} best-effort limit; "
                       "write it to a file and send a pointer instead")
    first = subprocess.run(["tmux", "send-keys", "-t", pane, "-l", "--", text],
                           capture_output=True, text=True)
    if first.returncode != 0:
        return False, "tmux send-keys failed"
    time.sleep(0.3)
    second = subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"],
                            capture_output=True, text=True)
    if second.returncode != 0:
        return False, "tmux send-keys Enter failed"
    return True, "sent (unverified: no adapter to confirm against)"


def read(pane, lines=LINES):
    """The pane's text, or raise PaneError when the pane is gone."""
    text = capture(pane, lines)
    if text is None:
        raise PaneError(f"pane {pane} is gone")
    return text
