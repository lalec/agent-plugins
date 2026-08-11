# dev-workflow — rollout findings

Open changes discovered while rolling the delivery graph (Stage 0+1) across real installs.
Each item: what, the evidence, and what has to be decided. Delete an entry when it ships.

**Delete this file when the rollout closes.** Templates are done and rolled out; what remains is
listed under **Next**. Everything below is transitional.

---

## Where we are (handover, 2026-08-10)

**Plugin:** `lalec/agent-plugins`, `plugins/dev-workflow/`. Everything pushed.

> ⚠️ **Templates changed after the last rollout — all four projects are now behind.** The salvage
> SendMessage/re-spawn split and the Notion silent-skip both touch `tpl-commands.md` /
> `tpl-agents.md`, with matching upgrade-checklist items and apply bullets. **Each project needs
> `/dev-workflow:upgrade` run in its own repo** (the command resolves `.claude` against cwd, so it
> cannot be driven from here). Until then the byte-current table below describes the *previous*
> state, not the current one.

**All four projects are byte-current at `dd86bfe`** — verified, not assumed:

```
              graph.py  TRANSCRIPT=  dev1.5  log-closed  paths  marker-caveat  pilot(lane/ledger/parked)
tosk-web        ok          0          1         1        2/2         1              2/1/1
tosk-agent      ok          0          1         1        2/2         1              2/1/1
jobzeeker       ok          0          1         1        2/2         1              2/1/1
portrais        ok          0          1         1        2/2         1              2/1/1
```

Project-side commits: tosk-web `67d29cf` · tosk-agent `2a1aabc` (1 unpushed) · jobzeeker `f9d7c3d` ·
portrais `f9e3482`. **Only portrais declares `pilot-lane:` lanes** (`run-check` free, `tune`
metered:generations); the other three have the registry but nothing to discover.

**Validated by real runs:**

| Change | Evidence |
|---|---|
| Session-scoped markers `8b3766b` | tosk-agent `d677c16d` + tosk-web `b9129d3f` — single-id markers holding subagent-only skills |
| Behavioral-surface `paths` `e4a8470` | tosk-web + tosk-agent verifications scoped to real source only, no docs/`.claude` |
| `/pilot` lanes + ledger + parked verdicts `65593aa` | portrais mission: `budget=generations:10 (user)`, 7 spent, `leg-2=skipped … (pilot-auto)`, `keep/adopt=parked (human-gated)` |
| Deferral path | tosk-agent recorded a real `UAT-deferred:` with `status: blocked` in `last:` |
| 6-point acceptance | **tosk-agent 6/6** (`2c56aa7`) and **tosk-web 6/6** (`24ace96`, incl. a QA-blocked retest cycle) |

**Cost baseline — measured, not estimated.** tosk-web's `/fix` (session `b9129d3f`, two QA rounds,
window cut at `2026-08-09T22:04Z`) cost **$21.56**:

| Component | Model | Output | Cache read | Cache write | Cost | Share |
|---|---|---:|---:|---:|---:|---:|
| top-level `/fix` | opus-5 | 52.4k | 5.0M | 412k (1h) | $7.96 | 37% |
| dev | opus-5 | 59.0k | 7.2M | 278k (5m) | $6.81 | 32% |
| qa (retest) | opus-5 | 44.9k | 4.9M | 135k (5m) | $4.43 | 21% |
| qa (initial) | opus-5 | 29.0k | 1.2M | 82k (5m) | $1.85 | 9% |
| pm | sonnet-5 | 10.2k | 1.1M | 77k (5m) | $0.51 | 2% |

Reading it: **cache traffic is most of the bill** — 44% cache read + 34% cache write = **78%**,
against 22% generation and 89 fresh input tokens. The QA-blocked **retest cost 2.4× the initial pass**
($4.43 vs $1.85) because it inherited a larger context, so a second QA round is worse than double on
that half. `model: sonnet` on pm is doing real work at $0.51. **No single component dominates** — the
top level is 37% and the three subagent roles are 63% between them, so there is no one place to
attack. Cost scales with the pipeline being a pipeline, which is the design working as intended.

