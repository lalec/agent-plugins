#!/usr/bin/env bash
# Claude Code status line: cwd  model  context%  [git-branch]
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

# Git branch (skip optional locks to avoid hangs)
git_branch=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  git_branch=$(GIT_OPTIONAL_LOCKS=0 git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
               || GIT_OPTIONAL_LOCKS=0 git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
fi

parts=("$short_cwd" "$model" "$ctx_part")
[ -n "$git_branch" ] && parts+=("$git_branch")
printf '%s' "${parts[*]}"
