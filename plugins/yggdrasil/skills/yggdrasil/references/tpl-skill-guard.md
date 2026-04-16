# Hook Templates

Replace these placeholders before writing the files:
- `<PROJECT_DIR_VAR>` → `$CLAUDE_PROJECT_DIR` (Claude Code) or `$GEMINI_PROJECT_DIR` (Gemini CLI)
- `<CONFIG_DIR_PREFIX>` → `^\.claude/` (Claude Code) or `^\.gemini/` (Gemini CLI)
- `<CONFIG_DIR>` → `.claude` (Claude Code) or `.gemini` (Gemini CLI)
- `<PREFIX>` → the chosen skill/agent prefix
- `<GOVERNED_ROOTS>` → ERE alternation of **actual top-level source/asset directories**, e.g. `^(src/|lambda/|infra/|public/)`. Must be directory prefixes — **never extension globs** like `.*\.(html|css|js)$`, which match files outside the project dir (e.g. `/tmp/`) and defeat the guard. Root-level files (e.g. `index.html`) are owned via PATH_MAP entries, not GOVERNED_ROOTS.
- `<PATH_MAP_ENTRIES>` → generated entries from § How to generate governed-paths.conf
- `<LINT_CMD>` → project lint command (e.g. `pnpm exec biome check .` or `npm run lint`)
- `<TYPECHECK_CMD>` → project typecheck command (e.g. `pnpm exec tsc --noEmit` or `npm run typecheck`)

---

## § governed-paths.conf

The single source of truth for path→skill ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source this file. **Never put path patterns directly in the hook scripts.**

```bash
# governed-paths.conf
# Single source of truth for path→skill ownership.
# Sourced by skill-guard.sh and path-coverage-check.sh — edit here only.
#
# PATH_MAP format: 'PATTERN:SKILL'
#   SKILL=EXEMPT  — always allowed, skip guard (e.g. project-log.md written by <PREFIX>-log)
#   SKILL=OPEN    — inside <CONFIG_DIR>/ but no ownership guard needed
#   SKILL=<name>  — the skill that must be loaded before editing this path
#
# GOVERNED_ROOTS: ERE alternation of top-level roots that must be fully covered.
# path-coverage-check.sh blocks Write to these roots if no PATH_MAP entry matches.

GOVERNED_ROOTS='<GOVERNED_ROOTS>'

PATH_MAP=(
  '^docs/roadmap\.md$:EXEMPT'
  '^docs/project-log\.md$:EXEMPT'
  '<CONFIG_DIR_PREFIX>skills/:tosk-skill'
  '<CONFIG_DIR_PREFIX>hooks/|<CONFIG_DIR_PREFIX>agents/:<PREFIX>-skill'
  '^CLAUDE\.md$|^GEMINI\.md$:<PREFIX>-skill'
  '<CONFIG_DIR_PREFIX>:OPEN'
<PATH_MAP_ENTRIES>
  '^README\.md$|^docs/:<PREFIX>-docs'
)
```

---

## § How to generate governed-paths.conf

For each confirmed skill→path mapping, add one `'PATTERN:SKILL'` entry to `PATH_MAP`. More-specific patterns must come before catch-alls. The first matching entry wins.

**Example** (for a project with prefix `myapp`, backend=`lambda/`, frontend=`src/`, deploy=`infra/`):
```bash
PATH_MAP=(
  '^docs/project-log\.md$:EXEMPT'
  '^\.claude/skills/:myapp-skill'
  '^\.claude/hooks/|^\.claude/agents/:myapp-skill'
  '^CLAUDE\.md$:myapp-skill'
  '^\.claude/:OPEN'
  '^lambda/|^src/lib/api\.ts$:myapp-backend'
  '^src/|^astro\.config\.|^tsconfig\.json$:myapp-frontend'
  '^infra/|^\.github/|^package\.json$:myapp-deploy'
  '^README\.md$|^docs/:myapp-docs'
)
```

Rules:
- `docs/project-log.md` is always `EXEMPT` (written by `<PREFIX>-log` without skill loading)
- `<CONFIG_DIR>/skills/`, `<CONFIG_DIR>/hooks/`, `<CONFIG_DIR>/agents/`, and `CLAUDE.md`/`GEMINI.md` are always owned by `<PREFIX>-skill`
- The rest of `<CONFIG_DIR>/` is `OPEN` (no guard needed for other config)
- `README.md` and `docs/` are always owned by `<PREFIX>-docs`
- Domain skill entries go in between, ordered more-specific first

---

## § skill-guard.sh

Blocks Edit/Write (Claude Code) and replace/write_file (Gemini CLI) tool calls to owned paths if the owning skill hasn't been loaded. Sources `governed-paths.conf` — no path patterns in this file.

