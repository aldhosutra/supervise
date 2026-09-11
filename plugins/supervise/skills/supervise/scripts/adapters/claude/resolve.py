#!/usr/bin/env python3
"""Resolve Claude Code sessions to their live transcript and tmux pane.

The hard problem this solves: a session's `sessionId` changes every time the user
runs /clear, but a supervisor needs to keep following the same terminal. Every
transcript line carries a `bridgeSessionId` that is stable for the life of the
terminal, so that is the identity we track. Give this any sessionId in a lineage
and it finds the currently-active transcript for that terminal.

  resolve.py --list                 every session, newest first
  resolve.py --session <id>         resolve one (JSON)
  resolve.py --pane work:0.1        resolve by pane instead
  resolve.py --session <id> --field transcript
"""
import argparse, glob, json, os, re, subprocess, sys

PROJECTS = os.path.expanduser("~/.claude/projects")


def bridge_of(path):
    """Read the bridgeSessionId without parsing the whole file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                m = re.search(r'"bridgeSessionId":"([^"]+)"', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def cwd_of(path):
    """The working directory the session runs in, from its first message line."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(60):
                line = fh.readline()
                if not line:
                    break
                m = re.search(r'"cwd":"([^"]+)"', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def all_sessions():
    out = []
    for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        out.append({
            "session_id": os.path.basename(f)[:-6],
            "transcript": f,
            "bridge": bridge_of(f),
            "project_dir": os.path.basename(os.path.dirname(f)),
            "cwd": cwd_of(f),
            "mtime": os.path.getmtime(f),
            "size": os.path.getsize(f),
        })
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


def process_table():
    """pid -> (ppid, command) for every process."""
    try:
        raw = subprocess.run(["ps", "-ax", "-o", "pid=,ppid=,command="],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return {}
    table = {}
    for line in raw.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2])
    return table


def tmux_panes():
    fmt = "#{pane_pid}\t#{session_name}:#{window_index}.#{pane_index}\t#{pane_current_path}"
    try:
        raw = subprocess.run(["tmux", "list-panes", "-a", "-F", fmt],
                             capture_output=True, text=True, timeout=10)
        if raw.returncode != 0:
            return []
    except Exception:
        return []
    panes = []
    for line in raw.stdout.splitlines():
        bits = line.split("\t")
        if len(bits) == 3 and bits[0].isdigit():
            panes.append({"pane_pid": int(bits[0]), "pane": bits[1], "path": bits[2]})
    return panes


def claude_in_pane(pane_pid, table):
    """Depth-first search for a `claude` process under this pane's shell."""
    stack, seen = [pane_pid], set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        for child, (parent, cmd) in table.items():
            if parent != pid:
                continue
            base = cmd.split()[0].rsplit("/", 1)[-1] if cmd else ""
            if base == "claude" or " claude " in f" {cmd} ":
                return child, cmd
            stack.append(child)
    return None, None


def map_panes(sessions):
    """Attach each tmux pane to a bridge id.

    Two routes, in order of reliability:
      1. `claude --resume <id>` on the command line - that id names a lineage.
      2. The pane's working directory, matched against the most recently written
         session in that project. Used when the session was started fresh.
    """
    table = process_table()
    by_id = {s["session_id"]: s for s in sessions}
    mapped = []
    for pane in tmux_panes():
        pid, cmd = claude_in_pane(pane["pane_pid"], table)
        if pid is None:
            continue
        entry = {**pane, "claude_pid": pid, "cmd": cmd, "bridge": None, "how": None}
        m = re.search(r"--resume\s+([0-9a-f-]{36})", cmd or "")
        if m and m.group(1) in by_id:
            entry["bridge"] = by_id[m.group(1)]["bridge"]
            entry["how"] = "resume-flag"
        else:
            here = [s for s in sessions if s["cwd"] == pane["path"]]
            if here:
                entry["bridge"] = here[0]["bridge"]
                entry["how"] = "cwd+recency"
        mapped.append(entry)
    return mapped


def active_for(bridge, sessions):
    """The newest transcript in a lineage - i.e. the one after the last /clear."""
    same = [s for s in sessions if s["bridge"] == bridge and bridge]
    return same[0] if same else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--pane")
    ap.add_argument("--field")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sessions = all_sessions()
    panes = map_panes(sessions)
    pane_by_bridge = {p["bridge"]: p for p in panes if p["bridge"]}

    if args.list:
        seen = set()
        rows = []
        for s in sessions:
            if s["bridge"] in seen:
                continue          # one row per lineage, newest wins
            seen.add(s["bridge"])
            p = pane_by_bridge.get(s["bridge"])
            rows.append({
                "session_id": s["session_id"], "bridge": s["bridge"],
                "cwd": s["cwd"], "pane": p["pane"] if p else None,
                "how": p["how"] if p else None, "mtime": s["mtime"],
            })
        # Panes running Claude that no transcript matches yet: a session that has
        # only just started, or one still on its trust dialog, has written nothing
        # to disk. Show them rather than letting them be invisible.
        claimed = {r["pane"] for r in rows if r["pane"]}
        for p in panes:
            if p["pane"] not in claimed:
                rows.append({"session_id": None, "bridge": p["bridge"],
                             "cwd": p["path"], "pane": p["pane"],
                             "how": "unmatched", "mtime": 0})
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(f"{'SESSION':38} {'PANE':12} {'HOW':14} CWD")
            for r in rows:
                sid = r["session_id"] or "(no transcript yet)"
                print(f"{sid:38} {str(r['pane'] or '-'):12} "
                      f"{str(r['how'] or '-'):14} {r['cwd'] or '-'}")
        return

    if args.pane:
        # Resolving by pane is how the dispatcher reaches an agent it found by
        # looking at the process tree rather than by being handed an id.
        pane_here = next((p for p in panes if p["pane"] == args.pane), None)
        if not pane_here:
            sys.exit(f"no Claude session is running in pane {args.pane}")
        bridge = pane_here["bridge"]
        match = active_for(bridge, sessions)
        if not match:
            sys.exit(f"pane {args.pane} has not written a transcript yet")
    elif args.session:
        match = next((s for s in sessions if s["session_id"] == args.session), None)
        if not match:
            sys.exit(f"no transcript for session {args.session}")
        bridge = match["bridge"]
    else:
        sys.exit("give --list, --session <id> or --pane <pane>")

    active = active_for(bridge, sessions) or match
    pane = pane_by_bridge.get(bridge)
    result = {
        "agent": "claude",
        "asked_for": args.session or args.pane,
        "bridge": bridge,
        "active_session_id": active["session_id"],
        "transcript": active["transcript"],
        "cwd": active["cwd"],
        "pane": pane["pane"] if pane else None,
        "claude_pid": pane["claude_pid"] if pane else None,
        "mapped_by": pane["how"] if pane else None,
        "cleared_since": bool(args.session) and active["session_id"] != args.session,
    }
    if args.field:
        value = result.get(args.field)
        if value is None:
            sys.exit(f"{args.field} is not known for this session")
        print(value)
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
