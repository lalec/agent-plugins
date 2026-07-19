#!/usr/bin/env python3
"""
agent-eval discovery: read .claude/agents/*.md and infer per-agent metadata for checks.

No config file needed. Each agent's expected handoff format, artifact paths, and pipeline
position are derived from the agent's own markdown definition.
"""

import os
import re
import glob
from typing import Dict, List, Optional, Set, Tuple


# Match a `**Status:** <value>` line anywhere in the body. The value is the literal
# token after the marker (single word/hyphenated). We capture all unique values across
# the body so the per-agent handoff regex matches what the agent actually writes.
STATUS_LINE_RE = re.compile(r"\*\*Status:\*\*\s*([A-Za-z][\w-]*(?:\s*\|\s*[A-Za-z][\w-]*)*)")

# Alternative final-output markers some pipelines use instead of **Status:**
RESULT_LINE_RE = re.compile(r"^RESULT:\s*([A-Za-z][\w-]*(?:\s*\|\s*[A-Za-z][\w-]*)*)", re.MULTILINE)

# Cross-references to *-log skills (the project convention for delivery-log skills).
# Captures the skill name so we can resolve its written file from the skill body.
LOG_SKILL_RE = re.compile(
    r"(?:invoke|use|run|trigger|via)\s+`?([a-z][\w-]*-log)`?",
    re.IGNORECASE,
)

# docs/*.md paths near a *-log skill reference (within the same sentence/line). Used
# as a fallback when the skill body itself doesn't declare its target file. Anchored
# on log-skill proximity to avoid grabbing inline references like docs/roadmap.md
# that aren't the agent's primary artifact.
DOCS_PATH_RE = re.compile(r"docs/[\w/.-]+\.md")

# Explicit "Output: PATH" / "Writes to: PATH" / "Delivers: PATH" / "Artifact: PATH"
# declarations — escape hatch for projects that don't follow the *-log convention.
EXPLICIT_ARTIFACT_RE = re.compile(
    r"(?:^|\n)(?:#+\s+)?(?:Writes\s+to|Outputs?|Delivers?|Artifacts?)\s*[:\-]\s*`?([\w/.-]+\.md)",
    re.IGNORECASE,
)

# Downstream agent references: "invoke <name>", "spawn <name>", "delegate to <name>",
# "tell the user to invoke <name>", "hand off to <name>". Names match agent file
# stems (lowercase + hyphens, must contain a hyphen to filter out random verbs).
DOWNSTREAM_RE = re.compile(
    r"(?:invoke|spawn|delegate\s+(?:back\s+)?to|hand\s+off\s+to|"
    r"tell\s+(?:the\s+)?user\s+to\s+invoke)\s+`?([a-z][\w]*-[\w-]+)`?",
    re.IGNORECASE,
)

# Upstream reference in description: "Invoked after <name>", "after <name> completes/sign-off"
UPSTREAM_RE = re.compile(
    r"(?:invoked\s+after|after)\s+`?([a-z][\w]*-[\w-]+)`?",
    re.IGNORECASE,
)

# Heading template line inside a log skill's SKILL.md — a markdown heading whose
# text contains placeholder syntax (YYYY date stubs, <angle> or {curly}
# placeholders). Its heading level becomes the required header for artifact
# writes (H3). Example: `### YYYY-MM-DD HH:MM · <7-char hash> — <title>`.
HEADER_TEMPLATE_RE = re.compile(
    r"^(#{1,6})\s+.*(?:YYYY|<[^>\n]+>|\{[^}\n]+\})",
    re.MULTILINE,
)


