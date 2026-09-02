---
name: install
description: Install a 3-agent delivery workflow (dev → qa → pm, domain skills, skill-guard hooks, slash commands, roadmap tracking) on a fresh project. Trigger when the user wants to bootstrap a multi-agent workflow, set up an AI agent pipeline on a new project, add skill-guard hooks, or install the dev-workflow on a fresh repo. Claude Code only.
user-invocable: false
---

# install

> **Hard gate.** If `.claude/agents/<PREFIX>-dev.md` exists for any prefix, abort and tell the user: "An existing dev-workflow install was detected. Run `/dev-workflow:upgrade` instead." Do **not** continue to Phase 1.

Installs a multi-agent delivery workflow on a new project in five phases: discover project structure → create lifecycle infrastructure → wire domain skills + hooks → update CLAUDE.md → verify.

**What gets installed:**
- 3 orchestrator agents: `<PREFIX>-dev`, `<PREFIX>-qa`, `<PREFIX>-pm`
- 8 lifecycle skills: `<PREFIX>-log`, `<PREFIX>-review`, `<PREFIX>-debug`, `<PREFIX>-deploy`, `<PREFIX>-test`, `<PREFIX>-skill`, `<PREFIX>-docs`, `<PREFIX>-graph`
- 10 slash commands: `/code` + `/fix` + `/pilot` + `/tweak` + `/revert` + `/tidy` + `/design` (conditional on design skill) + `/whats-up` + `/roadmap` + `/wrap`
- `docs/roadmap.md` stub — source of truth for open items; tracked by `<PREFIX>-dev` (new entries) and `<PREFIX>-pm` (status updates)
- Domain skills: one per substantive source dir, derived from discovery (not hardcoded)
- `.claude/hooks/governed-paths.conf` — single source of truth for path→skill ownership (incl. per-skill self-ownership entries), `DEPLOY_PATHS`, and `REF_WATCH`; sourced by skill-guard, path-coverage-check, ref-sync-check, and close-out-gate
- `.claude/hooks/skill-guard.sh` — PreToolUse Edit+Write: blocks edits to owned paths without skill loaded (session-scoped markers)
- `.claude/hooks/path-coverage-check.sh` — PreToolUse Write: blocks new files in governed roots not covered by any pattern
- `.claude/hooks/dependency-guard.sh` — PreToolUse Bash: blocks `pnpm add` / `pip install` without `<PREFIX>-skill` loaded
- `.claude/hooks/package-edit-guard.sh` — PreToolUse Edit: blocks direct dependency additions to `package.json` without `<PREFIX>-skill`
- `.claude/hooks/pre-handoff-check.sh` — PreToolUse Skill + Task/Agent: blocks `<PREFIX>-qa` invocation (skill call or subagent spawn) if uncommitted changes exist, lint fails, or typecheck fails
- `.claude/hooks/close-out-gate.sh` — PreToolUse Bash: blocks `git push` while commits after the last delivery-log entry touch governed/deploy paths (iterate-lane close-out enforcement; `CLOSEOUT_OVERRIDE=1` escape hatch)
- `.claude/hooks/ref-sync-check.sh` — PostToolUse Bash: warns after `git commit` on reference-worthy drift (structural changes or `REF_WATCH` matches; modify-only cosmetic commits stay silent) and on deploy-mechanism drift without `deploy-config.yaml` updates
- `.claude/hooks/skill-mark.sh` — PostToolUse Skill: records invoked skills to a session-scoped marker
- `.claude/hooks/post-commit.sh` — PostToolUse Bash: reminds to run `<PREFIX>-log` after every commit
- `.claude/graph/graph.py` — delivery-graph projector + query engine (copied verbatim from `../../shared/graph.py`); `edges.jsonl` is generated and gitignored
- `.claude/skills/<PREFIX>-test/scripts/run-checks.py` — batched execution of resolved Integration commands and `last:` recording for every type (copied verbatim from `../../shared/run-checks.py`); returns observations, never verdicts
- `.claude/settings.json` — wires all hooks
- `CLAUDE.md` workflow sections

**Template files (read before Phase 2 and 3):**
- `../../shared/tpl-agents.md` — tosk-dev, tosk-qa, tosk-pm templates
- `../../shared/tpl-lifecycle.md` — 8 lifecycle skill templates
- `../../shared/graph.py` — the delivery-graph projector, copied verbatim to `.claude/graph/graph.py`
- `../../shared/run-checks.py` — the verification runner/recorder, copied verbatim to `.claude/skills/<PREFIX>-test/scripts/run-checks.py`
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

**Design skill rule:** If the Frontend category is present, also propose a `<PREFIX>-design` skill. This is always separate from the frontend skill — the frontend skill owns files, the design skill owns visual values (palette, tokens, typography), interaction patterns across the whole app, and icon sourcing. Enforcement is two-pronged:

1. **Mechanical (path-based)** — the design skill owns specific design token files (e.g. `^src/tokens\.css$`, `^src/theme\.css$`, `^app/styles/theme\.css$`) — list those before the frontend catch-all in `PATH_MAP` so they take priority. If no dedicated token file exists in the project, **propose creating one** at a sensible location for the stack (e.g. `<frontend-root>/tokens.css` for plain HTML/CSS, `app/styles/tokens.css` for Next.js, `src/styles/tokens.css` for Vite/Astro). Confirm location with user. If the user declines, `<PREFIX>-design` gets no `PATH_MAP` entry — mechanical enforcement is impossible and the install relies on instructional enforcement only.
2. **Instructional (skill-internal delegation)** — always required. The skill that owns the Frontend category receives the `<DESIGN_DELEGATION>` block (see `../../shared/tpl-domain-skill.md § Design delegation block`) wired in Phase 3a step 1. This block forbids the frontend skill from inventing CSS custom properties, colors, gradients, or typography, from standing up a second interaction pattern beside one the app already has, and from authoring icon artwork — routing all of it to `<PREFIX>-design`. This survives even when no dedicated token file exists, and it is the only enforcement patterns and icons get, since neither lives in a single file a `PATH_MAP` entry could guard.

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
- 8 lifecycle skills: <PREFIX>-log, <PREFIX>-review, <PREFIX>-debug, <PREFIX>-deploy, <PREFIX>-test, <PREFIX>-skill, <PREFIX>-docs, <PREFIX>-graph
- 1 design skill: <PREFIX>-design  ← omit if no frontend category
- <N> domain skills: <comma-separated list>
- <N> slash commands: /code, /fix, /pilot, /tweak, /revert, /tidy, /whats-up, /roadmap, /wrap[, /design if frontend]
- 9 hook scripts + governed-paths.conf + settings.json
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

