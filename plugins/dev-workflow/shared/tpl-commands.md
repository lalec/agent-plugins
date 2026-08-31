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

**Usage:** `/code <description>` — the Step 0.5 gate states what will be verified and asks whether to ship after sign-off. `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push; `--regression full|smart` pins the test scope that is otherwise resolved from the change itself.

**Examples:**
- `/code add export to CSV button on assessment list`
- `/code change pipeline phases status indication`
- `/code <description> --prod`

## Gate policy (governs every AskUserQuestion in this command)

If a question times out unanswered, split by risk:
- **Reversible** (confirm, ship choice, UAT-defer): proceed with the recommended default and label every downstream record `auto-selected on timeout — not user-confirmed` (handoffs, delivery log, final report). **Never present a timeout as user consent** — not to a subagent, not in a log, not in the report.
- **Irreversible** (prod deploy; any push that fires a prod CI deploy): **park** — do not proceed and do not decide. End the turn stating exactly what awaits confirmation and how to resume; on the user's next message, resume from the parked step. Park only after actually asking at the moment of the irreversible action — never skip the ask because an earlier, unrelated gate timed out; the user may have returned.

## Step 0 — Flags + entry hygiene

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `ship_mode = prod`; if it contains `--no-push`, set `ship_mode = hold` and `no_push = true`. If it contains `--regression full` or `--regression smart`, pin `regression_mode` to that value. Strip every flag from the task description used in every step below. If no ship flag is present, `ship_mode` is decided by the Ship question in the Step 0.5 gate; if no `--regression` flag is present, `regression_mode` is `auto` and the scope is resolved from the change itself (Step 0.5).

**Entry hygiene:** run `git status --porcelain` and `git rev-list --count @{upstream}..HEAD` (report "no upstream" rather than failing when the branch has none). If the count is non-zero, say so in one line with the reason if you can see it — held commits are work that already passed review and is waiting on a decision, and **nothing else raises them**: a close-out's Open row dies with its session, and entry hygiene is the only step that runs before every task. Report, do not gate; if the held set overlaps the paths this task will touch, say that too, because the task is about to build on unshipped work. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it in the close-out step — the pre-handoff gate blocks the qa spawn on any dirty tree, so deferring the stash just moves the failure mid-pipeline. If the WIP overlaps paths this task will touch, do not stash it blind — tell the user and run `/tidy` scoped to the overlapping paths first, then resume here.

**Open deferrals:** run `python3 .claude/graph/graph.py open-deferrals` and, if it returns anything, **split what comes back into three buckets before reporting it**: (1) a deferral whose `reason` names a *structural* fact — a component that only ships to prod, a journey that ends on a schedule, a cost- or quota-bound external call — can never be closed by a local run and is **counted, not listed** ("58 structurally unprovable: the worker declares no non-prod env, image generation is quota-bound"); (2) everything else with a reason is **closable** and gets listed; (3) a row with **no reason at all** is **unclassified** — counted separately and labelled as written before reasons were required. Never guess which of the first two an unclassified row belongs to: the text was never written and is not recoverable, so a guess would either inflate the backlog you act on or hide work in the count you ignore. New deferrals all carry a reason, so this bucket only shrinks. Without the split the list grows without bound as the same two facts re-defer on every task, and a number nobody reads is the same as no report at all. Then list the closable ones for the user in one line — these are verifications that are still unproven and nothing has passed since: either an earlier task formally deferred them, or a run recorded them `blocked` (which is what the vacuous-pass rule mandates when the assertion never got exercised). A blocked row carries its `reason` — the trigger that would close it — so quote that, not just the name. This read is the reason a deferral is an Emerged row at close-out rather than something the user has to hold: the three lanes that can discharge one — `/code`, `/fix`, `/pilot` — all open with it. Report, do not gate — **with one exception: if the same *fixable* blocker is named by 3+ open deferrals, or any single verification has been deferred 3+ times, say so and ask whether to fix the blocker first.** Repeated deferrals of that kind are not a backlog, they are one missing capability (usually a test environment) charging rent on every task that follows; five checks deferred across three deploys is how a feature ships unwalked. **Fixable means someone could build it** — seed data, an auth strategy, a `stack:` block, a missing non-prod env. A structural fact is not a blocker to escalate: a component that only ships to prod, or a journey that ends on a schedule, will produce deferrals forever and asking every third run is noise, not signal. Those are discharged by the post-deploy prod walk and by triggered follow-ups respectively — count them, never nag about them. Skip silently if the script is absent or exits non-zero. (Cheap by design — a few lines of output, not a file read; the Step 0.5 gate stays read-free.) Only the lanes that can turn a `blocked` into a `pass` run this read — `/code`, `/fix`, `/pilot`. `/tweak`, `/wrap`, `/revert` and `/tidy` persist no typed verifications and could not discharge one, so listing them there would be noise the user cannot act on.

**Plan shortcut:** if the session contains a just-approved plan covering this task **and that plan carries its own Verification / Acceptance section**, plan approval was the confirmation — omit the Confirm question from the Step 0.5 gate. Both halves are required: Confirm is the only place the derived verifications are shown, so omitting it on a plan that never stated an end state would ship a set the user has never seen — and with `--prod` or `--no-push` also pre-answering Ship, the gate would fall to zero questions.

## Step 0.5 — Single gate: confirm the plan of record

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

First write the **acceptance statement**: one sentence naming the end state in the user's terms — who does what, and where they end up. State the outcome, not the change. *"A user picks a look in the gallery and lands on the generate step with a pack built from it"* — never *"the gallery selection has a visible outcome"*. When the task names only a symptom ("clicking it does nothing"), the acceptance statement is the journey that symptom sits in: ask what the click is *for*, and say where it ends. Derive it from whichever source applies:
- **A plan exists** (the current session has a just-approved plan with a *Verification* / *Acceptance* section): the plan's outcome is the acceptance statement.
- **No plan** (e.g. `/code` invoked first thing in a fresh context): infer it from the task (`$ARGUMENTS`, with any flags already stripped) — the default fallback whenever no plan is in context.

Then derive 2–3 **verifications** *from that statement*. Each must be a clause of the acceptance statement — never an independent thought about the diff. A plan's lines describe *how it's proven*; restate each as *what must hold* so it reads as a regression invariant.

| Part of the acceptance statement | Type |
|---|---|
| The end state the user lands on | **E2E** — mandatory |
| Each boundary the journey crosses (UI → API, API → stored data) | **Integration** |
| Each surface the user acts on | **UX** |

**The end-state verification is not optional, and it is the one that proves the feature.** A set that checks every hop but not where the user lands passes while the journey dead-ends — a button that exists, is clickable, and leads nowhere. If nothing covers the last step of the statement, the *set* is wrong; fix it before asking. This is the whole point of deriving from an acceptance statement rather than from the diff: the diff cannot tell you the journey has an end.

**You derive the set — the user does not assemble it.** The gate states what will be verified and the free-text reply amends it; there is no pick-list, because choosing between checks you just derived is work the user should not have to do, and a picker invites dropping the end state one option at a time.

**No behavioral surface is the only exemption.** A task that changes nothing a user or caller can observe (docs, comments, a rename with no observable effect) derives an empty set — then say so **and name why** in the Confirm text, so an empty set is a visible claim rather than a silent omission. Anything that changes behavior has an end state; "no check came to mind" is not the same fact as "there is nothing to check".

Then ask in **one AskUserQuestion call** (at most two questions) — one gate interaction, so an AFK timeout costs 60 seconds once for the whole run:

1. **Confirm** (omit this question only when the plan shortcut applies):
   - question: the plan of record, on its own lines —
     ```
     Done means: <the acceptance statement>.
     Verifying: <assert> (E2E) · <assert> (Integration) · <assert> (UX)
     Regression: <"resolved after implementation, from the paths actually changed" | "full — pinned by --regression" | "smart — pinned by --regression">
     Proceed?
     ```
     With an empty set, the `Verifying:` line reads `nothing — <why this task has no behavioral surface>`. Leading with the end state is the point: this is the user's chance to correct the *goal*, which is cheap here and expensive after dev has built to the wrong one.
   - header: "Confirm"
   - options:
     - label: "Yes, proceed (Recommended)" — description: "Run the full <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm pipeline and verify exactly the checks above"
     - label: "No, cancel" — description: "Stop here, do not implement"
2. **Ship** (omit when `--prod` or `--no-push` already decided it):
   - question: "Ship after QA sign-off?"
   - header: "Ship"
   - options:
     - label: "Ship (Recommended)" — description: "After a clean sign-off, deploy/push to prod at close-out without asking again. On projects where push fires prod CI, shipping = prod deploy."
     - label: "Hold at UAT" — description: "End committed but not pushed/deployed; ship later with --prod or by asking"

Branch on the answers:
- Confirm = **Yes** or **timeout** → the stated set is the set. Gate policy: reversible — proceed on the recommended defaults, **except Ship, whose timeout default is always Hold** (shipping needs a real answer; holding is free to reverse), labeled `auto-selected on timeout — not user-confirmed`. Silence is acceptance *only because the set was shown* — which is why the plan shortcut may never omit Confirm on a plan that stated no end state.
- Confirm = **No, cancel** → tell the user it was cancelled and stop (discard the other answers).
- Confirm = **Other / custom input** → read the reply as exactly one of the rows below. When it could be read two ways, take the **earliest** matching row: re-asking costs one interaction, building to the wrong end state costs a pipeline.

| The free-text reply… | Do |
|---|---|
| restates the goal or the end state | it is the **new acceptance statement** — re-derive the whole set from it, restate, and re-ask the gate **once** |
| names, replaces, or removes checks | amend the set, then proceed without re-asking. The end-state rule still binds: if the amendment leaves the last step of the statement uncovered, say so and put a check back |
| names test scope ("run full regression", "smoke only") | pin `regression_mode` to it and proceed |
| declines automated verification ("I'll verify live") | the UAT-only path below |

**Honor the user's answer.** A free-text reply that declines automated verification ("I'll verify live", "I'll test by eye") is a decision: record this task as `UAT-only`, capture nothing, and skip Step 1.5 — do not persist synthesized entries against the user's stated intent.

Hold the resulting `{assert, type}` pairs in context — **do not write or commit anything yet**. For a verification the user supplied in free text, infer `type` from the wording (**UX** (frontend only) · **Integration** (backend: endpoint or stored data) · **E2E** (a UI action with a backend effect)).

**Regression scope is not asked here, and not decided here.** At this point <PREFIX>-dev has not run, so there is no changed-path list and any answer would be a guess about a diff that does not exist yet. Carry the value pinned by `--regression`, else the default `regression_mode: auto`:
- `auto` authorizes `<PREFIX>-test` to resolve the scope **once**, from the paths dev actually changed (see `<PREFIX>-test` → *Regression scope*). The resolved value, and its reason, come back on the qa handoff's `Tests:` line.
- A **pinned** value binds in **both directions** — nothing downstream may widen it and nothing may narrow it (see `<PREFIX>-test` Rules — a full unit-suite re-run is not a permissible "superset").

Capture the Ship answer as `ship_mode` = `prod` (Ship) or `hold`. A user-answered **Ship** is standing consent for the close-out — but it is conditional, and the conditions are verified mechanically at Step 4: it collapses back to a fresh ask if the run wasn't clean.

## Step 1 — Implement (<PREFIX>-dev)

Task:
  subagent_type: <PREFIX>-dev
  prompt: |
    Implement the following for <PROJECT>: $ARGUMENTS
    Complete the full <PREFIX>-dev workflow (domain skills, implement, deploy, Reference Sync).
    Done means: <the acceptance statement from Step 0.5> — this is the task, not the diff that
    approaches it. The journey's last step must be reachable by a user before you report complete.
    Verifications (these must hold when done): <the verifications captured in Step 0.5, or "none">

While the agent runs, do **not** edit governed source files at the top level — concurrent writers make QA's diff unattributable.

**Salvage protocol (applies to every subagent in this command):** if an agent returns **anything that is not a `## Handoff` block** — it died (watchdog kill, session limit, API error) **or** it ended its turn with an interim/progress status — do not absorb its role at the top level. Inspect `git status` / `git log` to see what landed, then resume with a salvage prompt naming what is already done and which contract steps remain (quality checks, deploy, Reference Sync, commit, handoff). **The two resume mechanisms are not interchangeable — they differ in control flow, not just in cost:**

