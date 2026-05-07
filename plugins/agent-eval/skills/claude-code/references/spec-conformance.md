# Spec Conformance Reference (Group S)

Static-conformance rules for the S-group. Each rule is anchored to a specific section of the Claude Code documentation. When the docs change, update the rule sets in `scripts/static_checks.py` and refresh the version stamp below.

**Doc snapshot version:** 2026-05-07
**Sources:**
- Sub-agents: https://code.claude.com/docs/en/sub-agents
- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks
- Slash commands (SDK; same principles apply to non-SDK commands): https://code.claude.com/docs/en/agent-sdk/slash-commands

---

## Subagents (S1–S6)

Source: sub-agents `Supported frontmatter fields` table.

### S1: Required fields
- **Rule:** `name` and `description` are both required (table says "Yes" in Required column)
- **Quote:** "Only `name` and `description` are required."
- **Trigger:** FAIL if either is missing

### S2: Name format
- **Rule:** "Unique identifier using lowercase letters and hyphens"
- **Regex enforced:** `^[a-z][a-z0-9-]*$`
- **Trigger:** FAIL on any non-matching name

### S3: Name matches filename
- **Rule:** Best practice — Claude Code uses both filename and `name` field. Mismatches lead to confusion when agents are referenced.
- **Trigger:** WARN if `name` field ≠ filename stem

### S4: Model value
- **Rule:** `model` accepts `sonnet`, `opus`, `haiku`, full model ID (e.g. `claude-opus-4-7`), or `inherit`
- **Quote:** "Use one of the available aliases: sonnet, opus, or haiku" / "Use a full model ID such as claude-opus-4-7"
- **Trigger:** WARN if value doesn't start with `sonnet`/`opus`/`haiku`/`inherit`/`claude-`

### S5: Enum-typed fields
- **Rules:**
  - `permissionMode`: `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`
  - `memory`: `user`, `project`, `local`
  - `color`: `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`
  - `effort`: `low`, `medium`, `high`, `xhigh`, `max`
  - `isolation`: `worktree`
- **Trigger:** FAIL on any out-of-range value

### S6: Name uniqueness
- **Rule:** Names are unique identifiers — duplicates would shadow each other unpredictably (per the priority table, higher-scope wins)
- **Trigger:** FAIL on duplicate names within `.claude/agents/`

---

## Skills (S7–S11)

Source: skills `Frontmatter reference` table.

### S7: Name format
- **Rule:** "Lowercase letters, numbers, and hyphens only (max 64 characters)"
- **Regex enforced:** `^[a-z][a-z0-9-]*$`, length ≤ 64
- **Note:** Applies whether the `name` field is present or inferred from the directory name
- **Trigger:** FAIL on non-matching name

### S8: Dir matches name
- **Rule:** "If omitted, uses the directory name"
- **Inferred best practice:** When `name` is set, it should match the directory name to avoid confusion
- **Trigger:** WARN on mismatch

### S9: Description length
- **Rule:** "the combined `description` and `when_to_use` text is truncated at 1,536 characters in the skill listing"
- **Trigger:** WARN if combined length > 1,536

### S10: Body size
- **Rule:** Tip in docs — "Keep SKILL.md under 500 lines. Move detailed reference material to separate files."
- **Trigger:** INFO if body exceeds 500 lines (soft limit, not enforced by Claude Code)

### S11: Name uniqueness
- **Rule:** When skills share the same name across levels, enterprise > personal > project. Within the project level, duplicates are still ambiguous.
- **Trigger:** FAIL on duplicate names within the project's `.claude/skills/`

---

## Hooks (S12–S14)

Source: hooks doc — full event list and handler structure.

### S12: Event names
- **Rule:** Top-level keys under `hooks` must be one of the 29 documented events:
  ```
  SessionStart, Setup, UserPromptSubmit, UserPromptExpansion,
  PreToolUse, PermissionRequest, PermissionDenied, PostToolUse,
  PostToolUseFailure, PostToolBatch, Notification, SubagentStart,
  SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure,
  TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged,
  FileChanged, WorktreeCreate, WorktreeRemove, PreCompact,
  PostCompact, Elicitation, ElicitationResult, SessionEnd
  ```
