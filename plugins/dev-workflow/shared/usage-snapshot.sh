#!/usr/bin/env bash
# The Claude allowance figures, published where a run can read them.
#
#   write (status line):  statusLine.command = bash ~/.claude/usage-snapshot.sh <your original command>
#   read  (a run):        bash ~/.claude/usage-snapshot.sh --read [--mark NAME]
#
# Also tees the session's own cost.total_cost_usd, printed as `spend:` beside the total across sessions,
# so a run can tell its own share of a window's rise from what other sessions spent meanwhile.
# Also tees the session's own context_window.used_percentage, printed as `context: N% used` — the
# figure /pilot's context ladder reads at every task boundary. Context is per session, so it is never
# aggregated across siblings. Each window line also carries `resets_at=<epoch>`, the key /pilot's
# weekly-budget ledger joins on (a formatted time would change with locale and break the join).
#
# Claude Code publishes the live subscription figures — percent of the 5-hour window used, percent of
# the week used, and when each resets — to exactly one place: the status-line command's stdin. No hook
# receives them and no endpoint serves them, so a run that wants to know how much allowance is left
# has to be handed them from here.
#
# WHY ONE FILE PER SESSION, AND WHY max() — the first version wrote one shared file and was worse than
# no signal at all. Measured on one machine: 12 concurrent sessions, each re-rendering its status line
# every 60 s, every render overwriting the same path. The file flipped between 46% and 7% for the same
# window four seconds apart, and published a null window under a `written_at` zero seconds old. A real
# mission then reversed its own correct decision to stop on the next (stale) read, ran into the wall,
# and had a subagent killed mid-write against production. Two properties fix it for good:
#
#   * per-session path — a session only ever overwrites its own figures, so no reading is ever a blend
#     of two sessions, and a second account's sessions cannot overwrite this one's
#   * max() within a window — usage only ever RISES inside a window, so the highest figure any session
#     has seen is the closest one to the truth and a stale session's lower number is discarded by
#     arithmetic rather than by trusting a clock. `written_at` stamps the write, never the measurement,
#     and is therefore only used to prune: 10 live sessions were once measured writing within ONE
#     second of each other while carrying figures hours apart (7%, 24% and 54% of the same window)
#
# The reader anchors on THIS session's own file ($CLAUDE_CODE_SESSION_ID) and aggregates only siblings
# whose `resets_at` matches it. A window boundary is per-account, so that one join keeps a second
# account's sessions out with no account field to read.
#
# Claude Code reports a window only while it is relevant to the account, so one session usually carries
# the 5-hour figure OR the 7-day figure and not both. For a window this session lacks, the reader
# borrows the siblings' figure and labels it — but only when they all name ONE live boundary; two
# boundaries mean two accounts that cannot be told apart, and that is `unknown`. Borrowing matters
# because the alternative hides an exhausted weekly window, which is the one fact a mission most needs.
#
# Three properties the writer must have, because a wrong figure here is worse than no figure:
#   * partial writes are omissions, never nulls — a window this session cannot see is left out, so it
#     never asserts absence over another session's real reading
#   * atomic — temp file + mv, so a reader never catches a half-written file
#   * harmless — no jq, no writable home, malformed input, absent rate_limits: do nothing, pass
#     through. The status line must never break because of this wrapper
#
# `rate_limits` is absent for API-key auth, and on a subscription until the session's first API
# response, so a fresh session legitimately has no file. Every reader treats that as `unknown` and
# proceeds — never as "there is room" and never as a reason to stop.
#
# Pair the write mode with `"refreshInterval": 60`. The status line is event-driven and goes quiet
# exactly while a mission runs, because the main session sits still waiting on background subagents.
#
# Copied VERBATIM from the plugin's shared/usage-snapshot.sh — fix it there, never the copy.

DIR="${CLAUDE_USAGE_DIR:-$HOME/.claude/usage}"
MAX_AGE_SECS=86400   # prune a session's file after a day; also the bound on what --read will consider