- **SendMessage — preferred.** It preserves the agent's context, so a fix round returns a delta instead of re-deriving the task. But resuming a completed agent **always runs detached**: the call returns immediately saying it resumed in the background, and *that return is not a status* — it reports nothing about the work. Do not read it as progress, do not act on it, and never forward it as an interim update. **End the turn.** The real result arrives later as a task notification, and only the `## Handoff` inside it counts. Waiting through this on the same turn is impossible; that is the mechanism, not a failure.
- **Re-spawn (`Agent`, `run_in_background: false`).** Blocks in-turn and hands back the handoff directly, but the fresh agent re-reads its way back to the current state. Use it when the agent's context is not worth preserving, or its transcript is unusable.

The trap is that SendMessage's immediate return looks exactly like the interim return this protocol treats as a stall — so a top level that "checks the result" after resuming re-triggers salvage on an agent that is working fine, or reports a parked step as done. Resume, then wait for the notification; never infer state from the resume call itself. A salvaged completion counts as `Status: complete` for the steps below.

A **parked** agent is the failure mode to watch for, because nothing announces it: an agent that backgrounds a long wait (a deploy watch, a poll loop) and returns control cannot be woken by that task — its completion notification is delivered here, to the top level, not to the dormant agent. So an interim return is never "still working"; it is a stalled step. Treat the missing `## Handoff` as the trigger and resume the agent. If the outstanding work is a wait, own the wait here and hand the result to the resumed agent — this is the same reason gates and the verification stack live at the top level: **only the top level has the channel** (to the user, to a held server, to an async completion).

## Step 1.5 — Persist captured verifications

Run unless the task was recorded `UAT-only` or the derived set was empty (no behavioral surface) — and only once <PREFIX>-dev has finished — `Status: complete` or a salvaged completion (captured verifications must never be lost to an agent death). If dev blocked, skip — nothing is written.

For each captured `{assert, type}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`). Keep it **symbolic**: reference behavior and configured values ("matches the configured tolerance"), never volatile constants copied from code — those rot within days and QA then wastes a cycle correcting them
- `type` — the inferred/confirmed type
- `paths` — the dev `## Handoff` `Files changed:` list, reduced to **behavioral surface only**: paths whose change could actually break the assertion. Exclude **documentation-only paths** (`docs/**`, `*.md` outside source trees, and any other docs-only tree this project keeps) and **workflow-internal reference/doc paths** under `.claude/**` — neither can change runtime behavior, so neither may drive prior-selection. One exception: executable source that happens to live under `.claude/` (e.g. `.claude/skills/**/scripts/**`) **is** behavioral surface and must be kept. If this reduction would leave `paths` empty, the entry is mis-anchored — name the code the assertion is actually about instead of storing the docs that described it

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 2.

## Step 1.7 — Ensure verification stack

