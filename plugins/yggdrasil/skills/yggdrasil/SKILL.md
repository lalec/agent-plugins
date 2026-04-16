---
name: yggdrasil
description: Install the Yggdrasil 3-agent delivery workflow (dev → qa → pm, domain skills, skill-guard hook, 4 slash commands, roadmap tracking) on any new project. Trigger when the user wants to bootstrap a multi-agent workflow, set up an AI agent pipeline on a new project, add skill-guard hooks, or install Yggdrasil on a fresh repo — even if they just say "set up the workflow here", "add agents to this project", or "bootstrap this project with AI agents". Handles both Claude Code (.claude/ / CLAUDE.md) and Gemini CLI (.gemini/ / GEMINI.md) — detects CLI target automatically.
---

# yggdrasil

Installs the Yggdrasil multi-agent delivery workflow on a new project in five phases: detect CLI target → discover project structure → create lifecycle infrastructure → wire domain skills + hooks → update project file.

**What gets installed:**
- 3 orchestrator agents: `<PREFIX>-dev`, `<PREFIX>-qa`, `<PREFIX>-pm`
- 6 lifecycle skills: `<PREFIX>-log`, `<PREFIX>-review`, `<PREFIX>-debug`, `<PREFIX>-test`, `<PREFIX>-skill`, `<PREFIX>-docs`
- 5 slash commands: `/code` + `/fix` + `/design` (conditional on design skill) + `/roadmap` + `/log` (always) — `.md` format for Claude Code, `.toml` for Gemini CLI (except `/design` which is Claude Code only)
- `docs/roadmap.md` stub — source of truth for open items; tracked by tosk-dev (new entries) and tosk-pm (status updates)
- Domain skills: one per substantive source dir, derived from discovery (not hardcoded)
- `<CONFIG_DIR>/hooks/governed-paths.conf` — single source of truth for path→skill ownership; sourced by skill-guard and path-coverage-check
- `<CONFIG_DIR>/hooks/skill-guard.sh` — PreToolUse Edit+Write: blocks edits to owned paths without skill loaded
- `<CONFIG_DIR>/hooks/path-coverage-check.sh` — PreToolUse Write: blocks new files in governed roots not covered by any pattern
- `<CONFIG_DIR>/hooks/dependency-guard.sh` — PreToolUse Bash: blocks `pnpm add` / `pip install` without `<PREFIX>-skill` loaded
- `<CONFIG_DIR>/hooks/package-edit-guard.sh` — PreToolUse Edit: blocks direct dependency additions to `package.json` without `<PREFIX>-skill` (closes the Edit-tool bypass)
- `<CONFIG_DIR>/hooks/pre-handoff-check.sh` — PreToolUse Skill: blocks `<PREFIX>-qa` invocation if uncommitted changes exist, lint fails, or typecheck fails
- `<CONFIG_DIR>/hooks/ref-sync-check.sh` — PostToolUse Bash: warns after `git commit` if `src/` or `lambda/` changed but no reference files updated
- `<CONFIG_DIR>/hooks/skill-mark.sh` — PostToolUse Skill: records which skills were invoked each session
- `<CONFIG_DIR>/hooks/post-commit.sh` — PostToolUse Bash: reminds to run `<PREFIX>-log` after every commit
- `<CONFIG_DIR>/settings.json` — wires all hooks (Claude Code and Gemini CLI, written automatically for both)
- Project file sections (CLAUDE.md or GEMINI.md)

**Template files (read before Phase 2 and 3):**
- `references/tpl-agents.md` — tosk-dev, tosk-qa, tosk-pm templates
- `references/tpl-lifecycle.md` — 6 lifecycle skill templates
- `references/tpl-skill-guard.md` — all hook templates + governed-paths.conf + settings.json
- `references/tpl-domain-skill.md` — domain skill stub + project file sections
- `references/tpl-commands.md` — `/code` and `/fix` slash command templates

---

## Phase 1 — Detect + Discover

### 1a. Detect CLI target

Check the current working directory:

