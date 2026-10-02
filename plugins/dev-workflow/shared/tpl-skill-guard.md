# Hook Templates

Claude Code only.

Replace these placeholders before writing the files:
- `<PREFIX>` → the chosen skill/agent prefix
- `<GOVERNED_ROOTS>` → ERE alternation of **actual top-level source/asset directories** (see § How to generate for an example). Must be directory prefixes — **never extension globs** like `.*\.(html|css|js)$`, which match files outside the project dir (e.g. `/tmp/`) and defeat the guard. Root-level files (e.g. `index.html`) are owned via PATH_MAP entries, not GOVERNED_ROOTS. Sourced from the Frontend, Backend, Database/storage, Auth, Observability, and Third-party SDK categories discovered in Phase 1c.
- `<DEPLOY_PATHS>` → ERE alternation of paths and root-level files belonging to the IaC, CI/CD, Build tooling, and Deployment scripts/config categories (see § How to generate for an example). May be the empty string `''` if no such categories were discovered (in which case `ref-sync-check.sh` simply skips its deploy-drift check). Folder names are signal-derived, not name-baked — whatever names the project actually uses.
- `<PATH_MAP_ENTRIES>` → generated entries from § How to generate governed-paths.conf
- `<SKILL_SELF_OWNERSHIP_ENTRIES>` → one `'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'` entry per installed skill (lifecycle + domain), so each skill edits its own SKILL.md and `references/` with itself loaded — without these, a domain skill's own reference updates get blocked for lacking `<PREFIX>-skill`
- `<REF_WATCH>` → optional ERE alternation of reference-worthy source files (API route/handler dirs, schema/model files, auth middleware) derived from the category map. Used by `ref-sync-check.sh` to decide whether a modify-only commit warrants a reference-sync warning. `''` when nothing clearly reference-worthy is identifiable — structural changes (add/delete/rename) in governed roots always warn regardless
- `<DEPENDENCY_MANIFESTS>` → optional ERE alternation of the project's dependency manifests, matched by **filename, not layout** — `requirements*.txt`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Gemfile` and their lock files, whichever of them this project actually has. Used by `ref-sync-check.sh` to warn when a dependency lands without its advisories being assessed. `''` when the project has none (the check is then silently skipped)
- `<COPY_PATHS>` → optional ERE of the directories holding this project's **user-facing** source — the Frontend category's paths, only when a `<PREFIX>-design` skill is installed. Used by `ref-sync-check.sh` to warn when a commit adds an em dash to a user-readable string. `''` when there is no design skill (the check is then silently skipped)
- `<UNATTENDED_DENY>` → ERE alternation of the paths an **unattended** `/pilot` run must never touch: `DEPLOY_PATHS` plus the Auth category's paths from `CATEGORY_MAP`, plus a migrations directory when one was discovered under Database/storage. Nobody is present to notice a change there, so a task whose paths intersect it is skipped and reported, never started unattended. When the auth paths are unknown, set it to the `DEPLOY_PATHS` value and say so — the project widens it.
- `<LINT_CMD>` → project lint command (e.g. `pnpm exec biome check .` or `npm run lint`)
- `<TYPECHECK_CMD>` → project typecheck command (e.g. `pnpm exec tsc --noEmit` or `npm run typecheck`)

**Hook conduct rules (apply to every script below):**
- *Gates* (skill-guard, path-coverage, dependency-guard, package-edit-guard, pre-handoff, close-out-gate) exit 2 with an actionable message on violation, 0 otherwise. `agent-mark` is the one gate on a lifecycle event: it blocks a stop through `decision: block` JSON (exit codes carry no meaning on `SubagentStop`), and only once per agent.
- *Lifecycle recorders* (pilot-cleanup on `SessionEnd`, limit-mark on `StopFailure`) write a file and exit 0; Claude Code ignores their output entirely, so the file is their whole effect.
- *Recorders* (ref-sync-check, skill-mark, post-commit) must **always exit 0** — a recorder that exits non-zero makes successful commands surface as errors and burns a reasoning turn. A recorder with something to tell the model prints it as `hookSpecificOutput.additionalContext` JSON on stdout. Stderr from a hook that exits 0 goes to the debug log only, so a warning written there reaches neither the model nor the user.

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
#
# DEPENDENCY_MANIFESTS: optional ERE of this project's dependency manifests, matched by filename
# rather than layout. ref-sync-check.sh warns when one changes without vex.yaml being assessed.
# '' = no manifests, check skipped.
#
# COPY_PATHS: optional ERE of user-facing source (the Frontend category, when <PREFIX>-design exists).
# ref-sync-check.sh warns when a commit adds an em dash on a non-comment line there. '' = skipped.

