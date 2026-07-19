# agent-eval

Evaluate Claude Code instruction-based agent pipelines. Parses JSONL transcripts from `~/.claude/projects/` — the subagent files and the parent (orchestrator) session — for runtime metrics, and reads `.claude/agents/`, `.claude/skills/`, `.claude/settings*.json` from the project under inspection for static and orchestration checks.

**Deterministic.** No model grading — thresholds applied to numeric metrics. Per-agent expectations (handoff format, artifact paths, artifact header template, pipeline shape) are discovered at runtime from `.claude/agents/*.md` and referenced log skills. No config file.

**Generic.** No workflow-specific assumptions: reading project source is never a violation, shell loops are informational, and identical commands re-run after an edit (iterate/verify loops) don't count as duplicates.

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

**Compare mode:** pass `--compare previous-run.json` to diff against a saved run — check-status regressions, metric deltas, per-agent-type deltas. Use it to catch regressions after changing agent configs, skills, or models.

## Checks (49 total)

| Group | Focus | Style |
|---|---|---|
| **F** Efficiency | Turn outliers, cache hit ratio, model right-sizing (Opus/Fable), tool churn, time-to-first-tool, empty turns | deterministic |
| **G** Reliability | Silent failures, result completeness, failure-status rate, unknown outcomes, handoff lineage | deterministic |
| **H** Behavioral | Suspect path access, shell loops (info), artifact format vs discovered template, repeated tool calls (mutation-aware), file re-reads | deterministic |
| **W** Workflow | Wall time, orchestrator overhead, parallel efficiency, sequential bottlenecks, idle time, spawn-order vs declared DAG, spawn decision latency | deterministic |
| **S** Spec conformance | Agent / skill / hook frontmatter against [Claude Code docs](https://code.claude.com/docs/en/) | static lint |
| **O** Orchestration | Tool grants right-sized, skill preload alignment, description quality, prompt size, destructive-skill safety, top-level role absorption | heuristic |

Cost is computed per agent from its actual model (Fable/Opus/Sonnet/Haiku rates), with cache writes priced by TTL (5-minute vs 1-hour).

## Output

JSON to stdout (DAG shape, discovered agents, check results, orchestrator metrics, per-agent metrics, summary, optional comparison). Save to a file and Claude writes the markdown report `{output-file}-agent-eval.md`.

See [SKILL.md](skills/claude-code/SKILL.md) for the full procedure, output format, and rule reference. `references/spec-conformance.md` is version-stamped against Claude Code doc URLs; `references/behavioral-rules.md` documents H/W thresholds; `references/orchestration-rules.md` documents O thresholds and rationale.

## Family

Sibling skills for non-Claude-Code runtimes (currently user-scope, may join this plugin later):

- `agent-eval-sdk` — Python `claude-agent-sdk` apps (`query()` / `ClaudeSDKClient`)
- `agent-eval-agentcore` — SDK apps deployed on AWS Bedrock AgentCore Runtime (sources metrics from CloudWatch + X-Ray)