| Condition | Result |
|---|---|
| Both (`.gemini/` or `GEMINI.md`) AND (`.claude/` or `CLAUDE.md`) present | Ask user which CLI to target |
| Only `.gemini/` or `GEMINI.md` | Gemini CLI: `CONFIG_DIR=.gemini`, `PROJECT_FILE=GEMINI.md` |
| Only `.claude/` or `CLAUDE.md` | Claude Code: `CONFIG_DIR=.claude`, `PROJECT_FILE=CLAUDE.md` |
| Neither | Ask: "Claude Code or Gemini CLI?" |

Derive `PROJECT` from the directory name (`basename $PWD`).

Ask the user for a skill/agent prefix:

> "What prefix should I use for agents and skills? (e.g. `myapp` → `myapp-dev`, `myapp-qa`, `myapp-backend`)"
> Default suggestion: the project name lowercased and shortened if long.

Capture as `PREFIX`. All agents, lifecycle skills, and domain skills will be named `<PREFIX>-<name>`.

### 1b. Read the project

1. List top-level directories and files
2. Read `<PROJECT_FILE>` if it exists
3. Note: language/stack, source dirs, infra dirs, docs files, existing linting commands

### 1c. Propose domain skills

For each **substantive** source directory (e.g. `src/`, `lambda/`, `agents/`, `infra/`, `frontend/`, `backend/`, `packages/`), propose:
- Skill name: `<PREFIX>-<dirname>` (or a cleaner name if the dir name is ambiguous)
- Owned path pattern: the dir prefix + any key config files it owns

**Design skill rule:** If the project has any HTML/CSS/JS website, UI framework, or frontend domain skill, also propose a `<PREFIX>-design` skill. This is always a separate skill from the frontend skill — the frontend skill owns files, the design skill owns visual decisions (palette, tokens, typography). The design skill owns only specific design token files (e.g. `^src/tokens\.css$`, `^src/theme\.css$`) — list those before the frontend catch-all in `PATH_MAP` so they take priority. If no dedicated token file exists, add it to the table with `—` in the Owns column and it gets no PATH_MAP entry.

Present as a table and **wait for user confirmation** before creating anything:

```
| Skill              | Owns                              |
|--------------------|-----------------------------------|
| <PREFIX>-backend   | ^lambda/ ^src/lib/api\.ts$        |
| <PREFIX>-frontend  | ^src/ ^astro\.config\. ^tsconfig  |
| <PREFIX>-deploy    | ^infra/ ^\.github/ ^package\.json |
```

User can rename skills or adjust path patterns. Capture the confirmed mapping as:
- `DOMAIN_SKILLS[]` — array of skill names
- `DOMAIN_PATTERNS[]` — parallel array of owned path regex patterns (one per skill)

---

## Phase 2 — Install lifecycle infrastructure

Read `references/tpl-agents.md` and `references/tpl-lifecycle.md` now.

For each template, substitute:
- `<PROJECT>` → the project name derived in Phase 1
- `<PREFIX>` → the prefix confirmed in Phase 1a
- `<DOMAIN_SKILL_MAPPING>` → the confirmed skill→path table from Phase 1c
- `<PROJECT_ENCODED>` → `$(echo "$PWD" | sed 's|/|-|g')` (for `<PREFIX>-log` grep)

Create these files (skip if already present, offer to overwrite if stale):

