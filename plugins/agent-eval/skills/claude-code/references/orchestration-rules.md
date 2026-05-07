# Orchestration Efficiency Rules (Group O)

Heuristic checks that cross-reference declared frontmatter (`.claude/agents/*.md` and `.claude/skills/*/SKILL.md`) against actual transcript behavior. The S group asks "is the frontmatter syntactically valid?" — the O group asks "is the frontmatter being used optimally for this workload?"

**Heuristic, not deterministic.** False-positive rate is higher than the other groups. Each detail line includes raw counts so the reader can verify findings fast.

**Doc snapshot version:** 2026-05-07

---

## O2: Tool grants right-sized

**Source:** sub-agents → "Available tools" — "By default, subagents inherit all tools from the main conversation, including MCP tools. To restrict tools, use either the `tools` field (allowlist) or the `disallowedTools` field (denylist)."

**Trigger:** Agent has **neither** `tools` nor `disallowedTools` set (inherits everything) AND the transcript shows ≤ 4 distinct tools across ≥ 10 tool calls.

**Why:** Inheriting all tools means every tool's description is in the agent's context budget. If the agent's actual workload only needs 3–4 tools, declaring `tools: <observed list>` shrinks startup context measurably.

**Threshold rationale:**
- 10-call floor: smaller samples don't tell us what the agent _would_ have used
- 4-tool ceiling: most legitimate multi-purpose agents use 5+ distinct tools (Read/Edit/Bash/Grep/Glob is already 5)

**Severity:** WARN.

---

## O3: Skill preload alignment

**Source:** sub-agents → "Preload skills into subagents" — "The full content of each skill is injected into the subagent's context at startup. … Subagents don't inherit skills from the parent conversation."

**Trigger:** Agent invoked `Skill X` mid-task (via the `Skill` tool), but `X` is not in the agent's frontmatter `skills:` field.

**Why:** Preloading skills the agent will need avoids late-load context churn. If the same skills are loaded mid-task across many sessions of the same agent, that's evidence they should be preloaded.

**Detection:** During per-agent JSONL parsing, every `tool_use` block with `name: "Skill"` contributes its `input.skill` to a `skills_invoked` set. The check compares that set against the declared `skills:` list (parsed from frontmatter — accepts both YAML list and space/comma-separated string).

**Severity:** INFO. Late skill loading is sometimes intentional (the skill is rarely needed); preloading isn't always the right answer.

---

## O4: Description quality

**Source:** sub-agents → "Understand automatic delegation" — "Claude automatically delegates tasks based on the task description in your request, the `description` field in subagent configurations, and current context. To encourage proactive delegation, include phrases like 'use proactively' in your subagent's description field."

**Trigger:**
- `description` length < 40 characters, OR
- `description` contains no delegation trigger phrase

**Trigger phrase regex (case-insensitive):**
```
\b(use\s+(?:when|proactively|for|to|after|immediately|whenever)|
  invoked?\s+(?:when|after|for|to)|
  call\s+(?:when|for)|
  trigger(?:s|ed)?\s+(?:when|on))\b
```

**Why:** The auto-delegation classifier reads each subagent's description. Short or vague descriptions ("Reviews code") give Claude little to match against, so the agent is rarely auto-invoked. Concrete trigger phrases ("Use proactively after writing or modifying code") align with how the docs encourage description writing.

**Severity:** WARN.

---

## O5: Orchestrator prompt size

**Source:** sub-agents → "Each subagent runs in its own context window" + the docs' broader emphasis on subagents existing to _preserve_ orchestrator context.

**Trigger:** Any agent's first user record (the orchestrator's handoff prompt) exceeds 5,000 characters.

**Why:** The whole point of a subagent is to do work in a separate window so the orchestrator doesn't carry the cost. If the orchestrator is sending the subagent 10K+ chars of context, two things are wrong: (1) the orchestrator is paying that token cost on every spawn, and (2) the subagent is starting from a saturated window. Distill the handoff to the actual task + the smallest necessary context.

**Threshold rationale:** 5,000 chars is roughly 1,000–1,500 tokens — generous enough that legitimate task descriptions with file paths and structured instructions fit comfortably, tight enough to flag dumps.

**Severity:** WARN.

---

## O6: Destructive skill safety

**Source:** skills → "Control who invokes a skill" — "`disable-model-invocation: true`: Only you can invoke the skill. Use this for workflows with side effects or that you want to control timing, like `/commit`, `/deploy`, or `/send-slack-message`. You don't want Claude deciding to deploy because your code looks ready."

**Trigger:** Skill's `description` (or `when_to_use`) matches any destructive verb pattern AND `disable-model-invocation` is not `true`.

**Destructive verb regex (case-insensitive):**
```
\b(deploy|commit|push|delete|migrate|release|drop|truncate|reset|publish)\w*\b
```

The trailing `\w*` catches conjugations: `deployed`, `commits`, `migrating`, etc.

**Why:** A skill that deploys or commits is a side-effect action. Without `disable-model-invocation: true`, Claude can fire it autonomously when it _thinks_ the codebase is ready — which is exactly what the docs warn against.

**Severity:** WARN.

---

## Maintenance

When tuning thresholds:
- O2: lower the `O2_DISTINCT_TOOL_CEILING` if you want narrower flagging; raise the `O2_MIN_TOTAL_CALLS` floor if small-sample noise becomes a problem
- O5: bump `O5_PROMPT_CHAR_THRESHOLD` if your project legitimately uses long structured handoffs

When adding destructive verbs (O6): edit `DESTRUCTIVE_VERB_RE` in `scripts/orchestration_checks.py`. Match against project conventions — e.g. if your project uses `flush` or `wipe` for destructive operations, add them.

To add new O-checks: same pattern as the existing five — a `_check_oN(...)` helper that returns one or more check dicts via the `_check()` builder, registered in `run_orchestration_checks()`. Group field is always `"orchestration"`.
