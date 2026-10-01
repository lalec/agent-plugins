# Install — `docs/workflow.md` template (Phase 2)

> Paths of the form `../../shared/<file>` are relative to the install skill's directory (`plugins/dev-workflow/skills/install/`), i.e. the plugin's `shared/`.

Also create `docs/workflow.md` if not present — generate with real content using values confirmed in Phase 1 (not a stub):

```markdown
# <PROJECT> Delivery Workflow

## Pipeline

```
/code or /fix
      │
      ▼
  (top level) single gate — states the acceptance statement and the verifications derived from it;
              free text amends them. Regression scope is not asked: it is pinned by --regression
              or resolved later from the paths that actually changed
      │
      ▼
  <PREFIX>-dev ── domain skills ── implement ── <PREFIX>-deploy(non-prod) ── Reference Sync
      │
      ▼
  (top level) ensure verification stack — start/restart the serve-env (with its stack: overrides) if a UX/E2E target is down or stale
      │
      ▼
  <PREFIX>-qa  ── <PREFIX>-review ── <PREFIX>-test ── sign-off (or signed-off-with-deferrals)
      │
      ▼
  <PREFIX>-pm  ── <PREFIX>-log ── docs update
      │
      ▼
  (only with `--prod`) ── <PREFIX>-deploy(prod) at the command top level, after sign-off
      │
      ▼
  (top level) close out — push per <PREFIX>-deploy § Push policy + verified scorecard