**Method (repeatable) — two traps, both of which bit.** Read
`~/.claude/projects/<encoded>/<session>.jsonl` plus `<session>/subagents/agent-*.jsonl`, price per
`message.model` (opus-5 $5/$25; sonnet-5 at $2/$10 intro through 2026-08-31), cache read at 0.1×,
cache write at 1.25× (5m) / 2.0× (1h) split by `cache_creation.ephemeral_5m/1h_input_tokens`.
`.meta.json` next to each subagent transcript names its `agentType`. Then:

1. **Rows are per *content block*, not per request** — collapse on `message.id` first. Input-side
   fields (`input_tokens`, `cache_read_input_tokens`, `cache_creation`) are identical on every row of
   a message, so any row is authoritative. **`output_tokens` is not** — it is a running partial, and
   only the final row (the one carrying `stop_reason`) holds the true total. Take `max()`. Keeping
   the *first* row instead undercounts output ~10× on subagent transcripts (dev: 6.3k vs the real
   59k) and is invisible, because the input-side numbers stay correct and the total still looks
   plausible. The top-level transcript happens to have uniform rows, so a spot-check there confirms
   nothing about the subagent files.
2. **A session file accumulates every resume** — `b9129d3f` had a 9.2h gap and then unrelated
   next-day work appended to it, and it was still being written to *during* this analysis. Costing
   the whole file answers "what has this session cost in total", not "what did one run cost". Cut the
   window at the run boundary.

Working script: `plugins/dev-workflow/session-cost.py` (maintainer tool at the plugin root —
deliberately *not* in `shared/`, which is install-artifact territory). It handles both traps and
warns on long idle gaps; `--until <iso>` cuts the window.

**Do not treat tosk-agent `d677c16d` as a second baseline.** It spans three work windows across two
days ($24.22 for the whole file), so it is "a day of work on that repo", not one `/fix`. There is
currently **one** clean single-run measurement, not two.

**The 1-hour cache TTL question is settled: leave it alone.** Claude Code gates 1h caching behind a
server-side allowlist defaulting to `["repl_main_thread*", "sdk", "auto_mode", "memdir_relevance"]` —
main thread only, which is exactly what the transcripts show (top level 1h, every subagent 5m). That
default matches the workload: on the clean run window the top level's request gaps are median 18s but
**p90 498s, with 6 of 45 over five minutes**, because it sits idle waiting on subagents — while the
subagents run rapid-fire and never need more than 5m. Forcing everything to 5m via
`FORCE_PROMPT_CACHING_5M=1` (the real env var; there is no settings.json key) saves the 0.75× write
premium but forces a full prefix re-write at every one of those gaps, and the re-writes cost more
than the premium saved: **−$1.22 on the run (−6%)**. The knob only makes it worse. It would only pay
off for a top level with no gaps over 5 minutes, which a pipeline that dispatches subagents does not
have. Note 1h caching also auto-disables while the org is in usage overage, so a run measured during
overage will show 5m writes on the top level and is not comparable.

**Landmines:**

- **Never `rm -rf .claude/graph/` in a user project.** Doing this during regression testing deleted
  tosk-web's installed `graph.py`. Because every call site falls back silently, nothing reported it.
- **Fix the plugin, never hand-patch an installed project** — two tosk-web workarounds had to be
  undone once the real parser bugs were fixed upstream.
- **Propagation:** commit → push → `/dev-workflow:upgrade` in the project. Editing the plugin
  templates from this repo and applying them to projects with a scripted, asserted replacement
  (dry-run first, one assert per edit) worked well for a 15-edit wave across four projects.
- **Transcript rows are per-content-block, and session files span resumes.** Both traps inflated the
  first cost baseline ($47.24 for what was really a $21.56 run). Collapse on `message.id` — taking
  `max()` on `output_tokens`, since that field is a running partial — and cut the window at the run
  boundary before summing. Applies to any transcript-derived metric, not just cost; see the Method
  note above for why a spot-check on the top-level file does not catch it.
- **Markers prove a *skill* ran, never a *command*.** `skill-mark.sh` fires on the Skill tool, so a
  user-typed slash command can leave no trace. Reading `pilot`'s absence as "no mission ran" was
  wrong once already — use the delivery log's `**Decisions:**` and `git log` instead.
- **Sibling repos share a `<PREFIX>`.** `ls -t /tmp/tosk-skills-* | head -1` crosses tosk-web and
  tosk-agent. Always scope by session id.
