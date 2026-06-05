# Command Templates

Substitute `<PROJECT>` with the project name and `<PREFIX>` with the chosen prefix derived in Phase 1.

Claude Code only. Markdown files in `.claude/commands/`, YAML frontmatter `description:`, `$ARGUMENTS` placeholder.

---

## § /code — code.md (Claude Code)

```markdown
---
description: Implement a feature through the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm delivery workflow
---

# Feature Implementation

**Usage:** `/code <description>` — append `--prod` to deploy to prod after QA sign-off (default ends at UAT, no prod deploy)

**Examples:**
- `/code add export to CSV button on assessment list`
- `/code change pipeline phases status indication`
- `/code <description> --prod`

## Step 0 — Confirm

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `prod_deploy = true` and strip `--prod` from the task description used in every step below. Otherwise `prod_deploy = false` — the pipeline ends at UAT with no prod deploy.

Use the AskUserQuestion tool with a single question:

- question: "Ready to implement: $ARGUMENTS?"
- header: "Confirm"
- options:
  - label: "Yes, proceed (Recommended)" — description: "Start the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm pipeline"
  - label: "No, cancel" — description: "Stop here, do not implement"
  - label: "Other" — description: "Let the user refine the description"

Then:
- **Yes** — continue to Step 0.5
- **No** — tell the user the feature was cancelled and stop
- **Other / custom input** — incorporate the comment, restate the updated description, and ask again

## Step 0.5 — Capture verifications + regression flag

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

**(a) Capture verifications.** Ask the user in prose (not AskUserQuestion):

> "What should be verified before this ships? One verification per line; blank to finish; `skip` for none."

For each verification, infer its `surface` from the wording — **ui** ("page", "button", "renders", "screenshot"), **api** ("endpoint", "returns", "status code"), or **data** ("row", "record", "stored", "status in"). Only if a sentence is genuinely ambiguous, use AskUserQuestion with options **UI · API · Data** to resolve that one. Hold the captured `{assert, surface}` pairs in context — **do not write or commit anything yet**. If the user answers `skip`, capture nothing and continue.

**(b) Regression flag.** Use the AskUserQuestion tool:

- question: "Run full regression after dev as well?"
- header: "Regression"
- options:
  - label: "No (Recommended)" — description: "Smoke + this task's verifications + prior verifications for the same files"
  - label: "Yes" — description: "Everything above + the full regression suite (all prior verifications + broad checks)"

Capture the answer as a bare boolean `regression_mode` = `smart` (No) or `full` (Yes).

## Step 1 — Implement (<PREFIX>-dev)

Task:
  subagent_type: <PREFIX>-dev
  prompt: |
    Implement the following for <PROJECT>: $ARGUMENTS
    Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync).
    Verifications (these must hold when done): <the verifications captured in Step 0.5, or "none">

## Step 1.5 — Persist captured verifications

Run only if verifications were captured in Step 0.5 (not `skip`) **and** <PREFIX>-dev returned `Status: complete`. If dev blocked, skip — nothing is written.

For each captured `{assert, surface}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`)
- `surface` — the inferred/confirmed surface
- `paths` — the dev `## Handoff` `Files changed:` list, **excluding any `.claude/**` paths** (workflow-internal reference/doc edits must not drive prior-selection)

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 2.

## Step 2 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, parse its `## Handoff` block:
- `Status: complete` → spawn <PREFIX>-qa with `mode=initial`.
- `Status: blocked` → tell the user dev blocked with `Notes:` and stop.

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. mode=initial
    regression_mode: <smart | full, from Step 0.5>
    New verifications this task: <names from Step 1.5, or "none">
    Changed paths: <the dev Handoff `Files changed:` list>
    Sign off when quality gates pass.

After <PREFIX>-qa returns, parse its `## Handoff` block:
- `Status: signed-off` → continue to Step 3.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — keep the same `regression_mode`. Repeat until signed-off or user aborts.

## Step 3 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off, capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 4 — Deploy to prod (only if `--prod`)

Run only if `prod_deploy` was set in Step 0. After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and asks via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code. If no `prod` env is declared or the user declines, report that and finish at UAT.

## Done

- If `--prod` and prod deploy succeeded: tell the user "Feature complete, logged, and deployed to prod."
- Otherwise: tell the user "Feature complete and logged. Ready for user acceptance testing — run `/code <task> --prod` (or invoke <PREFIX>-deploy) when ready to ship."
```

---

## § /fix — fix.md (Claude Code)

```markdown
---
description: Investigate and fix a bug or performance issue through <PREFIX>-debug → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm
---

# Bug Fix

**Usage:** `/fix <description>` — append `--prod` to deploy to prod after QA sign-off (default ends at UAT, no prod deploy)

**Examples:**
- `/fix pipeline table takes too long to load`
- `/fix assessment status stuck on running after completion`
- `/fix <description> --prod`

