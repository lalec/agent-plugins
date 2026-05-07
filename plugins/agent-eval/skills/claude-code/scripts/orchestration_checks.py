#!/usr/bin/env python3
"""
agent-eval orchestration efficiency checks (group O).

Compares each agent's declared frontmatter (in `.claude/agents/*.md` and
`.claude/skills/*/SKILL.md`) against the agent's actual transcript behavior to
flag inefficient orchestration setups: over-broad tool grants, late skill
loads, weak descriptions that prevent auto-delegation, bloated handoff
prompts, and destructive skills exposed to model invocation.

These rules are heuristic, not deterministic. False-positive rate is higher
than the S group; thresholds are tuned conservatively. Each finding includes
raw counts so the reader can verify quickly.

Doc source: https://code.claude.com/docs/en/sub-agents
            https://code.claude.com/docs/en/skills
"""

import re
from typing import Dict, List, Optional

from static_checks import _collect_agents, _collect_skills


# ── Thresholds ───────────────────────────────────────────────────────────────

DESCRIPTION_MIN_CHARS = 40

# Trigger phrases that the docs encourage in agent descriptions to make
# auto-delegation work. Source: sub-agents → "Understand automatic delegation"
# (the docs literally say: 'include phrases like "use proactively"').
DELEGATION_TRIGGER_RE = re.compile(
    r"\b(use\s+(?:when|proactively|for|to|after|immediately|whenever)|"
    r"invoked?\s+(?:when|after|for|to)|"
    r"call\s+(?:when|for)|"
    r"trigger(?:s|ed)?\s+(?:when|on))\b",
    re.IGNORECASE,
)

# How many distinct tools an inheriting agent must stay under for O2 to suggest
# narrowing. ≥10 calls keeps the sample size meaningful.
O2_DISTINCT_TOOL_CEILING = 4
O2_MIN_TOTAL_CALLS = 10

# O5: orchestrator handoff prompt length. >5000 chars suggests the orchestrator
# is dumping unnecessary context into the subagent's startup window.
O5_PROMPT_CHAR_THRESHOLD = 5000

