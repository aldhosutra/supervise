#!/usr/bin/env python3
"""Best-effort instruction delivery to an agent that has no adapter.

  send.py <pane> "<text>"
  send.py <pane> --file <path>

There is no transcript and no server to read here, so the instruction goes in
through the pane and cannot be confirmed against anything. It is refused on a
dialog, and capped, and it says it is unverified rather than pretending. For any
agent you use often, write a real adapter instead of leaning on this.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_detect  # noqa: E402
import sv_pane  # noqa: E402


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
    if info is None:
        print(f"REFUSED: no agent is running in pane {args.pane}", file=sys.stderr)
        sys.exit(3)

    ok, note = sv_pane.send(args.pane, text)
    if not ok:
        print(f"REFUSED: {note}", file=sys.stderr)
        sys.exit(2 if "dialog" in note else 3)
    name = info.get("name") or info.get("agent")
    print(f"{note} -> {args.pane} [{name}]")


if __name__ == "__main__":
    main()