## Step 0 — Confirm

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `prod_deploy = true` and strip `--prod` from the description used in every step below. Otherwise `prod_deploy = false` — the pipeline ends at UAT with no prod deploy.

Use the AskUserQuestion tool with a single question:

- question: "Ready to investigate and fix: $ARGUMENTS?"
- header: "Confirm"
- options:
  - label: "Yes, proceed (Recommended)" — description: "Run <PREFIX>-debug root cause analysis, then fix through the full pipeline"
  - label: "No, cancel" — description: "Stop here, do not investigate"
  - label: "Other" — description: "Let the user refine the description"

Then:
- **Yes** — continue to Step 0.5
- **No** — tell the user the fix was cancelled and stop
- **Other / custom input** — incorporate the comment, restate the updated description, and ask again

## Step 0.5 — Capture verifications + regression flag

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

**(a) Capture verifications.** Ask the user in prose (not AskUserQuestion):

> "What should be verified before this ships? One verification per line; blank to finish; `skip` for none."

For each verification, infer its `surface` from the wording — **ui** ("page", "button", "renders", "screenshot"), **api** ("endpoint", "returns", "status code"), or **data** ("row", "record", "stored", "status in"). Only if a sentence is genuinely ambiguous, use AskUserQuestion with options **UI · API · Data** to resolve that one. Hold the captured `{assert, surface}` pairs in context — **do not write or commit anything yet**. If the user answers `skip`, capture nothing and continue. (A bug's verification becomes its never-regress-again invariant.)

**(b) Regression flag.** Use the AskUserQuestion tool:

- question: "Run full regression after dev as well?"
- header: "Regression"
- options:
  - label: "No (Recommended)" — description: "Smoke + this task's verifications + prior verifications for the same files"
  - label: "Yes" — description: "Everything above + the full regression suite (all prior verifications + broad checks)"

Capture the answer as a bare boolean `regression_mode` = `smart` (No) or `full` (Yes).

## Step 1 — Investigate (<PREFIX>-debug)

Use the <PREFIX>-debug skill to investigate the root cause before any code is written.

Invoke the `<PREFIX>-debug` skill, then analyze the following bug or performance issue in <PROJECT>: $ARGUMENTS

Complete all four phases:
1. Root Cause Investigation — read errors, reproduce, check recent changes, gather evidence
2. Pattern Analysis — find working examples, compare, identify differences
3. Hypothesis and Testing — form theory, test minimally, verify
4. Hand off to Step 2 with root cause clearly identified

Do NOT write any fix until Phase 1–3 are complete.

## Step 2 — Implement (<PREFIX>-dev)

Once root cause is identified, spawn <PREFIX>-dev:

Task:
  subagent_type: <PREFIX>-dev
  prompt: |
    Fix the following in <PROJECT>: $ARGUMENTS
    Root cause has already been investigated — implement the fix.
    Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync).
    Verifications (these must hold when done): <the verifications captured in Step 0.5, or "none">

## Step 2.5 — Persist captured verifications

Run only if verifications were captured in Step 0.5 (not `skip`) **and** <PREFIX>-dev returned `Status: complete`. If dev blocked, skip — nothing is written.

For each captured `{assert, surface}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`)
- `surface` — the inferred/confirmed surface
- `paths` — the dev `## Handoff` `Files changed:` list, **excluding any `.claude/**` paths** (workflow-internal reference/doc edits must not drive prior-selection)

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 3.

## Step 3 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, parse its `## Handoff` block:
- `Status: complete` → spawn <PREFIX>-qa with `mode=initial`.
- `Status: blocked` → tell the user dev blocked with `Notes:` and stop.

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. mode=initial
    regression_mode: <smart | full, from Step 0.5>
    New verifications this task: <names from Step 2.5, or "none">
    Changed paths: <the dev Handoff `Files changed:` list>
    Sign off when quality gates pass.

After <PREFIX>-qa returns, parse its `## Handoff` block:
- `Status: signed-off` → continue to Step 4.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — keep the same `regression_mode`. Repeat until signed-off or user aborts.

## Step 4 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off, capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 5 — Deploy to prod (only if `--prod`)

Run only if `prod_deploy` was set in Step 0. After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and asks via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code. If no `prod` env is declared or the user declines, report that and finish at UAT.

## Done

- If `--prod` and prod deploy succeeded: tell the user "Fix complete, logged, and deployed to prod."
- Otherwise: tell the user "Fix complete and logged. Ready for user acceptance testing — run `/fix <task> --prod` (or invoke <PREFIX>-deploy) when ready to ship."
```

---

## § /design — design.md (Claude Code only)

**Install condition:** Only install if a design domain skill was discovered in Phase 1 (e.g. a `<PREFIX>-design`, `<PREFIX>-frontend`, or `<PREFIX>-ui` skill that owns UI/component paths).

```markdown
---
description: Generate design variants for a UI feature using the <PREFIX>-design skill
---

