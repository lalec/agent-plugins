# dev-workflow

A multi-agent delivery workflow for Claude Code. It runs your plan through a team of agents instead of you driving each step manually: one builds, another reviews and tests, a third ships and logs it — each gating the next, so nothing reaches prod unreviewed or undocumented. You say what done looks like; it works out what would prove that and holds the work to it — one task at a time, or a whole batch run unattended. The agents use lifecycle skills that handle each step of the delivery process and domain skills that learn your stack on install and improve as the code changes, with hooks that keep the process from being skipped and commands that let you guide it where it matters.

> Agent and skill names are prefixed with a name you choose during setup (e.g. `myapp`). Examples below use `myapp`.
>
> **Claude Code only.**

---

## What it installs

| Component | What it does |
|---|---|
| `myapp-dev` | **The builder.** Loads the right domain skills, writes the code, runs each skill's quality checks, deploys non-prod, syncs reference docs — then hands off a structured report, so QA always tests a live stack. |
| `myapp-qa` | **The gatekeeper.** Reviews the code and runs the test tiers before signing off, then walks the end state itself — the check that proves the feature runs on every pass, including retests, and reports *blocked* with a reason rather than being skipped for time. A UI change that stands up a second way to do something your app already does comes back as a finding rather than a sign-off. Routes any required fix back to `myapp-dev` instead of patching it itself. |
| `myapp-pm` | **The closer.** Confirms QA actually ran, ships prod when asked, writes the delivery log, refreshes docs, and advances the roadmap — the audit trail writes itself. |
| 8 lifecycle skills | `log`, `review`, `debug`, `deploy`, `test`, `skill`, `docs`, `graph` — one per delivery concern, shared by every agent. |
| Delivery graph | `myapp-graph` turns the records you already keep — the delivery log, captured verifications, path ownership, deploy config, git — into a typed edge index the agents query instead of re-reading files. Answers "what verifies this file", "what shipped here", "which deferrals are still open", "which roadmap items relate to these paths". The index is derived and disposable — rebuilt from scratch in under a second, gitignored, and every caller falls back to its old behaviour if it's missing; the script itself is committed, so a clean-up can't quietly remove the thing all those fallbacks are hiding the absence of. Rebuilding also warns about roadmap items it couldn't index, which is how a malformed entry stops being invisible. |
| Domain skills | One per source directory, generated from your actual structure. Each owns its paths, carries reference docs, and defines the lint/type/test checks `myapp-dev` runs before deploy — and improves itself as the code evolves. |
| 9 hooks | Make the workflow self-enforcing: skills must load before edits, bad installs are blocked, handoffs are gated, ref-sync drift is flagged, and nothing pushes without a delivery-log close-out. |
| `/code`, `/fix` | Drive the full pipeline (dev → qa → pm) from one line — one gate that *states* what done means and what will prove it, auto-retest after fixes, then close out with a push and a report you can read in one screen. Add `--prod` to ship after sign-off, `--no-push` to keep it local, `--regression full` to force the broad suite. |
| `/pilot` | The autonomous multi-task lane — feed it a goal (a roadmap batch, or "improve X until Y"), confirm the mission plan once, and it works task after task unattended: each routed to the full pipeline, the tweak lane, or a lane you defined yourself, with one batched close-out and a full mission report at the end. Point it at your open decisions instead with `/pilot --gates` and it re-measures each one before saying anything: the ones whose proposal has since died it closes itself, the ones waiting on something that hasn't happened yet it leaves alone and tells you what would move them, and the rest come back as a single sitting with a recommendation per row — so nothing that writes is ever decided without you, and nothing you already answered is asked again. Run it with nothing after it and it works the **standing mission** — whatever `/whats-up` would tell you needs doing, in rank order, asking nothing up front and only the high or critical questions at the end — which is what a session left on `/loop /pilot`, or a scheduled headless shift, keeps doing while you're away. |
| `/tweak` | The sanctioned lightweight lane for iterative rounds — pixel nudges, copy, small hotfixes — verified inline (screenshots/curl), with one batched close-out enforced at push time. |
| `/revert` | Sanctioned rollback: `git revert` (never reset), scoped re-verification, and a logged reversal. |
| `/tidy` | Resolve leftover WIP — sweeps the dirty tree, stashes, worktrees and stale branches, probes git history to establish what each item actually *is* (superseded ≠ accidental), then routes every one to commit / deliver / discard / ignore. |
| `/design` | Generate 2–3 HTML variants, open them in the browser, route the winner to `/code`. Each one is held to how your app already does things — the existing pattern is looked up before a new one is proposed, and icons come from your icon set or a generation skill rather than being drawn by hand *(if a design skill is present)*. |
| `/whats-up` | Where the project stands, in a fresh session with no handover. Reads every store that outlives a session — the roadmap, unproven checks, unpushed commits, gates still waiting on you, the working tree — then tells you whether the project is blocked on a decision, carrying more work than it's finishing, or clear to start something new, and ranks what to do about it. That verdict decides what leads, not what you're shown — work you started and didn't finish gets a row of its own with how long it's been idle, instead of disappearing into the backlog count, and each waiting decision names the started work it would release. It corrects the stores as it goes: a gate that reads *waiting on you* but was answered weeks ago closes itself, because every decision on a gate is read together and any later one closes it — you answer it in the entry that resolves it and never go back to edit the old one. It also checks whether a decision is one you can actually make today. A gate that recorded what would settle it — a threshold nothing has tripped yet, an example nobody has tagged — is reported with that trigger instead of being offered as a question for the fifth week running, and one resting on numbers that have had time to move is offered as *re-measure this first*, because a repair that looked right a fortnight ago is exactly how good data gets overwritten. If your project runs something unattended — a nightly job, a background loop — you point it at that too and a broken one outranks everything else in the report; `/pilot`'s own unattended runs are one of those out of the box, reported as fine, busy or stale. It only reads: anything at risk of being lost becomes the top row with the command that saves it. |
| `/roadmap` | The way in from tracked work. Ranks the open items, then either runs the top ones as a `/pilot` mission or starts a single one through the full pipeline — so a morning's worth of roadmap is one decision instead of one gate per item. |
| `/wrap` | Close out ad-hoc work done outside `/code`/`/fix` — reviews the diff when source changed, runs `myapp-log` + `myapp-docs` + `myapp-skill` reference sync, then pushes per the deploy skill's push policy with a verified scorecard (`--no-push` to skip). |
| Living docs | `docs/roadmap.md` (open scope), `docs/project-log.md` (delivery history), `docs/workflow.md` (pipeline map) — all kept current by the agents. |

