---
name: install
description: Install a 3-agent delivery workflow (dev → qa → pm, domain skills, skill-guard hooks, slash commands, roadmap tracking) on a fresh project. Trigger when the user wants to bootstrap a multi-agent workflow, set up an AI agent pipeline on a new project, add skill-guard hooks, or install the dev-workflow on a fresh repo. Claude Code only.
user-invocable: false
---

# install

> **Hard gate.** If `.claude/agents/<PREFIX>-dev.md` exists for any prefix, abort and tell the user: "An existing dev-workflow install was detected. Run `/dev-workflow:upgrade` instead." Do **not** continue to Phase 1.

Installs a multi-agent delivery workflow on a new project in five phases: discover project structure → create lifecycle infrastructure → wire domain skills + hooks → update CLAUDE.md → verify.

**What gets installed:**
- 4 agents: `<PREFIX>-dev`, `<PREFIX>-qa`, `<PREFIX>-pm` (the pipeline) + `<PREFIX>-verify` (the verification child qa fans out to; Sonnet, 60-turn cap, no CLAUDE.md — all frontmatter)
- 8 lifecycle skills: `<PREFIX>-log`, `<PREFIX>-review`, `<PREFIX>-debug`, `<PREFIX>-deploy`, `<PREFIX>-test`, `<PREFIX>-skill`, `<PREFIX>-docs`, `<PREFIX>-graph`
- 14 entry-point skills: `/code` + `/fix` + `/pilot` + `/tweak` + `/audit` + `/revert` + `/tidy` + `/design` (conditional on design skill) + `/whats-up` + `/roadmap` + `/blueprint` + `/wrap` + `/handover` + `/proceed`
- `docs/roadmap.md` stub — source of truth for open items; tracked by `<PREFIX>-dev` (new entries) and `<PREFIX>-pm` (status updates)
- Domain skills: one per substantive source dir, derived from discovery (not hardcoded)
- `.claude/hooks/governed-paths.conf` — single source of truth for path→skill ownership (incl. per-skill self-ownership entries), `DEPLOY_PATHS`, `REF_WATCH`, `DEPENDENCY_MANIFESTS`, and `COPY_PATHS`; sourced by skill-guard, path-coverage-check, ref-sync-check, and close-out-gate
- `.claude/hooks/skill-guard.sh` — PreToolUse Edit+Write: blocks edits to owned paths without skill loaded (session-scoped markers)
- `.claude/hooks/path-coverage-check.sh` — PreToolUse Write: blocks new files in governed roots not covered by any pattern
- `.claude/hooks/dependency-guard.sh` — PreToolUse Bash: blocks `pnpm add` / `pip install` without `<PREFIX>-skill` loaded
- `.claude/hooks/package-edit-guard.sh` — PreToolUse Edit: blocks direct dependency additions to `package.json` without `<PREFIX>-skill`
- `.claude/hooks/pre-handoff-check.sh` — PreToolUse Skill + Task/Agent: blocks `<PREFIX>-qa` invocation (skill call or subagent spawn) if uncommitted changes exist, lint fails, or typecheck fails
- `.claude/hooks/close-out-gate.sh` — PreToolUse Bash: blocks `git push` while commits after the last delivery-log entry touch governed/deploy paths (iterate-lane close-out enforcement; `CLOSEOUT_OVERRIDE=1` escape hatch)
- `.claude/hooks/ref-sync-check.sh` — PostToolUse Bash: warns after `git commit` on reference-worthy drift (structural changes or `REF_WATCH` matches; modify-only cosmetic commits stay silent) on deploy-mechanism drift without `deploy-config.yaml` updates, on dependency drift without `vex.yaml`, and on an em dash added to user-facing copy (`COPY_PATHS`); warnings reach the model as `additionalContext`
- `.claude/hooks/skill-mark.sh` — PostToolUse Skill: records invoked skills to a session-scoped marker
- `.claude/hooks/post-commit.sh` — PostToolUse Bash: reminds to run `<PREFIX>-log` after every commit
- `.claude/graph/graph.py` — delivery-graph projector + query engine (copied verbatim from `../../shared/graph.py`); `edges.jsonl` is generated and gitignored
- `.claude/skills/<PREFIX>-test/scripts/run-checks.py` — batched execution of resolved Integration commands and `last:` recording for every type (copied verbatim from `../../shared/run-checks.py`); returns observations, never verdicts
- `~/.claude/usage-snapshot.sh` — **outside the repo, opt-in** (Phase 3 Step 5): wraps the status line so a run can read the account's remaining allowance, writing one file per session under `~/.claude/usage/` and aggregating them on `--read`. Account-scoped, so one machine needs it once
- `.claude/settings.json` — wires all hooks
- `CLAUDE.md` workflow sections