- **Concurrent sessions are normal in these repos.** Re-read state immediately before acting, and
  never run a build or upgrade in a repo another session is holding.
- **`~/.claude/projects/**` is readable again — the user disabled the secretrun plugin (2026-08-10),
  no session restart needed.** This reverses an earlier landmine and is what made the cost analysis
  possible. It is conditional: if secretrun is re-enabled, transcripts go dark again and anything
  built on them must degrade gracefully.
- Per-project work needs a session **in that repo** — `/dev-workflow:upgrade` resolves `.claude`
  against cwd, and `/code`/`/fix` are project-local commands.

Test beds: **tosk-web** · **tosk-agent** · **portrais** · **jobzeeker**.

---

## Open — needs a decision

*(none — all five original decisions settled in `8b3766b`; see below)*

---

## Decided, not yet built

- **Stage 2 — `/pilot` mission graph.** Lives at `.claude/pilot/mission.json`, marked `EXEMPT` in
  PATH_MAP, written directly by `/pilot`. **No new lifecycle skill.** Deliberately *not* under
  `.claude/graph/` and never called a graph — the delivery graph is derived and disposable, mission
  state is authoritative and unrebuildable, and one skill cannot state a coherent invariant over
  both. This is also why `<PREFIX>-graph` keeps its name: with mission state elsewhere there is no
  collision.
- **Stage 3 — findings + hotspots: dropped, not deferred.** Redundant with skills + Reference Sync,
  which already does the job better: semantic rather than statistical, injected at point of use and
  enforced by `skill-guard.sh`, and aggregated per-domain (~5 buckets) where data is dense rather
  than per-file (326 paths, half touched exactly once). Raw touch-frequency ranking is dominated by
  `docs/roadmap.md` and reference docs, so it would need normalization before it said anything true.

---

## Untested

- **The parked-agent fix (`ed6f7ba`)** — the one shipped change with no live evidence. Nothing has
  parked since it landed, which is the good outcome but not proof. Both halves must hold together:
  the agent-side foreground-wait rule *and* the widened salvage trigger (any non-`## Handoff` return).
- **`/pilot` lane registry on a project other than portrais** — the other three have the registry
  but declare no lanes, so discovery has never run against a second shape.
- **`open-deferrals` at `/code`/`/fix` Step 0** — tosk-agent now has a real open deferral
  (`execute-valid-registers-and-completes-task`), so the next `/code`/`/fix` there finally exercises it.
- **A project with no `python3`** — the documented fallback path has never actually been hit.

---

## Fixed — do not re-litigate