Run only if verifications with type `UX` or `E2E` were captured. For each affected component (from the dev `Files changed:` paths), resolve its **first non-prod env** in `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`:
- Env has `deploy:` (ship-env) → nothing to do; <PREFIX>-dev already deployed it.
- Env has `run:` (serve-env) → start or restart it here at the top level (subagents can't hold a server), applying the env's `stack:` block if declared — env-var overrides that wire the frontend to the local backend, the `seed:` command, the `auth:` strategy (see the deploy-config schema). Then poll the url until HTTP 2xx (up to ~60s). If still unreachable, surface the output and ask the user how to proceed before spawning <PREFIX>-qa.
  **Freshness:** a server started before dev's commits is running stale code — restart it so QA tests the new code; a green check against a stale server is non-evidence.
- No non-prod env → continue; <PREFIX>-test reports those verifications blocked and Step 2 handles it.

Leave any server you started running — note it under Done.

## Step 2 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, parse its `## Handoff` block — and keep its `Roadmap:` ids: they are the Emerged rows for scope the agent tracked, and nothing else carries them out of the subagent:
- `Status: complete` → spawn <PREFIX>-qa with `mode=initial`.
- `Status: blocked` → tell the user dev blocked with `Notes:` and stop.

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. mode=initial
    regression_mode: <auto | smart | full, from Step 0.5 — `auto` unless --regression pinned it>
    Done means: <the acceptance statement from Step 0.5> — walk it end to end and report where it
    actually lands. Green on the individual checks while the journey dead-ends is a `blocked`, not a
    sign-off; the assertions are evidence for the statement, never a substitute for it.
    New verifications this task: <names from Step 1.5, or "none">
    Changed paths: <the dev Handoff `Files changed:` list>
    Sign off when quality gates pass.

After <PREFIX>-qa returns, parse its `## Handoff` block:
- `Status: signed-off` → continue to Step 3.
- `Status: signed-off-with-deferrals` → **first check what is being deferred.** Hop-level checks (a boundary, a surface) defer normally. If a deferral covers the **end state** of the acceptance statement, the journey is unproven, and what happens next depends on *why* — which `deploy-config.yaml` already answers, so read it rather than judging:
  - **A non-prod env for that component exists** and the end state still wasn't walked → the gap is fixable and is being avoided. Do not offer the deferral. Say which journey cannot be walked and what is missing (usually seed data, auth, or a `stack:` block), and ask whether to build that or stop. **This is the only case that blocks.**
  - **No non-prod env is declared** (the component ships only to prod) → nothing was avoided; the project cannot prove this before shipping and never could. Carry the end-state check forward as `prod-walk: <verification name>` into Step 4 and continue. It is **not** discharged here and **not** handed to the user.
  - **The end state is triggered out-of-band** (a schedule, a webhook, an external callback) → it cannot be walked on demand at any point in this run. Defer it, but only with a **named trigger, expected observable, and where to look** (e.g. "next 03:00 run writes a summary row for yesterday; check the jobs collection"). A deferral without those three is not a deferral, it is a shrug — send it back rather than accepting it. Otherwise ask via AskUserQuestion: "QA is clean except these verifications no environment can run: `<UAT-deferred list with reasons>`. Defer to UAT and continue, or stop?" On **Defer** — carry `UAT-deferred: <names> (user-confirmed)` into the Step 3 pm prompt and continue. On timeout — reversible gate: continue, but carry `UAT-deferred: <names> (auto-accepted on timeout — not user-confirmed)`. On **Stop** — halt and report. Never re-spawn qa to relabel its handoff — the deferral status IS the sign-off vocabulary.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — passing **the scope qa resolved on the first pass**, taken from its `Tests:` line, never `auto` again. Re-sending `auto` would let the scope flip mid-task, and the delivery log records one `regression=` value for the task. Repeat until signed-off or user aborts.

## Step 3 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off (either signed-off status), capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.
    Feature commit: <the dev Handoff `Commit:` hash — the delivery-log hash, not any later bookkeeping commit>
    UAT-deferred: <names + how confirmed, from Step 2 — omit line if none>
    Decisions: regression=<the scope qa resolved, smart|full> (<agent|user|timeout> — `agent` when Step 0.5 carried `auto`, `user` only when --regression pinned it) · ship=<prod|hold> (<user|timeout>)<append ` · defer=accept (<user|timeout>)` when the Step 2 deferral gate ran>
    Changed paths: <the dev Handoff `Files changed:` list>

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 4 — Deploy to prod (only if `ship_mode: prod`)

Run only if `ship_mode = prod` (from the `--prod` flag or the Step 0.5 Ship answer). After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and gates via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code.

**Pre-authorization.** If the user answered **Ship** at the Step 0.5 gate (not a timeout default), pass `preauth: user shipped at Step 0.5` to the skill **only when all of these hold** — verified now, not assumed:
- QA status is `signed-off`, or `signed-off-with-deferrals` where the deferral was **user-confirmed** (not auto-accepted on timeout);
- no gate in this run was auto-decided on timeout;
- the commits being shipped are exactly the reviewed set (nothing landed after QA's sign-off except the capture/log commits).

When any condition fails — or Ship was a timeout default — the skill gates normally (ask; on no answer it returns `gate: unanswered — parked` → park per the Gate policy; never decide a prod deploy on the user's behalf). If no `prod` env is declared or the user declines, report that and finish at UAT.

**Prod walk (run when Step 2 carried a `prod-walk:`, or when any prod-only deferral covers what this deploy just shipped).** After the deploy succeeds, walk the acceptance statement against prod **here at the top level** and report where it lands — the same end-to-end trace qa would have run, against the only environment that can host it. This is the whole point of the prod-only branch: a project that cannot prove a journey before shipping proves it immediately after, using the access this pipeline already has. Handing the user a checklist for a flow you can reach yourself is not a verification, and "I have prod access but asked you to click it" is the failure this step closes. Record the outcome in the scorecard and update the verification's `last:` accordingly — pass discharges it, failure opens a `/fix` with the journey as its acceptance statement. If prod genuinely cannot be reached from here (no credentials, human-only auth), say so explicitly and name what the user must click — a checklist is the fallback, never the default.

**Then drain what this deploy made provable.** A prod-only check is discharged by *a* prod deploy, not only by the task that first deferred it — so on a project that habitually holds at UAT, those checks accumulate forever while every `--prod` run walks one and leaves the rest. Run `python3 .claude/graph/graph.py blast <the paths this deploy shipped>` and walk every still-open prod-only deferral it returns, exactly as above. **The shipped paths are the bound** — do not walk the whole backlog, and never re-walk a check this deploy could not have affected. Report the ones you walked and the count still carried; if the graph is unavailable, walk only this task's carry and say the sweep was skipped.

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

## Done — the close-out report

**State where things stand. Do not narrate the run.** `docs/project-log.md` already records what happened; this report exists so the user can see the state of the work without reading the transcript. Every closing command reports in this shape and cites this section — `/fix`, `/wrap`, `/tweak`, `/revert`, `/tidy`, `/pilot`, `/whats-up`.

Five blocks, in this order, then one closing line, and nothing else. No preamble, no recap, no step-by-step account.

**1. Verdict** — one line: what state the work is in, and whether it needs the user.

**2. Learned** — **at most 3 bullets**, and often `None`. Admit only what changes what the reader believes or would change a decision they are about to make: a number they rely on that turns out to measure something else, a defect that passed every existing test, a surface that was being verified and did not exist. Not a recap of what was done — Status covers that — and not every interesting thing the run noticed. It sits second because it is the part that cannot be reconstructed from the diff or the log, so it must not be below the fold. **The cap is the rule that matters**: three bullets is a report, ten is the narrative this shape replaced. A finding that needs *action* is not a bullet here — it is an Open row, or a roadmap item in Emerged.

**3. Status** — one row per thing that was meant to happen or was checked:

| What | Status | Evidence |
|---|---|---|

Rows: the acceptance statement itself, each verification that ran, the deploy, the push, the delivery log, docs, reference sync, plus the facts the run produced that need no action — a serve-env left running, a value the pipeline resolved for you. Rows that are not in a good state come first. The deploy / push / log / docs / ref-sync rows are the Step 5 scorecard facts — each one checked against reality there, never echoed from a handoff.

Every row takes one word from this closed set. Nothing else may be dressed up as a status:

| Status | Means |
|---|---|
| `needs you` | Nothing moves until a person answers or acts |
| `failed` | It ran and did not hold |
| `not done` | It was meant to happen and did not |
| `not proven` | It happened, but nothing exercised it — including a check that could not run |
| `done` | It happened, and there was nothing to check (a commit, a push, a log entry) |
| `proven` | It happened and was checked against the running system, with the evidence in the row |
| `n/a` | Does not apply here — say why in one clause |

**`done` and `proven` are different words and never stand in for each other.** Code that was written is `done`. A journey somebody walked is `proven`. Collapsing the two is how a feature ships looking finished and unverified at the same time.

Translate honestly from what the agents reported, and never upgrade a status on the way up: a sign-off whose end state was walked is `proven`; a deferred check is `not proven` however clean the rest of the run was; a verification recorded `blocked` is `not proven` and one recorded `fail` is `failed`; a parked gate is `needs you`.

**Which block a row goes in — one test.** *Does this need a decision or an action from you now?* **Yes → Open**, and the row names the exact command — plus its roadmap id when it has one. **No → Emerged**, and the row names the store holding it.

**Filing is orthogonal to urgency, and this is the trap.** Everything fileable still gets filed, so nothing is lost either way — but an item can be both filed and the most urgent thing in the repo (a dry run that bills real money is on the roadmap *and* is what you should do next). Sorting by "will something raise it again?" sends that row to Emerged, where it reads as handled; sorting by "does it need you?" puts it in Open with its command and its id. **An item never appears in both blocks.** Open is your inbox; Emerged is the receipt.

**Open empty still means the session is disposable** — now because nothing needs you, and everything else names a reader that will raise it. That is the question this report exists to answer, so nothing that needs no action from you may sit in Open and make it look otherwise.

**4. Open** — what needs you:

| Item | Why it is open | Next |
|---|---|---|

**Three columns, always.** Compressing to two is a contract violation, and the column that must never be the one dropped is `Next` — a report that names no command cannot be acted on, which is the whole point of the block. **`Next` is a runnable command**, not a bare roadmap id and not a description: `/fix <id>` is a `Next`; `hosting-emulator-does-not-check-the-artifact-it-serves-is-complete` is not.

One row each for: a parked gate, a gate decided on a **timeout** (labelled as auto-decided, never as their choice), a verification recorded `fail` that **nothing already tracks** (`open-deferrals` excludes a bare fail by design — but if a roadmap item covers it, `/roadmap` raises it and the row belongs in Emerged instead), a task recorded `UAT-only` that nobody has verified, work left in the tree, an unreached task. `Next` is the exact thing to run or click. **Order: the parked gate first, then `failed`, then the rest** — the `Next:` line below is the top row. Nothing open → write `None`.

**5. Emerged** — work that appeared during the run that **nobody asked for**, and that now lives somewhere with a reader. **Both halves are required.** This task's own outputs are not emergent however durably they are stored: a verification it captured and passed, the roadmap item it was addressing flipped to `done`, the log entry it wrote — those are Status rows or nothing. If the run produced no unasked-for work, the honest answer is `None`; a block filled with the task's own artifacts reads as though scope appeared when none did. Every row names its home; there are only three:

| Item | Where it lives | What raises it |
|---|---|---|

- a roadmap `**Id:**` → `/roadmap`
- a `custom-tests.yaml` entry **this run** recorded `blocked` → Step 0 of `/code`, `/fix`, `/pilot` (name the route: walked after a prod deploy, or open on a named trigger)
- the git tree or a named stash → Step 0 entry hygiene and `/tidy`

**No home → the row is Open.** And **needs you now → the row is Open even when it has a home** — filing it does not discharge it, and the id rides in that Open row's `Next` instead. Filing is for **scope** only — work someone would pick up later. Append it to `docs/roadmap.md` in the format `<PREFIX>-dev` step 1.5 defines (`**Id:**`, `**Added:**`, matching the convention the file already uses); the path is `EXEMPT` in PATH_MAP, so no skill load is needed. A parked gate, a timeout decision and a `fail` are **not** scope: they are this run's unfinished business and stay Open. Otherwise this block becomes a way to make Open look empty. Nothing emerged → write `None`.

**Only what this run produced.** The roadmap is not reported here, and neither is a deferral that was already open when the run started — Step 0 listed those, and repeating them at the end is the backlog dump this block exists to prevent. If a row would carry the words "pre-existing" or "not from this run", it does not belong in the report at all: something already raises it, which is exactly why Step 0 showed it to you. **`/whats-up` is the single exception**, and it says so where it inverts this: it has no run of its own, so the standing backlog *is* its subject — reported as counts naming their readers, which is the form this rule was protecting.

**The last line.** After the five blocks, print one line. It is **derived from the Open rows**, never authored separately — so it can never disagree with the table above it. First sort the Open rows into *needs work* (a command would do it), *needs a decision* (only you can answer), and *nothing can be done* (a count, a fact). Then:

| Open rows that need work | The line |
|---|---|
| none | `Next: none — nothing open, safe to start a fresh session.` |
| one | that row's `Next` |
| two or more, **all carrying roadmap ids** | `Next: /pilot --items <id>,<id>` — ranked per `roadmap.md § Rank`, cited not restated |
| two or more, **mixed** | the top row's `Next` — never a `/pilot` line, which takes ids and would drop the unfiled ones silently |

**A parked gate outranks all of it**: `Next: resume here — <what it awaits>`, the only case where this session must survive. A row that needs a *decision* is not work and never becomes the line — say so in the Verdict instead. On the 2nd+ pipeline run of a session, append `— in a fresh session`; long sessions degrade quality and it does not need a paragraph.

### How to write it

- Name the thing, then its state. Cut any sentence that would be true of any run.
- No hedging. "mostly", "should be", "appears to", "successfully" all hide the status the table exists to show.
- A `proven` or `failed` row carries its evidence in the row — the command, the url, the screenshot path. A screenshot is a path, not a description of what it shows.
- **A caveat on a status goes in that row's evidence cell**, including what was walked and by which path when the real entry point could not be reached. Written after the blocks instead, it becomes the trailing summary this shape exists to remove — and it separates the qualification from the status it qualifies, which is how a row reads `proven` while the paragraph underneath explains that the actual entry point was never exercised.
- Do not explain what each agent did. That is the delivery log's job.
- Too long? Fold the rows in a good state into one (`N done · M proven`) and keep every other row as it is. **Open and Emerged are never folded.** If the report does not fit a screen, rows are being written as paragraphs.
- The Verdict states the **state**; the closing line states the **action**. Never let both say "needs you" — Verdict keeps the outcome word and the ship state, and the command lives only in the closing line.

**This run's rows.** Ship state belongs in the Verdict line: "deployed to prod" only after `<PREFIX>-deploy` confirmed CI completion and the health check; "held at UAT per your Ship answer — `--prod` when ready"; or, when a gate is parked, exactly what it is waiting for.

Rows this command produces that the test above places for you:

- **A serve-env started at Step 1.7** — a **Status** row, `done`, stating the **observed end state**: left running with its url, or stopped with the ports confirmed free, depending on what this project's close-out actually does. Either is `done` and neither is forward work — Step 1.7 restarts a stale server and reuses a live one, so nothing is owed here. Report what you see; do not assert one of the two because the template mentions it.
- **Parallel children qa dispatched** — its handoff `Fanned out:` count — is a **Status** row, `done`, with what they covered as the evidence. Nothing is owed; it is reported because it is a real cost the run has no other way of showing. Any priors carried rather than re-walked ride on the same row as qa's `Tests:` line reports them.
- **A value the pipeline resolved** — the regression scope when Step 0.5 carried `auto` — is a **Status** row carrying the reason from qa's `Tests:` line. Use the `Decisions:` provenance to place these: `agent` and `pilot-auto` are Status, **`timeout` is Open**, because that is the only case where the user was asked and did not answer.
- **A `prod-walk:` carried out of Step 2 that Step 5 never ran** (the run held at UAT) is an **Emerged** row: it stays filed as `last: blocked`, and the row names what discharges it — `/code --prod`. It must never vanish just because the deploy step was skipped.
- **A task recorded `UAT-only`** at Step 0.5 captured nothing and persisted nothing, by the user's own instruction. Its acceptance row in Status is `not proven`, and it is an **Open** row: `Next: verify live — <the acceptance statement>`.
- **Scope `<PREFIX>-dev` appended** — the ids on its handoff `Roadmap:` field — is an **Emerged** row, one per id. Scope this command uncovered at the top level and nobody filed is **Open** with its command, unless you file it here per block 4.
```

---

## § /fix — fix.md (Claude Code)

```markdown
---
description: Investigate and fix a bug or performance issue through <PREFIX>-debug → <PREFIX>-dev → <PREFIX>-qa → <PREFIX>-pm
---

# Bug Fix

**Usage:** `/fix <description>` — the Step 0.5 gate states what will be verified and asks whether to ship after sign-off. `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push; `--regression full|smart` pins the test scope that is otherwise resolved from the change itself.

**Examples:**
- `/fix pipeline table takes too long to load`
- `/fix assessment status stuck on running after completion`
- `/fix <description> --prod`

## Gate policy (governs every AskUserQuestion in this command)

If a question times out unanswered, split by risk:
- **Reversible** (confirm, ship choice, UAT-defer): proceed with the recommended default and label every downstream record `auto-selected on timeout — not user-confirmed` (handoffs, delivery log, final report). **Never present a timeout as user consent** — not to a subagent, not in a log, not in the report.
- **Irreversible** (prod deploy; any push that fires a prod CI deploy): **park** — do not proceed and do not decide. End the turn stating exactly what awaits confirmation and how to resume; on the user's next message, resume from the parked step. Park only after actually asking at the moment of the irreversible action — never skip the ask because an earlier, unrelated gate timed out; the user may have returned.

## Step 0 — Flags + entry hygiene

**Flag parse (first):** if `$ARGUMENTS` contains `--prod`, set `ship_mode = prod`; if it contains `--no-push`, set `ship_mode = hold` and `no_push = true`. If it contains `--regression full` or `--regression smart`, pin `regression_mode` to that value. Strip every flag from the description used in every step below. If no ship flag is present, `ship_mode` is decided by the Ship question in the Step 0.5 gate; if no `--regression` flag is present, `regression_mode` is `auto` and the scope is resolved from the change itself (Step 0.5).

**Entry hygiene:** run `git status --porcelain` and `git rev-list --count @{upstream}..HEAD` (report "no upstream" rather than failing when the branch has none). If the count is non-zero, say so in one line with the reason if you can see it — held commits are work that already passed review and is waiting on a decision, and **nothing else raises them**: a close-out's Open row dies with its session, and entry hygiene is the only step that runs before every task. Report, do not gate; if the held set overlaps the paths this task will touch, say that too, because the task is about to build on unshipped work. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it in the close-out step — the pre-handoff gate blocks the qa spawn on any dirty tree, so deferring the stash just moves the failure mid-pipeline. If the WIP overlaps paths this task will touch, do not stash it blind — tell the user and run `/tidy` scoped to the overlapping paths first, then resume here.

**Open deferrals:** run `python3 .claude/graph/graph.py open-deferrals` and, if it returns anything, **split what comes back into three buckets before reporting it**: (1) a deferral whose `reason` names a *structural* fact — a component that only ships to prod, a journey that ends on a schedule, a cost- or quota-bound external call — can never be closed by a local run and is **counted, not listed** ("58 structurally unprovable: the worker declares no non-prod env, image generation is quota-bound"); (2) everything else with a reason is **closable** and gets listed; (3) a row with **no reason at all** is **unclassified** — counted separately and labelled as written before reasons were required. Never guess which of the first two an unclassified row belongs to: the text was never written and is not recoverable, so a guess would either inflate the backlog you act on or hide work in the count you ignore. New deferrals all carry a reason, so this bucket only shrinks. Without the split the list grows without bound as the same two facts re-defer on every task, and a number nobody reads is the same as no report at all. Then list the closable ones for the user in one line — these are verifications that are still unproven and nothing has passed since: either an earlier task formally deferred them, or a run recorded them `blocked` (which is what the vacuous-pass rule mandates when the assertion never got exercised). A blocked row carries its `reason` — the trigger that would close it — so quote that, not just the name. This read is the reason a deferral is an Emerged row at close-out rather than something the user has to hold: the three lanes that can discharge one — `/code`, `/fix`, `/pilot` — all open with it. Report, do not gate — **with one exception: if the same *fixable* blocker is named by 3+ open deferrals, or any single verification has been deferred 3+ times, say so and ask whether to fix the blocker first.** Repeated deferrals of that kind are not a backlog, they are one missing capability (usually a test environment) charging rent on every task that follows; five checks deferred across three deploys is how a feature ships unwalked. **Fixable means someone could build it** — seed data, an auth strategy, a `stack:` block, a missing non-prod env. A structural fact is not a blocker to escalate: a component that only ships to prod, or a journey that ends on a schedule, will produce deferrals forever and asking every third run is noise, not signal. Those are discharged by the post-deploy prod walk and by triggered follow-ups respectively — count them, never nag about them. Skip silently if the script is absent or exits non-zero. (Cheap by design — a few lines of output, not a file read; the Step 0.5 gate stays read-free.) Only the lanes that can turn a `blocked` into a `pass` run this read — `/code`, `/fix`, `/pilot`. `/tweak`, `/wrap`, `/revert` and `/tidy` persist no typed verifications and could not discharge one, so listing them there would be noise the user cannot act on.

**Plan shortcut:** if the session contains a just-approved plan covering this fix **and that plan carries its own Verification / Acceptance section**, plan approval was the confirmation — omit the Confirm question from the Step 0.5 gate. Both halves are required: Confirm is the only place the derived verifications are shown, so omitting it on a plan that never stated an end state would ship a set the user has never seen — and with `--prod` or `--no-push` also pre-answering Ship, the gate would fall to zero questions.

## Step 0.5 — Single gate: confirm the plan of record

**Read-free step — do NOT read `custom-tests.yaml`, `test-commands.md`, or any reference file here.**

First write the **acceptance statement**: one sentence naming the end state in the user's terms — who does what, and where they end up. **A bug report names a symptom; the acceptance statement names the journey that symptom sits in.** "Clicking them does nothing" is a broken step, not a goal — the goal is *"a user picks a look in the gallery and lands on the generate step with a pack built from it"*. Fixing only the reported symptom is how a run ends with the click working and the journey still dead-ending: ask what the broken step is *for*, and state where it ends. Derive it from whichever source applies:
- **A plan exists** (the current session has a just-approved plan with a *Verification* / *Acceptance* section): the plan's outcome is the acceptance statement.
- **No plan** (e.g. `/fix` invoked first thing in a fresh context): infer it from the task (`$ARGUMENTS`, with any flags already stripped) — the default fallback whenever no plan is in context.

Then derive 2–3 **verifications** *from that statement*. Each must be a clause of the acceptance statement — never an independent thought about the diff. A plan's lines describe *how it's proven*; restate each as *what must hold* so it reads as a regression invariant. (A bug's verification becomes its never-regress-again invariant.)

| Part of the acceptance statement | Type |
|---|---|
| The end state the user lands on | **E2E** — mandatory |
| Each boundary the journey crosses (UI → API, API → stored data) | **Integration** |
| Each surface the user acts on | **UX** |

**The end-state verification is not optional, and it is the one that proves the fix.** A set that checks the repaired step but not where the user lands passes while the journey dead-ends — the reported symptom is gone and the feature still does not work. If nothing covers the last step of the statement, the *set* is wrong; fix it before asking. This is the whole point of deriving from an acceptance statement rather than from the bug report: the report names where the journey broke, never where it should end.

**You derive the set — the user does not assemble it.** The gate states what will be verified and the free-text reply amends it; there is no pick-list, because choosing between checks you just derived is work the user should not have to do, and a picker invites dropping the end state one option at a time.

**No behavioral surface is the only exemption.** A task that changes nothing a user or caller can observe (docs, comments, a rename with no observable effect) derives an empty set — then say so **and name why** in the Confirm text, so an empty set is a visible claim rather than a silent omission. Anything that changes behavior has an end state; "no check came to mind" is not the same fact as "there is nothing to check". A reported bug is behavior by definition, so an empty set here is nearly always wrong.

Then ask in **one AskUserQuestion call** (at most two questions) — one gate interaction, so an AFK timeout costs 60 seconds once for the whole run:

1. **Confirm** (omit this question only when the plan shortcut applies):
   - question: the plan of record, on its own lines —
     ```
     Done means: <the acceptance statement>.
     Verifying: <assert> (E2E) · <assert> (Integration) · <assert> (UX)
     Regression: <"resolved after implementation, from the paths actually changed" | "full — pinned by --regression" | "smart — pinned by --regression">
     Investigate and fix?
     ```
     With an empty set, the `Verifying:` line reads `nothing — <why this task has no behavioral surface>`. Leading with the end state is the point: this is the user's chance to correct the *goal*, which is cheap here and expensive after dev has built to the wrong one.
   - header: "Confirm"
   - options:
     - label: "Yes, proceed (Recommended)" — description: "Run <PREFIX>-debug root cause analysis, then fix through the full pipeline and verify exactly the checks above"
     - label: "No, cancel" — description: "Stop here, do not investigate"
2. **Ship** (omit when `--prod` or `--no-push` already decided it):
   - question: "Ship after QA sign-off?"
   - header: "Ship"
   - options:
     - label: "Ship (Recommended)" — description: "After a clean sign-off, deploy/push to prod at close-out without asking again. On projects where push fires prod CI, shipping = prod deploy."
     - label: "Hold at UAT" — description: "End committed but not pushed/deployed; ship later with --prod or by asking"

Branch on the answers:
- Confirm = **Yes** or **timeout** → the stated set is the set. Gate policy: reversible — proceed on the recommended defaults, **except Ship, whose timeout default is always Hold** (shipping needs a real answer; holding is free to reverse), labeled `auto-selected on timeout — not user-confirmed`. Silence is acceptance *only because the set was shown* — which is why the plan shortcut may never omit Confirm on a plan that stated no end state.
- Confirm = **No, cancel** → tell the user the fix was cancelled and stop (discard the other answers).
- Confirm = **Other / custom input** → read the reply as exactly one of the rows below. When it could be read two ways, take the **earliest** matching row: re-asking costs one interaction, building to the wrong end state costs a pipeline.

| The free-text reply… | Do |
|---|---|
| restates the goal or the end state | it is the **new acceptance statement** — re-derive the whole set from it, restate, and re-ask the gate **once** |
| names, replaces, or removes checks | amend the set, then proceed without re-asking. The end-state rule still binds: if the amendment leaves the last step of the statement uncovered, say so and put a check back |
| names test scope ("run full regression", "smoke only") | pin `regression_mode` to it and proceed |
| declines automated verification ("I'll verify live") | the UAT-only path below |

**Honor the user's answer.** A free-text reply that declines automated verification ("I'll verify live", "I'll test by eye") is a decision: record this task as `UAT-only`, capture nothing, and skip Step 2.5 — do not persist synthesized entries against the user's stated intent.

Hold the resulting `{assert, type}` pairs in context — **do not write or commit anything yet**. For a verification the user supplied in free text, infer `type` from the wording (**UX** (frontend only) · **Integration** (backend: endpoint or stored data) · **E2E** (a UI action with a backend effect)).

**Regression scope is not asked here, and not decided here.** At this point <PREFIX>-dev has not run, so there is no changed-path list and any answer would be a guess about a diff that does not exist yet. Carry the value pinned by `--regression`, else the default `regression_mode: auto`:
- `auto` authorizes `<PREFIX>-test` to resolve the scope **once**, from the paths dev actually changed (see `<PREFIX>-test` → *Regression scope*). The resolved value, and its reason, come back on the qa handoff's `Tests:` line.
- A **pinned** value binds in **both directions** — nothing downstream may widen it and nothing may narrow it (see `<PREFIX>-test` Rules — a full unit-suite re-run is not a permissible "superset").

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
    Done means: <the acceptance statement from Step 0.5> — this is the task, not the diff that
    approaches it. The journey's last step must be reachable by a user before you report complete.
    A bug report names a symptom; the statement names the state the user should end in. Removing the
    symptom without reaching that state is not a fix.
    Verifications (these must hold when done): <the verifications captured in Step 0.5, or "none">

While the agent runs, do **not** edit governed source files at the top level — concurrent writers make QA's diff unattributable.

**Salvage protocol (applies to every subagent in this command):** if an agent returns **anything that is not a `## Handoff` block** — it died (watchdog kill, session limit, API error) **or** it ended its turn with an interim/progress status — do not absorb its role at the top level. Inspect `git status` / `git log` to see what landed, then resume with a salvage prompt naming what is already done and which contract steps remain (quality checks, deploy, Reference Sync, commit, handoff). **The two resume mechanisms are not interchangeable — they differ in control flow, not just in cost:**

- **SendMessage — preferred.** It preserves the agent's context, so a fix round returns a delta instead of re-deriving the task. But resuming a completed agent **always runs detached**: the call returns immediately saying it resumed in the background, and *that return is not a status* — it reports nothing about the work. Do not read it as progress, do not act on it, and never forward it as an interim update. **End the turn.** The real result arrives later as a task notification, and only the `## Handoff` inside it counts. Waiting through this on the same turn is impossible; that is the mechanism, not a failure.
- **Re-spawn (`Agent`, `run_in_background: false`).** Blocks in-turn and hands back the handoff directly, but the fresh agent re-reads its way back to the current state. Use it when the agent's context is not worth preserving, or its transcript is unusable.

The trap is that SendMessage's immediate return looks exactly like the interim return this protocol treats as a stall — so a top level that "checks the result" after resuming re-triggers salvage on an agent that is working fine, or reports a parked step as done. Resume, then wait for the notification; never infer state from the resume call itself. A salvaged completion counts as `Status: complete` for the steps below.

A **parked** agent is the failure mode to watch for, because nothing announces it: an agent that backgrounds a long wait (a deploy watch, a poll loop) and returns control cannot be woken by that task — its completion notification is delivered here, to the top level, not to the dormant agent. So an interim return is never "still working"; it is a stalled step. Treat the missing `## Handoff` as the trigger and resume the agent. If the outstanding work is a wait, own the wait here and hand the result to the resumed agent — this is the same reason gates and the verification stack live at the top level: **only the top level has the channel** (to the user, to a held server, to an async completion).

## Step 2.5 — Persist captured verifications

Run unless the task was recorded `UAT-only` or the derived set was empty (no behavioral surface) — and only once <PREFIX>-dev has finished — `Status: complete` or a salvaged completion (captured verifications must never be lost to an agent death). If dev blocked, skip — nothing is written.

For each captured `{assert, type}`, append an entry to `.claude/skills/<PREFIX>-test/references/custom-tests.yaml`:
- `name` — auto-slug from the verification
- `added` — today's date
- `task` — `$ARGUMENTS`, written as a **single-quoted** YAML scalar (double any internal `'`) so colons / braces / double-quotes in the description can't break parsing
- `assert` — the sentence, also **single-quoted** (double any internal `'`). Keep it **symbolic**: reference behavior and configured values ("matches the configured tolerance"), never volatile constants copied from code — those rot within days and QA then wastes a cycle correcting them
- `type` — the inferred/confirmed type
- `paths` — the dev `## Handoff` `Files changed:` list, reduced to **behavioral surface only**: paths whose change could actually break the assertion. Exclude **documentation-only paths** (`docs/**`, `*.md` outside source trees, and any other docs-only tree this project keeps) and **workflow-internal reference/doc paths** under `.claude/**` — neither can change runtime behavior, so neither may drive prior-selection. One exception: executable source that happens to live under `.claude/` (e.g. `.claude/skills/**/scripts/**`) **is** behavioral surface and must be kept. If this reduction would leave `paths` empty, the entry is mis-anchored — name the code the assertion is actually about instead of storing the docs that described it

Commit: `test: capture verifications for <task-slug>` (the tree is clean post-dev — a clean follow-up commit). Keep the new entry `name`s to forward to Step 3.

## Step 2.7 — Ensure verification stack

Run only if verifications with type `UX` or `E2E` were captured. For each affected component (from the dev `Files changed:` paths), resolve its **first non-prod env** in `.claude/skills/<PREFIX>-deploy/references/deploy-config.yaml`:
- Env has `deploy:` (ship-env) → nothing to do; <PREFIX>-dev already deployed it.
- Env has `run:` (serve-env) → start or restart it here at the top level (subagents can't hold a server), applying the env's `stack:` block if declared — env-var overrides that wire the frontend to the local backend, the `seed:` command, the `auth:` strategy (see the deploy-config schema). Then poll the url until HTTP 2xx (up to ~60s). If still unreachable, surface the output and ask the user how to proceed before spawning <PREFIX>-qa.
  **Freshness:** a server started before dev's commits is running stale code — restart it so QA tests the new code; a green check against a stale server is non-evidence.
- No non-prod env → continue; <PREFIX>-test reports those verifications blocked and Step 3 handles it.

Leave any server you started running — note it under Done.

## Step 3 — Review & Test (<PREFIX>-qa)

After <PREFIX>-dev completes, parse its `## Handoff` block — and keep its `Roadmap:` ids: they are the Emerged rows for scope the agent tracked, and nothing else carries them out of the subagent:
- `Status: complete` → spawn <PREFIX>-qa with `mode=initial`.
- `Status: blocked` → tell the user dev blocked with `Notes:` and stop.

Task:
  subagent_type: <PREFIX>-qa
  prompt: |
    Run code review (<PREFIX>-review) and tests (<PREFIX>-test) for the most recent changes. mode=initial
    regression_mode: <auto | smart | full, from Step 0.5 — `auto` unless --regression pinned it>
    Done means: <the acceptance statement from Step 0.5> — walk it end to end and report where it
    actually lands. Green on the individual checks while the journey dead-ends is a `blocked`, not a
    sign-off; the assertions are evidence for the statement, never a substitute for it. The original
    symptom being gone is not the same as the end state being reached — check the latter.
    New verifications this task: <names from Step 2.5, or "none">
    Changed paths: <the dev Handoff `Files changed:` list>
    Sign off when quality gates pass.

After <PREFIX>-qa returns, parse its `## Handoff` block:
- `Status: signed-off` → continue to Step 4.
- `Status: signed-off-with-deferrals` → **first check what is being deferred.** Hop-level checks (a boundary, a surface) defer normally. If a deferral covers the **end state** of the acceptance statement, the journey is unproven, and what happens next depends on *why* — which `deploy-config.yaml` already answers, so read it rather than judging:
  - **A non-prod env for that component exists** and the end state still wasn't walked → the gap is fixable and is being avoided. Do not offer the deferral. Say which journey cannot be walked and what is missing (usually seed data, auth, or a `stack:` block), and ask whether to build that or stop. **This is the only case that blocks.**
  - **No non-prod env is declared** (the component ships only to prod) → nothing was avoided; the project cannot prove this before shipping and never could. Carry the end-state check forward as `prod-walk: <verification name>` into Step 5 and continue. It is **not** discharged here and **not** handed to the user.
  - **The end state is triggered out-of-band** (a schedule, a webhook, an external callback) → it cannot be walked on demand at any point in this run. Defer it, but only with a **named trigger, expected observable, and where to look** (e.g. "next 03:00 run writes a summary row for yesterday; check the jobs collection"). A deferral without those three is not a deferral, it is a shrug — send it back rather than accepting it.

  Otherwise ask via AskUserQuestion: "QA is clean except these verifications no environment can run: `<UAT-deferred list with reasons>`. Defer to UAT and continue, or stop?" On **Defer** — carry `UAT-deferred: <names> (user-confirmed)` into the Step 4 pm prompt and continue. On timeout — reversible gate: continue, but carry `UAT-deferred: <names> (auto-accepted on timeout — not user-confirmed)`. On **Stop** — halt and report. Never re-spawn qa to relabel its handoff — the deferral status IS the sign-off vocabulary.
- `Status: blocked` with code-fix `Notes:` → re-spawn <PREFIX>-dev with the fix request, then on dev complete re-spawn <PREFIX>-qa with `mode=retest` (review already passed, run tests only) — passing **the scope qa resolved on the first pass**, taken from its `Tests:` line, never `auto` again. Re-sending `auto` would let the scope flip mid-task, and the delivery log records one `regression=` value for the task. Repeat until signed-off or user aborts.

## Step 4 — Log & Docs (<PREFIX>-pm)

After <PREFIX>-qa signs off (either signed-off status), capture its `## Handoff` block verbatim and pass it to pm under `**QA-evidence:**`:

Task:
  subagent_type: <PREFIX>-pm
  prompt: |
    Verify QA phases ran. Write delivery log via <PREFIX>-log. Update docs if architectural changes were made.
    Feature commit: <the dev Handoff `Commit:` hash — the delivery-log hash, not any later bookkeeping commit>
    UAT-deferred: <names + how confirmed, from Step 3 — omit line if none>
    Decisions: regression=<the scope qa resolved, smart|full> (<agent|user|timeout> — `agent` when Step 0.5 carried `auto`, `user` only when --regression pinned it) · ship=<prod|hold> (<user|timeout>)<append ` · defer=accept (<user|timeout>)` when the Step 3 deferral gate ran>
    Changed paths: <the dev Handoff `Files changed:` list>

    **QA-evidence:**
    <paste the full ## Handoff block returned by <PREFIX>-qa, verbatim>

## Step 5 — Deploy to prod (only if `ship_mode: prod`)

Run only if `ship_mode = prod` (from the `--prod` flag or the Step 0.5 Ship answer). After <PREFIX>-pm has logged, invoke the `<PREFIX>-deploy` skill **here at the top level** (not via a subagent) with `target=prod`. It runs the fill-in pass, builds the gate context, and gates via `AskUserQuestion` — which works because this is the top level. Running after sign-off and any retest loop means it deploys the final, signed-off code.

**Pre-authorization.** If the user answered **Ship** at the Step 0.5 gate (not a timeout default), pass `preauth: user shipped at Step 0.5` to the skill **only when all of these hold** — verified now, not assumed:
- QA status is `signed-off`, or `signed-off-with-deferrals` where the deferral was **user-confirmed** (not auto-accepted on timeout);
- no gate in this run was auto-decided on timeout;
- the commits being shipped are exactly the reviewed set (nothing landed after QA's sign-off except the capture/log commits).

When any condition fails — or Ship was a timeout default — the skill gates normally (ask; on no answer it returns `gate: unanswered — parked` → park per the Gate policy; never decide a prod deploy on the user's behalf). If no `prod` env is declared or the user declines, report that and finish at UAT.

**Prod walk (run when Step 2 carried a `prod-walk:`, or when any prod-only deferral covers what this deploy just shipped).** After the deploy succeeds, walk the acceptance statement against prod **here at the top level** and report where it lands — the same end-to-end trace qa would have run, against the only environment that can host it. This is the whole point of the prod-only branch: a project that cannot prove a journey before shipping proves it immediately after, using the access this pipeline already has. Handing the user a checklist for a flow you can reach yourself is not a verification, and "I have prod access but asked you to click it" is the failure this step closes. Record the outcome in the scorecard and update the verification's `last:` accordingly — pass discharges it, failure opens a `/fix` with the journey as its acceptance statement. If prod genuinely cannot be reached from here (no credentials, human-only auth), say so explicitly and name what the user must click — a checklist is the fallback, never the default.

**Then drain what this deploy made provable.** A prod-only check is discharged by *a* prod deploy, not only by the task that first deferred it — so on a project that habitually holds at UAT, those checks accumulate forever while every `--prod` run walks one and leaves the rest. Run `python3 .claude/graph/graph.py blast <the paths this deploy shipped>` and walk every still-open prod-only deferral it returns, exactly as above. **The shipped paths are the bound** — do not walk the whole backlog, and never re-walk a check this deploy could not have affected. Report the ones you walked and the count still carried; if the graph is unavailable, walk only this task's carry and say the sweep was skipped.

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

Report per `code.md § Done` — the same five blocks (Verdict · Learned · Status · Open · Emerged) and closing line, the same closed status words, the same writing rules. Nothing about this lane changes the shape.

**This run's rows.** The Status rows for deploy / push / log / docs / ref-sync are the Step 6 scorecard facts, each checked against reality there. The root cause `<PREFIX>-debug` found belongs in the Verdict line — one clause, so the user knows what broke, not how it was traced. Ship state, a serve-env started at Step 2.7, a regression scope the pipeline worked out, any children qa fanned out to, an undischarged `prod-walk:`, and a `UAT-only` task are handled exactly as in `code.md § Done` — including that the first three are Status rows, not Open ones.
```

---

## § /pilot — pilot.md (Claude Code)

```markdown
---
description: Autonomous multi-task run — decompose a goal into tasks, route each through the right lane (full pipeline or tweak), and work unattended until the goal is met. One up-front gate, no mid-run questions, single batched close-out.
---

# Pilot

**Usage:** `/pilot <goal>` — a batch of work (e.g. open roadmap items matching a filter) or a target state to reach (improve an area until measurable criteria pass). Flags: `--max-tasks N` caps the run (default 10); `--items <id>,<id>` runs exactly those roadmap items (how `/roadmap` hands over a set); `--prod` pre-answers Ship; `--no-push` pre-answers Hold and skips the close-out push; `--grant <unit>=<N>` (repeatable) pre-answers Budget for a metered lane; `--regression full|auto` opts the whole mission out of the fixed `smart` scope.

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

**Flag parse (first):** `--max-tasks N` → cap the task list at N (default 10); `--items <id>[,<id>…]` → the task list is these roadmap `**Id:**` values, in this order (see Decompose); `--prod` → `ship_mode = prod`; `--no-push` → `ship_mode = hold` and `no_push = true`; `--grant <unit>=<N>` (repeatable) → seed the resource ledger below; `--regression full|auto` → the mission's test scope, otherwise `smart`. Strip all flags from the goal used below. If neither ship flag is present, `ship_mode` is decided by the Ship question in Step 1.

**Entry hygiene:** run `git status --porcelain` and `git rev-list --count @{upstream}..HEAD` (report "no upstream" rather than failing when the branch has none). If the count is non-zero, say so in one line with the reason if you can see it — held commits are work that already passed review and is waiting on a decision, and **nothing else raises them**: a close-out's Open row dies with its session, and entry hygiene is the only step that runs before every task. Report, do not gate; if the held set overlaps the paths this task will touch, say that too, because the task is about to build on unshipped work. If tracked files are already dirty, stash the pre-existing WIP **now** with a named stash (`git stash push -m "preexisting-wip"`), tell the user, and restore it at close-out. If the WIP overlaps paths this mission will touch, do not stash it blind — tell the user and run `/tidy` scoped to the overlapping paths first, then resume here.

**Open deferrals:** run the same read `.claude/commands/code.md § Step 0` defines — `python3 .claude/graph/graph.py open-deferrals` — and report it as a line, with the same silent skip when the script is absent or exits non-zero. A mission is the main way work starts, so leaving it out would mean nothing raises a deferral for the whole run. Report only: the routine list does **not** go into the Step 1 gate, which already carries a task per line. The one exception is that command's escalation — the same *fixable* blocker named by 3+ open deferrals, or a single verification deferred 3+ times: add it as a line in the Confirm question, so the user can redirect the mission to the blocker through the automatic "Other" rather than spending the run on top of it.

## Step 1 — Mission plan + single gate

**Decompose.** Build the task list from whichever source applies:
- **Pre-selected items** (`--items <id>[,<id>…]`, how `/roadmap` hands over a set): the ids **are** the selection, already ranked — take them in the given order and read each item's body in `docs/roadmap.md` for its description. Skip selection and ranking only; everything below still applies to each item, including the per-task derivation and the split rule. An id that matches no roadmap item is reported at the gate and dropped — never silently guessed at.
- **Roadmap-shaped goal** (the goal names the roadmap or matches its items): read `docs/roadmap.md`, select the open items the goal covers, and rank them per `.claude/commands/roadmap.md § Rank` — one rank rule, stated once, so the order a user saw in `/roadmap` is the order a mission runs.
- **Target-state goal** ("improve X until Y"): derive 2–3 **success criteria** — measurable checks, each with a command or observable that decides pass/fail — then derive the initial tasks that most plausibly move toward them. The loop re-plans between tasks; the criteria, not the initial list, define done.
- **Plain batch** (an explicit list of things to do): one task per item.

Cap at `max_tasks`. For each task derive: a one-line description, an **acceptance statement** (the end state in the user's terms — where the journey lands, not what changes), 1–3 verifications derived *from that statement* (`{assert, type}` — UX / Integration / E2E, same vocabulary and same mandatory end-state rule as `/code` Step 0.5), and a **lane**. The end-state check matters more here than anywhere: this lane runs unattended, so a task that ships a half-journey has no one present to notice it dead-ends.

**Lane registry — discovered, not hardcoded.** Two lanes are always present:
- `pipeline` — features, bug fixes, schema/API/auth changes, anything needing review depth. Default when unsure.
- `tweak` — small inline-verifiable changes (pixel nudges, copy, config values) per the `/tweak` lane rules.

Projects add their own. Scan `.claude/commands/*.md` frontmatter for a `pilot-lane:` key; each one that declares it is a lane this mission may route to:

```yaml
pilot-lane:
  routing: <one line — when a task belongs in this lane>
  close-out: <what the lane owes at task exit, e.g. "log entry" | "artifact + parked verdict" | "none">
  spend: none | metered:<unit>          # <unit> names the finite resource a task in this lane consumes
```

The lane's **name is the command's filename** (`<command>.md` → lane `<command>`) — there is no separate name field to drift. Route a task to a discovered lane only when its `routing` rule matches better than `pipeline`/`tweak`; `pipeline` remains the default when unsure. A lane whose frontmatter is malformed or whose `spend` is unparseable is **skipped with a warning at the gate**, never guessed at. Show each task's lane in the gate list so the user sees the routing before launch.

Discovered lanes are project-owned: this command knows how to *find and dispatch* them, never what they do.

**Split broad tasks (do this before the gate).** A single item that applies **one uniform change across an enumerable set** — phrased with "~N", "each", "all/every X", plural targets, "across the <collection>" — is really N sub-tasks. Bundled into one pipeline task it balloons the dev agent past a healthy context window and hands QA an unreviewable diff (the observed failure: one "invert ~9 modules" item ran 49 turns / 222k context / 41 min and had to spawn its own sub-agents to cope). For each such task, enumerate the concrete target set, then:
- **Split into bounded chunks** — group the set so each chunk is one coherent review unit (rule of thumb: ≤~5 files of the same uniform change per chunk), one `pipeline` task per chunk, sharing the parent's verifications. This is the **default** — a bounded pipeline unit keeps context healthy and the per-task diff reviewable.
- **Cap tension:** if splitting would exceed `max_tasks`, don't silently drop chunks — keep the item **whole** but tag it `[large]` in the gate list with the target count, so the user sees the ballooning risk and can raise `--max-tasks` or pre-split via "Other". Never split a task whose changes are genuinely interdependent (a single edit touching N files together) — that's one review unit, not a set; tag it `[large]` instead.

**Gate.** Ask everything in **one AskUserQuestion call** — the only planned interaction of the run:

1. **Confirm**:
   - question: "Fly this mission? <goal> — <N> tasks: <numbered task list with lanes and verifications; split chunks shown as sub-items; any `[large]` tag with its target count; success criteria if any> · Regression: <the mission scope> — <N> tasks x <scope>"
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

3. **Budget** (include only when the task list routes to a lane whose `spend` is `metered:<unit>` **and** no `--grant` already covered that unit):
   - question: "Grant a budget for <unit>? <M> task(s) route to metered lanes."
   - header: "Budget"
   - options: two or three concrete grants sized to the task count (e.g. "20", "50"), plus "None — skip those tasks". The automatic "Other" accepts an exact number.

**Resource ledger.** Each granted unit starts at its grant and is decremented by the spend a metered lane reports at task exit. Before dispatching any metered task, check the ledger: **at 0 or below, the lane is closed** — remaining tasks in it are marked `skipped — budget exhausted` and the loop continues with the others. **No grant for a unit means every lane metered in that unit is off for the whole mission** — those tasks are dropped at the gate, not silently attempted.

Be precise about what this enforces: the ledger governs **dispatch**, not consumption. `/pilot` decides whether to start another metered task; it cannot cap spend *inside* a task that is already running — the lane owns that, and a lane that under-reports its spend corrupts the ledger. State the granted units and the running balance in the progress line and the close-out, so an over-spend is visible even though it cannot be prevented here.

**State the regression scope in that question, not just the tasks.** It is the one setting that moves mission cost by an order of magnitude: `full` re-covers every prior verification per task *and* on every fix cycle, so `--regression full` on a multi-task mission is a different order of spend from the pinned `smart` default. The user is present exactly once, here — pricing the run while they can still change it is the same reason **Budget** is asked up front. Report it; never gate on it.

Timeout → same risk split as the `/code` Gate policy: launch on the recommended defaults labeled `auto-selected on timeout — not user-confirmed`, **except Ship, whose timeout default is always Hold, and Budget, whose timeout default is always None** (an unattended run must not spend a resource nobody granted). Regression scope is fixed at `smart` for every task unless `--regression` said otherwise — a full regression per task would multiply cost across the mission, and `auto` would escalate on evidence nobody is present to read; each task's QA already runs prior verifications for the files it touched. This is a deliberate asymmetry with `/code`/`/fix`, whose default is `auto`: there, a person sees the resolved scope and its reason.

## Step 2 — The loop

Work the task list in order until: tasks exhausted, all success criteria pass, or `max_tasks` tasks completed. No user gates inside the loop.

**(a) Pipeline lane** — run the `/code` machinery without its interactive steps (`.claude/commands/code.md` holds the exact mechanics; reuse them, replacing every mid-run AskUserQuestion with the autonomous branch below):
1. Spawn `<PREFIX>-dev` with the task + its verifications (`/code` Step 1 prompt shape). The salvage protocol and the no-top-level-edits rule apply verbatim.
2. On `Status: complete`, persist the task's verifications exactly as `/code` Step 1.5 (single-quoted scalars, `paths` reduced to behavioral surface, `test:` commit). On `Status: blocked`, mark the task **failed** with dev's `Notes:` and go to (c).
3. Ensure the verification stack as `/code` Step 1.7 — except on an unreachable env, don't ask: leave the affected verifications to report blocked and continue (they surface as deferrals below).
4. Spawn `<PREFIX>-qa` `mode=initial`, `regression_mode:` the mission scope (`smart` unless `--regression` set it), with the new verification names + changed paths. Branch on its handoff:
   - `signed-off` → continue to 5.
   - `signed-off-with-deferrals` → **auto-accept the deferral, but first route each deferred verification by declared project fact** — the same three branches as `/code` Step 2, read from `deploy-config.yaml`, not judged. Auto-accept means no mid-run *gate*; it does not mean every unrun check is equivalent:
     - **A non-prod env exists and the end state still wasn't walked** → this is not a deferral, it is an unproven feature. Treat it exactly like `blocked`: re-spawn dev, spend a fix cycle, and if it still can't be walked mark the task **failed**. Never auto-accept this branch — an unattended run is the worst place to let a feature ship unwalked, because nobody is present to notice.
     - **No non-prod env is declared** (the component ships only to prod) → carry it forward as `prod-walk: <verification name>` into Step 3(a) and walk it **after** the prod deploy. It is not discharged here.
     - **The end state is triggered out-of-band** (schedule, webhook, external callback) → defer with a named trigger, expected observable, and where to look. Without those three it is not a deferral; send it back to qa's `Notes:` rather than accepting a shrug.
     Carry `UAT-deferred: <names> (auto-accepted — pilot run, not user-confirmed)` into the pm prompt and the mission report for the branches that were genuinely deferred, then continue to 5.
   - `blocked` with code-fix `Notes:` → re-spawn `<PREFIX>-dev` with the fix, then `<PREFIX>-qa` `mode=retest`. At most **2 fix cycles per task**; still blocked → mark the task **failed** with qa's notes. If the failure leaves the tree broken (smoke fails), `git revert` the task's commits before moving on. If later tasks depend on this one, stop the loop and go to Step 3.
5. Spawn `<PREFIX>-pm` with the feature commit, any UAT-deferred line, the changed paths, and the verbatim QA-evidence block (`/code` Step 3 prompt shape). Its `Decisions:` line carries the mission gate's answers plus anything decided inside the loop — every autonomous branch is labelled `(pilot-auto)`, never `(user)`; an auto-accepted deferral is `defer=accept (pilot-auto)`. The mission gate's own Ship answer keeps its true origin (`user` or `timeout`).

**(b) Tweak lane** — top-level inline work under the `/tweak` lane rules: load the owning domain skill first, verify every change inline with shown evidence, commit in small named steps. Task exit: use the `<PREFIX>-review` skill on the task's diff (fix non-source nits directly; a source finding needing review depth → reclassify the task to the pipeline lane and run (a)), then one `<PREFIX>-log` entry for the task. **Scope guard:** if the work grows into schema/API/auth/migrations, reclassify to the pipeline lane before continuing.

**(b2) Discovered lane** — invoke the lane's command with the task, then hold it to its declared contract. It owes whatever its `close-out` names (a log entry, an artifact, a parked verdict, or nothing) and, if its `spend` is metered, a spend figure to decrement the ledger — a metered lane that reports no spend is treated as having exhausted its remaining balance, so an unreported burn closes the lane instead of running free. The lane's own steps are project-owned and not restated here; the salvage protocol applies to it exactly as to any subagent. If the lane's work turns out to need review depth (it changed source), reclassify to the pipeline lane and run (a).

**Parked verdicts.** A lane may produce measurements and artifacts autonomously, but any **keep / ship / adopt decision it marks human-gated is never decided in-run** — not by the lane, not by this command, not by a default. Park it: carry it into the mission report as an explicit parked decision with the evidence needed to answer it, and record it in the task's log entry as `**Decisions:** <name>=parked (human-gated)`. This is the autonomy contract's irreversible-gate rule applied to lane output — an unanswered gate is never recorded as decided, exactly as a timeout is never recorded as `user`. A parked verdict does not fail the task and does not stop the loop.

**(c) Progress + re-plan.** Keep each task's `<PREFIX>-dev` handoff `Roadmap:` ids — they are the mission report's Emerged rows. Then emit one status line — `task k/N · <title> · <status> · <commit> · <evidence pointer>` — a report, not a question. Then re-plan: drop later tasks the outcome obsoleted, insert a revealed prerequisite (within `max_tasks`), and if success criteria exist, evaluate them with evidence — stop the loop when all pass. Record every plan amendment for the mission report. For roadmap-driven runs, verify pm flipped the item's status.

**Context health:** keep the top level thin — never read source files or heavy references at the top level; work from handoff blocks. If context is clearly degrading (earlier tasks summarized away, repeated re-derivation), finish the current task, then go to Step 3 and list the remaining tasks as resumable — a degraded pilot ships worse code than a fresh session.

## Step 3 — Close out (once per mission)

**(a) Deploy to prod** — only if `ship_mode = prod`. Invoke the `<PREFIX>-deploy` skill **here at the top level** with `target=prod`. Pass `preauth: user shipped at the mission gate` **only when all of these hold** — verified now, not assumed: every completed task is `signed-off` (no deferrals, no failed tasks), Ship was user-answered (not a timeout default), and the commits being shipped are exactly the reviewed set (nothing after the sign-offs except capture/log commits). Otherwise the skill gates normally — the user is often back by close-out; on no answer it returns `gate: unanswered — parked` → park per the `/code` Gate policy. If no `prod` env is declared or the user declines, report that and finish at UAT.

**(a2) Prod walk** — run when Step 2 carried any `prod-walk:` items **and** (a) actually deployed. This is the only moment in the mission when a prod-only journey can be proven, so it is not optional: for each carried verification, walk its task's acceptance statement against the deployed prod system at the top level and update the entry's `last:` accordingly — a `pass` discharges it; a failure records `status: fail` with the reason and becomes a named follow-up in the report, never a silent close and never a mid-close-out fix round. Commit the outcomes with `test: record verification outcomes`. Then drain what the deploy made provable, exactly as `/code` Step 5 does: `blast` the shipped paths, walk every still-open prod-only deferral it returns, and report the count still carried. If (a) did not deploy — `ship_mode: hold`, no prod env, a declined or parked gate — the items stay deferred: say so explicitly, naming what would discharge them, rather than letting them read as accepted. Deploying to prod and then not walking the checks only prod can answer wastes the single opportunity the mission had to prove them.

**(b) Push.** Skip if `no_push` or no remote is configured. Resolve via the `<PREFIX>-deploy` skill § Push policy: if pushing fires a prod CI deploy, pushing IS shipping — push only if (a) ran and its gate (or pre-authorization) approved; otherwise ask now (irreversible gate — park on silence). If push does not trigger prod, push now.

**(c) Scorecard.** Verify each fact against reality — never echo handoff claims:

| Fact | Evidence |
|---|---|
| Tasks | per task: feature commit in `git log`, QA status, log-entry title grepped in `docs/project-log.md` |
| Pushed | `git rev-list --count @{upstream}..HEAD` → 0, or "not pushed — <reason>" |
| Deployed | curl the env url/health (2xx), or "no deployable env" / "held" |
| Roadmap | roadmap-driven runs: item statuses flipped in `docs/roadmap.md` |
| Prod walk | every `prod-walk:` item carried from Step 2 now has a `last:` written at the deployed commit — or the reason none ran. A carried item still showing the pre-deploy `blocked` is the failure this row exists to catch |
| Ref sync | `Reference Sync:` fields from the handoffs |
| Spend | per granted unit: `<spent>/<grant>` from the ledger, plus any lane closed on exhaustion |

**(d) Restore stashed WIP.** If pre-existing WIP was stashed at Step 0, `git stash pop` it now; report any conflict instead of resolving it silently.

## Done — mission report

Report per `code.md § Done` — the same five blocks (Verdict · Learned · Status · Open · Emerged) and closing line, the same closed status words, the same writing rules. A mission covers more work, so it needs **more rows, not more prose**.

**This mission's rows.**

- **Verdict** — one line: goal met, partly met, or stopped, plus the ship state. On a mission with success criteria, the criteria decide that word and their evidence goes in Status.
- **Status** — one row per task first (`task · status · evidence`, where evidence is the feature commit and the log-entry title), then the mission-level rows: prod deploy, push, roadmap statuses flipped, prod walk, reference sync, and one row per granted unit as `<spent>/<grant>`. A task whose end state was walked is `proven`; a task that shipped with a check nobody could run is `not proven`, never `done`.
- **Open** — every parked verdict, one row each, carrying the evidence needed to answer it and where that evidence lives; these are the reason the user is reading this at all, so they are never folded into the task rows and never shown as decided. Then: each failed or unreached task with enough state to resume, each lane that stopped on an exhausted budget, and each gate this run decided on a `timeout`. For an `--items` mission the resume row's `Next` is `/pilot --items <id>,<id>` — the ids are permanent, so that line is exact and copy-pasteable. A **goal-shaped or plain-batch** mission has no such handle, so file the remaining goal as a roadmap item per `code.md § Done` block 4 and make its id the resume row's `Next`; a goal restated only in this report dies with the session.
- **Emerged** — each deferral **with its route** (walked at prod in (a2), or still open on a named out-of-band trigger — "deferred" must never cover both facts), the roadmap ids each task's `<PREFIX>-dev` reported on its `Roadmap:` field, scope the mission filed itself, and follow-ups a failed task created. Every row names its home, per `code.md § Done`.
- Serve-envs the mission left running are **Status** rows with their urls, not Open ones.
- The closing line carries "in a fresh session" — a completed pilot has consumed most of this one.
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

## § /whats-up — whats-up.md (Claude Code)

```markdown
---
description: Where the project stands and what to do next — reads every store that outlives a session, diagnoses whether the project can take on new work, and ranks what to do about it. Read-only.
---

# What's up

**Usage:** `/whats-up` — the whole picture. `/whats-up <filter>` narrows to matching ids, titles, verification names or paths.

**Examples:**
- `/whats-up`
- `/whats-up <a roadmap id, a word from an item title, or a path prefix>`

**For someone who has been away and wants to be productive in five minutes.** A close-out's `Open` block dies with its session. Six stores outlive it, and each has exactly one reader that runs only if you happen to start its lane — so work that needs you can sit unseen for weeks while every individual store is behaving correctly. This is the composed reader, and it answers one question: **what should I do right now?**

**This command reads; it never writes.** No commit, no stash, no edit, no reprojection — not even to repair something obviously broken. Work at risk of being lost becomes the top `Open` row naming the command that saves it, and nothing more. A status command that mutates is a status command you stop trusting.

Two rules govern the output:

- **Recommend, don't inventory.** A count nobody acts on is noise. Every number must change what the reader does, or it folds into a total.
- **Housekeeping is never the headline.** Branches, worktrees and commit mechanics are one `Status` row.

## Step 1 — Read the stores

Read-only, in parallel. **A store that is absent or errors gets a `not done` Status row, never a silent skip** — an unread store is the one failure this report cannot recover from, because the reader has no way to know what it did not see.

| Store | Read | If it fails |
|---|---|---|
| What moved | `git log --oneline --since=<date of the newest `docs/project-log.md` entry>` | no entries yet → last 20 commits |
| Held commits | `git rev-list --count @{upstream}..HEAD` | no upstream → say so, do not fail |
| Roadmap | `python3 .claude/graph/graph.py roadmap-open` | read `docs/roadmap.md`. Either way, count `**Status:** in-progress` separately from open |
| Unproven work | `python3 .claude/graph/graph.py open-deferrals --with-fail` | read `custom-tests.yaml` for every `last.status` of `blocked` or `fail` |
| Gates | `grep -n '=parked' docs/project-log.md`, then each hit's full `**Decisions:**` line and its entry date | none — the log is the only record one exists |
| Repo | the `/tidy` **Step 1** sweep — run it, do not restate it here | none |

`--with-fail` is what makes this store complete: a recorded `fail` is deliberately excluded from every other caller, because the close-out puts it in `Open` and no lane's Step 0 re-raises it. That is exactly the row a fresh session loses, so this is the one caller that asks for it.

**Filter.** When `$ARGUMENTS` is non-empty, keep only rows whose id, title, verification name or path matches it case-insensitively. If nothing matches, say so and report the unfiltered set — a typo'd filter must never read as "nothing open".

## Step 2 — Reconcile before reporting

Every store records what was true when it was written. Three of them go stale in ways that **invert** the answer, so check each before it reaches the report:

- **A `parked` gate is a claim, not a state.** Nothing edits a past delivery-log entry — that file is append-only and is the delivery graph's input — so a gate answered weeks ago still reads `parked` forever. Before reporting one, look for its answer: a later entry deciding the same gate, a deploy or push that could only have happened if it was answered, or the change itself sitting in the tree. Found → it is not open, and that correction is a `Learned` bullet. Not found → it is open, and its age is its entry's date.
- **A roadmap item may already be delivered.** Cross-check each open item's `**Id:**` against `**Addresses:**` lines in the log. An item a delivered entry cites is closable, not open.
- **A `blocked` may already be answerable.** Its `reason` names the trigger that would close it; if that trigger has since happened — the env now exists, the deploy landed — say so. A check that cannot run and a check nobody re-ran are different problems with different next steps.

State the evidence whenever a reconcile changes a store's answer. **A reconcile never edits the store**; it changes only what this report says about it.

## Step 3 — Diagnose

Two questions, in order, answered from Step 1's numbers as reconciled by Step 2. The answer is the `Verdict` line.

1. **Is anything blocked on you?** A gate that survived Step 2, an approval, a decision only a person makes.
2. **Is more work in flight than is finishing?** In-progress roadmap items plus held commits, against the delivery-log entries of the last two weeks.

| Answers | Diagnosis | What the report recommends |
|---|---|---|
| Something waits on you | **gate-blocked** | Clear the gate first. Say what it unblocks |
| Nothing waits on you, but in-flight is growing | **fragmented** | Finish before starting. Name the in-progress item closest to done |
| Neither | **clear** | Start the top-ranked open item |

**Gate-blocked wins when both are true** — a gate is cleared in minutes and a roadmap item in days. State the diagnosis in one line with the two numbers that produced it, and nothing else.

**Held commits are never an action on their own.** They are a symptom: either a gate holds them or nobody decided. Never recommend "push" — recommend clearing whatever holds them, and note that the push follows.

## Done

Report per `code.md § Done` — the same five blocks (Verdict · Learned · Status · Open · Emerged) and closing line, the same closed status words, the same writing rules. **This command runs no work, so the report is the whole of its output**: no separate plan, no numbered action list, no summary after the blocks. The ranked `Open` table *is* the plan, and a second list of the same rows in prose is the bloat this shape exists to remove.

**This run's rows.**

- **Verdict** — Step 3's diagnosis and the two numbers behind it.
- **Learned** — what Step 2's reconcile changed, at most 3 bullets: a gate that reads `parked` and is not, a roadmap item already delivered, a `blocked` whose trigger has since happened. Nothing to correct → `None`. This is the block that makes the command worth running rather than reading the stores yourself.
- **Status** — one row per store, `done` with the number it returned or `not done` with why it could not be read. Held commits are a Status row carrying the count **and what holds them**. The repo sweep is one row: `clean`, or the counts with `/tidy` as its evidence. Fold every store in a good state into a single row.
- **Open** — the ranked plan, and the only block that proposes work. **Order it so a row that unblocks a later one comes first**, then per `code.md § Done`: the parked gate, then `failed`, then the rest. `Why it is open` carries the one line of why; `Next` is the command that does it. A row needing a decision only you can make states the options **and which one this run would pick** — a gate reported without a recommendation is how gates sit for weeks.
- **Emerged** — the backlog that already has a reader, **counted per store, never listed**: open roadmap items → `/roadmap`, structurally unprovable deferrals → the prod walk, a named stash → `/tidy`. These are the rows that do not need you now. Listing them is the inventory this command exists to replace. This lane produces no scope of its own, so it never files anything here. **This is the one sanctioned inversion of `code.md § Done`'s *only what this run produced* rule**: there is no run, the standing backlog is the subject, and the counted form is what keeps it from becoming the dump that rule prevents.

**The Open/Emerged split is the whole command.** Coming from a store is not what makes a row `Emerged` — every row here comes from a store. What places it is `code.md § Done`'s test: needs a decision or an action from you now → `Open` with its command; does not → `Emerged` as a count naming its reader.
```

---

## § /roadmap — roadmap.md (Claude Code)

```markdown
---
description: Rank the open roadmap items and either run the top ones as a <PREFIX> mission or start one through the full pipeline
---

# Roadmap

**Usage:** `/roadmap` or `/roadmap <filter>` — `<filter>` narrows the open set before ranking. Flags are passed straight through to `/pilot` (`--max-tasks N`, `--prod`, `--no-push`).

**Examples:**
- `/roadmap`
- `/roadmap high priority`
- `/roadmap integrations --max-tasks 4`

This command **selects**; it never implements. Work happens in `/code`, `/fix`, or `/pilot` — so nothing here models a loop, a budget, or a retry: those belong to `/pilot` and duplicating them would put two answers in the repo for one question.

## Step 1 — Read the open set

Run `python3 .claude/graph/graph.py roadmap-open` — it returns the open and in-progress items with priority, status, and which prior deliveries touched the same paths. **Fall back** to reading `docs/roadmap.md` directly if the script is absent or exits non-zero; the graph is an accelerator here, never a gate. If there is no roadmap at all, say "No roadmap found — create `docs/roadmap.md` first." and stop.

**Filter.** When `$ARGUMENTS` (flags stripped) is non-empty, keep only items whose title, category, priority, or `**Id:**` matches it case-insensitively. If nothing matches, say so and rank the unfiltered set rather than reporting an empty roadmap — a typo'd filter must not read as "no open work".

## Step 2 — Rank

Order the open set by, in this order:
1. **Priority** — high → medium → low
2. **Dependency** — an item another selected item depends on comes first. This outranks category because it is a correctness constraint, not a preference: running a dependent first wastes the run.
3. **Category** — integration > improvement > tech-debt > other

This is the project's single rank rule: `/pilot` cites this section rather than restating it, so a mission runs items in the order the user was shown them.

## Step 3 — Present and route

Take the top `max_tasks` items (default 10) and ask once, via AskUserQuestion:

- question: "Top of the roadmap: `<numbered list — title · category · priority>`. How should these run?"
- header: "Roadmap"
- options:
  - label: "Run the top <N> as a mission (Recommended when 2+ qualify)" — description: "Hand the set to /pilot: one gate up front, then unattended through the lanes"
  - label: "Just the first one" — description: "Start `<title>` through the full pipeline now, with its own gate"
  - label: "None of these" — description: "Show more items or cancel"

Recommend the mission when 2+ items qualify, and the single item when only one does. Route the answer:

- **Mission** → invoke `/pilot --items <id>,<id>,…` with the ranked `**Id:**` values and any flags the user passed. **Do not pre-answer `/pilot`'s gate** — it asks a different question (this plan, with the lanes and verifications it derives) than the one just answered here (which items).
- **Just the first one** → classify it as a new feature (→ `/code`) or a bug/regression (→ `/fix`) — this classification is the one thing this command knows that `/pilot` does not — then say "Starting: `<item title>`" and invoke that command. A lone item is better served by `/code`'s own gate than by a mission whose autonomy contract suppresses the questions a present user could answer.
- **None of these** → ask whether to show more items or cancel.
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
1.5. **Walk the end state, once** — name the journey this burst was for and trace it end to end against the running stack, with shown evidence. Each tweak was verified inline where it landed; none of them proves the journey still arrives, and a burst of individually-correct nudges is exactly how a path breaks between its steps. If it does not arrive, that is a `/fix`, not a close-out note. (No `custom-tests.yaml` entry is captured here — this lane persists nothing; the walk is evidence in the log entry.)
2. **Log** — one `<PREFIX>-log` entry covering the whole burst (name the commits it spans).
3. **Docs + references** — use `<PREFIX>-docs` to check staleness; use `<PREFIX>-skill` for reference sync scoped to the affected skills.
4. **Push + scorecard** — same close-out as `/code` Step 5: push policy via the `<PREFIX>-deploy` skill § Push policy (a push that fires prod CI is an irreversible gate — ask, park on timeout), then the verified scorecard (committed / pushed / logged / docs / ref-sync, each evidence-checked).
5. **Report** — per `code.md § Done`: the same five blocks, the closing line, the same closed status words. The burst is one Status row per tweak plus the close-out rows; the end-state walk from step 1.5 is the row that carries `proven` or `not proven` for the journey as a whole. This lane runs no `<PREFIX>-dev`, so scope the burst uncovered has no writer but this one — file it per `code.md § Done` block 4 and cite the id, or leave it Open with the command that picks it up.
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

Push + verified scorecard, same as `/code` Step 5. If the original change was deployed, redeploy the reverted state to the same envs via `<PREFIX>-deploy` (prod requires its gate — park on timeout). Then report per `code.md § Done` — the same five blocks, the closing line and the same status words, with a Status row for the re-verification: a reverted state nobody re-checked is `not proven`. What the revert re-opened belongs in Emerged, and Step 3's flip back to `open` is what earns it that block — the row cites the roadmap id.
```

---

## § /tidy — tidy.md (Claude Code)

```markdown
---
description: Resolve leftover WIP — sweep the dirty working tree, stashes, worktrees and stale branches, investigate history to establish what each item actually is, then route every item to commit / deliver / discard / ignore.
---

# Tidy

**Usage:** `/tidy` — sweeps the whole repo. `/tidy <paths or area>` limits the sweep.

**Examples:**
- `/tidy`
- `/tidy <path prefix>`

## Gate policy

`commit`, `deliver`, `ignore`, `keep` are reversible — on timeout proceed with the proposal and label it `auto-selected on timeout — not user-confirmed`. `discard` destroys uncommitted work and is **irreversible** — park on timeout, never discard on silence.

## Step 1 — Sweep

One read-only pass: `git status --porcelain`, `git rev-list --count @{upstream}..HEAD` (report "no upstream" rather than failing when the branch has none), `git stash list`, `git worktree list`, and per local branch its merged-into-default state, unique-commit count (`git rev-list --count <default>..<branch>`), and last-commit date. Add recent CI status if `gh` is available. Scope to `$ARGUMENTS` when given.

If the tree is clean with no stashes, extra worktrees, or stale branches, report that and stop — nothing to tidy.

## Step 2 — Establish intent (history investigation)

Never call an item accidental, orphaned, or stale from its appearance alone — **a `discard` or `ignore` disposition requires a history probe backing it.** Probe only what the sweep leaves ambiguous:

| Ambiguity | Probe |
|---|---|
| Deleted or removed content | `git log -S"<distinctive token>" -- <path>` plus a repo-wide grep for surviving references — content whose replacement already landed is **superseded on purpose**, not an accident |
| Untracked file | `git log --diff-filter=D -- <path>` (was it deleted before?) and whether an existing `.gitignore` rule was meant to cover it |
| Modified file | `git log -1 --format='%h %s' -- <path>` — an unfinished follow-up to that commit, or unrelated drift? |
| Stash | `git stash show -p` against the current tree — already landed, or still unique? |
| Branch | merged with 0 unique commits → leftover pointer; unmerged commits → real WIP, treat it as an item |

State the evidence behind each conclusion. When a probe contradicts your first read, say so plainly and go with the probe.

## Step 3 — Propose dispositions

Present one table — item · what it is · evidence · disposition — using this fixed vocabulary:

- **commit** — finished work → group into named commits by concern
- **deliver** — unfinished real work → route to `/code`, `/fix`, or `/tweak`; do not commit it here
- **discard** — scratch, superseded, or generated output
- **ignore** — local-only or generated → a `.gitignore` rule instead
- **keep** — deliberately uncommitted; say why and leave it alone

Then one AskUserQuestion: "Apply this plan?" — options: `Apply as proposed` · `Apply, but keep everything marked discard` · `Stash it all instead` (one named stash, decide later) · `Cancel`.

## Step 4 — Apply

In this order, so nothing is destroyed before it is recoverable:

1. **commit** — one commit per concern. Load the owning domain skill before any edit (skill-guard enforces this).
2. **ignore** — add the `.gitignore` rules, `git rm --cached` anything already tracked, commit that.
3. **discard** — `git stash push -u -m "tidy-discard-<YYYY-MM-DD>" -- <paths>`, never `checkout --` or `rm`. Same clean tree, but recoverable; tell the user the stash name and leave dropping it to them.
4. **branches** — `git branch -d` only, never `-D`: `-d` refuses anything unmerged, so it is self-protecting. Report the printed SHAs as reflog-recoverable.

## Step 5 — Close out

- Anything committed → one `<PREFIX>-log` entry covering the tidy, then push per `<PREFIX>-deploy` § Push policy (a push that fires prod CI is an irreversible gate — ask, park on timeout).
- Anything `deliver` → name each one and the command it goes to; hand them over rather than starting them silently.
- Nothing committed → no log entry, no push.

## Done

Report per `code.md § Done` — the same five blocks (Verdict · Learned · Status · Open · Emerged) and closing line, the same closed status words, the same writing rules.

**This run's rows.** Re-run the Step 1 sweep and make it the Status block — working tree, unpushed commits, stashes, worktrees, branches, CI — each row an observed fact, never a claim about what was applied. Every item you touched gets a row carrying its disposition. `deliver` and `keep` items are still dirty **by design**: they are Open rows naming the command they go to, so "clean" is never overstated. A `tidy-discard-*` stash is an **Emerged** row — it is named, and this command's own Step 1 sweep is what surfaces it again. Work you found that belongs to someone else's backlog is an Emerged row too, filed per `code.md § Done` block 4 and cited by id — this lane has no `<PREFIX>-dev` to file it for you.
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

Report per `code.md § Done` — the same five blocks (Verdict · Learned · Status · Open · Emerged) and closing line, the same closed status words, the same writing rules. This is the shortest lane, so most runs are a one-line Verdict, a five-row Status, two `None`s, and a closing line saying it is safe to start fresh.

**This run's rows.** Status: the change being wrapped, the delivery-log entry, docs, reference sync, and the push — the last three from the Step 4 checks, each verified against reality. The change itself is `done`, not `proven`, unless something actually exercised it — ad-hoc work usually has nothing that did, and saying so is the point of wrapping it. Open: a source finding from Step 0 with `Next: /fix <it>`, anything left unpushed and why, docs left stale. This lane runs no `<PREFIX>-dev`, so **scope it uncovered has no writer but this one** — file it as a roadmap item per `code.md § Done` block 4 and make it an Emerged row citing the id, or leave it Open with the command that would pick it up. Naming it in prose alone is how ad-hoc scope disappears. Do not describe what `<PREFIX>-log`, `<PREFIX>-docs` or `<PREFIX>-skill` did — the log entry is that record.
```
