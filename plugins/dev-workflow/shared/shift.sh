#!/usr/bin/env bash
# shift.sh — headless shifts for /pilot.
#
# Copied VERBATIM into a project at `.claude/pilot/shift.sh` by dev-workflow install — no
# substitution, so it stays byte-identical across projects. Fix the plugin, never the copy.
#
#   shift.sh run       [--max-tasks N] [--budget USD] [--dry-run]
#   shift.sh install   [--interval SECONDS] [--max-tasks N] [--budget USD] [--notify URL] [--dry-run]
#   shift.sh uninstall
#   shift.sh pause [<N>h|<N>m]                  hold shifts for a while (default 4h); a stop that ends by itself
#   shift.sh resume                             lift a pause now
#   shift.sh status
#   shift.sh parse <result.json> <exit-code>     what `run` would record from a saved result
#
# A shift is one fresh headless `claude -p "/pilot --max-tasks N"` — the standing mission — with
# the orchestrator on Opus, every subagent on Sonnet (pilot.md decides that, not this script), a
# dollar cap, and a one-minute question timeout so a gate nobody answers defaults instead of
# hanging. The timeout value is one of the CLI's enum strings ("60s" | "5m" | "10m" | "never") —
# the shipped schema drops anything else silently and the default is "never", i.e. wait forever. Everything the run concludes lands in the project's own stores (log, roadmap,
# custom-tests.yaml); this script keeps only a run marker, `state.json`, and the raw result.
#
# The usage window: Claude Code's auto-continue-at-limit is interactive-only, so when a shift is
# cut off by the subscription limit this script records `ended: limit` with the reset time the
# message named (else now + interval), and the next launch that is allowed to run RESUMES that
# session first — same flags again, since `--resume` restores none of them — before starting a
# fresh standing mission.
#
# launchd fires `run` every --interval seconds; `run` decides in a few milliseconds whether there
# is anything to do. Labels are single-instance, so the only concurrency this guards against is a
# person's own session in the same repo, via `.claude/pilot/running` (written by /pilot itself).

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
DIR="$ROOT/.claude/pilot"
STATE="$DIR/state.json"
RUNNING="$DIR/running"
LOG="$DIR/shifts.log"
LABEL="com.dev-workflow.$(basename "$ROOT").shift"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STALE_SECS=$((6 * 3600))

say() { printf 'shift: %s\n' "$*"; }
die() { printf 'shift: %s\n' "$*" >&2; exit 2; }
now_iso() { date -u +%FT%TZ; }

# ------------------------------------------------------------------------------ helpers

# Read one key from state.json (empty when absent). python3 is a workflow prerequisite already.
state_get() {
  [ -f "$STATE" ] || { echo ""; return; }
  python3 - "$STATE" "$1" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1])).get(sys.argv[2], "")
except Exception:
    v = ""
print("" if v is None else v)
PY
}

