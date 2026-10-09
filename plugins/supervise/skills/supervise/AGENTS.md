# supervise — agent contract

If you are acting as the supervisor in a `/supervise` run, these are non-negotiable.

1. **Find the wake mode first**, with `scripts/sv-capability.py`, and say it out loud.
2. **`monitor` (Claude Code):** the harness wakes you. **Nothing to arm.**
3. **`tmux-nudge` (opencode in tmux):** run `scripts/sv-arm.sh <pane>...`, then
   **END YOUR TURN**. The watcher starts your next turn on a transition.
4. **`sync`:** nothing can wake you. Restore the channel (relaunch inside tmux) or
   acknowledge the degraded path with `SV_SYNC_OK=1` and tell the user — never a silent loop.
5. **Never write a `sleep` / `while` / `for` loop over `sv-state.sh` or `sv-read.py` inside
   your own turn.** It holds the turn open and queues `[sv-wake ...]` lines behind you.
6. This is enforced: `sv-state.sh` and `sv-read.py` **refuse** (exit 9, with the remedy)
   when an opencode supervisor calls them with no watcher armed. `sv-floor.py` (one-call
   discovery) and `sv-watch.sh` (the watcher) are exempt. `SV_SYNC_OK=1` and `SV_GUARD=off`
   are the explicit escape hatches; use them only deliberately.

Why: the supervisor's value is that it is *reactive* — it processes a wake and goes back to
waiting. A supervisor that polls is blind to the difference between "working" and "stalled",
and no user watching tmux can tell either.
