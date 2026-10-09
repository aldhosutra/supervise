#!/usr/bin/env python3
"""Policy guard: refuse to be the primitive a supervisor hand-polls with.

The skill's rule is simple — when you are async (Claude's `monitor`, or opencode's
`tmux-nudge`), arm the watcher and END YOUR TURN; never hand-write a
`sleep`/`sv-state.sh` loop inside your own turn. Prose can be skipped. This makes
skipping it fail loudly.

The guard is a no-op where it must be:

  * Claude Code (`monitor`)      — the harness wakes you; there is nothing to arm.
  * a plain human / other caller — harness is `unknown`; not our loop to police.
  * the watcher itself           — `SV_WATCHER=1`; it calls sv-state.sh every cycle.
  * sanctioned internal tools    — `SV_GUARD=off` (sv-floor discovery, tests).
  * a deliberate sync run        — `SV_SYNC_OK=1`, an explicit acknowledgement.

Everywhere else, `enforce()` allows while a watcher is registered and alive, and
refuses (exit 9, with the remedy on stderr) when an opencode supervisor is about
to poll with nothing armed.

CLI:
  sv_guard.py check [--primitive NAME]        exit 0 allow / 9 refuse
  sv_guard.py register --pid PID [--panes "p"] [--session NAME]
  sv_guard.py unregister --pid PID
  sv_guard.py status                          JSON {mode, harness, watchers_live, ...}
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAPS = None

REFUSAL = """\
REFUSED: {primitive} was called by an opencode supervisor in mode '{mode}' with no \
watcher armed and no synchronous acknowledgement.

That call is the busy-poll anti-pattern the skill exists to prevent: a hand-written \
loop over sv-state.sh / sv-read.py holds your turn open, so the [sv-wake ...] lines \
the watcher sends queue up behind you and the run stalls while looking busy.

Do one of these, then END YOUR TURN and let the wake start the next one:

  1. Arm the watcher (one command; works for every supervised pane at once):
       {arm}

  2. If you are deliberately running the degraded synchronous path (mode 'sync'),
     say so out loud to the user and acknowledge it explicitly:
       SV_SYNC_OK=1 <command>          # or: export SV_SYNC_OK=1

(Internal tooling and tests may set SV_GUARD=off; the watcher sets SV_WATCHER=1.)
""".format(primitive="{primitive}", mode="{mode}", arm=os.path.join(SCRIPTS, "sv-arm.sh"))


# --- capability probe -------------------------------------------------------

def capabilities():
    """How this supervisor can be woken. `SV_GUARD_FORCE_MODE` overrides for tests."""
    global _CAPS
    if _CAPS is not None:
        return _CAPS
    forced = os.environ.get("SV_GUARD_FORCE_MODE")
    if forced:
        harness = {"monitor": "claude", "tmux-nudge": "opencode",
                   "sync": "opencode"}.get(forced, "unknown")
        _CAPS = {"harness": harness, "mode": forced}
        return _CAPS
    _CAPS = {"harness": "unknown", "mode": "sync"}
    try:
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "sv-capability.py")],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            _CAPS = json.loads(out.stdout)
    except Exception:
        pass
    return _CAPS


# --- watcher registry -------------------------------------------------------

def state_dir():
    d = os.environ.get("SV_STATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "sv-supervise")
    os.makedirs(d, exist_ok=True)
    return d


def _state_file():
    return os.path.join(state_dir(), "state.json")


def _load():
    try:
        with open(_state_file()) as f:
            return json.load(f)
    except Exception:
        return {}


def _update(mutate):
    """Read-modify-write the registry under a lock, atomically."""
    d = state_dir()
    lock = open(os.path.join(d, ".lock"), "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        st = _load()
        mutate(st)
        tmp = _state_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, _state_file())
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False
    return True


def watchers_live():
    """Registered watchers whose process is still alive (stale entries pruned)."""
    ws = _load().get("watchers", {})
    live = {p: v for p, v in ws.items() if _alive(p)}
    if len(live) != len(ws):
        _update(lambda s: s.__setitem__("watchers", live))
    return live


def register(pid, panes, session):
    entry = {"panes": panes, "session": session or "", "started": int(time.time())}
    _update(lambda s: s.setdefault("watchers", {}).__setitem__(str(pid), entry))


def unregister(pid):
    def drop(s):
        s.get("watchers", {}).pop(str(pid), None)
    _update(drop)


# --- the gate ---------------------------------------------------------------

def enforce(primitive="sv-state.sh"):
    """0 = allowed. 9 = refused (remedy already written to stderr)."""
    if os.environ.get("SV_GUARD") == "off":
        return 0
    if os.environ.get("SV_WATCHER") == "1":
        return 0
    if os.environ.get("SV_SYNC_OK") == "1":
        return 0

    caps = capabilities()
    harness = caps.get("harness")
    mode = caps.get("mode", "sync")

    # Claude Code is woken by its harness; a human or unknown caller is not ours.
    if harness in ("claude", "unknown", "", None):
        return 0

    # opencode: the watcher is the wake channel. Allowed once it is armed and alive.
    if watchers_live():
        return 0

    sys.stderr.write(REFUSAL.format(primitive=primitive, mode=mode))
    return 9


# --- CLI --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check")
    c.add_argument("--primitive", default="sv-state.sh")

    r = sub.add_parser("register")
    r.add_argument("--pid", required=True)
    r.add_argument("--panes", default="")
    r.add_argument("--session", default="")

    u = sub.add_parser("unregister")
    u.add_argument("--pid", required=True)

    sub.add_parser("status")

    args = ap.parse_args()

    if args.cmd == "check":
        sys.exit(enforce(args.primitive))
    if args.cmd == "register":
        register(args.pid, args.panes.split(), args.session)
        return
    if args.cmd == "unregister":
        unregister(args.pid)
        return
    if args.cmd == "status":
        caps = capabilities()
        live = watchers_live()
        print(json.dumps({
            "mode": caps.get("mode"),
            "harness": caps.get("harness"),
            "watchers_live": len(live),
            "watchers": live,
        }, indent=2))
        return


if __name__ == "__main__":
    main()