file_age_secs() { echo $(( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1") )); }

# Parse a saved `--output-format json` result plus the exit code into the fields state.json keeps.
# Prints `key=value` lines. Limit detection is the only judgment here and it is deliberately
# narrow: the documented messages ("You've hit your session limit", "…weekly limit", "…Opus
# limit") plus the older "usage limit reached". A reset time is taken only in the `3pm` / `3:30 pm`
# shape; anything else falls back to now + interval, capped, so a misparse costs one extra wait
# and never a week of silence.
parse_result() {
  python3 - "$1" "$2" "${3:-1800}" <<'PY'
import json, re, sys, time
from datetime import datetime, timedelta

path, code, interval = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
raw = open(path, errors="replace").read() if path != "-" else ""
data = {}
try:
    data = json.loads(raw)
    if isinstance(data, list):  # stream-json fallback: last object wins
        data = next((d for d in reversed(data) if isinstance(d, dict) and "result" in d), {})
except Exception:
    data = {}
result = str(data.get("result", "")) if data else raw
text = result + "\n" + raw[-2000:]

limit = re.search(r"hit your (session|weekly|opus|sonnet)?\s*limit|usage limit reached", text, re.I)
ended = "ok" if code == 0 and not limit else ("limit" if limit else "error")
kind = (limit.group(1) or "session").lower() if limit else ""

next_allowed = ""
if limit:
    m = re.search(r"reset\w*\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text, re.I)
    now = datetime.now()
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        h = (h % 12) + (12 if ap == "pm" else 0)
        t = now.replace(hour=h, minute=mi, second=0, microsecond=0) + timedelta(minutes=2)
        if t < now:
            # A named time already behind us: the window is five hours, so a reset up to
            # five hours ago has happened (allowed now); older means it is tomorrow's.
            t = now if now - t <= timedelta(hours=5) else t + timedelta(days=1)
        t = min(t, now + timedelta(hours=5))
    else:
        t = now + timedelta(seconds=interval)
    if kind == "weekly":
        t = now + timedelta(hours=24)
    next_allowed = t.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

denials = [d for d in (data.get("permission_denials") or []) if d.get("tool_name") != "AskUserQuestion"]
verdict = ""
for line in result.splitlines():
    bare = line.replace("*", "").strip("# ").strip()
    # The Verdict *line* ("**Verdict:** 2 done, 1 parked"), not the "## Verdict" heading above it.
    if bare.lower().startswith("verdict") and len(bare) > len("verdict:") + 1:
        verdict = bare[:200]
        break

out = {
    "ended": ended,
    "limit_kind": kind,
    "next_allowed": next_allowed,
    "session_id": data.get("session_id", ""),
    "total_cost_usd": data.get("total_cost_usd", ""),
    "subtype": data.get("subtype", ""),
    "denials": len(denials),
    "verdict": verdict,
}
for k, v in out.items():
    print(f"{k}={v}")
PY
}

write_state() {  # write_state key=value ... (merges over the existing file; an argument may carry several key=value lines)
  python3 - "$STATE" "$@" <<'PY'
import json, os, sys
path = sys.argv[1]
# One quoted argument can hold many lines (parse_result's output) — values carry spaces, so
# they are never word-split by the shell; stdin is taken by the script itself.
pairs = [ln for arg in sys.argv[2:] for ln in arg.split("\n") if "=" in ln]
state = {}
if os.path.exists(path):
    try:
        state = json.load(open(path))
    except Exception:
        state = {}
for p in pairs:
    k, _, v = p.partition("=")
    if v.replace(".", "", 1).isdigit():
        v = float(v) if "." in v else int(v)
    state[k] = v
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(state, open(path, "w"), indent=2)
PY
}

set_flags() {  # the full flag set, passed on BOTH the resume and the fresh invocation
  FLAGS=(--model opus --output-format json --permission-mode bypassPermissions
    --max-budget-usd "$BUDGET" --settings '{"askUserQuestionTimeout":"60s"}')
}

# ---------------------------------------------------------------------------------- run

cmd_run() {
  MAX_TASKS=3; BUDGET=15; DRY=0; INTERVAL=1800
  while [ $# -gt 0 ]; do
    case "$1" in
      --max-tasks) MAX_TASKS=$2; shift 2 ;;
      --budget) BUDGET=$2; shift 2 ;;
      --interval) INTERVAL=$2; shift 2 ;;
      --dry-run) DRY=1; shift ;;
      *) die "unknown run option $1" ;;
    esac
  done
  for tool in claude python3 git; do
    command -v "$tool" >/dev/null || die "preflight: $tool not on PATH ($PATH)"
  done
  mkdir -p "$DIR"

  # Skip conditions, cheapest first. Each is a line in shifts.log so a quiet day is legible.
  # A run the usage limit cut off leaves its marker behind; that marker belongs to the session
  # this launch is about to resume, so it must not read as "someone else is active".
  resumable=0
  [ "$(state_get ended)" = "limit" ] && [ -n "$(state_get session_id)" ] && resumable=1
  if [ -f "$RUNNING" ] && [ "$resumable" != 1 ]; then
    age=$(file_age_secs "$RUNNING")
    if [ "$age" -lt "$STALE_SECS" ]; then
      say "skip: a run is active since $(cat "$RUNNING") (${age}s)"; return 0
    fi
    say "stale run marker (${age}s) — removing"; rm -f "$RUNNING"
  fi
  # The pilot dir is gitignored on a correct install; excluding it here as well means a
  # missing ignore line can never make a shift skip itself on its own state file.
  if [ -n "$(git -C "$ROOT" status --porcelain -- . ':!.claude/pilot' 2>/dev/null)" ]; then
    say "skip: working tree is dirty — a person's work is in flight; /tidy it or commit it"
    return 0
  fi
  next=$(state_get next_allowed)
  if [ -n "$next" ]; then
    next_epoch=$(python3 -c 'import sys;from datetime import datetime;print(int(datetime.fromisoformat(sys.argv[1]).timestamp()))' "$next" 2>/dev/null || echo 0)
    if [ "$next_epoch" -gt "$(date +%s)" ]; then
      say "skip: $([ "$(state_get paused_by)" = user ] && echo paused || echo "usage limit") — next allowed $next"; return 0
    fi
  fi

  ts=$(date -u +%Y%m%dT%H%M%SZ)
  set_flags   # macOS ships bash 3.2: plain arrays only, no mapfile

  # Resume first: a run the limit interrupted holds a mission plan nobody else has.
  if [ "$(state_get ended)" = "limit" ] && [ -n "$(state_get session_id)" ]; then
    sid=$(state_get session_id)
    prompt="The usage limit interrupted the previous run. Resume from the current task using the mission state in context: finish the task in flight, continue per /pilot Step 2, and close out per /pilot Step 3."
    say "resume: session $sid"
    if [ "$DRY" = 1 ]; then
      printf '  claude -p --resume %s %s %q\n' "$sid" "${FLAGS[*]}" "$prompt"
    else
      run_once "$ts-resume" claude -p --resume "$sid" "${FLAGS[@]}" "$prompt" || true
      [ "$(state_get ended)" = "limit" ] && { say "limit hit again during resume — waiting"; return 0; }
      # The resumed run's close-out clears its own marker; if it ended without reaching that
      # step, the marker is stale by definition and must not block the fresh run below.
      rm -f "$RUNNING"
    fi
  fi

  prompt="/pilot --max-tasks $MAX_TASKS"
  say "run: $prompt (budget \$$BUDGET)"
  if [ "$DRY" = 1 ]; then
    printf '  claude -p %q %s\n' "$prompt" "${FLAGS[*]}"
    return 0
  fi
  run_once "$ts" claude -p "$prompt" "${FLAGS[@]}"
}

