---
name: upgrade
description: Upgrade an existing dev-workflow install in the current project. Detects gaps against the latest templates (agents, hooks, lifecycle skills, commands, deploy contract) and applies idempotent fixes after user confirmation. Claude Code only. Trigger when the user wants to upgrade, update, sync, or refresh an existing dev-workflow install.
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

`CONFIG_DIR=.claude` and `PROJECT_FILE=CLAUDE.md` are fixed (Claude Code only).

---

## Step 2 — Refresh category map

Run a fresh Phase 1c (category discovery) — read `../../shared/tpl-domain-skill.md` § Domain categories. Use existing `EXISTING_SKILLS` as the skill names — do not propose renames. If category discovery surfaces categories not currently owned by any existing skill (e.g. project added Observability since first install), warn the user and recommend invoking `<PREFIX>-skill` after the upgrade to register the new ownership; do **not** create new skills as part of the upgrade.

---

## Step 3 — Scaffold missing foundational components

No confirmation needed — these are absent, not stale.

Read `../../shared/tpl-agents.md` and `../../shared/tpl-commands.md` now.

- **Missing commands** — if `.claude/commands/` is absent or any of `code.md`, `fix.md`, `roadmap.md`, `wrap.md` are missing: create `.claude/commands/` if needed, then create each missing command file from the corresponding template in `tpl-commands.md`, substituting `<PREFIX>` and `<PROJECT>`. Announce what was created.
- **Missing docs stubs** — create `docs/roadmap.md` and `docs/project-log.md` if absent (same stubs as install Phase 2).
- **Design command** — if a frontend/design domain skill is detected and `.claude/commands/design.md` is missing: create it from `tpl-commands.md § /design`.

Do **not** create or restructure skill files in this step — skills are owned by `<PREFIX>-skill` after install.

---

## Step 4 — Detect LEGACY_DEPLOY_OWNER

Used only by the migration to lifecycle deploy below. Scan `EXISTING_SKILLS` for one with both a `## Deployment` section in its SKILL.md AND a `references/deploy-config.yaml`. If found and that skill is not `<PREFIX>-deploy`, capture its name as `LEGACY_DEPLOY_OWNER`. Otherwise leave empty.

---

## Step 5 — Diff against the gaps the upgrade fixes

Present to the user as a checklist before changing anything:

