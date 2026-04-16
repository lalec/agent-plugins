# Command Templates

Substitute `<PROJECT>` with the project name and `<PREFIX>` with the chosen prefix derived in Phase 1.

**Claude Code** — Markdown files in `<CONFIG_DIR>/commands/`, YAML frontmatter `description:`, `$ARGUMENTS` placeholder.
**Gemini CLI** — TOML files in `<CONFIG_DIR>/commands/`, `description` and `prompt` keys, `{{args}}` placeholder.

---

## § /code — code.md (Claude Code)

```markdown
---
description: Implement a feature through the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm delivery workflow
---

# Feature Implementation

**Usage:** `/code <description>`

**Examples:**
- `/code add export to CSV button on assessment list`
- `/code change pipeline phases status indication`

## Step 0 — Confirm

Use the AskUserQuestion tool with a single question:

- question: "Ready to implement: $ARGUMENTS?"
- header: "Confirm"
- options:
  - label: "Yes, proceed (Recommended)" — description: "Start the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm pipeline"
  - label: "No, cancel" — description: "Stop here, do not implement"
  - label: "Other" — description: "Let the user refine the description"

Then:
- **Yes** — continue to Step 1
- **No** — tell the user the feature was cancelled and stop
- **Other / custom input** — incorporate the comment, restate the updated description, and ask again

## Step 1 — Implement (<PREFIX>-dev)

Task:
  subagent_type: <PREFIX>-dev
  prompt: |
    Implement the following for <PROJECT>: $ARGUMENTS
    Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync).

## Step 2 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, spawn <PREFIX>-qa:

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes.
    Sign off when quality gates pass.

## Step 3 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off, spawn <PREFIX>-pm:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.

## Done

Tell the user: "Feature complete and logged. Ready for user acceptance testing."
```

---

## § /code — code.toml (Gemini CLI)

```toml
description = "Implement a feature through the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm delivery workflow"
prompt = """
Implement the following for <PROJECT>: {{args}}

Follow this multi-agent workflow:

### Step 0 — Confirm
Use the `ask_user` tool (choice type) to confirm: "Ready to implement: {{args}}?"
- Yes: Proceed to Step 1.
- No: Cancel and stop.
- Other: Refine the description and ask again.

### Step 1 — Implement (<PREFIX>-dev)
Invoke `<PREFIX>-dev` to handle the implementation.
Prompt: "Implement the following for <PROJECT>: {{args}}. Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync)."

### Step 2 — Review & Test (<PREFIX>-qa)
After <PREFIX>-dev completes, invoke `<PREFIX>-qa`.
Prompt: "Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. Sign off when quality gates pass."

### Step 3 — Log & Docs (<PREFIX>-pm)
After <PREFIX>-qa signs off, invoke `<PREFIX>-pm`.
Prompt: "Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made."

### Done
Inform the user: "Feature complete and logged. Ready for user acceptance testing."
"""
```

---

## § /fix — fix.md (Claude Code)

```markdown
---
description: Investigate and fix a bug or performance issue through <PREFIX>-debug → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm
---

# Bug Fix

**Usage:** `/fix <description>`

**Examples:**
- `/fix pipeline table takes too long to load`
- `/fix assessment status stuck on running after completion`

## Step 0 — Confirm

Use the AskUserQuestion tool with a single question:

- question: "Ready to investigate and fix: $ARGUMENTS?"
- header: "Confirm"
- options:
  - label: "Yes, proceed (Recommended)" — description: "Run <PREFIX>-debug root cause analysis, then fix through the full pipeline"
  - label: "No, cancel" — description: "Stop here, do not investigate"
  - label: "Other" — description: "Let the user refine the description"

Then:
- **Yes** — continue to Step 1
- **No** — tell the user the fix was cancelled and stop
- **Other / custom input** — incorporate the comment, restate the updated description, and ask again

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

## Step 3 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, spawn <PREFIX>-qa:

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes.
    Sign off when quality gates pass.

## Step 4 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off, spawn <PREFIX>-pm:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.

## Done

Tell the user: "Fix complete and logged. Ready for user acceptance testing."
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

## § /log — log.md (Claude Code)

```markdown
---
description: Log a manual change (direct data update, config change, no code written) — updates docs, skill references, and delivery log without running QA.
---

# Log

**Usage:** `/log <description of what was changed manually>`

