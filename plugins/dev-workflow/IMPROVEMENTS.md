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
| tosk-web | done, pushed | ✅ `0c9169a` — **6/6 acceptance pass** | 156/156, no warnings |
| jobzeeker | done (`b14cbe6`), unpushed | not yet run | 216/216, no warnings |
| portrais | done (`3e41b58`), unpushed | not yet run | 189/189, no warnings |
| tosk-agent | done (`07d8dd1`), unpushed — incl. all of `8b3766b` | not yet run | 93/93, no warnings |

jobzeeker and portrais were further along than the previous handover recorded. Their newest log
entries *predate* their upgrade commits, which is why those entries show no `Addresses:`/`Decisions:`
and list agent names under `Skills:` — old derivation, not a regression. Both still need one
post-upgrade `/fix` before the acceptance test means anything.

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
- **The session-scoped marker rename (`8b3766b`)** — verified by construction and against 12 real
  markers, but no pipeline has yet run with the rewritten hooks. First `/fix` after upgrade proves
  it: acceptance points 1 and 2.

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

**All four projects are now upgraded.** What remains is verification and propagation.

1. **jobzeeker, portrais, tosk-agent** — one `/fix` each against the 6-point test; push the pending
   upgrade commit. tosk-agent's is `07d8dd1`.
2. **jobzeeker, portrais** — re-run `/dev-workflow:upgrade` to pick up `8b3766b` (they were upgraded
   before it landed: their hooks still carry the per-agent `AGENT` suffix, `graph.py` predates the
   fence fix, dev step 1.5 lacks the convention rule, and the log field set is not declared closed).
3. **tosk-web** — same: re-run `/dev-workflow:upgrade` for `8b3766b`, then confirm acceptance
   points 1–2 still pass with the rewritten hooks.
4. Run `/plugin update` first in each session — the marketplace clone was at `bd082f7` as of
   2026-08-05 23:00 and does not yet have `4f5a780`, `8b3766b` or later.

**portrais roadmap hygiene (`b162aeb`) — checked, no interference.** It gave `### ` headings + `**Id:**`
to two *headless* items (metadata with no heading) and added two new ones: 82 → 86 items, all ids
unique, and a full cross-check of parsed status against the literal `**Status:**` line matched on
89/89 items, so none of the long `**Updated: …**` prose lines shadow a real field. Both recovered
items read `done · 2026-08-06`, which is a later legitimate flip, not a parse artifact. Net effect is
recovery: two items that were invisible to `roadmap-open` and uncitable by `**Addresses:**` are now
both. This is what motivated `0adea66`.

**tosk-agent leftover:** `docs/plan-vpc-deployment.md` is still untracked, and the roadmap item
`agentcore-vpc-networking-deferred-design-in` (added by the pre-upgrade session) points at it. Commit
the plan doc or the reference dangles. Deliberately left out of the upgrade commit — unrelated scope.