GOVERNED_ROOTS='<GOVERNED_ROOTS>'
DEPLOY_PATHS='<DEPLOY_PATHS>'
REF_WATCH='<REF_WATCH>'
DEPENDENCY_MANIFESTS='<DEPENDENCY_MANIFESTS>'
COPY_PATHS='<COPY_PATHS>'
UNATTENDED_DENY='<UNATTENDED_DENY>'

PATH_MAP=(
  '^docs/roadmap\.md$:EXEMPT'
  '^docs/project-log\.md$:EXEMPT'
  '^\.claude/skills/<PREFIX>-test/references/custom-tests\.yaml$:EXEMPT'
  '^\.claude/skills/<PREFIX>-review/references/vex\.yaml$:EXEMPT'
  '^\.claude/graph/edges\.jsonl$:EXEMPT'
  '^\.claude/pilot/:EXEMPT'
  '^\.claude/graph/:<PREFIX>-graph'
  '^\.claude/skills/(code|fix|pilot|tweak|audit|revert|tidy|whats-up|roadmap|blueprint|wrap|design|handover|proceed)/:OPEN'
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

`DEPENDENCY_MANIFESTS` comes from a **filename scan**, not the category map: list the manifest and lock filenames this repo actually contains, anchored `(^|/)…$` so a monorepo's per-package copies match too. `''` when the project has none.

`COPY_PATHS` is the Frontend category's paths, and only when `<PREFIX>-design` is installed — the same condition that ships `voice.md`, whose rule the check points at. `''` otherwise.

**Example** (myapp: Backend=`api/`, Frontend=`app/`, IaC=`infra/`, CI/CD=`.github/workflows/`, Deployment=`scripts/deploy.sh` + `fly.toml`):
```bash
GOVERNED_ROOTS='^(api/|app/)'
DEPLOY_PATHS='^(infra/|\.github/workflows/|scripts/deploy\.sh$|fly\.toml$)'
REF_WATCH='^(api/routes/|api/models/|api/auth/)'
DEPENDENCY_MANIFESTS='(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|requirements[^/]*\.txt|pyproject\.toml|uv\.lock)$'
COPY_PATHS='^app/'
UNATTENDED_DENY='^(infra/|\.github/workflows/|scripts/deploy\.sh$|fly\.toml$|api/auth/)'

PATH_MAP=(
  '^docs/project-log\.md$:EXEMPT'
  '^\.claude/skills/myapp-test/references/custom-tests\.yaml$:EXEMPT'
  '^\.claude/skills/myapp-review/references/vex\.yaml$:EXEMPT'
  '^\.claude/graph/edges\.jsonl$:EXEMPT'
  '^\.claude/pilot/:EXEMPT'
  '^\.claude/graph/:myapp-graph'
  '^\.claude/skills/(code|fix|pilot|tweak|audit|revert|tidy|whats-up|roadmap|blueprint|wrap|design|handover|proceed)/:OPEN'
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
- `UNATTENDED_DENY` is read by `/pilot` only (Step 2, the unattended skip); no hook enforces it, because the run that would violate it is the one deciding what to start, and a hook on `Edit` would fire inside the agent after the work had begun.
- The entry-point skills (`code`, `fix`, `pilot`, … — the fixed names in `preflight.md § Where the entry points live`) are `OPEN`, exactly as `.claude/commands/` always was: they are commands in Rules 1–2's sense and no lifecycle skill owns them. The entry sits **before** the `.claude/skills/` catch-all, or every edit to one would demand `<PREFIX>-skill` loaded.
- `.claude/pilot/` is always `EXEMPT` and gitignored whole — `/pilot` writes its run markers there at the top level and the lifecycle hooks write `limit-hit`; nothing in it is tracked. (Legacy note, kept so a grep finds it: the directory once held a tracked `shift.sh`, a verbatim plugin copy that no skill authors
- `<PREFIX>-test/references/custom-tests.yaml` is always `EXEMPT` — the `/code`/`/fix` Step 1.5 persist step writes it at the top level and carries the schema itself; gating it forces a full skill load per pipeline run for a 10-line append
- `<PREFIX>-review/references/vex.yaml` is always `EXEMPT` — the security pass writes a status from inside `<PREFIX>-qa` and `/audit` writes one at the top level, and `<PREFIX>-review` is a read-only reference skill that owns no write path of its own
- **Every installed `<PREFIX>-*` skill gets a self-ownership entry** (`'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'`) before the `.claude/skills/` catch-all — a skill maintains its own SKILL.md and `references/` with itself loaded. The `<PREFIX>-skill` catch-all after them still owns cross-skill structure (new skill dirs, renames)
- `.claude/skills/` (catch-all), `.claude/hooks/`, `.claude/agents/`, and `CLAUDE.md` are owned by `<PREFIX>-skill`
- The rest of `.claude/` is `OPEN` (no guard needed for other config)
- `README.md` and `docs/` are always owned by `<PREFIX>-docs`
- Domain skill entries go in between, ordered more-specific first
- `DEPLOY_PATHS` is independent of `PATH_MAP` ownership. A file can appear in `DEPLOY_PATHS` (for drift watching) *and* be owned by a non-deploy skill in `PATH_MAP` — a deploy-mechanism file that lives in the backend domain is correctly listed under both. Every path from IaC/CI/CD/Build/Deployment categories goes into `DEPLOY_PATHS` regardless of which skill owns it.
- `REF_WATCH` narrows the reference-sync warning to commits that plausibly change what reference files describe (contracts, schemas, auth) — without it every copy tweak in a governed root warned, and the warning was learned to be ignorable (15 ignored warnings in one audited session).
- `COPY_PATHS` checks **added lines only**, so a project with hundreds of em dashes already in its copy is never blocked or nagged about them — only a commit that writes a new one, or edits a line that still carries an old one, warns. Comment lines are skipped because em dashes in code comments are common and harmless; a check that fired on them would be learned as ignorable.
- `DEPENDENCY_MANIFESTS` is matched by **filename anywhere in the tree**, not by a top-level path, because a monorepo carries one per package and a layout-shaped pattern misses all but the root. Include the lock files only if this project's routine updates do not churn them — a warning that fires on every lockfile bump is learned as ignorable exactly like the one above, and the fix is to narrow this variable, never to blunt the message.

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

# Marker is scoped per SESSION, not per agent. Subagents inherit the parent's transcript_path,
# so no per-agent key is derivable from the hook payload. The gate is deliberately session-wide:
# <PREFIX>-log derives the delivery log's Skills field from this same marker, and that field is
# the only surviving record that a subagent-only skill (<PREFIX>-review, <PREFIX>-debug) ran.
# Consequence, stated plainly: within one session, a skill loaded by one agent DOES satisfy
# another agent's gate. That is the accepted trade — do not "fix" it without moving the
# Skills derivation in <PREFIX>-log at the same time.
MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}"

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

MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}"  # session-scoped — see skill-guard.sh

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

MARKER="/tmp/<PREFIX>-skills-${SESSION_ID}"  # session-scoped — see skill-guard.sh

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

Blocks invocation of `<PREFIX>-qa` if the working tree has uncommitted changes, lint fails, or typecheck fails — and blocks **every** pipeline-agent dispatch while `.claude/pilot/stop` exists, so a stop dropped from a phone lands at the next subagent boundary. Enforces commit-before-review and clean-code gates mechanically. **Must match both invocation paths:** the Skill tool (`tool_input.skill`) *and* an Agent/Task spawn (`tool_input.subagent_type`) — in the pipeline qa is spawned as a subagent, so a Skill-only match makes this gate dead code.

```bash
#!/bin/bash
# PreToolUse Skill+Task hook — blocks <PREFIX>-qa invocation if work isn't committed, lint fails, or types fail.

INPUT=$(cat) || exit 0
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null)