**Examples:**
- `/log updated database record directly to fix corrupted state`
- `/log changed configuration value in cloud console`
- `/log corrected resource policy manually`

## When to use

Use when you made a direct change outside the normal pipeline:
- Direct database update
- Config or data change with no code written
- Manual cloud console change

Do NOT use when code was written — use `/code` or `/fix` instead.

## Step 1 — Docs

Use `<PREFIX>-docs` skill to update docs affected by this change: $ARGUMENTS

## Step 2 — Skill references

Use `<PREFIX>-skill` skill to update skill reference files affected by this change: $ARGUMENTS. Scope to the specific reference file(s) affected — do not run a full manifest audit.

## Step 3 — Delivery log

Use `<PREFIX>-log` skill to log this change: $ARGUMENTS. Tests: none (manual change).

## Done

Tell the user: "Logged. Docs and skill references updated."
```

---

## § /roadmap — roadmap.toml (Gemini CLI)

```toml
description = "Review open roadmap items and pick the next one to work on"
prompt = """
Review the project roadmap and help pick the next item to work on.
Filter/context (if provided): {{args}}

### Step 1 — Read roadmap
Read `docs/roadmap.md`. If it does not exist, tell the user: "No roadmap found — create `docs/roadmap.md` first." and stop.

### Step 2 — Rank and present
From all open or in-progress items, select the top 3 ranked by:
1. Priority (high → medium → low)
2. Then by category: integration > improvement > tech-debt > other

Use the `ask_user` tool (choice type):
- question: "Which roadmap item should we work on next?"
- One choice per top-ranked item (label = title, description = category · priority · status)
- Final choice: "None of these"

### Step 3 — Route
- Selected item: determine if it's a feature (→ /code) or bug (→ /fix), tell the user "Starting: [title]", and invoke the appropriate command
- None of these: ask if the user wants to see more items or cancel
"""
```

---

## § /log — log.toml (Gemini CLI)

```toml
description = "Log a manual change (direct data update, config change, no code written) — updates docs, skill references, and delivery log without running QA"
prompt = """
Log the following manual change for <PROJECT>: {{args}}

Follow this workflow:

### When to use
Use when a direct change was made outside the normal pipeline:
- Direct database update
- Config or data change with no code written
- Manual cloud console change

Do NOT use when code was written — use /code or /fix instead.

### Step 1 — Docs
Invoke `<PREFIX>-docs` to update docs affected by this change: {{args}}

### Step 2 — Skill references
Invoke `<PREFIX>-skill` to update skill reference files affected by this change: {{args}}. Scope to the specific reference file(s) affected — do not run a full manifest audit.

### Step 3 — Delivery log
Invoke `<PREFIX>-log` to log this change: {{args}}. Tests: none (manual change).

### Done
Inform the user: "Logged. Docs and skill references updated."
"""
```

---

## § /fix — fix.toml (Gemini CLI)

```toml
description = "Investigate and fix a bug or performance issue through <PREFIX>-debug → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm"
prompt = """
Investigate and fix the following bug/issue in <PROJECT>: {{args}}

Follow this multi-agent workflow:

### Step 0 — Confirm
Use the `ask_user` tool (choice type) to confirm: "Ready to investigate and fix: {{args}}?"
- Yes: Proceed to Step 1.
- No: Cancel and stop.
- Other: Refine the description and ask again.

### Step 1 — Investigate (<PREFIX>-debug)
Invoke the `<PREFIX>-debug` skill to investigate the root cause.
Complete all four phases:
1. Root Cause Investigation — read errors, reproduce, check recent changes, gather evidence.
2. Pattern Analysis — find working examples, compare, identify differences.
3. Hypothesis and Testing — form theory, test minimally, verify.
4. Hand off to Step 2 with root cause clearly identified.

### Step 2 — Implement (<PREFIX>-dev)
Once root cause is identified, invoke `<PREFIX>-dev`.
Prompt: "Fix the following in <PROJECT>: {{args}}. Root cause has already been investigated — implement the fix. Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync)."

### Step 3 — Review & Test (<PREFIX>-qa)
After <PREFIX>-dev completes, invoke `<PREFIX>-qa`.
Prompt: "Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. Sign off when quality gates pass."

### Step 4 — Log & Docs (<PREFIX>-pm)
After <PREFIX>-qa signs off, invoke `<PREFIX>-pm`.
Prompt: "Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made."

### Done
Inform the user: "Fix complete and logged. Ready for user acceptance testing."
"""
```
