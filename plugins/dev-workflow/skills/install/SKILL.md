---
name: install
description: Install a 3-agent delivery workflow (dev → qa → pm, domain skills, skill-guard hooks, slash commands, roadmap tracking) on a fresh project. Trigger when the user wants to bootstrap a multi-agent workflow, set up an AI agent pipeline on a new project, add skill-guard hooks, or install the dev-workflow on a fresh repo. Claude Code only.
---

# install

> **Hard gate.** If `.claude/agents/<PREFIX>-dev.md` exists for any prefix, abort and tell the user: "An existing dev-workflow install was detected. Run `/dev-workflow:upgrade` instead." Do **not** continue to Phase 1.

Installs a multi-agent delivery workflow on a new project in five phases: discover project structure → create lifecycle infrastructure → wire domain skills + hooks → update CLAUDE.md → verify.

**What gets installed:**
- 3 orchestrator agents: `<PREFIX>-dev`, `<PREFIX>-qa`, `<PREFIX>-pm`
- 7 lifecycle skills: `<PREFIX>-log`, `<PREFIX>-review`, `<PREFIX>-debug`, `<PREFIX>-deploy`, `<PREFIX>-test`, `<PREFIX>-skill`, `<PREFIX>-docs`
- 5 slash commands: `/code` + `/fix` + `/design` (conditional on design skill) + `/roadmap` + `/wrap`
- `docs/roadmap.md` stub — source of truth for open items; tracked by `<PREFIX>-dev` (new entries) and `<PREFIX>-pm` (status updates)
- Domain skills: one per substantive source dir, derived from discovery (not hardcoded)
- `.claude/hooks/governed-paths.conf` — single source of truth for path→skill ownership; sourced by skill-guard and path-coverage-check
- `.claude/hooks/skill-guard.sh` — PreToolUse Edit+Write: blocks edits to owned paths without skill loaded
- `.claude/hooks/path-coverage-check.sh` — PreToolUse Write: blocks new files in governed roots not covered by any pattern
- `.claude/hooks/dependency-guard.sh` — PreToolUse Bash: blocks `pnpm add` / `pip install` without `<PREFIX>-skill` loaded
- `.claude/hooks/package-edit-guard.sh` — PreToolUse Edit: blocks direct dependency additions to `package.json` without `<PREFIX>-skill`
- `.claude/hooks/pre-handoff-check.sh` — PreToolUse Skill: blocks `<PREFIX>-qa` invocation if uncommitted changes exist, lint fails, or typecheck fails
- `.claude/hooks/ref-sync-check.sh` — PostToolUse Bash: warns after `git commit` if governed source paths or deploy-mechanism paths changed without reference file updates
- `.claude/hooks/skill-mark.sh` — PostToolUse Skill: records which skills were invoked each session
- `.claude/hooks/post-commit.sh` — PostToolUse Bash: reminds to run `<PREFIX>-log` after every commit
- `.claude/settings.json` — wires all hooks
- `CLAUDE.md` workflow sections

**Template files (read before Phase 2 and 3):**
- `../../shared/tpl-agents.md` — tosk-dev, tosk-qa, tosk-pm templates
- `../../shared/tpl-lifecycle.md` — 7 lifecycle skill templates
- `../../shared/tpl-skill-guard.md` — all hook templates + governed-paths.conf + settings.json
- `../../shared/tpl-domain-skill.md` — domain skill stub + project file sections
- `../../shared/tpl-commands.md` — slash command templates

---

## Preflight

Read `../../shared/preflight.md` and follow it before continuing.

---

## Phase 1 — Detect + Discover

### 1a. Set fixed paths and prompt for prefix

`CONFIG_DIR=.claude` and `PROJECT_FILE=CLAUDE.md` are fixed (Claude Code only).

Derive `PROJECT` from the directory name (`basename $PWD`).

Ask the user for a skill/agent prefix:

> "What prefix should I use for agents and skills? (e.g. `myapp` → `myapp-dev`, `myapp-qa`, `myapp-backend`)"
> Default suggestion: the project name lowercased and shortened if long.

Capture as `PREFIX`. All agents, lifecycle skills, and domain skills will be named `<PREFIX>-<name>`.

### 1b. Read the project

1. List top-level directories and files
2. Read `CLAUDE.md` if it exists
3. Read README.md, package.json, pyproject.toml, or other manifest files at the root for stack/run/lint signals

### 1c. Discover categories

Read `../../shared/tpl-domain-skill.md` § Domain categories before starting. Identify which of the 10 categories the project contains by **purpose**, not pattern matching against a fixed marker list.

For each category present, capture:
- **paths** — the directories or root-level files where this category lives
- **tools** — the specific frameworks/tools used (Astro, FastAPI, Terraform, etc.)

