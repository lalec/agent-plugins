# Hook Templates

Claude Code only.

Replace these placeholders before writing the files:
- `<PREFIX>` → the chosen skill/agent prefix
- `<GOVERNED_ROOTS>` → ERE alternation of **actual top-level source/asset directories** (see § How to generate for an example). Must be directory prefixes — **never extension globs** like `.*\.(html|css|js)$`, which match files outside the project dir (e.g. `/tmp/`) and defeat the guard. Root-level files (e.g. `index.html`) are owned via PATH_MAP entries, not GOVERNED_ROOTS. Sourced from the Frontend, Backend, Database/storage, Auth, Observability, and Third-party SDK categories discovered in Phase 1c.
- `<DEPLOY_PATHS>` → ERE alternation of paths and root-level files belonging to the IaC, CI/CD, Build tooling, and Deployment scripts/config categories (see § How to generate for an example). May be the empty string `''` if no such categories were discovered (in which case `ref-sync-check.sh` simply skips its deploy-drift check). Folder names are signal-derived, not name-baked — whatever names the project actually uses.
- `<PATH_MAP_ENTRIES>` → generated entries from § How to generate governed-paths.conf
- `<SKILL_SELF_OWNERSHIP_ENTRIES>` → one `'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'` entry per installed skill (lifecycle + domain), so each skill edits its own SKILL.md and `references/` with itself loaded — without these, a domain skill's own reference updates get blocked for lacking `<PREFIX>-skill`
- `<REF_WATCH>` → optional ERE alternation of reference-worthy source files (API route/handler dirs, schema/model files, auth middleware) derived from the category map. Used by `ref-sync-check.sh` to decide whether a modify-only commit warrants a reference-sync warning. `''` when nothing clearly reference-worthy is identifiable — structural changes (add/delete/rename) in governed roots always warn regardless
- `<LINT_CMD>` → project lint command (e.g. `pnpm exec biome check .` or `npm run lint`)
- `<TYPECHECK_CMD>` → project typecheck command (e.g. `pnpm exec tsc --noEmit` or `npm run typecheck`)

**Hook conduct rules (apply to every script below):**
- *Gates* (skill-guard, path-coverage, dependency-guard, package-edit-guard, pre-handoff, close-out-gate) exit 2 with an actionable message on violation, 0 otherwise.
- *Recorders* (ref-sync-check, skill-mark, post-commit) must **always exit 0** — a recorder that exits non-zero makes successful commands surface as errors and burns a reasoning turn.

---

## § governed-paths.conf

The single source of truth for path→skill ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source this file. **Never put path patterns directly in the hook scripts.**

```bash
# governed-paths.conf
# Single source of truth for path→skill ownership AND for deploy-mechanism path watching.
# Sourced by skill-guard.sh, path-coverage-check.sh, and ref-sync-check.sh — edit here only.
#
# PATH_MAP format: 'PATTERN:SKILL'
#   SKILL=EXEMPT  — always allowed, skip guard (e.g. project-log.md written by <PREFIX>-log)
#   SKILL=OPEN    — inside .claude/ but no ownership guard needed
#   SKILL=<name>  — the skill that must be loaded before editing this path
#
# GOVERNED_ROOTS: ERE alternation of top-level roots that must be fully covered.
# path-coverage-check.sh blocks Write to these roots if no PATH_MAP entry matches.
# ref-sync-check.sh warns if these change without reference file updates.
# Populated from Frontend/Backend/Database/Auth/Observability/SDK categories.
#
# DEPLOY_PATHS: ERE alternation of files/dirs belonging to deploy-mechanism categories
# (IaC, CI/CD, Build tooling, Deployment scripts/config). Watched by ref-sync-check.sh
# for drift against deploy-config.yaml. Empty string if project has no deploy mechanism.
#
# REF_WATCH: optional ERE of reference-worthy source files (route/handler dirs, schema/model
# files, auth middleware). ref-sync-check.sh warns on modify-only commits ONLY when these match;
# add/delete/rename in GOVERNED_ROOTS always warns. '' = structural-only warnings.

GOVERNED_ROOTS='<GOVERNED_ROOTS>'
DEPLOY_PATHS='<DEPLOY_PATHS>'
REF_WATCH='<REF_WATCH>'

PATH_MAP=(
  '^docs/roadmap\.md$:EXEMPT'
  '^docs/project-log\.md$:EXEMPT'
<SKILL_SELF_OWNERSHIP_ENTRIES>
  '^\.claude/skills/:<PREFIX>-skill'
  '^\.claude/hooks/|^\.claude/agents/:<PREFIX>-skill'
  '^CLAUDE\.md$:<PREFIX>-skill'
  '^\.claude/:OPEN'
<PATH_MAP_ENTRIES>
  '^README\.md$|^docs/:<PREFIX>-docs'
)
```

