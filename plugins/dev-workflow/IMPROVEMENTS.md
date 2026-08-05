# dev-workflow — rollout findings

Open changes discovered while rolling the delivery graph (Stage 0+1) across real installs.
Each item: what, the evidence, and what has to be decided. Delete an entry when it ships.

---

## Where we are (handover, 2026-08-05)

**What shipped.** The delivery graph: `shared/graph.py` (a derived, disposable typed-edge index over
`docs/project-log.md`, `docs/roadmap.md`, `custom-tests.yaml`, `governed-paths.conf`,
`deploy-config.yaml` and `git log`), an 8th lifecycle skill `<PREFIX>-graph`, three new fields
(roadmap `**Id:**`, log `**Addresses:**` / `**Decisions:**`, `custom-tests.yaml` `last:`), and seven
read/write call sites. Design rationale: `~/.claude/plans/please-research-how-we-refactored-summit.md`.

**Plugin repo:** `lalec/agent-plugins`, `plugins/dev-workflow/`. Everything pushed; nothing local-only.

**Rollout status:**

| Project | State |
|---|---|
| tosk-web | Upgraded, `/fix` verified end to end, committed + pushed ✅ |
| jobzeeker | Upgrade in progress — 145 roadmap items, packed inline form |
| portrais | Not started |
| tosk-agent | Not started |

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

Test beds: **tosk-web** · **tosk-agent** · **portrais** · **jobzeeker**.

---

## Open — needs a decision

### 1. The agent-scoped marker claim is false

`skill-mark.sh` writes `/tmp/<PREFIX>-skills-${SESSION_ID}${AGENT}` where `AGENT` derives from
`transcript_path`. **Subagents share the parent's `transcript_path`**, so every agent writes to one
file and `AGENT` never differentiates.

**Evidence:** 7 markers on the dev machine across many pipeline runs — *zero* with differing
session/agent halves. tosk-web's `/fix` (session `4646b2e9`) produced exactly one marker containing
`tosk-review`, `tosk-test`, `tosk-backend`, `tosk-frontend`, `tosk-design` — all loaded inside the
dev/qa subagents.

**Consequence:** `tpl-skill-guard.md` asserts *"a skill loaded by one agent never satisfies another
agent's gate."* That is untrue — gates are session-wide. A skill dev loads satisfies qa's gate.
tosk-web's 2026-07-23 delivery log claims a prior upgrade fixed this; it did not take.

Cuts both ways: this is exactly *why* the `<PREFIX>-log` marker union captures subagent skills.
Tightening the gate would break the `Skills:` derivation unless both move together.

**Decide:** fix the derivation (needs a look at what `transcript_path` actually holds for a
subagent) **or** correct the claim in the templates. Asserting something untrue is the worst option.

### 2. Roadmap metadata form is undefined, so writers drift

Three forms exist in the wild and the parser now reads all of them: list (`- **Status:** open`),
bare (`**Status:** open`), and packed (`**Added:** … · **Owner:** … · **Status:** …`).

The **writers** don't say which to emit. tosk-web's upgrade agent reformatted 390 lines to list form
as a workaround for a parser bug — pure churn once the parser was fixed, and it left `tosk-dev` s1.5
and `tosk-test § Roadmap` diverged from the templates.

**Fix:** `<PREFIX>-dev` step 1.5 should say *match the file's existing convention* rather than
mandate a form, and the install stub should stop implying one. Also add to the upgrade skill: never
propose reformatting an existing roadmap.

Per-project: jobzeeker packs inline (145 items) → append `· **Id:** <slug>`, do not add a separate
`- **Id:**` line. tosk-agent is 100% bare. portrais and tosk-web are list form.

### 3. `**Follow-ups:**` — undocumented log field

tosk-web's `/fix` emitted a `**Follow-ups:**` line. Useful content; the projector ignores unknown
fields so nothing breaks. But per repo CLAUDE.md any log field must land in the `<PREFIX>-log`
template, the `docs/workflow.md` template, and the upgrade checklist **together**.

**Decide:** adopt it properly in all three, or fold the content into the body and drop the field.

### 4. `Deployed:` absent on a `ship=prod` run

tosk-web's entry recorded `**Decisions:** … ship=prod (user)` and pushed clean, but carried no
`**Deployed:**` line — while four earlier entries in the same log do. Either no prod deploy
happened, or it happened via CI-on-push and went unrecorded.

**Check:** if a CI-triggered prod deploy doesn't produce a `Deployed:` line, that's a template gap —
push-fires-prod is the normal shape on these projects.

### 5. Install stub ships a literal example roadmap item

`### [category] Title` appears as a real `### ` heading in installed roadmaps (seen in tosk-agent
and tosk-web), so `roadmap-open` counts it as an open item forever.

**Fix:** make the stub's example a comment, or have the parser skip a placeholder title. Cosmetic,
low priority, trivially fixed at install.

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

**Verified on real data:** parse coverage N/N on all four corpora · prior-selection parity against an
independently written parser · byte-identical rebuilds · zero edges without `src` · roadmap-open
matching ground truth 55/55, 105/105, 75/75, 59/59 · prior-selection cost 11,757 → 81 tokens.