# run_once <tag> <command...> — execute, save the raw result, parse it into state.json.
run_once() {
  local tag=$1; shift
  local out="$DIR/$tag.json" err="$DIR/$tag.stderr"
  local code=0
  write_state "started=$(now_iso)" "status=running"
  set +e
  "$@" >"$out" 2>"$err"
  code=$?
  set -e
  # The limit message can arrive on stderr; fold it in so the parser sees it.
  [ -s "$err" ] && cat "$err" >>"$out.stderr" && cat "$err" >>"$out"
  local kv; kv=$(parse_result "$out" "$code" "$INTERVAL")
  local ended; ended=$(printf '%s\n' "$kv" | sed -n 's/^ended=//p')
  write_state "$kv" "finished=$(now_iso)" "status=$([ "$ended" = ok ] && echo idle || echo degraded)" "exit=$code"
  [ "$ended" = "limit" ] && write_state "status=idle"   # a limit inside its window is not degraded
  # Keep the readable report next to the raw JSON.
  python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("result",""))' "$out" >"$DIR/$tag.log" 2>/dev/null || true
  printf '%s %s exit=%s %s\n' "$(now_iso)" "$tag" "$code" "$(printf '%s\n' "$kv" | tr '\n' ' ')" >>"$LOG"
  say "$tag: $(printf '%s\n' "$kv" | tr '\n' ' ')"
  return "$code"
}

# ------------------------------------------------------------------------ install / etc.