Build the **category map** — a single table that drives every downstream phase:

```
| Category                  | Paths                          | Tools                |
|---------------------------|--------------------------------|----------------------|
| Frontend                  | app/                           | Next.js, Tailwind    |
| Backend                   | api/                           | FastAPI, Python      |
| Database / storage        | (consumed via SDK)             | PostgreSQL           |
| Auth                      | app/auth/                      | Auth0                |
| IaC                       | infra/                         | Pulumi               |
| CI/CD                     | .github/workflows/             | GitHub Actions       |
| Build tooling             | package.json scripts           | npm, esbuild         |
| Deployment scripts/config | fly.toml, scripts/deploy.sh    | Fly.io, shell        |
| Observability             | (none)                         | —                    |
| Third-party SDK           | api/billing/                   | Stripe               |
```

*Paths and Tools are filled from discovery — not imported from this template.*

If you are uncertain whether something fits a category, ask the user. Use § Anchors in `tpl-domain-skill.md` only as a recognition aid, never as a whitelist.

### 1d. Propose domain skills from the category map

Group categories into proposed domain skills. Default groupings (override per-project as appropriate):

| Categories | Proposed skill |
|---|---|
| Backend, Database/storage, Auth (when consumed by backend), Third-party SDK (when consumed by backend) | `<PREFIX>-backend` |
| Frontend, Auth (when consumed by frontend) | `<PREFIX>-frontend` |
| Observability (when distinct from backend code) | `<PREFIX>-observability` (else fold into backend) |

The IaC, CI/CD, Build tooling, and Deployment scripts/config categories are owned by the `<PREFIX>-deploy` lifecycle skill — not a domain skill. They drive `DEPLOY_PATHS` in `governed-paths.conf` and feed the `deploy-config.yaml` populated in Phase 2; they do not produce a domain skill of their own.

A category may belong to multiple skills if it spans them (e.g. Auth shared between FE/BE) — record it under each owning skill. Single-component projects collapse to fewer skills (FE-only → just `<PREFIX>-frontend`; the deploy capability is always provided by the `<PREFIX>-deploy` lifecycle skill).

**Design skill rule:** If the Frontend category is present, also propose a `<PREFIX>-design` skill. This is always separate from the frontend skill — the frontend skill owns files, the design skill owns visual decisions (palette, tokens, typography). Enforcement is two-pronged:

1. **Mechanical (path-based)** — the design skill owns specific design token files (e.g. `^src/tokens\.css$`, `^src/theme\.css$`, `^app/styles/theme\.css$`) — list those before the frontend catch-all in `PATH_MAP` so they take priority. If no dedicated token file exists in the project, **propose creating one** at a sensible location for the stack (e.g. `<frontend-root>/tokens.css` for plain HTML/CSS, `app/styles/tokens.css` for Next.js, `src/styles/tokens.css` for Vite/Astro). Confirm location with user. If the user declines, `<PREFIX>-design` gets no `PATH_MAP` entry — mechanical enforcement is impossible and the install relies on instructional enforcement only.
2. **Instructional (skill-internal delegation)** — always required. The skill that owns the Frontend category receives the `<DESIGN_DELEGATION>` block (see `../../shared/tpl-domain-skill.md § Design delegation block`) wired in Phase 3a step 1. This block forbids the frontend skill from inventing CSS custom properties, colors, gradients, or typography, and routes all such decisions to `<PREFIX>-design`. This survives even when no dedicated token file exists.

Present the confirmation summary and **wait for user confirmation before creating anything**. The output must:
- Open with a `---` horizontal rule on its own line, followed by a blank line before `Project:`
- Close with the exact line `Confirm with yes (or adjust anything above) and I'll proceed with all phases.` on its own line, followed by a `---` horizontal rule on its own line
- Include any unresolved questions (e.g. missing local port for deploy-config.yaml) between the "What will be created" list and the confirm line

Template (substitute all `<…>` placeholders with real values from this project):