- **Trigger:** FAIL on any unknown event (Claude Code silently ignores unknown events, so this is a critical lint)

### S13: Handler types
- **Rule:** `type` must be one of `command`, `http`, `mcp_tool`, `prompt`, `agent`
- **Trigger:** FAIL on any other value

### S14: Handler shape
- **Rules:**
  - `type: command` — `command` field must be a string, not an array. Quote: "Must be string. The `command` field must be a quoted string, not an array."
  - `type: http` — `url` field is required and must be a string
  - `if` field — must be a single permission rule. Quote: "There is no `&&`, `||`, or list syntax for combining rules; to apply multiple conditions, define a separate hook handler for each."
- **Trigger:** FAIL on any shape violation

---

## Cross-cutting (S15)

### S15: Spawned agents declared
- **Rule:** Agent types observed in transcripts (`agent_type` from `meta.json`) should be declared in `.claude/agents/` so the project's pipeline is self-documenting and discovery can apply runtime checks (G1, G2, G4, W7) to them.
- **Allowlist:** Built-in agents from the docs (sub-agents → Built-in subagents): `Explore`, `Plan`, `general-purpose`, `statusline-setup`, `claude-code-guide`. Update this set when Claude Code adds new built-ins.
- **Trigger:** WARN if any non-built-in agent is undeclared. PASS otherwise.

---

## Skill enum fields (S16)

### S16: Skill context/shell/effort/model
- **Source:** skills → `Frontmatter reference` table
- **Rules:**
  - `context`: only `fork` is documented
  - `shell`: `bash` (default) or `powershell`
  - `effort`: `low`, `medium`, `high`, `xhigh`, `max`
  - `model`: same as agents — `sonnet`/`opus`/`haiku`/`inherit` or full `claude-*` ID
- **Why this is a separate check from S5:** S5 covers agent enum fields. The skill spec uses different fields (`context`, `shell`) that don't apply to agents and weren't validated until S16. The `SKILL_VALID_CONTEXT` and `SKILL_VALID_SHELL` constants existed in `static_checks.py` for several iterations before being wired up — S16 closes that gap.
- **Trigger:** FAIL on any out-of-range value

---

## Tool reference shape (S17)

### S17: tools / disallowedTools / allowed-tools
- **Source:** sub-agents → `Available tools` (agent fields); skills → `Pre-approve tools for a skill` (`allowed-tools` field)
- **Frontmatter accepts:** YAML list, comma-separated string, or space-separated string. Tokenizer respects parens so `Bash(git push *)` and `Agent(worker, researcher)` (commas inside parens) are not split.
- **Validation regex:** `^(?:[A-Z][A-Za-z0-9]*(?:\(.*\))?|mcp__[a-zA-Z][\w-]*__[\w.*-]+)$`
  - Standard Claude Code tool: PascalCase name with optional args. Examples: `Read`, `Bash`, `NotebookEdit`, `Bash(git push *)`, `Agent(worker)`
  - MCP tool: `mcp__<server>__<tool>` with optional wildcard suffix. Examples: `mcp__memory__store_data`, `mcp__memory__.*`
- **What it catches:**
  - Lowercase typos: `read` instead of `Read`
  - Missed commas that swallow the next token: `Bash git Read` (splits to `Bash`, `git`, `Read`; `git` fails the regex)
  - Empty tokens from trailing commas
  - Malformed MCP forms: `mcp__bad` (missing tool name segment)
- **Severity:** WARN — Claude Code may silently ignore malformed entries, so this is a quality-of-life check rather than a runtime crash
- **Why we don't maintain a tool allowlist:** the Claude Code tool list grows over time and isn't centrally enumerated in the docs. Shape validation catches typos without becoming brittle on every release.

---

## Maintenance

When the Claude Code docs change:
1. Update the constant sets at the top of `scripts/static_checks.py` (`AGENT_VALID_*`, `HOOK_VALID_EVENTS`, etc.)
2. Update this file's "Doc snapshot version" stamp
3. If new fields are documented, decide whether to add a new S-check or extend an existing one (S5 covers all enum-typed agent fields; S14 covers all hook handler shape rules)
4. Run the negative-test suite by constructing a fixture in `/tmp/` with deliberate violations of each rule and confirming the corresponding check FAILs