Platform detection: Gemini sets `$GEMINI_PROJECT_DIR`; Claude Code sets `$CLAUDE_PROJECT_DIR`. Gemini requires valid JSON to stdout and exit code 2 to block.

```bash
#!/bin/bash
INPUT=$(cat) || exit 0
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

# Strip project dir prefix from absolute paths
if [ -n "$GEMINI_PROJECT_DIR" ]; then
  FILE="${FILE#"$GEMINI_PROJECT_DIR"/}"
else
  FILE="${FILE#"$CLAUDE_PROJECT_DIR"/}"
fi
FILE="${FILE#/}"

source "$(dirname "$0")/governed-paths.conf"

SKILL=""
for entry in "${PATH_MAP[@]}"; do
  pattern="${entry%%:*}"
  owner="${entry##*:}"
  if echo "$FILE" | grep -qE "$pattern"; then
    [ "$owner" = "EXEMPT" ] && exit 0
    [ "$owner" = "OPEN" ]   && exit 0
    SKILL="$owner"
    break
  fi
done
[ -z "$SKILL" ] && exit 0

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0  # fail-open if no session ID

MARKER="/tmp/tosk-skills-${SESSION_ID}"
if [ ! -f "$MARKER" ] || ! grep -qF "$SKILL" "$MARKER"; then
  MSG="Skill gate: '${FILE##*/}' is owned by ${SKILL} — invoke it first (skill=\"${SKILL}\"), then retry."
  echo "$MSG" >&2
  if [ -n "$GEMINI_PROJECT_DIR" ]; then
    # Idiomatic Gemini block: exit 0 + {"decision":"deny",...} to stdout
    printf '{"decision":"deny","reason":"%s"}' "$MSG"
    exit 0
  fi
  exit 2
fi
exit 0
```

---

## § path-coverage-check.sh

Blocks Write/write_file tool calls to files in governed roots that aren't covered by any PATH_MAP entry. Sources `governed-paths.conf` — no path patterns in this file.

```bash
#!/bin/bash
# PreToolUse Write hook — blocks new files in governed roots not covered by any PATH_MAP entry.

INPUT=$(cat) || exit 0
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

if [ -n "$GEMINI_PROJECT_DIR" ]; then
  FILE="${FILE#"$GEMINI_PROJECT_DIR"/}"
else
  FILE="${FILE#"$CLAUDE_PROJECT_DIR"/}"
fi
FILE="${FILE#/}"

source "$(dirname "$0")/governed-paths.conf"

# Only check files inside a governed root
echo "$FILE" | grep -qE "$GOVERNED_ROOTS" || exit 0

# If any PATH_MAP entry matches, the path is covered — let skill-guard.sh handle ownership
for entry in "${PATH_MAP[@]}"; do
  pattern="${entry%%:*}"
  echo "$FILE" | grep -qE "$pattern" && exit 0
done

# In a governed root but no pattern matches — uncovered path
MSG="Path coverage gap: '${FILE}' is in a governed root but no skill owns it — invoke <PREFIX>-skill first to register the path, then retry."
echo "$MSG" >&2
if [ -n "$GEMINI_PROJECT_DIR" ]; then
  printf '{"decision":"deny","reason":"%s"}' "$MSG"
  exit 0
fi
exit 2
```

---

## § dependency-guard.sh

Blocks `pnpm add`, `npm install`, `yarn add`, and `pip install` commands unless `<PREFIX>-skill` has been loaded. Forces the agent to assess whether a new package requires a reference file before installing.

Gemini CLI note: tool input field for shell commands is `command` in `run_shell_command` — same field name as Claude Code's Bash tool.

```bash
#!/bin/bash
# PreToolUse Bash/run_shell_command hook — blocks dependency installs without <PREFIX>-skill loaded.

INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# Check if command installs dependencies
echo "$CMD" | grep -qE "(pnpm add|npm install|yarn add|pip install)" || exit 0

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0  # fail-open if no session ID

MARKER="/tmp/tosk-skills-${SESSION_ID}"
if [ ! -f "$MARKER" ] || ! grep -qF "<PREFIX>-skill" "$MARKER"; then
  MSG="Dependency gate: '${CMD}' installs a new package — invoke <PREFIX>-skill first (skill=\"<PREFIX>-skill\") to assess whether new packages need reference files, then retry."
  echo "$MSG" >&2
  if [ -n "$GEMINI_PROJECT_DIR" ]; then
    printf '{"decision":"deny","reason":"%s"}' "$MSG"
    exit 0
  fi
  exit 2
fi
exit 0
```

---

## § package-edit-guard.sh

Blocks direct dependency additions to `package.json` via the Edit/replace tool without `<PREFIX>-skill` loaded. Closes the bypass path where agents edit `package.json` directly instead of running `pnpm add`.