```
---
Project: <PROJECT> · Prefix: <PREFIX>

Category Map:
| Category | Paths | Tools |
|----------|-------|-------|
| <row per discovered category> | | |

Proposed domain skills:
| Skill | Categories | Owns |
|-------|------------|------|
| <row per proposed skill> | | |

Lifecycle path ownership:
- `<PREFIX>-deploy` → `<PATH_MAP pattern>` (PATH_MAP); contributes `<DEPLOY_PATHS pattern>` to DEPLOY_PATHS

(Omit this section entirely if no IaC/CI/CD/Build/Deployment categories were discovered. Compute `<PATH_MAP pattern>` and `<DEPLOY_PATHS pattern>` from the IaC/CI/CD/Build/Deployment rows of `CATEGORY_MAP` using the same rules as Phase 3b — anchored alternation per file, e.g. `^main\.tf$|^Dockerfile$` for PATH_MAP and `^(main\.tf$|Dockerfile$)` for DEPLOY_PATHS.)

Already present in docs/: <list any of workflow.md, project-log.md, roadmap.md that exist> — will skip creating stubs for these.
(Omit this line entirely if none exist.)

What will be created:
- 3 agents: <PREFIX>-dev, <PREFIX>-qa, <PREFIX>-pm
- 7 lifecycle skills: <PREFIX>-log, <PREFIX>-review, <PREFIX>-debug, <PREFIX>-deploy, <PREFIX>-test, <PREFIX>-skill, <PREFIX>-docs
- 1 design skill: <PREFIX>-design  ← omit if no frontend category
- <N> domain skills: <comma-separated list>
- <N> slash commands: /code, /fix, /roadmap, /wrap[, /design if frontend]
- 8 hook scripts + governed-paths.conf + settings.json
- CLAUDE.md with workflow sections

<Unresolved questions, if any — e.g. "One question before proceeding: what port does the local dev server run on? (I can see http://host:port in main.py — should I use that?)">

Confirm with yes (or adjust anything above) and I'll proceed with all phases.
---
```