# ============================== read mode =====================================================
if [ "$1" = "--read" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "allowance: unknown — no python3 to aggregate the snapshots"; exit 0
  fi
  MARK=""; [ "$2" = "--mark" ] && MARK="$3"
  DIR="$DIR" MAX_AGE_SECS="$MAX_AGE_SECS" SID="${CLAUDE_CODE_SESSION_ID:-}" MARK="$MARK" python3 - <<'PY'
import glob, json, os, re, time

d = os.environ["DIR"]
max_age = int(os.environ["MAX_AGE_SECS"])
sid = os.environ.get("SID") or ""
now = time.time()

files = {}
for p in glob.glob(os.path.join(d, "*.json")):
    try:
        with open(p) as fh:
            row = json.load(fh)
    except Exception:
        continue
    if now - float(row.get("written_at", 0)) > max_age:
        try:
            os.remove(p)          # prune: a session that stopped a day ago has nothing to say
        except OSError:
            pass
        continue
    files[os.path.splitext(os.path.basename(p))[0]] = row

own = files.get(sid)
if own is None:
    # No file for this session: either the status-line wrapper is not wired, or this session has not
    # had an API response yet. Both are unknown, and unknown proceeds.
    extra = f" ({len(files)} other session(s) have one)" if files else ""
    print(f"allowance: unknown — no snapshot for this session{extra}")
    raise SystemExit(0)

lines = []
for kind, label in (("five_hour", "5-hour"), ("seven_day", "7-day")):
    mine = own.get(kind)
    # Claude Code reports a window only while it is relevant to the account, so a session commonly
    # carries ONE window and not the other (measured: 10 live sessions, every one with either the
    # 5-hour or the 7-day figure, never both). Falling straight to `unknown` would then hide an
    # exhausted weekly window — the single fact a mission most needs — so borrow from the siblings
    # when they are unambiguous about which window they mean.
    boundaries = {r[kind]["resets_at"] for r in files.values()
                  if isinstance(r.get(kind), dict) and r[kind].get("resets_at") is not None}
    borrowed = False
    if not mine or mine.get("resets_at") is None:
        live = {b for b in boundaries if b > now}
        if len(live) != 1:
            why = ("this session reports no window and no other does either"
                   if not live else
                   f"{len(live)} different windows across sessions — two accounts cannot be told apart")
            lines.append(f"{label}: unknown — {why}")
            continue
        resets, borrowed = live.pop(), True
    else:
        resets = int(mine["resets_at"])
        if resets <= now:
            # The boundary has passed, so every figure carrying it describes a window that no longer
            # exists. A dead number is not a low number.
            lines.append(f"{label}: unknown — window reset since it was measured")
            continue
    # Usage only rises inside a window, so the highest figure any session holding this boundary has
    # seen is the closest one to the truth. This is the whole reason `written_at` is never consulted
    # here: 10 sessions once wrote within one second of each other carrying figures hours apart.
    agree = [r[kind]["used_percentage"] for r in files.values()
             if isinstance(r.get(kind), dict) and r[kind].get("resets_at") == resets
             and isinstance(r[kind].get("used_percentage"), (int, float))]
    if not agree:
        lines.append(f"{label}: unknown — no usable figure for this window")
        continue
    used = max(agree)
    hrs = (resets - now) / 3600.0
    lines.append(
        f"{label}: {used:.0f}% used, {100 - used:.0f}% left, resets "
        f"{time.strftime('%H:%M %d-%b', time.localtime(resets))} (in {hrs:.1f}h) · resets_at={resets}"
        f" · {len(agree)} session(s) on this window"
        + (" · borrowed: this session reports no such window" if borrowed else "")
    )
# Spend: the windows are the whole account's, so their rise across a task is every session's work, not
# the task's. Each session's own running cost (the status line's cost.total_cost_usd, subagents included)
# splits it. Only sessions on this session's own boundary are summed — the join that keeps a second
# account out of the figures above.
key = "seven_day" if isinstance(own.get("seven_day"), dict) else "five_hour"
mark_at = (own.get(key) or {}).get("resets_at")
costs = {r.get("sid"): r["cost_usd"] for r in files.values() if isinstance(r.get("cost_usd"), (int, float))
         and (mark_at is None or (r.get(key) or {}).get("resets_at") in (None, mark_at))}
if sid in costs:
    lines.append(f"spend: ${costs[sid]:.2f} this session · ${sum(costs.values()):.2f} across {len(costs)} session(s)")
else:
    lines.append("spend: unknown")
# --mark NAME: this session's share of the spend since its last read with the same NAME, then the mark
# moves here. Kept on disk, so a compaction between two reads loses nothing. Only sessions present in
# both reads count: one that appears with spend already on it, or disappears, would otherwise swing the
# share toward 0 or past 1, and a share near 0 never stops a budget.
mark = os.environ.get("MARK") or ""
if mark and re.fullmatch(r"[A-Za-z0-9_-]+", mark) and sid and re.fullmatch(r"[A-Za-z0-9_-]+", sid):
    mdir = os.path.join(d, "marks")
    os.makedirs(mdir, exist_ok=True)
    for p in glob.glob(os.path.join(mdir, "*.json")):
        try:
            if now - os.path.getmtime(p) > max_age:
                os.remove(p)
        except OSError:
            pass
    path = os.path.join(mdir, f"{sid}-{mark}.json")
    try:
        with open(path) as fh:
            prev = json.load(fh)
    except Exception:
        prev = None
    if prev is None:
        lines.append(f"share: unknown — first read with --mark {mark}")
    elif sid not in costs or sid not in prev or costs[sid] < prev[sid]:
        lines.append("share: unknown — this session's own spend is missing or fell")
    else:
        both = [k for k in costs if k in prev and costs[k] >= prev[k]]
        mine, total = costs[sid] - prev[sid], sum(costs[k] - prev[k] for k in both)
        if total <= 0:
            lines.append("share: unknown — no spend since the last mark")
        else:
            lines.append(f"share: {min(1.0, mine / total) * 100:.0f}% of the spend since the last mark — "
                         f"${mine:.2f} of ${total:.2f} across {len(both)} session(s) in both reads")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(costs, fh)
    os.replace(tmp, path)
# Context is per session, so no sibling aggregation: this session's own last figure, or unknown.
ctx = own.get("context") if isinstance(own.get("context"), dict) else None
if ctx and isinstance(ctx.get("used_percentage"), (int, float)):
    lines.append(f"context: {ctx['used_percentage']:.0f}% used (this session)")
else:
    lines.append("context: unknown")
print("\n".join(lines))
PY
  exit 0
fi

# ============================== write mode (default) ==========================================
input=$(cat)

if command -v jq >/dev/null 2>&1; then
  # The session id in the payload is authoritative for the writing session; fall back to the env var.
  snap=$(printf '%s' "$input" | jq -c --arg envsid "${CLAUDE_CODE_SESSION_ID:-}" '
    (.rate_limits // {}) as $r
    | (.session_id // $envsid) as $sid
    | select(($sid | length) > 0)
    | select((($r.five_hour // $r.seven_day) != null) or (.context_window.used_percentage != null))
    | {sid: $sid, written_at: (now | floor)}
      + (if .context_window.used_percentage != null then {context: {used_percentage: .context_window.used_percentage}} else {} end)
      + (if (.cost.total_cost_usd | type) == "number" then {cost_usd: .cost.total_cost_usd} else {} end)
      + (if $r.five_hour then {five_hour: {used_percentage: $r.five_hour.used_percentage, resets_at: $r.five_hour.resets_at}} else {} end)
      + (if $r.seven_day then {seven_day: {used_percentage: $r.seven_day.used_percentage, resets_at: $r.seven_day.resets_at}} else {} end)
    ' 2>/dev/null)

  # Empty output means no rate_limits or no session id — keep whatever is already on disk.
  if [ -n "$snap" ]; then
    sid=$(printf '%s' "$snap" | jq -r '.sid' 2>/dev/null)
    case "$sid" in
      ''|*/*|.|..) sid='' ;;   # never let a payload value escape the directory
    esac
    if [ -n "$sid" ] && mkdir -p "$DIR" 2>/dev/null; then
      target="$DIR/$sid.json"
      if tmp=$(mktemp "$target.XXXXXX" 2>/dev/null); then
        if printf '%s\n' "$snap" >"$tmp" 2>/dev/null; then
          mv -f "$tmp" "$target" 2>/dev/null || rm -f "$tmp" 2>/dev/null
        else
          rm -f "$tmp" 2>/dev/null
        fi
      fi
    fi
  fi
fi

# ---- hand the same stdin to the original status-line command ----------------------------------
# No wrapped command: print nothing. The wrapper is then a pure tee, which is a valid way to run it
# on a machine that has no status line of its own.
[ "$#" -eq 0 ] && exit 0
printf '%s' "$input" | "$@"