---

## Prerequisites

- Claude Code (`claude`) installed and authenticated
- A git repo (recommended — hooks use `git status`)
- `jq` on PATH (used by hook scripts)
- `python3` on PATH (used by the delivery graph; stdlib only, no packages). Without it the graph simply never builds and every call site falls back — the pipeline still works, just without the index.
- For unattended runs: `askUserQuestionTimeout` and `autoContinueAtUsageLimit` set in your own `/config` — nothing in an install sets them, a gate with no timeout waits forever, and without auto-continue the usage window is a dead stop. Headless shifts also need macOS `launchd`, and take an optional Discord or Slack incoming-webhook URL for their reports
- [`agent-browser`](https://github.com/vercel-labs/agent-browser) plugin installed — used by `<PREFIX>-test` for E2E browser automation
- [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill installed — used by `<PREFIX>-skill` to author and update skills
- [`ui-ux-pro-max`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) skill installed — used by `<PREFIX>-design` for design intelligence (styles, palettes, font pairings, design-system generation) *(conditional: only if a design skill is installed; can be replaced with any design skill — update the reference in `<PREFIX>-design/SKILL.md` after install)*
- `visual-assets` skill installed, with `GEMINI_API_KEY` exported — used by `<PREFIX>-design` to generate icons and artwork at the exact size a platform needs, so a new icon sits in the same family as the ones beside it *(conditional: only if a design skill is installed; can be replaced with any image-generation skill — update the reference in `<PREFIX>-design/SKILL.md` after install)*

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

It opens by telling you what state the repo is already in: work sitting uncommitted, commits that passed review but were never pushed, and the checks still unproven that you could still close. None of that blocks anything — it's there because a run that builds on unshipped work should say so first.

Then one gate, and it tells you rather than asks: here is what *done* means, here are the checks that will prove it, ship after sign-off or hold? Type into the free-text field to correct the goal, swap a check, or say you'll verify it live — otherwise silence is agreement.

### Fix a bug
```
/fix <describe the bug or regression>
```
Runs: `myapp-debug` → `myapp-dev` → `myapp-qa` → `myapp-pm`

### Run a whole batch autonomously
```
/pilot <goal — e.g. implement all open roadmap items, or improve an area until measurable criteria pass>
```
Opens by telling you which checks are still unproven in this repo — a mission is one of the few places that can actually close them, so it starts by showing you what it's about to build on top of, and if the same missing piece is blocking three of them, that becomes an option at the gate. Then it decomposes the goal into tasks, asks one up-front gate (confirm plan + ship policy), and works unattended: each task routed to the lane that fits it, per-task delivery-log entries, no mid-run questions. Prod deploy and push happen only at the single close-out, gated as usual — and the close-out checks docs and reference sync once for every task that didn't go through the full pipeline, so a run made entirely of small changes still ends with the docs and the path-ownership map caught up. `--max-tasks N` caps the run; ends with a mission report of every task, its status, and its evidence — and, when the run stopped short, a resume line you can paste back.

Lanes are yours to extend: any command that declares how work should reach it becomes a destination, so a project-specific routine joins the rotation without touching `/pilot`. A lane that burns something finite — credits, API calls, generation runs — runs against a budget you grant at the same up-front gate, and stops dispatching when it's spent rather than quietly overrunning. A lane also says how an approved decision gets carried out, and the run proves it can do that *before* it asks you — so you're never asked to approve something the session then turns out to be unable to perform.

Anything that writes, ships or adopts is still yours to decide and comes back with the evidence needed to answer it. What changed is everything else: a run may conclude what its own measurement concludes. Point it at your open decisions with

```
/pilot --gates
```

and it re-measures each one first. A repair whose bad records are already gone, a payoff that no longer exists at today's numbers, a change nothing reads any more — it closes those itself and records the measurement that killed them. A decision waiting on something that hasn't happened yet stays put, with the trigger restated, instead of arriving as a question you can't answer. Whatever's left comes back as one sitting: a table of what it found and what it recommends per row, answered in a single reply. You're asked about scope up front and about dispositions once, at the end — never the same decision twice, because until the re-measure runs the only thing it could recommend from is the stale evidence you're re-measuring. Your answer is written down before anything acts on it, and an approval is never recorded without the work it authorises attached — so if the session dies mid-repair, the decision survives and the next one picks it up from `/whats-up` rather than from a note you had to write yourself.

### Let it run while you're away
```
/loop 30m /pilot --max-tasks 1
```
`/pilot` with nothing after it is the standing mission: the same read `/whats-up` does, turned into a task list — finish what's started, re-walk checks whose blocker has cleared, close decisions the evidence has killed, then the ranked backlog — capped at a few tasks so one run never drains your usage window. It asks nothing up front, because every task came from a record you already keep, and holds everything at UAT, so nothing ships until you've seen it. Give the loop a fixed interval rather than letting it pace itself: a self-paced loop's only heartbeat is the wake its last turn set, so when the usage limit refuses that turn nothing is left to fire and it sleeps until you come back; a fixed interval keeps firing, fails cheaply while the window is spent, and on the first firing after the reset picks up the run it was in the middle of. A firing that lands while a tick is still working simply waits for the next one.

One setting of yours makes that safe to walk away from, in `/config`: a question timeout, so a gate nobody answers defaults instead of waiting forever. Auto-continue at the usage limit is worth switching on too, but don't rely on it for a loop — it resumes a conversation stopped mid-request, and a loop hitting the limit is usually asleep on a timer or waiting on an agent, which is why the fixed interval carries the weight. Start the session with Remote Control and the few questions a run does decide to ask — a decision whose evidence moved, something blocking a high-priority item, a task that failed twice — arrive on your phone as a push; answer in time and it's yours, miss it and it's parked. Everything else it could have asked is parked without asking. A check-in is `/whats-up` and then `/pilot --gates`, which puts the whole parked batch to you in one sitting; the report also lists the next shift's queue, so a word from you drops an item before a run nobody watches starts it.

When a session left open isn't reliable enough — the Mac sleeps, the terminal closes — `.claude/pilot/shift.sh install` schedules the same run headless: a fresh process every half hour with a dollar cap, resuming a run the usage limit cut short before starting the next, and posting its report to a Discord or Slack webhook if you give it one. Unattended runs put every agent on Sonnet and keep the session that directs them on your chosen model; runs you sit in on use the agents' own models — so the work you're watching gets the pricier model, the work you aren't gets the cheaper one, and the report says which was which.

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

### Clean up a dirty working tree
```
/tidy
```
Sweeps uncommitted changes, stashes, worktrees and stale branches, then investigates history before judging any of it — a file whose replacement already landed is *superseded*, not accidentally deleted, and the two want opposite treatment. Proposes a disposition per item (commit / deliver / discard / ignore / keep), applies it with self-protecting commands (`discard` becomes a named stash, `git branch -d` never `-D`), and re-runs the sweep as proof. `/code`, `/fix`, and `/pilot` route here when entry WIP overlaps the paths they're about to touch.

### Design a UI feature *(if design skill installed)*
```
/design <describe the UI to design>
```
Generates 2–3 HTML variants, opens in browser, routes chosen direction to `/code`.

Before anything is proposed, `myapp-design` looks at how your app already handles what you're asking for — the confirm dialog it already has, the empty state it already shows — and either matches it, migrates the older ones to the better form, or records why this one deliberately differs. That record grows with the app, so the next person to touch a surface starts where the last one left off instead of inventing a second answer. Icons work from the same principle: your icon set wins when it has one, and when it doesn't, the asset skill generates one from your palette with the neighbouring icons as reference. Nothing is drawn by hand — an icon composed from a description comes out logically right and graphically wrong.

### Pick up where you left off
```
/whats-up
/whats-up consent
```
Start here after a few days away. Every close-out's *Open* block lives only as long as its session, so what needs you is scattered across six places that each get read only when you happen to start the matching lane. This reads all six at once and answers one question — what should I do right now? You get the diagnosis in a line (*blocked on you*, *carrying more than it's finishing*, or *clear*), then the same five blocks every other command ends with, where the Open table is already ranked so the thing that unblocks the others sits at the top. The diagnosis decides what leads, never what you're told: a project blocked on a decision still lists the work it has half-finished. **Anything you started and didn't finish gets its own row** — what's left, the command that finishes it, and how long it's been since anything touched it, so a repair that quietly stopped three weeks ago stops reading like active work. Each waiting decision names the started work it releases, which is usually the argument for answering it first — and only decisions you can actually make today are put to you. One that recorded what would settle it, and is still waiting for that, is reported with the trigger rather than asked again; one resting on measurements old enough to have moved comes with *re-measure first* as its next step, because the recommendation matters less than whether the numbers behind it are still true. Items nobody has picked up stay a count, and that count says what it's made of — how many are genuinely queued versus never given a status at all. Because the rows are usually three kinds at once, the closing line stages them by what it costs to clear one: answer the decisions first, then the repairs, then the missions — and it won't propose a mission that answering a decision would reshape. A filter narrows it to one feature or path. It changes nothing in the repo — so a failing check, a stale branch or an unanswered gate is reported with the command that fixes it, never fixed behind your back.

### Work the roadmap
```
/roadmap
/roadmap high priority --max-tasks 4
```
Ranks the open items — anything already started before anything untouched, then priority, then dependency order so nothing runs before the thing it needs, then category — and offers two ways forward: hand the top set to `/pilot` as one unattended mission, or start a single item through `/code`/`/fix` with its own gate. A filter narrows the set before ranking. Only the selecting happens here; the run limits, retries and budget all belong to `/pilot`.

### Wrap up ad-hoc work
```
/wrap <description of what changed>
```
Close-out for changes made outside the `/code`/`/fix` pipelines — manual data fixes, config changes, ad-hoc edits. Runs `myapp-log` + `myapp-docs` + `myapp-skill` reference sync to ensure the audit trail and references stay consistent.

---

## What gets verified

You describe the outcome; the workflow works out what would prove it. Each task states one sentence of *done* — where the user ends up, not what changed — and derives its checks as clauses of that sentence. They're kept as plain assertions and re-run against the live stack every time they're relevant, so a route change can't quietly make one stale.

| | |
|---|---|
| **Who writes them** | The agents, from the stated outcome. You correct them at the gate if they're wrong — you never assemble them from a list. |
| **How they run** | Checks that talk to an endpoint or the datastore are executed in batches by a small runner rather than one at a time, so response bodies don't pile up in the session. The runner reports what happened — the status code, how long it took, the first line of the body — and never decides the outcome; the workflow reads those observations and rules on each check itself. A batch runs a few checks at a time with a short timeout each, so one hung endpoint costs one observation, not the batch. Screen checks stay hands-on, because the evidence is a screenshot someone has to look at. When a set is big enough to split across helpers, the helpers run on Sonnet — they execute and record against a brief, nothing more — and the report names the model so the saving is measurable. |
| **What always runs** | Smoke, this task's checks, and any earlier check covering the same files. The end-state one is never traded away for time. An earlier check that passed at a commit nothing has touched since is carried forward with that commit range as its evidence rather than run again — it's reported on its own line, so a carry never reads as a fresh pass. Anything that failed, was blocked, or covers files that did change is always re-run. |
| **How wide it goes** | Decided after the code is written, from what actually changed: a change crossing two domains, or landing where a check is already failing, pulls in the full suite. `--regression full` forces it — and because that re-covers every earlier check on every task *and* every fix round, a run tells you the scope up front, next to the task list, while you can still change it. |
| **When it can't run** | Recorded *blocked*, with the reason and what would close it — never as a pass. A check whose condition never arose didn't pass; it didn't run. |
| **Where it goes then** | Sorted, not waved through: one a local environment *could* have run sends the work back for another fix round; one only production can answer is walked right after the deploy; one waiting on an outside trigger — a nightly job, a webhook — is deferred with that trigger named. A prod deploy clears everything it makes answerable, not only the check from the run that triggered it, so holding at UAT for a while doesn't leave a pile nobody can reach. |
| **What reopens** | Anything still unproven resurfaces at the start of the next `/code`, `/fix` or `/pilot` in that repo — the three that could actually close it — so a deferral has to be closed rather than forgotten. Checks nothing local can ever run — a component that only ships to prod, a quota-bound call — are counted rather than listed, so the ones you can still close stay readable. |

---

## What you get back

Every command that closes work ends the same way, so you read the shape instead of the sentences. Five blocks, and then it stops:

| Block | What it tells you |
|---|---|
| **Verdict** | One line: what state the work is in, and whether it needs you. |
| **Learned** | At most three bullets, often none — only what changes your picture: a number you rely on that turns out to measure something else, a bug that passed every test you already had, a page that was being checked and didn't exist. It's second because it's the part you can't get from the diff. |
| **Status** | A row per thing that was meant to happen or was checked, each with one word from a fixed set — `needs you`, `failed`, `not done`, `not proven`, `done`, `proven`, `n/a`. Rows that aren't in a good state come first. |
| **Open** | Your inbox: anything that needs a decision or an action from you now — a question waiting on you, a check that failed, something you said you'd verify live, work left in the tree, work you started and haven't finished. Each row carries the exact thing to run or click, and something already written to the roadmap still shows up here if it's what you should do next. A choice made for you because you didn't answer in time appears here, labelled as such. Nothing open says `None`. |
| **Emerged** | The receipt: everything else the run turned up and where it now lives — a roadmap item with its id, a check filed as unproven, a named stash. Each row names what will raise it again, so you can forget it on purpose. Nothing appears in both blocks, and anything with nowhere to live goes in Open rather than quietly evaporating. |

Then one last line, and it's the one you act on: `none — nothing open, safe to start a fresh session`, or the single command that clears the top of Open — or, when two or more things are waiting, one `/pilot` line that takes on the whole set at once — by id when they are all tracked, otherwise as a goal naming them — so you are never handed seven open things and one of them. That's the answer to the question a report usually leaves you guessing at — whether this piece of work is finished, or whether closing the terminal loses something. It can only say you're clear when Open is empty, and Open can only be empty once everything else has somewhere to live.

`done` and `proven` are deliberately different words. Code that was written is *done*; a journey somebody actually walked is *proven* — and a change that shipped with a check nothing could run says `not proven`, rather than reading as finished. Long runs get more rows, never more prose: rows in a good state fold into a single line, and the two blocks that need you never fold at all.

---

## How the hooks enforce correctness

| Hook | Fires on | Blocks if |
|---|---|---|
| `skill-guard.sh` | Edit / Write | Editing an owned path without the owning skill loaded (markers scoped per session, so a skill loaded inside a subagent still counts) |
| `path-coverage-check.sh` | Write | New file in a governed root with no matching PATH_MAP entry |
| `dependency-guard.sh` | Bash | `pnpm add` / `pip install` without `myapp-skill` loaded |
| `package-edit-guard.sh` | Edit | Adding packages to `package.json` directly without `myapp-skill` |
| `pre-handoff-check.sh` | Skill + Task/Agent | Invoking or spawning `myapp-qa` with uncommitted changes, lint errors, or type errors |
| `close-out-gate.sh` | Bash | `git push` while commits since the last delivery-log entry touch governed/deploy paths (`CLOSEOUT_OVERRIDE=1` escape hatch) |
| `ref-sync-check.sh` | Bash (post) | Warns after commit on reference-worthy drift — structural changes or `REF_WATCH` matches — without reference updates, or deploy-mechanism drift without `deploy-config.yaml` updates. Path patterns sourced from `governed-paths.conf`. |
| `skill-mark.sh` | Skill (post) | Records loaded skills to a session-scoped marker (used by all guards, and by `myapp-log` to fill the delivery log's skills line) |
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