# O6: destructive verb pattern in skill descriptions. A skill matching this
# pattern that lacks `disable-model-invocation: true` can fire without your
# explicit invocation, which is high-risk for irreversible actions.
DESTRUCTIVE_VERB_RE = re.compile(
    r"\b(deploy|commit|push|delete|migrate|release|drop|truncate|reset|publish)\w*\b",
    re.IGNORECASE,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check(check_id: str, status: str, name: str, detail: str, value=None) -> Dict:
    return {
        "id": check_id, "group": "orchestration",
        "name": name, "status": status,
        "value": value, "detail": detail,
    }


def _agent_label(a: Dict) -> str:
    return (a.get("description") or "")[:30] or a.get("agent_id", "")


def _normalize_list_field(value) -> List[str]:
    """Frontmatter lists can be YAML lists, comma-separated strings, or
    space-separated strings. Return a clean list of names."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        # Tools/skills frontmatter accepts either commas or whitespace.
        parts = re.split(r"[,\s]+", value)
        return [p.strip() for p in parts if p.strip()]
    return []


def _index_declared_agents(declared: List[Dict]) -> Dict[str, Dict]:
    """Index static-collected agents by their `name` (or filename stem)."""
    out = {}
    for d in declared:
        nm = d["frontmatter"].get("name") or d["filename_stem"]
        if nm:
            out[nm] = d
    return out


# ── O2: Tool inherit-all but narrow usage ────────────────────────────────────

def _check_o2(eval_agents: List[Dict], declared_by_name: Dict[str, Dict]) -> List[Dict]:
    candidates = []
    for a in eval_agents:
        atype = a.get("agent_type")
        d = declared_by_name.get(atype)
        if not d:
            continue
        fm = d["frontmatter"]
        # Both unset → agent inherits everything from the parent.
        if fm.get("tools") is not None or fm.get("disallowedTools") is not None:
            continue
        tool_calls = a.get("tool_calls", {}) or {}
        total = sum(tool_calls.values())
        distinct = len(tool_calls)
        if total >= O2_MIN_TOTAL_CALLS and distinct <= O2_DISTINCT_TOOL_CEILING:
            candidates.append({
                "label": _agent_label(a),
                "type": atype,
                "distinct": distinct,
                "total": total,
                "tools": sorted(tool_calls.keys()),
            })
    if not candidates:
        return [_check("O2", "PASS", "Tool grants right-sized",
                       "No agents with inherits-all + narrow actual usage")]
    detail = "; ".join(
        f"{c['label']} (used only {c['tools']} across {c['total']} calls — could declare `tools: {' '.join(c['tools'])}`)"
        for c in candidates
    )
    return [_check("O2", "WARN", "Tool grants right-sized",
                   f"{len(candidates)} agent(s) inherit all tools but use ≤{O2_DISTINCT_TOOL_CEILING} distinct: {detail}",
                   value=len(candidates))]


# ── O3: Skill invoked mid-task but not preloaded ─────────────────────────────

def _check_o3(eval_agents: List[Dict], declared_by_name: Dict[str, Dict]) -> List[Dict]:
    findings = []
    for a in eval_agents:
        atype = a.get("agent_type")
        d = declared_by_name.get(atype)
        if not d:
            continue
        invoked = set(a.get("skills_invoked") or [])
        if not invoked:
            continue
        preloaded = set(_normalize_list_field(d["frontmatter"].get("skills")))
        late_loads = invoked - preloaded
        if late_loads:
            findings.append({
                "label": _agent_label(a),
                "type": atype,
                "late": sorted(late_loads),
            })
    if not findings:
        return [_check("O3", "PASS", "Skill preload alignment",
                       "All mid-task skill invocations are preloaded (or no skills used)")]
    detail = "; ".join(
        f"{f['label']} loaded {f['late']} mid-task — consider `skills: [...]` in {f['type']}.md"
        for f in findings
    )
    return [_check("O3", "INFO", "Skill preload alignment",
                   f"{len(findings)} agent(s) invoked skills not in their preload list: {detail}",
                   value=len(findings))]


# ── O4: Description quality ──────────────────────────────────────────────────

def _check_o4(declared: List[Dict]) -> List[Dict]:
    if not declared:
        return [_check("O4", "SKIP", "Description quality",
                       "No declared agents in .claude/agents/")]
    weak = []
    for d in declared:
        desc = (d["frontmatter"].get("description") or "").strip()
        nm = d["frontmatter"].get("name") or d["filename_stem"]
        reasons = []
        if len(desc) < DESCRIPTION_MIN_CHARS:
            reasons.append(f"too short ({len(desc)} chars, <{DESCRIPTION_MIN_CHARS})")
        if desc and not DELEGATION_TRIGGER_RE.search(desc):
            reasons.append("no delegation trigger phrase ('use when/for/proactively', 'invoked when')")
        if reasons:
            weak.append(f"{nm} ({', '.join(reasons)})")
    if not weak:
        return [_check("O4", "PASS", "Description quality",
                       f"All {len(declared)} agent descriptions look auto-delegate-friendly")]
    return [_check("O4", "WARN", "Description quality",
                   f"{len(weak)} agent(s) have weak descriptions: {weak[:3]}",
                   value=len(weak))]


# ── O5: Orchestrator prompt bloat ────────────────────────────────────────────

def _check_o5(eval_agents: List[Dict]) -> List[Dict]:
    bloated = []
    for a in eval_agents:
        chars = a.get("first_user_prompt_chars")
        if chars is None or chars <= O5_PROMPT_CHAR_THRESHOLD:
            continue
        bloated.append(f"{_agent_label(a)} ({chars:,} chars)")
    if not bloated:
        return [_check("O5", "PASS", "Orchestrator prompt size",
                       f"All handoff prompts under {O5_PROMPT_CHAR_THRESHOLD:,} chars")]
    return [_check("O5", "WARN", "Orchestrator prompt size",
                   f"{len(bloated)} handoff prompt(s) over {O5_PROMPT_CHAR_THRESHOLD:,} chars: {bloated[:3]} "
                   f"— orchestrator may be passing unnecessary context",
                   value=len(bloated))]


# ── O6: Destructive skill auto-invocable ─────────────────────────────────────

def _check_o6(declared_skills: List[Dict]) -> List[Dict]:
    if not declared_skills:
        return [_check("O6", "SKIP", "Destructive skill safety",
                       "No project skills found")]
    risky = []
    for s in declared_skills:
        fm = s["frontmatter"]
        desc = str(fm.get("description") or "")
        wtu = str(fm.get("when_to_use") or "")
        match = DESTRUCTIVE_VERB_RE.search(desc + " " + wtu)
        if not match:
            continue
        # Skip skills that already lock down model invocation.
        if fm.get("disable-model-invocation") is True:
            continue
        # YAML scalar-string fallback (when PyYAML isn't available, our flat
        # parser leaves the value as a string).
        if str(fm.get("disable-model-invocation")).strip().lower() == "true":
            continue
        risky.append(f"{s['dir_name']} (verb: {match.group(0).lower()})")
    if not risky:
        return [_check("O6", "PASS", "Destructive skill safety",
                       "All skills with destructive verbs are locked to user invocation")]
    return [_check("O6", "WARN", "Destructive skill safety",
                   f"{len(risky)} skill(s) match destructive verbs without `disable-model-invocation: true`: "
                   f"{risky[:5]} — Claude could trigger these without your explicit invocation",
                   value=len(risky))]


# ── Entry point ──────────────────────────────────────────────────────────────

def run_orchestration_checks(cwd: str, eval_agents: List[Dict]) -> List[Dict]:
    """Run O-group checks. `eval_agents` is the runtime agent list from
    transcript-parser; static frontmatter is collected from `cwd`."""
    declared_agents = _collect_agents(cwd)
    declared_skills = _collect_skills(cwd)
    declared_by_name = _index_declared_agents(declared_agents)

    checks = []
    checks.extend(_check_o2(eval_agents, declared_by_name))
    checks.extend(_check_o3(eval_agents, declared_by_name))
    checks.extend(_check_o4(declared_agents))
    checks.extend(_check_o5(eval_agents))
    checks.extend(_check_o6(declared_skills))
    return checks
