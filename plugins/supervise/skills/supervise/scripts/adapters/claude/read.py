#!/usr/bin/env python3
"""Read what a supervised session actually said, from its transcript.

Never read a session's output from the tmux pane. A pane is a lossy render: long
replies scroll out of the scrollback, and relaying a silently-trimmed tail as if
it were the whole answer is the worst failure a supervisor can have. The
transcript on disk is the ground truth.

  sv-read.py --session <id>              last assistant turn
  sv-read.py --session <id> --turns 3
  sv-read.py --transcript <path> --tools  include tool-call names
  sv-read.py --session <id> --sentinel    print any <<<...>>> markers only
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def wait_for_reply(path, timeout):
    """Block until the latest user turn has a completed assistant reply."""
    def replied():
        events = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                kind = d.get("type")
                if kind not in ("user", "assistant"):
                    continue
                msg = d.get("message", {}) or {}
                content = msg.get("content")
                if kind == "user" and isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content):
                    continue
                events.append((kind, msg.get("stop_reason") if kind == "assistant" else None))
        last_user = None
        for i, (kind, _) in enumerate(events):
            if kind == "user":
                last_user = i
        if last_user is None:
            return False
        return any(kind == "assistant" and stop for kind, stop in events[last_user + 1:])

    deadline = time.time() + timeout
    while True:
        if replied():
            return
        if time.time() >= deadline:
            return
        time.sleep(1.0)


def resolve(session_id):
    out = subprocess.run([sys.executable, os.path.join(HERE, "resolve.py"),
                          "--session", session_id],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stderr.strip() or f"cannot resolve {session_id}")
    return json.loads(out.stdout)


def text_of(msg, with_tools):
    content = msg.get("content")
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block["text"])
        elif block.get("type") == "tool_use" and with_tools:
            parts.append(f"    [tool: {block.get('name')}]")
    return "\n".join(parts)


def turns_of(path, with_tools):
    events = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            kind = d.get("type")
            if kind not in ("user", "assistant"):
                continue
            msg = d.get("message", {}) or {}
            content = msg.get("content")
            # Tool results are logged as type "user" but are not a human turn.
            if kind == "user" and isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            body = text_of(msg, with_tools)
            if kind == "user" and not body.strip():
                continue
            events.append((kind, body, d.get("timestamp", "")))

    turns, current = [], None
    for kind, body, ts in events:
        if kind == "user":
            if current:
                turns.append(current)
            current = {"user": body, "assistant": [], "ts": ts}
        elif current is not None and body.strip():
            current["assistant"].append(body)
    if current:
        turns.append(current)
    return turns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--transcript")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--sentinel", action="store_true")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--wait-timeout", type=float,
                    default=float(os.environ.get("SV_WAIT_SECONDS", "120")))
    args = ap.parse_args()

    if args.transcript:
        path, note = args.transcript, ""
    elif args.session:
        info = resolve(args.session)
        path = info["transcript"]
        note = ("  [note: /clear has happened since; now reading "
                f"{info['active_session_id']}]" if info["cleared_since"] else "")
    else:
        sys.exit("give --session <id> or --transcript <path>")

    if args.wait:
        wait_for_reply(path, args.wait_timeout)

    turns = turns_of(path, args.tools)
    if not turns:
        sys.exit("no turns found in that transcript")

    if args.sentinel:
        body = "\n".join("\n".join(t["assistant"]) for t in turns[-args.turns:])
        found = re.findall(r"<<<[^>]{0,200}>>>", body)
        print("\n".join(found) if found else "(no sentinel in the last "
              f"{args.turns} turn(s))")
        return

    for turn in turns[-args.turns:]:
        print("=" * 72)
        print(f"USER [{turn['ts'][:19]}]: {turn['user'][:400].strip()}")
        print("-" * 72)
        print("\n".join(turn["assistant"]).strip() or "(no assistant text)")
    print("=" * 72)
    print(f"[{os.path.basename(path)}, {len(turns)} turns]{note}")


if __name__ == "__main__":
    main()