*(Paths and tool names come from CATEGORY_MAP — derived from this project's actual structure, not this template.)*

Capture the confirmed mapping as:
- `CATEGORY_MAP` — the full category → paths/tools/skill table from this phase
- `DOMAIN_SKILLS[]` — array of domain skill names (does **not** include lifecycle skills like `<PREFIX>-deploy`)
- `DOMAIN_PATTERNS[]` — parallel array of owned path regex patterns (one per domain skill)

---

## Phase 2 — Install lifecycle infrastructure

Read `../../shared/tpl-agents.md` and `../../shared/tpl-lifecycle.md` now.

For each template, substitute:
- `<PROJECT>` → the project name derived in Phase 1
- `<PREFIX>` → the prefix confirmed in Phase 1a
- `<DOMAIN_SKILL_MAPPING>` → the confirmed skill→path table from Phase 1c
- `<PROJECT_ENCODED>` → `$(echo "$PWD" | sed 's|/|-|g')` (for `<PREFIX>-log` grep)

Create these files (skip if already present, offer to overwrite if stale):

```
.claude/agents/<PREFIX>-dev.md        ← from tpl-agents.md § tosk-dev
.claude/agents/<PREFIX>-qa.md         ← from tpl-agents.md § tosk-qa
.claude/agents/<PREFIX>-pm.md         ← from tpl-agents.md § tosk-pm
.claude/skills/<PREFIX>-log/SKILL.md
.claude/skills/<PREFIX>-review/SKILL.md
.claude/skills/<PREFIX>-debug/SKILL.md        ← also create 4 reference files + scripts (see tpl-lifecycle.md § debug)
.claude/skills/<PREFIX>-deploy/SKILL.md       ← from tpl-lifecycle.md § tosk-deploy/SKILL.md
.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml  ← populated, not a stub — see "Populate deploy-config.yaml" below
.claude/skills/<PREFIX>-test/SKILL.md       ← also creates references/test-commands.md, sync-checklist.md, custom-tests.md, and custom-tests.yaml (tests: []) — see tpl-lifecycle.md § tosk-test
.claude/skills/<PREFIX>-skill/SKILL.md
.claude/skills/<PREFIX>-skill/references/skill-manifest.md  ← stub; populate with all lifecycle + domain skills installed in this run
.claude/skills/<PREFIX>-docs/SKILL.md
.claude/skills/<PREFIX>-design/SKILL.md       ← only if a frontend/website domain skill was confirmed in Phase 1c; also create references/design-tokens.md stub
.claude/commands/code.md          ← from tpl-commands.md § /code, substitute <PROJECT> and <PREFIX>
.claude/commands/fix.md           ← from tpl-commands.md § /fix, substitute <PROJECT> and <PREFIX>
.claude/commands/roadmap.md       ← from tpl-commands.md § /roadmap, substitute <PROJECT> and <PREFIX>
.claude/commands/wrap.md          ← from tpl-commands.md § /wrap, substitute <PROJECT> and <PREFIX>
.claude/commands/design.md        ← from tpl-commands.md § /design (only if a design domain skill was discovered in Phase 1)
```

### Populate `deploy-config.yaml`

`.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` is **populated** during install — never left as a stub. Schema and rules: `../../shared/tpl-domain-skill.md § deploy-config.yaml schema`.

**Source from the category map.** The IaC, CI/CD, Build tooling, and Deployment scripts/config rows of `CATEGORY_MAP` already list the paths and tools detected in Phase 1c. For each, **read the actual file at its path** and derive yaml fields by purpose — do not apply tool names as a lookup table:

- **Trigger mechanism** (a workflow file, CI config, Makefile target): read it for env names, job triggers, and deploy commands. If it accepts parameters that select an environment, those parameters are env names. If it triggers a CD pipeline, that pipeline action is the deploy command; set `trigger: ci`. **If the same trigger file fires deploys for multiple components** (e.g. a single `deploy.yml` with `deploy-backend` + `deploy-frontend` jobs gated by `paths:` or `if:` conditions), still derive one `deploy:` entry per component, but emit the line `# TODO: split into deploy-<component>.yml — see tpl-domain-skill.md § deploy-config.yaml schema rules` above the first shared component block in the generated yaml. The flag travels into the repo as a visible reminder; it does not block the install.
- **Script file** (shell, Python, etc.): `deploy: "./<script>"` + `trigger: manual`. Read the script for any env-conditional branching to split into multiple envs.
- **Platform config file** (any config that names a cloud target or embeds a deploy CLI invocation): extract the deploy command from the config itself; extract the URL if present.
- **Run script in project manifest** (a `dev` or `start` entry in package.json, Pipfile, Procfile, pyproject.toml, etc.): use as `local.run`. Read the command for port flags to populate `local.url`.
- **IaC files**: read for env names (variable files, workspace names, environment variable definitions). IaC files rarely contain the deploy command themselves — pair with the CI/CD entry that invokes them.
- **README "Deploy" / "Deployment" section** with fenced commands: use as a last resort when no programmatic source is present.

**`local.url`**: do not use a preset port table. Instead:
1. Look for an explicit port in the dev run command (flags like `-p`, `--port`, `--listen`, `--host`).
2. Look for a port in the framework's own config file (e.g. a `port` or `server.port` field).
3. If still not found, ask: "What port does the local dev server run on for `<component>`?"

**`health_path`**: optional everywhere. Set when the project exposes a dedicated readiness endpoint (e.g. `/health`, `/_ready`, `/api/health`) — discovered by reading backend route files or framework configs. Omit when the base url itself is a sufficient liveness signal (typical for frontends).

**Determine components** from `CATEGORY_MAP`:
- `frontend` component if the Frontend category is present
- `backend` component if the Backend category is present
- Single-component projects (FE-only or BE-only) collapse to one component
- Default verify target per component: `local` for `frontend`; `cloud:<first-non-prod-env>` for `backend` if any non-prod env was detected, else `local`
- **Frontend with no own dev server**: if a Frontend category exists with no independent local dev server detected (no FE-specific dev/start script in the project manifest, no FE framework dev-server config), set `verify: cloud:<env>` and omit the `local:` block. If a Backend category also exists and serves the frontend's static assets, instead share the backend's `local:` block (one URL, two components).
- Populate the `local:` block whenever the component can be run locally (typical for FE; optional for BE if a local run command was detected). Required when `verify: local`.

**Propose** the populated YAML to the user. Wait for confirmation or edits. Prompt for missing values explicitly (e.g. "I couldn't find a prod URL for the backend — what is it?"). Never write placeholder text like `<fill in>` into the yaml.

**Write** to `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`.

If the project has no deploy mechanism at all (no IaC/CI/CD/Build/Deployment categories AND no local run command anywhere), still create the file with an empty `components: {}` map and a leading comment `# No deploy mechanism detected at install time — invoke <PREFIX>-skill to add components and envs when the project gains a deploy story.` This keeps the contract uniform and lets the deploy skill no-op cleanly.

Also create `docs/roadmap.md` stub if not present:
```markdown
# Roadmap

Items tracked here are the source of truth for open scope.
Format: title, **Category:** improvement | dogfood | integration | tech-debt, **Priority:** high | medium | low, **Status:** open | in-progress | done · YYYY-MM-DD, **Added:** YYYY-MM-DD HH:MM

---

## Improvements

## Tech Debt

## Integrations
```

Also create `docs/project-log.md` stub if not present:
```markdown
# Project Log

---
```

Also create `docs/workflow.md` if not present — generate with real content using values confirmed in Phase 1 (not a stub):

```markdown
# <PROJECT> Delivery Workflow

## Pipeline

```
/code or /fix
      │
      ▼
  <PREFIX>-dev ── domain skills ── implement ── <PREFIX>-deploy(non-prod) ── Reference Sync
      │
      ▼
  <PREFIX>-qa  ── <PREFIX>-review ── <PREFIX>-test ── sign-off
      │
      ▼
  <PREFIX>-pm  ── <PREFIX>-deploy(prod) ── <PREFIX>-log ── docs update
```

## Agents

| Agent | Role |
|---|---|
| `<PREFIX>-dev` | Design → implement → deploy non-prod → Reference Sync → hand off to `<PREFIX>-qa` |
| `<PREFIX>-qa` | Code review (`<PREFIX>-review`) + tests (`<PREFIX>-test`) → sign-off → hand off to `<PREFIX>-pm` |
| `<PREFIX>-pm` | Verify QA phases ran → deploy prod (if declared) → write delivery log (`<PREFIX>-log`) → update docs if needed |

## Skills

### Lifecycle

| Skill | Purpose |
|---|---|
| `<PREFIX>-log` | Appends delivery log entries to `docs/project-log.md` |
| `<PREFIX>-review` | Code review reception, reviewer dispatch, verification gates |
| `<PREFIX>-debug` | Systematic debugging — four-phase root cause investigation |
| `<PREFIX>-deploy` | Deploy authority — caller-driven env selection (`target=non-prod` from `<PREFIX>-dev`, `target=prod` from `<PREFIX>-pm`); reads `references/deploy-config.yaml`, fills missing values, gates prod inline via `AskUserQuestion`, verifies reachability |
| `<PREFIX>-test` | Smoke (always) · per-task verifications via `custom-tests.yaml` · on-demand regression |
| `<PREFIX>-skill` | Meta-skill — skill system governance and path ownership |
| `<PREFIX>-docs` | Documentation sync — README and workflow.md |

### Domain

<DOMAIN_SKILL_TABLE>

(Path ownership is the single source of truth in `.claude/hooks/governed-paths.conf`.)

Each domain skill defines a `## Quality Checklist` — what to run (tests, lint, type check) before proceeding to deploy. `<PREFIX>-dev` step 3 delegates to these checklists; the specific commands live in the skill, not in the agent.

## Hook Infrastructure

All hooks wired in `.claude/settings.json`.

| Hook | Event | Enforces |
|---|---|---|
| `skill-guard.sh` | PreToolUse Edit/Write | Owning skill must be loaded before editing governed paths |
| `path-coverage-check.sh` | PreToolUse Write | Blocks new files in governed roots with no matching owner |
| `dependency-guard.sh` | PreToolUse Bash | Requires `<PREFIX>-skill` before adding packages |
| `package-edit-guard.sh` | PreToolUse Edit | Requires `<PREFIX>-skill` before editing package files directly |
| `pre-handoff-check.sh` | PreToolUse Skill | Blocks `<PREFIX>-qa` if uncommitted changes or lint fails |
| `ref-sync-check.sh` | PostToolUse Bash | Warns after commits touching source without reference file updates |
| `skill-mark.sh` | PostToolUse Skill | Records which skills were invoked each session |
| `post-commit.sh` | PostToolUse Bash | Reminds to run `<PREFIX>-log` after every commit |

## Delivery Log Format

Each entry in `docs/project-log.md`:

```
---
### YYYY-MM-DD HH:MM · `<7-char hash>` — <short title>

<1–3 sentences: what shipped and why it matters>

**Tests:** <what was verified>
**Skills:** <skill-x> · <skill-y>
**Checklist:** <skill> — <what changed>  ← omit line if nothing updated
```
```

Substitute `<DOMAIN_SKILL_TABLE>` with a markdown table built from `DOMAIN_SKILLS[]` and `DOMAIN_PATTERNS[]` confirmed in Phase 1c:

```
| Skill | Owns |
|---|---|
| `<PREFIX>-<name>` | `<path-pattern>` |
| `<PREFIX>-design` | *(no path ownership — visual decisions only)* |  ← only if design skill was created
```

---

## Phase 3 — Create domain skills + wire hooks

Read `../../shared/tpl-domain-skill.md` and `../../shared/tpl-skill-guard.md` now.

### 3a. Domain skills

For each confirmed domain skill `<PREFIX>-<name>`:

1. Create `.claude/skills/<PREFIX>-<name>/SKILL.md` from stub template (in `tpl-domain-skill.md`), substituting:
   - `<SKILL_NAME>` → `<PREFIX>-<name>`
   - `<OWNED_PATHS>` → the confirmed path pattern for this skill
   - `<DESIGN_DELEGATION>` → if **this** skill owns the Frontend category in `CATEGORY_MAP` AND `<PREFIX>-design` is in `DOMAIN_SKILLS[]`, substitute with the `## Visual Decisions` block from `tpl-domain-skill.md § Design delegation block` (substituting `<PREFIX>`). Otherwise substitute with an empty string — remove the placeholder line entirely so non-frontend skills don't carry it.

2. Determine typed reference files for this skill from the category map (Phase 1c). Use the mapping in `tpl-domain-skill.md` § Reference files per category as the single source of truth — do not duplicate it here.

   For this skill, look up which categories it owns in `CATEGORY_MAP` and create one reference file per matching row. Do not create files for categories absent from this skill's domain. When no category matches but cloud resources exist (referenced in code), fall back to `resources.md` only.

   Create each file as `.claude/skills/<PREFIX>-<name>/references/<file>`. All files are stubs with only a `# Title` header and one `<!-- Fill in: ... -->` comment (see `tpl-domain-skill.md` § Reference files per category for the example stub). `deploy-config.yaml` is **not** a domain-skill reference — it lives in `<PREFIX>-deploy` and is populated in Phase 2.

   Use the created files to generate `<REFERENCE_SYNC_CHECKLIST>` and `<REFERENCES_LIST>` substitutions for this skill's SKILL.md (one entry per file).

### 3b. Hooks + governed-paths.conf + settings.json

Read `tpl-skill-guard.md` for all templates.

**Step 1 — Create `governed-paths.conf`**

Create `.claude/hooks/governed-paths.conf` from the template in `tpl-skill-guard.md § governed-paths.conf`, substituting:
- `<GOVERNED_ROOTS>` → ERE alternation of the paths from `CATEGORY_MAP` belonging to **Frontend, Backend, Database/storage, Auth, Observability, and Third-party SDK** categories (see `tpl-skill-guard.md § How to generate` for an example). **Never use extension globs** (e.g. `.*\.(html|css|js)$`) — these match files outside the project directory (such as `/tmp/`), defeating the guard. Root-level files like `index.html` are owned via explicit `PATH_MAP` entries, not via `GOVERNED_ROOTS`.
- `<DEPLOY_PATHS>` → ERE alternation of **every path from `CATEGORY_MAP` belonging to IaC, CI/CD, Build tooling, or Deployment scripts/config** (see `tpl-skill-guard.md § How to generate` for an example). Independent of `PATH_MAP` ownership — a path can be in `DEPLOY_PATHS` AND owned by a non-deploy skill (a deployment config file may live under the backend skill's ownership and still belong in `DEPLOY_PATHS`; both are correct). Drift watching and ownership are separate concerns. Set to `''` only if no IaC/CI/CD/Build/Deployment categories were discovered — `ref-sync-check.sh` then silently skips the deploy-drift check.
- `<PATH_MAP_ENTRIES>` → one `'PATTERN:SKILL'` entry per confirmed domain skill **plus** one entry for `<PREFIX>-deploy` covering the IaC/CI/CD/Build/Deployment paths from `CATEGORY_MAP` (omit the `<PREFIX>-deploy` entry only when no such categories were discovered). Standard catch-alls go at the end (see `tpl-skill-guard.md § How to generate governed-paths.conf`).

This is the **only** file that should contain path→skill mappings. Do not duplicate patterns in hook scripts.

**Step 2 — Create hook scripts**

Create all 8 hooks from their templates in `tpl-skill-guard.md`. Substitute `<PREFIX>` throughout:

| Hook | Template section |
|---|---|
| `skill-guard.sh` | § skill-guard.sh |
| `path-coverage-check.sh` | § path-coverage-check.sh |
| `dependency-guard.sh` | § dependency-guard.sh |
| `package-edit-guard.sh` | § package-edit-guard.sh |
| `pre-handoff-check.sh` | § pre-handoff-check.sh |
| `ref-sync-check.sh` | § ref-sync-check.sh |
| `skill-mark.sh` | § skill-mark.sh |
| `post-commit.sh` | § post-commit.sh |

Make all 8 executable:
```bash
chmod +x .claude/hooks/skill-guard.sh
chmod +x .claude/hooks/path-coverage-check.sh
chmod +x .claude/hooks/dependency-guard.sh
chmod +x .claude/hooks/package-edit-guard.sh
chmod +x .claude/hooks/pre-handoff-check.sh
chmod +x .claude/hooks/ref-sync-check.sh
chmod +x .claude/hooks/skill-mark.sh
chmod +x .claude/hooks/post-commit.sh
```

**Step 3 — Wire `settings.json`**

Use `tpl-skill-guard.md § settings.json`. If the file does not exist, create it from the template. If it already exists, merge the `hooks` key — add all hook entries without removing unrelated settings. Do not tell the user to wire hooks manually; write the file in this step.

---

## Phase 4 — Wire CLAUDE.md

Read `../../shared/tpl-domain-skill.md` § "Project file sections" for the section templates.

Upsert the following sections in `CLAUDE.md` (add if missing, replace if present):

- `## Plan Mode` — two bullets: (1) `docs/workflow.md` as the source of truth for the delivery pipeline; (2) "After finalizing a plan, invoke `/code` to hand off to the agent pipeline"
- `## Agents` — single line: `Pipeline: /code or /fix → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm. Details in docs/workflow.md.`
- `## Skills` — "Path→skill ownership is defined in `.claude/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically."
- `## Roadmap` — single line: `docs/roadmap.md` is the source of truth for open items.
- `## Linting` — only add if lint commands were discovered in Phase 1; omit entirely if none found (no `<fill in>` stub)

---

## Phase 5 — Verify

Walk the checklist before declaring done:

- [ ] `.claude/agents/` has `<PREFIX>-dev.md`, `<PREFIX>-qa.md`, `<PREFIX>-pm.md`
- [ ] `.claude/skills/` has all 7 lifecycle skills (`<PREFIX>-log`, `-review`, `-debug`, `-deploy`, `-test`, `-skill`, `-docs`) + all confirmed domain skills, all named `<PREFIX>-*`
- [ ] `.claude/skills/<PREFIX>-skill/references/skill-manifest.md` exists and lists all installed lifecycle and domain skills
- [ ] `.claude/skills/<PREFIX>-test/references/` has `test-commands.md` (with `## Smoke`, `## Regression`, `## Functional Feature Subjects` headings), `sync-checklist.md`, `custom-tests.md`, and `custom-tests.yaml` (initialized to `tests: []`). `<PREFIX>-test/SKILL.md` has a `## Test Plan` with the three tiers and no `## E2E Browser Tests` section
- [ ] `.claude/commands/code.md`, `fix.md`, `roadmap.md`, and `wrap.md` exist (markdown format, `$ARGUMENTS`)
- [ ] `.claude/skills/<PREFIX>-debug/` has SKILL.md + `references/systematic-debugging.md`, `references/root-cause-tracing.md`, `references/defense-in-depth.md`, `references/verification.md` + `scripts/find-polluter.sh` (executable) + `scripts/find-polluter.test.md`. SKILL.md contains a `## Read Map` and **no** `## Reference Sync` section (static-content skill).
- [ ] `.claude/skills/<PREFIX>-review/` has SKILL.md + `references/code-review-reception.md`, `references/requesting-code-review.md`, `references/issuing-findings.md` (no `verification-before-completion.md` — `<PREFIX>-debug` owns that). SKILL.md contains a `## Read Map` and **no** `## Reference Sync` section (static-content skill).
- [ ] `.claude/agents/<PREFIX>-qa.md` step 3 begins with `Test — invoke` and there is no `## Sign-off criteria` section (tier rules live only in `<PREFIX>-test`)
- [ ] `.claude/commands/design.md` exists if a frontend/website domain skill was confirmed in Phase 1c
- [ ] If `<PREFIX>-design` was created: `.claude/skills/<PREFIX>-design/SKILL.md` and `references/design-tokens.md` exist; `/design` command invokes `<PREFIX>-design` (not the frontend skill)
- [ ] If `<PREFIX>-design` was created: the skill that owns the Frontend category contains a `## Visual Decisions — Delegate to <PREFIX>-design` section (instructional delegation — closes the gap where the frontend skill could invent hex values without routing through design)
- [ ] If `<PREFIX>-design` was created: its SKILL.md description starts with "MUST be invoked" (mandatory invocation language — not the legacy permissive "Use when...")
- [ ] No leftover `<DESIGN_DELEGATION>` placeholder in any installed skill (frontend skill has it substituted; non-frontend skills have it removed)
- [ ] No command file contains stale project or prefix references — all use substituted values
- [ ] `.claude/hooks/governed-paths.conf` exists and has `GOVERNED_ROOTS` (directory prefixes only, no extension globs) + `DEPLOY_PATHS` (alternation of IaC/CI-CD/Build/Deployment paths, or `''` if none) + `PATH_MAP` with one entry per domain skill + standard catch-alls
- [ ] `.claude/hooks/skill-guard.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns
- [ ] `.claude/hooks/path-coverage-check.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns
- [ ] `.claude/hooks/dependency-guard.sh` is executable and checks for `<PREFIX>-skill` in session marker
- [ ] `.claude/hooks/package-edit-guard.sh` is executable and checks for `<PREFIX>-skill` in session marker
- [ ] `.claude/hooks/pre-handoff-check.sh` is executable, fires on `<PREFIX>-qa`, checks dirty tree + lint + typecheck
- [ ] `.claude/hooks/ref-sync-check.sh` is executable, sources `governed-paths.conf` — contains NO hardcoded path patterns; warns on `GOVERNED_ROOTS` drift without reference updates AND on `DEPLOY_PATHS` drift without `deploy-config.yaml` updates
- [ ] `.claude/hooks/skill-mark.sh` is executable
- [ ] `.claude/hooks/post-commit.sh` is executable and references `<PREFIX>-log`
- [ ] `.claude/settings.json` exists and wires all 8 hooks across `PreToolUse`/`PostToolUse` + `Edit`/`Write`/`Bash`/`Skill` matchers
- [ ] `CLAUDE.md` has `## Plan Mode`, `## Agents`, `## Skills`, and `## Roadmap` sections with correct references
- [ ] `docs/roadmap.md` exists (even as a stub)
- [ ] `docs/project-log.md` exists
- [ ] `docs/workflow.md` exists (even as a stub)
- [ ] `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` exists and parses as valid YAML. If any IaC/CI/CD/Build/Deployment categories were discovered or any component can be run locally, the file has at least one component, every component with `verify: local` has a `local:` block with both `run` and `url` populated, and there is no placeholder text. If the project has no deploy mechanism and no local run command, the file contains `components: {}` plus an explanatory leading comment.
- [ ] No domain-skill SKILL.md contains a `## Deployment` section (deploy logic lives only in `<PREFIX>-deploy/SKILL.md`)
- [ ] If any IaC/CI/CD/Build/Deployment categories were discovered, `governed-paths.conf` `DEPLOY_PATHS` is non-empty and contains every path from those categories (regardless of which skill owns each path in `PATH_MAP`); otherwise `DEPLOY_PATHS=''` and the deploy-drift check is skipped silently
- [ ] If any IaC/CI/CD/Build/Deployment categories were discovered, `governed-paths.conf` `PATH_MAP` has a `<PREFIX>-deploy` entry covering those paths
- [ ] `<PREFIX>-deploy/SKILL.md` `## Deployment` contains the strings "Caller contract", "Fill-in pass", and the inline gate context block fields (`env:`, `url:`, `command:`, `trigger:`, `commit:`, `branch:`) — gate runs inside the skill's turn via `AskUserQuestion`
- [ ] `<PREFIX>-dev.md` step 4 invokes `<PREFIX>-deploy` with `target=non-prod` and does not contain the phrase "If a gate is declined"
- [ ] `<PREFIX>-pm.md` has a step 1.5 invoking `<PREFIX>-deploy` with `target=prod` between step 1 (Verify QA phases) and step 2 (Write delivery log)
- [ ] `<PREFIX>-dev.md` step 7 (Hand off) is a one-line pointer to `## Response Requirements`; the structured `## Handoff` block format (`Status: complete | blocked`, Files changed, Deployed, Reference Sync, Commit, Notes) lives in a terminal `## Response Requirements` section after `## Boundaries`
- [ ] `<PREFIX>-qa.md` step 2 (Address findings) explicitly forbids self-patching ("You do not edit code") and routes fixes back to `<PREFIX>-dev` via blocked-status return
- [ ] `<PREFIX>-qa.md` step 6 (Hand off) is a one-line pointer to `## Response Requirements`; the structured `## Handoff` block format (`Status: signed-off | blocked`, Review, Tests, Reference Sync, Notes) lives in a terminal `## Response Requirements` section after `## Boundaries`
- [ ] `<PREFIX>-pm.md` step 1 (Verify QA evidence) reads `**QA-evidence:**` from the invocation prompt — does **not** grep session jsonl (subagent skill invocations don't reach the parent session)
- [ ] `<PREFIX>-pm.md` step 1.5 contains "You do not ask the user" — the deploy skill is the single gate; pm never returns mid-flow questions to the orchestrator
- [ ] `<PREFIX>-qa.md` has a `## Invocation modes` section with `mode: initial` (default, full pipeline) and `mode: retest` (skip review, run tests only — for re-runs after a dev fix)
- [ ] `.claude/commands/code.md` Step 2 parses dev `## Handoff` Status, branches on qa Status, and re-spawns qa with `mode=retest` after a dev fix; Step 3 passes the qa handoff verbatim to pm under `**QA-evidence:**`
- [ ] `.claude/commands/fix.md` Step 3 has the same qa-branching + retest logic; Step 4 passes `**QA-evidence:**` to pm
- [ ] Both `<PREFIX>-dev.md` and `<PREFIX>-qa.md` end with a `## Response Requirements` section (the **last** section of the file) containing the imperative "Every response MUST end with the `## Handoff` block" — terminal placement leverages prompt-recency so agents reliably emit the block
- [ ] No placeholder text (`<PROJECT>`, `<PREFIX>`, `<fill in>`, etc.) left in any installed file — prompt the user to fill these in

Report a summary: what was installed, what stubs need filling in, and how to test the hooks:
1. Try editing a file in an owned path without the skill loaded → should see the skill gate message
2. Try running `pnpm add some-package` without `<PREFIX>-skill` loaded → should see the dependency gate message
3. Try invoking `<PREFIX>-qa` with uncommitted changes → should see the pre-handoff gate message