---

## § How to generate governed-paths.conf

For each confirmed skill→path mapping, add one `'PATTERN:SKILL'` entry to `PATH_MAP`. More-specific patterns must come before catch-alls. The first matching entry wins.

`GOVERNED_ROOTS` and `DEPLOY_PATHS` are derived from the category map produced in Phase 1c — not name-baked. Build them by iterating the categories actually present in this project:

| Category | Contributes to |
|---|---|
| Frontend, Backend, Database/storage, Auth, Observability, Third-party SDK | `GOVERNED_ROOTS` |
| IaC, CI/CD, Build tooling, Deployment scripts/config | `DEPLOY_PATHS` |

Each category contributes the actual paths (or root-level files) it occupies in this project. If no categories of a given group are present, the corresponding variable is `''`.

**Example** (myapp: Backend=`api/`, Frontend=`app/`, IaC=`infra/`, CI/CD=`.github/workflows/`, Deployment=`scripts/deploy.sh` + `fly.toml`):
```bash
GOVERNED_ROOTS='^(api/|app/)'
DEPLOY_PATHS='^(infra/|\.github/workflows/|scripts/deploy\.sh$|fly\.toml$)'
REF_WATCH='^(api/routes/|api/models/|api/auth/)'

PATH_MAP=(
  '^docs/project-log\.md$:EXEMPT'
  '^\.claude/skills/myapp-backend/:myapp-backend'
  '^\.claude/skills/myapp-frontend/:myapp-frontend'
  '^\.claude/skills/myapp-deploy/:myapp-deploy'
  '^\.claude/skills/myapp-test/:myapp-test'
  '^\.claude/skills/:myapp-skill'
  '^\.claude/hooks/|^\.claude/agents/:myapp-skill'
  '^CLAUDE\.md$:myapp-skill'
  '^\.claude/:OPEN'
  '^api/|^app/auth/:myapp-backend'
  '^app/|^next\.config\.|^tsconfig\.json$:myapp-frontend'
  '^infra/|^\.github/|^fly\.toml$|^scripts/:myapp-deploy'
  '^README\.md$|^docs/:myapp-docs'
)
```

For projects with no deploy mechanism (e.g. a static prototype), set `DEPLOY_PATHS=''` — `ref-sync-check.sh` skips the deploy-drift check.

Rules:
- `docs/project-log.md` is always `EXEMPT` (written by `<PREFIX>-log` without skill loading)
- **Every installed `<PREFIX>-*` skill gets a self-ownership entry** (`'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'`) before the `.claude/skills/` catch-all — a skill maintains its own SKILL.md and `references/` with itself loaded. The `<PREFIX>-skill` catch-all after them still owns cross-skill structure (new skill dirs, renames)
- `.claude/skills/` (catch-all), `.claude/hooks/`, `.claude/agents/`, and `CLAUDE.md` are owned by `<PREFIX>-skill`
- The rest of `.claude/` is `OPEN` (no guard needed for other config)
- `README.md` and `docs/` are always owned by `<PREFIX>-docs`
- Domain skill entries go in between, ordered more-specific first
- `DEPLOY_PATHS` is independent of `PATH_MAP` ownership. A file can appear in `DEPLOY_PATHS` (for drift watching) *and* be owned by a non-deploy skill in `PATH_MAP` — a deploy-mechanism file that lives in the backend domain is correctly listed under both. Every path from IaC/CI/CD/Build/Deployment categories goes into `DEPLOY_PATHS` regardless of which skill owns it.
- `REF_WATCH` narrows the reference-sync warning to commits that plausibly change what reference files describe (contracts, schemas, auth) — without it every copy tweak in a governed root warned, and the warning was learned to be ignorable (15 ignored warnings in one audited session).