def _read_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Split YAML frontmatter from body. Returns (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _resolve_log_skill_artifacts(skill_name: str, cwd: str) -> Tuple[List[str], Optional[str]]:
    """Read a *-log skill's SKILL.md → (docs/*.md paths it writes, header pattern).

    The header pattern is derived from the first heading-shaped template line in
    the skill body (see HEADER_TEMPLATE_RE): its heading level becomes the regex
    artifact writes must contain. None when no template is found.
    """
    candidates = [
        os.path.join(cwd, ".claude", "skills", skill_name, "SKILL.md"),
        os.path.expanduser(f"~/.claude/skills/{skill_name}/SKILL.md"),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                body = f.read()
        except OSError:
            continue
        # Pull docs/*.md mentions from the skill body — log skills always document
        # their target file in their own SKILL.md.
        paths = list(set(re.findall(r"docs/[\w/.-]+\.md", body)))
        header_pattern = None
        m = HEADER_TEMPLATE_RE.search(body)
        if m:
            header_pattern = rf"^#{{{len(m.group(1))}}}\s+"
        if paths:
            return paths, header_pattern
    return [], None


def _discover_agent(path: str, cwd: str) -> Dict:
    """Parse one .claude/agents/<name>.md file."""
    with open(path) as f:
        text = f.read()
    fm, body = _read_frontmatter(text)
    name = fm.get("name") or os.path.splitext(os.path.basename(path))[0]
    description = fm.get("description", "")

    # Handoff format: collect all **Status:** values seen anywhere in the body, plus
    # any RESULT: lines. If both exist, both are accepted by the regex.
    status_values: Set[str] = set()
    for m in STATUS_LINE_RE.finditer(body):
        for v in re.split(r"\s*\|\s*", m.group(1)):
            v = v.strip()
            if v:
                status_values.add(v)

    result_values: Set[str] = set()
    for m in RESULT_LINE_RE.finditer(body):
        for v in re.split(r"\s*\|\s*", m.group(1)):
            v = v.strip()
            if v:
                result_values.add(v)

    handoff_patterns: List[str] = []
    if status_values:
        alt = "|".join(sorted(re.escape(v) for v in status_values))
        handoff_patterns.append(rf"\*\*Status:\*\*\s*({alt})")
    if result_values:
        alt = "|".join(sorted(re.escape(v) for v in result_values))
        handoff_patterns.append(rf"^RESULT:\s*({alt})")

    has_handoff = bool(handoff_patterns)

    # Artifact paths: anchored on (1) *-log skill references — the project convention
    # for delivery-log skills declares the canonical artifact in the skill body — and
    # (2) explicit `Output: PATH` / `Writes to: PATH` declarations as an escape hatch.
    # Inline mentions of docs/*.md without one of these anchors are ignored to avoid
    # over-flagging on conditional writes (e.g. roadmap entries).
    artifact_paths: Set[str] = set()
    artifact_header_pattern: Optional[str] = None

    log_skills: Set[str] = set()
    for m in LOG_SKILL_RE.finditer(body):
        log_skills.add(m.group(1).lower())
    for skill in log_skills:
        resolved, header = _resolve_log_skill_artifacts(skill, cwd)
        artifact_paths.update(resolved)
        if header and artifact_header_pattern is None:
            artifact_header_pattern = header
        # Fallback: if the skill body didn't declare a path, look for docs/*.md
        # in the same line as the skill reference in the agent body.
        if not resolved:
            for line in body.splitlines():
                if skill.lower() in line.lower():
                    artifact_paths.update(DOCS_PATH_RE.findall(line))

    for m in EXPLICIT_ARTIFACT_RE.finditer(body):
        artifact_paths.add(m.group(1))

    # Cross-references — both description and body. "Invoked after X" → upstream;
    # "invoke/spawn/hand off to X" → downstream. Filter out self-references.
    downstreams: Set[str] = set()
    for m in DOWNSTREAM_RE.finditer(description + "\n" + body):
        ref = m.group(1).lower()
        if ref != name:
            downstreams.add(ref)

    upstreams: Set[str] = set()
    for m in UPSTREAM_RE.finditer(description):
        ref = m.group(1).lower()
        if ref != name:
            upstreams.add(ref)

    # Role inference: name suffix takes precedence (project convention is consistent),
    # then status-value heuristic, else "free-form" (no handoff, no artifact).
    suffix = name.rsplit("-", 1)[-1] if "-" in name else name
    role_by_suffix = {"dev": "producer", "qa": "reviewer", "pm": "terminal", "log": "writer"}
    role = role_by_suffix.get(suffix)
    if role is None:
        if "complete" in status_values:
            role = "producer"
        elif "signed-off" in status_values:
            role = "reviewer"
        elif not has_handoff and not artifact_paths:
            role = "free-form"
        else:
            role = "unknown"

    return {
        "name": name,
        "description": description,
        "role": role,
        "has_handoff": has_handoff,
        "handoff_patterns": handoff_patterns,
        "artifact_paths": sorted(artifact_paths),
        "artifact_header_pattern": artifact_header_pattern,
        "downstreams": sorted(downstreams),
        "upstreams": sorted(upstreams),
    }


def _infer_dag_shape(agents: List[Dict]) -> str:
    """
    Classify the pipeline shape from cross-references.
      - "sequential": each agent has ≤1 forward downstream pointing to a declared
        agent (back-references for failure-routing are ignored — e.g. zeeker-qa
        routing fixes back to zeeker-dev is not a branch).
      - "branching": at least one agent has ≥2 forward downstreams.
      - "unknown": no agents.
    """
    if not agents:
        return "unknown"
    by_name = {a["name"]: a for a in agents}
    for a in agents:
        forward = [
            d for d in a["downstreams"]
            if d in by_name and a["name"] not in by_name[d]["downstreams"]
        ]
        if len(forward) >= 2:
            return "branching"
    return "sequential"


def discover_project(cwd: str) -> Dict:
    """
    Read .claude/agents/*.md from cwd and return a discovery record.
    Empty record if no agents directory or no agent files.
    """
    agents_dir = os.path.join(cwd, ".claude", "agents")
    agent_files = sorted(glob.glob(os.path.join(agents_dir, "*.md")))
    if not agent_files:
        return {"agents": {}, "dag_shape": "unknown", "agent_files_dir": agents_dir}

    discovered = [_discover_agent(p, cwd) for p in agent_files]
    return {
        "agents": {a["name"]: a for a in discovered},
        "dag_shape": _infer_dag_shape(discovered),
        "agent_files_dir": agents_dir,
    }


def artifact_match(file_path: str, expected_paths: List[str]) -> bool:
    """
    Check whether a tool_use file_path matches any expected artifact path.
    Match is path-suffix based: `docs/project-log.md` matches both
    `docs/project-log.md` and `/abs/path/docs/project-log.md`.
    """
    if not file_path or not expected_paths:
        return False
    fp = file_path.lstrip("/").lstrip("./")
    for expected in expected_paths:
        ep = expected.lstrip("/").lstrip("./")
        if fp == ep or fp.endswith("/" + ep):
            return True
    return False


def build_handoff_regex(agent_meta: Dict):
    """Compile the per-agent handoff-status regex. Returns None when has_handoff is False."""
    if not agent_meta.get("has_handoff"):
        return None
    patterns = agent_meta.get("handoff_patterns", [])
    if not patterns:
        return None
    combined = "|".join(f"(?:{p})" for p in patterns)
    return re.compile(combined, re.MULTILINE)


def build_artifact_header_regex(agent_meta: Dict):
    """Compile the per-agent artifact header regex discovered from the log
    skill's template. Returns None when no template was discoverable."""
    pattern = agent_meta.get("artifact_header_pattern")
    if not pattern:
        return None
    return re.compile(pattern, re.MULTILINE)