```
<CONFIG_DIR>/agents/<PREFIX>-dev.md        ← from tpl-agents.md § tosk-dev
<CONFIG_DIR>/agents/<PREFIX>-qa.md         ← from tpl-agents.md § tosk-qa
<CONFIG_DIR>/agents/<PREFIX>-pm.md         ← from tpl-agents.md § tosk-pm
<CONFIG_DIR>/skills/<PREFIX>-log/SKILL.md
<CONFIG_DIR>/skills/<PREFIX>-review/SKILL.md
<CONFIG_DIR>/skills/<PREFIX>-debug/SKILL.md        ← also create 4 reference files + scripts (see tpl-lifecycle.md § debug)
<CONFIG_DIR>/skills/<PREFIX>-test/SKILL.md
<CONFIG_DIR>/skills/<PREFIX>-skill/SKILL.md
<CONFIG_DIR>/skills/<PREFIX>-skill/references/skill-manifest.md  ← stub; populate with all lifecycle + domain skills installed in this run
<CONFIG_DIR>/skills/<PREFIX>-docs/SKILL.md
<CONFIG_DIR>/skills/<PREFIX>-design/SKILL.md       ← only if a frontend/website domain skill was confirmed in Phase 1c; also create references/design-tokens.md stub
Claude Code:
<CONFIG_DIR>/commands/code.md          ← from tpl-commands.md § /code (Claude Code), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/fix.md           ← from tpl-commands.md § /fix (Claude Code), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/roadmap.md       ← from tpl-commands.md § /roadmap (Claude Code), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/log.md           ← from tpl-commands.md § /log (Claude Code), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/design.md        ← from tpl-commands.md § /design (Claude Code only), substitute <PROJECT> and <PREFIX>
                                          (only if a design domain skill was discovered in Phase 1)

Gemini CLI:
<CONFIG_DIR>/commands/code.toml        ← from tpl-commands.md § /code (Gemini CLI), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/fix.toml         ← from tpl-commands.md § /fix (Gemini CLI), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/roadmap.toml     ← from tpl-commands.md § /roadmap (Gemini CLI), substitute <PROJECT> and <PREFIX>
<CONFIG_DIR>/commands/log.toml         ← from tpl-commands.md § /log (Gemini CLI), substitute <PROJECT> and <PREFIX>
```

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
  <PREFIX>-dev ── domain skills ── implement ── deploy ── Reference Sync
      │
      ▼
  <PREFIX>-qa  ── <PREFIX>-review ── <PREFIX>-test ── sign-off
      │
      ▼
  <PREFIX>-pm  ── <PREFIX>-log ── docs update
```

## Agents

| Agent | Role |
|---|---|
| `<PREFIX>-dev` | Design → implement → deploy → Reference Sync → hand off to `<PREFIX>-qa` |
| `<PREFIX>-qa` | Code review (`<PREFIX>-review`) + tests (`<PREFIX>-test`) → sign-off → hand off to `<PREFIX>-pm` |
| `<PREFIX>-pm` | Verify QA phases ran → write delivery log (`<PREFIX>-log`) → update docs if needed |

## Skills

### Lifecycle

| Skill | Purpose |
|---|---|
| `<PREFIX>-log` | Appends delivery log entries to `docs/project-log.md` |
| `<PREFIX>-review` | Code review reception, reviewer dispatch, verification gates |
| `<PREFIX>-debug` | Systematic debugging — four-phase root cause investigation |
| `<PREFIX>-test` | Unit, smoke, and E2E testing |
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

Read `references/tpl-domain-skill.md` and `references/tpl-skill-guard.md` now.

### 3a. Domain skills

For each confirmed domain skill `<PREFIX>-<name>`:

1. Create `<CONFIG_DIR>/skills/<PREFIX>-<name>/SKILL.md` from stub template (in `tpl-domain-skill.md`), substituting:
   - `<SKILL_NAME>` → `<PREFIX>-<name>`
   - `<OWNED_PATHS>` → the confirmed path pattern for this skill

2. Determine typed stub files for this skill based on signals detected in Phase 1 for its owned paths:

   | Signal in owned paths | Stub to create |
   |---|---|
   | REST/GraphQL API (FastAPI, Express, Flask, Hono) | `api-schema.md` |
   | Database (Postgres, DynamoDB, Firestore, MySQL, Mongo) | `db-schema.md` |
   | Infra/deploy (Terraform, CDK, serverless.yml, Dockerfile) | `deploy-config.md` |
   | Cloud resources (AWS, GCP, Azure — ARNs, bucket names) | `resources.md` |
   | Frontend framework (React, Astro, Vue, Svelte) | `component-manifest.md` |
   | Auth patterns (OAuth, JWT, session middleware) | `auth-patterns.md` |
   | SDK / third-party integrations | `patterns.md` |

   Rules:
   - Create only the stubs whose signals are present for this skill — not all 7
   - Always create `resources.md` when cloud resources are present (even alongside others)
   - Fall back to a single `resources.md` if no specific signal matches

   Create each stub as `<CONFIG_DIR>/skills/<PREFIX>-<name>/references/<stub-file>` with only a `# Title` header and one `<!-- Fill in: ... -->` comment (see `tpl-domain-skill.md` § Domain skill resources stubs for content).

   Use the created stub files to generate `<REFERENCE_SYNC_CHECKLIST>` and `<REFERENCES_LIST>` substitutions for this skill's SKILL.md (one entry per stub).