cmd_install() {
  INTERVAL=1800; MAX_TASKS=3; BUDGET=15; NOTIFY=""; DRY=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --interval) INTERVAL=$2; shift 2 ;;
      --max-tasks) MAX_TASKS=$2; shift 2 ;;
      --budget) BUDGET=$2; shift 2 ;;
      --notify) NOTIFY=$2; shift 2 ;;
      --dry-run) DRY=1; shift ;;
      *) die "unknown install option $1" ;;
    esac
  done
  [ "$(uname)" = "Darwin" ] || die "install renders a launchd plist and is macOS-only; run \`shift.sh run\` from cron elsewhere"
  mkdir -p "$DIR"
  local plist
  plist=$(cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$DIR/shift.sh</string><string>run</string>
    <string>--max-tasks</string><string>$MAX_TASKS</string>
    <string>--budget</string><string>$BUDGET</string>
    <string>--interval</string><string>$INTERVAL</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><false/>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$PATH</string>
    <key>HOME</key><string>$HOME</string>$( [ -n "$NOTIFY" ] && printf '\n    <key>PILOT_NOTIFY_URL</key><string>%s</string>' "$NOTIFY" )
  </dict>
  <key>StandardOutPath</key><string>$DIR/launchd.log</string>
  <key>StandardErrorPath</key><string>$DIR/launchd.log</string>
</dict></plist>
EOF
)
  if [ "$DRY" = 1 ]; then printf '%s\n' "$plist"; return 0; fi
  mkdir -p "$(dirname "$PLIST")"
  printf '%s\n' "$plist" >"$PLIST"
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  say "installed $LABEL — every ${INTERVAL}s, up to $MAX_TASKS tasks, \$$BUDGET cap$( [ -n "$NOTIFY" ] && echo ', notifying')"
  say "log: $DIR/shifts.log · state: $STATE · uninstall: $DIR/shift.sh uninstall"
}

cmd_uninstall() {
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  say "removed $LABEL"
}

# A pause is a stop with an end date. It reuses `next_allowed` — the same field a usage limit
# sets — so `run` needs no second rule, and a person who pauses and forgets is not a person
# who has to remember: the shifts come back on their own.
cmd_pause() {
  local spec=${1:-4h} secs
  case "$spec" in
    *h) secs=$(( ${spec%h} * 3600 )) ;;
    *m) secs=$(( ${spec%m} * 60 )) ;;
    *) die "pause takes <N>h or <N>m" ;;
  esac
  mkdir -p "$DIR"
  local until_iso; until_iso=$(python3 -c 'import sys;from datetime import datetime,timedelta;print((datetime.now().astimezone()+timedelta(seconds=int(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%S%z"))' "$secs")
  write_state "next_allowed=$until_iso" "paused_by=user"
  say "paused until $until_iso — shifts resume on their own after that; \`shift.sh resume\` lifts it now"
}

cmd_resume() {
  [ -f "$STATE" ] || { say "nothing to resume"; return 0; }
  write_state "next_allowed=" "paused_by="
  say "resumed — the next launchd tick runs"
}

cmd_status() {
  if [ -f "$PLIST" ]; then
    say "scheduled: $LABEL ($(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | sed -n 's/^\s*state = //p' | head -1))"
  else
    say "not scheduled (no $PLIST)"
  fi
  if [ -f "$RUNNING" ]; then say "running since $(cat "$RUNNING")"; else say "no run in flight"; fi
  [ "$(state_get paused_by)" = "user" ] && say "paused until $(state_get next_allowed)"
  if [ -f "$STATE" ]; then python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])),indent=2))' "$STATE"; else say "no state.json yet"; fi
  [ -f "$LOG" ] && { say "last shifts:"; tail -5 "$LOG"; }
  return 0
}

# ------------------------------------------------------------------------------------ cli

case "${1:-}" in
  run) shift; cmd_run "$@" ;;
  install) shift; cmd_install "$@" ;;
  uninstall) cmd_uninstall ;;
  pause) shift; cmd_pause "$@" ;;
  resume) cmd_resume ;;
  status) cmd_status ;;
  parse) [ $# -ge 3 ] || die "parse <result.json> <exit-code>"; parse_result "$2" "$3" "${4:-1800}" ;;
  ""|-h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command ${1} — run, install, uninstall, pause, resume, status, parse" ;;
esac
