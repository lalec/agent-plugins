# dev-workflow — open work

Scope: the plugin itself. Per-project rollout status is deliberately **not** tracked here — check an
install directly when you need to know its state. Delete this file when the list below empties.

Plugin repo: `lalec/agent-plugins`, `plugins/dev-workflow/`. Everything committed and pushed.

---

## 1. Rollout backlog — the one concrete task

**8 template commits have landed since installs were last upgraded.** The largest is the
acceptance-statement rework (`51c1993` + `8b5cca3` + `ce8688b` + `c22dffa`), which changes how every
task defines "done". Two installs have it, two have none — check with:

```sh
grep -c 'Done means:' <project>/.claude/commands/code.md <project>/.claude/commands/fix.md   # want 3 + 3
```

Run `/dev-workflow:upgrade` **in each repo's own session** — the skill resolves `.claude` against
cwd, so it cannot be driven from here. Everything in the backlog has a Step 5 checklist entry and a
Step 7 apply bullet; nothing needs hand-authoring.

---

## 2. Shipped without live evidence

Each of these is correct by construction and unproven in a real run. They are listed in rough order
of how likely a silent failure is to matter.

- **The agent-owned gate.** Step 0.5 no longer asks the user to pick verifications, and no longer
  asks the regression scope before dev has run. Confirm states the plan of record and free text is
  the only override; scope defaults to `auto` and is resolved once by `<PREFIX>-test` from the paths
  actually changed. Two things to watch on the first real runs: whether the four-row "Other"
  disposition routes a real reply correctly (a goal correction misread as a check amendment builds
  the wrong thing silently), and whether `auto` escalates sanely — check an `auto→full` run against
  the $21.56 baseline with `session-cost.py`.
- **The end state is non-negotiable.** It cannot be narrowed away by `smart`, by a retest, or by
  `/pilot`'s fixed-`smart` lane; unreachable is `blocked` with a `reason`, never skipped. The
  `last.reason` field was being read by `graph.py` and quoted by `/code` Step 0 while nothing told
  the writer to write it — now required on `blocked`/`fail`, and unproven until a blocked row
  renders with a real reason.
- **`/roadmap` as a lane.** It ranks (via `roadmap-open`, with the fallback) and hands the top set
  to `/pilot --items`, or starts one item through `/code`/`/fix`. The rank rule now exists once, in
  `roadmap.md § Rank`; `/pilot` cites it. Never run against a roadmap with real dependencies between
  selected items, which is where the merged rule differs from both old ones.
- **Acceptance statement, end to end** (`51c1993`). The pipeline now derives verifications from a
  stated end state rather than the diff, dev must walk it before `complete`, qa before sign-off.
  Never exercised on a task where the journey actually dead-ends — which is the case it exists for.
- **Deferral routing by declared environment shape** (`8b5cca3`). Three branches: non-prod env
  exists → block; prod-only → post-deploy prod walk; out-of-band trigger → defer with
  trigger + observable + location. Only the first has plausible coverage; the prod-walk carry-forward
  has never run.
- **`pass` means exercised-and-held** (`ce8688b`). A check whose condition never arose is `blocked`,
  not `pass`. Found on real data, but the corrected semantics have not been through a full cycle.
- **The parked-agent fix** (`ed6f7ba`). Foreground-wait rule + salvage on any non-`## Handoff`
  return. Nothing has parked since — good outcome, not proof. Both halves must hold together.
- **Salvage mechanism split** (`263ea15`). SendMessage to a completed agent always resumes
  *detached*, so the retry leg (qa blocks → dev fixes) silently left the foreground contract. The
  fix forbids inferring state from the resume call; the retry leg has not run since.
- **`/pilot` lane registry against a second shape.** Only one project declares lanes, so discovery
  has run against exactly one config. A second declaration is the cheap test.
- **`open-deferrals` at `/code`/`/fix` Step 0.** A real open deferral exists somewhere in the fleet,
  so the next task in that repo exercises it.
- **A project with no `python3`.** The documented graph fallback has never been hit.

---

## 3. Decided, not yet built

