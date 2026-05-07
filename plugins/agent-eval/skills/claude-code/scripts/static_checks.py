#!/usr/bin/env python3
"""
agent-eval static conformance checks (group S).

Validates project files against Claude Code documented specs. All rules are
anchored to specific doc sections so future drift is traceable. Source URLs:

  - sub-agents:       https://code.claude.com/docs/en/sub-agents
  - skills:           https://code.claude.com/docs/en/skills
  - hooks:            https://code.claude.com/docs/en/hooks
  - slash-commands:   https://code.claude.com/docs/en/agent-sdk/slash-commands

Doc anchor: see references/spec-conformance.md for the version-stamped rule list.
"""

import json
import os
import re
import glob
from typing import Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


# ── Documented allowed values ────────────────────────────────────────────────

AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")  # docs: lowercase + numbers + hyphens

AGENT_VALID_MODELS_PREFIXES = ("sonnet", "opus", "haiku", "inherit", "claude-")
AGENT_VALID_PERMISSION_MODES = {
    "default", "acceptEdits", "auto", "dontAsk", "bypassPermissions", "plan",
}
AGENT_VALID_MEMORY = {"user", "project", "local"}
AGENT_VALID_COLORS = {
    "red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan",
}
EFFORT_VALID = {"low", "medium", "high", "xhigh", "max"}
AGENT_VALID_ISOLATION = {"worktree"}

SKILL_VALID_CONTEXT = {"fork"}
SKILL_VALID_SHELL = {"bash", "powershell"}

# Agents Claude Code ships with — never expected to appear in a project's
# .claude/agents/ directory. Source: https://code.claude.com/docs/en/sub-agents
# Built-in subagents section. Refresh when Claude Code adds new built-ins.
BUILTIN_AGENT_NAMES = {
    "Explore", "Plan", "general-purpose",
    "statusline-setup", "claude-code-guide",
}

# Tool reference shape — Claude Code tool names are PascalCase, optionally
# followed by parenthesized args (e.g. `Bash(git push *)`, `Agent(worker)`),
# or MCP-namespaced (`mcp__server__tool` with optional wildcard suffix).
# Anchored regex catches typos (lowercase names, internal whitespace, dangling
# parens). Keeps `.*` inside parens permissive — Claude Code accepts a wide
# range of arg patterns and we don't want to be more restrictive than the
# docs.
TOOL_REF_RE = re.compile(
    r"^(?:[A-Z][A-Za-z0-9]*(?:\(.*\))?"
    r"|mcp__[a-zA-Z][\w-]*__[\w.*-]+)$"
)

# Full hook event list (docs: https://code.claude.com/docs/en/hooks)
HOOK_VALID_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Notification", "SubagentStart",
    "SubagentStop", "TaskCreated", "TaskCompleted", "Stop", "StopFailure",
    "TeammateIdle", "InstructionsLoaded", "ConfigChange", "CwdChanged",
    "FileChanged", "WorktreeCreate", "WorktreeRemove", "PreCompact",
    "PostCompact", "Elicitation", "ElicitationResult", "SessionEnd",
}
HOOK_VALID_TYPES = {"command", "http", "mcp_tool", "prompt", "agent"}

# Skill description+when_to_use combined cap from the docs.
SKILL_DESCRIPTION_CAP = 1_536
# Soft body limit suggested by docs ("Keep SKILL.md under 500 lines").
SKILL_BODY_LINE_SOFT_LIMIT = 500