# A stop file refuses every pipeline-agent dispatch: a /pilot stop dropped mid-task lands at the next
# subagent boundary instead of the next task boundary. The run deletes the file when it honours it.
STOP="${CLAUDE_PROJECT_DIR:-.}/.claude/pilot/stop"
if [ -f "$STOP" ] && [ -n "$AGENT_TYPE" ] && echo "$AGENT_TYPE" | grep -qE '^<PREFIX>-(dev|qa|pm|verify)$'; then
  echo "Stop gate: .claude/pilot/stop exists ($(head -1 "$STOP")) — no further agent is dispatched; close out the run, which removes the file." >&2
  exit 2
fi

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

**Bare-shell rule (critical).** This hook runs in a **bare, non-interactive shell that does not inherit the project's activated environment** — no virtualenv, no `nvm`/`asdf` shim, no `direnv`, none of the `PATH` your terminal has. A command that names a bare interpreter or tool (`ruff check .`, `python -m ruff`, `eslint .`, `tsc`) works in your terminal but **fails inside this hook** the moment it depends on an activated env — silently failing the gate on every handoff. Substitute a command that resolves its own toolchain from a bare shell, in this order of preference:
1. An env-launcher that finds the project env itself: `uv run ruff check .`, `poetry run ruff check .`, `pnpm exec biome check .`, `npx --no-install eslint .`.
2. An absolute path into the project env: `.venv/bin/ruff check .`, `node_modules/.bin/eslint .`.
3. Only if neither exists, a bare tool name — and then confirm the tool is genuinely on the global `PATH` a bare shell sees.

