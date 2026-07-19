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

**Usage:** `/code <description>` — the Step 0.5 gate asks whether to ship after sign-off. `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push.

**Examples:**
- `/code add export to CSV button on assessment list`
- `/code change pipeline phases status indication`
- `/code <description> --prod`

## Gate policy (governs every AskUserQuestion in this command)

If a question times out unanswered, split by risk:
- **Reversible** (confirm, verification capture, regression flag, ship choice, UAT-defer): proceed with the recommended default and label every downstream record `auto-selected on timeout — not user-confirmed` (handoffs, delivery log, final report). **Never present a timeout as user consent** — not to a subagent, not in a log, not in the report.
- **Irreversible** (prod deploy; any push that fires a prod CI deploy): **park** — do not proceed and do not decide. End the turn stating exactly what awaits confirmation and how to resume; on the user's next message, resume from the parked step. Park only after actually asking at the moment of the irreversible action — never skip the ask because an earlier, unrelated gate timed out; the user may have returned.

## Step 0 — Flags + entry hygiene

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `ship_mode = prod`; if it contains `--no-push`, set `ship_mode = hold` and `no_push = true`. Strip both flags from the task description used in every step below. If neither flag is present, `ship_mode` is decided by the Ship question in the Step 0.5 gate.

**Entry hygiene:** run `git status --porcelain`. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it in the close-out step — the pre-handoff gate blocks the qa spawn on any dirty tree, so deferring the stash just moves the failure mid-pipeline. If the WIP overlaps paths this task will touch, ask the user how to proceed instead of stashing.

**Plan shortcut:** if the session contains a just-approved plan covering this task, plan approval was the confirmation — omit the Confirm question from the Step 0.5 gate.

## Step 0.5 — Single gate: confirm + capture verifications + regression flag

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

First produce 2–3 **candidate verifications** — plain one-line statements of what must be true after the change — from whichever source applies:
- **A plan exists** (the current session has a just-approved plan with a *Verification* / *Acceptance* section): translate each of its lines into a one-line what-must-hold assertion and use those as the candidates. A plan's lines describe *how it's proven*; restate each as *what must hold* so it reads as a regression invariant.
- **No plan** (e.g. `/code` invoked first thing in a fresh context): infer the candidates from the task (`$ARGUMENTS`, with any flags already stripped) — the default fallback whenever no plan is in context.

Then ask everything in **one AskUserQuestion call** (up to three questions) — one gate interaction instead of three sequential ones, so an AFK timeout costs 60 seconds once, not three times:

1. **Confirm** (omit this question when the plan shortcut applies):
   - question: "Ready to implement: $ARGUMENTS?"
   - header: "Confirm"
   - options:
     - label: "Yes, proceed (Recommended)" — description: "Start the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm pipeline"
     - label: "No, cancel" — description: "Stop here, do not implement"
2. **Verify**:
   - question: "What should be verified before this ships?"
   - header: "Verify"
   - multiSelect: true
   - options:
     - one per inferred candidate — label: a short tag (the endpoint/element + expected result); description: the full one-line verification followed by its type (`UX` / `Integration` / `E2E`)
     - a final option — label: "Nothing to verify"; description: "Refactor / docs / no behavior change"
   - The automatic "Other" field lets the user type their own one-line verification.
3. **Regression**:
   - question: "Run full regression after dev as well?"
   - header: "Regression"
   - options:
     - label: "No (Recommended)" — description: "Smoke + this task's verifications + prior verifications for the same files"
     - label: "Yes" — description: "Everything above + the full regression suite (all prior verifications + broad checks)"
4. **Ship** (omit when `--prod` or `--no-push` already decided it):
   - question: "Ship after QA sign-off?"
   - header: "Ship"
   - options:
     - label: "Ship (Recommended)" — description: "After a clean sign-off, deploy/push to prod at close-out without asking again. On projects where push fires prod CI, shipping = prod deploy."
     - label: "Hold at UAT" — description: "End committed but not pushed/deployed; ship later with --prod or by asking"

Branch on the answers:
- Confirm = **No, cancel** → tell the user it was cancelled and stop (discard the other answers).
- Confirm = **Other / custom input** → incorporate the comment, restate the updated description, and re-ask the full gate once.
- Timeout → Gate policy: reversible — proceed on the recommended defaults, **except Ship, whose timeout default is always Hold** (shipping needs a real answer; holding is free to reverse), labeled `auto-selected on timeout — not user-confirmed`.

For every Verify option the user selects (and any "Other" text), take the one-line verification and its `type` — already known for the proposed ones; for a custom line, infer `type` from the wording (**UX** (frontend only) · **Integration** (backend: endpoint or stored data) · **E2E** (a UI action with a backend effect)). Hold the `{assert, type}` pairs in context — **do not write or commit anything yet**. If only "Nothing to verify" is chosen (or nothing is selected), capture nothing and continue.

**Honor the user's answer.** A free-text reply that declines automated verification ("I'll verify live", "I'll test by eye") is a decision: record this task as `UAT-only`, capture nothing, and skip Step 1.5 — do not persist synthesized entries against the user's stated intent.

Capture the Regression answer as `regression_mode` = `smart` (No) or `full` (Yes). This answer **binds test scope downstream**: it is forwarded to `<PREFIX>-qa` and `<PREFIX>-test`, and neither may widen it (see `<PREFIX>-test` Rules — a full unit-suite re-run is not a permissible "superset").

Capture the Ship answer as `ship_mode` = `prod` (Ship) or `hold`. A user-answered **Ship** is standing consent for the close-out — but it is conditional, and the conditions are verified mechanically at Step 4: it collapses back to a fresh ask if the run wasn't clean.

## Step 1 — Implement (<PREFIX>-dev)

Task:
  subagent_type: <PREFIX>-dev
  prompt: |
    Implement the following for <PROJECT>: $ARGUMENTS
    Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync).
    Verifications (these must hold when done): <the verifications captured in Step 0.5, or "none">

While the agent runs, do **not** edit governed source files at the top level — concurrent writers make QA's diff unattributable.

**Salvage protocol (applies to every subagent in this command):** if an agent dies without a `## Handoff` (watchdog kill, session limit, API error), do not absorb its role at the top level. Inspect `git status` / `git log` to see what landed, then continue the same agent via SendMessage or re-spawn it with a salvage prompt naming what is already done and which contract steps remain (quality checks, deploy, Reference Sync, commit, handoff). A salvaged completion counts as `Status: complete` for the steps below.