# ── Frontmatter parsing ──────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> Tuple[str, str]:
    """Return (frontmatter_yaml, body). Empty frontmatter if no leading ---."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    return text[3:end].strip(), text[end + 4:].lstrip("\n")


def _parse_frontmatter(fm_text: str) -> Dict:
    """Parse YAML frontmatter. Falls back to a flat key:value parser if no PyYAML."""
    if not fm_text.strip():
        return {}
    if HAVE_YAML:
        try:
            data = yaml.safe_load(fm_text)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}
    out: Dict = {}
    for line in fm_text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check(check_id: str, status: str, name: str, detail: str, value=None) -> Dict:
    return {
        "id": check_id, "group": "spec",
        "name": name, "status": status,
        "value": value, "detail": detail,
    }


def _model_value_recognized(model_str: str) -> bool:
    if not isinstance(model_str, str):
        return False
    s = model_str.strip().lower()
    return any(s.startswith(p) for p in AGENT_VALID_MODELS_PREFIXES)


def _is_bool(v) -> bool:
    return isinstance(v, bool)


def _tokenize_tool_list(value) -> List[str]:
    """Split a tools/disallowedTools/allowed-tools field into individual
    tool references. Frontmatter accepts both YAML lists and strings (comma-
    or space-separated). This tokenizer respects parentheses, so
    `Bash(git push *), Read` and `Bash(git add *) Bash(git push *)` both
    parse correctly even though the args contain commas/spaces.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not isinstance(value, str):
        return []
    tokens, current, depth = [], [], 0
    for ch in value:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch in ", \t\n" and depth == 0:
            if current:
                tokens.append("".join(current).strip())
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current).strip())
    return [t for t in tokens if t]


# ── Collectors ───────────────────────────────────────────────────────────────

def _collect_agents(cwd: str) -> List[Dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(cwd, ".claude", "agents", "*.md"))):
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            continue
        fm_text, body = _split_frontmatter(text)
        fm = _parse_frontmatter(fm_text)
        out.append({
            "path": path,
            "filename_stem": os.path.splitext(os.path.basename(path))[0],
            "frontmatter": fm,
            "body": body,
        })
    return out


def _collect_skills(cwd: str) -> List[Dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(cwd, ".claude", "skills", "*", "SKILL.md"))):
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            continue
        fm_text, body = _split_frontmatter(text)
        fm = _parse_frontmatter(fm_text)
        out.append({
            "path": path,
            "dir_name": os.path.basename(os.path.dirname(path)),
            "frontmatter": fm,
            "body": body,
        })
    return out


def _collect_settings(cwd: str) -> List[Dict]:
    """Read .claude/settings.json and .claude/settings.local.json."""
    out = []
    for fname in ("settings.json", "settings.local.json"):
        path = os.path.join(cwd, ".claude", fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"path": path, "data": data})
    return out


def _collect_commands(cwd: str) -> List[Dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(cwd, ".claude", "commands", "*.md"))):
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            continue
        fm_text, body = _split_frontmatter(text)
        fm = _parse_frontmatter(fm_text)
        out.append({"path": path, "frontmatter": fm, "body": body})
    return out


# ── Subagent checks (S1–S6) ──────────────────────────────────────────────────

