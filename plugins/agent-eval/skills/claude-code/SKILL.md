---
name: claude-code
description: Use when evaluating agent process quality and workflow efficiency for Claude Code instruction-based agent pipelines — projects that define agents in .claude/agents/*.md and spawn them via Claude Code's Agent tool. Identifies inefficient agents, behavioral violations, silent failures, and cost hotspots. Use this skill whenever asked to evaluate, audit, or benchmark a Claude Code markdown-driven agent workflow, even if the user doesn't say "agent-eval:claude-code" explicitly.
---

# agent-eval:claude-code

## Overview

Evaluates **agent process quality, workflow efficiency, Claude Code spec conformance, and orchestration efficiency** for instruction-based agent pipelines. Parses JSONL transcripts from `~/.claude/projects/` for runtime metrics, and reads `.claude/agents/`, `.claude/skills/`, `.claude/settings*.json` from CWD for static and orchestration checks. Applies **46 checks** across 6 groups (deterministic for F/G/H/W/S; heuristic for O).

**No model grading.** All checks are deterministic — thresholds applied to numeric metrics.

**No config.** Per-agent expectations (handoff format, artifact paths, pipeline shape) are discovered at runtime from `.claude/agents/*.md`. Per-agent cost is computed from each spawn's actual model recorded in the JSONL transcript. There is no `agent-eval.json` — if one exists in the project, it is ignored.

**Claude Code native.** Agent types come from `agent-{id}.meta.json` written by the runtime at spawn time.

**W2/W6 omitted.** They require `queue-operation` records that Claude Code's `Agent` tool never writes. Permanently removed — not SKIP noise.

---

## Step 1: Run transcript-parser

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/claude-code/scripts/transcript-parser.py \
  <session-id> <target-name> [--output-dir DIR] [--scan]
```

**Arguments**
- `<session-id>`: parent session UUID. If not known, list sessions sorted by date and ask which to evaluate (`ls -lt ~/.claude/projects/{project-slug}/*.jsonl | head -10`). Do NOT default to the current conversation session.
- `<target-name>`: free-text label for the run (used in the output report; no logic depends on it).
- `--scan`: if the given session has no agents, scan sibling sessions in `~/.claude/projects/{project-dir}/` and switch to the first one containing agent JSONL files.

**Project slug:** the directory under `~/.claude/projects/` is your CWD with `/` replaced by `-`. Example: `/Users/me/proj/foo` → `-Users-me-proj-foo`.

**Output:** JSON to stdout:
- `dag_shape` — `sequential` / `branching` / `unknown`
- `discovered_agent_names` — agents found in `.claude/agents/`
- `notes` — top-level warnings (undeclared agents, unknown models)
- `checks` — 46 check results (id, group, name, status, value, detail). Groups: `efficiency` (F), `reliability` (G), `behavioral` (H), `workflow` (W), `spec` (S — static conformance to Claude Code docs), `orchestration` (O — frontmatter usage vs actual transcript behavior)
- `agents` — per-agent metrics (peak_context_tokens, billed_tokens, cache_hit_ratio, role, tool_churn_ratio, time_to_first_tool_s, empty_turns, repeated_tool_calls, first_user_prompt, last_text, …)
- `summary` — aggregate counts (headline: `total_peak_context_tokens`; cost via `total_billed_tokens`)

Save output:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/claude-code/scripts/transcript-parser.py \
  <session-id> <target-name> > {output-file}.json
```

---

## Step 2: Discovery

Discovery reads `.claude/agents/*.md` from CWD. Per agent file:

| Discovered field | Source |
|---|---|
| `name` | YAML frontmatter `name`, fallback to filename stem |
| `has_handoff` | Body contains a `**Status:** <values>` line **or** `RESULT: <value>` line |
| `handoff_patterns` | Built from the captured Status values per agent (so each agent's actual format is checked) |
| `artifact_paths` | (1) Resolved from any `<prefix>-log` skill the agent invokes (read from `.claude/skills/<name>-log/SKILL.md` or `~/.claude/skills/<name>-log/SKILL.md`); (2) explicit `Output: PATH`, `Writes to: PATH`, `Delivers: PATH`, `Artifact: PATH` lines |
| `downstreams` | "spawn X", "invoke X", "delegate to X", "hand off to X", "tell user to invoke X" — references to other declared agent names |
| `upstreams` | "Invoked after X" / "after X completes" in the description |
| `role` | Suffix `-dev` → producer, `-qa` → reviewer, `-pm` → terminal, `-log` → writer; otherwise inferred from Status values |
| `dag_shape` (project-level) | `sequential` if no agent has ≥2 forward downstreams to declared agents (back-references for failure-routing don't count); else `branching` |

Discovery is conservative: when an agent's body doesn't unambiguously declare a handoff format or artifact path, the corresponding checks SKIP for that agent. Free-form returns are not flagged.

If `.claude/agents/` doesn't exist or is empty: discovery returns no agents. G1, G2, G4 SKIP for all agents; metric-only checks (F-, H-, W-) still run.

---

## Step 3: Review JSON, write eval report

For each check with `status == "FAIL"` or `status == "WARN"`, note the check ID, detail, and affected agents. Cross-reference the `agents` array for per-agent context.

For G1 (silent failure): verify the artifact actually exists on disk.

Write `{output-file}-agent-eval.md` using the format below.

---

## Auto-Detection

The parser scans CWD for project indicators:

| Indicator | Detected type | Effect |
|---|---|---|
| `package.json`, `*.js`, `*.ts` | `web` | H1 (source-code reading) and H3 (artifact format) activate |
| `Dockerfile` | `docker` | (no checks currently) |
| `requirements.txt`, `*.py` | `python` | (no checks currently) |

On non-web projects, H1 and H3 SKIP.

---

## Check Reference

### Group F: Efficiency

| ID | Name | Trigger |
|---|---|---|
| F1 | Turn outliers (>2× median) | WARN if any agent's turns > 2× median; only fires with ≥4 agents |
| F3 | Cost per output artifact | INFO |
| F4 | Context outliers (>2× median peak) | WARN if any agent's `peak_context_tokens` > 2× median |
| F5 | Duration spread | WARN if max/min > 5× |
| F6 | Cache hit ratio | WARN if any multi-turn agent (≥3 turns, ≥50k input+cache_read) reads <30% from cache |
| F7 | Model right-sizing | WARN if any terminal/writer-role agent runs on Opus |
| F8 | Tool churn ratio | WARN if any agent with ≥10 tool calls has `total_calls / distinct_tools` > 10 |
| F9 | Time-to-first-tool | WARN if any agent waits >30s between first user record and first tool_use |
| F10 | Empty (no-tool) turns | WARN if any agent with ≥5 turns has >30% (and ≥3) empty turns |

### Group G: Reliability

| ID | Name | Gating | Trigger |
|---|---|---|---|
| G1 | Silent failures | Skip when no agent declares an artifact path | FAIL if any artifact-declaring agent didn't Edit/Write a matching path |
| G2 | Result completeness | Skip when no agent declares a handoff format | WARN if any handoff-declaring agent's final message has no parseable Status |
| G3 | Retry rate | — | INFO |
| G4 | Unknown outcomes | Skip when no agent declares either | FAIL if a declaring agent produced neither Status nor artifact |
| G5 | Handoff content lineage | Skip if <2 agents | INFO — reports % of consecutive transitions where upstream's `last_text` tokens (file paths, Status values, backticked identifiers) appear in downstream's first user prompt |

### Group H: Behavioral Compliance

| ID | Name | Auto-detect | Trigger |
|---|---|---|---|
| H1 | Source code reading | Web projects | FAIL on any |
| H2 | Shell loop usage | Always | WARN on any |
| H3 | Output artifact format | Web projects | WARN on malformed artifact header |
| H4 | Repeated identical tool calls | Always | WARN on any duplicate `(tool, input)` pair within an agent |
| H5 | File re-read without edit | Always | WARN if any agent Reads the same `file_path` ≥3× without an intervening Edit/Write |

### Group W: Workflow Efficiency

| ID | Name | Trigger |
|---|---|---|
| W1 | Total workflow duration | INFO (wall time vs sum of agent durations) |
| W3 | Parallel efficiency | WARN < 30% concurrent — auto-downgraded to INFO when DAG is `sequential` |
| W4 | Sequential bottlenecks | WARN > 50% serial — auto-downgraded to INFO when DAG is `sequential` |
| W5 | Idle time | WARN > 20% of wall time |
| W7 | Spawn-order vs declared DAG | FAIL if any declared `upstream` agent (from "Invoked after X" in description) was first-spawned after the agent that declares it. SKIP if no upstream edges declared |

### Group S: Claude Code Spec Conformance

Static lint pass over `.claude/agents/`, `.claude/skills/`, `.claude/settings*.json`. Each rule is anchored to a documented spec — see `references/spec-conformance.md` for the version-stamped rule list with doc URLs.

| ID | Name | Trigger |
|---|---|---|
| S1 | Agent required fields | FAIL if any `.claude/agents/*.md` is missing `name` or `description` |
| S2 | Agent name format | FAIL if any agent `name` violates `[a-z][a-z0-9-]*` |
| S3 | Agent name matches filename | WARN if `name` field doesn't match the filename stem |
| S4 | Agent model value | WARN if `model` isn't `sonnet`/`opus`/`haiku`/`inherit` or a `claude-*` ID |
| S5 | Agent enum values | FAIL if `permissionMode`, `memory`, `color`, `effort`, or `isolation` use undocumented values |
| S6 | Agent name uniqueness | FAIL on duplicate names across `.claude/agents/` |
| S7 | Skill name format | FAIL if skill `name` (or directory name) violates `[a-z][a-z0-9-]*`, or exceeds 64 chars |
| S8 | Skill dir matches name | WARN if frontmatter `name` doesn't match the containing directory |
| S9 | Skill description length | WARN if `description` + `when_to_use` exceed 1,536 chars (will be truncated by Claude Code) |
| S10 | Skill body size | INFO if `SKILL.md` body exceeds 500 lines (docs recommend moving reference material to separate files) |
| S11 | Skill name uniqueness | FAIL on duplicate skill names |
| S12 | Hook event names | FAIL if any key under `hooks` isn't a documented event name |
| S13 | Hook handler types | FAIL if any handler `type` isn't `command`/`http`/`mcp_tool`/`prompt`/`agent` |
| S14 | Hook handler shape | FAIL if `type: command` has `command` as an array (must be string), or if `if` field uses `&&`/`\|\|` (must be a single rule) |
| S15 | Spawned agents declared | WARN if a non-built-in agent appeared in transcripts but isn't in `.claude/agents/`. Built-ins (`Explore`, `Plan`, `general-purpose`, `statusline-setup`, `claude-code-guide`) are exempted |
| S16 | Skill enum values | FAIL if any skill's `context`, `shell`, `effort`, or `model` uses an undocumented value. Mirrors S5 for skills |
| S17 | Tool reference shape | WARN if any entry in agent `tools` / `disallowedTools` or skill `allowed-tools` doesn't parse as a Claude Code tool — PascalCase name with optional parens (`Bash(git push *)`, `Agent(worker)`) or MCP form (`mcp__server__tool`, `mcp__server__.*`). Catches typos like `read` (lowercase) or missed commas (`Bash git` → splits to invalid `git`) |

### Group O: Orchestration Efficiency (heuristic)

Cross-references each agent's declared frontmatter against actual transcript behavior. Findings are heuristic — false-positive rate is higher than F/G/H/W/S. Each detail line includes raw counts so you can verify each finding fast. See `references/orchestration-rules.md` for thresholds and rationale.

| ID | Name | Trigger |
|---|---|---|
| O2 | Tool grants right-sized | WARN if agent has neither `tools` nor `disallowedTools` (inherits all) and used ≤4 distinct tools across ≥10 calls. Suggests declaring `tools: <observed list>` |
| O3 | Skill preload alignment | INFO if agent invoked a Skill mid-task that isn't in its `skills:` preload list. Preloading reduces mid-task context churn |
| O4 | Description quality | WARN if agent `description` is <40 chars or lacks a delegation trigger phrase (`use when/for/proactively`, `invoked when/after`, etc.) |
| O5 | Orchestrator prompt size | WARN if any agent's first user prompt exceeds 5,000 chars — orchestrator may be dumping unnecessary context |
| O6 | Destructive skill safety | WARN if a skill's description matches destructive verbs (`deploy`, `commit`, `push`, `delete`, `migrate`, `release`, `drop`, `truncate`, `reset`, `publish`) without `disable-model-invocation: true` |

---

## Edge cases

- **No `.claude/agents/` directory** — runs metric-only checks; G1/G2/G4 SKIP.
- **Agent has no `## Handoff` block and no declared artifact** — treated as free-form; not flagged.
- **Custom handoff header (e.g. `## Output` instead of `## Handoff`)** — fine. Discovery scans the whole body for `**Status:**` and `RESULT:` lines, not the header.
- **Agent spawned but not in `.claude/agents/`** — added to top-level `notes` ("agent X spawned but not declared"); doesn't crash. The agent's checks SKIP individually.
- **Mixed-model pipeline (one agent on Opus, others on Sonnet)** — per-agent cost reflects each agent's actual model. Unknown model strings fall back to Sonnet rates and are listed in `notes`.

---

## Output Format

```markdown
# Agent Eval: {target}

**Date:** {timestamp}
**Session:** {session-id}
**DAG:** {dag_shape}
**Agents evaluated:** {N}

## Summary

| Metric | Value |
|---|---|
| Total context tokens (peak, sum across agents) | {total_peak_context_tokens} |
| Token breakdown | input: X · output: Y · cache_r: Z · cache_w: W |
| Workflow cache hit ratio | {workflow_cache_hit_ratio} |
| Total billed tokens (cost basis) | {total_billed_tokens} |
| Total cost | ${cost} |
| Result statuses | {status_counts} |

**Headline = peak context, not billed tokens.** `total_peak_context_tokens` sums each agent's largest single-turn context — matches what Claude Code shows in agent returns ("35.2k tokens"). `total_billed_tokens` re-counts cached context per turn and is only useful as the cost basis.

## Check Results

### F: Efficiency
| Check | Status | Value | Detail |
|---|---|---|---|
| F1 | {status} | {value} | {detail} |
...

### G: Reliability
...

### H: Behavioral Compliance
...

### W: Workflow Efficiency
...

## Per-Agent Detail

| Agent | Type | Role | Model | Peak context | Cache hit | Cost | Turns | Result | Wrote artifact |
|---|---|---|---|---|---|---|---|---|---|
| {label} | {type} | {role} | {model} | {peak_context_tokens} | {cache_hit_ratio} | ${cost} | {turns} | {result} | {yes/no} |
...

## Flagged Agents

### {agent} — {description}

**Type:** {agent_type}
**Role:** {role}
**Model:** {model}
**Peak context:** {peak_context_tokens} | **Billed:** {billed_tokens} (input: X, output: Y, cache_r: Z, cache_w: W)
**Cache hit ratio:** {cache_hit_ratio}
**Cost:** ${cost}
**Turns:** {turns}
**Result:** {result_status}
**Wrote artifact:** {yes/no} ({matched paths})
**Violations:**
- H1: {detail}

## Recommendations

1. {Specific actionable fix for each FAIL/WARN}
```

---

## References

- `scripts/transcript-parser.py` — entry point; reads JSONL transcripts and runs checks
- `scripts/discovery.py` — reads `.claude/agents/*.md` and infers per-agent metadata + DAG shape
- `scripts/static_checks.py` — S-group static conformance checks against Claude Code docs
- `scripts/orchestration_checks.py` — O-group heuristic checks (frontmatter usage vs actual behavior)
- `references/behavioral-rules.md` — violation patterns, thresholds, W-check logic
- `references/spec-conformance.md` — S-group rules anchored to Claude Code doc URLs (with version stamp)
- `references/orchestration-rules.md` — O-group thresholds and rationale
