#!/usr/bin/env bash
# Copy the Claude allowance figures somewhere a run can read them.
#
#   statusLine.command:  bash ~/.claude/usage-snapshot.sh <your original status-line command>
#
# Claude Code publishes the live subscription figures — percent of the 5-hour window used, percent of
# the week used, and when each resets — to exactly one place: the status-line command's stdin. No hook
# receives them and no endpoint serves them, so a run that wants to know how much allowance is left
# has to be handed them from here.
#
# This is a WRAPPER, never an edit. It tees the figures to ~/.claude/usage-snapshot.json and then runs
# whatever status-line command was configured before, on the same stdin, printing its output verbatim.
# Removing this one indirection from settings.json undoes the whole thing.
#
# Three properties, because a wrong file here is worse than no file:
#   * stamped   — every write carries written_at; no reader may use a figure without it
#   * atomic    — temp file + mv, so a reader never catches a half-written file
#   * harmless  — no jq, no writable home, malformed input, absent rate_limits: do nothing, pass
#                 through. The status line must never break because of this wrapper.
#
# `rate_limits` is absent for API-key auth, and absent on a subscription until the session's first API
# response. Absent means LEAVE THE EXISTING FILE ALONE — overwriting a good snapshot with nulls would
# make every reader report unknown for the rest of the session.
#
# Pair it with `"refreshInterval": 60` on the statusLine setting. The status line is event-driven and
# goes quiet exactly while a mission runs, because the main session sits still waiting on background
# subagents — without the timer this file freezes at whatever it said when the mission began.
#
# Copied VERBATIM from the plugin's shared/usage-snapshot.sh — fix it there, never the copy.

SNAPSHOT="${CLAUDE_USAGE_SNAPSHOT:-$HOME/.claude/usage-snapshot.json}"

input=$(cat)

# ---- tee the figures (best effort; every failure is silent by design) -------------------------
if command -v jq >/dev/null 2>&1; then
  snap=$(printf '%s' "$input" | jq -c '
    (.rate_limits // {}) as $r
    | select(($r.five_hour // $r.seven_day) != null)
    | {
        written_at: (now | floor),
        five_hour:  (if $r.five_hour  then {used_percentage: $r.five_hour.used_percentage,  resets_at: $r.five_hour.resets_at}  else null end),
        seven_day:  (if $r.seven_day  then {used_percentage: $r.seven_day.used_percentage,  resets_at: $r.seven_day.resets_at}  else null end)
      }' 2>/dev/null)

  # Empty output means rate_limits was absent — keep whatever is already on disk.
  if [ -n "$snap" ]; then
    dir=$(dirname "$SNAPSHOT")
    if mkdir -p "$dir" 2>/dev/null && tmp=$(mktemp "$SNAPSHOT.XXXXXX" 2>/dev/null); then
      if printf '%s\n' "$snap" >"$tmp" 2>/dev/null; then
        mv -f "$tmp" "$SNAPSHOT" 2>/dev/null || rm -f "$tmp" 2>/dev/null
      else
        rm -f "$tmp" 2>/dev/null
      fi
    fi
  fi
fi

# ---- hand the same stdin to the original status-line command ----------------------------------
# No wrapped command: print nothing. The wrapper is then a pure tee, which is a valid way to run it
# on a machine that has no status line of its own.
[ "$#" -eq 0 ] && exit 0
printf '%s' "$input" | "$@"