---

## § skill-guard.sh

Blocks Edit/Write tool calls to owned paths if the owning skill hasn't been loaded. Sources `governed-paths.conf` — no path patterns in this file.

```bash
#!/bin/bash
INPUT=$(cat) || exit 0
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

# Strip project dir prefix from absolute paths
FILE="${FILE#"$CLAUDE_PROJECT_DIR"/}"
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

# Marker is scoped per agent: subagents have their own transcript_path, so a skill loaded
# by one agent never satisfies another agent's gate (shared markers let pm inherit dev's marks).
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
AGENT=""
[ -n "$TRANSCRIPT" ] && AGENT="-$(basename "$TRANSCRIPT" .jsonl)"
MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}${AGENT}"

if [ ! -f "$MARKER" ] || ! grep -qF "$SKILL" "$MARKER"; then
  MSG="Skill gate: '${FILE##*/}' is owned by ${SKILL} — invoke it first (skill=\"${SKILL}\"), then retry."
  echo "$MSG" >&2
  exit 2
fi
exit 0
```

---

## § path-coverage-check.sh

Blocks Write tool calls to files in governed roots that aren't covered by any PATH_MAP entry. Sources `governed-paths.conf` — no path patterns in this file.

```bash
#!/bin/bash
# PreToolUse Write hook — blocks new files in governed roots not covered by any PATH_MAP entry.

INPUT=$(cat) || exit 0
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

FILE="${FILE#"$CLAUDE_PROJECT_DIR"/}"
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
exit 2
```

---

## § dependency-guard.sh

Blocks `pnpm add`, `npm install`, `yarn add`, and `pip install` commands unless `<PREFIX>-skill` has been loaded. Forces the agent to assess whether a new package requires a reference file before installing.

```bash
#!/bin/bash
# PreToolUse Bash hook — blocks dependency installs without <PREFIX>-skill loaded.

INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# Check if command installs dependencies
echo "$CMD" | grep -qE "(pnpm add|npm install|yarn add|pip install)" || exit 0

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0  # fail-open if no session ID

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
AGENT=""
[ -n "$TRANSCRIPT" ] && AGENT="-$(basename "$TRANSCRIPT" .jsonl)"
MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}${AGENT}"

if [ ! -f "$MARKER" ] || ! grep -qF "<PREFIX>-skill" "$MARKER"; then
  MSG="Dependency gate: '${CMD}' installs a new package — invoke <PREFIX>-skill first (skill=\"<PREFIX>-skill\") to assess whether new packages need reference files, then retry."
  echo "$MSG" >&2
  exit 2
fi
exit 0
```

---

## § package-edit-guard.sh

Blocks direct dependency additions to `package.json` via the Edit tool without `<PREFIX>-skill` loaded. Closes the bypass path where agents edit `package.json` directly instead of running `pnpm add`.

```bash
#!/bin/bash
# PreToolUse Edit hook — blocks direct dependency additions to package.json without <PREFIX>-skill loaded.

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

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
AGENT=""
[ -n "$TRANSCRIPT" ] && AGENT="-$(basename "$TRANSCRIPT" .jsonl)"
MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}${AGENT}"

if [ ! -f "$MARKER" ] || ! grep -qF "<PREFIX>-skill" "$MARKER"; then
  MSG="Dependency gate: new packages detected in package.json — invoke <PREFIX>-skill first to assess whether new packages need reference files, then retry."
  echo "$MSG" >&2
  echo "  Adding: $(echo "$ADDED" | head -5 | tr '\n' ' ')" >&2
  exit 2
fi
exit 0
```

---

## § pre-handoff-check.sh

Blocks invocation of `<PREFIX>-qa` if the working tree has uncommitted changes, lint fails, or typecheck fails. Enforces commit-before-review and clean-code gates mechanically. **Must match both invocation paths:** the Skill tool (`tool_input.skill`) *and* an Agent/Task spawn (`tool_input.subagent_type`) — in the pipeline qa is spawned as a subagent, so a Skill-only match makes this gate dead code.