**Template files (read before Phase 2 and 3):**
- `../../shared/tpl-agents.md` — tosk-dev, tosk-qa, tosk-pm, tosk-verify templates
- `../../shared/tpl-lifecycle.md` — 8 lifecycle skill templates
- `../../shared/graph.py` — the delivery-graph projector, copied verbatim to `.claude/graph/graph.py`
- `../../shared/run-checks.py` — the verification runner/recorder, copied verbatim to `.claude/skills/<PREFIX>-test/scripts/run-checks.py`
- `../../shared/usage-snapshot.sh` — the status-line allowance tee, copied verbatim to `~/.claude/usage-snapshot.sh` (opt-in, Phase 3 Step 5)
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
- 4 agents: <PREFIX>-dev, <PREFIX>-qa, <PREFIX>-pm, <PREFIX>-verify
- 8 lifecycle skills: <PREFIX>-log, <PREFIX>-review, <PREFIX>-debug, <PREFIX>-deploy, <PREFIX>-test, <PREFIX>-skill, <PREFIX>-docs, <PREFIX>-graph
- 1 design skill: <PREFIX>-design  ← omit if no frontend category
- <N> domain skills: <comma-separated list>
- <N> slash commands: /code, /fix, /pilot, /tweak, /audit, /revert, /tidy, /whats-up, /roadmap, /blueprint, /wrap[, /design if frontend]
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
.claude/agents/<PREFIX>-verify.md     ← from tpl-agents.md § tosk-verify
.claude/skills/<PREFIX>-log/SKILL.md
.claude/skills/<PREFIX>-review/SKILL.md       ← also create references/{code-review-reception,requesting-code-review,issuing-findings,security-review}.md and references/vex.yaml (`statements: []`) (see tpl-lifecycle.md § tosk-review)
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
.claude/loop.md                               ← from tpl-commands.md § loop.md — what a bare `/loop <interval>` runs: the standing mission
.claude/skills/<PREFIX>-design/SKILL.md       ← only if a frontend/website domain skill was confirmed in Phase 1c; also create references/design-tokens.md, references/ux-patterns.md and references/voice.md stubs
.claude/skills/code/SKILL.md                  ← from tpl-commands.md § /code, substitute <PROJECT> and <PREFIX>
.claude/skills/code/references/pipeline.md    ← from tpl-commands.md § /code — references/pipeline.md (Steps 1–3 shared by /code, /fix, /pilot)
.claude/skills/code/references/close-out.md   ← from tpl-commands.md § /code — references/close-out.md (the report contract every lane cites)
.claude/skills/fix/SKILL.md                   ← from tpl-commands.md § /fix (a thin delta over the code skill)
.claude/skills/pilot/SKILL.md                 ← from tpl-commands.md § /pilot
.claude/skills/pilot/references/{lanes,allowance,verdicts,close-out}.md  ← from tpl-commands.md § /pilot — references/*
.claude/skills/tweak/SKILL.md                 ← from tpl-commands.md § /tweak
.claude/skills/audit/SKILL.md                 ← from tpl-commands.md § /audit
.claude/skills/revert/SKILL.md                ← from tpl-commands.md § /revert
.claude/skills/tidy/SKILL.md                  ← from tpl-commands.md § /tidy
.claude/skills/whats-up/SKILL.md              ← from tpl-commands.md § /whats-up
.claude/skills/roadmap/SKILL.md               ← from tpl-commands.md § /roadmap
.claude/skills/blueprint/SKILL.md             ← from tpl-commands.md § /blueprint; keep its `model:` line — the planning lane runs on the strongest model
.claude/skills/wrap/SKILL.md                  ← from tpl-commands.md § /wrap
.claude/skills/handover/SKILL.md              ← from tpl-commands.md § /handover
.claude/skills/proceed/SKILL.md               ← from tpl-commands.md § /proceed
.claude/skills/design/SKILL.md                ← from tpl-commands.md § /design (only if a design domain skill was discovered in Phase 1)
```

### Seed `<PREFIX>-design/references/ux-patterns.md` and `voice.md`

Only when a `<PREFIX>-design` skill was confirmed. Create it from the stub in `../../shared/tpl-lifecycle.md § <PREFIX>-design/SKILL.md`, then fill the two `§ Iconography` fields that are discoverable **now**: the icon set the project already depends on (read the manifest for the dependency and one call site for the import convention — never name a set the project doesn't have), and the directory generated assets belong in (the frontend's existing static/asset dir). An empty field is honest; an invented one sends every future icon to the wrong place. `§ Inventory` stays empty — it fills as `<PREFIX>-design` runs, one row per pattern decision. `§ Baseline states` ships as written.

Create `references/voice.md` from the same section's stub. `§ Rules` ships as written; `§ Vocabulary` and `§ Won't do` stay empty — they fill as `<PREFIX>-design` writes copy, and a guessed row would put a word on the denylist the product actually uses.

### Populate `deploy-config.yaml`

`.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` is **populated** during install — never left as a stub. Schema and rules: `../../shared/tpl-domain-skill.md § deploy-config.yaml schema`.

**Source from the category map.** The IaC, CI/CD, Build tooling, and Deployment scripts/config rows of `CATEGORY_MAP` already list the paths and tools detected in Phase 1c. For each, **read the actual file at its path** and derive yaml fields by purpose — do not apply tool names as a lookup table:

- **Trigger mechanism** (a workflow file, CI config, Makefile target): read it for env names, job triggers, and deploy commands. If it accepts parameters that select an environment, those parameters are env names. If it triggers a CD pipeline, that pipeline action is the deploy command; set `trigger: ci`. **If the same trigger file fires deploys for multiple components** (e.g. a single `deploy.yml` with `deploy-backend` + `deploy-frontend` jobs gated by `paths:` or `if:` conditions), still derive one `deploy:` entry per component, but emit the line `# TODO: split into deploy-<component>.yml — see tpl-domain-skill.md § deploy-config.yaml schema rules` above the first shared component block in the generated yaml. The flag travels into the repo as a visible reminder; it does not block the install.
- **Script file** (shell, Python, etc.): `deploy: "./<script>"` + `trigger: manual`. Read the script for any env-conditional branching to split into multiple envs.
- **Platform config file** (any config that names a cloud target or embeds a deploy CLI invocation): extract the deploy command from the config itself; extract the URL if present.
- **Run script in project manifest** (a `dev` or `start` entry in package.json, Pipfile, Procfile, pyproject.toml, etc.): use as `envs.local.run` (a serve-env). Read the command for port flags to populate `envs.local.url`. If the command binds every interface — `0.0.0.0`, a bare `--host`, a `host: true` in the framework config — add an explicit loopback flag to `run` (the schema's loopback rule), and say so in the install report.
- **Run-to-completion job** (a scheduled function, a cron entry, a batch or worker entrypoint that exits when it finishes — no server, no port): use as `envs.<name>.invoke` (an invoke-env), and write **no** `url`. Inventing one produces an address nothing answers at, which then reads as a component that is down. An invoke-env is never a verification target, so a component that also has a servable form still needs its own serve-env or ship-env.
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
- Default `verify:` per component: `local` for `frontend`; the first non-prod ship-env for `backend` if one was detected, else `local`. A component whose only envs are invoke-envs gets **no `verify:` line** — a job that runs to completion is not proven by being reachable.
- **Frontend with no own dev server**: if a Frontend category exists with no independent local dev server detected (no FE-specific dev/start script in the project manifest, no FE framework dev-server config) and a Backend category serves the frontend's static assets, share the backend's `envs.local` serve-env (one URL, two components). Only when nothing serves the frontend locally set `verify: <ship-env>` and omit `envs.local`.
- Populate an `envs.local` serve-env (`run` + `url`) for **every component that can run locally** — frontends and backends alike. It is the zero-cost non-prod target typed verifications resolve to when no cloud non-prod env exists; a component that can be *served* locally must never be left with no non-prod env that declares a url. Required when `verify: local`. A component that only ever runs to completion has no servable form, so this does not apply to it.

**Propose** the populated YAML to the user. Wait for confirmation or edits. Prompt for missing values explicitly (e.g. "I couldn't find a prod URL for the backend — what is it?"). Never write placeholder text like `<fill in>` into the yaml.

**Write** to `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`.

If the project has no deploy mechanism at all (no IaC/CI/CD/Build/Deployment categories AND no local run command anywhere), still create the file with an empty `components: {}` map and a leading comment `# No deploy mechanism detected at install time — invoke <PREFIX>-skill to add components and envs when the project gains a deploy story.` This keeps the contract uniform and lets the deploy skill no-op cleanly.

### Pin critical packages and add the start-up check

For each component with a ship-env, apply `<PREFIX>-deploy`'s `## Build inputs` (`../../shared/tpl-lifecycle.md § tosk-deploy/SKILL.md`). Read the packages its deployed entrypoints import and propose the critical set by that section's four signals, one reason per package, plus the start-up check its build will run — in the same confirmation as the yaml. Never pin on inference alone: the user confirms the set. Pin each at the version the running artifact uses (or the last good build), not the newest release, and add the check to the build file, in one commit. A component that already installs from a committed lockfile needs only the check.

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

A plan written by `/blueprint` is one umbrella item plus children that carry `**Parent:**` (the
umbrella's id) and `**Depends on:**` (sibling ids, or `nothing`). Readers nest children under their
umbrella; the umbrella closes when its last child does.

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
.claude/pilot/
.claude/handovers/
```
The index is generated, churns on every delivery, and is rebuilt in under a second — committing it
would add noise to every diff for no recoverable value. `__pycache__/` appears whenever anything
imports `graph.py` rather than running it as a script. `.claude/pilot/` holds `/pilot`'s run
markers (`running`, `last-run.json`, `limit-hit`) — per-machine facts about *when* a run happened,
never *what* it decided (that lives in the log and the roadmap), so nothing in it belongs in the repo.

**`graph.py` itself must be committed** — stage it explicitly:
```bash
git add .claude/graph/graph.py .claude/loop.md .gitignore
```
An untracked `graph.py` has no protection: any `git clean`, a `/tidy` discard, or a stray `rm -rf`
deletes it, and because every call site is required to fall back silently, the workflow keeps
running with the graph quietly gone and **no signal that it was ever there**. Tracking it is the
only thing that makes its absence visible.

Then run `python3 .claude/graph/graph.py build` once to prove the projector works against this
project's artifacts. On a fresh repo it correctly reports `0 edges · 0/0 log entries parsed`.

Also create `docs/workflow.md` if not present — read `references/workflow-template.md` and generate it with real content using values confirmed in Phase 1 (not a stub), substituting `<DOMAIN_SKILL_TABLE>` as that file says.

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

Read `references/hooks.md` now and run its six steps in order: `governed-paths.conf`, the hook scripts, `settings.json`, the standing mission on a schedule, the opt-in allowance snapshot, the one-line auto-compact instruction. Nothing in it is optional to read — the substitution rules for the conf and the bare-shell rule for `pre-handoff-check.sh` are where installs go wrong.

---

## Phase 4 — Wire CLAUDE.md

Read `../../shared/tpl-domain-skill.md` § "Project file sections" for the section templates.

Upsert the following sections in `CLAUDE.md` (add if missing, replace if present):

- `## Plan Mode` — two bullets: (1) `docs/workflow.md` as the source of truth for the delivery pipeline; (2) the one-task → `/code`, several-tasks → `/blueprint` routing from the template
- `## Agents` — the pipeline line plus the routing paragraph (pipeline-shaped work → `/code`/`/fix`, iterative rounds → `/tweak`) from the template
- `## Skills` — "Path→skill ownership is defined in `.claude/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically."
- `## Roadmap` — single line: `docs/roadmap.md` is the source of truth for open items.
- `## Secrets` — the never-through-chat rule from the template
- `## Linting` — only add if lint commands were discovered in Phase 1; omit entirely if none found (no `<fill in>` stub)

---

## Phase 5 — Verify

Read `references/verify.md` now and walk every line before declaring done. A line that cannot be checked here is reported as not checked, never as passed.
