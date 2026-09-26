#!/usr/bin/env python3
"""Give an opencode pane its next instruction, and confirm it arrived.

  send.py <pane> "<text>"
  send.py <pane> --file <path>

The Claude adapter types into the terminal with `tmux send-keys`, which
silently truncates long input — hence its 120-character limit and the
write-a-file-and-send-a-pointer habit. opencode takes the prompt over its API,
so there is no truncation to defend against and long instructions can go
straight through. The file route stays available for anything genuinely long,
because a standing instruction the session can re-read still beats one that
exists only in its context.

This goes through the TUI's own prompt box rather than posting a message
behind its back, so the instruction appears on screen exactly as a watching
user would see it typed.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_detect  # noqa: E402
import sv_opencode as oc  # noqa: E402
import sv_pane  # noqa: E402
from state import classify  # noqa: E402


def user_texts(base_url, session_id):
    out = []
    for message in oc.messages(base_url, session_id):
        if (message.get("info", {}) or {}).get("role") != "user":
            continue
        out.append("".join(p.get("text", "") for p in message.get("parts", [])
                           if p.get("type") == "text"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pane")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--file", help="read the instruction from this file instead")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    elif args.text:
        text = args.text
    else:
        sys.exit("usage: send.py <pane> <text> | send.py <pane> --file <path>")
    if not text:
        sys.exit("REFUSED: nothing to send")

    info = sv_detect.for_pane(args.pane)
    if info is None or info["agent"] != "opencode":
        print(f"REFUSED: no opencode session in pane {args.pane}", file=sys.stderr)
        sys.exit(3)
    if not info["base_url"]:
        # A TUI started without --port serves no HTTP, but opencode still writes
        # the message to its database. Deliver through the pane and confirm
        # against that database rather than guessing.
        ok, note = sv_pane.send(args.pane, text)
        if not ok:
            print(f"REFUSED: {note}", file=sys.stderr)
            sys.exit(2 if "dialog" in note else 3)
        import sv_opencode_db as db
        session_id = db.latest_session(info.get("cwd") or "")
        deadline = time.time() + float(os.environ.get("SV_SEND_CONFIRM_SECONDS", "15"))
        while session_id and time.time() < deadline:
            time.sleep(1.5)
            try:
                if text.strip()[:60] in db.last_user_text(session_id):
                    print(f"VERIFIED via db ({len(text)} chars) -> {args.pane} "
                          f"[{session_id}]")
                    return
            except Exception:
                break
        print(f"{note} -> {args.pane} [opencode, no server]")
        return
    base = info["base_url"]

    state = classify(args.pane)
    if state == "GONE":
        print(f"REFUSED: pane {args.pane} is gone", file=sys.stderr)
        sys.exit(3)
    if state == "PROMPT":
        print(f"REFUSED: {args.pane} is waiting on a dialog. Answering it is a "
              "human decision.", file=sys.stderr)
        sys.exit(2)

    session, _ = oc.current_session(base, info["cwd"])
    before = len(user_texts(base, session["id"])) if session else 0
    before_id = session["id"] if session else None

    try:
        oc.clear_prompt(base)
        oc.append_prompt(base, text)
        oc.submit_prompt(base)
    except oc.OpencodeError as exc:
        print(f"FAILED to send: {exc}", file=sys.stderr)
        sys.exit(5)

    # Confirm it landed rather than trusting the call that sent it. A prompt
    # can be accepted by the TUI and still not reach a session — if the pane
    # was on a modal, say — and reporting a delivery that did not happen is
    # how a supervisor ends up waiting forever on a session it never spoke to.
    deadline = time.time() + float(os.environ.get("SV_SEND_CONFIRM_SECONDS", "15"))
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            # Re-resolve on every poll rather than pinning the session we saw
            # before sending. A TUI opened in a directory with history shows an
            # empty new session that opencode has not written down yet, so the
            # prompt lands in a session that did not exist a moment ago -
            # holding on to the old one reports a delivery failure that did not
            # happen.
            session, _ = oc.current_session(base, info["cwd"])
            if not session:
                continue
            if session["id"] != before_id:
                before = 0
            texts = user_texts(base, session["id"])
            if len(texts) > before and text.strip()[:60] in texts[-1]:
                print(f"VERIFIED ({len(text)} chars) -> {args.pane} "
                      f"[{session['id']}]")
                return
            if oc.status(base).get(session["id"]):
                print(f"ACCEPTED ({len(text)} chars) -> {args.pane} "
                      f"[{session['id']}] — the session is working on it")
                return
        except oc.OpencodeError:
            continue

    print("VERIFY FAILED — the prompt was submitted but no matching message "
          f"appeared in the session. Look at pane {args.pane}.", file=sys.stderr)
    sys.exit(5)


if __name__ == "__main__":
    main()