# Design

**Usage:** `/design <description>`

**Examples:**
- `/design new onboarding flow for first-time users`
- `/design redesign the pipeline status card`

## Step 0 — Confirm

Use the AskUserQuestion tool with a single question:

- question: "Ready to design: $ARGUMENTS?"
- header: "Confirm"
- options:
  - label: "Yes, proceed (Recommended)" — description: "Generate 2–3 HTML design variants"
  - label: "No, cancel" — description: "Stop here"
  - label: "Other" — description: "Let the user refine the description"

Then:
- **Yes** — continue to Step 1
- **No** — tell the user design was cancelled and stop
- **Other / custom input** — incorporate the comment, restate the updated description, and ask again

## Step 1 — Design (<PREFIX>-design)

Invoke the `<PREFIX>-design` and generate 2–3 distinct HTML design variants for: $ARGUMENTS

- Write each variant to `/tmp/<PREFIX>-design-variant-N.html` (N = 1, 2, 3)
- Each variant must be a complete, self-contained HTML file with inline CSS
- Variants should explore meaningfully different directions (layout, visual style, interaction pattern)
- Open each file in the default browser using `open /tmp/<PREFIX>-design-variant-N.html`

## Step 2 — Choose direction

Use the AskUserQuestion tool:

- question: "Which design direction do you prefer?"
- header: "Pick a direction"
- options:
  - label: "Variant 1" — description: "Proceed with variant 1"
  - label: "Variant 2" — description: "Proceed with variant 2"
  - label: "Variant 3" — description: "Proceed with variant 3" (if generated)
  - label: "None — iterate" — description: "Describe what to change and regenerate"
  - label: "Cancel" — description: "Stop here"

Route based on selection:
- **Variant N** — tell the user the chosen direction is ready to implement via `/code`
- **None — iterate** — incorporate feedback, regenerate variants, return to Step 2
- **Cancel** — stop
```

---

## § /roadmap — roadmap.md (Claude Code)

```markdown
---
description: Review open roadmap items and pick the next one to work on
---

# Roadmap

**Usage:** `/roadmap` or `/roadmap <filter>`

**Examples:**
- `/roadmap`
- `/roadmap high priority`
- `/roadmap integrations`

## Step 1 — Read roadmap

Read `docs/roadmap.md`. If it does not exist, tell the user: "No roadmap found — create `docs/roadmap.md` first." and stop.

## Step 2 — Rank and present

From all open or in-progress items, select the top 3 ranked by:
1. Priority (high → medium → low)
2. Then by category: integration > improvement > tech-debt > other

Use the AskUserQuestion tool:

- question: "Which roadmap item should we work on next?"
- header: "Roadmap — Top 3"
- options: one per top-ranked item, label = item title, description = category · priority · status
- Add a final option: label: "None of these" — description: "Show more items or cancel"

## Step 3 — Route

- **Selected item** — determine whether it's a new feature (→ `/code`) or a bug/regression (→ `/fix`), then tell the user: "Starting: [item title]" and invoke the appropriate command
- **None of these** — ask if the user wants to see more items or cancel
```

---

## § /wrap — wrap.md (Claude Code)

```markdown
---
description: Manually trigger post-change close-out — <PREFIX>-log + <PREFIX>-docs + <PREFIX>-skill reference sync. Use when work happened outside the /code or /fix pipelines.
---

# /wrap

Close-out for changes made **outside** the normal `/code`/`/fix` pipeline — ad-hoc edits, direct data fixes, manual config changes, or any work where `<PREFIX>-pm` didn't run automatically. The `/code` and `/fix` pipelines run `<PREFIX>-pm` at the end; use `/wrap` only when they didn't.

**Usage:** `/wrap <description of what changed>`

**Examples:**
- `/wrap manually updated database row to fix corrupted state`
- `/wrap changed configuration value in cloud console`
- `/wrap ad-hoc script run that imported new dataset`

## Step 1 — Delivery log

Use `<PREFIX>-log` skill to append a log entry to `docs/project-log.md` for the most recent commit. Pass `$ARGUMENTS` as context for the entry title and body.

## Step 2 — Docs sync

Use `<PREFIX>-docs` skill to check whether project docs need updating based on what changed. Update any that are stale. Pass `$ARGUMENTS` as context.

## Step 3 — Reference sync

Use `<PREFIX>-skill` skill to run the reference sync check:
- Verify `governed-paths.conf` matches current directory structure
- Confirm `## References` and `## Reference Sync` are in 1:1 parity in every `<PREFIX>-*` skill
- Confirm `skill-manifest.md` is current

Scope to affected skills only — do not run a full manifest audit unless something actually changed.

## Done

Tell the user: "Wrapped. Log, docs, and skill references are up to date."
```