Gemini CLI note: `replace` tool uses `old_string`/`new_string` input fields — same as Claude Code's Edit tool.

```bash
#!/bin/bash
# PreToolUse Edit/replace hook — blocks direct dependency additions to package.json without <PREFIX>-skill loaded.

INPUT=$(cat) || exit 0
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

# Only fire on package.json
echo "$FILE" | grep -qE "(^|/)package\.json$" || exit 0

# Check if new packages are being added to dependencies or devDependencies
OLD=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null)
NEW=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null)

# Extract package entries from both strings and find additions
OLD_PKGS=$(echo "$OLD" | grep -oE '"[a-zA-Z@][^"]*": "[^"]+"' | sort)
NEW_PKGS=$(echo "$NEW" | grep -oE '"[a-zA-Z@][^"]*": "[^"]+"' | sort)
ADDED=$(comm -13 <(echo "$OLD_PKGS") <(echo "$NEW_PKGS"))
[ -z "$ADDED" ] && exit 0

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0

MARKER="/tmp/tosk-skills-${SESSION_ID}"
if [ ! -f "$MARKER" ] || ! grep -qF "<PREFIX>-skill" "$MARKER"; then
  MSG="Dependency gate: new packages detected in package.json — invoke <PREFIX>-skill first to assess whether new packages need reference files, then retry."
  echo "$MSG" >&2
  echo "  Adding: $(echo "$ADDED" | head -5 | tr '\n' ' ')" >&2
  if [ -n "$GEMINI_PROJECT_DIR" ]; then
    printf '{"decision":"deny","reason":"%s"}' "$MSG"
    exit 0
  fi
  exit 2
fi
exit 0
```

---

## § pre-handoff-check.sh

Blocks invocation of `<PREFIX>-qa` if the working tree has uncommitted changes, lint fails, or typecheck fails. Enforces commit-before-review and clean-code gates mechanically.

Gemini CLI note: `activate_skill` tool input uses `name` field (not `skill`). Both fields are checked below for compatibility.

```bash
#!/bin/bash
# PreToolUse Skill/activate_skill hook — blocks <PREFIX>-qa invocation if work isn't committed, lint fails, or types fail.

INPUT=$(cat) || exit 0
# Claude Code uses .tool_input.skill; Gemini CLI uses .tool_input.name
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // .tool_input.name // empty' 2>/dev/null)
[ -z "$SKILL" ] && exit 0

# Only fire when invoking <PREFIX>-qa
[ "$SKILL" != "<PREFIX>-qa" ] && exit 0

block() {
  echo "$1" >&2
  if [ -n "$GEMINI_PROJECT_DIR" ]; then
    printf '{"decision":"deny","reason":"%s"}' "$1"
    exit 0
  fi
  exit 2
}

# Block if there are any uncommitted changes to tracked files
DIRTY=$(git status --porcelain 2>/dev/null | grep -v '^??' | awk '{print $NF}')
if [ -n "$DIRTY" ]; then
  echo "Pre-handoff gate: uncommitted changes detected — commit all work before invoking <PREFIX>-qa:" >&2
  echo "$DIRTY" | head -10 | sed 's/^/  /' >&2
  if [ -n "$GEMINI_PROJECT_DIR" ]; then
    printf '{"decision":"deny","reason":"uncommitted changes detected"}'
    exit 0
  fi
  exit 2
fi

# Run lint check
if ! <LINT_CMD> > /dev/null 2>&1; then
  block "Pre-handoff gate: lint check failed — fix lint errors, then retry <PREFIX>-qa."
fi

# Run type check
if ! <TYPECHECK_CMD> > /dev/null 2>&1; then
  block "Pre-handoff gate: type check failed — fix type errors, then retry <PREFIX>-qa."
fi

exit 0
```

**Note:** Replace `<LINT_CMD>` and `<TYPECHECK_CMD>` with the project's actual commands. If the project has no typecheck, remove that block. If lint/typecheck commands aren't known at install time, leave `<fill in>` stubs and prompt the user to fill them in.

---

## § ref-sync-check.sh

Warns after `git commit` if `src/` or `lambda/` changed but no reference files were updated. Warn-only — always exits 0. Adjust the path patterns to match the project's source directories.