def _check_agents(agents: List[Dict]) -> List[Dict]:
    if not agents:
        return [_check("S1", "SKIP", "Agent required fields", "No .claude/agents/*.md found"),
                _check("S2", "SKIP", "Agent name format", "No agents"),
                _check("S3", "SKIP", "Agent name matches filename", "No agents"),
                _check("S4", "SKIP", "Agent model value", "No agents"),
                _check("S5", "SKIP", "Agent enum values", "No agents"),
                _check("S6", "SKIP", "Agent name uniqueness", "No agents")]

    checks = []

    # S1: name + description required
    missing = []
    for a in agents:
        fm = a["frontmatter"]
        absent = [k for k in ("name", "description") if not fm.get(k)]
        if absent:
            missing.append(f"{a['filename_stem']}.md (missing: {', '.join(absent)})")
    if missing:
        checks.append(_check("S1", "FAIL", "Agent required fields",
                             f"{len(missing)} agent(s) missing name/description: {missing[:3]}",
                             value=len(missing)))
    else:
        checks.append(_check("S1", "PASS", "Agent required fields",
                             f"All {len(agents)} agents declare name + description"))

    # S2: name lowercase letters + hyphens
    bad = []
    for a in agents:
        nm = a["frontmatter"].get("name")
        if nm and not AGENT_NAME_RE.match(str(nm)):
            bad.append(f"{a['filename_stem']}.md (name='{nm}')")
    if bad:
        checks.append(_check("S2", "FAIL", "Agent name format",
                             f"Names must match [a-z][a-z0-9-]*: {bad}",
                             value=len(bad)))
    else:
        checks.append(_check("S2", "PASS", "Agent name format",
                             "All agent names match lowercase+hyphens convention"))

    # S3: name matches filename stem (best practice)
    mismatched = []
    for a in agents:
        nm = a["frontmatter"].get("name")
        if nm and nm != a["filename_stem"]:
            mismatched.append(f"{a['filename_stem']}.md (name='{nm}')")
    if mismatched:
        checks.append(_check("S3", "WARN", "Agent name matches filename",
                             f"{len(mismatched)} mismatch(es): {mismatched[:3]}",
                             value=len(mismatched)))
    else:
        checks.append(_check("S3", "PASS", "Agent name matches filename",
                             "All agent name fields match their filenames"))

    # S4: model value (when present) must look like an alias or full model ID
    bad_model = []
    for a in agents:
        m = a["frontmatter"].get("model")
        if m is not None and not _model_value_recognized(str(m)):
            bad_model.append(f"{a['filename_stem']}.md (model='{m}')")
    if bad_model:
        checks.append(_check("S4", "WARN", "Agent model value",
                             f"Unrecognized model: {bad_model}",
                             value=len(bad_model)))
    else:
        checks.append(_check("S4", "PASS", "Agent model value",
                             "All declared models are recognized aliases or claude-* IDs"))

    # S5: enum-typed fields. permissionMode, memory, color, effort, isolation.
    enum_violations = []
    enum_specs = [
        ("permissionMode", AGENT_VALID_PERMISSION_MODES),
        ("memory", AGENT_VALID_MEMORY),
        ("color", AGENT_VALID_COLORS),
        ("effort", EFFORT_VALID),
        ("isolation", AGENT_VALID_ISOLATION),
    ]
    for a in agents:
        fm = a["frontmatter"]
        for field, valid in enum_specs:
            v = fm.get(field)
            if v is None:
                continue
            if str(v) not in valid:
                enum_violations.append(f"{a['filename_stem']}.md ({field}='{v}', valid: {sorted(valid)})")
    if enum_violations:
        checks.append(_check("S5", "FAIL", "Agent enum values",
                             f"{len(enum_violations)} invalid enum value(s): {enum_violations[:3]}",
                             value=len(enum_violations)))
    else:
        checks.append(_check("S5", "PASS", "Agent enum values",
                             "All permissionMode/memory/color/effort/isolation values are valid"))

    # S6: name uniqueness across .claude/agents/
    seen = {}
    dups = []
    for a in agents:
        nm = a["frontmatter"].get("name") or a["filename_stem"]
        if nm in seen:
            dups.append(f"{nm}: {seen[nm]}, {a['filename_stem']}.md")
        else:
            seen[nm] = f"{a['filename_stem']}.md"
    if dups:
        checks.append(_check("S6", "FAIL", "Agent name uniqueness",
                             f"Duplicate names: {dups}", value=len(dups)))
    else:
        checks.append(_check("S6", "PASS", "Agent name uniqueness",
                             f"All {len(agents)} agent names are unique"))

    return checks


# ── Skill checks (S7–S11) ────────────────────────────────────────────────────