| Fix | Commit |
|---|---|
| Roadmap parser read only `- **Field:**` list form → reads bare, list and packed (`MULTI_FIELD_RE`) | `bd082f7` |
| Status whitelist hid `closed`/`reopened`/`removed` → terminal blacklist + leading-token extraction | `bd082f7` |
| Log entries with an empty hash region silently dropped (2 in tosk-web) | `1888b44` |
| `Skills:` from parent-transcript grep — 27–64% recall, blocked by secretrun → session-scoped marker union | `bc7c672`, `1888b44` |
| Marker union scoped by mtime → cross-contaminated sibling repos sharing a `<PREFIX>` (tosk-web/tosk-agent) | `1888b44` |
| `graph.py` installed untracked → silently deleted, and mandatory fallbacks hid its absence | `4f5a780` |
| Multi-hash (`` `a` + `b` ``) and missing-`HH:MM` log headings unparsed | `1888b44` |
| `build --append` removed — full rebuild is <1s and append leaked deleted verifications | `763d217` |
| Hooks claimed per-agent marker scoping they never had → keyed on `${SESSION_ID}` alone, claim corrected | `8b3766b` |
| Parser read `### ` headings inside ``` fences → fenced format examples became phantom roadmap items | `8b3766b` |
| Roadmap metadata form undefined → dev matches the file's existing convention, never reformats | `8b3766b` |
| Log field set open-ended → declared closed; `Follow-ups:`-style invented fields routed to roadmap / `UAT-deferred:` | `8b3766b` |
| `Deployed:` absent on a `ship=prod` run — **not a bug**; tosk-web declares no `envs.prod` and has no CI, so nothing deployed | n/a |
| Headless roadmap items (metadata with no `### ` heading) silently absorbed by the item above → build warns | `0adea66` |
| A subagent backgrounding a long deploy watch parked the pipeline **silently** — the completion routes to the parent, and salvage only triggered on a *dead* agent → foreground-wait rule + salvage on any non-`## Handoff` return | `ed6f7ba` |
| `/pilot` lanes frozen at pipeline/tweak, spend caps chat-granted with nothing tracking them, human-gated verdicts auto-decided or dropped → `pilot-lane:` frontmatter registry + granted resource ledger + parked-verdict contract | `65593aa` |
| Markers read as proof a command ran — `skill-mark.sh` only sees Skill-tool invocations, so a user-typed slash command can leave no trace (misled a real `/pilot` audit) → caveat in `<PREFIX>-log` step 3 | `dd86bfe` |
| Two upgrade entries still told installs to key markers **per agent**, and the apply bullet's skip condition was inverted (skipped exactly when the bug was present) — leftovers from `8b3766b` | `dd86bfe` |
| `paths` reduction was a flat `.claude/**` exclusion — let docs-only paths drive prior-selection and dropped executable source under `.claude/skills/**/scripts/**` → behavioral-surface rule (upstreamed from jobzeeker) | `e4a8470` |
| Cost baseline summed raw transcript rows across every resume in the file — usage repeats per content block, and the file spanned unrelated next-day work → $47.24 for "one `/fix`" was really **$21.56**; collapse on `message.id` (max on `output_tokens`) and cut the window | this pass |
| Pipeline was diff-shaped end to end — the gate synthesized verification candidates from the change, so dev built to the diff, qa verified the assertions it was handed, and a feature shipped with its control wired and the journey dead-ending → **acceptance statement**: end state in the user's terms, written first, candidates derived as clauses of it with a mandatory end-state check, carried into both agent prompts, walked by dev before complete and by qa before sign-off | this pass |
| The one check that proves a journey could be deferred like any other (`signed-off-with-deferrals`), and repeat deferrals were report-only — one missing test environment blocked five checks across three deploys, each run noting it and moving on → end-state deferrals route by declared project fact, and 3+ deferrals on one **fixable** blocker asks to fix it first | this pass |
| First cut of that rule blocked *any* unwalked end state — which would have failed every task on a prod-only component (tosk-agent) and anything cron-triggered (jobzeeker). Corrected before rollout: read `deploy-config.yaml` and route — non-prod env exists → block; prod-only → post-deploy prod walk at top level; out-of-band trigger → deferral with trigger + observable + where to look. Structural facts are counted, never nagged about | this pass |
| `last: pass` was undefined for a check that ran but never exercised its assertion — a vacuous observation (no refresh was due, no gate open) looks identical to a clean pass, and a pass **permanently discharges** the deferral → `pass` now means exercised-and-held; an absence is `blocked` with the reason. Found on a real jobzeeker read-out where 3 of 7 deferrals were vacuous | this pass |
| Salvage protocol treated SendMessage and re-spawn as equivalent — but SendMessage to a completed agent **always resumes detached**, so the retry leg (QA blocks → dev fixes) silently left the foreground contract and the immediate return was indistinguishable from a parked agent → mechanism split + "never infer state from the resume call" | this pass |
| Notion mirror sub-steps read as "attempt and report" — dev and pm both emitted "Notion page NOT created" on a project with no Notion MCP, ending every delivery with a phantom manual-sync note → silent-skip, absence is not a finding | this pass |
| 1-hour cache TTL flagged as "the largest single cost lever" — it is not a lever; forcing 5m costs **more** (−$1.22, −6%) because the top level idles past 5m waiting on subagents (p90 498s, 6/45 gaps) | this pass |

**Verified on real data:** parse coverage N/N on all four corpora · prior-selection parity against an
independently written parser · byte-identical rebuilds · zero edges without `src` · roadmap-open
matching ground truth 55/55, 105/105, 75/75, 59/59 · prior-selection cost 11,757 → 81 tokens ·
`8b3766b`'s fence fix drops exactly one phantom on tosk-agent (82→81) and leaves tosk-web, portrais
and jobzeeker byte-identical (edge counts and parse coverage unchanged on all three).

### How the five decisions were settled (`8b3766b`)