```bash
#!/bin/bash
# PostToolUse Bash hook — warns if src/lambda changed but no reference files updated.
# Fires after git commit. Warn-only (always exit 0).

INPUT=$(cat) || exit 0
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Only fire on git commit commands
echo "$COMMAND" | grep -qE "git commit" || exit 0
echo "$COMMAND" | grep -qE "\-\-dry-run|--help|-h[^a-z]" && exit 0

# Check if source files changed in the last commit (adjust paths for project)
git diff HEAD~1 --name-only 2>/dev/null | grep -qE '^(src/|lambda/)' || exit 0

# If reference files were also updated, no warning needed
git diff HEAD~1 --name-only 2>/dev/null | grep -qE '^<CONFIG_DIR>/skills/.*/references/' && exit 0

echo "" >&2
echo "⚠ Reference Sync: src/ or lambda/ changed but no reference files updated — verify Reference Sync is complete" >&2
echo "" >&2
exit 0
```

---

## § skill-mark.sh

Records each invoked skill to a session-scoped marker file. Used by `skill-guard.sh`, `dependency-guard.sh`, and `package-edit-guard.sh` to verify a skill was loaded.

Gemini CLI note: `activate_skill` uses `name` field (not `skill`) in tool input — both fields are checked.

```bash
#!/bin/bash
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
# Claude Code: .tool_input.skill; Gemini CLI activate_skill: .tool_input.name
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // .tool_input.name // empty' 2>/dev/null)
[ -z "$SKILL" ] && exit 0
echo "$SKILL" >> "/tmp/tosk-skills-${SESSION_ID}"
exit 0
```

---

## § post-commit.sh

Reminds the agent to run `<PREFIX>-log` after every successful git commit.

```bash
#!/bin/bash
# Reminds Claude to run <PREFIX>-log after a successful git commit.
# Fires as a PostToolUse hook on Bash.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only fire on git commit commands (not --dry-run, -h, --help, etc.)
if ! echo "$COMMAND" | grep -qE "git commit"; then
  exit 0
fi
if echo "$COMMAND" | grep -qE "\-\-dry-run|--help|-h[^a-z]"; then
  exit 0
fi

echo "" >&2
echo "📋 Commit complete — run <PREFIX>-log to append an entry to docs/project-log.md" >&2
echo "" >&2

exit 0
```

---

## § settings.json — Claude Code

Wire all 8 hooks. If the file already exists, merge the `hooks` key without removing unrelated settings. Timeout unit: **seconds**.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/skill-guard.sh", "timeout": 5 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/package-edit-guard.sh", "timeout": 5 }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/skill-guard.sh", "timeout": 5 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/path-coverage-check.sh", "timeout": 5 }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/dependency-guard.sh", "timeout": 5 }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/pre-handoff-check.sh", "timeout": 60 }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/post-commit.sh", "timeout": 10 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/ref-sync-check.sh", "timeout": 10 }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/<CONFIG_DIR>/hooks/skill-mark.sh", "timeout": 5 }
        ]
      }
    ]
  }
}
```

---

## § settings.json — Gemini CLI

Gemini CLI tool names: `replace` (Edit), `write_file` (Write), `run_shell_command` (Bash), `activate_skill` (Skill). Timeout unit: **milliseconds**. Hooks must output valid JSON to stdout — plain text to stdout causes parsing failure. Blocking exit code: **2**.

Matchers are regex on tool names. One hook object per `hooks` array entry (Gemini CLI does not support multiple hook objects per matcher entry — use separate matcher blocks for hooks that share a trigger tool).

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "replace",
        "hooks": [
          { "name": "skill-guard", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/skill-guard.sh", "timeout": 5000 }
        ]
      },
      {
        "matcher": "replace",
        "hooks": [
          { "name": "package-edit-guard", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/package-edit-guard.sh", "timeout": 5000 }
        ]
      },
      {
        "matcher": "write_file",
        "hooks": [
          { "name": "skill-guard-write", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/skill-guard.sh", "timeout": 5000 }
        ]
      },
      {
        "matcher": "write_file",
        "hooks": [
          { "name": "path-coverage-check", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/path-coverage-check.sh", "timeout": 5000 }
        ]
      },
      {
        "matcher": "run_shell_command",
        "hooks": [
          { "name": "dependency-guard", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/dependency-guard.sh", "timeout": 5000 }
        ]
      },
      {
        "matcher": "activate_skill",
        "hooks": [
          { "name": "pre-handoff-check", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/pre-handoff-check.sh", "timeout": 60000 }
        ]
      }
    ],
    "AfterTool": [
      {
        "matcher": "run_shell_command",
        "hooks": [
          { "name": "post-commit", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/post-commit.sh", "timeout": 10000 }
        ]
      },
      {
        "matcher": "run_shell_command",
        "hooks": [
          { "name": "ref-sync-check", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/ref-sync-check.sh", "timeout": 10000 }
        ]
      },
      {
        "matcher": "activate_skill",
        "hooks": [
          { "name": "skill-mark", "type": "command", "command": "$GEMINI_PROJECT_DIR/<CONFIG_DIR>/hooks/skill-mark.sh", "timeout": 5000 }
        ]
      }
    ]
  }
}
