#!/usr/bin/env python3
"""Read a pane for an agent that has no adapter. Lossy, and says so.

  read.py --pane <pane> [--lines N]

There is no transcript and no server, so the screen is all there is. A pane
scrolls, so a long reply arrives as its tail; the banner is there so a reader
never mistakes that tail for the whole answer.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))

import sv_pane  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pane", required=True)
    ap.add_argument("--lines", type=int, default=sv_pane.LINES)
    args = ap.parse_args()

    try:
        text = sv_pane.read(args.pane, args.lines)
    except sv_pane.PaneError as exc:
        sys.exit(str(exc))

    print("# LOSSY PANE READ — no adapter for this agent. The screen scrolls, so a")
    print("# long reply arrives as its tail. Treat this as a signal, not the answer.")
    print("-" * 72)
    print(text.rstrip())


if __name__ == "__main__":
    main()