1. **Marker agent-scoping claim was false — confirmed, claim corrected.** All 12 `/tmp/*-skills-*`
   markers on the dev machine have *identical* session and agent halves, including sessions that ran
   `/code`, `/fix` and `/pilot` with subagents. `basename(transcript_path)` returns the session id,
   so the `AGENT` suffix was provably always a duplicate. Fixed by keying all four scripts on
   `${SESSION_ID}` alone and replacing the comment with the truth: the gate **is** session-wide, and
   that is required — `<PREFIX>-log` derives `**Skills:**` from the same marker, and only session
   scope sees `<PREFIX>-review` / `<PREFIX>-debug`, which load exclusively inside subagents.
   Old doubled-name markers still match the log skill's glob, so no cleanup is needed.
2. **Roadmap form drift.** Parser already read all three forms; the *writers* were unconstrained.
   `<PREFIX>-dev` step 1.5 now says match the file's existing convention and never reformat existing
   items; the install stub documents that all three forms are read; the upgrade skill is barred from
   proposing a reformat (the `**Id:**` backfill remains its only sanctioned roadmap edit).
3. **`Follow-ups:` — dropped, not adopted.** tosk-web's instance restated a roadmap item the same
   task had just created, so the field duplicated tracked scope rather than recording anything new.
   The log's field set is now explicitly **closed**, with leftover scope routed to `docs/roadmap.md`
   and unrunnable verifications to `**UAT-deferred:**`. Applied to the `<PREFIX>-log` template, the
   `docs/workflow.md` template and the upgrade checklist together, per repo CLAUDE.md.
4. **`Deployed:` on a `ship=prod` run — no gap.** tosk-web's `deploy-config.yaml` states that neither
   component declares `envs.prod`, so `target: prod` is a no-op and `--prod` finishes at UAT; the repo
   has no CI workflows at all. `ship=prod (user)` with no `**Deployed:**` line is the honest record.
   No template change. (Worth revisiting only once a project actually wires push-fires-prod CI.)
5. **Install stub's literal example item — root cause was the parser.** The current stub ships no
   literal `### [category] Title`; tosk-agent's phantom came from a **fenced** format example in its
   roadmap header, which `parse_roadmap` read as a real item. Fixed generally with `strip_fences()`,
   applied to `parse_roadmap`, `parse_log` and the build's heading count (that last one matters —
   counting unstripped text would have raised a permanent false `WARNING`). Any project documenting
   its own format in a fence is now safe, not just this one.

---

## Next

What remains, in order:

0. **Roll the salvage + Notion template fixes to all four projects** — `/dev-workflow:upgrade` in
   each repo (tosk-web, tosk-agent, jobzeeker, portrais). Both are checklist items with apply
   bullets; nothing else changed. This supersedes the "templates and rollout are done" state above.
1. **Exercise the parked-agent fix** — the only unvalidated shipped change. It needs a run where a
   deploy or suite genuinely outlasts a turn. Can't be forced cheaply; watch for it on the next slow
   deploy rather than engineering a repro.
2. **Declare a `pilot-lane:` on a second project** — proves the registry against a shape other than
   portrais'. jobzeeker is the natural candidate (it has genuinely distinct command types).
3. **Then Stage 2 (`/pilot` mission graph) — but re-justify it first.** It is still *decided, not
   built* (below), and the evidence has moved against it: portrais ran an overnight `/pilot` and a
   lane mission without losing state, and the real failure we hit was the parked agent, not lost
   mission state. Build it when a run actually loses its place, not before.

**Cost work is done for now** — the baseline is corrected and reproducible (`session-cost.py`), and
the one open cost question (1h TTL) is settled against changing anything. Nothing about token usage
currently looks broken: no runaway component, no single dominant cost, 78% cache traffic which is
what a pipeline that re-reads context each turn is supposed to look like. If cost is revisited, the
honest framing is that **$21.56 buys a full design → implement → review → test → sign-off → log
cycle**, and the question is whether that is worth it per task, not which component to shave. The one
structural lever is reducing how much context each role re-reads per turn — a context-design
question, not a caching-config one, and not worth opening until something else forces it.

**Housekeeping:** tosk-agent has 1 unpushed commit. jobzeeker and portrais have had live sessions
throughout — re-read their state before touching either.