```bash
#!/bin/bash
# PreToolUse Skill+Task hook — blocks <PREFIX>-qa invocation if work isn't committed, lint fails, or types fail.

INPUT=$(cat) || exit 0
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null)

# Fire when qa is invoked as a skill OR spawned as a subagent
[ "$SKILL" != "<PREFIX>-qa" ] && [ "$AGENT_TYPE" != "<PREFIX>-qa" ] && exit 0

# Block if there are any uncommitted changes to tracked files
DIRTY=$(git status --porcelain 2>/dev/null | grep -v '^??' | awk '{print $NF}')
if [ -n "$DIRTY" ]; then
  echo "Pre-handoff gate: uncommitted changes detected — commit all work before invoking <PREFIX>-qa:" >&2
  echo "$DIRTY" | head -10 | sed 's/^/  /' >&2
  exit 2
fi

# Run lint check
if ! <LINT_CMD> > /dev/null 2>&1; then
  echo "Pre-handoff gate: lint check failed — fix lint errors, then retry <PREFIX>-qa." >&2
  exit 2
fi

# Run type check
if ! <TYPECHECK_CMD> > /dev/null 2>&1; then
  echo "Pre-handoff gate: type check failed — fix type errors, then retry <PREFIX>-qa." >&2
  exit 2
fi

exit 0
```

**Note:** Replace `<LINT_CMD>` and `<TYPECHECK_CMD>` with the project's actual commands. If the project has no typecheck, remove that block. If lint/typecheck commands aren't known at install time, leave `<fill in>` stubs and prompt the user to fill them in.

---

## § ref-sync-check.sh

Warns after `git commit` when paths watched in `governed-paths.conf` changed without corresponding reference file updates. Two independent checks:

1. **Source drift** — warns only on commits that plausibly change what references describe: files **added/deleted/renamed** in `GOVERNED_ROOTS`, or modified files matching `REF_WATCH` (contracts, schemas, auth). Modify-only cosmetic commits (copy tweaks, style nudges) stay silent — an alarm that fires on every commit gets learned as ignorable and loses all signal.
2. **Deploy drift** — `DEPLOY_PATHS` changed without `deploy-config.yaml` being touched → the deploy profile is now stale.

Sources `governed-paths.conf` — **no path patterns hardcoded in this script**. If a variable is empty, the corresponding check is silently skipped. Warn-only — always exits 0.

```bash
#!/bin/bash
# PostToolUse Bash hook — warns when governed paths changed without reference updates.
# Fires after git commit. Warn-only (always exit 0). Sources governed-paths.conf.

INPUT=$(cat) || exit 0
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Only fire on git commit commands; skip dry-runs and help invocations
echo "$COMMAND" | grep -qE "git commit" || exit 0
echo "$COMMAND" | grep -qE "\-\-dry-run|--help|-h[^a-z]" && exit 0

source "$(dirname "$0")/governed-paths.conf"

CHANGED=$(git diff HEAD~1 --name-only 2>/dev/null) || exit 0
[ -z "$CHANGED" ] && exit 0

# Check 1 — source drift: structural changes (A/D/R) in governed roots, or REF_WATCH matches
if [ -n "$GOVERNED_ROOTS" ]; then
  STRUCTURAL=$(git diff HEAD~1 --name-status 2>/dev/null | awk '$1 ~ /^(A|D|R)/ {print $NF}' | grep -E "$GOVERNED_ROOTS")
  WATCHED=""
  [ -n "${REF_WATCH:-}" ] && WATCHED=$(echo "$CHANGED" | grep -E "$REF_WATCH")
  if [ -n "$STRUCTURAL" ] || [ -n "$WATCHED" ]; then
    if ! echo "$CHANGED" | grep -qE '^\.claude/skills/.*/references/'; then
      echo "" >&2
      echo "⚠ Reference Sync: reference-worthy source changed (structural or watched paths) but no reference files updated — verify Reference Sync is complete" >&2
      echo "" >&2
    fi
  fi
fi

# Check 2 — deploy drift
if [ -n "$DEPLOY_PATHS" ] && echo "$CHANGED" | grep -qE "$DEPLOY_PATHS"; then
  if ! echo "$CHANGED" | grep -qE '^\.claude/skills/.*/references/deploy-config\.yaml$'; then
    echo "" >&2
    echo "⚠ Deploy Profile: deploy-mechanism paths (\$DEPLOY_PATHS) changed but deploy-config.yaml was not updated — invoke the deploy-owning skill to reconcile" >&2
    echo "" >&2
  fi
fi

exit 0
```