- [ ] `<PREFIX>-deploy` lifecycle skill is missing — needs creation from `tpl-lifecycle.md § tosk-deploy/SKILL.md`
- [ ] `deploy-config.yaml` lives in `<LEGACY_DEPLOY_OWNER>/references/` instead of `<PREFIX>-deploy/references/` — needs migration
- [ ] A domain skill (`<LEGACY_DEPLOY_OWNER>` or any other) carries a `## Deployment` section — deploy logic now lives only in `<PREFIX>-deploy`
- [ ] `governed-paths.conf` `PATH_MAP` maps deploy-mechanism paths to `<LEGACY_DEPLOY_OWNER>` instead of `<PREFIX>-deploy`
- [ ] `governed-paths.conf` missing `DEPLOY_PATHS` variable
- [ ] `ref-sync-check.sh` hardcodes path patterns inline (grep for `grep -qE` with literal directory names) instead of sourcing `governed-paths.conf`
- [ ] `<PREFIX>-dev.md` step 4 contains inline yaml-handling rules (`verify: local`/`cloud:<env>`) — superseded by the one-line delegation in `tpl-agents.md § tosk-dev` step 4
- [ ] `<PREFIX>-dev.md` step 4 references `<PREFIX>-deploy` as a domain skill — wording should treat it as a lifecycle skill
- [ ] `<PREFIX>-dev.md` step 6 contains the legacy `invoke the <PREFIX>-qa agent directly` wording (causes subagent context confusion)
- [ ] `<PREFIX>-qa.md` step 7 contains the legacy `invoke the <PREFIX>-pm agent directly` wording (causes subagent context confusion)
- [ ] `<PREFIX>-dev.md` is missing an explicit `Commit` step between Reference Sync and Hand off
- [ ] `<PREFIX>-qa.md` is missing an explicit `Reference Sync` step between Sign off and Hand off
- [ ] `<PREFIX>-pm.md` is missing an explicit `Reference Sync` step between Docs check and Verify log written
- [ ] `.claude/commands/log.md` exists — superseded by `/wrap`, which covers the same use case with broader framing
- [ ] `<PREFIX>-log/SKILL.md` entry format missing the `Deployed:` field (optional touch — ask user)
- [ ] `<PREFIX>-design` exists but the skill that owns the Frontend category is missing the `## Visual Decisions — Delegate to <PREFIX>-design` section
- [ ] `<PREFIX>-design/SKILL.md` description is permissive ("Use when...") rather than mandatory ("MUST be invoked before...")
- [ ] `<PREFIX>-review/references/verification-before-completion.md` exists — superseded by `<PREFIX>-debug/references/verification.md`
- [ ] `<PREFIX>-qa.md` has separate `Determine test tier` (step 3) and `Test` (step 4) steps with a `Sign-off criteria` tier table — superseded by collapsed step 3
- [ ] Agents (`<PREFIX>-dev`, `<PREFIX>-qa`, `<PREFIX>-pm`) have unconditional Reference Sync steps — superseded by the gated form
- [ ] Agents carry a `## What this agent does NOT do` section — superseded by the one-line `## Boundaries` paragraph
- [ ] `<PREFIX>-debug/SKILL.md` carries the legacy verbose body — superseded by the trimmed `## Read Map` + `## References` form
- [ ] `<PREFIX>-review/SKILL.md` inlines protocol detail AND a `## Reference Sync` section — superseded by the trimmed `## Read Map` + `## References` form (no Reference Sync)
- [ ] `<PREFIX>-deploy/SKILL.md` `## Deployment` section is missing the **Caller contract** (target=non-prod / target=prod), **Fill-in pass**, or inline-gate **context block** (env / url / command / trigger / commit / branch)
- [ ] `<PREFIX>-dev.md` step 4 does not pass `target=non-prod`
- [ ] `<PREFIX>-dev.md` step 4 still contains the trailing "If a gate is declined or skipped" clause — unreachable once gates are inline
- [ ] `<PREFIX>-pm.md` **has** a prod-deploy step (step 1.5 / `target=prod`) — superseded by the top-level `/code|/fix --prod` step (the deploy gate's `AskUserQuestion` can't reach the user from a subagent); must be removed
- [ ] `<PREFIX>-dev.md` step 7 (Hand off) does not require a structured `## Handoff` block
- [ ] `<PREFIX>-qa.md` step 2 (Address findings) does not contain "You do not edit code"
- [ ] `<PREFIX>-qa.md` step 6 (Hand off) does not require a structured `## Handoff` block
- [ ] `<PREFIX>-pm.md` step 1 (Verify QA phases) says "scan the session transcript" without specifying the jsonl grep pattern
- [ ] `<PREFIX>-pm.md` step 1 contains the literal `PROJECT_ENCODED=` jsonl-grep pattern — superseded by reading `**QA-evidence:**` from the invocation prompt
- [ ] `.claude/commands/code.md` / `fix.md` lack a `--prod` flag parse (Step 0) and the final top-level prod-deploy step that invokes `<PREFIX>-deploy target=prod` after pm
- [ ] `<PREFIX>-qa.md` is missing the `## Invocation modes` section (`mode: initial` / `mode: retest`)
- [ ] `.claude/commands/code.md` Step 2 does not parse the dev handoff block, branch on qa Status, or re-spawn with `mode=retest` after a dev fix
- [ ] `.claude/commands/code.md` Step 3 does not pass `**QA-evidence:**` to pm
- [ ] `.claude/commands/fix.md` Step 3 does not parse the dev handoff block, branch on qa Status, or re-spawn with `mode=retest` after a dev fix
- [ ] `.claude/commands/fix.md` Step 4 does not pass `**QA-evidence:**` to pm
- [ ] `<PREFIX>-dev.md` carries the `## Handoff` block format inside step 7 of `## Workflow` and has no terminal `## Response Requirements` section — the strengthened wording lives mid-file (recency loss), and agents still drop the block. Superseded by the structural form in `tpl-agents.md § tosk-dev`: step 7 is a one-line pointer; the block format + imperative live in a final `## Response Requirements` section.
- [ ] `<PREFIX>-qa.md` carries the `## Handoff` block format inside step 6 of `## Workflow` and has no terminal `## Response Requirements` section — same drift as dev. Superseded by the structural form in `tpl-agents.md § tosk-qa`.
- [ ] Domain skills are missing the `## Preconditions — Verify Before Writing References` section between `## Architecture` and the next section — this is the rule that requires grepping for the definition of any referenced identifier before emitting the reference (closes the "wrote `var(--undefined-token)`" failure class)
- [ ] `<PREFIX>-review/references/issuing-findings.md` is missing, or `<PREFIX>-review/SKILL.md` `## Read Map` lacks the `Issuing review findings` branch — the rule that blocking findings need a file:line citation read in this session (closes the "false-positive blocking finding" failure class)
- [ ] `<PREFIX>-test/references/custom-tests.yaml` is missing — per-task functional-feature store captured by `/code` and `/fix` (needs scaffolding)
- [ ] `<PREFIX>-test/references/custom-tests.md` is missing — schema + runtime execution/inference protocol + prior-selection rule (needs scaffolding)
- [ ] `<PREFIX>-test/references/test-commands.md` lacks `## Smoke` / `## Regression` / `## Functional Feature Subjects` headings — needs restructure, preserving existing content
- [ ] `<PREFIX>-test/SKILL.md` still has a `## E2E Browser Tests` section or a `<FRONTEND_PATHS>`→E2E row in `## Test Plan` — superseded by the 3-tier form (Smoke / Functional Feature / Regression) + Rule-5 pointer to `custom-tests.md`
- [ ] `<PREFIX>-test/references/sync-checklist.md` contains the "E2E browser target URL" line — superseded by the `custom-tests.yaml` assert/surface/paths trigger
- [ ] `<PREFIX>-qa.md` `## Invocation modes` lacks `regression_mode`, or step 3 does not forward `regression_mode` / new-entry names / `Files changed:` paths to `<PREFIX>-test`
- [ ] `.claude/commands/code.md` / `fix.md` lack Step 0.5 (capture) and the persist step, **or** their persist step writes `task`/`assert` unquoted (invalid-YAML risk) / includes `.claude/**` in `paths`, **or** the Step 0.5 capture is a prose prompt instead of the AskUserQuestion that proposes 2–3 candidate verifications — superseded by the current `tpl-commands.md` (single-quoted scalars, `.claude/**`-filtered paths, candidate-proposal capture, "verification" vocabulary)
- [ ] `<PREFIX>-test/references/custom-tests.md` is missing **or** lacks the `Running-stack rule` (in-process test runners like FastAPI `TestClient` must report blocked, not a green pass) / single-quoted schema — needs create-or-re-sync