def _check_skills(skills: List[Dict]) -> List[Dict]:
    if not skills:
        return [_check("S7", "SKIP", "Skill name format", "No .claude/skills/<name>/SKILL.md found"),
                _check("S8", "SKIP", "Skill dir matches name", "No skills"),
                _check("S9", "SKIP", "Skill description length", "No skills"),
                _check("S10", "SKIP", "Skill body size", "No skills"),
                _check("S11", "SKIP", "Skill name uniqueness", "No skills")]

    checks = []

    # S7: name format. The `name` field is optional; if omitted, the directory
    # name is used and the dir name must match the same pattern.
    bad = []
    for s in skills:
        nm = s["frontmatter"].get("name") or s["dir_name"]
        if not isinstance(nm, str) or not SKILL_NAME_RE.match(nm) or len(nm) > 64:
            bad.append(f"{s['dir_name']}/SKILL.md (name='{nm}')")
    if bad:
        checks.append(_check("S7", "FAIL", "Skill name format",
                             f"Names must be lowercase+numbers+hyphens, ≤64 chars: {bad}",
                             value=len(bad)))
    else:
        checks.append(_check("S7", "PASS", "Skill name format",
                             f"All {len(skills)} skill names valid"))

    # S8: name field, if present, should match the directory name.
    mismatch = []
    for s in skills:
        nm = s["frontmatter"].get("name")
        if nm and nm != s["dir_name"]:
            mismatch.append(f"{s['dir_name']}/ (name='{nm}')")
    if mismatch:
        checks.append(_check("S8", "WARN", "Skill dir matches name",
                             f"{len(mismatch)} mismatch(es): {mismatch[:3]}",
                             value=len(mismatch)))
    else:
        checks.append(_check("S8", "PASS", "Skill dir matches name",
                             "All skill name fields match their containing directories"))

    # S9: description + when_to_use combined cap.
    long_desc = []
    for s in skills:
        fm = s["frontmatter"]
        desc = str(fm.get("description") or "")
        wtu = str(fm.get("when_to_use") or "")
        combined = len(desc) + len(wtu)
        if combined > SKILL_DESCRIPTION_CAP:
            long_desc.append(f"{s['dir_name']} ({combined} chars)")
    if long_desc:
        checks.append(_check("S9", "WARN", "Skill description length",
                             f"{len(long_desc)} skill(s) exceed {SKILL_DESCRIPTION_CAP} char cap "
                             f"(description+when_to_use will be truncated): {long_desc}",
                             value=len(long_desc)))
    else:
        checks.append(_check("S9", "PASS", "Skill description length",
                             f"All skills under {SKILL_DESCRIPTION_CAP}-char description cap"))

    # S10: body size soft limit (informational — docs say "keep under 500 lines")
    long_body = []
    for s in skills:
        lines = s["body"].count("\n") + 1
        if lines > SKILL_BODY_LINE_SOFT_LIMIT:
            long_body.append(f"{s['dir_name']} ({lines} lines)")
    if long_body:
        checks.append(_check("S10", "INFO", "Skill body size",
                             f"{len(long_body)} skill(s) over {SKILL_BODY_LINE_SOFT_LIMIT}-line "
                             f"soft limit (consider moving reference material to separate files): {long_body}",
                             value=len(long_body)))
    else:
        checks.append(_check("S10", "PASS", "Skill body size",
                             f"All skills under {SKILL_BODY_LINE_SOFT_LIMIT}-line soft limit"))

    # S11: name uniqueness across project skills (dir-name based).
    seen = {}
    dups = []
    for s in skills:
        nm = s["frontmatter"].get("name") or s["dir_name"]
        if nm in seen:
            dups.append(f"{nm}: {seen[nm]}, {s['dir_name']}/")
        else:
            seen[nm] = f"{s['dir_name']}/"
    if dups:
        checks.append(_check("S11", "FAIL", "Skill name uniqueness",
                             f"Duplicate names: {dups}", value=len(dups)))
    else:
        checks.append(_check("S11", "PASS", "Skill name uniqueness",
                             f"All {len(skills)} skill names unique"))

    return checks


# ── Skill enum fields (S16) ──────────────────────────────────────────────────