---

## § skill-mark.sh

Records each invoked skill to an agent-scoped marker file. Used by `skill-guard.sh`, `dependency-guard.sh`, and `package-edit-guard.sh` to verify a skill was loaded. The marker key must match the guards' derivation exactly: session id + transcript basename — per-agent scoping is what stops one subagent's skill loads from satisfying another's gates.

```bash
#!/bin/bash
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
[ -z "$SKILL" ] && exit 0
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
AGENT=""
[ -n "$TRANSCRIPT" ] && AGENT="-$(basename "$TRANSCRIPT" .jsonl)"
echo "$SKILL" >> "/tmp/<PREFIX>-skills-${SESSION_ID}${AGENT}"
exit 0
```

---

## § close-out-gate.sh

Blocks `git push` while commits after the last delivery-log entry touch governed or deploy paths — the iterate lane's teeth: work and commit freely all day, but nothing leaves the machine without one batched close-out (`/tweak` exit, `/wrap`, or the pipeline's pm step, all of which commit a log entry). Emergency override: `CLOSEOUT_OVERRIDE=1 git push …`.

```bash
#!/bin/bash
# PreToolUse Bash hook — blocks git push when governed commits lack delivery-log coverage.

INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0
echo "$CMD" | grep -qE "git push" || exit 0
echo "$CMD" | grep -qE "CLOSEOUT_OVERRIDE=1" && exit 0

source "$(dirname "$0")/governed-paths.conf"
[ -z "$GOVERNED_ROOTS" ] && [ -z "$DEPLOY_PATHS" ] && exit 0

# Last close-out = last commit touching the delivery log; none yet → don't block a fresh repo
LAST_LOG=$(git log -n1 --format=%H -- docs/project-log.md 2>/dev/null)
[ -z "$LAST_LOG" ] && exit 0

CHANGED=$(git diff "$LAST_LOG"..HEAD --name-only 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

UNCOVERED=""
[ -n "$GOVERNED_ROOTS" ] && UNCOVERED=$(echo "$CHANGED" | grep -E "$GOVERNED_ROOTS")
if [ -z "$UNCOVERED" ] && [ -n "$DEPLOY_PATHS" ]; then
  UNCOVERED=$(echo "$CHANGED" | grep -E "$DEPLOY_PATHS")
fi
[ -z "$UNCOVERED" ] && exit 0

echo "Close-out gate: commits since the last delivery-log entry touch governed paths with no log coverage — run the close-out (review + <PREFIX>-log + <PREFIX>-docs + ref sync; /wrap or the /tweak exit) before pushing. Emergency override: CLOSEOUT_OVERRIDE=1 git push …" >&2
echo "$UNCOVERED" | head -10 | sed 's/^/  /' >&2
exit 2
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

## § settings.json

Wire all 9 hooks. If the file already exists, merge the `hooks` key without removing unrelated settings. Timeout unit: **seconds**. The `Task|Agent` matcher is what makes `pre-handoff-check.sh` fire when qa is spawned as a subagent — without it the gate never runs in the pipeline.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/skill-guard.sh", "timeout": 5 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/package-edit-guard.sh", "timeout": 5 }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/skill-guard.sh", "timeout": 5 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/path-coverage-check.sh", "timeout": 5 }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/dependency-guard.sh", "timeout": 5 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/close-out-gate.sh", "timeout": 10 }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pre-handoff-check.sh", "timeout": 60 }
        ]
      },
      {
        "matcher": "Task|Agent",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pre-handoff-check.sh", "timeout": 60 }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/post-commit.sh", "timeout": 10 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ref-sync-check.sh", "timeout": 10 }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/skill-mark.sh", "timeout": 5 }
        ]
      }
    ]
  }
}
```