```

Iterative work (pixel nudges, copy rounds, small hotfixes) uses `/tweak` — top-level, inline-verified, close-out batched at exit and enforced by the `close-out-gate` hook at push time. Dependency advisories use `/audit`: it gives each one a VEX status, blocks only on the ones an attacker can actually reach, records the rest in `vex.yaml` so they are never re-decided, and `--deep` runs the built-in `/security-review` over the commits no deep pass has covered. Rollbacks use `/revert` (git revert + scoped re-verify + logged reversal). Leftover WIP — a dirty tree, orphaned stashes, stale branches — uses `/tidy`: it sweeps, probes history to establish what each item actually is, and routes every item to commit / deliver / discard / ignore. Multi-task autonomous runs (a roadmap batch, a goal to iterate toward) use `/pilot` — it decomposes the goal, gates once up-front, routes each task through the pipeline or the tweak lane, and closes out once at the end. `/pilot --gates` is the same lane aimed at a store instead of a goal: it re-measures every parked verdict, closes on its own the ones whose proposal the measurement killed or whose trigger has not fired, and brings the rest back as one batched decision with a recommendation per row — nothing that writes is ever concluded without an answer. `/roadmap` is the way in from tracked work: it ranks the open items (one rank rule, defined in `roadmap.md § Rank` and cited by `/pilot`) and either hands the top set to `/pilot --items <id>,…` as a mission or starts a single item through `/code`/`/fix`. It selects and never implements, so run constraints — task cap, retry limit, budget — live only in `/pilot`. `/blueprint` is the way in for work nobody has planned yet: it reads the record, probes every value it prescribes against the code — that the cited site is on the path production takes, that the literal being replaced exists once, that the literal itself survives the values the project already stores — makes every decision an executor would otherwise guess, and writes one umbrella plus `/pilot`-shaped child items to `docs/roadmap.md` — planning on the strongest model (its frontmatter `model:`), execution unchanged; `/pilot --items <umbrella-id>` expands to the children, and the decisions block follows any item carrying a `**Parent:**` however the mission was addressed. `/whats-up` is the read-only composed reader for a fresh session: it reads every store that outlives a session, reconciles them, and reports what needs a person — and `/pilot` with no arguments is the **standing mission** that takes exactly that report's rows as its task list, asks nothing up front, and asks nothing at close-out either — whatever needs a person parks for `/pilot --gates`, most urgent first. That is what runs unattended: `/loop 30m /pilot --max-tasks 1` in a session left open with Remote Control (a fixed interval, never self-paced — a self-paced loop dies when its own wake is refused at the usage limit, a fixed one fires again after the reset and resumes its own interrupted run; a loop over named items asks its gate once, on the first firing, and later firings inherit the answer), or `.claude/pilot/shift.sh install` for headless launchd shifts that need no open session at all. An unattended run dispatches every subagent on Sonnet and keeps the orchestrator on the session model; an attended run uses the agents' own models. A check-in is `/whats-up` → `/pilot --gates`, which asks everything the unattended runs parked, in one sitting.

## Agents

| Agent | Role |
|---|---|
| `<PREFIX>-dev` | Design → implement → deploy non-prod → Reference Sync → hand off to `<PREFIX>-qa` |
| `<PREFIX>-qa` | Code review (`<PREFIX>-review`) + tests (`<PREFIX>-test`) → sign-off (`signed-off` \| `signed-off-with-deferrals` when only unrunnable verifications remain) → hand off to `<PREFIX>-pm` |
| `<PREFIX>-pm` | Verify QA phases ran → write delivery log (`<PREFIX>-log`, hash = the feature commit) → update docs if needed |
| `<PREFIX>-verify` | Verification child: executes one slice of a split verification set and records outcomes through the runner. Dispatched only by `<PREFIX>-qa`; Sonnet, 60-turn cap and no CLAUDE.md are set in its frontmatter, so no caller decides its price |

Prod deploy is **not** an agent step — it runs at the command top level only when `/code` / `/fix` is invoked with `--prod` (so the `<PREFIX>-deploy` `AskUserQuestion` gate reaches the user), after QA sign-off, on the final code. The `<PREFIX>-deploy` skill carries **no** `disable-model-invocation` frontmatter — the dev step and the command must be able to invoke it via the Skill tool; prod safety comes from its `user_confirm` gate, not a frontmatter gate.

Gate timeouts split by risk: reversible gates proceed with defaults labeled `auto-selected on timeout — not user-confirmed`; irreversible gates (prod deploy, CI-coupled push) park until the user responds. A timeout is never presented as consent.

## Skills

### Lifecycle

| Skill | Purpose |
|---|---|
| `<PREFIX>-log` | Appends delivery log entries to `docs/project-log.md` |
| `<PREFIX>-review` | Code review reception, reviewer dispatch, verification gates |
| `<PREFIX>-debug` | Systematic debugging — four-phase root cause investigation |
| `<PREFIX>-deploy` | Deploy authority — caller-driven env selection (`target=non-prod` from `<PREFIX>-dev`, `target=prod` from the `/code\|/fix --prod` command step); reads `references/deploy-config.yaml` (unified env schema: `run:` serve-envs / `deploy:` ship-envs / `invoke:` run-to-completion jobs, which serve no url and are passed over when resolving a target), fills missing values, gates prod inline via `AskUserQuestion`, verifies reachability; holds critical packages to exact pins and every build to a start-up check |
| `<PREFIX>-test` | Smoke (always) · per-task verifications via `custom-tests.yaml`, end-state check never narrowed away · regression scope pinned by the caller or resolved from the changed paths |
| `<PREFIX>-skill` | Meta-skill — skill system governance and path ownership |
| `<PREFIX>-docs` | Documentation sync — README and workflow.md |
| `<PREFIX>-graph` | Delivery graph — projects the log, verifications, ownership and deploy config into a queryable edge index (`covers` / `blast` / `history` / `roadmap-open` / `open-deferrals` / `open-gates`); derived and disposable, every caller falls back without it |

### Domain

<DOMAIN_SKILL_TABLE>

(Path ownership is the single source of truth in `.claude/hooks/governed-paths.conf`.)

Each domain skill defines a `## Quality Checklist` — what to run (tests, lint, type check) before proceeding to deploy. `<PREFIX>-dev` step 3 delegates to these checklists; the specific commands live in the skill, not in the agent.

## Hook Infrastructure

All hooks wired in `.claude/settings.json`.