Create these files (skip if already present, offer to overwrite if stale):

```
.claude/agents/<PREFIX>-dev.md        ← from tpl-agents.md § tosk-dev
.claude/agents/<PREFIX>-qa.md         ← from tpl-agents.md § tosk-qa
.claude/agents/<PREFIX>-pm.md         ← from tpl-agents.md § tosk-pm
.claude/skills/<PREFIX>-log/SKILL.md
.claude/skills/<PREFIX>-review/SKILL.md       ← also create references/{code-review-reception,requesting-code-review,issuing-findings,security-review}.md (see tpl-lifecycle.md § tosk-review)
.claude/skills/<PREFIX>-debug/SKILL.md        ← also create 4 reference files + scripts (see tpl-lifecycle.md § debug)
.claude/skills/<PREFIX>-deploy/SKILL.md       ← from tpl-lifecycle.md § tosk-deploy/SKILL.md
.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml  ← populated, not a stub — see "Populate deploy-config.yaml" below
.claude/skills/<PREFIX>-test/SKILL.md       ← also creates references/test-commands.md, sync-checklist.md, custom-tests.md, and custom-tests.yaml (tests: []) — see tpl-lifecycle.md § tosk-test
.claude/skills/<PREFIX>-test/scripts/run-checks.py  ← copy ../../shared/run-checks.py VERBATIM — no substitution (it glob-discovers the test skill), so it stays byte-identical across projects; `git add` it, and no chmod (it runs as `python3 …`)
.claude/skills/<PREFIX>-skill/SKILL.md
.claude/skills/<PREFIX>-skill/references/skill-manifest.md  ← stub; populate with all lifecycle + domain skills installed in this run
.claude/skills/<PREFIX>-docs/SKILL.md
.claude/skills/<PREFIX>-graph/SKILL.md        ← from tpl-lifecycle.md § tosk-graph; also create references/graph-schema.md
.claude/graph/graph.py                        ← copy ../../shared/graph.py VERBATIM — no substitution (it glob-discovers skill dirs), so it stays byte-identical across projects and diffs cleanly on upgrade
.claude/skills/<PREFIX>-design/SKILL.md       ← only if a frontend/website domain skill was confirmed in Phase 1c; also create references/design-tokens.md and references/ux-patterns.md stubs
.claude/commands/code.md          ← from tpl-commands.md § /code, substitute <PROJECT> and <PREFIX>
.claude/commands/fix.md           ← from tpl-commands.md § /fix, substitute <PROJECT> and <PREFIX>
.claude/commands/pilot.md         ← from tpl-commands.md § /pilot, substitute <PROJECT> and <PREFIX>
.claude/commands/tweak.md         ← from tpl-commands.md § /tweak, substitute <PROJECT> and <PREFIX>
.claude/commands/revert.md        ← from tpl-commands.md § /revert, substitute <PROJECT> and <PREFIX>
.claude/commands/tidy.md          ← from tpl-commands.md § /tidy, substitute <PROJECT> and <PREFIX>
.claude/commands/whats-up.md      ← from tpl-commands.md § /whats-up, substitute <PROJECT> and <PREFIX>
.claude/commands/roadmap.md       ← from tpl-commands.md § /roadmap, substitute <PROJECT> and <PREFIX>
.claude/commands/wrap.md          ← from tpl-commands.md § /wrap, substitute <PROJECT> and <PREFIX>
.claude/commands/design.md        ← from tpl-commands.md § /design (only if a design domain skill was discovered in Phase 1)
```

### Seed `<PREFIX>-design/references/ux-patterns.md`

Only when a `<PREFIX>-design` skill was confirmed. Create it from the stub in `../../shared/tpl-lifecycle.md § <PREFIX>-design/SKILL.md`, then fill the two `§ Iconography` fields that are discoverable **now**: the icon set the project already depends on (read the manifest for the dependency and one call site for the import convention — never name a set the project doesn't have), and the directory generated assets belong in (the frontend's existing static/asset dir). An empty field is honest; an invented one sends every future icon to the wrong place. `§ Inventory` stays empty — it fills as `<PREFIX>-design` runs, one row per pattern decision.

### Populate `deploy-config.yaml`

`.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` is **populated** during install — never left as a stub. Schema and rules: `../../shared/tpl-domain-skill.md § deploy-config.yaml schema`.

**Source from the category map.** The IaC, CI/CD, Build tooling, and Deployment scripts/config rows of `CATEGORY_MAP` already list the paths and tools detected in Phase 1c. For each, **read the actual file at its path** and derive yaml fields by purpose — do not apply tool names as a lookup table:

- **Trigger mechanism** (a workflow file, CI config, Makefile target): read it for env names, job triggers, and deploy commands. If it accepts parameters that select an environment, those parameters are env names. If it triggers a CD pipeline, that pipeline action is the deploy command; set `trigger: ci`. **If the same trigger file fires deploys for multiple components** (e.g. a single `deploy.yml` with `deploy-backend` + `deploy-frontend` jobs gated by `paths:` or `if:` conditions), still derive one `deploy:` entry per component, but emit the line `# TODO: split into deploy-<component>.yml — see tpl-domain-skill.md § deploy-config.yaml schema rules` above the first shared component block in the generated yaml. The flag travels into the repo as a visible reminder; it does not block the install.
- **Script file** (shell, Python, etc.): `deploy: "./<script>"` + `trigger: manual`. Read the script for any env-conditional branching to split into multiple envs.
- **Platform config file** (any config that names a cloud target or embeds a deploy CLI invocation): extract the deploy command from the config itself; extract the URL if present.
- **Run script in project manifest** (a `dev` or `start` entry in package.json, Pipfile, Procfile, pyproject.toml, etc.): use as `envs.local.run` (a serve-env). Read the command for port flags to populate `envs.local.url`.
- **IaC files**: read for env names (variable files, workspace names, environment variable definitions). IaC files rarely contain the deploy command themselves — pair with the CI/CD entry that invokes them.
- **README "Deploy" / "Deployment" section** with fenced commands: use as a last resort when no programmatic source is present.

**`envs.local.url`**: do not use a preset port table. Instead:
1. Look for an explicit port in the dev run command (flags like `-p`, `--port`, `--listen`, `--host`).
2. Look for a port in the framework's own config file (e.g. a `port` or `server.port` field).
3. If still not found, ask: "What port does the local dev server run on for `<component>`?"