### 3b. Hooks + governed-paths.conf + settings.json

Read `tpl-skill-guard.md` for all templates.

**Step 1 — Create `governed-paths.conf`**

Create `<CONFIG_DIR>/hooks/governed-paths.conf` from the template in `tpl-skill-guard.md § governed-paths.conf`, substituting:
- `<CONFIG_DIR_PREFIX>` → `^\.claude/` or `^\.gemini/`
- `<GOVERNED_ROOTS>` → ERE alternation of the **actual top-level source/asset directories** found in Phase 1b (e.g. `^(src/|public/)`). **Never use extension globs** (e.g. `.*\.(html|css|js)$`) — these match files outside the project directory (such as `/tmp/`), defeating the guard. Root-level files like `index.html` are owned via explicit `PATH_MAP` entries, not via `GOVERNED_ROOTS`.
- `<DOMAIN_SKILL_PATTERNS>` → one `'PATTERN:SKILL'` entry per confirmed domain skill, plus the standard catch-alls at the end (see `tpl-skill-guard.md § How to generate governed-paths.conf`)

This is the **only** file that should contain path→skill mappings. Do not duplicate patterns in hook scripts.

**Step 2 — Create hook scripts**

Create all 8 hooks from their templates in `tpl-skill-guard.md`. Substitute `<PROJECT_DIR_VAR>`, `<CONFIG_DIR>`, `<PREFIX>` throughout:

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
chmod +x <CONFIG_DIR>/hooks/skill-guard.sh
chmod +x <CONFIG_DIR>/hooks/path-coverage-check.sh
chmod +x <CONFIG_DIR>/hooks/dependency-guard.sh
chmod +x <CONFIG_DIR>/hooks/package-edit-guard.sh
chmod +x <CONFIG_DIR>/hooks/pre-handoff-check.sh
chmod +x <CONFIG_DIR>/hooks/ref-sync-check.sh
chmod +x <CONFIG_DIR>/hooks/skill-mark.sh
chmod +x <CONFIG_DIR>/hooks/post-commit.sh
```

**Step 3 — Wire settings.json** (both CLIs)

- **Claude Code:** use `tpl-skill-guard.md § settings.json (Claude Code)`, substituting `<CONFIG_DIR>`.
- **Gemini CLI:** use `tpl-skill-guard.md § settings.json (Gemini CLI)`, substituting `<CONFIG_DIR>`.

For both CLIs: if the file does not exist, create it from the template. If it already exists, merge the `hooks` key — add all hook entries without removing unrelated settings. Do not tell the user to wire hooks manually; write the file in this step.

---

## Phase 4 — Wire project file

Read `references/tpl-domain-skill.md` § "Project file sections" for the section templates.

Upsert the following sections in `<PROJECT_FILE>` (add if missing, replace if present):

- `## Plan Mode` — single bullet pointing to `docs/workflow.md` as the source of truth for the delivery pipeline
- `## Docs` — explicit list of what triggers a `docs/workflow.md` update: agents, skills, commands, hooks, settings.json
- `## Agents` — `<PREFIX>-dev` / `<PREFIX>-qa` / `<PREFIX>-pm` one-liner each + "For any non-trivial task, invoke `<PREFIX>-dev` to start."
- `## Skills` — "Path→skill ownership is defined in `<CONFIG_DIR>/hooks/governed-paths.conf` — edit that file to add or change path ownership. Both `skill-guard.sh` and `path-coverage-check.sh` source it automatically."
- `## Roadmap` — explain that `docs/roadmap.md` is the source of truth for open items; format: **Category** (improvement | dogfood | integration | tech-debt), **Priority** (high | medium | low), **Status** (open | in-progress | done · YYYY-MM-DD), **Added** (YYYY-MM-DD HH:MM). `<PREFIX>-dev` appends new entries autonomously; `<PREFIX>-pm` advances status after delivery.
- `## Linting` — only add if lint commands were discovered in Phase 1; omit entirely if none found (no `<fill in>` stub)
- `## Git` — two rules only: group interdependent changes in the same commit; commit messages: single short line, no body, no Co-Authored-By