When the interpreter path itself varies (a venv that may or may not exist), resolve it defensively at the top of the hook rather than hardcoding one path, e.g.:
```bash
if   [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
elif command -v python3       >/dev/null 2>&1; then PY="python3"
elif command -v python        >/dev/null 2>&1; then PY="python"
fi
[ -n "$PY" ] && ! "$PY" -m ruff check . >/dev/null 2>&1 && { echo "Pre-handoff gate: lint check failed …" >&2; exit 2; }
```
The same bare-shell constraint applies to any tool a hook shells out to (typecheckers, test runners) — never assume the project env is active.

---

## § ref-sync-check.sh

Warns after `git commit` when paths watched in `governed-paths.conf` changed without corresponding reference file updates, or when user-facing copy broke a mechanical voice rule. Four independent checks:

1. **Source drift** — warns only on commits that plausibly change what references describe: files **added/deleted/renamed** in `GOVERNED_ROOTS`, or modified files matching `REF_WATCH` (contracts, schemas, auth). Modify-only cosmetic commits (copy tweaks, style nudges) stay silent — an alarm that fires on every commit gets learned as ignorable and loses all signal.
2. **Deploy drift** — `DEPLOY_PATHS` changed without `deploy-config.yaml` being touched → the deploy profile is now stale.
3. **Dependency drift** — `DEPENDENCY_MANIFESTS` changed without `vex.yaml` being touched → a package landed whose advisories nobody has assessed. Warn, never block: a gate here fires on lockfile churn and gets overridden reflexively inside a week, which is worse than no hook. The value is the reminder at the moment the package lands.
4. **Copy** — a line **added** under `COPY_PATHS` carries an em dash and is not a comment → a user-readable string breaks `voice.md` rule 3. Warn, never block: a gate would fire on the first edit to a line that already had one, in a project that has hundreds. The rest of `voice.md` is judgment, checked at review, not here.

Sources `governed-paths.conf` — **no path patterns hardcoded in this script**. If a variable is empty, the corresponding check is silently skipped. Warn-only — always exits 0, and every warning goes out as one `additionalContext` block so the model actually reads it.

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

WARNINGS=""
warn() { WARNINGS="${WARNINGS}⚠ $1"$'\n'; }

# Check 1 — source drift: structural changes (A/D/R) in governed roots, or REF_WATCH matches
if [ -n "$GOVERNED_ROOTS" ]; then
  STRUCTURAL=$(git diff HEAD~1 --name-status 2>/dev/null | awk '$1 ~ /^(A|D|R)/ {print $NF}' | grep -E "$GOVERNED_ROOTS")
  WATCHED=""
  [ -n "${REF_WATCH:-}" ] && WATCHED=$(echo "$CHANGED" | grep -E "$REF_WATCH")
  if [ -n "$STRUCTURAL" ] || [ -n "$WATCHED" ]; then
    if ! echo "$CHANGED" | grep -qE '^\.claude/skills/.*/references/'; then
      warn "Reference Sync: reference-worthy source changed (structural or watched paths) but no reference files updated — verify Reference Sync is complete"
    fi
  fi
fi