---

## Step 6 — Wait for explicit user confirmation

Do not proceed until the user confirms which gaps to apply.

---

## Step 7 — Apply only the confirmed fixes

Each step is idempotent — re-running the upgrade is safe.

- **Create `<PREFIX>-deploy` lifecycle skill**: if `.claude/skills/<PREFIX>-deploy/SKILL.md` does not exist, create it from `../../shared/tpl-lifecycle.md § tosk-deploy/SKILL.md` (substituting `<PROJECT>` and `<PREFIX>`). Idempotent.
- **Migrate `deploy-config.yaml`**: if `<LEGACY_DEPLOY_OWNER>/references/deploy-config.yaml` exists, move it to `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` (preserving content). If no yaml exists yet, generate one following install Phase 2's "Populate deploy-config.yaml" sub-step. Idempotent.
- **Strip `## Deployment` section** from every domain skill SKILL.md that has it (deploy logic lives only in `<PREFIX>-deploy/SKILL.md`). Remove the section block; leave the rest of the file untouched. Idempotent.
- **Re-point `PATH_MAP`** in `governed-paths.conf`: if any `'PATTERN:SKILL'` entry maps deploy-mechanism paths to `<LEGACY_DEPLOY_OWNER>` (and that name is not `<PREFIX>-deploy`), change the owner to `<PREFIX>-deploy`. Idempotent.
- **Simplify `<PREFIX>-dev.md` step 4**: replace any inline yaml-handling rules (`verify: local`/`cloud:<env>` etc.) with the one-line delegation from `../../shared/tpl-agents.md § tosk-dev` step 4. Idempotent — skip if step 4 is already a single delegation paragraph.
- **Update `governed-paths.conf`**: add the `DEPLOY_PATHS='<value>'` line (and the explanatory comment block from `../../shared/tpl-skill-guard.md § governed-paths.conf`) above `PATH_MAP`. Compute `<value>` from the IaC/CI/CD/Build/Deployment paths in `CATEGORY_MAP`. Update the file's header comment to mention `ref-sync-check.sh` as a consumer.
- **Replace `ref-sync-check.sh`** with the conf-sourcing version from `../../shared/tpl-skill-guard.md § ref-sync-check.sh`. `chmod +x`.
- **Add `Commit` step** to `.claude/agents/<PREFIX>-dev.md`: insert step 6 from `../../shared/tpl-agents.md § tosk-dev` between Reference Sync and Hand off, and update Hand off to step 7 with the latest wording. Idempotent — skip if a Commit step already exists.
- **Add `Reference Sync` step** to `.claude/agents/<PREFIX>-qa.md`: insert step 6.5 from `../../shared/tpl-agents.md § tosk-qa` between Sign off and Hand off, and update Hand off to mention Reference Sync. Idempotent — skip if a Reference Sync step already exists.
- **Add `Reference Sync` step** to `.claude/agents/<PREFIX>-pm.md`: insert step 3.5 from `../../shared/tpl-agents.md § tosk-pm` between Docs check and Verify log written. Idempotent — skip if a Reference Sync step already exists.
- **Migrate `/log` → `/wrap`**: if `.claude/commands/log.md` exists, replace its content with the `/wrap` template from `../../shared/tpl-commands.md § /wrap`, then rename the file to `wrap.md`. Idempotent — skip if `wrap.md` already exists.
- **Fix dev Hand off wording** in `.claude/agents/<PREFIX>-dev.md`: replace any legacy `invoke the <PREFIX>-qa agent directly...` wording with the current Hand off line from `../../shared/tpl-agents.md § tosk-dev` step 7. Idempotent — skip if already updated.
- **Fix qa Hand off wording** in `.claude/agents/<PREFIX>-qa.md`: replace any legacy `invoke the <PREFIX>-pm agent directly...` wording with the current Hand off line from `../../shared/tpl-agents.md § tosk-qa` step 7. Idempotent — skip if already updated.
- **Update `<PREFIX>-log/SKILL.md`** entry format only if user opted in: add the `**Deployed:**` line and the corresponding field guidance + Quality Checklist item from `../../shared/tpl-lifecycle.md § tosk-log/SKILL.md`. Idempotent — skip if already present.
- **Add `## Visual Decisions` block to frontend skill** if `<PREFIX>-design` exists and the skill that owns the Frontend category in `CATEGORY_MAP` is missing the section: insert the block from `../../shared/tpl-domain-skill.md § Design delegation block` (substituting `<PREFIX>`) immediately after the `## Architecture` section. Idempotent — skip if a `## Visual Decisions` section already exists.
- **Replace `<PREFIX>-design/SKILL.md`** description and "When this skill MUST be invoked" section with the stricter version from `../../shared/tpl-lifecycle.md § <PREFIX>-design/SKILL.md` (preserving any user customization in `## What this skill owns`, `## References`, and `## Reference Sync`). Idempotent — skip if description already starts with "Visual authority for <PROJECT>. MUST be invoked".
- **Dedupe verification doc**: if `.claude/skills/<PREFIX>-review/references/verification-before-completion.md` exists, delete it; update `<PREFIX>-review/SKILL.md` `## References` to replace the bullet for that file with `Verification gates: see <PREFIX>-debug/references/verification.md (single source of truth — owned by <PREFIX>-debug)`, and delete the corresponding `## Reference Sync` checklist line. Idempotent.
- **Collapse `<PREFIX>-qa.md` step 3+4 and remove tier table**: replace the separate `Determine test tier` (step 3) and `Test` (step 4) steps with the single delegation step from `../../shared/tpl-agents.md § tosk-qa` step 3. Remove the `## Sign-off criteria` section in full. Renumber subsequent steps (5→4, 6→5, 6.5→5.5, 7→6). Idempotent — skip if step 3 already begins with `Test — invoke`.
- **Gate the Reference Sync step in agents**: replace the unconditional Reference Sync paragraph in `.claude/agents/<PREFIX>-dev.md` step 5, `<PREFIX>-qa.md` step 5.5, and `<PREFIX>-pm.md` step 3.5 with the gated form from `../../shared/tpl-agents.md`. Idempotent — skip if step text already contains `if its `## Reference Sync` checklist exists AND files in its owned paths`.
- **Replace `## What this agent does NOT do` with `## Boundaries`** in all three agents: rewrite the bullet list as a single one-line paragraph using the wording in `../../shared/tpl-agents.md`. Idempotent — skip if a `## Boundaries` section already exists.
- **Trim `<PREFIX>-debug/SKILL.md` to read-map form**: replace the body with the `## Iron Law` + `## Read Map` + `## References` + `## Red Flags` structure from `../../shared/tpl-lifecycle.md § tosk-debug/SKILL.md` and tighten the frontmatter description. Reference files (`systematic-debugging.md`, `root-cause-tracing.md`, `defense-in-depth.md`, `verification.md`) and `scripts/find-polluter.sh` are unchanged. The skill must end up without a `## Reference Sync` section. Idempotent — skip if SKILL.md already contains `## Read Map`.
- **Trim `<PREFIX>-review/SKILL.md` to read-map form**: replace the body with the `## Read Map` + `## References` structure from `../../shared/tpl-lifecycle.md § tosk-review/SKILL.md`. Drop the `## Reference Sync` section entirely. Reference files (`code-review-reception.md`, `requesting-code-review.md`, `issuing-findings.md`) are unchanged or added by the next step. Idempotent — skip if SKILL.md already contains `## Read Map` and lacks `## Reference Sync`.
- **Add `<PREFIX>-review/references/issuing-findings.md`** if missing: copy the file content from `../../shared/tpl-lifecycle.md § tosk-review/SKILL.md` (the `references/issuing-findings.md` block). Then ensure `<PREFIX>-review/SKILL.md` `## Read Map` includes the `Issuing review findings → references/issuing-findings.md` branch and `## References` lists the file. Idempotent — skip if the file exists and the read-map branch is present.
- **Add `## Preconditions` section to every domain skill SKILL.md** that has a `## Architecture` section but no `## Preconditions` section: insert the block from `../../shared/tpl-domain-skill.md § Domain skill stub` (the `## Preconditions — Verify Before Writing References` block, verbatim) immediately after the `## Architecture` section's content and before the next section (which may be `## Visual Decisions`, `## Quality Checklist`, or other). Domain skills are identified by the presence of `## Architecture` — lifecycle skills don't have it. Idempotent — skip any skill that already contains `## Preconditions`.
- **Replace `<PREFIX>-deploy/SKILL.md` `## Deployment` section** with the version from `../../shared/tpl-lifecycle.md § tosk-deploy/SKILL.md` (Caller contract + Fill-in pass + inline gate with context block). Preserve `references/deploy-config.yaml` content as-is. Idempotent — skip if `## Deployment` already contains "Caller contract".
- **Update `<PREFIX>-dev.md` step 4** to pass `target=non-prod` and drop the trailing "If a gate is declined or skipped" clause. Use the wording from `../../shared/tpl-agents.md § tosk-dev` step 4. Idempotent — skip if step 4 already contains "target=non-prod".
- **Remove `<PREFIX>-pm.md` prod-deploy step + harden the log**: delete the `1.5. Deploy to prod` step (any step referencing `<PREFIX>-deploy` / `target=prod`) and renumber; add the "defining deliverable is the delivery log" framing to the title block, the "core, non-negotiable job" note on the Write-delivery-log step, the step-4 hard-gate wording, and "No deployments" to `## Boundaries` — all from `../../shared/tpl-agents.md § tosk-pm`. Idempotent — skip if pm has no `target=prod` and `## Boundaries` already contains "No deployments".
- **Replace `<PREFIX>-dev.md` step 7 (Hand off)** with the structured `## Handoff` block version from `../../shared/tpl-agents.md § tosk-dev` step 7. Update step 6 (Commit) to handle the no-git-repo case. Idempotent — skip if step 7 already contains "Status: complete | blocked".
- **Replace `<PREFIX>-qa.md` step 2 (Address findings)** with the no-self-patch version from `../../shared/tpl-agents.md § tosk-qa` step 2. Idempotent — skip if step 2 already contains "You do not edit code".
- **Replace `<PREFIX>-qa.md` step 6 (Hand off)** with the structured `## Handoff` block version from `../../shared/tpl-agents.md § tosk-qa` step 6. Idempotent — skip if step 6 already contains "Status: signed-off | blocked".
- **Replace `<PREFIX>-pm.md` step 1 (Verify QA phases)** with the QA-evidence-from-prompt version from `../../shared/tpl-agents.md § tosk-pm` step 1. Idempotent — skip if step 1 already contains `**QA-evidence:**`.
- **Re-sync `code.md` and `fix.md`** from `../../shared/tpl-commands.md § /code` and `§ /fix` in full (commands are uniform across projects — Rule 3 — so a whole-template re-sync is safe and carries no project-specific content). This delivers, in one pass: the `--prod` flag parse + top-level prod-deploy step; the Step 0.5 capture (the AskUserQuestion proposing 2–3 **candidate verifications** + "Other") + the persist step (added if absent); **single-quoted** `task`/`assert` in the persist step (valid YAML); `.claude/**`-filtered `paths`; and the "verification" vocabulary. Substitute `<PREFIX>`/`<PROJECT>`. Idempotent — skip if both files already contain `--prod` **and** `candidate verifications`.
- **Add `## Invocation modes` to `<PREFIX>-qa.md`** between the title block and `## Workflow`, from `../../shared/tpl-agents.md § tosk-qa § Invocation modes`. Idempotent — skip if `## Invocation modes` already exists.
- **Rewrite `.claude/commands/code.md` Steps 2–3** from `../../shared/tpl-commands.md § /code`: Step 2 must parse dev `## Handoff` Status, branch on qa Status, and re-spawn qa with `mode=retest` after a dev fix; Step 3 must pass `**QA-evidence:**` (qa's full handoff block) to pm. Idempotent — skip if Step 3 already contains "QA-evidence" and Step 2 already contains "mode=retest".
- **Rewrite `.claude/commands/fix.md` Steps 3–4** from `../../shared/tpl-commands.md § /fix` with the same shape (Step 3 = qa branching + retest, Step 4 = QA-evidence to pm). Idempotent — skip if Step 4 already contains "QA-evidence" and Step 3 already contains "mode=retest".
- **Restructure `<PREFIX>-dev.md` Hand off** to the terminal-section form in `../../shared/tpl-agents.md § tosk-dev`: collapse step 7 to the one-line pointer (`emit the ## Handoff block specified in ## Response Requirements below. Stop.`), strip the block format + Use-Status-blocked note from the workflow step, and append a new `## Response Requirements` section as the **last** section of the file (after `## Boundaries`) containing the CRITICAL imperative + block format. Idempotent — skip if a `## Response Requirements` section already exists.
- **Restructure `<PREFIX>-qa.md` Hand off** to the terminal-section form in `../../shared/tpl-agents.md § tosk-qa`: same shape — step 6 becomes the one-line pointer; block format + imperative move to a terminal `## Response Requirements` section after `## Boundaries`. Idempotent — skip if a `## Response Requirements` section already exists.
- **Scaffold / re-sync test reference files**: create `.claude/skills/<PREFIX>-test/references/custom-tests.yaml` (`tests: []` + leading comment) if missing; create-or-re-sync `references/custom-tests.md` from `../../shared/tpl-lifecycle.md § tosk-test`. Idempotent — skip `custom-tests.yaml` if it exists (never overwrite captured data); skip `custom-tests.md` if it already contains "Running-stack rule". The re-sync delivers the running-stack rule (C), the single-quoted schema (A), and the "verification" vocabulary.
- **Restructure `<PREFIX>-test/references/test-commands.md`**: if it lacks the three headings, insert `## Smoke`, `## Regression`, and `## Functional Feature Subjects` from the `tosk-test` template, **preserving all existing content** — move existing curl/smoke snippets under `## Smoke` and any subject-query snippets under `## Functional Feature Subjects`; leave everything else in place. Idempotent — skip if all three headings already present.
- **Rework `<PREFIX>-test/SKILL.md`**: replace the body with the 3-tier form from `../../shared/tpl-lifecycle.md § tosk-test` — `## Test Plan` tier table, `## Smoke` / `## Functional Feature Tests` / `## Regression` sections, the Rule-5 pointer to `references/custom-tests.md`, and `## References` ↔ `## Reference Sync` listing the four reference files. Delete the `## E2E Browser Tests` section and the `<FRONTEND_PATHS>`→E2E row from `## Test Plan` (its screenshot/`open` rules now live in `custom-tests.md`). Idempotent — skip if `## Test Plan` already lists `Functional Feature` and `Regression` tiers, the body says "per-task verifications", and no `## E2E Browser Tests` section exists.
- **Update `<PREFIX>-test/references/sync-checklist.md`**: replace the "E2E browser target URL" line with the "Smoke or Regression command no longer matches" line, and add the `## Update references/custom-tests.yaml when:` block from the `tosk-test` template. Idempotent — skip if a `custom-tests.yaml` section already exists.
- **Add `regression_mode` to `<PREFIX>-qa.md`**: add the `regression_mode` bullets to `## Invocation modes` and update step 3 to forward `regression_mode` + new functional-feature entry names + the dev `Files changed:` paths to `<PREFIX>-test`, from `../../shared/tpl-agents.md § tosk-qa`. Idempotent — skip if `## Invocation modes` already mentions `regression_mode`.
Update `<PREFIX>-skill` skill-manifest.md last: add the `<PREFIX>-deploy` lifecycle skill (with its `deploy-config.yaml` reference). Remove any `## Deployment` / `deploy-config.yaml` mention from the legacy domain owner's entry.

---

## Step 8 — Verify

Run these verification checks on the upgrade-affected items:

- `.claude/skills/<PREFIX>-deploy/SKILL.md` exists with a `## Deployment` section
- `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml` exists and parses as valid YAML
- No domain skill SKILL.md contains a `## Deployment` section (deploy logic lives only in `<PREFIX>-deploy`)
- `governed-paths.conf` has `DEPLOY_PATHS` and `PATH_MAP` references `<PREFIX>-deploy` (not `<LEGACY_DEPLOY_OWNER>`) for deploy-mechanism paths
- `ref-sync-check.sh` sources the conf and contains no inline path patterns
- `<PREFIX>-dev.md` step 4 is a single delegation paragraph — no inline `verify:` rules
- Neither `<PREFIX>-dev.md` nor `<PREFIX>-qa.md` contains the literal phrase `invoke the <PREFIX>-` (with `qa` or `pm`) `agent directly`
- `<PREFIX>-dev.md` has an explicit `Commit` step between Reference Sync and Hand off
- `<PREFIX>-qa.md` has an explicit `Reference Sync` step between Sign off and Hand off
- `<PREFIX>-pm.md` has an explicit `Reference Sync` step between Docs check and Verify log written
- `.claude/commands/wrap.md` exists; legacy `log.md` command file removed
- `.claude/commands/code.md`, `fix.md`, `roadmap.md`, `wrap.md` all exist
- If `<PREFIX>-design` exists: the frontend-owning skill contains a `## Visual Decisions — Delegate to <PREFIX>-design` section AND `<PREFIX>-design/SKILL.md` description starts with "Visual authority for <PROJECT>. MUST be invoked"
- `<PREFIX>-review/references/verification-before-completion.md` does not exist; `<PREFIX>-review/SKILL.md` `## References` points to `<PREFIX>-debug/references/verification.md`
- `<PREFIX>-qa.md` step 3 begins with `Test — invoke`; the `## Sign-off criteria` section is removed
- All three agents have the gated Reference Sync step and a `## Boundaries` section instead of `## What this agent does NOT do`
- `<PREFIX>-debug/SKILL.md` and `<PREFIX>-review/SKILL.md` contain a `## Read Map` section and **no** `## Reference Sync` section (static-content skills)
- `<PREFIX>-deploy/SKILL.md` `## Deployment` contains the strings "Caller contract", "Fill-in pass", and the inline gate context block fields (`env:`, `url:`, `command:`, `trigger:`, `commit:`, `branch:`)
- `<PREFIX>-dev.md` step 4 contains "target=non-prod" and does not contain "If a gate is declined"
- `<PREFIX>-pm.md` contains **no** prod-deploy step (no `target=prod`) and its `## Boundaries` says "No deployments"
- `<PREFIX>-dev.md` contains the strings "## Handoff" and "Status: complete | blocked" (under the new layout these live in `## Response Requirements`, not step 7)
- `<PREFIX>-qa.md` step 2 contains "You do not edit code"
- `<PREFIX>-qa.md` contains "## Handoff" and "Status: signed-off | blocked" (under the new layout these live in `## Response Requirements`, not step 6)
- `<PREFIX>-pm.md` step 1 contains `**QA-evidence:**` and does **not** contain `PROJECT_ENCODED=`
- `.claude/commands/code.md` and `fix.md` parse `--prod` in Step 0 and end with a top-level "Deploy to prod (only if `--prod`)" step invoking `<PREFIX>-deploy target=prod`; their Step 0.5 capture proposes 2–3 candidate verifications via AskUserQuestion (not a prose prompt); their persist step writes `task`/`assert` **single-quoted** and excludes `.claude/**` from `paths`
- `<PREFIX>-qa.md` contains a `## Invocation modes` section listing `mode: initial` and `mode: retest`
- `.claude/commands/code.md` Step 2 contains `mode=retest` and Step 3 contains `**QA-evidence:**`
- `.claude/commands/fix.md` Step 3 contains `mode=retest` and Step 4 contains `**QA-evidence:**`
- `<PREFIX>-dev.md` and `<PREFIX>-qa.md` both end with a `## Response Requirements` section (the **last** section, after `## Boundaries`) containing the imperative "Every response MUST end with the `## Handoff` block" and the block format; their workflow Hand off step (dev step 7, qa step 6) is a one-line pointer to that section
- Every domain skill SKILL.md (those with `## Architecture`) contains a `## Preconditions — Verify Before Writing References` section between `## Architecture` and the next section
- `<PREFIX>-review/references/issuing-findings.md` exists; `<PREFIX>-review/SKILL.md` `## Read Map` contains the literal string `Issuing review findings`; `## References` lists `references/issuing-findings.md`
- `<PREFIX>-test/references/` contains `custom-tests.yaml` (`tests: []`), `custom-tests.md`, and `test-commands.md` with `## Smoke` / `## Regression` / `## Functional Feature Subjects` headings (existing content preserved)
- `<PREFIX>-test/SKILL.md` `## Test Plan` lists Smoke / Functional Feature / Regression tiers; there is **no** `## E2E Browser Tests` section; `## References` and `## Reference Sync` both list the four reference files (`test-commands.md`, `custom-tests.yaml`, `custom-tests.md`, `sync-checklist.md`)
- `<PREFIX>-test/references/sync-checklist.md` has no "E2E browser target URL" line and contains an `## Update references/custom-tests.yaml when:` section
- `<PREFIX>-test/references/custom-tests.md` contains the "Running-stack rule" and a single-quoted schema
- `<PREFIX>-qa.md` `## Invocation modes` includes `regression_mode: smart | full`; step 3 forwards `regression_mode`, new-entry names, and changed paths to `<PREFIX>-test`
- `.claude/commands/code.md` contains "What should be verified before this ships" (Step 0.5) and a Step 1.5 persist; `.claude/commands/fix.md` contains the same Step 0.5 and a Step 2.5 persist
- `skill-manifest.md` is current

Report a summary of what was upgraded.
