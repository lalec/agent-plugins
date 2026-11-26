# Hook Templates

Claude Code only.

Replace these placeholders before writing the files:
- `<PREFIX>` → the chosen skill/agent prefix
- `<GOVERNED_ROOTS>` → ERE alternation of **actual top-level source/asset directories** (see § How to generate for an example). Must be directory prefixes — **never extension globs** like `.*\.(html|css|js)$`, which match files outside the project dir (e.g. `/tmp/`) and defeat the guard. Root-level files (e.g. `index.html`) are owned via PATH_MAP entries, not GOVERNED_ROOTS. Sourced from the Frontend, Backend, Database/storage, Auth, Observability, and Third-party SDK categories discovered in Phase 1c.
- `<DEPLOY_PATHS>` → ERE alternation of paths and root-level files belonging to the IaC, CI/CD, Build tooling, and Deployment scripts/config categories (see § How to generate for an example). May be the empty string `''` if no such categories were discovered (in which case `ref-sync-check.sh` simply skips its deploy-drift check). Folder names are signal-derived, not name-baked — whatever names the project actually uses.
- `<PATH_MAP_ENTRIES>` → generated entries from § How to generate governed-paths.conf
- `<SKILL_SELF_OWNERSHIP_ENTRIES>` → one `'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'` entry per installed skill (lifecycle + domain), so each skill edits its own SKILL.md and `references/` with itself loaded — without these, a domain skill's own reference updates get blocked for lacking `<PREFIX>-skill`
- `<REF_WATCH>` → optional ERE alternation of reference-worthy source files (API route/handler dirs, schema/model files, auth middleware) derived from the category map. Used by `ref-sync-check.sh` to decide whether a modify-only commit warrants a reference-sync warning. `''` when nothing clearly reference-worthy is identifiable — structural changes (add/delete/rename) in governed roots always warn regardless
- `<DEPENDENCY_MANIFESTS>` → optional ERE alternation of the project's dependency manifests, matched by **filename, not layout** — `requirements*.txt`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Gemfile` and their lock files, whichever of them this project actually has. Read by the dependencies security slot (`paths: '$DEPENDENCY_MANIFESTS'` in `scanners.yaml`), so a manifest change runs the dependency scan at task review. `''` when the project has none (the check is then silently skipped)
- `<COPY_PATHS>` → optional ERE of the directories holding this project's **user-facing** source — the Frontend category's paths, only when a `<PREFIX>-design` skill is installed. Used by `ref-sync-check.sh` to warn when a commit adds an em dash to a user-readable string. `''` when there is no design skill (the check is then silently skipped)
- `<UNATTENDED_DENY>` → ERE alternation of the paths an **unattended** `/pilot` run must never touch: `DEPLOY_PATHS` plus the Auth category's paths from `CATEGORY_MAP`, plus a migrations directory when one was discovered under Database/storage. Nobody is present to notice a change there, so a task whose paths intersect it is skipped and reported, never started unattended. When the auth paths are unknown, set it to the `DEPLOY_PATHS` value and say so — the project widens it.
- `<LINT_CMD>` → project lint command (e.g. `pnpm exec biome check .` or `npm run lint`)
- `<TYPECHECK_CMD>` → project typecheck command (e.g. `pnpm exec tsc --noEmit` or `npm run typecheck`)
- `<LINT_SCOPE>` / `<TYPECHECK_SCOPE>` → the directory each command checks, with a trailing slash (the component's root); `''` when it checks the whole repo

**Hook conduct rules (apply to every script below):**
- *Gates* (skill-guard, path-coverage, dependency-guard, package-edit-guard, pre-handoff, close-out-gate, paid-meter) exit 2 with an actionable message on violation, 0 otherwise. `agent-mark` and `pilot-continue` are the gates on lifecycle events: each blocks a stop through `decision: block` JSON (exit codes carry no meaning on `SubagentStop` or `Stop`), and only once in a row.
- *Lifecycle recorders* (pilot-cleanup on `SessionEnd`, limit-mark on `StopFailure`) write a file and exit 0; Claude Code ignores their output entirely, so the file is their whole effect. `precompact-handover` on `PreCompact` is a recorder outside a `/pilot` run and a gate inside one: exit 2 skips an automatic compaction until the run reaches a task boundary.
- *Messages* a hook prints are plain text inside double quotes: name a command in single quotes ('ruff check'), never in unescaped backticks — the shell runs a backticked word as a command, so the message breaks the hook exactly when it fires. This holds for every line install writes into a hook, project-specific messages included.
- *Folder*: a hook starts in the session shell's current folder, wherever the session last `cd`-ed — not the repo root. A hook that runs a command by a relative path changes to the repo root first. Measured: a session left in a subfolder failed a passing build at the QA gate twice.
- *Recorders* (ref-sync-check, skill-mark, post-commit, scan-due) must **always exit 0** — a recorder that exits non-zero makes successful commands surface as errors and burns a reasoning turn. A recorder with something to tell the model prints it as `hookSpecificOutput.additionalContext` JSON on stdout. Stderr from a hook that exits 0 goes to the debug log only, so a warning written there reaches neither the model nor the user.

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
# rather than layout. The dependencies security slot runs at task review when one changes
# (scanners.yaml paths: '$DEPENDENCY_MANIFESTS'). '' = no manifests.
#
# COPY_PATHS: optional ERE of user-facing source (the Frontend category, when <PREFIX>-design exists).
# ref-sync-check.sh warns when a commit adds an em dash on a non-comment line there. '' = skipped.
#
# PAID_* — tests that spend money outside Claude (the app's own model calls, cloud runs). Read by
# paid-meter.sh and pre-handoff-check.sh; derived, never asked (§ How to generate). How each was
# derived goes in a comment above it.
# PAID_USAGE_CMD: read-only command printing one '<unit> <N>' line per capped unit — 0 when nothing
#   ran today — for the test target only. '' = not declared yet (reports say unmetered); 'none' = tests
#   spend nothing. A capped unit with no line reads as unreadable.
# PAID_DAILY_CAP: '<unit>:<N>' per unit PAID_USAGE_CMD prints; at or over it, paid commands stop.
# PAID_COMMANDS: ERE per paid entry point, matching the launcher that runs it plus the script — never the
#   bare name, or `git add`, `cat` and a commit message naming the script would count as paid.
# PAID_FULL_FORMS: '<match ERE>!<sample ERE>' — a paid set run in full: matches the first, not the second.

GOVERNED_ROOTS='<GOVERNED_ROOTS>'
DEPLOY_PATHS='<DEPLOY_PATHS>'
REF_WATCH='<REF_WATCH>'
DEPENDENCY_MANIFESTS='<DEPENDENCY_MANIFESTS>'
COPY_PATHS='<COPY_PATHS>'
UNATTENDED_DENY='<UNATTENDED_DENY>'
PAID_USAGE_CMD='<PAID_USAGE_CMD>'
PAID_DAILY_CAP=(<PAID_DAILY_CAP>)
PAID_COMMANDS=(<PAID_COMMANDS>)
PAID_FULL_FORMS=(<PAID_FULL_FORMS>)

PATH_MAP=(
  '^docs/roadmap\.md$:EXEMPT'
  '^docs/project-log\.md$:EXEMPT'
  '^\.claude/skills/<PREFIX>-test/references/custom-tests\.yaml$:EXEMPT'
  '^\.claude/skills/<PREFIX>-review/references/vex\.yaml$:EXEMPT'
  '^\.claude/skills/<PREFIX>-review/references/scan-baseline\.txt$:EXEMPT'
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
PAID_USAGE_CMD='none'   # discovery: no test calls a paid service
PAID_DAILY_CAP=()
PAID_COMMANDS=()
PAID_FULL_FORMS=()

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
- **`PAID_*` are derived, never asked** — at install Phase 2 and by the upgrade item, attended or `--yes` alike. The project gives no number and types no flag; it can edit the result afterwards.
  - *Paid services and entry points:* read deploy-config, the infra code and the test scripts for every service the **test target** calls that bills per use (a hosted model, a metered cloud API, a deployed agent runtime), and every command that reaches one — test sets, live-walk scripts, direct invocations. Each becomes a `PAID_COMMANDS` ERE that matches **running** it — the interpreter or launcher and the script, `(^|[;&|] *)<launcher>[^;&|]* <script>` — never the bare script name, which also matches `git add`, `cat` and a commit message that mentions it, and would refuse dev's own commit. None found → `PAID_USAGE_CMD='none'` and the arrays empty.
  - *Full forms:* a paid set that runs many paid calls per invocation gets a `PAID_FULL_FORMS` entry — its command, and the option that narrows it to chosen cases as the sample marker. A set with no such option gets no entry; file a roadmap item to add one, since until then every run is a full run.
  - *Usage command:* a read-only provider query that prints today's usage of the test target as one `<unit> <N>` line per capped unit, `0` when nothing ran — the provider's near-real-time metrics, never its billing export, which lags a day. Scope it to what tests use (the test environment, account, or tag), or ordinary traffic trips the cap. Prove it through the hook: `bash .claude/hooks/paid-meter.sh --read --fresh` must print `ok` (or `over`); anything else → leave `PAID_USAGE_CMD=''` and report `unmetered` with what it printed. It runs in the hook's bare shell (`§ pre-handoff-check.sh` Bare-shell rule).
  - *Cap:* query the last 14 days of the same usage and set each unit's cap to 2× the median day, floored at **three** full runs of every declared paid set — one task's worst case (the sign-off pass plus two fix cycles), so a task can always finish. No history → the floor. Write the derivation (`# 2x median of 14 days = <N>`) as a comment above `PAID_DAILY_CAP`.
- `paid-meter.sh` fires on Bash **mid-task**, unlike `UNATTENDED_DENY`: an edit can be reverted, money spent cannot, so the guard sits where the spend happens.
- The entry-point skills (`code`, `fix`, `pilot`, … — the fixed names in `preflight.md § Where the entry points live`) are `OPEN`, exactly as `.claude/commands/` always was: they are commands in Rules 1–2's sense and no lifecycle skill owns them. The entry sits **before** the `.claude/skills/` catch-all, or every edit to one would demand `<PREFIX>-skill` loaded.
- `.claude/pilot/` is always `EXEMPT` and gitignored whole — `/pilot` writes its run markers there at the top level and the lifecycle hooks write `limit-hit`; nothing in it is tracked. (Legacy note, kept so a grep finds it: the directory once held a tracked `shift.sh`, a verbatim plugin copy that no skill authors
- `<PREFIX>-test/references/custom-tests.yaml` is always `EXEMPT` — the `/code`/`/fix` Step 1.5 persist step writes it at the top level and carries the schema itself; gating it forces a full skill load per pipeline run for a 10-line append
- `<PREFIX>-review/references/vex.yaml` and `scan-baseline.txt` are always `EXEMPT` — the review writes a status from inside `<PREFIX>-qa`, `/audit` and the ship step write them at the top level, and `scan.py` treats a commit touching only `EXEMPT` paths as no change to rescan, and `<PREFIX>-review` is a read-only reference skill that owns no write path of its own
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

Blocks invocation of `<PREFIX>-qa` if the working tree has uncommitted changes, or lint or typecheck fails for a part of the project the task changed — the paths on the dispatch's `Changed paths:` line that git also reports changed in the unpushed range (the list is trusted as written, so a file dev left off it is not checked), else every unpushed commit — and blocks **every** pipeline-agent dispatch while `.claude/pilot/stop` exists, so a stop dropped from a phone lands at the next subagent boundary, and every dev/qa/verify dispatch while today's paid usage is over its cap (`§ paid-meter.sh`), which stops paid calls no `PAID_COMMANDS` pattern recognises. Enforces commit-before-review and clean-code gates mechanically. **Must match both invocation paths:** the Skill tool (`tool_input.skill`) *and* an Agent/Task spawn (`tool_input.subagent_type`) — in the pipeline qa is spawned as a subagent, so a Skill-only match makes this gate dead code. It also stamps the time of every agent dispatch in `.claude/pilot/dispatched`, which `precompact-handover.sh` compares with the run's newest handover to tell a task boundary from a task in flight.

```bash
#!/bin/bash
# PreToolUse Skill+Task hook — blocks <PREFIX>-qa invocation if work isn't committed, lint fails, or types fail.

INPUT=$(cat) || exit 0
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null)

# Stamp every agent dispatch: precompact-handover.sh lets a /pilot run compact only once its own
# handover is newer than this, so no compaction lands between a dispatch and the task's boundary.
case "$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)" in
  Task|Agent) [ -d "${CLAUDE_PROJECT_DIR:-.}/.claude/pilot" ] && date +%s > "${CLAUDE_PROJECT_DIR:-.}/.claude/pilot/dispatched" ;;
esac

# A stop file refuses every pipeline-agent dispatch: a /pilot stop dropped mid-task lands at the next
# subagent boundary instead of the next task boundary. The run deletes the file when it honours it.
STOP="${CLAUDE_PROJECT_DIR:-.}/.claude/pilot/stop"
if [ -f "$STOP" ] && [ -n "$AGENT_TYPE" ] && echo "$AGENT_TYPE" | grep -qE '^<PREFIX>-(dev|qa|pm|verify)$'; then
  echo "Stop gate: .claude/pilot/stop exists ($(head -1 "$STOP")) — no further agent is dispatched; close out the run, which removes the file." >&2
  exit 2
fi

# Paid cap: no agent that can spend is dispatched while today's paid usage is over its cap.
if [ -n "$AGENT_TYPE" ] && echo "$AGENT_TYPE" | grep -qE '^<PREFIX>-(dev|qa|verify)$' \
   && [ "$("$(dirname "$0")/paid-meter.sh" --read | head -1)" = over ]; then
  echo "Paid cap gate: today's paid usage is over its cap — no agent that can spend is dispatched; park the task (reason 'paid cap: …') and close out." >&2
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

# Files the task changed: the qa dispatch's `Changed paths:` line (the dev handoff's list, trusted as written),
# kept only where git agrees the file changed in the unpushed range — so another session's commit never fails
# this task's checks. The list can only narrow git's own list, never add to it; a file the task changed but did not
# list skips these checks and is still read by the QA review. No line, or nothing on it git agrees with: the whole range, against the upstream, else
# origin's default branch. Empty when nothing resolves — then every check runs.
BASE=$(git rev-parse -q --verify '@{upstream}' 2>/dev/null || git rev-parse -q --verify origin/HEAD 2>/dev/null)
CHANGED=$([ -n "$BASE" ] && git diff --name-only "$BASE"...HEAD 2>/dev/null)
TOP=$(git rev-parse --show-toplevel 2>/dev/null)
LISTED=$(echo "$INPUT" | jq -r '.tool_input.prompt // empty' 2>/dev/null | sed -n 's/^[[:space:]]*Changed paths:[[:space:]]*//p' | head -1 \
  | tr -d '\140' | tr ', ' '\n\n' | sed -e "s#^$TOP/##" -e 's#^\./##' | grep -v '^$')
OWN=$([ -n "$CHANGED" ] && [ -n "$LISTED" ] && printf '%s\n' "$CHANGED" | grep -Fx -f <(printf '%s\n' "$LISTED"))
[ -n "$OWN" ] && CHANGED=$OWN
# touches <dir/> — the commits change a file under it ('' = anywhere), or CHANGED is unknown
touches() { [ -z "$CHANGED" ] || printf '%s\n' "$CHANGED" | grep -q "^$1"; }

# The checks below name paths from the repo root; the hook starts wherever the session's shell is.
cd "${TOP:-${CLAUDE_PROJECT_DIR:-.}}" || exit 0

# Run lint check
if touches '<LINT_SCOPE>' && ! <LINT_CMD> > /dev/null 2>&1; then
  echo "Pre-handoff gate: lint check failed — fix lint errors, then retry <PREFIX>-qa." >&2
  exit 2
fi

# Run type check
if touches '<TYPECHECK_SCOPE>' && ! <TYPECHECK_CMD> > /dev/null 2>&1; then
  echo "Pre-handoff gate: type check failed — fix type errors, then retry <PREFIX>-qa." >&2
  exit 2
fi

exit 0
```

**Note:** Replace `<LINT_CMD>` and `<TYPECHECK_CMD>` with the project's actual commands. If the project has no typecheck, remove that block. If lint/typecheck commands aren't known at install time, leave `<fill in>` stubs and prompt the user to fill them in. A project with several components gets **one `if touches '<dir>/' && ! <cmd>` block per component check**, each scoped to the directory it checks — a check of a component the task never changed can only fail for reasons the task cannot fix.

**Self-contained rule.** A gate check must pass with no server running — no dev server, local API or emulator. A build that fetches live data while it builds (a static page generated from an API) is not self-contained: prefer a check that is (the component's lint or typecheck); when that build is the component's only real check, keep it scoped to its component and name the serve-env it needs in its failure message, so a failure reads as "start <env>", not as broken code. Measured: an unscoped frontend build that fetched the local API refused every backend-only task at the QA gate until someone started the backend by hand.

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

## § push-match.sh

Not a hook: a helper the two push gates source, so what counts as a push of this project is decided in one place. `project_push "$CMD"` succeeds only when the command runs `git push` itself — `git` at the start of a command, after `;`, `&&`, `||`, `|`, `(`, an environment assignment or a `srun … --` prefix — so a push quoted inside a message, a `grep` or an `echo` never starts a scan. A push run in another repository — `git -C <dir> push`, or a push after `cd <dir>`, where `<dir>` does not share this project's git directory — is that repository's, so a scratch clone or a sibling repo pushes without this project's gates, while a linked worktree of this project is still gated. A gate whose helper is missing blocks a push and names the file, rather than letting every push through. Install copies it without `chmod +x`; nothing runs it directly.

```bash
# push-match.sh — sourced by security-gate.sh and close-out-gate.sh; not wired as a hook.
# project_push CMD: succeeds when CMD runs `git push` for this project's repository.
# `git` where a command starts: after a separator or a word that runs the next one, past any VAR=value
# prefixes and a `srun NAME --`; then `push` as a whole word. A quoted string that contains `push` is masked first, so
# a mention inside quotes is not a push even after a `(` or `;` (measured: a quoted "(git -C … push" was blocked).
PUSH_RE="(^|[;&|({]|(^|[[:space:]])(then|do|else|time|nohup|exec|command|sudo))[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=(\"[^\"]*\"|'[^']*'|[^[:space:]]*)[[:space:]]+)*(srun [^;&|]*--[[:space:]]+)?git([[:space:]]+-C[[:space:]]+[^[:space:]]+)*[[:space:]]+push([^A-Za-z0-9_-]|\$)"
project_push() {
  local cmd pre cdir cflag dir common here
  cmd=$(printf '%s' "$1" | tr '\n' ';' | sed -E "s/\"[^\"]*push[^\"]*\"/Q/g; s/'[^']*push[^']*'/Q/g")
  echo "$cmd" | grep -qE "$PUSH_RE" || return 1
  # Where the push runs: its `-C <dir>`, taken from the last `cd <dir>` before it.
  # A `cd` inside a subshell that closed before the push does not move the push: drop closed `( … )` groups.
  pre=$(echo "$cmd" | sed -E "s/$PUSH_RE.*//" | sed -E -e ':a' -e 's/\([^()]*\)//' -e 'ta')
  cdir=$(echo "$pre" | grep -oE '(^|[;&|(])[[:space:]]*cd +[^ ;&|)]+' | tail -1 | sed -E 's/.*cd +//')
  cflag=$(echo "$cmd" | grep -oE "$PUSH_RE" | head -1 | grep -oE -- '-C[[:space:]]+[^[:space:]]+' | tail -1 | sed -E 's/-C[[:space:]]+//')
  cdir=${cdir//[\"\']/}; cflag=${cflag//[\"\']/}; cdir=${cdir/#\~/$HOME}; cflag=${cflag/#\~/$HOME}
  case "$cflag" in /*) dir=$cflag ;; "") dir=$cdir ;; *) dir=${cdir:-.}/$cflag ;; esac
  [ -z "$dir" ] && return 0
  # Same repository = same git common dir, so a linked worktree of this project is still this project.
  common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 0   # unresolvable: gate it
  here=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  [ "$common" = "$here" ]
}
```

---

## § security-gate.sh

Blocks a `git push`, and a `<PREFIX>-deploy` call with `target=prod`, until the security slots have run on everything about to ship and every finding has a decision — so a scan cannot be skipped by forgetting it. The hook runs `<PREFIX>-review/scripts/scan.py gate`, which reuses a ship run of each tool slot that already covers `origin/HEAD..HEAD`, runs the missing ones in parallel, and exits 2 while a slot errored twice, a new finding has no `vex.yaml` statement, a finding that holds is open, or the change review has not recorded a result for governed or deploy paths in the range. What is new and what holds is decided in `scan.py` and `<PREFIX>-review/references/security-review.md`, not here. The hook checks that every finding has a decision, never that the decision is right; the baseline file and the change-review record are written by the session and trusted as written. A project with no remote passes — there is nothing to push to. `CLOSEOUT_OVERRIDE=1 git push …` bypasses the push half only; a prod deploy has no override.

Its `settings.json` Bash entries carry `"if": "Bash(git push*)"`, `"if": "Bash(git -C * push*)"` and `"if": "Bash(srun *)"`, so the hook starts only for a command that may push — the second catches `git -C <dir> push` and the third `srun NAME -- git push`, both of which the first misses (tested on Claude Code 2.1.330: `Bash(srun *)` fires on `srun …`, `cd … && srun …` and `X=1 srun …`, and not on a quoted mention). The filters let through commands that only mention a push or run another `srun` command; `push-match.sh` then passes those. A push spelt another way (`env`, a full path to git, `sh -c`) is not covered: the gate stops a session that forgot the checks, not one avoiding them. Dropping the filters would not change that, and it would run both gates on every Bash call — measured at about 85 ms each. Each carries `"onFailure": "block"`, so a crash or a timeout blocks the push instead of letting it through (Claude Code lets a failed hook's call proceed otherwise); `scan.py` keeps a slot's two tries under the 600-second timeout. The Skill entry has no `onFailure`, so a broken hook cannot block every skill. It cannot be narrowed to the deploy skill instead: tested on Claude Code 2.1.327, an `if` of `Skill(<name>)` never fires, and only `Skill(*)` or a bare `Skill` does, for every skill. Callers therefore run § Before ship before a prod deploy call, since this hook runs before the deploy skill loads.

```bash
#!/bin/bash
# PreToolUse Bash + Skill hook — a push or prod deploy waits for the security slots (scan.py gate).
INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)
ARGS=$(echo "$INPUT" | jq -r '.tool_input.args // empty' 2>/dev/null)
if [ -n "$CMD" ]; then
  if ! . "$(dirname "$0")/push-match.sh" 2>/dev/null; then
    echo "$CMD" | grep -qE "git( +-C +[^ ]+)* +push" || exit 0
    echo "Push gate: .claude/hooks/push-match.sh is missing, so no push can be checked — restore it (git checkout -- .claude/hooks/push-match.sh) or re-run /dev-workflow:upgrade." >&2
    exit 2
  fi
  project_push "$CMD" || exit 0
  echo "$CMD" | grep -qE "CLOSEOUT_OVERRIDE=1" && exit 0
elif [ "$SKILL" = "<PREFIX>-deploy" ]; then
  echo "$ARGS" | grep -qiE "target[[:punct:][:space:]]*prod" || exit 0
else
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-.}"
[ -z "$(git -C "$ROOT" remote 2>/dev/null)" ] && exit 0   # nothing to push to
cd "$ROOT" && python3 .claude/skills/<PREFIX>-review/scripts/scan.py gate && exit 0
echo "Fix what is listed, per <PREFIX>-review/references/security-review.md § Before ship.${CMD:+ Emergency override for a push only: CLOSEOUT_OVERRIDE=1 git push …}" >&2
exit 2
```

---

## § ref-sync-check.sh

Warns after `git commit` when paths watched in `governed-paths.conf` changed without corresponding reference file updates, or when user-facing copy broke a mechanical voice rule. Three independent checks:

1. **Source drift** — warns only on commits that plausibly change what references describe: files **added/deleted/renamed** in `GOVERNED_ROOTS`, or modified files matching `REF_WATCH` (contracts, schemas, auth). Modify-only cosmetic commits (copy tweaks, style nudges) stay silent — an alarm that fires on every commit gets learned as ignorable and loses all signal.
2. **Deploy drift** — `DEPLOY_PATHS` changed without `deploy-config.yaml` being touched → the deploy profile is now stale.
3. **Copy** — a line **added** under `COPY_PATHS` carries an em dash and is not a comment → a user-readable string breaks `voice.md` rule 3. Warn, never block: a gate would fire on the first edit to a line that already had one, in a project that has hundreds. The rest of `voice.md` is judgment, checked at review, not here.

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

# Check 3 — copy: em dashes on added, non-comment lines in user-facing source
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

Blocks `git push` while commits after the last delivery-log entry touch governed or deploy paths — the iterate lane's teeth: work and commit freely all day, but nothing leaves the machine without one batched close-out (`/tweak` exit, `/wrap`, or the pipeline's pm step, all of which commit a log entry). Emergency override: `CLOSEOUT_OVERRIDE=1 git push …`. It acts only on a push of this project (`push-match.sh`), so its `settings.json` entries carry the same three `if` filters as `security-gate.sh`.

```bash
#!/bin/bash
# PreToolUse Bash hook — blocks git push when governed commits lack delivery-log coverage.

INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0
if ! . "$(dirname "$0")/push-match.sh" 2>/dev/null; then
  echo "$CMD" | grep -qE "git( +-C +[^ ]+)* +push" || exit 0
  echo "Push gate: .claude/hooks/push-match.sh is missing, so no push can be checked — restore it (git checkout -- .claude/hooks/push-match.sh) or re-run /dev-workflow:upgrade." >&2
  exit 2
fi
project_push "$CMD" || exit 0
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

## § pilot-continue.sh

Fires on `Stop`, the end of every main-session turn. A `/pilot` run is a chain of short turns: each dispatches a background agent and ends, and the agent's completion wakes the next. The chain breaks when a turn ends with nothing in flight — measured: the built-in `security-review` skill's instructions make its report the turn's final reply, the orchestrator ran it inline with no agent behind it, and the run sat idle 5½ hours with 10 of 17 tasks left. Claude Code hands this hook what tells the two apart: `background_tasks` (in-flight work, each with a `type`) and `session_crons` (scheduled wake-ups). So it blocks **once** when this session owns `.claude/pilot/running`, no `subagent`, `workflow` or `teammate` task is in flight and no wake-up is scheduled — the turn then continues the mission in place, with no timer and no new session. A `shell` or `monitor` task does not count: a dev stack left running would otherwise switch the hook off for the whole run. It never blocks twice in a row (`stop_hook_active`), so a run that truly cannot proceed still ends — and the reason names the two honest ones: an agent that finished while the turn was busy drops out of `background_tasks` before its result is delivered, which happens only after the turn ends (measured: the continued turn said "not received yet", ended, and the result arrived), and a step only a person can give. It does nothing when either field is absent — an older Claude Code that sends neither is unknown, never idle.

It also fires on `SessionStart` with matcher `compact`, the moment a compaction finishes. When this session owns the marker it adds one line to the new context: invoke `proceed` on the newest handover, read `.claude/skills/pilot/references/loop.md`, then continue. A compaction re-attaches the skills a session invoked newest first, each cut at 5,000 tokens and all of them together at 25,000; `/pilot` is invoked once, at the start of a run, so on a long run it is the oldest and the first dropped (measured: two live runs carried 20,000 of its 53,000 characters forward, and neither invoked `proceed`). This line does not depend on what was kept.

```bash
#!/bin/bash
# Stop + SessionStart(compact) hook — keeps this session's /pilot run going: continues a turn that ends
# with nothing in flight to wake it, and points the run back at its loop after a compaction.
INPUT=$(cat) || exit 0
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0
[ "$(sed -n 2p "${CLAUDE_PROJECT_DIR:-.}/.claude/pilot/running" 2>/dev/null)" = "$SESSION_ID" ] || exit 0
if [ "$(echo "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null)" = "SessionStart" ]; then
  jq -n '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: "This session'"'"'s /pilot run is still open (.claude/pilot/running) and a compaction just ran. Before anything else: invoke the proceed skill on the newest .claude/handovers/ file, read .claude/skills/pilot/references/loop.md, then continue the task list from the next task."}}'
  exit 0
fi
[ "$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ] && exit 0
WAKERS=$(echo "$INPUT" | jq -r 'if has("background_tasks") and has("session_crons")
  then ([.background_tasks[] | select(.type == "subagent" or .type == "workflow" or .type == "teammate")] | length) + (.session_crons | length)
  else "unknown" end' 2>/dev/null)
[ "$WAKERS" = "0" ] || exit 0
jq -n '{decision: "block", reason: "This session'"'"'s /pilot run is still open (.claude/pilot/running) and nothing is in flight to wake it: no agent, no workflow, no scheduled wake-up. A report is not the end of the run. Continue from the step you are on: push if the push was next, dispatch the next task, or close out per Step 3, which removes the marker. If a Step 2 stop applies, apply it. Two reasons to end the turn again instead: an agent you launched has not returned its result yet (a result that arrived while you were busy is delivered only after the turn ends), or only a person can give the next step; then say which in one line."}'
exit 0
```

---

## § scan-due.sh

Fires on `SessionStart` for `startup|resume` — not after a compaction or `/clear`, so it speaks once per session — and says when a whole-repository security scan in `<PREFIX>-review/references/scanners.yaml` is past its cadence — so a due scan reaches you every time a session opens, not only when someone thinks to run `/whats-up`. The due rule is `graph.py scans-due`'s, never restated here. It also starts the advisory watch's refresh, detached, when its record is over a day old, and adds the watch's line when it names a critical — so a critical published overnight reaches you when the session opens, while a project with only non-critical advisories hears about them in `/whats-up` and before each task, not at every start. It prints the same line to you (`systemMessage`) and to the model (`additionalContext`), never blocks or waits on the network, and is silent when nothing is due and nothing is critical, when `python3` or the graph script is missing, or when the project has no `scanners.yaml`.

```bash
#!/bin/bash
# SessionStart hook — names every security scan past its cadence (/audit --scan runs them) and a critical advisory.
ROOT="${CLAUDE_PROJECT_DIR:-.}"
DUE=$(cd "$ROOT" && python3 .claude/graph/graph.py scans-due --json 2>/dev/null \
  | jq -r '.due[] | .name + (if .last_run then " (last run " + .last_run + ")" else " (never run)" end)' 2>/dev/null \
  | paste -sd ',' - | sed 's/,/, /g')
WATCH="$ROOT/.claude/skills/<PREFIX>-review/scripts/watch.py"
CRIT=""
if [ -f "$WATCH" ]; then
  (cd "$ROOT" && python3 "$WATCH" refresh --if-older --background >/dev/null 2>&1)
  CRIT=$(cd "$ROOT" && python3 "$WATCH" open --line 2>/dev/null | grep ' critical (')
fi
[ -z "$DUE" ] && [ -z "$CRIT" ] && exit 0
MSG=$( { [ -n "$DUE" ] && echo "Security scan due: $DUE — run /audit --scan"; [ -n "$CRIT" ] && echo "$CRIT"; } | paste -sd '|' - | sed 's/|/ · /')
jq -n --arg m "$MSG" '{systemMessage: $m, hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $m}}'
exit 0
```

---

## § precompact-handover.sh

Fires on `PreCompact`. **Inside this session's `/pilot` run it decides when an automatic compaction may land: only at a task boundary.** A boundary is when the run's own newest handover is newer than the last agent dispatch, which `pre-handoff-check.sh` stamps in `.claude/pilot/dispatched`; the run writes that handover at every boundary from 30% context, so the compaction fires on the request right after it and the summary replaces a context whose state is already in a file. While a task is in flight the hook exits 2, which Claude Code honours: the compaction is skipped and asked again on the next request, with no limit on how often (measured: 21 refusals in a row, then the compaction ran on the first request after the boundary, and the same turn carried on with no input). Claude Code does **not** override the refusal at the hard limit — measured: a session refused at its limit stopped with `Prompt is too long` — so the hook lets the compaction through once this session's context (read from the status-line snapshot) is 80% or more, or cannot be read. Anything else — a manual `/compact`, a subagent's own compaction, a session with no run — is let through as before. A summary Claude Code prepares ahead of time (including idle compaction) asks this hook when it is built, not when it is applied; built at a boundary and applied mid-task, it keeps every message since the boundary word for word — so the summary still ends at a boundary (read from the CLI 2.1.330 bundle, not run live).

Whenever it does not let a boundary compaction through, it writes a **fallback** handover from files alone — git log, status, branch, `.claude/pilot/last-run.json`, the `running` marker — one file per dispatch, overwritten on each refusal, so a compaction that still lands mid-task leaves a record `/proceed` can read. At a boundary it writes none: the run's handover is newer and better, and a fallback written after it would outrank it.

```bash
#!/bin/bash
# PreCompact hook — inside this session's /pilot run an automatic compaction waits for a task boundary
# (the run's handover newer than the last dispatch); otherwise writes a file-derived fallback handover.
INPUT=$(cat) || exit 0
ROOT="${CLAUDE_PROJECT_DIR:-.}"
DIR="$ROOT/.claude/handovers"
SID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRIGGER=$(echo "$INPUT" | jq -r '.trigger // "auto"' 2>/dev/null)
AGENT=$(echo "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null)
STAMP="$ROOT/.claude/pilot/dispatched"
OWN=0; [ -n "$SID" ] && [ "$(sed -n 2p "$ROOT/.claude/pilot/running" 2>/dev/null)" = "$SID" ] && OWN=1
GATE=0; [ "$OWN" = 1 ] && [ "$TRIGGER" = auto ] && [ -z "$AGENT" ] && GATE=1
if [ "$GATE" = 1 ]; then
  RUN_HO=$(ls -t "$DIR"/*.md 2>/dev/null | grep -v '_precompact\.md$' | head -1)
  # Boundary: the run's own handover is newer than the last dispatch — compact now, no fallback.
  [ -n "$RUN_HO" ] && { [ ! -f "$STAMP" ] || [ "$RUN_HO" -nt "$STAMP" ]; } && exit 0
fi
mkdir -p "$DIR" 2>/dev/null || exit 0
# One fallback per dispatch while gated (overwritten on each refusal); one per compaction otherwise.
TS=$(date +%Y-%m-%dT%H%M)
# Inside a run, name the file for the dispatch it covers; otherwise for now.
if [ "$GATE" = 1 ] && [ -f "$STAMP" ]; then
  D=$(cat "$STAMP"); TS=$(date -r "$D" +%Y-%m-%dT%H%M 2>/dev/null || date -d "@$D" +%Y-%m-%dT%H%M 2>/dev/null || echo "$TS")
fi
OUT="$DIR/${TS}_precompact.md"
{
  echo "# Handover — fallback written by precompact-handover.sh ($TRIGGER compaction)"
  echo
  echo "This file was written by a hook from files alone, while a task was in flight or at a compaction the run did not time. If a newer run-written handover exists beside it, prefer that one. Files win over both."
  echo
  echo "## Branch"; git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null
  echo; echo "## Commits (last 10)"; git -C "$ROOT" log --oneline -10 2>/dev/null
  echo; echo "## Working tree"; git -C "$ROOT" status --short 2>/dev/null
  echo; echo "## Held commits"; git -C "$ROOT" rev-list --count @{upstream}..HEAD 2>/dev/null || echo "no upstream"
  if [ -f "$ROOT/.claude/pilot/running" ]; then echo; echo "## Run in flight"; cat "$ROOT/.claude/pilot/running"; fi
  if [ -f "$ROOT/.claude/pilot/last-run.json" ]; then echo; echo "## last-run.json"; cat "$ROOT/.claude/pilot/last-run.json"; fi
  echo; echo "## How to resume"; echo "1. /proceed — then compare this file with git and the delivery log; files win."
} > "$OUT" 2>/dev/null
[ "$GATE" = 1 ] || exit 0
# Near the limit, or context unknown: let it through — Claude Code does not override a refusal at its limit.
CTX=$(CLAUDE_CODE_SESSION_ID="$SID" bash ~/.claude/usage-snapshot.sh --read 2>/dev/null | sed -n 's/^context: \([0-9]*\)% used.*/\1/p')
[ -z "$CTX" ] || [ "$CTX" -ge 80 ] && exit 0
echo "A task is in flight — compaction waits for the next task boundary (the run's next handover)." >&2
exit 2
```
---

## § paid-meter.sh

Fires on every Bash call and stops paid test spend the same day, inside a running task. It reads the project's own usage — `PAID_USAGE_CMD`, cached for 5 minutes in `.claude/pilot/paid-usage` — and refuses a command matching `PAID_COMMANDS` once any unit reaches its `PAID_DAILY_CAP`, or when the usage cannot be read (closed for paid work only). Every other command passes, so git, `run-checks.py record`, the run record and close-out keep working at the cap. It also refuses a `PAID_FULL_FORMS` run from inside `<PREFIX>-dev`: dev iterates on the sample form, and the full set runs at qa's sign-off. Measured: one project's dev agent re-ran a several-hundred-case paid set dozens of times in a day while tuning, and nothing counted it until the monthly bill.

It only reads usage — no counter is written per call, so parallel calls cannot race. A command that starts under the cap runs to its end: one Bash call (a batch, a background script) is the overshoot unit, which is why the cap's floor is three full runs. Ad-hoc paid calls that match no pattern are stopped at the next agent dispatch instead (`§ pre-handoff-check.sh`). `--read` prints the reading — state on the first line, then `<unit> <N>` lines — for `/pilot` and `pre-handoff-check.sh`; `--fresh` re-queries regardless of age.

```bash
#!/bin/bash
# PreToolUse Bash hook — caps paid test usage per day, and keeps paid full runs out of <PREFIX>-dev.
# Also: paid-meter.sh --read [--fresh] prints the reading (ok|over|unreadable|unmetered|none, then usage).
DIR="${CLAUDE_PROJECT_DIR:-.}"
source "$DIR/.claude/hooks/governed-paths.conf" 2>/dev/null || exit 0
CACHE="$DIR/.claude/pilot/paid-usage"

reading() { # $1 = fresh → re-query regardless of age
  [ "$PAID_USAGE_CMD" = none ] && { echo none; return; }
  [ -z "$PAID_USAGE_CMD" ] && { echo unmetered; return; }
  local now ts; now=$(date +%s); ts=$(sed -n 2p "$CACHE" 2>/dev/null)
  local age=$(( now - ${ts:-0} ))
  if [ "$1" = fresh ] || [ "$age" -ge 300 ] || [ "$(date -r "$CACHE" +%F 2>/dev/null)" != "$(date +%F)" ]; then
    mkdir -p "$(dirname "$CACHE")"; local tmp; tmp=$(mktemp "$CACHE.XXXX") || return
    local out state=ok
    if out=$(perl -e 'alarm shift; exec @ARGV' 20 bash -c "$PAID_USAGE_CMD" 2>/dev/null) && [ -n "$out" ]; then
      for c in "${PAID_DAILY_CAP[@]}"; do   # a capped unit with no line is unreadable; over wins
        local used; used=$(printf '%s\n' "$out" | awk -v u="${c%%:*}" '$1 == u {print $2; exit}')
        if [ -z "$used" ]; then [ $state = over ] || state=unreadable
        elif awk -v a="$used" -v b="${c##*:}" 'BEGIN {exit !(a >= b)}'; then state=over; fi
      done
    else state=unreadable; out=; fi
    printf '%s\n%s\n%s\n' "$state" "$now" "$out" > "$tmp" && mv "$tmp" "$CACHE"
  fi
  sed '2d' "$CACHE"
}

if [ "$1" = --read ]; then reading "${2#--}"; exit 0; fi

INPUT=$(cat) || exit 0
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# Dev iterates on samples: a full run from inside <PREFIX>-dev is refused (agent_id = a subagent call).
if [ -n "$(echo "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null)" ] \
   && [ "$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)" = "<PREFIX>-dev" ]; then
  for f in "${PAID_FULL_FORMS[@]}"; do
    if echo "$CMD" | grep -qE -e "${f%%!*}" && ! echo "$CMD" | grep -qE -e "${f#*!}"; then
      echo "Paid gate: this runs a paid set in full — iterate on its sample form (.claude/skills/<PREFIX>-test/references/test-commands.md § Paid); the full set runs once, at qa's sign-off." >&2
      exit 2
    fi
  done
fi

PAID=0
for p in "${PAID_COMMANDS[@]}"; do echo "$CMD" | grep -qE -e "$p" && PAID=1 && break; done
[ $PAID = 1 ] || exit 0

R=$(reading)
case "$(echo "$R" | head -1)" in
  over) echo "Paid cap: today's paid usage reached its cap ($(echo "$R" | sed -n '2,$p' | tr '\n' ' ')/ ${PAID_DAILY_CAP[*]}) — report the verification blocked with reason 'paid cap: …' and park the task; do not retry or work around it." >&2; exit 2 ;;
  unreadable) echo "Paid cap: today's paid usage could not be read (PAID_USAGE_CMD failed or timed out) — paid commands stay closed until it reads; report the verification blocked with reason 'paid cap: usage unreadable'." >&2; exit 2 ;;
esac
exit 0
```

---

## § settings.json

Set `autoCompactWindow` to 450,000 tokens on a 1M-context session model, 90,000 on a 200K one (the installing session's own model decides) — how full a session may get before Claude Code compacts it, kept well under the 80% at which the gate lets a compaction through; inside a `/pilot` run, `precompact-handover.sh` then holds the compaction to the next task boundary — and wire all 17 hook scripts — 25 entries, since `skill-guard.sh` sits under both `Edit` and `Write`, `pre-handoff-check.sh` under both `Skill` and `Task|Agent`, `security-gate.sh` three times under `Bash` (one per push filter) and once under `Skill`, `close-out-gate.sh` three times under `Bash`, and `pilot-continue.sh` under both `Stop` and `SessionStart` (`compact`). If the file already exists, merge the `hooks` key without removing unrelated settings. Timeout unit: **seconds**. The `Task|Agent` matcher is what makes `pre-handoff-check.sh` fire when qa is spawned as a subagent — without it the gate never runs in the pipeline. The `SubagentStop` matcher names the four pipeline agents so a research fork or an Explore child never gets blocked for lacking a handoff block. The secrets hooks are not in this file: they ship with the srun plugin, so they guard projects without dev-workflow too.

```json
{
  "autoCompactWindow": 450000,
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
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/close-out-gate.sh", "if": "Bash(git push*)", "timeout": 10 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/close-out-gate.sh", "if": "Bash(git -C * push*)", "timeout": 10 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/close-out-gate.sh", "if": "Bash(srun *)", "timeout": 10 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/security-gate.sh", "if": "Bash(git push*)", "timeout": 600, "onFailure": "block" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/security-gate.sh", "if": "Bash(git -C * push*)", "timeout": 600, "onFailure": "block" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/security-gate.sh", "if": "Bash(srun *)", "timeout": 600, "onFailure": "block" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/paid-meter.sh", "timeout": 30 }
        ]
      },
      {
        "matcher": "Skill",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pre-handoff-check.sh", "timeout": 60 },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/security-gate.sh", "timeout": 600 }
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
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scan-due.sh", "timeout": 10 }
        ]
      },
      {
        "matcher": "compact",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pilot-continue.sh", "timeout": 5 }
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
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pilot-continue.sh", "timeout": 5 }
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
    ],
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/precompact-handover.sh", "timeout": 10 }
        ]
      }
    ]
  }
}
```