**`health_path`**: optional everywhere. Set when the project exposes a dedicated readiness endpoint (e.g. `/health`, `/_ready`, `/api/health`) — discovered by reading backend route files or framework configs. Omit when the base url itself is a sufficient liveness signal (typical for frontends).

**`envs.local.stack`** (composed local stack — see `tpl-domain-skill.md § deploy-config.yaml schema`): when a component's plain dev-run command starts it wired to prod (e.g. the frontend's API-base-URL env var points at the prod API) or unusable headless (no data, no auth), derive a `stack:` block: find the env var that selects the API base url (framework config, `.env.example`, code) and override it to the local backend's url; record a `seed:` command only if a real one exists (fixtures script, `scripts/seed*`); record the headless `auth:` strategy only if one exists (test-user env vars, local auth bypass). Never invent seed commands or auth strategies — if local verification is genuinely impossible, omit `stack:` and typed verifications will honestly report blocked.

**Determine components** from `CATEGORY_MAP`:
- `frontend` component if the Frontend category is present
- `backend` component if the Backend category is present
- Single-component projects (FE-only or BE-only) collapse to one component
- Default `verify:` per component: `local` for `frontend`; the first non-prod ship-env for `backend` if one was detected, else `local`
- **Frontend with no own dev server**: if a Frontend category exists with no independent local dev server detected (no FE-specific dev/start script in the project manifest, no FE framework dev-server config) and a Backend category serves the frontend's static assets, share the backend's `envs.local` serve-env (one URL, two components). Only when nothing serves the frontend locally set `verify: <ship-env>` and omit `envs.local`.
- Populate an `envs.local` serve-env (`run` + `url`) for **every component that can run locally** — frontends and backends alike. It is the zero-cost non-prod target typed verifications resolve to when no cloud non-prod env exists; a locally-runnable component must never be left with no non-prod env. Required when `verify: local`.

**Propose** the populated YAML to the user. Wait for confirmation or edits. Prompt for missing values explicitly (e.g. "I couldn't find a prod URL for the backend — what is it?"). Never write placeholder text like `<fill in>` into the yaml.

**Write** to `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`.

If the project has no deploy mechanism at all (no IaC/CI/CD/Build/Deployment categories AND no local run command anywhere), still create the file with an empty `components: {}` map and a leading comment `# No deploy mechanism detected at install time — invoke <PREFIX>-skill to add components and envs when the project gains a deploy story.` This keeps the contract uniform and lets the deploy skill no-op cleanly.

Also create `docs/roadmap.md` stub if not present:
```markdown
# Roadmap

Items tracked here are the source of truth for open scope.
Each item is a `### ` heading, a 1–2 sentence description, then its metadata fields:
**Id:** stable-kebab-slug · **Category:** improvement | dogfood | integration | tech-debt ·
**Priority:** high | medium | low · **Status:** open | in-progress | done · YYYY-MM-DD ·
**Added:** YYYY-MM-DD HH:MM

Fields may be written one per line, as list items (`- **Status:** open`), or packed several to a
line — all three are read correctly. Pick one and stay consistent within the file; never reformat
existing items to match a different one.

`**Id:**` is the item's permanent handle — the delivery log's `**Addresses:**` line cites it, which
is what links a shipped commit back to the scope it closed. Assign one when the item is created and
**never change it**, even if the title is later rewritten; a title-derived id silently orphans every
prior reference the moment the title changes.

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

Also append to `.gitignore` (create it if absent) any of these lines not already present:
```
.claude/graph/edges.jsonl
.claude/graph/__pycache__/
```
The index is generated, churns on every delivery, and is rebuilt in under a second — committing it
would add noise to every diff for no recoverable value. `__pycache__/` appears whenever anything
imports `graph.py` rather than running it as a script.

**`graph.py` itself must be committed** — stage it explicitly:
```bash
git add .claude/graph/graph.py .gitignore
```
An untracked `graph.py` has no protection: any `git clean`, a `/tidy` discard, or a stray `rm -rf`
deletes it, and because every call site is required to fall back silently, the workflow keeps
running with the graph quietly gone and **no signal that it was ever there**. Tracking it is the
only thing that makes its absence visible.

Then run `python3 .claude/graph/graph.py build` once to prove the projector works against this
project's artifacts. On a fresh repo it correctly reports `0 edges · 0/0 log entries parsed`.

Also create `docs/workflow.md` if not present — generate with real content using values confirmed in Phase 1 (not a stub):

```markdown
# <PROJECT> Delivery Workflow

## Pipeline

```
/code or /fix
      │
      ▼
  (top level) single gate — states the acceptance statement and the verifications derived from it;
              free text amends them. Regression scope is not asked: it is pinned by --regression
              or resolved later from the paths that actually changed
      │
      ▼
  <PREFIX>-dev ── domain skills ── implement ── <PREFIX>-deploy(non-prod) ── Reference Sync
      │
      ▼
  (top level) ensure verification stack — start/restart the serve-env (with its stack: overrides) if a UX/E2E target is down or stale
      │
      ▼
  <PREFIX>-qa  ── <PREFIX>-review ── <PREFIX>-test ── sign-off (or signed-off-with-deferrals)
      │
      ▼
  <PREFIX>-pm  ── <PREFIX>-log ── docs update
      │
      ▼
  (only with `--prod`) ── <PREFIX>-deploy(prod) at the command top level, after sign-off
      │
      ▼
  (top level) close out — push per <PREFIX>-deploy § Push policy + verified scorecard
