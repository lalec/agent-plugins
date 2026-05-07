# agent-eval

Evaluate Claude Code instruction-based agent pipelines. Parses JSONL transcripts from `~/.claude/projects/` for runtime metrics and reads `.claude/agents/`, `.claude/skills/`, `.claude/settings*.json` from the project under inspection for static and orchestration checks.

**Deterministic.** No model grading — thresholds applied to numeric metrics. Per-agent expectations (handoff format, artifact paths, pipeline shape) are discovered at runtime from `.claude/agents/*.md`. No config file.

## Install

```
/plugin marketplace add lalec/agent-plugins
/plugin install agent-eval@agent-plugins
/reload-plugins
```

## Use

```
/agent-eval:claude-code <session-id> <target-name>
```

Or just ask: *"evaluate the last agent run"* / *"audit my dev-workflow pipeline"* — the skill auto-triggers on those phrasings.

`<session-id>` is the parent session UUID (find with `ls -lt ~/.claude/projects/{project-slug}/*.jsonl | head -10`). `<target-name>` is a free-text label for the report.

## Checks (46 total)

| Group | Focus | Style |
|---|---|---|
| **F** Efficiency | Turn outliers, cache hit ratio, model right-sizing, tool churn, time-to-first-tool, empty turns | deterministic |
| **G** Reliability | Silent failures, result completeness, retry rate, unknown outcomes, handoff lineage | deterministic |
| **H** Behavioral | Source-code reading, shell loops, artifact format, repeated tool calls, file re-reads | deterministic |
| **W** Workflow | Wall time, parallel efficiency, sequential bottlenecks, idle time, spawn-order vs declared DAG | deterministic |
| **S** Spec conformance | Agent / skill / hook frontmatter against [Claude Code docs](https://code.claude.com/docs/en/) | static lint |
| **O** Orchestration | Tool grants right-sized, skill preload alignment, description quality, prompt size, destructive-skill safety | heuristic |

## Output

JSON to stdout (DAG shape, discovered agents, check results, per-agent metrics, summary). Save to a file and Claude writes the markdown report `{output-file}-agent-eval.md`.

See [SKILL.md](skills/claude-code/SKILL.md) for the full procedure, output format, and rule reference. `references/spec-conformance.md` is version-stamped against Claude Code doc URLs; `references/behavioral-rules.md` documents H/W thresholds; `references/orchestration-rules.md` documents O thresholds and rationale.

## Family

Sibling skills for non-Claude-Code runtimes (currently user-scope, may join this plugin later):

- `agent-eval-sdk` — Python `claude-agent-sdk` apps (`query()` / `ClaudeSDKClient`)
- `agent-eval-agentcore` — SDK apps deployed on AWS Bedrock AgentCore Runtime (sources metrics from CloudWatch + X-Ray)
