# dev-workflow — rollout findings

Open changes discovered while rolling the delivery graph (Stage 0+1) across real installs.
Each item: what, the evidence, and what has to be decided. Delete an entry when it ships.

**Delete this file when the rollout closes** — i.e. once all four projects are on the current
templates and have passed the 6-point acceptance test. All four are upgraded as of 2026-08-06; the
acceptance runs are what remain. Everything below is transitional.

---

## Where we are (handover, 2026-08-05 23:35)

**What shipped.** The delivery graph: `shared/graph.py` (a derived, disposable typed-edge index over
`docs/project-log.md`, `docs/roadmap.md`, `custom-tests.yaml`, `governed-paths.conf`,
`deploy-config.yaml` and `git log`), an 8th lifecycle skill `<PREFIX>-graph`, three new fields
(roadmap `**Id:**`, log `**Addresses:**` / `**Decisions:**`, `custom-tests.yaml` `last:`), and seven
read/write call sites. Design rationale: `~/.claude/plans/please-research-how-we-refactored-summit.md`.

**Plugin repo:** `lalec/agent-plugins`, `plugins/dev-workflow/`. Everything pushed; nothing local-only.

**Rollout status:**

| Project | Upgrade | Post-upgrade `/fix` | Graph build |
|---|---|---|---|
| tosk-web | current at `dd86bfe` (`67d29cf`) | ✅ `0c9169a` — 6/6, but on pre-`8b3766b` templates | 157/157, no warnings |
| tosk-agent | current at `dd86bfe` (`2a1aabc`) | not yet run | 93/93, no warnings |
| jobzeeker | current at `dd86bfe` (`f9d7c3d`) | not yet run | 228/228, no warnings |
| portrais | current at `dd86bfe` (`f9e3482`) | not yet run | 208/208, no warnings |

**All four verified byte-current** against the plugin on 2026-08-09:
`graph.py` identical, zero `TRANSCRIPT=` in hooks, dev 1.5 convention rule, closed log field set,
behavioral-surface `paths` in both `code.md` and `fix.md`, graph artifacts ignored (verified with
`git check-ignore`, not a grep — jobzeeker's repo-wide `__pycache__/` rule covers it and a literal
grep false-reports a gap), build N/N with no warnings.

**Template rollout is done; only the acceptance runs remain.** Every project's newest log entry
predates its upgrade, which is why those entries show no `Addresses:`/`Decisions:` and list agent
names under `Skills:` — old derivation, not a regression. tosk-web's 6/6 pass was on pre-`8b3766b`
templates, so it needs a re-run too: the session-scoped markers and behavioral-surface `paths` have
never been exercised by a real pipeline anywhere.

**Acceptance test per project** — run one `/fix` (better than `/code`: it also exercises the
`<PREFIX>-debug` → `history` read site) and check:

1. `**Skills:**` contains `<PREFIX>-log` — the marker-union derivation ran
2. `**Skills:**` contains `<PREFIX>-review` — subagent skills were captured
3. `**Addresses:**` carries a real roadmap `**Id:**`, or pm's `Notes:` explains no match
4. `**Decisions:**` present, any timeout recorded as `(timeout)` not `(user)`
5. `custom-tests.yaml` gained a `last:` block for each verification that ran
6. `graph.py build` reports `N/N log entries parsed`, no `WARNING`

**Landmines:**

- **Never `rm -rf .claude/graph/` in a user project.** Doing this during regression testing deleted
  tosk-web's installed `graph.py`. Because every call site falls back silently, nothing reported it.
- **Fix the plugin, never hand-patch an installed project** — two tosk-web workarounds had to be
  undone once the real parser bugs were fixed upstream.
- **Propagation:** commit → push → the plugin cache updates → `/dev-workflow:upgrade` in the project.
  A push alone does not reach a project; a local edit without a push reaches nothing.
- `~/.claude/projects/**` is blocked by the secretrun guard — transcripts and memory are unreadable
  from Bash. Don't design anything that depends on reading them.
- **Sibling sessions run concurrently in these repos.** On 2026-08-05 ~23:30, tosk-agent, portrais
  and jobzeeker all had live sessions (dirty trees, HEADs moving mid-analysis). Re-read state
  immediately before acting on it, and never run a build or an upgrade in a repo another session
  is holding.
- The plugin work is safe to do from the `agent-plugins` session; the per-project work is not.
  `/dev-workflow:upgrade` resolves `.claude` relative to cwd and `/fix` is a project-local command —
  neither can be driven from another repo's session.

Test beds: **tosk-web** · **tosk-agent** · **portrais** · **jobzeeker**.

---

## Open — needs a decision

*(none — all five open decisions were settled in `8b3766b`; see below)*

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

- **`open-deferrals` at `/code`/`/fix` Step 0** — tosk-web's run produced no deferrals. Exercises
  itself the first time a verification can't run in any environment.
- **`/pilot` against the graph** — no autonomous run yet.
- **A project with no `python3`** — the documented fallback path has never actually been hit.
- **Behavioral-surface `paths` (`e4a8470`)** — no pipeline has captured a verification since it
  shipped, so the reduction has never actually run.

**Now validated:** the session-scoped marker rename (`8b3766b`) — tosk-agent `/fix`, session
`d677c16d`, wrote a single-id marker (`/tmp/tosk-skills-d677c16d-…f75`, not doubled) containing
`tosk-debug · tosk-backend · tosk-test · tosk-deploy` — all loaded **inside** the `tosk-dev`
subagent. Subagent skills reach the parent-session marker exactly as the `Skills:` derivation needs.

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

**All four projects on current templates** (portrais user-driven). Only the acceptance runs remain.

1. One `/fix` per project against the 6-point test — none has run on post-`8b3766b` templates, so
   the session-scoped markers and behavioral-surface `paths` are still unexercised in a real
   pipeline. tosk-web included: its 6/6 pass predates them.
2. Push where pending, and run `/plugin update` in each session first.

**tosk-web / tosk-agent leftovers (not mine, left dirty):** tosk-web has `docs/roadmap.md` modified;
tosk-agent has `.claude/skills/tosk-stats/references/rates.json` modified. Neither relates to the
upgrade; both deliberately excluded from the upgrade commits.