```

Iterative work (pixel nudges, copy rounds, small hotfixes) uses `/tweak` — top-level, inline-verified, close-out batched at exit and enforced by the `close-out-gate` hook at push time. Rollbacks use `/revert` (git revert + scoped re-verify + logged reversal). Leftover WIP — a dirty tree, orphaned stashes, stale branches — uses `/tidy`: it sweeps, probes history to establish what each item actually is, and routes every item to commit / deliver / discard / ignore. Multi-task autonomous runs (a roadmap batch, a goal to iterate toward) use `/pilot` — it decomposes the goal, gates once up-front, routes each task through the pipeline or the tweak lane, and closes out once at the end. `/pilot --gates` is the same lane aimed at a store instead of a goal: it re-measures every parked verdict, closes on its own the ones whose proposal the measurement killed or whose trigger has not fired, and brings the rest back as one batched decision with a recommendation per row — nothing that writes is ever concluded without an answer. `/roadmap` is the way in from tracked work: it ranks the open items (one rank rule, defined in `roadmap.md § Rank` and cited by `/pilot`) and either hands the top set to `/pilot --items <id>,…` as a mission or starts a single item through `/code`/`/fix`. It selects and never implements, so run constraints — task cap, retry limit, budget — live only in `/pilot`.

## Agents

| Agent | Role |
|---|---|
| `<PREFIX>-dev` | Design → implement → deploy non-prod → Reference Sync → hand off to `<PREFIX>-qa` |
| `<PREFIX>-qa` | Code review (`<PREFIX>-review`) + tests (`<PREFIX>-test`) → sign-off (`signed-off` \| `signed-off-with-deferrals` when only unrunnable verifications remain) → hand off to `<PREFIX>-pm` |
| `<PREFIX>-pm` | Verify QA phases ran → write delivery log (`<PREFIX>-log`, hash = the feature commit) → update docs if needed |

Prod deploy is **not** an agent step — it runs at the command top level only when `/code` / `/fix` is invoked with `--prod` (so the `<PREFIX>-deploy` `AskUserQuestion` gate reaches the user), after QA sign-off, on the final code. The `<PREFIX>-deploy` skill carries **no** `disable-model-invocation` frontmatter — the dev step and the command must be able to invoke it via the Skill tool; prod safety comes from its `user_confirm` gate, not a frontmatter gate.

Gate timeouts split by risk: reversible gates proceed with defaults labeled `auto-selected on timeout — not user-confirmed`; irreversible gates (prod deploy, CI-coupled push) park until the user responds. A timeout is never presented as consent.

## Skills

### Lifecycle

| Skill | Purpose |
|---|---|
| `<PREFIX>-log` | Appends delivery log entries to `docs/project-log.md` |
| `<PREFIX>-review` | Code review reception, reviewer dispatch, verification gates |
| `<PREFIX>-debug` | Systematic debugging — four-phase root cause investigation |
| `<PREFIX>-deploy` | Deploy authority — caller-driven env selection (`target=non-prod` from `<PREFIX>-dev`, `target=prod` from the `/code\|/fix --prod` command step); reads `references/deploy-config.yaml` (unified env schema: `run:` serve-envs / `deploy:` ship-envs), fills missing values, gates prod inline via `AskUserQuestion`, verifies reachability |
| `<PREFIX>-test` | Smoke (always) · per-task verifications via `custom-tests.yaml`, end-state check never narrowed away · regression scope pinned by the caller or resolved from the changed paths |
| `<PREFIX>-skill` | Meta-skill — skill system governance and path ownership |
| `<PREFIX>-docs` | Documentation sync — README and workflow.md |
| `<PREFIX>-graph` | Delivery graph — projects the log, verifications, ownership and deploy config into a queryable edge index (`covers` / `blast` / `history` / `roadmap-open` / `open-deferrals`); derived and disposable, every caller falls back without it |

### Domain

<DOMAIN_SKILL_TABLE>

(Path ownership is the single source of truth in `.claude/hooks/governed-paths.conf`.)

Each domain skill defines a `## Quality Checklist` — what to run (tests, lint, type check) before proceeding to deploy. `<PREFIX>-dev` step 3 delegates to these checklists; the specific commands live in the skill, not in the agent.

## Hook Infrastructure

All hooks wired in `.claude/settings.json`.

| Hook | Event | Enforces |
|---|---|---|
| `skill-guard.sh` | PreToolUse Edit/Write | Owning skill must be loaded before editing governed paths (session-scoped markers) |
| `path-coverage-check.sh` | PreToolUse Write | Blocks new files in governed roots with no matching owner |
| `dependency-guard.sh` | PreToolUse Bash | Requires `<PREFIX>-skill` before adding packages |
| `package-edit-guard.sh` | PreToolUse Edit | Requires `<PREFIX>-skill` before editing package files directly |
| `pre-handoff-check.sh` | PreToolUse Skill + Task/Agent | Blocks `<PREFIX>-qa` (skill call or subagent spawn) if uncommitted changes or lint fails |
| `close-out-gate.sh` | PreToolUse Bash | Blocks `git push` while governed commits lack a delivery-log entry (`CLOSEOUT_OVERRIDE=1` escape) |
| `ref-sync-check.sh` | PostToolUse Bash | Warns on reference-worthy drift (structural / `REF_WATCH`) and deploy-config drift |
| `skill-mark.sh` | PostToolUse Skill | Records invoked skills to a session-scoped marker |
| `post-commit.sh` | PostToolUse Bash | Reminds to run `<PREFIX>-log` after every commit |

## Delivery Log Format

Each entry in `docs/project-log.md`:

```
---
### YYYY-MM-DD HH:MM · `<7-char hash>` — <short title>

<1–3 sentences: what shipped and why it matters>

**Tests:** <what was verified>
**Skills:** <skill-x> · <skill-y>
**Deployed:** <component> → <env> · <url>  ← omit line if no deploy happened
**Addresses:** <roadmap **Id:** value(s)>  ← omit line if no tracked item is addressed
**UAT-deferred:** <verification names + how confirmed>  ← omit line if nothing deferred
**Decisions:** <gate>=<value> (<user|timeout|agent|pilot-auto>) · …  ← omit line if no gate came up
**Checklist:** <skill> — <what changed>  ← omit line if nothing updated
```

The hash is the primary feature/fix commit, never a `test:`/`log:`/`docs:` bookkeeping commit.

`**Addresses:**` cites the roadmap item's permanent `**Id:**` — that citation is what links a
shipped commit back to the scope it closed. `**Decisions:**` records how each gate was settled;
a timeout, a pipeline-derived value (`agent` — the regression scope resolved from the changed paths
is the standing case), or an autonomous choice is never written as `user`, and a gate deliberately
left for a human is written `<gate>=parked (human-gated)` rather than being decided.

This field set is **closed**. Leftover scope goes to `docs/roadmap.md` as its own item, and a
verification that could not be run goes to `**UAT-deferred:**` — not into an invented field. The
graph ignores unknown fields silently, so an invented one reads as recorded but is not.

