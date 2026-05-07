# dev-workflow

A multi-agent delivery workflow for Claude Code. Two commands — `/dev-workflow:install` and `/dev-workflow:upgrade` — bootstrap a full AI-assisted dev pipeline on any project: agents, domain skills, enforcement hooks, slash commands, and a living roadmap.

> Agent and skill names are prefixed with a name you choose during setup (e.g. `myapp`). Examples below use `myapp`.
>
> **Claude Code only.**

---

## What it installs

| Component | What it does |
|---|---|
| `myapp-dev` | Implements features. Loads domain skills, writes code, deploys non-prod, syncs reference docs, appends roadmap entries. Returns a structured `## Handoff` block. |
| `myapp-qa` | Reviews and tests. Gates on `myapp-review` + `myapp-test` before sign-off. Routes code-fix requests back to `myapp-dev` (never self-patches). |
| `myapp-pm` | Process gate. Verifies QA via the handoff block, deploys prod (if declared), writes delivery log, updates docs, advances roadmap status. |
| 7 lifecycle skills | `log`, `review`, `debug`, `deploy`, `test`, `skill`, `docs` — one per delivery concern |
| Domain skills | One per source directory — own their paths, carry reference files, and define quality checklists (tests, lint, type check) that `myapp-dev` runs before deploying |
| 8 hooks | Enforce skill loading, block bad installs, guard pre-handoff, warn on missing ref-sync |
| `/code`, `/fix` | Full pipeline: dev → qa → pm with confirmation step. Parses handoff blocks; re-runs qa with `mode=retest` after dev fixes. |
| `/design` | Generate 2–3 HTML variants, open in browser, route chosen direction to `/code` *(conditional on design skill)* |
| `/roadmap` | Read `docs/roadmap.md`, rank by priority, pick next item to work |
| `/wrap` | Close-out for ad-hoc work outside the `/code` or `/fix` pipelines — runs `myapp-log` + `myapp-docs` + `myapp-skill` reference sync |
| `docs/roadmap.md` | Source of truth for open scope — auto-updated by agents |
| `docs/project-log.md` | Delivery history |

---

## Prerequisites

- Claude Code (`claude`) installed and authenticated
- A git repo (recommended — hooks use `git status`)
- `jq` on PATH (used by hook scripts)
- [`agent-browser`](https://github.com/vercel-labs/agent-browser) plugin installed — used by `<PREFIX>-test` for E2E browser automation
- [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill installed — used by `<PREFIX>-skill` to author and update skills
- [`frontend-design`](https://github.com/anthropics/skills/tree/main/skills/frontend-design) skill installed — used by `<PREFIX>-design` for generating HTML variants *(conditional: only if a design skill is installed; can be replaced with any design skill — update the reference in `<PREFIX>-design/SKILL.md` after install)*

---

## Install (fresh project)

**1. Add the marketplace and install the plugin:**
```
/plugin marketplace add lalec/agent-plugins
/plugin install dev-workflow@agent-plugins
```

**2. Navigate to your project root and run:**
```
/dev-workflow:install
```

The `install` command aborts cleanly if it detects an existing dev-workflow install — use `/dev-workflow:upgrade` instead in that case.

**3. Answer two questions:**
- Your preferred prefix (e.g. `myapp` → `myapp-dev`, `myapp-qa`, `myapp-backend`)
- Confirm the proposed domain skill → path mapping

Everything else is written automatically.

---

## Upgrade (existing install)

When this plugin updates with new templates or workflow improvements, run:

```
/dev-workflow:upgrade
```

The upgrade is idempotent. It captures your existing prefix and skills, presents a gap-diff checklist of every fix that the latest templates would apply, waits for your confirmation, then applies only the confirmed fixes.

---

## Daily workflow

### Implement a feature
```
/code add CSV export to the assessment list
```
Runs: `myapp-dev` → `myapp-qa` → `myapp-pm`

### Fix a bug
```
/fix pipeline table takes too long to load
```
Runs: `myapp-debug` → `myapp-dev` → `myapp-qa` → `myapp-pm`

### Design a UI feature *(if design skill installed)*
```
/design redesign the onboarding flow
```
Generates 2–3 HTML variants, opens in browser, routes chosen direction to `/code`.

### Pick the next roadmap item
```
/roadmap
```
Reads `docs/roadmap.md`, ranks by priority, presents top 3, routes to `/code` or `/fix`.

### Wrap up ad-hoc work
```
/wrap <description of what changed>
```
Close-out for changes made outside the `/code`/`/fix` pipelines — manual data fixes, config changes, ad-hoc edits. Runs `myapp-log` + `myapp-docs` + `myapp-skill` reference sync to ensure the audit trail and references stay consistent.

---

## How the hooks enforce correctness

| Hook | Fires on | Blocks if |
|---|---|---|
| `skill-guard.sh` | Edit / Write | Editing an owned path without the owning skill loaded |
| `path-coverage-check.sh` | Write | New file in a governed root with no matching PATH_MAP entry |
| `dependency-guard.sh` | Bash | `pnpm add` / `pip install` without `myapp-skill` loaded |
| `package-edit-guard.sh` | Edit | Adding packages to `package.json` directly without `myapp-skill` |
| `pre-handoff-check.sh` | Skill | Invoking `myapp-qa` with uncommitted changes, lint errors, or type errors |
| `ref-sync-check.sh` | Bash (post) | Warns after commit if governed source paths changed without reference updates, or if deploy-mechanism paths changed without `deploy-config.yaml` updates. Path patterns sourced from `governed-paths.conf`. |
| `skill-mark.sh` | Skill (post) | Records loaded skills to session marker (used by all guards) |
| `post-commit.sh` | Bash (post) | Reminds to run `myapp-log` after every commit |

All path→skill ownership lives in one file: `.claude/hooks/governed-paths.conf`. Edit there to add or change ownership — hooks pick it up automatically.

---

## Roadmap format

`docs/roadmap.md` entries follow this structure:

```
### Entry title
**Category:** improvement | dogfood | integration | tech-debt
**Priority:** high | medium | low
**Status:** open | in-progress | done · YYYY-MM-DD
**Added:** YYYY-MM-DD HH:MM
```

- `myapp-dev` appends new entries autonomously during implementation
- `myapp-pm` flips status to `in-progress` or `done` after delivery

---

## Verify the install

Run these smoke tests after install:

```bash
# 1. Skill gate — should block
# Try editing a file in an owned path (e.g. src/) without loading the domain skill
# Expected: "Skill gate: ... is owned by myapp-backend — invoke it first"

# 2. Dependency gate — should block
pnpm add some-package
# Expected: "Dependency gate: ... invoke myapp-skill first"

# 3. Pre-handoff gate — should block
# Make a change without committing, then invoke myapp-qa
# Expected: "Pre-handoff gate: uncommitted changes detected"
```

---

## Customising after install

| Change | How |
|---|---|
| Add a new domain (new source dir) | Invoke `myapp-skill` — it owns the `governed-paths.conf` lifecycle |
| Change path→skill ownership | Edit `.claude/hooks/governed-paths.conf` directly |
| Add a reference file to a skill | Invoke the domain skill — it manages its own `references/` |
| Update `docs/workflow.md` | Invoke `myapp-docs` |
