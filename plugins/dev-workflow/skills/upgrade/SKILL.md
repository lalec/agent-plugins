---
name: upgrade
description: Upgrade an existing dev-workflow install in the current project. Detects gaps against the latest templates (agents, hooks, lifecycle skills, commands, deploy contract) and applies idempotent fixes after user confirmation. Claude Code only. Trigger when the user wants to upgrade, update, sync, or refresh an existing dev-workflow install.
user-invocable: false
---

# upgrade

> **Hard gate.** If no `.claude/agents/<PREFIX>-dev.md` exists for any prefix, abort and tell the user: "No existing dev-workflow install detected. Run `/dev-workflow:install` instead." Do **not** continue.
>
> **You MUST execute steps 1–8 in order. Do not summarize the existing install or claim it is "complete" without running step 5 (the diff checklist) — every running install has gaps unless every checklist item from step 5 has been verified absent. Skipping step 5 is a workflow violation.**

Upgrades an existing dev-workflow install to the current templates. Idempotent — safe to re-run. Reads templates from `../../shared/`, captures existing state from `.claude/`, presents a gap diff, applies confirmed fixes, verifies.

---

## Preflight

Read `../../shared/preflight.md` and follow it before continuing.

---

## Step 1 — Capture existing state

Read current files (do not prompt the user for things already known):
- `EXISTING_PREFIX` — read from `.claude/hooks/governed-paths.conf` `PATH_MAP` entries or from agent filenames (`<PREFIX>-dev.md`)
- `EXISTING_SKILLS[]` — list `.claude/skills/`
- `UNKNOWN_FILES[]` — every `.claude/commands/*.md`, `.claude/skills/*/SKILL.md` and `.claude/agents/*.md` whose name is neither a template name (the fourteen entry points, `<PREFIX>-{dev,qa,pm,verify}`, the lifecycle skills, the domain skills the category map produced) nor marked `project-owned: true` in its frontmatter. These are asked about in Step 7, one by one, never removed unasked — the two installs each grew `quality-review`, `handover`, `proceed` and a stats skill by hand, and one carried 32 KB of tracked prompt files from a tool no longer used.

`CONFIG_DIR=.claude` and `PROJECT_FILE=CLAUDE.md` are fixed (Claude Code only).

---

## Step 2 — Refresh category map

Run a fresh Phase 1c (category discovery) — read `../../shared/tpl-domain-skill.md` § Domain categories. Use existing `EXISTING_SKILLS` as the skill names — do not propose renames. If category discovery surfaces categories not currently owned by any existing skill (e.g. project added Observability since first install), warn the user and recommend invoking `<PREFIX>-skill` after the upgrade to register the new ownership; do **not** create new skills as part of the upgrade.

---

## Step 3 — Scaffold missing foundational components

No confirmation needed — these are absent, not stale.

Read `../../shared/tpl-agents.md` and `../../shared/tpl-commands.md` now.

- **Missing commands** — if `.claude/commands/` is absent or any of `code.md`, `fix.md`, `pilot.md`, `tweak.md`, `revert.md`, `tidy.md`, `roadmap.md`, `blueprint.md`, `wrap.md` are missing: create `.claude/commands/` if needed, then create each missing command file from the corresponding template in `tpl-commands.md`, substituting `<PREFIX>` and `<PROJECT>`. Announce what was created.
- **Missing docs stubs** — create `docs/roadmap.md` and `docs/project-log.md` if absent (same stubs as install Phase 2).
- **Design command** — if a frontend/design domain skill is detected and `.claude/commands/design.md` is missing: create it from `tpl-commands.md § /design`.

Do **not** create or restructure skill files in this step — skills are owned by `<PREFIX>-skill` after install.

---

## Step 4 — Detect LEGACY_DEPLOY_OWNER

Used only by the migration to lifecycle deploy below. Scan `EXISTING_SKILLS` for one with both a `## Deployment` section in its SKILL.md AND a `references/deploy-config.yaml`. If found and that skill is not `<PREFIX>-deploy`, capture its name as `LEGACY_DEPLOY_OWNER`. Otherwise leave empty.

---

## Step 5 — Diff against the gaps the upgrade fixes

Read `references/probes.md` now — every probe, in order, each stated as a grep or a file check whose absence (or presence) is the finding — and present the result to the user as a checklist before changing anything. Every running install has gaps unless every probe has been verified absent; a probe that was not run is reported as not run, never as clean.

---

## Step 6 — Wait for explicit user confirmation

Do not proceed until the user confirms which gaps to apply.

---

## Step 7 — Apply only the confirmed fixes

Read `references/apply.md` now and apply the confirmed steps in its order — the entry-point move first, `<PREFIX>-skill`'s manifest last. Writes under `.claude/skills/<PREFIX>-<x>/` are gated by `skill-guard.sh` on that skill being loaded: invoke the owning skill once via the Skill tool before editing its files, and never work around the gate with a shell write — the gate is the install's own invariant. Each step is idempotent and guarded on its **end state**, never on a phrase: a step revised since it shipped lists every clause its guard must check, because an install that took an earlier version already satisfies a guard written on the earlier phrase and the extension then silently never lands.

---

## Step 8 — Verify

Read `references/verify.md` now and run every check that the applied steps touched. Report each as passed, failed with what was seen, or not runnable here with why; the next real delivery proves the rest.