The delivery log is also the delivery graph's primary input — `<PREFIX>-log` runs
`python3 .claude/graph/graph.py build` after committing each entry, so these fields become
queryable. See `<PREFIX>-graph`.
```

Substitute `<DOMAIN_SKILL_TABLE>` with a markdown table built from `DOMAIN_SKILLS[]` and `DOMAIN_PATTERNS[]` confirmed in Phase 1c:

```
| Skill | Owns |
|---|---|
| `<PREFIX>-<name>` | `<path-pattern>` |
| `<PREFIX>-design` | *(no path ownership — visual + UX-pattern + icon decisions)* |  ← only if design skill was created
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
- `<SKILL_SELF_OWNERSHIP_ENTRIES>` → one `'^\.claude/skills/<PREFIX>-<name>/:<PREFIX>-<name>'` entry per installed skill (all lifecycle + domain skills from this run), placed before the `.claude/skills/` catch-all.
- `<REF_WATCH>` → ERE alternation of reference-worthy source paths derived from `CATEGORY_MAP` (Backend route/handler dirs, schema/model files, Auth paths). Set `''` when nothing clearly reference-worthy is identifiable.

This is the **only** file that should contain path→skill mappings. Do not duplicate patterns in hook scripts.

**Step 2 — Create hook scripts**

Create all 9 hooks from their templates in `tpl-skill-guard.md`. Substitute `<PREFIX>` throughout:

| Hook | Template section |
|---|---|
| `skill-guard.sh` | § skill-guard.sh |
| `path-coverage-check.sh` | § path-coverage-check.sh |
| `dependency-guard.sh` | § dependency-guard.sh |
| `package-edit-guard.sh` | § package-edit-guard.sh |
| `pre-handoff-check.sh` | § pre-handoff-check.sh |
| `close-out-gate.sh` | § close-out-gate.sh |
| `ref-sync-check.sh` | § ref-sync-check.sh |
| `skill-mark.sh` | § skill-mark.sh |
| `post-commit.sh` | § post-commit.sh |

For `pre-handoff-check.sh`, also substitute `<LINT_CMD>` and `<TYPECHECK_CMD>` with the commands discovered in Phase 1 — following the **Bare-shell rule** in `tpl-skill-guard.md § pre-handoff-check.sh`: the hook runs without the project's activated environment, so a bare interpreter/tool command (`ruff check .`, `python -m ruff`, `eslint .`, `tsc`) that works in a terminal will silently fail the gate. Substitute an env-launcher (`uv run …`, `poetry run …`, `pnpm exec …`, `npx --no-install …`) or an absolute project-env path (`.venv/bin/…`, `node_modules/.bin/…`); when the interpreter path itself may or may not exist, resolve it defensively at the top of the hook (the venv-fallback snippet in the template Note). If no lint/typecheck command was discovered, leave the `<fill in>` stub and tell the user. A command counts as *discovered* only if it **verifiably resolves** — the `lint` script exists under `scripts` in `package.json`, or the linter is an installed dependency; a conventional-but-unwired `npm run lint` errors on every run, so stub it rather than substitute it.

Make all 9 executable:
```bash
chmod +x .claude/hooks/skill-guard.sh
chmod +x .claude/hooks/path-coverage-check.sh
chmod +x .claude/hooks/dependency-guard.sh
chmod +x .claude/hooks/package-edit-guard.sh
chmod +x .claude/hooks/pre-handoff-check.sh
chmod +x .claude/hooks/close-out-gate.sh
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
- `## Agents` — the pipeline line plus the routing paragraph (pipeline-shaped work → `/code`/`/fix`, iterative rounds → `/tweak`) from the template
- `## Skills` — "Path→skill ownership is defined in `.claude/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically."
- `## Roadmap` — single line: `docs/roadmap.md` is the source of truth for open items.
- `## Secrets` — the never-through-chat rule from the template
- `## Linting` — only add if lint commands were discovered in Phase 1; omit entirely if none found (no `<fill in>` stub)

---

## Phase 5 — Verify

Walk the checklist before declaring done:

