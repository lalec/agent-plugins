#!/usr/bin/env bash
# Run the dev-workflow upgrade in every other live Claude Code session that has an install.
# macOS + iTerm2 only: it types into each session's own tab, exactly as a person would, because
# /compact, /reload-plugins and /exit are built-in commands no tool and no session message can run.
#
# Usage: fanout.sh [--restart] [--session <id>]... [--dry-run]
#   first, once for the machine: update dev-workflow and every plugin its manifest depends on
#   (default)  per session: /compact, /reload-plugins, /dev-workflow:upgrade --yes
#   --restart  also claude update once, then per session: /compact, /exit, relaunch with the same
#              flags plus --resume <id> '/dev-workflow:upgrade --yes'. A session that owns an
#              open /pilot run is never exited (its in-flight agents would die) — it gets the default.
#   --session  limit to these session ids
#   --dry-run  list what would happen, type nothing
set -euo pipefail

RESTART=0 DRY=0 ONLY=()
while [ $# -gt 0 ]; do
  case $1 in
    --restart) RESTART=1 ;;
    --dry-run) DRY=1 ;;
    --session) ONLY+=("$2"); shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

SELF=${CLAUDE_CODE_SESSION_ID:-}
UPGRADE='/dev-workflow:upgrade --yes'
IDLE_TIMEOUT=${FANOUT_IDLE_TIMEOUT:-3600}
LOG_DIR=${TMPDIR:-/tmp}/dev-workflow-fanout
mkdir -p "$LOG_DIR"; rm -f "$LOG_DIR"/*.log

[ "$(uname)" = Darwin ] && [ -d /Applications/iTerm.app ] || {
  echo "fanout needs macOS + iTerm2. In each session's tab, type: /compact, /reload-plugins, $UPGRADE" >&2
  exit 3
}

# pid<TAB>session id<TAB>cwd<TAB>owns-open-run(0|1) — live interactive sessions with an install, not this one
list_sessions() {
  python3 - "$SELF" "${ONLY[@]+"${ONLY[@]}"}" <<'PY'
import glob, json, os, sys
self_id, only = sys.argv[1], set(sys.argv[2:])
for f in glob.glob(os.path.expanduser("~/.claude/sessions/*.json")):
    try:
        d = json.load(open(f))
        os.kill(d["pid"], 0)
    except Exception:
        continue
    sid, cwd = d.get("sessionId", ""), d.get("cwd", "")
    if d.get("kind") != "interactive" or sid == self_id or (only and sid not in only):
        continue
    if not os.path.isfile(os.path.join(cwd, ".claude/skills/pilot/SKILL.md")):
        continue
    try:
        owns = open(os.path.join(cwd, ".claude/pilot/running")).read().splitlines()[1:2] == [sid]
    except Exception:
        owns = False
    print(f'{d["pid"]}\t{sid}\t{cwd}\t{int(owns)}')
PY
}

status() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' ~/.claude/sessions/"$1".json 2>/dev/null || echo gone; }

# Idle twice, 10 s apart: a Stop hook that continues the turn flips it back to busy in between.
wait_idle() {
  local pid=$1 waited=0
  while [ $waited -lt "$IDLE_TIMEOUT" ]; do
    if [ "$(status "$pid")" = idle ]; then
      sleep 10; waited=$((waited + 10))
      [ "$(status "$pid")" = idle ] && return 0
    fi
    sleep 5; waited=$((waited + 5))
  done
  return 1
}

type_into() { # tty text — the text plus Return, into the iTerm session on that tty
  osascript - "$1" "$2" <<'AS'
on run argv
  tell application "iTerm2"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if tty of s is (item 1 of argv) then
            tell s to write text (item 2 of argv)
            return "ok"
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return "no iTerm session on " & (item 1 of argv)
end run
AS
}

step() { # pid tty text — wait for idle, then type
  wait_idle "$1" || { echo "not idle after ${IDLE_TIMEOUT}s — stopped before: $3"; return 1; }
  [ "$(type_into "$2" "$3")" = ok ] || { echo "no iTerm tab on $2"; return 1; }
  echo "typed: $3"
  sleep 15 # let the command start before the next idle check
}

relaunch_cmd() { # pid sid — the session's own argv, any resume/continue dropped, then resume this id
  python3 - "$(ps -o args= -p "$1")" "$2" "$UPGRADE" <<'PY'
import shlex, sys
args, sid, prompt = shlex.split(sys.argv[1]), sys.argv[2], sys.argv[3]
out, skip = [], False
for a in args:
    if skip: skip = False; continue
    if a in ("-r", "--resume"): skip = True; continue
    if a in ("-c", "--continue") or a.startswith("--resume="): continue
    out.append(a)
print(shlex.join(out + ["--resume", sid, prompt]))
PY
}

one() { # pid sid cwd owns
  local pid=$1 sid=$2 cwd=$3 owns=$4 tty
  tty=/dev/$(ps -o tty= -p "$pid" | tr -d ' ')
  local mode=attach
  [ $RESTART = 1 ] && [ "$owns" = 0 ] && mode=restart
  echo "$(basename "$cwd") $sid $tty mode=$mode$([ "$owns" = 1 ] && echo ' (owns an open /pilot run)')"
  [ $DRY = 1 ] && return 0
  step "$pid" "$tty" /compact || return 1
  if [ $mode = attach ]; then
    step "$pid" "$tty" /reload-plugins || return 1
    step "$pid" "$tty" "$UPGRADE" || return 1
    return 0
  fi
  local cmd; cmd=$(relaunch_cmd "$pid" "$sid")
  step "$pid" "$tty" /exit || return 1
  for _ in $(seq 60); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
  kill -0 "$pid" 2>/dev/null && { echo "still running after /exit — not relaunched"; return 1; }
  [ "$(type_into "$tty" "cd $(printf %q "$cwd") && $cmd")" = ok ] || { echo "no iTerm tab on $tty"; return 1; }
  echo "relaunched: $cmd"
}

update_plugins() { # dev-workflow and its manifest dependencies, each from its own marketplace
  local manifest names
  manifest=$(cd "$(dirname "$0")/../../.." && pwd)/.claude-plugin/plugin.json
  names=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" ".join([d["name"]] + d.get("dependencies", [])))' "$manifest")
  claude plugin list --json | python3 -c 'import json,sys; w=set(sys.argv[1:]); [print(x["id"]) for x in json.load(sys.stdin) if x["id"].split("@")[0] in w]' $names |
    while read -r id; do
      claude plugin marketplace update "${id#*@}" >/dev/null 2>&1 || true
      claude plugin update "$id" 2>&1 | tail -1
    done
}

SESSIONS=$(list_sessions)
[ -n "$SESSIONS" ] || { echo "no other live session has a dev-workflow install"; exit 0; }
if [ $DRY = 0 ]; then
  update_plugins
  [ $RESTART = 1 ] && { claude update || echo "claude update failed — relaunching on the current version"; }
fi

while IFS=$'\t' read -r pid sid cwd owns; do
  log=$LOG_DIR/$sid.log
  if [ $DRY = 1 ]; then one "$pid" "$sid" "$cwd" "$owns"; else
    ( one "$pid" "$sid" "$cwd" "$owns" > "$log" 2>&1 && echo done >> "$log" || echo FAILED >> "$log" ) &
  fi
done <<< "$SESSIONS"
wait
[ $DRY = 1 ] || for f in "$LOG_DIR"/*.log; do echo "== $f"; cat "$f"; done