def _check_skills_enums(skills: List[Dict]) -> List[Dict]:
    """Mirrors S5 for skill frontmatter: validate context/shell/effort/model
    against the documented allowed values. Closes the gap where
    SKILL_VALID_CONTEXT and SKILL_VALID_SHELL were defined but never checked.
    """
    if not skills:
        return [_check("S16", "SKIP", "Skill enum values", "No skills")]

    enum_specs = [
        ("context", SKILL_VALID_CONTEXT),
        ("shell", SKILL_VALID_SHELL),
        ("effort", EFFORT_VALID),
    ]
    violations = []
    for s in skills:
        fm = s["frontmatter"]
        for field, valid in enum_specs:
            v = fm.get(field)
            if v is None:
                continue
            if str(v) not in valid:
                violations.append(
                    f"{s['dir_name']} ({field}='{v}', valid: {sorted(valid)})"
                )
        m = fm.get("model")
        if m is not None and not _model_value_recognized(str(m)):
            violations.append(
                f"{s['dir_name']} (model='{m}', expected sonnet/opus/haiku/inherit/claude-*)"
            )
    if violations:
        return [_check("S16", "FAIL", "Skill enum values",
                       f"{len(violations)} invalid: {violations[:3]}",
                       value=len(violations))]
    return [_check("S16", "PASS", "Skill enum values",
                   "All skill context/shell/effort/model values valid")]


# ── Tool reference shape (S17) ───────────────────────────────────────────────

def _check_tool_names(agents: List[Dict], skills: List[Dict]) -> List[Dict]:
    """Validate that every entry in `tools` / `disallowedTools` (agents) and
    `allowed-tools` (skills) parses as a Claude Code tool reference: a
    PascalCase name with optional parens, or a `mcp__server__tool` form.

    Catches typos like `read` (lowercase), trailing commas leaving empty
    tokens, and split-by-mistake entries like `Bash git` (a missed comma
    swallows the next tool).
    """
    if not agents and not skills:
        return [_check("S17", "SKIP", "Tool reference shape",
                       "No agents or skills with tool fields")]

    bad: List[str] = []
    for a in agents:
        nm = a["filename_stem"]
        for field in ("tools", "disallowedTools"):
            for tok in _tokenize_tool_list(a["frontmatter"].get(field)):
                if not TOOL_REF_RE.match(tok):
                    bad.append(f"agent {nm}.md/{field}: '{tok}'")
    for s in skills:
        nm = s["dir_name"]
        for tok in _tokenize_tool_list(s["frontmatter"].get("allowed-tools")):
            if not TOOL_REF_RE.match(tok):
                bad.append(f"skill {nm}/allowed-tools: '{tok}'")

    if bad:
        return [_check("S17", "WARN", "Tool reference shape",
                       f"{len(bad)} malformed reference(s): {bad[:3]}",
                       value=len(bad))]
    return [_check("S17", "PASS", "Tool reference shape",
                   "All tool references parse as Claude Code tools or MCP forms")]


# ── Hooks checks (S12–S14) ───────────────────────────────────────────────────