- [ ] `.claude/agents/` has `<PREFIX>-dev.md`, `<PREFIX>-qa.md`, `<PREFIX>-pm.md`
- [ ] `.claude/skills/` has all 8 lifecycle skills (`<PREFIX>-log`, `-review`, `-debug`, `-deploy`, `-test`, `-skill`, `-docs`, `-graph`) + all confirmed domain skills, all named `<PREFIX>-*`
- [ ] `.claude/skills/<PREFIX>-skill/references/skill-manifest.md` exists and lists all installed lifecycle and domain skills
- [ ] `.claude/skills/<PREFIX>-test/references/` has `test-commands.md` (with `## Smoke`, `## Regression`, `## Functional Feature Subjects` headings), `sync-checklist.md`, `custom-tests.md`, and `custom-tests.yaml` (initialized to `tests: []`). `<PREFIX>-test/SKILL.md` has a `## Test Plan` with the three tiers and no `## E2E Browser Tests` section. `custom-tests.md`'s schema uses `type: UX | Integration | E2E` (not `surface`)
- [ ] `.claude/commands/code.md`, `fix.md`, `pilot.md`, `tweak.md`, `revert.md`, `tidy.md`, `whats-up.md`, `roadmap.md`, and `wrap.md` exist (markdown format, `$ARGUMENTS`)
- [ ] `whats-up.md` reads six universal stores plus any declared via a `whats-up-store:` frontmatter key (each with a stated fallback), calls `open-deferrals --with-fail` and `open-gates`, reconciles a `parked` gate against later evidence before reporting it, states that it never writes, and reports per `code.md § Done` with the ranked `Open` table as its plan — **no** separate numbered action list. Its Step 3 ladder must say it **ranks the report rather than filtering it**, and its § Done must carry the in-progress exception: one `Open` row per `in-progress` item (stalled at 21+ days since `last_addressed`), the `Emerged` roadmap count broken down by status, a gate row naming what it `releases`, and the closing line staged decisions → repairs → items
- [ ] `roadmap.md` ranks via `graph.py roadmap-open` (with the read-the-file fallback), applies `$ARGUMENTS` as a filter, and routes to `/pilot --items` or a single `/code`/`/fix`; the rank rule appears **only** in `roadmap.md § Rank` — `pilot.md` cites it rather than restating it
- [ ] `.claude/skills/<PREFIX>-debug/` has SKILL.md + `references/systematic-debugging.md`, `references/root-cause-tracing.md`, `references/defense-in-depth.md`, `references/verification.md` + `scripts/find-polluter.sh` (executable) + `scripts/find-polluter.test.md`. SKILL.md contains a `## Read Map` and **no** `## Reference Sync` section (static-content skill).
- [ ] `.claude/skills/<PREFIX>-review/` has SKILL.md + `references/code-review-reception.md`, `references/requesting-code-review.md`, `references/issuing-findings.md` (no `verification-before-completion.md` — `<PREFIX>-debug` owns that). SKILL.md contains a `## Read Map` and **no** `## Reference Sync` section (static-content skill).
- [ ] `.claude/agents/<PREFIX>-qa.md` step 3 begins with `Test — invoke` and there is no `## Sign-off criteria` section (tier rules live only in `<PREFIX>-test`)
- [ ] `.claude/commands/design.md` exists if a frontend/website domain skill was confirmed in Phase 1c
- [ ] If `<PREFIX>-design` was created: `.claude/skills/<PREFIX>-design/SKILL.md` and `references/design-tokens.md` exist; `/design` command invokes `<PREFIX>-design` (not the frontend skill)
- [ ] If `<PREFIX>-design` was created: the skill that owns the Frontend category contains a `## Visual Decisions — Delegate to <PREFIX>-design` section (instructional delegation — closes the gap where the frontend skill could invent hex values without routing through design)
- [ ] If `<PREFIX>-design` was created: its SKILL.md description starts with "MUST be invoked" (mandatory invocation language — not the legacy permissive "Use when...")
- [ ] If `<PREFIX>-design` was created: `references/ux-patterns.md` exists with `## Inventory`, `## Consistency sweep`, and `## Iconography`; the sweep names all three verdicts (match / migrate / diverge) and `§ Iconography` forbids hand-authored icon geometry, routes anything the icon set doesn't cover to the asset skill named in SKILL.md, and carries both guards (no interview from a subagent; a missing API key is `blocked`, never a hand-drawn fallback)
- [ ] If `<PREFIX>-design` was created: its `## When this skill MUST be invoked` list covers **surfaces / interaction patterns and icons**, not only values, and the skill names both external skills by role (design intelligence + asset generation) with the replace-either-name note
- [ ] If `<PREFIX>-design` was created: the frontend skill's `## Visual Decisions` block carries the interaction-pattern and icon triggers, and `<PREFIX>-review/SKILL.md` has the `ux-patterns.md` branch in its `## Read Map` **and** `## References`. If **no** design skill was created, `<PREFIX>-review` must mention `ux-patterns.md` nowhere — a branch to a file the project has no owner for is a dead route
- [ ] No leftover `<DESIGN_DELEGATION>` placeholder in any installed skill (frontend skill has it substituted; non-frontend skills have it removed)
- [ ] No command file contains stale project or prefix references — all use substituted values
- [ ] `.claude/hooks/governed-paths.conf` exists and has `GOVERNED_ROOTS` (directory prefixes only, no extension globs) + `DEPLOY_PATHS` (alternation of IaC/CI-CD/Build/Deployment paths, or `''` if none) + `REF_WATCH` (reference-worthy paths, or `''`) + `PATH_MAP` with the `custom-tests.yaml` EXEMPT entry, one self-ownership entry per installed skill (before the `.claude/skills/` catch-all), one entry per domain skill, and standard catch-alls
- [ ] `.claude/hooks/skill-guard.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns; marker derivation includes the transcript-basename agent scope
- [ ] `.claude/hooks/path-coverage-check.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns
- [ ] `.claude/hooks/dependency-guard.sh` is executable and checks for `<PREFIX>-skill` in the session-scoped session marker
- [ ] `.claude/hooks/package-edit-guard.sh` is executable and checks for `<PREFIX>-skill` in the session-scoped session marker
- [ ] `.claude/hooks/pre-handoff-check.sh` is executable, matches **both** `tool_input.skill` and `tool_input.subagent_type` for `<PREFIX>-qa`, checks dirty tree + lint + typecheck
- [ ] Every domain-skill `## Quality Checklist` command **resolves against the project** — each named `package.json` script exists under `scripts`, each linter/tool is an installed dependency or resolvable path; no rule names a conventional-but-unwired command (e.g. `npm run lint` with no `lint` script). The Quality Checklist lint command and the hook `<LINT_CMD>` **agree**: both name the same verified command, or both are absent
- [ ] `.claude/hooks/close-out-gate.sh` is executable, fires on `git push`, sources `governed-paths.conf`, and honors `CLOSEOUT_OVERRIDE=1`
- [ ] `.claude/hooks/ref-sync-check.sh` is executable, sources `governed-paths.conf` — contains NO hardcoded path patterns; source-drift warning fires only on structural (A/D/R) changes or `REF_WATCH` matches; deploy-drift check unchanged
- [ ] `.claude/hooks/skill-mark.sh` is executable and writes to the session-scoped marker (same derivation as the guards)
- [ ] `.claude/hooks/post-commit.sh` is executable, references `<PREFIX>-log`, and exits 0 on success paths (recorders never exit non-zero)
- [ ] `.claude/settings.json` exists and wires all 9 hooks across `PreToolUse`/`PostToolUse` + `Edit`/`Write`/`Bash`/`Skill`/`Task|Agent` matchers
- [ ] `CLAUDE.md` has `## Plan Mode`, `## Agents`, `## Skills`, and `## Roadmap` sections with correct references
- [ ] `docs/roadmap.md` exists (even as a stub) and its format line documents `**Id:**` as the item's permanent handle
- [ ] `docs/project-log.md` exists
- [ ] `.claude/graph/graph.py` exists and is **byte-identical** to the plugin's `shared/graph.py` (no substitution — a diff means someone edited the copy instead of the plugin)
- [ ] `python3 .claude/graph/graph.py build` exits 0, reports `N/N log entries parsed` with no `WARNING`, and running it twice produces an identical `edges.jsonl` body (on a fresh repo it correctly reports `0 edges · 0/0`)
- [ ] `.gitignore` contains `.claude/graph/edges.jsonl` and `.claude/graph/__pycache__/`; `graph.py` itself is **not** ignored
- [ ] `graph.py` is **tracked by git** — `git ls-files --error-unmatch .claude/graph/graph.py` exits 0. Present-but-untracked is the failure that silently deletes itself later, and the mandatory fallbacks mean nothing reports it
- [ ] `governed-paths.conf` `PATH_MAP` has `'^\.claude/graph/edges\.jsonl$:EXEMPT'` **before** `'^\.claude/graph/:<PREFIX>-graph'`, and both before the `'^\.claude/:OPEN'` catch-all
- [ ] `<PREFIX>-graph/SKILL.md` exists with `references/graph-schema.md`; the schema reference documents every edge type `graph.py` emits with its source artifact
- [ ] `<PREFIX>-log/SKILL.md` entry format has `**Addresses:**` and `**Decisions:**`, and its Process runs `graph.py build` after committing the entry
- [ ] `<PREFIX>-log/SKILL.md` derives `**Skills:**` from the `/tmp/<PREFIX>-skills-*` markers scoped **by session id**, not by file mtime (two sibling repos sharing a prefix share the marker namespace, and an mtime window cross-contaminates them). It must **not** contain `PROJECT_ENCODED` or a `~/.claude/projects/*.jsonl` grep (that source cannot see subagent skill loads and is blocked outright by a secret guard), and must filter with `grep -E '^<PREFIX>-'` so slash-command names are excluded
- [ ] `<PREFIX>-test` `custom-tests.md` schema documents the `last:` block **including `reason`** (required on `blocked`/`fail` — `graph.py` and `/code` Step 0 both read it), and the execution protocol writes it after each run
- [ ] `<PREFIX>-test` `custom-tests.md` has a `## Regression scope` section, and `<PREFIX>-test/SKILL.md`'s tier table marks the end-state verification non-negotiable
- [ ] Every graph call site (`<PREFIX>-test` prior-selection, `<PREFIX>-dev` step 1, `<PREFIX>-pm` step 1.5, `<PREFIX>-debug` Phase 1, `/code` + `/fix` Step 0) states an explicit fallback for a missing or failing script — the graph is never a gate
- [ ] `docs/workflow.md` exists (even as a stub)
- [ ] `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` exists and parses as valid YAML. If any IaC/CI/CD/Build/Deployment categories were discovered or any component can be run locally, the file has at least one component; every env declares exactly one of `run:`/`deploy:` plus a `url`; every locally-runnable component has at least one non-prod env (`envs.local` serve-env or a cloud non-prod ship-env); there is no top-level `local:` block, no `cloud:` prefix in `verify:`, and no placeholder text. If the project has no deploy mechanism and no local run command, the file contains `components: {}` plus an explanatory leading comment.
- [ ] No domain-skill SKILL.md contains a `## Deployment` section (deploy logic lives only in `<PREFIX>-deploy/SKILL.md`)
- [ ] If any IaC/CI/CD/Build/Deployment categories were discovered, `governed-paths.conf` `DEPLOY_PATHS` is non-empty and contains every path from those categories (regardless of which skill owns each path in `PATH_MAP`); otherwise `DEPLOY_PATHS=''` and the deploy-drift check is skipped silently
- [ ] If any IaC/CI/CD/Build/Deployment categories were discovered, `governed-paths.conf` `PATH_MAP` has a `<PREFIX>-deploy` entry covering those paths
- [ ] `<PREFIX>-deploy/SKILL.md` `## Deployment` contains the strings "Caller contract", "Fill-in pass", and the inline gate context block fields (`env:`, `url:`, `command:`, `trigger:`, `commit:`, `branch:`) — gate runs inside the skill's turn via `AskUserQuestion`
- [ ] `<PREFIX>-dev.md` step 4 invokes `<PREFIX>-deploy` with `target=non-prod` and does not contain the phrase "If a gate is declined"
- [ ] `<PREFIX>-pm.md` has **no** prod-deploy step (no `target=prod`) — prod deploy lives only in the `/code` / `/fix` `--prod` command step; pm's `## Boundaries` says "No deployments"
- [ ] `<PREFIX>-dev.md` step 7 (Hand off) is a one-line pointer to `## Response Requirements`; the structured `## Handoff` block format (`Status: complete | blocked`, Files changed, Deployed, **Roadmap**, Reference Sync, Commit, Notes) lives in a terminal `## Response Requirements` section after `## Boundaries`; step 1.5 tells the agent to report every appended `**Id:**` on that `Roadmap:` field
- [ ] `<PREFIX>-qa.md` step 2 (Address findings) explicitly forbids self-patching ("You do not edit code") and routes fixes back to `<PREFIX>-dev` via blocked-status return
- [ ] `<PREFIX>-qa.md` step 6 (Hand off) is a one-line pointer to `## Response Requirements`; the structured `## Handoff` block format (`Status: signed-off | blocked`, Review, Tests, Reference Sync, Notes) lives in a terminal `## Response Requirements` section after `## Boundaries`
- [ ] `<PREFIX>-pm.md` step 1 (Verify QA evidence) reads `**QA-evidence:**` from the invocation prompt — does **not** grep session jsonl (subagent skill invocations don't reach the parent session)
- [ ] `.claude/commands/code.md` and `fix.md` parse `--prod` and `--no-push` flags in Step 0 and have a final "Deploy to prod (only if `--prod`)" step that invokes `<PREFIX>-deploy target=prod` at the top level after pm
- [ ] `.claude/commands/code.md` and `fix.md` Step 0.5 is a **single** AskUserQuestion call carrying at most Confirm + Ship — the Confirm question states the acceptance statement and the verifications the command derived, and there is **no** Verify picker and **no** Regression question (`regression_mode` defaults to `auto` and is resolved by `<PREFIX>-test` from the changed paths, or pinned by `--regression`); `ship_mode` drives the prod step, whose pre-authorization conditions are verified (not assumed); Step 0 stashes pre-existing WIP; the close-out restores it
- [ ] `<PREFIX>-deploy/SKILL.md` gate contains the Pre-authorization clause (`preauth` accepted only from the top-level command, never inferred)
- [ ] `.claude/commands/code.md` has a `## Done — the close-out report` section defining the five blocks (Verdict · Learned · Status · Open · Emerged) and the closed status vocabulary (`needs you` / `failed` / `not done` / `not proven` / `done` / `proven` / `n/a`), with `done` and `proven` explicitly not interchangeable; `fix.md`, `wrap.md`, `tweak.md`, `revert.md`, `tidy.md` and `pilot.md` each cite `code.md § Done` instead of defining a report shape of their own
- [ ] `code.md`/`fix.md`/`pilot.md` `Entry hygiene:` counts unpushed commits (`rev-list --count @{upstream}..HEAD`) and reports them — nothing else raises held work; `code.md`/`fix.md` `Open deferrals:` counts structurally unprovable entries and lists only the closable ones
- [ ] `code.md`/`fix.md` Prod walk and `pilot.md` Step 3(a2) drain still-open prod-only deferrals covering the shipped paths (`blast`-bounded), not just the task's own carry
- [ ] That section defines **five** blocks in order (Verdict · Learned · Status · Open · Emerged), `Learned` capped at 3 bullets and admitting only what changes the reader's picture; Open's table is three columns with `Next` a runnable command, never a bare roadmap id
- [ ] `<PREFIX>-test/references/custom-tests.md § Execution` pins `last.commit` **once** at the start of the run (not `rev-parse HEAD` per verification) and commits outcomes **as they go**, so a killed agent loses one record rather than the run's
- [ ] `.claude/skills/<PREFIX>-test/scripts/run-checks.py` exists, is **byte-identical** to the plugin's `shared/run-checks.py`, and is tracked by git; `custom-tests.md § Execution` routes the Integration set through `run-checks.py run` in chunks of ≤10 and records **every** type through `run-checks.py record`. The runner must return observations only — if any instruction anywhere lets it emit a `pass`, that is the finding, because a scripted verdict discharges a vacuous check permanently
- [ ] `<PREFIX>-log`'s `**UAT-deferred:**` format requires a spaced dash and the reason each verification could not run; `graph.py` emits `reason` on the `DEFERRED` edge and `open-deferrals` renders it
- [ ] That same section carries the **row-placement test** (*does this need a decision or an action from you now?* → Open naming the command, else Emerged naming its store), the rule that filing is orthogonal to urgency and **an item never appears in both blocks**, the three legal Emerged homes with **no home → the row is Open**, and the **closing line derived from the Open rows** (none → `none — nothing open, safe to start a fresh session`; one → its `Next`; 2+ all carrying ids → `/pilot --items`; 2+ with any unfiled → a goal-shaped `/pilot` naming the set — two or more always batches, never one row at a time)
- [ ] `pilot.md` carries the verdict ladder in Step 2 (`superseded`/`expired`/`moot`/`waiting` concluded by the run, `drifted`/`live`/`judgment` by the user), the unattended rule that a run with nobody present takes only the first two rows, `--gates` in Usage/Step 0/Decompose, `apply:` in the `pilot-lane:` schema, and Step 3 `(a0)` — preflight the apply route, one batched `AskUserQuestion`, answers written to `Decisions:` before any apply, and no `approved` without a cited commit or an `**Addresses:**` id
- [ ] `pilot.md` Step 1's Confirm settles scope only on a store-targeted mission — it lists each claim with its age and current condition and never a disposition, because the only evidence at that moment is the parked evidence; Step 3 `(a0)` skips its question when nothing is left to ask and otherwise leads each row with what the re-measure changed
- [ ] `whats-up.md` Step 2 classifies each parked gate from the `condition` and `age_days` `open-gates` returns — a trigger that has not fired is a Status row, measurable evidence older than the delivery entries since it was parked is `unrecommendable` with `/pilot --gates <name>` as its `Next`, and a preference is recommendable at any age
- [ ] `.claude/commands/pilot.md` Step 0 runs the same `open-deferrals` read as `code.md`, reports it as a line, and folds only the 3+-on-one-blocker escalation into its Confirm question
- [ ] `.claude/commands/code.md` and `fix.md` contain a "Gate policy" section (reversible → proceed + `auto-selected on timeout — not user-confirmed` label; irreversible → park; never present a timeout as consent) and a final "Close out: push + verified scorecard" step (push via `<PREFIX>-deploy` § Push policy; scorecard facts each checked against reality)
- [ ] `<PREFIX>-qa.md` has a `## Invocation modes` section with `mode: initial` (default, full pipeline) and `mode: retest` (skip review, run tests only — for re-runs after a dev fix)
- [ ] `<PREFIX>-test/references/custom-tests.md` has a `## Carrying a prior forward` section (a `pass` whose `last.commit`..`HEAD` diff misses its `paths:` is carried with that range as evidence, reported separately from what was walked, `last:` left untouched) and a `## Splitting a large set across parallel children` section (brief each child inline rather than sending it to read the protocol; bound a child's turns ~60, never the child count; keep verbose output out of context). `<PREFIX>-test/SKILL.md` § Rules says carrying is not narrowing a pinned scope
- [ ] `<PREFIX>-qa.md` handoff vocabulary is `signed-off | signed-off-with-deferrals | blocked` with an `Evidence:` field, a `Fanned out:` field, and an optional `UAT-deferred:` field; step 2 allows direct fixes for **non-source** findings only; step 5 maps environmental-only blocks to `signed-off-with-deferrals`
- [ ] `<PREFIX>-pm.md` step 1 accepts both signed-off statuses; step 2 uses the feature commit for the log hash and carries `UAT-deferred:` items
- [ ] `<PREFIX>-deploy/SKILL.md` contains a `## Push policy` section (CI-coupled push = shipping; post-push CI watch + health check) and its gate returns `gate: unanswered — parked` on timeout
- [ ] `.claude/commands/code.md` Step 2 parses dev `## Handoff` Status, branches on qa Status (including `signed-off-with-deferrals` → user-gated defer), and re-spawns qa with `mode=retest` after a dev fix; Step 3 passes the qa handoff verbatim to pm under `**QA-evidence:**` plus the `Feature commit:` hash
- [ ] `.claude/commands/fix.md` Step 3 has the same qa-branching + retest logic; Step 4 passes `**QA-evidence:**` + `Feature commit:` to pm
- [ ] Both commands contain the salvage protocol (dead subagent → inspect tree, SendMessage/re-spawn with salvage prompt — no top-level role absorption) and the "no top-level governed edits while a subagent runs" rule
- [ ] `.claude/commands/tweak.md` defines the lane rules (inline verification, no per-commit log) and the mandatory batched close-out at exit; `.claude/commands/revert.md` uses `git revert` (never reset) + scoped re-verify + logged reversal
- [ ] `.claude/commands/tidy.md` carries the history-probe rule (no `discard`/`ignore` without a probe backing it), the 5-term disposition vocabulary, `discard` as a named stash (never `checkout --`/`rm`), and `git branch -d` never `-D`
- [ ] Both `<PREFIX>-dev.md` and `<PREFIX>-qa.md` end with a `## Response Requirements` section (the **last** section of the file) containing the imperative "Every response MUST end with the `## Handoff` block" — terminal placement leverages prompt-recency so agents reliably emit the block
- [ ] No placeholder text (`<PROJECT>`, `<PREFIX>`, `<fill in>`, etc.) left in any installed file — prompt the user to fill these in

Report a summary: what was installed, what stubs need filling in, and how to test the hooks:
1. Try editing a file in an owned path without the skill loaded → should see the skill gate message
2. Try running `pnpm add some-package` without `<PREFIX>-skill` loaded → should see the dependency gate message
3. Try invoking `<PREFIX>-qa` with uncommitted changes → should see the pre-handoff gate message
