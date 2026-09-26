#!/usr/bin/env python3
"""A smoke test for the skill's own primitives. Run after any change.

Deterministic and offline: it stands up throwaway tmux panes for the pane-level
paths (a fake "other" agent and a fake dialog) and exercises the binding,
detection, floor and database helpers directly. It does not call a model, and it
removes everything it created unless --keep is given.

  scripts/sv-selftest.py [--keep]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

import sv_bind as bind  # noqa: E402
import sv_opencode_db as db  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else f"  — {detail}"))


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    root = tempfile.mkdtemp(prefix="sv-selftest-")
    os.environ["SV_STATE_DIR"] = os.path.join(root, "state")
    sessions = []

    def tmux_new(name, command, cwd):
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "50",
                        "-c", cwd], capture_output=True)
        subprocess.run(["tmux", "send-keys", "-t", f"{name}:0.0", command, "Enter"],
                       capture_output=True)
        sessions.append(name)

    try:
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        os.symlink("/bin/cat", os.path.join(bindir, "aider"))
        gen = os.path.join(root, "gen")
        os.makedirs(gen)
        tmux_new("svself-gen", f"PATH={bindir}:$PATH aider", gen)

        dlg = os.path.join(root, "dlg")
        os.makedirs(dlg)
        tmux_new("svself-dlg",
                 "printf '  Permission required\\n  Allow once   Allow always   Reject\\n"
                 "  ctrl+f fullscreen  ⇆ select  enter confirm\\n'; sleep 600", dlg)
        time.sleep(2)

        out = run([sys.executable, os.path.join(HERE, "sv-capability.py"), "--field", "mode"])
        check("capability reports a mode", out.stdout.strip() in ("monitor", "tmux-nudge", "sync"),
              out.stdout.strip())

        out = run([sys.executable, os.path.join(HERE, "lib", "sv_detect.py"), "--all"])
        try:
            rows = json.loads(out.stdout)
            ok = isinstance(rows, list) and all("harness" in r for r in rows)
        except ValueError:
            ok = False
        check("sv_detect --all", ok)

        out = run([sys.executable, os.path.join(HERE, "sv-floor.py"), "--json"])
        try:
            fr = json.loads(out.stdout)
            ok = isinstance(fr, list) and all({"pane", "harness", "state"} <= set(r) for r in fr)
        except ValueError:
            ok = False
        check("sv-floor --json", ok)

        out = run([os.path.join(HERE, "sv-state.sh"), "svself-gen:0.0"])
        check("other agent -> UNKNOWN", out.stdout.strip() == "UNKNOWN", out.stdout.strip())

        out = run([os.path.join(HERE, "sv-send.sh"), "svself-gen:0.0", "SELFTEST-hello"])
        check("generic send", out.returncode == 0
              and "sent" in (out.stdout + out.stderr).lower(), out.stdout.strip())
        time.sleep(1)
        out = run([sys.executable, os.path.join(HERE, "sv-read.py"), "--pane", "svself-gen:0.0"])
        check("generic read shows the text", "SELFTEST-hello" in out.stdout)

        out = run([sys.executable, os.path.join(HERE, "sv-nudge.py"), "--pane", "svself-dlg:0.0",
                   "--token", "x", "--text", "y"])
        check("nudge holds on a dialog", out.returncode == 3, f"exit={out.returncode}")

        bind.put("9:9.9", "ses_bogus", "opencode")
        check("stale opencode binding dropped", bind.valid("9:9.9", "opencode") is None)

        real = db.sessions_in(os.path.expanduser("~"))
        if real:
            bind.put("9:9.8", real[0][0], "opencode")
            check("live opencode binding kept",
                  (bind.valid("9:9.8", "opencode") or {}).get("session_id") == real[0][0])

        bind.put("9:9.7", "no-such-claude-id", "claude")
        check("stale claude binding dropped", bind.valid("9:9.7", "claude") is None)

        claude_files = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
        if claude_files:
            sid = os.path.basename(claude_files[0])[:-6]
            bind.put("9:9.5", sid, "claude")
            check("live claude binding kept",
                  (bind.valid("9:9.5", "claude") or {}).get("session_id") == sid)

        bind.put("9:9.6", "ses_whatever", "opencode")
        check("wrong-agent binding dropped", bind.valid("9:9.6", "claude") is None)

        empty = os.path.join(root, "empty")
        os.makedirs(empty)
        check("sessions_in(empty directory) is empty", db.sessions_in(empty) == [])
    finally:
        if not args.keep:
            for name in sessions:
                subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
            shutil.rmtree(root, ignore_errors=True)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