| Hook | Event | Enforces |
|---|---|---|
| `skill-guard.sh` | PreToolUse Edit/Write | Owning skill must be loaded before editing governed paths (session-scoped markers) |
| `path-coverage-check.sh` | PreToolUse Write | Blocks new files in governed roots with no matching owner |
| `dependency-guard.sh` | PreToolUse Bash | Requires `<PREFIX>-skill` before adding packages |
| `package-edit-guard.sh` | PreToolUse Edit | Requires `<PREFIX>-skill` before editing package files directly |
| `pre-handoff-check.sh` | PreToolUse Skill + Task/Agent | Blocks `<PREFIX>-qa` (skill call or subagent spawn) if uncommitted changes or lint fails |
| `close-out-gate.sh` | PreToolUse Bash | Blocks `git push` while governed commits lack a delivery-log entry (`CLOSEOUT_OVERRIDE=1` escape) |
| `ref-sync-check.sh` | PostToolUse Bash | Warns on reference-worthy drift (structural / `REF_WATCH`), deploy-config drift, dependency drift, and em dashes added to user-facing copy |
| `skill-mark.sh` | PostToolUse Skill | Records invoked skills to a session-scoped marker |
| `post-commit.sh` | PostToolUse Bash | Reminds to run `<PREFIX>-log` after every commit |
| `agent-mark.sh` | SubagentStop (pipeline agents) | Records every pipeline-agent stop to a session marker; blocks a stop **once** when the agent's last message lacks its `## Handoff` block |
| `pilot-cleanup.sh` | SessionEnd | Removes `.claude/pilot/running` when its second line is this session's id |
| `limit-mark.sh` | StopFailure `rate_limit` | Writes `.claude/pilot/limit-hit` (ts · session id · error_type) so the next `/pilot` resumes a limit-killed run instead of waiting it out |

## Delivery Log Format

Each entry in `docs/project-log.md`:

```
---
### YYYY-MM-DD HH:MM · `<7-char hash>` — <short title>

<1–3 sentences: what shipped and why it matters>

**Tests:** <what was verified>
**Skills:** <skill-x> · <skill-y>
**Deployed:** <component> → <env> · <url>  ← omit line if no deploy happened
**Addresses:** <roadmap **Id:** value(s)>  ← omit line if no tracked item is addressed
**UAT-deferred:** <verification names + how confirmed>  ← omit line if nothing deferred
**Decisions:** <gate>=<value> (<user|timeout|agent|pilot-auto>) · …  ← omit line if no gate came up
**Checklist:** <skill> — <what changed>  ← omit line if nothing updated
```

The hash is the primary feature/fix commit, never a `test:`/`log:`/`docs:` bookkeeping commit.

`**Addresses:**` cites the roadmap item's permanent `**Id:**` — that citation is what links a
shipped commit back to the scope it closed. `**Decisions:**` records how each gate was settled;
a timeout, a pipeline-derived value (`agent` — the regression scope resolved from the changed paths
is the standing case), or an autonomous choice is never written as `user`, and a gate deliberately
left for a human is written `<gate>=parked (human-gated)` rather than being decided.

This field set is **closed**. Leftover scope goes to `docs/roadmap.md` as its own item, and a
verification that could not be run goes to `**UAT-deferred:**` — not into an invented field. The
graph ignores unknown fields silently, so an invented one reads as recorded but is not.

The delivery log is also the delivery graph's primary input — `<PREFIX>-log` runs
`python3 .claude/graph/graph.py build` after committing each entry, so these fields become
queryable. See `<PREFIX>-graph`.
```

Substitute `<DOMAIN_SKILL_TABLE>` with a markdown table built from `DOMAIN_SKILLS[]` and `DOMAIN_PATTERNS[]` confirmed in Phase 1c:

```
| Skill | Owns |
|---|---|
| `<PREFIX>-<name>` | `<path-pattern>` |
| `<PREFIX>-design` | *(no path ownership — visual + UX-pattern + icon decisions)* |  ← only if design skill was created
```
