#!/usr/bin/env python3
"""Talk to a running opencode instance over its own HTTP server.

Every opencode TUI serves an HTTP API — on a random port unless it was given
`--port`. That server is a far better supervision channel than the terminal:
session state, the message history and the pending-permission queue are all
first-class there, so we never have to guess at what a screen means.

We still run opencode inside tmux, because the point of this skill is that the
user can attach and watch. The API is how we read and drive; the pane is how a
human looks over its shoulder.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = float(os.environ.get("SV_HTTP_TIMEOUT", "10"))


class OpencodeError(RuntimeError):
    pass


def _auth_header():
    """opencode servers started with OPENCODE_SERVER_PASSWORD want basic auth."""
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if not password:
        return {}
    import base64
    user = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def request(base_url, path, method="GET", body=None, params=None):
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    data = json.dumps(body if body is not None else {}).encode() if method == "POST" else None
    headers = {"content-type": "application/json", **_auth_header()}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise OpencodeError(f"{method} {path} -> HTTP {exc.code}") from exc
    except Exception as exc:
        raise OpencodeError(f"{method} {path} -> {exc}") from exc
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def reachable(base_url):
    try:
        request(base_url, "/session")
        return True
    except OpencodeError:
        return False


def sessions(base_url, directory=None):
    """Sessions this server knows about, newest first.

    The server lists every project it has seen, not just the one the TUI has
    open, so filtering by directory is the caller's job and we do it here
    rather than trusting a query parameter to have narrowed anything.
    """
    data = request(base_url, "/session") or []
    if isinstance(data, dict):
        data = data.get("data", [])
    if directory:
        want = os.path.realpath(directory)
        data = [s for s in data if os.path.realpath(s.get("directory", "")) == want]
    return sorted(data, key=lambda s: (s.get("time", {}) or {}).get("updated", 0), reverse=True)


def current_session(base_url, directory):
    """The session a pane is working in, and how sure we are of it.

    Two signals, in order of authority:

      busy          the server names the session it is running right now. This
                    is the TUI's open session, no inference involved.
      cwd+recency   nothing is running, so fall back to the most recently
                    updated session in this directory.

    The fallback is a guess, and it is wrong in one case worth knowing about: a
    TUI freshly opened in a directory that already has history shows an empty
    new session, while the newest stored session is the previous one. opencode
    does not write the new session down until its first message, so there is
    nothing better to point at until then. Callers that must not act on a guess
    check the `how` this returns.
    """
    found = sessions(base_url, directory)
    if not found:
        return None, "no-session-yet"
    running = status(base_url)
    for session in found:
        if session["id"] in running:
            return session, "busy"
    return found[0], "cwd+recency"


def messages(base_url, session_id):
    data = request(base_url, f"/session/{session_id}/message") or []
    if isinstance(data, dict):
        data = data.get("data", [])
    return data


def status(base_url):
    """{session_id: {"type": "busy"}} for whatever is working right now."""
    data = request(base_url, "/session/status") or {}
    return data if isinstance(data, dict) else {}


def pending_permissions(base_url, session_id=None):
    """Permission requests waiting for a human.

    One TUI, one server, so the unfiltered list is normally right — but a shared
    `opencode serve` can hold several sessions, hence the filter.
    """
    data = request(base_url, "/permission") or []
    if isinstance(data, dict):
        data = data.get("data", [])
    if session_id:
        data = [p for p in data if p.get("sessionID") == session_id]
    return data


def pending_questions(base_url, session_id=None):
    try:
        data = request(base_url, "/question") or []
    except OpencodeError:
        return []
    if isinstance(data, dict):
        data = data.get("data", [])
    if session_id:
        data = [q for q in data if q.get("sessionID") == session_id]
    return data


def append_prompt(base_url, text):
    return request(base_url, "/tui/append-prompt", "POST", {"text": text})


def clear_prompt(base_url):
    return request(base_url, "/tui/clear-prompt", "POST", {})


def submit_prompt(base_url):
    return request(base_url, "/tui/submit-prompt", "POST", {})
