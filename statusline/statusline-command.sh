#!/usr/bin/env bash
# Claude Code status line: cwd  model  context%  [session%  weekly%]  [git-branch]
# Requires: jq  (brew install jq)

input=$(cat)

# Current directory, with $HOME shortened to ~
cwd=$(echo "$input" | jq -r '.cwd // .workspace.current_dir // ""')
short_cwd="${cwd/#$HOME/~}"

# Model display name (strip "Claude " prefix for brevity)
model=$(echo "$input" | jq -r '.model.display_name // .model.id // ""')
model="${model#Claude }"

# Context window usage (null before the first API call)
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
if [ -n "$used_pct" ]; then
  ctx_part="$(printf '%.0f' "$used_pct")% ctx"
else
  ctx_part="ctx -"
fi

# Plan usage: share of the rolling session (5-hour) and weekly allowance spent, each with the time
# left until it resets — the numbers `/usage` shows as bars, and the ones that actually stop a
# session. Subscription sessions only, and only after the first API response; a session commonly
# reports one window and not the other, so each shows independently. One jq call for both — this
# runs on every render — and jq labels and joins them itself, because splitting two values out of
# one line in bash puts the wrong label on the figure the moment the absent window is the first one.
limits_part=$(echo "$input" | jq -r '
  def left(t): ((t - now) | floor) as $s
    | if   $s <= 0    then "now"
      elif $s < 60    then "<1m"
      elif $s < 3600  then "\(($s / 60) | floor)m"
      elif $s < 86400 then "\(($s / 3600) | floor)h\((($s % 3600) / 60) | floor)m"
      else                 "\(($s / 86400) | floor)d\((($s % 86400) / 3600) | floor)h" end;
  def show(w; name): w | select(. != null) | select(.used_percentage != null)
    | "\(.used_percentage | round)% \(name)"
      + (if .resets_at then " (\(left(.resets_at)))" else "" end);
  [ show(.rate_limits.five_hour; "session"), show(.rate_limits.seven_day; "weekly") ]
  | join(" ")')

# Git branch (skip optional locks to avoid hangs)
git_branch=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  git_branch=$(GIT_OPTIONAL_LOCKS=0 git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
               || GIT_OPTIONAL_LOCKS=0 git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
fi

parts=("$short_cwd" "$model" "$ctx_part")
[ -n "$limits_part" ] && parts+=("$limits_part")
[ -n "$git_branch" ] && parts+=("$git_branch")
printf '%s' "${parts[*]}"