- **Stage 2 — `/pilot` mission graph** (`.claude/pilot/mission.json`, `EXEMPT` in PATH_MAP, written
  directly by `/pilot`, no new lifecycle skill; deliberately *not* under `.claude/graph/` because the
  delivery graph is derived and disposable while mission state is authoritative and unrebuildable).

  **Re-justify before building.** The evidence has moved against it: an overnight `/pilot` and a
  later lane mission both completed without losing state, and every real failure so far has been
  something else (a parked agent, a dropped acceptance statement). Build it when a run actually
  loses its place.

  `/roadmap --items` weakened the case further rather than strengthening it. A roadmap-driven
  mission has no state that needs a file: the ids are permanent, so the unreached set is exactly
  re-expressible as `/pilot --items <id>,…`, and pm's required roadmap status flip is already an
  authoritative record of what completed — **the roadmap is the mission state for this lane.**
  Duplicating it into `mission.json` would be the parallel mechanism Rule 7 forbids. So any future
  justification must come from a **target-state or plain-batch** mission — the only shapes whose
  state has no other home.

- **Stage 3 — findings + hotspots: dropped, not deferred.** Redundant with skills + Reference Sync,
  which is semantic rather than statistical, injected at point of use, and aggregated per-domain
  where the data is dense. Raw touch-frequency ranking is dominated by `docs/roadmap.md` and
  reference docs, so it would need normalisation before it said anything true.

---

## 4. Settled — do not re-litigate

Recent and subtle enough to be worth re-opening by accident:

| Question | Answer |
|---|---|
| Is the 1-hour cache TTL a cost lever? | **No.** Forcing 5m costs *more* (−$1.22, −6%) — the top level idles past 5m waiting on subagents (p90 498s). Leave it. |
| What does a pipeline run cost? | **$21.56** for a full design → implement → review → test → sign-off → log cycle. No dominant component; 78% is cache traffic, which is what re-reading context each turn looks like. Reproduce with `session-cost.py`. |
| Should `Deployed:` appear on a `ship=prod` run with no prod env? | No — nothing deployed, so its absence is the honest record. |
| Should verification `paths` exclude all of `.claude/**`? | No — behavioural surface only: docs-only paths out, `.claude/skills/**/scripts/**` in. |
| Are skill markers per-agent? | No, per-**session**, and that is required — `<PREFIX>-log` derives `Skills:` from the same marker and only session scope sees subagent-only skills. |
| Can a marker prove a *command* ran? | No. `skill-mark.sh` fires on the Skill tool; a user-typed slash command can leave no trace. Use the delivery log's `Decisions:` and `git log`. |
| Is the log field set extensible? | No — closed. Leftover scope goes to `docs/roadmap.md`, unrunnable checks to `UAT-deferred:`. |

Older settled items (roadmap/log parser shapes, graph tracking, marker scoping, fence handling) are
in `git log plugins/dev-workflow/` — they have been stable for many passes and are not worth
re-reading unless a symptom points at them.

---

## 5. Working rules earned the hard way

- **Fix the plugin, never hand-patch an install.** Project-side patches get overwritten and hide the
  upstream hole. If a project needs a change, the template needs it.
- **When `/code` and `/fix` share a mechanism, diff the two sections** — they are near-duplicates by
  design, so a change applied to one is invisible from inside either file. `/fix` shipped for weeks
  capturing an acceptance statement it never passed to its agents.
- **Idempotency guards must check the end state, not a phrase.** An upgrade bullet that skipped on
  "acceptance statement" was satisfied by the half-applied state and would never have repaired it.
- **Grep the old vocabulary, not just the old code.** A mechanism change in four places left its
  *description* wrong in seven more.
- **Transcript metrics: collapse on `message.id` taking `max()` on `output_tokens`** (rows are
  per-content-block and output is a running partial), **and cut the window at the run boundary**
  (session files accumulate every resume). Both traps inflated the first cost baseline; `max()`
  matters because first-row undercounts subagent output ~10× while looking plausible.
- **Per-project work needs a session in that repo.** `/dev-workflow:upgrade` and `/code`/`/fix`
  resolve against cwd.
- **Concurrent sessions in the test-bed repos are normal.** Re-read state immediately before acting.
- **Never `rm -rf .claude/graph/` in a project.** Every call site falls back silently, so its absence
  is invisible.

---

## Maintainer tools

- `plugins/dev-workflow/session-cost.py` — transcript cost accounting; handles both traps above,
  warns on long idle gaps, `--until <iso>` cuts the window. Deliberately at the plugin root, not in
  `shared/` (which is install-artifact territory).
