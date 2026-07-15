# dev-workflow

A multi-agent delivery workflow for Claude Code. It runs your plan through a team of agents instead of you driving each step manually: one builds, another reviews and tests, a third ships and logs it — each gating the next, so nothing reaches prod unreviewed or undocumented. The agents use lifecycle skills that handle each step of the delivery process and domain skills that learn your stack on install and improve as the code changes, with hooks that keep the process from being skipped and commands that let you guide it where it matters.

> Agent and skill names are prefixed with a name you choose during setup (e.g. `myapp`). Examples below use `myapp`.
>
> **Claude Code only.**

---

## What it installs

| Component | What it does |
|---|---|
| `myapp-dev` | **The builder.** Loads the right domain skills, writes the code, runs each skill's quality checks, deploys non-prod, syncs reference docs — then hands off a structured report, so QA always tests a live stack. |
| `myapp-qa` | **The gatekeeper.** Reviews the code and runs the test tiers before signing off. Routes any required fix back to `myapp-dev` instead of patching it itself. |
| `myapp-pm` | **The closer.** Confirms QA actually ran, ships prod when asked, writes the delivery log, refreshes docs, and advances the roadmap — the audit trail writes itself. |
| 7 lifecycle skills | `log`, `review`, `debug`, `deploy`, `test`, `skill`, `docs` — one per delivery concern, shared by every agent. |
| Domain skills | One per source directory, generated from your actual structure. Each owns its paths, carries reference docs, and defines the lint/type/test checks `myapp-dev` runs before deploy — and improves itself as the code evolves. |
| 9 hooks | Make the workflow self-enforcing: skills must load before edits, bad installs are blocked, handoffs are gated, ref-sync drift is flagged, and nothing pushes without a delivery-log close-out. |
| `/code`, `/fix` | Drive the full pipeline (dev → qa → pm) from one line — confirm, capture verifications, auto-retest after fixes, then close out with a push + evidence-backed scorecard. Add `--prod` to ship after sign-off, `--no-push` to keep it local. |
| `/tweak` | The sanctioned lightweight lane for iterative rounds — pixel nudges, copy, small hotfixes — verified inline (screenshots/curl), with one batched close-out enforced at push time. |
| `/revert` | Sanctioned rollback: `git revert` (never reset), scoped re-verification, and a logged reversal. |
| `/design` | Generate 2–3 HTML variants, open them in the browser, route the winner to `/code` *(if a design skill is present)*. |
| `/roadmap` | Rank open roadmap items by priority and pick the next thing to work on. |
| `/wrap` | Close out ad-hoc work done outside `/code`/`/fix` — reviews the diff when source changed, runs `myapp-log` + `myapp-docs` + `myapp-skill` reference sync, then pushes per the deploy skill's push policy with a verified scorecard (`--no-push` to skip). |
| Living docs | `docs/roadmap.md` (open scope), `docs/project-log.md` (delivery history), `docs/workflow.md` (pipeline map) — all kept current by the agents. |

---

## Prerequisites

- Claude Code (`claude`) installed and authenticated
- A git repo (recommended — hooks use `git status`)
- `jq` on PATH (used by hook scripts)
- [`agent-browser`](https://github.com/vercel-labs/agent-browser) plugin installed — used by `<PREFIX>-test` for E2E browser automation
- [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill installed — used by `<PREFIX>-skill` to author and update skills
- [`ui-ux-pro-max`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) skill installed — used by `<PREFIX>-design` for design intelligence (styles, palettes, font pairings, design-system generation) *(conditional: only if a design skill is installed; can be replaced with any design skill — update the reference in `<PREFIX>-design/SKILL.md` after install)*

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
/code <describe the feature>
```
Runs: `myapp-dev` → `myapp-qa` → `myapp-pm`

### Fix a bug
```
/fix <describe the bug or regression>
```
Runs: `myapp-debug` → `myapp-dev` → `myapp-qa` → `myapp-pm`

### Iterate on something small
```
/tweak <describe the visual/copy/hotfix round>
```
Top-level, inline-verified iteration — no subagent ceremony. The close-out (review + log + docs + ref-sync) is batched at exit; the `close-out-gate` hook blocks `git push` until it runs.

### Roll something back
```
/revert <commit or description of what to undo>
```
`git revert` (never reset), re-runs the affected verifications, logs the reversal.

### Design a UI feature *(if design skill installed)*
```
/design <describe the UI to design>
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
| `skill-guard.sh` | Edit / Write | Editing an owned path without the owning skill loaded (markers scoped per agent) |
| `path-coverage-check.sh` | Write | New file in a governed root with no matching PATH_MAP entry |
| `dependency-guard.sh` | Bash | `pnpm add` / `pip install` without `myapp-skill` loaded |
| `package-edit-guard.sh` | Edit | Adding packages to `package.json` directly without `myapp-skill` |
| `pre-handoff-check.sh` | Skill + Task/Agent | Invoking or spawning `myapp-qa` with uncommitted changes, lint errors, or type errors |
| `close-out-gate.sh` | Bash | `git push` while commits since the last delivery-log entry touch governed/deploy paths (`CLOSEOUT_OVERRIDE=1` escape hatch) |
| `ref-sync-check.sh` | Bash (post) | Warns after commit on reference-worthy drift — structural changes or `REF_WATCH` matches — without reference updates, or deploy-mechanism drift without `deploy-config.yaml` updates. Path patterns sourced from `governed-paths.conf`. |
| `skill-mark.sh` | Skill (post) | Records loaded skills to an agent-scoped session marker (used by all guards) |
| `post-commit.sh` | Bash (post) | Reminds to run `myapp-log` after every commit |

All path→skill ownership lives in one file: `.claude/hooks/governed-paths.conf`. Edit there to add or change ownership — hooks pick it up automatically.

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