---

## Phase 5 — Verify

Walk the checklist before declaring done:

- [ ] `<CONFIG_DIR>/agents/` has `<PREFIX>-dev.md`, `<PREFIX>-qa.md`, `<PREFIX>-pm.md`
- [ ] `<CONFIG_DIR>/skills/` has all 6 lifecycle skills + all confirmed domain skills, all named `<PREFIX>-*`
- [ ] `<CONFIG_DIR>/skills/<PREFIX>-skill/references/skill-manifest.md` exists and lists all installed lifecycle and domain skills
- [ ] Claude Code: `<CONFIG_DIR>/commands/code.md`, `fix.md`, `roadmap.md`, and `log.md` exist (markdown format, `$ARGUMENTS`)
- [ ] `<CONFIG_DIR>/skills/<PREFIX>-debug/` has SKILL.md + `references/systematic-debugging.md`, `references/root-cause-tracing.md`, `references/defense-in-depth.md`, `references/verification.md` + `scripts/find-polluter.sh` (executable) + `scripts/find-polluter.test.md`
- [ ] Claude Code: `<CONFIG_DIR>/commands/design.md` exists if a frontend/website domain skill was confirmed in Phase 1c
- [ ] If `<PREFIX>-design` was created: `<CONFIG_DIR>/skills/<PREFIX>-design/SKILL.md` and `references/design-tokens.md` exist; `/design` command invokes `<PREFIX>-design` (not the frontend skill)
- [ ] Gemini CLI: `<CONFIG_DIR>/commands/code.toml`, `fix.toml`, `roadmap.toml`, and `log.toml` exist (TOML format, `{{args}}`)
- [ ] Neither command file contains stale project or prefix references — all use substituted values
- [ ] `<CONFIG_DIR>/hooks/governed-paths.conf` exists and has `GOVERNED_ROOTS` (directory prefixes only, no extension globs) + `PATH_MAP` with one entry per domain skill + standard catch-alls
- [ ] `<CONFIG_DIR>/hooks/skill-guard.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns
- [ ] `<CONFIG_DIR>/hooks/path-coverage-check.sh` is executable and sources `governed-paths.conf` — contains NO hardcoded path patterns
- [ ] `<CONFIG_DIR>/hooks/dependency-guard.sh` is executable and checks for `<PREFIX>-skill` in session marker
- [ ] `<CONFIG_DIR>/hooks/package-edit-guard.sh` is executable and checks for `<PREFIX>-skill` in session marker
- [ ] `<CONFIG_DIR>/hooks/pre-handoff-check.sh` is executable, fires on `<PREFIX>-qa`, checks dirty tree + lint + typecheck
- [ ] `<CONFIG_DIR>/hooks/ref-sync-check.sh` is executable and warns after commits that touch src/lambda without reference updates
- [ ] `<CONFIG_DIR>/hooks/skill-mark.sh` is executable
- [ ] `<CONFIG_DIR>/hooks/post-commit.sh` is executable and references `<PREFIX>-log`
- [ ] `<CONFIG_DIR>/settings.json` exists and wires all 8 hooks across all event types — Claude Code uses `PreToolUse`/`PostToolUse` + `Edit`/`Write`/`Bash`/`Skill` matchers; Gemini CLI uses `BeforeTool`/`AfterTool` + `replace`/`write_file`/`run_shell_command`/`activate_skill` matchers
- [ ] `<PROJECT_FILE>` has `## Agents`, `## Skills`, and `## Docs` sections with correct references
- [ ] `docs/roadmap.md` exists (even as a stub)
- [ ] `docs/project-log.md` exists
- [ ] `docs/workflow.md` exists (even as a stub)
- [ ] No placeholder text (`<PROJECT>`, `<PREFIX>`, `<fill in>`, etc.) left in any installed file — prompt the user to fill these in

Report a summary: what was installed, what stubs need filling in, and how to test the hooks:
1. Try editing a file in an owned path without the skill loaded → should see the skill gate message
2. Try running `pnpm add some-package` without `<PREFIX>-skill` loaded → should see the dependency gate message
3. Try invoking `<PREFIX>-qa` with uncommitted changes → should see the pre-handoff gate message
