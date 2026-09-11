#!/usr/bin/env python3
"""Read what a supervised session actually said, whichever agent is running it.

Never read a session's output from the tmux pane. A pane is a lossy render:
long replies scroll out of the scrollback, and relaying a silently-trimmed tail
as if it were the whole answer is the worst failure a supervisor can have. The
agent's own record — a transcript file for Claude Code, the server's message
history for opencode — is the ground truth.

  sv-read.py --session <id>              last assistant turn
  sv-read.py --pane work:0.1 --turns 3
  sv-read.py --session <id> --tools      include tool-call names
  sv-read.py --session <id> --sentinel   print any <<<...>>> markers only
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_detect  # noqa: E402

ADAPTERS = {
    "claude": os.path.join(HERE, "adapters", "claude", "read.py"),
    "opencode": os.path.join(HERE, "adapters", "opencode", "read.py"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--transcript", help="a Claude Code transcript file, read directly")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--sentinel", action="store_true")
    args = ap.parse_args()

    if args.transcript:
        # A transcript path only exists for Claude Code; opencode keeps its
        # history behind the server rather than in a file.
        agent, passthrough = "claude", ["--transcript", args.transcript]
    elif args.pane:
        info = sv_detect.for_pane(args.pane)
        if info is None:
            sys.exit(f"no supervisable agent is running in pane {args.pane}")
        agent = info["agent"]
        passthrough = ["--pane", args.pane] if agent == "opencode" else []
        if not passthrough:
            # The Claude adapter reads by session, so turn the pane into one.
            out = subprocess.run(
                [sys.executable, os.path.join(HERE, "sv-resolve.py"),
                 "--pane", args.pane, "--field", "active_session_id"],
                capture_output=True, text=True)
            if out.returncode != 0:
                sys.exit(out.stderr.strip() or f"cannot resolve pane {args.pane}")
            passthrough = ["--session", out.stdout.strip()]
    elif args.session:
        agent = "opencode" if args.session.startswith("ses_") else "claude"
        passthrough = ["--session", args.session]
    else:
        sys.exit("give --session <id>, --pane <pane> or --transcript <path>")

    passthrough += ["--turns", str(args.turns)]
    if args.tools:
        passthrough.append("--tools")
    if args.sentinel:
        passthrough.append("--sentinel")

    sys.exit(subprocess.run([sys.executable, ADAPTERS[agent]] + passthrough).returncode)


if __name__ == "__main__":
    main()
