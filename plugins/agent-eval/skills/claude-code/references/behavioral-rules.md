# Behavioral Rules Reference

Rules, thresholds, and detection logic used by `transcript-parser.py`. There is no config file — every per-agent expectation is discovered at runtime from `.claude/agents/*.md` (see `discovery.py`).

---

## Discovery (per-agent)

`discovery.discover_project(cwd)` reads each `.claude/agents/*.md` and returns:

| Field | How it's discovered |
|---|---|
| `name` | YAML frontmatter `name`; falls back to filename stem |
| `has_handoff` | True if the body contains a `**Status:** <values>` line or `RESULT: <value>` line |
| `handoff_patterns` | Per-agent regex(es) built from the captured Status values — each agent's actual format is matched, not a global pattern |
| `artifact_paths` | Resolved from `<prefix>-log` skill cross-references (read from the skill's SKILL.md), plus explicit `Output: PATH` / `Writes to: PATH` / `Delivers: PATH` / `Artifact: PATH` lines |
| `artifact_header_pattern` | From the first heading-shaped template line in the log skill's SKILL.md — a markdown heading containing placeholder syntax (`YYYY`, `<angle>`, `{curly}`). Its heading level becomes the H3 regex (e.g. `### YYYY-MM-DD …` → `^#{3}\s+`). `None` when no template found → H3 SKIPs |
| `downstreams` | "spawn X", "invoke X", "delegate to X", "hand off to X", "tell user to invoke X" |
| `upstreams` | "Invoked after X" / "after X completes" in the description |
| `role` | Suffix `-dev` → producer, `-qa` → reviewer, `-pm` → terminal, `-log` → writer; otherwise inferred from Status values |
| `dag_shape` | `sequential` if no agent has ≥2 forward downstreams to declared agents (back-references for failure-routing don't count); else `branching` |

When discovery is empty (no `.claude/agents/`), G1/G2/G4 SKIP cleanly.

---

## Project-Type Detection (informational only)

`detect_project_type(cwd)` scans CWD (`package.json`/`*.ts` → `web`, `Dockerfile` → `docker`, `requirements.txt`/`*.py` → `python`) and reports the result in the JSON. **No checks depend on it** — H1's patterns are suspect in any project type and H3 is gated on discovery, not stack.

---

## H1: Suspect Path Access

**Check:** Bash or Read tool calls touching paths that are suspect in any project type. Reading application source is **not** flagged — in dev/QA pipelines that is the agents' job.

**Patterns** (always active):
- `(^|/)node_modules/` — dependency tree (wasted context)
- `\.claude/projects/` — other sessions' transcripts (snooping / context pollution)

**Trigger:** WARN on any match.

---

## H2: Shell Loop Usage

**Check:** Bash tool calls containing `for ... do`, `while ... do`, or `until ... do`.

**Detection pattern:** `\b(for|while|until)\b.*\bdo\b` (DOTALL).

**Trigger:** INFO always — shell loops are legitimate in generic workflows; the count is reported for visibility, never as a violation.

---

## H3: Output Artifact Format

**Check:** Write tool calls to a discovered artifact path where the content lacks the header discovered from the log skill's template (see `artifact_header_pattern` above).

**Gating:** runs only when discovery found a header template for at least one evaluated agent; SKIPs otherwise. There is no hardcoded default header.

H3 only inspects `Write` calls — `Edit` modifies existing files, where the header is presumed already correct.

---

## H4: Repeated Identical Tool Calls

**Check:** Same `(tool_name, input)` pair invoked more than once **within a single mutation-free span** of one agent. Any `Edit`/`Write` resets the span: the workspace changed, so re-running an identical command afterwards (edit → test → edit → test loops) is legitimate iterate/verify behavior, not a duplicate.

**Hash:** `(name, json.dumps(input, sort_keys=True))`. Different inputs → different hash → not a duplicate.

**Trigger:** WARN if any agent repeats a signature with no intervening Edit/Write. Detail names the worst offender (`tool ×N`).

Always enabled. The signal: an agent forgot it already made the call and nothing changed in between — pure wasted work.

---

## H5: File Re-Read Without Edit

**Check:** Same `file_path` Read ≥3× within an agent with no intervening `Edit` or `Write` to that path.

**Detection:** Per-agent counter `read_count_for_path[path]` increments on each `Read` and resets to 0 on any `Edit`/`Write` to that path. Crossing 3 emits a violation (once per cycle — won't refire on Read 4, 5, 6 unless an Edit resets).

**Difference from H4:** H4 requires identical `Read` inputs (same offset/limit). H5 ignores offset/limit — re-reading different chunks of the same file three times is still cache thrash if no Edit happened. H5 is the more permissive signal.

**Trigger:** WARN if any violation. Detail lists the affected agent labels.

Always enabled.

---

## Cost Model

`MODEL_RATES` in `transcript-parser.py` — substring-matched against each agent's model from the JSONL `message.model` field (per-MTok):

| Key | Input | Output | Cache read | Cache write 5m (1.25×) | Cache write 1h (2×) |
|---|---|---|---|---|---|
| `fable`  | $10.00 | $50.00 | $1.00 | $12.50 | $20.00 |
| `opus`   | $5.00  | $25.00 | $0.50 | $6.25  | $10.00 |
| `sonnet` | $3.00  | $15.00 | $0.30 | $3.75  | $6.00  |
| `haiku`  | $1.00  |  $5.00 | $0.10 | $1.25  | $2.00  |

Cache writes are priced per TTL from the JSONL `cache_creation` breakdown (`ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`). The legacy `cache_creation_input_tokens` total duplicates that breakdown and is used only when the breakdown is absent — adding both would double-count.

Each agent's cost is computed from its actual model — mixed-model pipelines are reported correctly. Unknown models fall back to Sonnet rates and are listed in the top-level `notes`.

Refresh manually when models change.

---

## Token Reporting

Three distinct totals — pick the right one for the right question:

| Field | Definition | Use for |
|---|---|---|
| `peak_context_tokens` (per agent) | Max `input + output + cache_read + cache_write` of any single turn | "How big is the agent's working set?" — cache-creation tokens are part of the turn's window (a first turn that writes 100k to cache held those tokens), so they count |
| `total_peak_context_tokens` (summary) | Sum of each agent's `peak_context_tokens` | Headline volume metric for the workflow |
| `billed_tokens` / `total_billed_tokens` | Sum of `input + output + cache_read + cache_write` across **every turn** | Cost basis only — `cache_read` is re-billed each turn, so this inflates with turn count |

**Why peak instead of summed billing for the headline:** a 20-turn agent with 100k cached context shows up as ~2M billed tokens but only ever held 100k in its window. Summing billing as the "token count" punishes long agents that are actually efficient (high cache hit ratio = cheap).

`output_tokens` is also tracked separately — it's the only token type that's purely "new work" (not re-bill of cached prompt).

---

## Efficiency Thresholds (F-checks)

| Check | Trigger |
|---|---|
| F1: Turn outliers (>2× median) | WARN if any agent's turns > 2× median across the run. Only fires with ≥4 evaluable agents (median is unstable below). |
| F4: Context outliers (>2× median peak) | WARN if any agent's `peak_context_tokens` > 2× median. Needs ≥2 agents. Pivoted from billed tokens — long, well-cached agents shouldn't be flagged for being long. |
| F5: Duration spread | WARN if max/min duration > 5×. |
| F6: Cache hit ratio | WARN if any multi-turn agent (≥3 turns, ≥50k input+cache_read) has `cache_hit_ratio < 0.30`. Skips agents below the volume floor (caching has no opportunity to pay off in 1–2 short turns). Reports the workflow's weighted-average ratio across all qualifying agents. |
| F7: Model right-sizing | WARN if any agent with `role ∈ {terminal, writer}` runs on Opus or Fable. Roles come from discovery (suffix `-pm` → terminal, `-log` → writer). SKIPs when no roles were inferred. Reviewer/producer on a big model is fine — those agents need the reasoning. |
| F8: Tool churn ratio | WARN if any agent with ≥10 tool calls has `total_tool_calls / distinct_tools > 10`. Catches "stuck on one tool" patterns (e.g. 30 Bash calls with one distinct tool used). Threshold tuned high to avoid flagging legitimate multi-edit producer work (a 12-Read/10-Edit producer naturally hits ~7×). |
| F9: Time-to-first-tool | WARN if any agent waits >60s between its first user record and first `tool_use`. SKIPs when no timestamp pairs are available. Adaptive-thinking models legitimately reason for tens of seconds on hard tasks before acting — the threshold flags stuck reasoning, not normal thinking. |
| F10: Empty (no-tool) turns | WARN if any agent with ≥5 turns has both >30% empty turns *and* ≥3 empty turns. A turn is "empty" if the assistant produced text blocks but invoked zero tools across that requestId. One trailing text-only turn (the final return) is normal — the floor and ratio together suppress that false positive. |

F3 (cost per artifact) and G3 (failure-status rate) are informational. G3 matches the *discovered* status vocabulary against failure tokens (`block|fail|retry|error|abort`, case-insensitive) and reports the full status distribution — nothing project-specific is hardcoded.

F1/F2 (turn utilization, budget exhaustion) are removed — `.claude/agents/*.md` rarely declares per-agent budgets, so the metric was almost always SKIP.

---

## Reliability Logic (G-checks)

| Check | Gating | Trigger |
|---|---|---|
| G1: Silent failures | Skip when no agent declares an artifact path | FAIL if any artifact-declaring agent didn't `Edit`/`Write` a matching path |
| G2: Result completeness | Skip when no agent declares a handoff format | WARN if any handoff-declaring agent's final assistant text has no parseable Status |
| G4: Unknown outcomes | Skip when neither is declared | FAIL if a declaring agent produced neither Status nor artifact |
| G5: Handoff content lineage | Skip if <2 agents have both `last_text` and `first_user_prompt` | INFO only — reports `with_lineage / total_transitions`. Tokens checked: file paths (regex `[\w./-]+\.[a-zA-Z]{1,6}`), backticked identifiers (length ≥3), `**Status:** <value>` lines. Tokens shorter than 4 chars stripped to suppress noise. Transitions are the consecutive pairs after sorting by spawn timestamp. |

Artifact path matching is suffix-based: `docs/project-log.md` matches both the bare path and any absolute path ending in `/docs/project-log.md`.

G5 is intentionally INFO, not WARN: a "broken" transition often means the orchestrator legitimately re-prompted the next agent with a fresh task, but it can also mean the upstream's output was lost. The ratio is a diagnostic, not a verdict.

---

## Workflow Logic (W-checks)

### W1: Total Workflow Duration
Wall time from first timestamp of any agent to last timestamp of any agent. INFO only — used as denominator for W5.

### W2: Orchestrator Overhead
Computed from the parent JSONL (see `parent_session.py`): orchestrator billed tokens as a share of the workflow total (orchestrator + all agents), plus orchestrator cost from its actual model. INFO only — a heavy orchestrator isn't wrong per se, but a rising share across runs means work is drifting back to the top level.

### W3: Parallel Efficiency
Max concurrent agents (overlap in time windows) / total agents. WARN if < 30%. **Auto-downgraded to INFO when discovery infers `dag_shape == "sequential"`** — low concurrency is by design.

### W4: Sequential Bottlenecks
Counts agents whose time window overlaps with no other agent. WARN if > 50% of agents are purely serial. **Auto-downgraded to INFO when `dag_shape == "sequential"`**.

### W5: Idle Time
Total gaps where no agent was running / workflow wall time. WARN if > 20%.

### W7: Spawn-Order vs Declared DAG
Forward edges are derived from each agent's `upstreams` field — the result of `UPSTREAM_RE` matching "Invoked after X" / "after X completes" in the agent's frontmatter description. For each edge `A → B`, the first spawn timestamp of agent type A must be earlier than the first spawn of B. FAIL on any inversion.

**Why upstreams, not downstreams:** `downstreams` regex catches all call-site verbs ("invoke X", "spawn X", "delegate to X", "hand off to X"). It picks up failure-routing arrows (e.g. `qa.md` saying "delegate back to dev for fixes") which create a `qa → dev` edge that isn't a pipeline ordering — it's a fix-back loop. `upstreams` is anchored on declarative ordering language and is the only unambiguous "must run after" signal in the discovery model.

SKIP when no agent declares an upstream, or when neither endpoint of any declared edge was spawned in the session.

### W8: Spawn Decision Latency
For each agent's last transcript timestamp, the gap to the next `Agent`/`Task` `tool_use` in the parent session. Median and max reported as INFO — long gaps mean the orchestrator is deliberating (or doing work itself — cross-check O7) between handoffs. SKIP when no spawn follows any completion.

W6 (spawn pattern) is omitted — it needs `queue-operation` records that Claude Code's `Agent` tool doesn't write.