## Step 1.5 — Persist captured verifications

Run only if verifications were captured in Step 0.5 (not `skip`, not `UAT-only`) **and** <PREFIX>-dev finished — `Status: complete` or a salvaged completion (captured verifications must never be lost to an agent death). If dev blocked, skip — nothing is written.

For each captured `{assert, type}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`). Keep it **symbolic**: reference behavior and configured values ("matches the configured tolerance"), never volatile constants copied from code — those rot within days and QA then wastes a cycle correcting them
- `type` — the inferred/confirmed type
- `paths` — the dev `## Handoff` `Files changed:` list, **excluding any `.claude/**` paths** (workflow-internal reference/doc edits must not drive prior-selection)

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 2.

## Step 1.7 — Ensure verification stack

Run only if verifications with type `UX` or `E2E` were captured. For each affected component (from the dev `Files changed:` paths), resolve its **first non-prod env** in `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`:
- Env has `deploy:` (ship-env) → nothing to do; <PREFIX>-dev already deployed it.
- Env has `run:` (serve-env) → start or restart it here at the top level (subagents can't hold a server), applying the env's `stack:` block if declared — env-var overrides that wire the frontend to the local backend, the `seed:` command, the `auth:` strategy (see the deploy-config schema). Then poll the url until HTTP 2xx (up to ~60s). If still unreachable, surface the output and ask the user how to proceed before spawning <PREFIX>-qa.
  **Freshness:** a server started before dev's commits is running stale code — restart it so QA tests the new code; a green check against a stale server is non-evidence.
- No non-prod env → continue; <PREFIX>-test reports those verifications blocked and Step 2 handles it.

Leave any server you started running — note it under Done.

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
- `Status: signed-off-with-deferrals` → ask via AskUserQuestion: "QA is clean except these verifications no environment can run: `<UAT-deferred list with reasons>`. Defer to UAT and continue, or stop?" On **Defer** — carry `UAT-deferred: <names> (user-confirmed)` into the Step 3 pm prompt and continue. On timeout — reversible gate: continue, but carry `UAT-deferred: <names> (auto-accepted on timeout — not user-confirmed)`. On **Stop** — halt and report. Never re-spawn qa to relabel its handoff — the deferral status IS the sign-off vocabulary.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — keep the same `regression_mode`. Repeat until signed-off or user aborts.

## Step 3 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off (either signed-off status), capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.
    Feature commit: <the dev Handoff `Commit:` hash — the delivery-log hash, not any later bookkeeping commit>
    UAT-deferred: <names + how confirmed, from Step 2 — omit line if none>

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 4 — Deploy to prod (only if `ship_mode: prod`)

Run only if `ship_mode = prod` (from the `--prod` flag or the Step 0.5 Ship answer). After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and gates via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code.

**Pre-authorization.** If the user answered **Ship** at the Step 0.5 gate (not a timeout default), pass `preauth: user shipped at Step 0.5` to the skill **only when all of these hold** — verified now, not assumed:
- QA status is `signed-off`, or `signed-off-with-deferrals` where the deferral was **user-confirmed** (not auto-accepted on timeout);
- no gate in this run was auto-decided on timeout;
- the commits being shipped are exactly the reviewed set (nothing landed after QA's sign-off except the capture/log commits).

When any condition fails — or Ship was a timeout default — the skill gates normally (ask; on no answer it returns `gate: unanswered — parked` → park per the Gate policy; never decide a prod deploy on the user's behalf). If no `prod` env is declared or the user declines, report that and finish at UAT.

## Step 5 — Close out: push + verified scorecard

Runs on every completion, regardless of `ship_mode`.

**(a) Push.** Skip if `no_push` or no remote is configured. Resolve the push policy via the `<PREFIX>-deploy` skill § Push policy: if pushing the current branch fires a prod CI deploy, pushing IS shipping — push only if Step 4 ran and its gate (or pre-authorization) approved; otherwise ask now (irreversible gate — ask at this moment even if an earlier gate timed out; park only if this ask goes unanswered). If push does not trigger prod, push now.

**(b) Scorecard.** Verify each fact against reality — never echo handoff claims:

| Fact | Evidence |
|---|---|
| Committed | `git log --oneline -5` shows the feature + capture + log commits |
| Pushed | `git rev-list --count @{upstream}..HEAD` → 0, or "not pushed — <reason>" |
| Deployed | curl the env url/health from the dev handoff (2xx), or "no deployable env" |
| Logged | new entry present at top of `docs/project-log.md` (grep the title) |
| Docs | pm handoff `Docs:` field; spot-check the file if `updated` |
| Ref sync | `Reference Sync:` fields from all three handoffs |

**(c) Restore stashed WIP.** If pre-existing WIP was stashed at Step 0, `git stash pop` it now and confirm it restored cleanly; report any conflict instead of resolving it silently.

## Done

Report, in this order:
1. The Step 5 scorecard — each fact with its evidence, any ✗ called out first.
2. QA's `Evidence:` lines verbatim (verification traces, screenshot paths) — this is what lets the user skip re-testing.
3. Anything auto-decided on a gate timeout, explicitly labeled.
4. UAT-deferred verifications as explicit follow-ups.
5. If a serve-env was started in Step 1.7: it is still running, and where (`<url>`).
6. If shipped (`ship_mode: prod`): "deployed to prod" only after `<PREFIX>-deploy` confirmed CI completion + health check. If held (`ship_mode: hold`): "held at UAT per your Ship answer — say ship (or re-run with `--prod`) when ready." If parked: state exactly what awaits your confirmation.
7. If this is the 2nd+ pipeline run in this session, suggest closing out and starting a fresh session — long sessions degrade quality.
```

---

## § /fix — fix.md (Claude Code)

```markdown
---
description: Investigate and fix a bug or performance issue through <PREFIX>-debug → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm
---

# Bug Fix

**Usage:** `/fix <description>` — the Step 0.5 gate asks whether to ship after sign-off. `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push.

**Examples:**
- `/fix pipeline table takes too long to load`
- `/fix assessment status stuck on running after completion`
- `/fix <description> --prod`

## Gate policy (governs every AskUserQuestion in this command)

If a question times out unanswered, split by risk:
- **Reversible** (confirm, verification capture, regression flag, ship choice, UAT-defer): proceed with the recommended default and label every downstream record `auto-selected on timeout — not user-confirmed` (handoffs, delivery log, final report). **Never present a timeout as user consent** — not to a subagent, not in a log, not in the report.
- **Irreversible** (prod deploy; any push that fires a prod CI deploy): **park** — do not proceed and do not decide. End the turn stating exactly what awaits confirmation and how to resume; on the user's next message, resume from the parked step. Park only after actually asking at the moment of the irreversible action — never skip the ask because an earlier, unrelated gate timed out; the user may have returned.

## Step 0 — Flags + entry hygiene

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `ship_mode = prod`; if it contains `--no-push`, set `ship_mode = hold` and `no_push = true`. Strip both flags from the description used in every step below. If neither flag is present, `ship_mode` is decided by the Ship question in the Step 0.5 gate.

**Entry hygiene:** run `git status --porcelain`. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it in the close-out step — the pre-handoff gate blocks the qa spawn on any dirty tree, so deferring the stash just moves the failure mid-pipeline. If the WIP overlaps paths this task will touch, ask the user how to proceed instead of stashing.

**Plan shortcut:** if the session contains a just-approved plan covering this fix, plan approval was the confirmation — omit the Confirm question from the Step 0.5 gate.

## Step 0.5 — Single gate: confirm + capture verifications + regression flag

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

First produce 2–3 **candidate verifications** — plain one-line statements of what must be true after the change — from whichever source applies:
- **A plan exists** (the current session has a just-approved plan with a *Verification* / *Acceptance* section): translate each of its lines into a one-line what-must-hold assertion and use those as the candidates. A plan's lines describe *how it's proven*; restate each as *what must hold* so it reads as a regression invariant.
- **No plan** (e.g. `/fix` invoked first thing in a fresh context): infer the candidates from the task (`$ARGUMENTS`, with any flags already stripped) — the default fallback whenever no plan is in context. (A bug's verification becomes its never-regress-again invariant.)

Then ask everything in **one AskUserQuestion call** (up to three questions) — one gate interaction instead of three sequential ones, so an AFK timeout costs 60 seconds once, not three times:

1. **Confirm** (omit this question when the plan shortcut applies):
   - question: "Ready to investigate and fix: $ARGUMENTS?"
   - header: "Confirm"
   - options:
     - label: "Yes, proceed (Recommended)" — description: "Run <PREFIX>-debug root cause analysis, then fix through the full pipeline"
     - label: "No, cancel" — description: "Stop here, do not investigate"
2. **Verify**:
   - question: "What should be verified before this ships?"
   - header: "Verify"
   - multiSelect: true
   - options:
     - one per inferred candidate — label: a short tag (the endpoint/element + expected result); description: the full one-line verification followed by its type (`UX` / `Integration` / `E2E`)
     - a final option — label: "Nothing to verify"; description: "Refactor / docs / no behavior change"
   - The automatic "Other" field lets the user type their own one-line verification.
3. **Regression**:
   - question: "Run full regression after dev as well?"
   - header: "Regression"
   - options:
     - label: "No (Recommended)" — description: "Smoke + this task's verifications + prior verifications for the same files"
     - label: "Yes" — description: "Everything above + the full regression suite (all prior verifications + broad checks)"
4. **Ship** (omit when `--prod` or `--no-push` already decided it):
   - question: "Ship after QA sign-off?"
   - header: "Ship"
   - options:
     - label: "Ship (Recommended)" — description: "After a clean sign-off, deploy/push to prod at close-out without asking again. On projects where push fires prod CI, shipping = prod deploy."
     - label: "Hold at UAT" — description: "End committed but not pushed/deployed; ship later with --prod or by asking"

Branch on the answers:
- Confirm = **No, cancel** → tell the user the fix was cancelled and stop (discard the other answers).
- Confirm = **Other / custom input** → incorporate the comment, restate the updated description, and re-ask the full gate once.
- Timeout → Gate policy: reversible — proceed on the recommended defaults, **except Ship, whose timeout default is always Hold** (shipping needs a real answer; holding is free to reverse), labeled `auto-selected on timeout — not user-confirmed`.

For every Verify option the user selects (and any "Other" text), take the one-line verification and its `type` — already known for the proposed ones; for a custom line, infer `type` from the wording (**UX** (frontend only) · **Integration** (backend: endpoint or stored data) · **E2E** (a UI action with a backend effect)). Hold the `{assert, type}` pairs in context — **do not write or commit anything yet**. If only "Nothing to verify" is chosen (or nothing is selected), capture nothing and continue.

**Honor the user's answer.** A free-text reply that declines automated verification ("I'll verify live", "I'll test by eye") is a decision: record this task as `UAT-only`, capture nothing, and skip Step 2.5 — do not persist synthesized entries against the user's stated intent.

Capture the Regression answer as `regression_mode` = `smart` (No) or `full` (Yes). This answer **binds test scope downstream**: it is forwarded to `<PREFIX>-qa` and `<PREFIX>-test`, and neither may widen it (see `<PREFIX>-test` Rules — a full unit-suite re-run is not a permissible "superset").

Capture the Ship answer as `ship_mode` = `prod` (Ship) or `hold`. A user-answered **Ship** is standing consent for the close-out — but it is conditional, and the conditions are verified mechanically at Step 5: it collapses back to a fresh ask if the run wasn't clean.

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

While the agent runs, do **not** edit governed source files at the top level — concurrent writers make QA's diff unattributable.

**Salvage protocol (applies to every subagent in this command):** if an agent dies without a `## Handoff` (watchdog kill, session limit, API error), do not absorb its role at the top level. Inspect `git status` / `git log` to see what landed, then continue the same agent via SendMessage or re-spawn it with a salvage prompt naming what is already done and which contract steps remain (quality checks, deploy, Reference Sync, commit, handoff). A salvaged completion counts as `Status: complete` for the steps below.

## Step 2.5 — Persist captured verifications

Run only if verifications were captured in Step 0.5 (not `skip`, not `UAT-only`) **and** <PREFIX>-dev finished — `Status: complete` or a salvaged completion (captured verifications must never be lost to an agent death). If dev blocked, skip — nothing is written.

For each captured `{assert, type}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`). Keep it **symbolic**: reference behavior and configured values ("matches the configured tolerance"), never volatile constants copied from code — those rot within days and QA then wastes a cycle correcting them
- `type` — the inferred/confirmed type
- `paths` — the dev `## Handoff` `Files changed:` list, **excluding any `.claude/**` paths** (workflow-internal reference/doc edits must not drive prior-selection)

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 3.

## Step 2.7 — Ensure verification stack

Run only if verifications with type `UX` or `E2E` were captured. For each affected component (from the dev `Files changed:` paths), resolve its **first non-prod env** in `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`:
- Env has `deploy:` (ship-env) → nothing to do; <PREFIX>-dev already deployed it.
- Env has `run:` (serve-env) → start or restart it here at the top level (subagents can't hold a server), applying the env's `stack:` block if declared — env-var overrides that wire the frontend to the local backend, the `seed:` command, the `auth:` strategy (see the deploy-config schema). Then poll the url until HTTP 2xx (up to ~60s). If still unreachable, surface the output and ask the user how to proceed before spawning <PREFIX>-qa.
  **Freshness:** a server started before dev's commits is running stale code — restart it so QA tests the new code; a green check against a stale server is non-evidence.
- No non-prod env → continue; <PREFIX>-test reports those verifications blocked and Step 3 handles it.

Leave any server you started running — note it under Done.

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
- `Status: signed-off-with-deferrals` → ask via AskUserQuestion: "QA is clean except these verifications no environment can run: `<UAT-deferred list with reasons>`. Defer to UAT and continue, or stop?" On **Defer** — carry `UAT-deferred: <names> (user-confirmed)` into the Step 4 pm prompt and continue. On timeout — reversible gate: continue, but carry `UAT-deferred: <names> (auto-accepted on timeout — not user-confirmed)`. On **Stop** — halt and report. Never re-spawn qa to relabel its handoff — the deferral status IS the sign-off vocabulary.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — keep the same `regression_mode`. Repeat until signed-off or user aborts.

## Step 4 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off (either signed-off status), capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.
    Feature commit: <the dev Handoff `Commit:` hash — the delivery-log hash, not any later bookkeeping commit>
    UAT-deferred: <names + how confirmed, from Step 3 — omit line if none>

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 5 — Deploy to prod (only if `ship_mode: prod`)

Run only if `ship_mode = prod` (from the `--prod` flag or the Step 0.5 Ship answer). After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and gates via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code.

**Pre-authorization.** If the user answered **Ship** at the Step 0.5 gate (not a timeout default), pass `preauth: user shipped at Step 0.5` to the skill **only when all of these hold** — verified now, not assumed:
- QA status is `signed-off`, or `signed-off-with-deferrals` where the deferral was **user-confirmed** (not auto-accepted on timeout);
- no gate in this run was auto-decided on timeout;
- the commits being shipped are exactly the reviewed set (nothing landed after QA's sign-off except the capture/log commits).

When any condition fails — or Ship was a timeout default — the skill gates normally (ask; on no answer it returns `gate: unanswered — parked` → park per the Gate policy; never decide a prod deploy on the user's behalf). If no `prod` env is declared or the user declines, report that and finish at UAT.

## Step 6 — Close out: push + verified scorecard

Runs on every completion, regardless of `ship_mode`.

**(a) Push.** Skip if `no_push` or no remote is configured. Resolve the push policy via the `<PREFIX>-deploy` skill § Push policy: if pushing the current branch fires a prod CI deploy, pushing IS shipping — push only if Step 5 ran and its gate (or pre-authorization) approved; otherwise ask now (irreversible gate — ask at this moment even if an earlier gate timed out; park only if this ask goes unanswered). If push does not trigger prod, push now.

**(b) Scorecard.** Verify each fact against reality — never echo handoff claims:

| Fact | Evidence |
|---|---|
| Committed | `git log --oneline -5` shows the fix + capture + log commits |
| Pushed | `git rev-list --count @{upstream}..HEAD` → 0, or "not pushed — <reason>" |
| Deployed | curl the env url/health from the dev handoff (2xx), or "no deployable env" |
| Logged | new entry present at top of `docs/project-log.md` (grep the title) |
| Docs | pm handoff `Docs:` field; spot-check the file if `updated` |
| Ref sync | `Reference Sync:` fields from all three handoffs |

**(c) Restore stashed WIP.** If pre-existing WIP was stashed at Step 0, `git stash pop` it now and confirm it restored cleanly; report any conflict instead of resolving it silently.

## Done

Report, in this order:
1. The Step 6 scorecard — each fact with its evidence, any ✗ called out first.
2. QA's `Evidence:` lines verbatim (verification traces, screenshot paths) — this is what lets the user skip re-testing.
3. Anything auto-decided on a gate timeout, explicitly labeled.
4. UAT-deferred verifications as explicit follow-ups.
5. If a serve-env was started in Step 2.7: it is still running, and where (`<url>`).
6. If shipped (`ship_mode: prod`): "deployed to prod" only after `<PREFIX>-deploy` confirmed CI completion + health check. If held (`ship_mode: hold`): "held at UAT per your Ship answer — say ship (or re-run with `--prod`) when ready." If parked: state exactly what awaits your confirmation.
7. If this is the 2nd+ pipeline run in this session, suggest closing out and starting a fresh session — long sessions degrade quality.
```

---

## § /pilot — pilot.md (Claude Code)

```markdown
---
description: Autonomous multi-task run — decompose a goal into tasks, route each through the right lane (full pipeline or tweak), and work unattended until the goal is met. One up-front gate, no mid-run questions, single batched close-out.
---

# Pilot

**Usage:** `/pilot <goal>` — a batch of work (e.g. open roadmap items matching a filter) or a target state to reach (improve an area until measurable criteria pass). Flags: `--max-tasks N` caps the run (default 10); `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push.

**Examples:**
- `/pilot implement all open roadmap items`
- `/pilot work through the high-priority roadmap items --max-tasks 5`
- `/pilot improve <area> until <measurable criteria> --prod`

## Autonomy contract

After the single Step 1 gate, the run is unattended until close-out:
- Reversible decisions are made autonomously with the recommended default and labeled `auto-decided (pilot run — not user-confirmed)` in every downstream record — never presented as user consent.
- Irreversible actions (prod deploy; any push that fires prod CI) never happen mid-run — they are deferred to close-out, where they gate normally per the `/code` Gate policy (ask at the moment of the action; park on silence).
- The user may interrupt at any time; on their next message, resume from the current task using the mission state in context.

## Step 0 — Flags + entry hygiene

**Flag parse (first):** `--max-tasks N` → cap the task list at N (default 10); `--prod` → `ship_mode = prod`; `--no-push` → `ship_mode = hold` and `no_push = true`. Strip all flags from the goal used below. If neither ship flag is present, `ship_mode` is decided by the Ship question in Step 1.

**Entry hygiene:** run `git status --porcelain`. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it at close-out. If the WIP overlaps paths this mission will touch, ask the user how to proceed instead of stashing.

## Step 1 — Mission plan + single gate

**Decompose.** Build the task list from whichever source applies:
- **Roadmap-shaped goal** (the goal names the roadmap or matches its items): read `docs/roadmap.md`, select the open items the goal covers, order by priority then dependency.
- **Target-state goal** ("improve X until Y"): derive 2–3 **success criteria** — measurable checks, each with a command or observable that decides pass/fail — then derive the initial tasks that most plausibly move toward them. The loop re-plans between tasks; the criteria, not the initial list, define done.
- **Plain batch** (an explicit list of things to do): one task per item.

Cap at `max_tasks`. For each task derive: a one-line description, 1–3 candidate verifications (`{assert, type}` — UX / Integration / E2E, same vocabulary as `/code` Step 0.5), and a **lane**:
- `pipeline` — features, bug fixes, schema/API/auth changes, anything needing review depth. Default when unsure.
- `tweak` — small inline-verifiable changes (pixel nudges, copy, config values) per the `/tweak` lane rules.

**Split broad tasks (do this before the gate).** A single item that applies **one uniform change across an enumerable set** — phrased with "~N", "each", "all/every X", plural targets, "across the <collection>" — is really N sub-tasks. Bundled into one pipeline task it balloons the dev agent past a healthy context window and hands QA an unreviewable diff (the observed failure: one "invert ~9 modules" item ran 49 turns / 222k context / 41 min and had to spawn its own sub-agents to cope). For each such task, enumerate the concrete target set, then:
- **Split into bounded chunks** — group the set so each chunk is one coherent review unit (rule of thumb: ≤~5 files of the same uniform change per chunk), one `pipeline` task per chunk, sharing the parent's verifications. This is the **default** — a bounded pipeline unit keeps context healthy and the per-task diff reviewable.
- **Cap tension:** if splitting would exceed `max_tasks`, don't silently drop chunks — keep the item **whole** but tag it `[large]` in the gate list with the target count, so the user sees the ballooning risk and can raise `--max-tasks` or pre-split via "Other". Never split a task whose changes are genuinely interdependent (a single edit touching N files together) — that's one review unit, not a set; tag it `[large]` instead.

**Gate.** Ask everything in **one AskUserQuestion call** — the only planned interaction of the run:

1. **Confirm**:
   - question: "Fly this mission? <goal> — <N> tasks: <numbered task list with lanes and verifications; split chunks shown as sub-items; any `[large]` tag with its target count; success criteria if any>"
   - header: "Confirm"
   - options:
     - label: "Launch (Recommended)" — description: "Run all tasks unattended; everything holds at UAT until close-out"
     - label: "No, cancel" — description: "Stop here"
   - The automatic "Other" field lets the user reorder, drop, or add tasks and amend verifications or criteria — incorporate, restate the updated plan, and re-ask the full gate once.
2. **Ship** (omit when `--prod` or `--no-push` already decided it):
   - question: "Ship after the mission completes clean?"
   - header: "Ship"
   - options:
     - label: "Ship (Recommended)" — description: "If every task signs off clean, deploy/push to prod at close-out without asking again. On projects where push fires prod CI, shipping = prod deploy."
     - label: "Hold at UAT" — description: "End committed but not pushed/deployed; ship later with /code --prod or by asking"

Timeout → same risk split as the `/code` Gate policy: launch on the recommended defaults labeled `auto-selected on timeout — not user-confirmed`, **except Ship, whose timeout default is always Hold**. Regression scope is fixed at `smart` for every task — a full regression per task would multiply cost across the mission; each task's QA already runs prior verifications for the files it touched.

## Step 2 — The loop

Work the task list in order until: tasks exhausted, all success criteria pass, or `max_tasks` tasks completed. No user gates inside the loop.

**(a) Pipeline lane** — run the `/code` machinery without its interactive steps (`.claude/commands/code.md` holds the exact mechanics; reuse them, replacing every mid-run AskUserQuestion with the autonomous branch below):
1. Spawn `<PREFIX>-dev` with the task + its verifications (`/code` Step 1 prompt shape). The salvage protocol and the no-top-level-edits rule apply verbatim.
2. On `Status: complete`, persist the task's verifications exactly as `/code` Step 1.5 (single-quoted scalars, `.claude/**` excluded from `paths`, `test:` commit). On `Status: blocked`, mark the task **failed** with dev's `Notes:` and go to (c).
3. Ensure the verification stack as `/code` Step 1.7 — except on an unreachable env, don't ask: leave the affected verifications to report blocked and continue (they surface as deferrals below).
4. Spawn `<PREFIX>-qa` `mode=initial`, `regression_mode: smart`, with the new verification names + changed paths. Branch on its handoff:
   - `signed-off` → continue to 5.
   - `signed-off-with-deferrals` → **auto-accept** (no mid-run gate): carry `UAT-deferred: <names> (auto-accepted — pilot run, not user-confirmed)` into the pm prompt and the mission report, then continue to 5.
   - `blocked` with code-fix `Notes:` → re-spawn `<PREFIX>-dev` with the fix, then `<PREFIX>-qa` `mode=retest`. At most **2 fix cycles per task**; still blocked → mark the task **failed** with qa's notes. If the failure leaves the tree broken (smoke fails), `git revert` the task's commits before moving on. If later tasks depend on this one, stop the loop and go to Step 3.
5. Spawn `<PREFIX>-pm` with the feature commit, any UAT-deferred line, and the verbatim QA-evidence block (`/code` Step 3 prompt shape).

**(b) Tweak lane** — top-level inline work under the `/tweak` lane rules: load the owning domain skill first, verify every change inline with shown evidence, commit in small named steps. Task exit: use the `<PREFIX>-review` skill on the task's diff (fix non-source nits directly; a source finding needing review depth → reclassify the task to the pipeline lane and run (a)), then one `<PREFIX>-log` entry for the task. **Scope guard:** if the work grows into schema/API/auth/migrations, reclassify to the pipeline lane before continuing.

**(c) Progress + re-plan.** After each task, emit one status line — `task k/N · <title> · <status> · <commit> · <evidence pointer>` — a report, not a question. Then re-plan: drop later tasks the outcome obsoleted, insert a revealed prerequisite (within `max_tasks`), and if success criteria exist, evaluate them with evidence — stop the loop when all pass. Record every plan amendment for the mission report. For roadmap-driven runs, verify pm flipped the item's status.

**Context health:** keep the top level thin — never read source files or heavy references at the top level; work from handoff blocks. If context is clearly degrading (earlier tasks summarized away, repeated re-derivation), finish the current task, then go to Step 3 and list the remaining tasks as resumable — a degraded pilot ships worse code than a fresh session.

## Step 3 — Close out (once per mission)

**(a) Deploy to prod** — only if `ship_mode = prod`. Invoke the `<PREFIX>-deploy` skill **here at the top level** with `target=prod`. Pass `preauth: user shipped at the mission gate` **only when all of these hold** — verified now, not assumed: every completed task is `signed-off` (no deferrals, no failed tasks), Ship was user-answered (not a timeout default), and the commits being shipped are exactly the reviewed set (nothing after the sign-offs except capture/log commits). Otherwise the skill gates normally — the user is often back by close-out; on no answer it returns `gate: unanswered — parked` → park per the `/code` Gate policy. If no `prod` env is declared or the user declines, report that and finish at UAT.

**(b) Push.** Skip if `no_push` or no remote is configured. Resolve via the `<PREFIX>-deploy` skill § Push policy: if pushing fires a prod CI deploy, pushing IS shipping — push only if (a) ran and its gate (or pre-authorization) approved; otherwise ask now (irreversible gate — park on silence). If push does not trigger prod, push now.

**(c) Scorecard.** Verify each fact against reality — never echo handoff claims:

| Fact | Evidence |
|---|---|
| Tasks | per task: feature commit in `git log`, QA status, log-entry title grepped in `docs/project-log.md` |
| Pushed | `git rev-list --count @{upstream}..HEAD` → 0, or "not pushed — <reason>" |
| Deployed | curl the env url/health (2xx), or "no deployable env" / "held" |
| Roadmap | roadmap-driven runs: item statuses flipped in `docs/roadmap.md` |
| Ref sync | `Reference Sync:` fields from the handoffs |

**(d) Restore stashed WIP.** If pre-existing WIP was stashed at Step 0, `git stash pop` it now; report any conflict instead of resolving it silently.

## Done — mission report

Report, in this order:
1. Goal outcome — met / partial / stopped — with success-criteria evidence if criteria were set.
2. The task table: task · lane · status (`signed-off` / `deferred` / `failed` / `dropped` / `not-reached`) · commit · log entry.
3. QA `Evidence:` lines per task, verbatim.
4. Everything auto-decided, explicitly labeled: gate timeouts, auto-accepted deferrals, plan amendments.
5. Failed and unreached tasks as follow-ups, with enough state to resume (`/pilot <remaining goal>` re-derives the plan from the roadmap or criteria).
6. Serve-envs still running and where (`<url>`).
7. Ship state: "deployed to prod" only after `<PREFIX>-deploy` confirmed CI completion + health check; "held at UAT per your Ship answer"; or parked — state exactly what awaits confirmation.
8. Recommend a fresh session before the next mission — a completed pilot has consumed most of this one.
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

## § /tweak — tweak.md (Claude Code)

```markdown
---
description: Sanctioned lightweight lane for iterative work — pixel nudges, copy rounds, small hotfixes — at the top level, without the full pipeline. Close-out is batched and enforced at push time.
---

# Iterate

**Usage:** `/tweak <description>` — small, iterative, inline-verified changes. For features and bug fixes that need review depth, use `/code` / `/fix`.

**Examples:**
- `/tweak nudge the map labels so city names don't overlap`
- `/tweak reword the pricing card subtitles`

## Lane rules

- Work happens at the top level — no dev/qa/pm subagents. Skill governance still applies: load the owning domain skill before editing (skill-guard enforces this).
- **Verify inline after every change:** visual change → screenshot via agent-browser and show it; backend change → curl/command with the observed output shown. No unverified iteration rounds.
- Commit in small named steps. Do **not** write a delivery-log entry per commit — close-out is batched at exit.
- **Scope guard:** if the work grows into schema/API changes, auth, migrations, or anything needing review depth, stop and route it through `/code` or `/fix` instead.

## Exit — batched close-out (mandatory)

Run when the user says done, or asks to push or deploy. (The `close-out-gate` hook blocks push and deploy until a delivery-log entry covers the burst — iterate freely, but nothing leaves the machine without this.)

1. **Review the burst** — use the `<PREFIX>-review` skill on the accumulated diff since the last delivery-log entry. Fix non-source nits directly; a source finding that needs real review depth → route to `/fix`.
2. **Log** — one `<PREFIX>-log` entry covering the whole burst (name the commits it spans).
3. **Docs + references** — use `<PREFIX>-docs` to check staleness; use `<PREFIX>-skill` for reference sync scoped to the affected skills.
4. **Push + scorecard** — same close-out as `/code` Step 5: push policy via the `<PREFIX>-deploy` skill § Push policy (a push that fires prod CI is an irreversible gate — ask, park on timeout), then the verified scorecard (committed / pushed / logged / docs / ref-sync, each evidence-checked).
```

---

## § /revert — revert.md (Claude Code)

```markdown
---
description: Sanctioned rollback — git revert (never reset), scoped re-verification via <PREFIX>-test, and a logged reversal.
---

# Revert

**Usage:** `/revert <commit-ish or description of what to undo>`

## Step 0 — Confirm scope

Identify the commits to undo from `git log --oneline` and the delivery log. Present the exact commit list via AskUserQuestion before touching anything. **Never `git reset` shared history** — `git revert` preserves the audit trail (a reset once destroyed a delivery-log commit alongside the target).

## Step 1 — Revert

`git revert` the confirmed commits (newest first). Resolve conflicts; keep revert commits separate from any new work.

## Step 2 — Re-verify

Use the `<PREFIX>-test` skill: Smoke + every `custom-tests.yaml` verification whose `paths` intersect the reverted files. A failure here means the revert is incomplete — fix before proceeding. Retire or amend any captured verification that asserted the now-reverted behavior.

## Step 3 — Log the reversal

Use `<PREFIX>-log`: one entry naming what was reverted and why. Flip any roadmap item the reverted work had closed back to `open`.

## Step 4 — Close out

Push + verified scorecard, same as `/code` Step 5. If the original change was deployed, redeploy the reverted state to the same envs via `<PREFIX>-deploy` (prod requires its gate — park on timeout).
```

---

## § /wrap — wrap.md (Claude Code)

```markdown
---
description: Manually trigger post-change close-out — <PREFIX>-log + <PREFIX>-docs + <PREFIX>-skill reference sync. Use when work happened outside the /code or /fix pipelines.
---

# /wrap

Close-out for changes made **outside** the normal `/code`/`/fix` pipeline — ad-hoc edits, direct data fixes, manual config changes, or any work where `<PREFIX>-pm` didn't run automatically. The `/code` and `/fix` pipelines run `<PREFIX>-pm` at the end; use `/wrap` only when they didn't.

**Usage:** `/wrap <description of what changed>` — append `--no-push` to skip the close-out push

**Examples:**
- `/wrap manually updated database row to fix corrupted state`
- `/wrap changed configuration value in cloud console`
- `/wrap ad-hoc script run that imported new dataset`

## Step 0 — Review (conditional)

If commits since the last delivery-log entry touch governed source paths (check `governed-paths.conf` `GOVERNED_ROOTS` against `git diff --name-only`), use the `<PREFIX>-review` skill on that diff first — ad-hoc source changes otherwise ship on self-review only. Fix non-source nits directly; a source finding needing depth → route to `/fix`. Skip this step when only docs/config/data changed.

## Step 1 — Delivery log

Use `<PREFIX>-log` skill to append a log entry to `docs/project-log.md` for the most recent commit. Pass `$ARGUMENTS` as context for the entry title and body.

## Step 2 — Docs sync

Use `<PREFIX>-docs` skill to check whether project docs need updating based on what changed. Update any that are stale. Pass `$ARGUMENTS` as context.

## Step 3 — Reference sync

Use `<PREFIX>-skill` skill to run the reference sync check:
- Verify `governed-paths.conf` matches current directory structure
- Confirm `## References` and `## Reference Sync` parity per the `<PREFIX>-skill` parity invariant (static-content skills exempt, or scoped to their project-authored references)
- Confirm `skill-manifest.md` is current

Scope to affected skills only — do not run a full manifest audit unless something actually changed.

## Step 4 — Push + scorecard

Skip if `--no-push` was passed or no remote is configured. Resolve pushability via the `<PREFIX>-deploy` skill § Push policy: a push that fires a prod CI deploy is an irreversible gate (ask via AskUserQuestion; park on timeout — never push on silence); otherwise push now. Then verify against reality — never claims: committed (`git log --oneline -3`), pushed (`git rev-list --count @{upstream}..HEAD` → 0, or "not pushed — <reason>"), logged (entry at top of `docs/project-log.md`).

## Done

Tell the user: "Wrapped. Log, docs, and skill references are up to date." — followed by the Step 4 scorecard (committed / pushed / logged, each with its evidence).
```