# Check 2 — deploy drift
if [ -n "$DEPLOY_PATHS" ] && echo "$CHANGED" | grep -qE "$DEPLOY_PATHS"; then
  if ! echo "$CHANGED" | grep -qE '^\.claude/skills/.*/references/deploy-config\.yaml$'; then
    warn "Deploy Profile: deploy-mechanism paths (\$DEPLOY_PATHS) changed but deploy-config.yaml was not updated — invoke the deploy-owning skill to reconcile"
  fi
fi

# Check 3 — dependency drift
if [ -n "${DEPENDENCY_MANIFESTS:-}" ] && echo "$CHANGED" | grep -qE "$DEPENDENCY_MANIFESTS"; then
  if ! echo "$CHANGED" | grep -qE '^\.claude/skills/.*/references/vex\.yaml$'; then
    warn "Advisory triage: dependency manifests changed but vex.yaml was not updated — run /audit; rank by what the new package parses or fetches, not by severity"
  fi
fi

# Check 4 — copy: em dashes on added, non-comment lines in user-facing source
if [ -n "${COPY_PATHS:-}" ]; then
  COPY_FILES=()
  while IFS= read -r f; do COPY_FILES+=("$f"); done < <(echo "$CHANGED" | grep -E "$COPY_PATHS")
  if [ ${#COPY_FILES[@]} -gt 0 ]; then
    HITS=$(git diff HEAD~1 -U0 -- "${COPY_FILES[@]}" 2>/dev/null \
      | grep -E '^\+[^+]' | grep '—' \
      | grep -cvE '^\+[[:space:]]*(//|#|\*|/\*|<!--|\{/\*)')
    if [ "${HITS:-0}" -gt 0 ]; then
      warn "Voice: $HITS added line(s) in user-facing source carry an em dash. Rewrite them per <PREFIX>-design/references/voice.md rule 3 (comment lines are already skipped)"
    fi
  fi
fi

[ -n "$WARNINGS" ] && jq -n --arg m "$WARNINGS" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
exit 0
```

---

## § skill-mark.sh

Records each invoked skill to a session-scoped marker file. Used by `skill-guard.sh`, `dependency-guard.sh`, and `package-edit-guard.sh` to verify a skill was loaded, and by `<PREFIX>-log` to derive the delivery log's `**Skills:**` field. The marker key must match the guards' derivation exactly: session id alone.

**Do not key this per agent.** Subagents inherit the parent's `transcript_path`, so `basename "$TRANSCRIPT"` returns the session id itself — a per-agent suffix is provably always equal to the session id (verified across 12 real markers on a machine that had run `/code`, `/fix` and `/pilot` pipelines: every filename's two halves were identical). Session scope is also what makes the `Skills:` derivation work at all, since `<PREFIX>-review` and `<PREFIX>-debug` only ever load inside subagents.

```bash
#!/bin/bash
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
[ -z "$SKILL" ] && exit 0
echo "$SKILL" >> "/tmp/<PREFIX>-skills-${SESSION_ID}"  # session-scoped — see skill-guard.sh
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

jq -n '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: "📋 Commit complete — run <PREFIX>-log to append an entry to docs/project-log.md"}}'

exit 0
```

---

## § agent-mark.sh

Fires on `SubagentStop` for the four pipeline agents. Two jobs, both things prose could only ask for: it **records** every child that finished to a session-scoped marker (`agent_type`, `subagent_id`, and whether its last message carried a `## Handoff` block) — the deterministic count a close-out checks `Fanned out:` totals against, and the evidence the salvage protocol reads instead of guessing whether an agent returned — and it **blocks once** when a pipeline agent tries to stop without the block, telling it to end with the handoff. Once: the marker records the block, and a second stop from the same `subagent_id` is let through, so a genuinely stuck agent costs one extra turn, never a loop. The hook is evidence for salvage, not a replacement for it — `last_assistant_message` is truncated at 10,000 characters, and a very long final message could hide a real block from the grep, which is one more reason the second stop always passes.

```bash
#!/bin/bash
# SubagentStop hook — records pipeline-agent stops; blocks once on a missing ## Handoff block.
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)
SUB_ID=$(echo "$INPUT" | jq -r '.subagent_id // .agent_id // "unknown"' 2>/dev/null)
MARKER="/tmp/<PREFIX>-agents-${SESSION_ID}"   # session-scoped — same derivation as skill-mark.sh

HAS_HANDOFF=no
echo "$INPUT" | jq -r '.last_assistant_message // ""' 2>/dev/null | grep -q '^## Handoff' && HAS_HANDOFF=yes

if [ "$HAS_HANDOFF" = no ] && ! grep -q "^${TYPE} ${SUB_ID} blocked" "$MARKER" 2>/dev/null; then
  echo "${TYPE} ${SUB_ID} blocked $(date -u +%FT%TZ)" >> "$MARKER"
  jq -n '{decision: "block", reason: "End your turn with the ## Handoff block from your Response Requirements — the caller machine-reads it, and a return without it parks the pipeline."}'
  exit 0
fi

echo "${TYPE} ${SUB_ID} ${HAS_HANDOFF} $(date -u +%FT%TZ)" >> "$MARKER"
exit 0
```

---

## § pilot-cleanup.sh

Fires on `SessionEnd`. Removes `.claude/pilot/running` **only when the marker names this session, and never on a `/resume` switch** (the event fires with `reason: resume` while the old session's subagents may still be running) — `/pilot` Step 0 writes the session id (`$CLAUDE_CODE_SESSION_ID`, which the Bash tool exposes) as the marker's second line. Concurrent sessions in one repo are normal, so a plain removal would delete another mission's marker and let two runs commit into one tree. A marker another session owns is left for its own session end, or for `/pilot`'s 6-hour staleness rule. Output is ignored on this event by design; it is cleanup, not a message.

```bash
#!/bin/bash
# SessionEnd hook — clears this session's own /pilot run marker.
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
[ "$(echo "$INPUT" | jq -r '.reason // empty' 2>/dev/null)" = "resume" ] && exit 0   # switching conversations is not ending the run
MARKER="${CLAUDE_PROJECT_DIR:-.}/.claude/pilot/running"
[ -f "$MARKER" ] || exit 0
OWNER=$(sed -n 2p "$MARKER" 2>/dev/null)
[ "$OWNER" = "$SESSION_ID" ] && rm -f "$MARKER"
exit 0
```

---

## § limit-mark.sh

Fires on `StopFailure` with matcher `rate_limit` — only that: an `overloaded` 529 is transient and a retry succeeds, so recording it here would make Step 0 resume a run that never died. The turn that an allowance limit kills is the one no agent can report, so this hook writes the fact where the next `/pilot` Step 0 and `/whats-up`'s store row read it: `.claude/pilot/limit-hit`, three lines — timestamp, session id, `error_type` verbatim. A `running` marker older than a `limit-hit` from the same session is a run the limit killed, which Step 0 then **resumes instead of waiting six hours for the marker to age out**. The `error_type` line also answers a question the docs leave open — whether a claude.ai usage limit arrives as `rate_limit` — the first time one lands. Output is ignored on this event; the file is the whole effect.

```bash
#!/bin/bash
# StopFailure hook — records a limit-killed turn for /pilot and /whats-up.
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
ERR=$(echo "$INPUT" | jq -r '.error_type // "unknown"' 2>/dev/null)
DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/pilot"
mkdir -p "$DIR" 2>/dev/null || exit 0
printf '%s\n%s\n%s\n' "$(date -u +%FT%TZ)" "$SESSION_ID" "$ERR" > "$DIR/limit-hit"
exit 0
```

---

## § settings.json

Wire all 12 hook scripts — 14 entries, since `skill-guard.sh` sits under both `Edit` and `Write` and `pre-handoff-check.sh` under both `Skill` and `Task|Agent`. If the file already exists, merge the `hooks` key without removing unrelated settings. Timeout unit: **seconds**. The `Task|Agent` matcher is what makes `pre-handoff-check.sh` fire when qa is spawned as a subagent — without it the gate never runs in the pipeline. The `SubagentStop` matcher names the four pipeline agents so a research fork or an Explore child never gets blocked for lacking a handoff block.

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
    ],
    "SubagentStop": [
      {
        "matcher": "<PREFIX>-dev|<PREFIX>-qa|<PREFIX>-pm|<PREFIX>-verify",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/agent-mark.sh", "timeout": 5 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pilot-cleanup.sh", "timeout": 5 }
        ]
      }
    ],
    "StopFailure": [
      {
        "matcher": "rate_limit",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/limit-mark.sh", "timeout": 5 }
        ]
      }
    ]
  }
}
```