def _check_hooks(settings_files: List[Dict]) -> List[Dict]:
    if not settings_files:
        return [_check("S12", "SKIP", "Hook event names", "No .claude/settings*.json found"),
                _check("S13", "SKIP", "Hook handler types", "No settings"),
                _check("S14", "SKIP", "Hook handler shape", "No settings")]

    checks = []
    bad_events = []
    bad_types = []
    bad_shape = []

    for sf in settings_files:
        hooks_obj = sf["data"].get("hooks", {})
        if not isinstance(hooks_obj, dict):
            continue
        sf_label = os.path.basename(sf["path"])
        for event_name, matcher_groups in hooks_obj.items():
            if event_name not in HOOK_VALID_EVENTS:
                bad_events.append(f"{sf_label}: '{event_name}'")
            if not isinstance(matcher_groups, list):
                continue
            for group in matcher_groups:
                if not isinstance(group, dict):
                    continue
                handlers = group.get("hooks", [])
                if not isinstance(handlers, list):
                    continue
                for h in handlers:
                    if not isinstance(h, dict):
                        continue
                    htype = h.get("type")
                    if htype not in HOOK_VALID_TYPES:
                        bad_types.append(f"{sf_label}/{event_name}: type='{htype}'")
                    # type=command: command must be string (not array). Docs are
                    # explicit: "Must be string, not an array".
                    if htype == "command":
                        cmd = h.get("command")
                        if not isinstance(cmd, str):
                            bad_shape.append(f"{sf_label}/{event_name}: 'command' is {type(cmd).__name__}, expected string")
                    # type=http: url required and must be string.
                    if htype == "http":
                        url = h.get("url")
                        if not isinstance(url, str):
                            bad_shape.append(f"{sf_label}/{event_name}: http hook missing 'url' string")
                    # `if` field: docs forbid &&/||/list combinators.
                    if "if" in h:
                        if_val = h.get("if")
                        if isinstance(if_val, list):
                            bad_shape.append(f"{sf_label}/{event_name}: 'if' is a list, must be a single rule")
                        elif isinstance(if_val, str) and re.search(r"\|\||&&", if_val):
                            bad_shape.append(f"{sf_label}/{event_name}: 'if' uses &&/|| (define separate handlers instead)")

    if bad_events:
        checks.append(_check("S12", "FAIL", "Hook event names",
                             f"{len(bad_events)} unknown event(s): {bad_events[:3]}",
                             value=len(bad_events)))
    else:
        checks.append(_check("S12", "PASS", "Hook event names",
                             "All declared hook events are documented Claude Code events"))

    if bad_types:
        checks.append(_check("S13", "FAIL", "Hook handler types",
                             f"{len(bad_types)} invalid type(s): {bad_types[:3]}",
                             value=len(bad_types)))
    else:
        checks.append(_check("S13", "PASS", "Hook handler types",
                             "All hook handlers use a documented type"))

    if bad_shape:
        checks.append(_check("S14", "FAIL", "Hook handler shape",
                             f"{len(bad_shape)} shape error(s): {bad_shape[:3]}",
                             value=len(bad_shape)))
    else:
        checks.append(_check("S14", "PASS", "Hook handler shape",
                             "All hook handlers are well-formed (command is string, no &&/|| in `if`)"))

    return checks


# ── Cross-cutting (S15) ──────────────────────────────────────────────────────

def _check_cross_cutting(agents: List[Dict], spawned_undeclared: List[str]) -> List[Dict]:
    # Filter out Claude Code's built-in agents — they're never expected in
    # the project's agents/ directory, so flagging them is noise.
    real_undeclared = [a for a in spawned_undeclared if a not in BUILTIN_AGENT_NAMES]
    if not real_undeclared:
        builtins_seen = [a for a in spawned_undeclared if a in BUILTIN_AGENT_NAMES]
        detail = "All custom agent types are declared in .claude/agents/"
        if builtins_seen:
            detail += f" (built-ins also spawned, ignored: {builtins_seen})"
        return [_check("S15", "PASS", "Spawned agents declared", detail)]
    return [_check("S15", "WARN", "Spawned agents declared",
                   f"{len(real_undeclared)} undeclared custom agent(s): {real_undeclared[:5]} "
                   f"— consider adding to .claude/agents/ or removing the spawn site",
                   value=len(real_undeclared))]


# ── Entry point ──────────────────────────────────────────────────────────────

def run_static_checks(cwd: str, spawned_undeclared: Optional[List[str]] = None) -> List[Dict]:
    """Run all S-group checks. Returns a list of check dicts in the same shape
    the runtime checks emit, ready to merge into the report's `checks` array.

    `spawned_undeclared`: agent type names that appeared in the transcript but
    are not present in `.claude/agents/`. Threaded in by `transcript-parser.py`
    after it scans the parent JSONL.
    """
    agents = _collect_agents(cwd)
    skills = _collect_skills(cwd)
    settings = _collect_settings(cwd)
    checks = []
    checks.extend(_check_agents(agents))
    checks.extend(_check_skills(skills))
    checks.extend(_check_hooks(settings))
    checks.extend(_check_cross_cutting(agents, spawned_undeclared or []))
    checks.extend(_check_skills_enums(skills))
    checks.extend(_check_tool_names(agents, skills))
    return checks
