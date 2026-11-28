# dev-workflow

A multi-agent delivery workflow for Claude Code. One agent builds, one reviews and tests, one ships and logs — each gating the next, so nothing reaches prod unreviewed or undocumented. You say what done looks like; it works out what would prove that and holds the work to it, one task at a time or a whole batch unattended.

> Agent and skill names are prefixed with a name you choose during setup. Examples below use `myapp`.
>
> **Claude Code only.**

---

## What it installs

| Component | What it does |
|---|---|
| `myapp-dev` | **The builder.** Loads the right domain skills, writes the code, runs the quality checks, deploys non-prod and hands off a report, so QA always tests a live stack. |
| `myapp-qa` | **The gatekeeper.** Reviews the code with Claude Code's `/code-review`, runs the security scanners, runs the tests, then walks the end state itself as your declared test user — never as you, never on prod. A fix goes back to `myapp-dev`; a check it can't run is reported *blocked*, never skipped. |
| `myapp-pm` | **The closer.** Confirms QA ran, ships prod when asked, writes the delivery log, refreshes docs and advances the roadmap, so the audit trail writes itself. |
| `myapp-verify` | **The runner.** Walks one slice of a test set too big for one context, on the cheaper model with a hard turn cap, so a fan-out costs what it says. |
| 8 lifecycle skills | `log`, `review`, `debug`, `deploy`, `test`, `skill`, `docs`, `graph` — one per delivery concern, shared by every agent. |
| Delivery graph | `myapp-graph` indexes the delivery log, checks, path ownership and git, so agents ask "what verifies this file" instead of re-reading files. Rebuilt in under a second, gitignored. |
| Domain skills | One per source directory, generated from your structure. Each owns its paths and its lint/type/test checks, and updates itself as the code changes. |
| 17 hooks | Keep the process from being skipped: skills load before edits, handoffs are gated, nothing pushes without a close-out and a security check, and a `/pilot` run can't stall or overspend. See [the hooks](#how-the-hooks-enforce-correctness). |
| Secrets wrapper | **Values stay out of sight.** Secrets are used by name through `srun`, from your Keychain, 1Password, Dashlane, LastPass, AWS or GCP, and masked out of output. It is its own plugin; `/srun:setup` protects any other project too. |
| `/code`, `/fix` | Run the full pipeline (dev → qa → pm) from one line, with one gate that states what done means and what will prove it. `--prod` ships after sign-off, `--no-push` stays local, `--regression full` runs the whole suite. |
| `/pilot` | **The autonomous lane.** Give it a goal or roadmap ids; it works task after task unattended, within your Claude allowance and a weekly budget, and ends with one close-out. `--gates` puts your open decisions to you in one sitting. |
| `/tweak` | The light lane for small rounds — pixel nudges, copy, hotfixes — verified inline, with one close-out at push time. |
| `/audit` | Turns scanner output into decisions: each finding is exploitable here or not, with the reason. `--scan` runs the 90-day whole-repository scans. See [Security](#security). |
| `/revert` | `git revert` (never reset), scoped re-verification and a logged reversal. |
| `/tidy` | Sorts leftover work — dirty tree, stashes, worktrees, stale branches — into commit, deliver, discard or ignore, after checking history for what each one is. |
| `/design` | 2–3 HTML variants built on your app's existing patterns and words; the winner goes to `/code` *(if a design skill is present)*. |
| `/whats-up` | Where the project stands, read cold: what's blocked on you, what's half-finished, what to do next, with the commands to paste. Changes nothing. |
| `/roadmap` | Ranks open items, milestone first, and runs the top ones as a `/pilot` mission or one through `/code`. |
| `/blueprint` | Plans on the strongest model and writes the plan to the roadmap as items sized for `/pilot`, each checked against the code first. |
| `/handover`, `/proceed` | Save a session's state to a file and pick it up in a fresh session, with a drift check first. |
| `/wrap` | Close out work done outside `/code`/`/fix`: review, log, docs, reference sync, push (`--no-push` to skip). |
| Living docs | `docs/roadmap.md`, `docs/project-log.md`, `docs/workflow.md` — kept current by the agents. |

---

## Security

Security is checked at seven points, so a flaw is caught where it is cheapest to fix and nothing ships that a scanner and a reviewer haven't read.

| When | What runs | What it stops |
|---|---|---|
| Every change | `myapp-qa` runs the scanners on the task's commits — gitleaks for secrets, Semgrep for code, osv-scanner for packages, Trivy for infrastructure — and decides each new finding: exploitable here, or not, with the reason | A leaked key or unsafe code reaching sign-off |
| Every push and prod deploy | The security gate runs any scanner that hasn't read the unpushed commits, and Claude Code's `/security-review` reads the source changes | A push with an undecided or open finding, or a scanner that failed twice. It holds only on what the change brings in; older findings are backlog |
| Daily, and after a dependency file changes | The advisory watch re-checks the whole dependency tree in the background, sending only package names and versions | A critical advisory published overnight going unseen — it is named before every task, in `/whats-up`, and first in `/pilot`'s list |
| On demand | `/audit` decides the backlog: each finding is exploitable or not, and *not* needs one of five reasons | A long list with no priority. Fixes become upgrade items `/pilot` can run unattended |
| Every 90 days | `/audit --scan` runs the whole-repository scans listed in `scanners.yaml` — the `claude-security` plugin by default | A flaw spread across files no single change touches. Each finding becomes a roadmap item |
| After a prod deploy | A passive scan of the live site | A misconfigured live site. Findings are filed; the deploy is not undone |
| Always | Secrets are used by name through `srun`. Its guard blocks reading a `.env`, `~/.aws` or `~/.ssh`; its redactor masks anything shaped like a credential | A secret value reaching a transcript |

Rules that hold throughout:
- A scanner that fails leaves the code unassessed, never clean.
- A WAF or rate limit lowers a finding's priority, never closes it.
- An unattended run may change only versions in a dependency file, and only for an `/audit` upgrade item.
- Known limit: a push spelt through `sh -c`, `env` or a full path to `git` is not gated.

---

## Prerequisites

- Claude Code (`claude`), installed and signed in. Its `/code-review` runs at the effort you last set (`/code-review high` sets it for later runs).
- A git repo, `jq`, and `python3` (**required** — the delivery graph needs it; stdlib only).
- The [`srun`](../srun/README.md) plugin — installed with this one.
- Security scanners — gitleaks, Semgrep, osv-scanner, Trivy, and ZAP for a live site *(optional, needs Docker)*. Install puts any missing ones on the machine for you. Any SARIF tool can fill a slot; one that sends code to a vendor is used only when you name it.
- The `claude-security` plugin *(optional)* — the 90-day whole-repository scan.
- [`agent-browser`](https://github.com/vercel-labs/agent-browser) — browser automation for E2E checks.
- [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) — used to write and update skills.
- [`ui-ux-pro-max`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) and [`visual-assets`](https://github.com/lalec/agent-skills/tree/main/visual-assets) — design and icons *(only with a design skill; any equivalent works — update the reference in `myapp-design/SKILL.md`)*.
- Optional: `autoContinueAtUsageLimit` for attended sessions, and `PILOT_NOTIFY_URL` (a Discord or Slack webhook) to receive run reports.

---

## Install (fresh project)

```
/plugin marketplace add lalec/agent-plugins
/plugin install dev-workflow@agent-plugins
/dev-workflow:install
```

Run the last line from your project root. It stops if the project already has an install — use `/dev-workflow:upgrade` then. You answer three questions: your prefix, the domain skill → path mapping, and which packages your product can't run without (they get pinned). It ends with the open-advisories line and `Next: /audit`.

When a check needs a login or a key, the agent names the secret and where it goes — `srun add NAME` in your own terminal, or your password manager — so you never type a value into the chat. Install also offers to save your status line's usage figures so `/pilot` can see your allowance; it doesn't edit your own script, and one settings line undoes it.

---

## Upgrade (existing install)

```
/dev-workflow:upgrade
```

Shows every fix the latest templates would apply, waits for your yes, then applies only those. It names any script of yours that reads something it would remove. `--yes` applies everything and lists what needs your judgement afterwards.

With several projects open in their own sessions, run `/dev-workflow:rollout` once instead. It upgrades each idle session in its iTerm tab and leaves a running `/pilot` alone. `--restart` also updates Claude Code and relaunches each session; `--dry-run` shows what it would do. macOS and iTerm2 only.

---

## Daily workflow

### Implement a feature
```
/code <describe the feature>
```
Runs `myapp-dev` → `myapp-qa` → `myapp-pm`. It opens with the repo's state — uncommitted work, unpushed commits, unproven checks, and one line of open advisories. Then one gate tells you what *done* means and what will prove it; type to correct it, or say nothing to agree. A dev server it starts listens on `localhost` only and stops when the run ends.

### Fix a bug
```
/fix <describe the bug or regression>
```
Runs `myapp-debug` → `myapp-dev` → `myapp-qa` → `myapp-pm`.

### Run a whole batch autonomously
```
/pilot <goal — e.g. all open roadmap items, or improve an area until criteria pass>
```
It splits the goal into tasks, asks one gate up front (or none, when you typed the item ids), then works unattended. A decision a task needs is taken the way the run would recommend and reported, so one word overturns it; anything that can't be undone, spends beyond its grant or reaches real people is parked for you. Push and prod deploy happen once, at the close-out. It pauses between tasks before the 5-hour limit and sets one wake-up for the reset, rather than dying mid-task. `--max-tasks N` caps what you selected; `--unattended` skips the gate, so a loop over named items never waits on you. It ends with a mission report and, if it stopped short, a resume line.

Any command that declares how work reaches it becomes a lane `/pilot` can route to. A lane that spends credits runs against a budget you grant at the gate. A plan across repos runs each repo's half in its own session (`/pilot --items other-repo:umbrella-id`), and the sessions message each other when one side finishes what the other waits on.

```
/pilot --gates
```
Re-measures each open decision first: ones the evidence has killed close themselves, ones waiting on a trigger stay put, and the rest come back as one table with a recommendation per row, answered in one reply.

### Let it run while you're away
```
/loop 30m /pilot --max-tasks 1
```
`/pilot` with nothing after it is the **standing mission**: what `/whats-up` would say needs doing — a critical advisory first, then started work, then the backlog — asking nothing. It stops on:
- the **weekly budget** (`--budget`, default 30 points of your 7-day allowance, counted across every run);
- a stop file — `touch .claude/pilot/stop` ends it at the next task;
- three failed tasks in a row, or a nearly full disk;
- the **daily cap** on paid services your tests call (`PAID_DAILY_CAP` in `governed-paths.conf`, worked out at install).

Paths in `UNATTENDED_DENY` (deploy and auth by default) are never touched unattended, except version changes from an `/audit` upgrade item. Everything is held at UAT until you've seen it. Use a fixed interval: a self-paced loop has nothing to wake it after the usage limit refuses a turn.

To run toward a goal instead of a timer, use Claude Code's `/goal`: `/goal all high-priority roadmap items done or parked — each turn run /pilot --max-tasks 1 --unattended; stop when the report says runnable rows left: 0 or budget spent`. Every report ends with `runnable rows left:` and `budget:` lines for it to read.

A run holds the Mac awake while the session is open. To check in, run `/whats-up`, then `/pilot --gates`. For a schedule that survives a closed terminal, use the Desktop app: **Routines → New routine → Local**, this folder, `/pilot --max-tasks 1`, hourly; a bare `/loop 30m` reads `.claude/loop.md`. Agents run on Sonnet by default; an item `/blueprint` marked *hard*, or `--agents session`, runs on your session's model.

### Iterate on something small
```
/tweak <describe the visual/copy/hotfix round>
```
Inline-verified, no subagents. The close-out runs once at the end; the `close-out-gate` hook blocks `git push` until it has.

### Decide which vulnerabilities matter
```
/audit
/audit --scan
```
`/audit` tells you which findings an attacker can reach. Each gets one status, and `not exploitable` must name why: not shipped, not in the build, never called, not reachable by attacker input, or behind a control that can't be turned off. It takes each package whole, a few at a time, and saves each batch, so a run cut short keeps what it decided; `--max-packages 5` bounds it. Anything not reached is counted as undecided, never as clean. A container backend is scanned as its image, so the base image's packages count. Answers are kept until the package version moves.

An advisory with a published fix becomes an upgrade item `/pilot` can run; once a check stops finding it, it stops counting. Zero means nothing unjudged or unfiled; a flaw with no upstream fix is shown as its own count. A check that failed, or is over three days old, says so rather than reading as zero.

`--scan` runs the whole-repository scans in `scanners.yaml` once each is 90 days old. It asks the cost once before spending; an unattended run never starts it. Results from a scan you ran by hand are filed first. Critical, high and medium findings become one roadmap item each; low ones share one.

### Roll something back
```
/revert <commit or description of what to undo>
```
`git revert` (never reset), re-runs the affected checks, logs the reversal.

### Clean up a dirty working tree
```
/tidy
```
Checks history before judging each leftover — a file whose replacement already landed is *superseded*, not accidentally deleted. Proposes commit / deliver / discard / ignore / keep per item and applies it safely (`discard` becomes a named stash, `git branch -d` never `-D`). `/code`, `/fix` and `/pilot` send you here when leftovers overlap their paths.

### Design a UI feature *(if design skill installed)*
```
/design <describe the UI to design>
```
2–3 HTML variants, opened in the browser; your pick goes to `/code`. `myapp-design` first looks at how your app already does the same thing and matches it, or records why not. Icons come from your icon set or the asset skill, never drawn by hand. Copy uses your users' words, and a project list of internal terms keeps them off screens. Em dashes in new copy are flagged.

### Pick up where you left off
```
/whats-up
/whats-up consent
```
Reads every store that outlives a session — roadmap, unproven checks, unpushed commits, waiting decisions, the working tree — and says whether you're *blocked on a decision*, *carrying more than you're finishing*, or *clear*. Half-finished work gets its own row with how long it's been idle. A decision is put to you only if you can make it today. It ends with three commands to paste: *Next*, *All* (one `/pilot` mission), *Loop all*. A word after it filters to one feature or path. It changes nothing. Mid-session, use `/handover` then `/proceed` instead.

### Work the roadmap
```
/roadmap
/roadmap high priority --max-tasks 4
```
Ranks open items — milestone first, then started work, priority and dependency order — and hands the top set to `/pilot` or one item to `/code`/`/fix`.

### Plan something bigger than one task
```
/blueprint <goal that spans several tasks>
/blueprint <roadmap id that is only a name>
```
Plans on the strongest model, so the cheaper agents building it don't have to guess. It writes one umbrella item with the decisions made, plus child items each sized for one run — lane, dependencies, model, where it lands, what *done* means, and checks with expected values. Each value is tried against the code before it's written down. Decisions that are yours come to you once. Its only write is the roadmap; *Write and run* starts `/pilot --items <umbrella> --no-push` at once, or run `/code <first item>` to sit in on the first one. If the gate times out, `/blueprint <its id>` resumes it.

A migration also gets: how old and new coexist, the cutover order, a last item that walks a real user journey across the change, and a cleanup item with a trigger. A plan across repos keeps its umbrella in one repo and its steps in each repo's roadmap, linked as `other-repo:item-id`. It's `/blueprint` because Claude Code's `/plan` is plan mode. It runs on Fable; change its frontmatter if your account doesn't have it.

### Wrap up ad-hoc work
```
/wrap <description of what changed>
```
Close-out for changes made outside `/code`/`/fix`: runs `myapp-log`, `myapp-docs` and `myapp-skill` reference sync.

---

## What gets verified

You describe the outcome; the workflow derives the checks from one sentence of *done* and re-runs them against the live stack whenever they're relevant.

| | |
|---|---|
| **Who writes them** | The agents, from the stated outcome. You correct them at the gate. |
| **How they run** | Endpoint and datastore checks run in batches with short timeouts. A browser check is recorded on its first walk and replayed after; the agent still judges the screenshot. |
| **What always runs** | Smoke, this task's checks, and earlier checks on the same files. A passing check on untouched code is carried forward, and reported as carried, not fresh. |
| **How wide it goes** | Decided from what changed. Only you can ask for the whole suite (`--regression full`), and you see the price first. What the budget doesn't reach is recorded as unproven. |
| **What the build can change** | Nothing you'd notice only in prod. Packages your product can't run without are pinned; every build starts the app before it takes traffic. |
| **What costs money** | Paid-service tests run as a sample while building and in full only on the sign-off pass. At the daily cap, paid tests stop and the task waits for the next day. Install checks your cloud budget alerts reach a confirmed address. |
| **What it leaves alone** | Anything it didn't make. It deletes only records it created and stops only servers it started, by process id. |
| **When it can't run** | Recorded *blocked* with the reason — never a pass. |
| **Where it goes then** | Back for another fix if local could run it; walked after deploy if only prod can; deferred with its trigger if it waits on a job or webhook. |
| **What reopens** | Anything unproven resurfaces at the next `/code`, `/fix` or `/pilot`. A check that can never run again is *retired* with the reason. |

---

## What you get back

Every command that closes work ends with the same five blocks:

| Block | What it tells you |
|---|---|
| **Verdict** | One line: the state of the work, and whether it needs you. |
| **Learned** | Up to three bullets that change your picture, often none. |
| **Status** | One row per thing meant to happen, with one word: `needs you`, `failed`, `not done`, `not proven`, `done`, `proven`, `n/a`. |
| **Open** | Your inbox: what needs you now, each with the exact thing to run and the run's recommendation. Nothing open says `None`. |
| **Emerged** | Everything else the run found, ranked, each with where it now lives. |

Then one last line: the command to run next — usually one `/pilot` over every open item — or `none — nothing open, safe to start a fresh session`. Code written is `done`; a journey actually walked is `proven`.

---

## How the hooks enforce correctness

| Hook | Fires on | Blocks if |
|---|---|---|
| `skill-guard.sh` | Edit / Write | Editing an owned path without its skill loaded |
| `path-coverage-check.sh` | Write | A new file in a governed root with no owner |
| `dependency-guard.sh` | Bash | `pnpm add` / `pip install` without `myapp-skill` loaded |
| `package-edit-guard.sh` | Edit | Adding packages to `package.json` directly without `myapp-skill` |
| `pre-handoff-check.sh` | Skill + Task/Agent | Handing to `myapp-qa` with uncommitted changes or lint/type errors in the changed part; any dispatch after a stop file or at the paid cap |
| `paid-meter.sh` | Bash | A paid test once today's cap is reached or usage can't be read |
| `close-out-gate.sh` | Bash | `git push` before the close-out has logged governed or deploy changes (`CLOSEOUT_OVERRIDE=1` overrides) |
| `security-gate.sh` | Bash + Skill | `git push` or a prod deploy until every scanner and `/security-review` have read what ships and every new finding has a decision. A crash or timeout blocks. An unusual push command is checked rather than missed (`CLOSEOUT_OVERRIDE=1` works for a push only) |
| `ref-sync-check.sh` | Bash (post) | Warns after a commit that drifts from reference docs, `REF_WATCH` or `deploy-config.yaml`, or adds an em dash to user-facing copy |
| `skill-mark.sh` | Skill (post) | Records loaded skills for the guards and the delivery log |
| `post-commit.sh` | Bash (post) | Reminds to run `myapp-log` after a commit |
| `agent-mark.sh` | Subagent stop | Sends a pipeline agent back once to write its missing handoff |
| `pilot-cleanup.sh` | Session end | Clears only this session's `/pilot` marker |
| `precompact-handover.sh` | Before compaction | Holds compaction inside a `/pilot` task until its handover is written; otherwise writes a fallback handover |
| `pilot-continue.sh` | Turn end, after a compaction | Sends a stalled `/pilot` run on to its next step once, and points it back at its handover after a compaction |
| `limit-mark.sh` | API limit error | Records the moment the usage limit hit, so the next `/pilot` resumes the run |
| `scan-due.sh` | Session start | Never blocks — names a due security scan or a critical advisory, and starts the day's advisory check |
| srun `guard.py` | Bash, Read, Grep | Printing a `.env`, anything under `~/.aws` or `~/.ssh`, a password-manager entry or the environment; `grep -c` and `.env.example` stay allowed |
| srun `redact.py` | Any tool (post) | Never blocks — masks anything shaped like a credential (`sk-…`, `ghp_…`, AWS keys, JWTs) |

All path → skill ownership lives in `.claude/hooks/governed-paths.conf`; hooks pick up edits automatically.

---

## Verify the install

```bash
# 1. Skill gate — should block
# Edit a file in an owned path (e.g. src/) without loading its domain skill
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
| Add a new domain (new source dir) | Invoke `myapp-skill` — it owns `governed-paths.conf` |
| Change path → skill ownership | Edit `.claude/hooks/governed-paths.conf` |
| Add a reference file to a skill | Invoke the domain skill — it manages its own `references/` |
| Update `docs/workflow.md` | Invoke `myapp-docs` |
