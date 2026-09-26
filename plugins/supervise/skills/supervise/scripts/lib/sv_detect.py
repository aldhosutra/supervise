#!/usr/bin/env python3
"""Work out which coding agent is running in a tmux pane.

Everything above this file is agent-agnostic; everything below it is an adapter.
The whole supervision model — a pane the user can attach to, a transcript read
from the agent's own records rather than the screen, a state machine of
BUSY/IDLE/PROMPT — holds for Claude Code and opencode alike. Only the mechanics
differ, and this is where we decide which mechanics apply.

  sv_detect.py --pane work:0.1              JSON for one pane
  sv_detect.py --all                        JSON for every pane running an agent
  sv_detect.py --pane work:0.1 --field agent
"""
import argparse
import json
import re
import subprocess
import sys

# Agents with a real adapter: a transcript file (Claude Code) or a server (opencode).
ADAPTER_BINARIES = {"claude": "claude", "opencode": "opencode"}
# Other agent CLIs we can see but not read. They are reported honestly as harness
# "other" (and driven best-effort over the pane) rather than misreported as gone.
OTHER_BINARIES = {
    "codex", "aider", "gemini", "cursor-agent", "goose", "crush", "amp",
    "droid", "qwen", "copilot", "opencode-go",
}
# basename -> harness
AGENT_BINARIES = {**ADAPTER_BINARIES, **{b: "other" for b in OTHER_BINARIES}}


def run(cmd, timeout=10):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def process_table():
    """pid -> (ppid, command) for every process."""
    table = {}
    for line in run(["ps", "-ax", "-o", "pid=,ppid=,command="]).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2])
    return table


def tmux_panes():
    fmt = "#{pane_pid}\t#{session_name}:#{window_index}.#{pane_index}\t#{pane_current_path}"
    panes = []
    for line in run(["tmux", "list-panes", "-a", "-F", fmt]).splitlines():
        bits = line.split("\t")
        if len(bits) == 3 and bits[0].isdigit():
            panes.append({"pane_pid": int(bits[0]), "pane": bits[1], "path": bits[2]})
    return panes


def basename_of(cmd):
    return cmd.split()[0].rsplit("/", 1)[-1] if cmd else ""


def agents_under(root_pid, table):
    """Every agent process in this pane's process tree, shallowest first.

    An agent often has helper children of the same name, so we collect all of
    them rather than returning the first hit: the caller picks by evidence
    (which one is listening on a port, say) instead of by luck.
    """
    found, stack, seen = [], [(root_pid, 0)], set()
    while stack:
        pid, depth = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        for child, (parent, cmd) in table.items():
            if parent != pid:
                continue
            base = basename_of(cmd)
            if base in AGENT_BINARIES:
                found.append({"pid": child, "cmd": cmd, "agent": AGENT_BINARIES[base],
                              "depth": depth})
            stack.append((child, depth + 1))
    found.sort(key=lambda p: (p["depth"], p["pid"]))
    return found


def listening_port(pid):
    """The TCP port a process is listening on, or None."""
    raw = run(["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"])
    for line in raw.splitlines()[1:]:
        m = re.search(r":(\d+)\s*(?:\(LISTEN\))?\s*$", line)
        if m:
            return int(m.group(1))
    return None


def opencode_port(candidates):
    """Find the port an opencode TUI serves on.

    Two routes: the `--port` it was started with (cheap, and what sv-launch
    always sets), then lsof across the tree (covers a TUI the user started
    themselves, where the port is random).
    """
    for proc in candidates:
        m = re.search(r"--port[= ](\d+)", proc["cmd"] or "")
        if m and int(m.group(1)) != 0:
            return int(m.group(1)), proc["pid"]
    for proc in candidates:
        port = listening_port(proc["pid"])
        if port:
            return port, proc["pid"]
    return None, (candidates[0]["pid"] if candidates else None)


def describe(pane):
    """What is running in this pane, if anything we know how to supervise."""
    table = process_table()
    procs = agents_under(pane["pane_pid"], table)
    if not procs:
        return None
    agent = procs[0]["agent"]
    procs = [p for p in procs if p["agent"] == agent]
    info = {"pane": pane["pane"], "cwd": pane["path"], "agent": agent,
            "harness": agent, "name": basename_of(procs[0]["cmd"]),
            "pid": procs[0]["pid"], "cmd": procs[0]["cmd"], "port": None,
            "base_url": None}
    if agent == "opencode":
        port, pid = opencode_port(procs)
        info["port"] = port
        info["pid"] = pid or info["pid"]
        if port:
            info["base_url"] = f"http://127.0.0.1:{port}"
    return info


def all_agent_panes():
    out = []
    for pane in tmux_panes():
        info = describe(pane)
        if info:
            out.append(info)
    return out


def for_pane(pane_id):
    for pane in tmux_panes():
        if pane["pane"] == pane_id:
            return describe(pane)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pane")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--field")
    args = ap.parse_args()

    if args.all:
        print(json.dumps(all_agent_panes(), indent=2))
        return
    if not args.pane:
        sys.exit("give --pane <pane> or --all")

    info = for_pane(args.pane)
    if info is None:
        sys.exit(f"no supervisable agent is running in pane {args.pane}")
    if args.field:
        value = info.get(args.field)
        if value is None:
            sys.exit(f"{args.field} is not known for {args.pane}")
        print(value)
    else:
        print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
