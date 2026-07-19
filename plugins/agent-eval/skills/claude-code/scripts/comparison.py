#!/usr/bin/env python3
"""
agent-eval compare mode: diff two runs' JSON outputs → regression report.

Stateless — the caller passes the baseline file via --compare. Severity ranks:
PASS/INFO = 0, WARN = 1, FAIL = 2. A check whose rank increased is a
regression; decreased is an improvement. SKIP transitions are coverage
changes, not regressions (a check that stopped running is worth seeing but
isn't evidence the workflow got worse).
"""

from typing import Dict, List, Optional

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

# Summary metrics worth diffing run-over-run.
_SUMMARY_KEYS = (
    "agents_evaluated",
    "total_peak_context_tokens",
    "total_output_tokens",
    "total_billed_tokens",
    "workflow_cache_hit_ratio",
    "total_cost_usd",
)

# Per-agent metrics worth diffing (aggregated by agent_type).
_AGENT_KEYS = ("cost_usd", "peak_context_tokens", "billed_tokens", "turns")


def _index_checks(run: Dict) -> Dict[str, Dict]:
    return {c["id"]: c for c in run.get("checks", []) if c.get("id")}


def _agents_by_type(run: Dict) -> Dict[str, Dict]:
    """Aggregate per-agent metrics by agent_type (a type may spawn several times)."""
    out: Dict[str, Dict] = {}
    for a in run.get("agents", []):
        if "error" in a:
            continue
        t = a.get("agent_type") or "agent"
        agg = out.setdefault(t, {k: 0 for k in _AGENT_KEYS} | {"count": 0})
        agg["count"] += 1
        for k in _AGENT_KEYS:
            v = a.get(k)
            if isinstance(v, (int, float)):
                agg[k] = round(agg[k] + v, 4)
    return out


def _delta(baseline_v, current_v):
    entry = {"baseline": baseline_v, "current": current_v}
    if isinstance(baseline_v, (int, float)) and isinstance(current_v, (int, float)):
        entry["delta"] = round(current_v - baseline_v, 4)
    return entry


def build_comparison(baseline: Dict, current: Dict) -> Dict:
    """Diff a baseline run's JSON against the current run's result dict."""
    base_checks = _index_checks(baseline)
    curr_checks = _index_checks(current)

    regressions: List[Dict] = []
    improvements: List[Dict] = []
    coverage_changes: List[Dict] = []

    for check_id in sorted(set(base_checks) & set(curr_checks)):
        b, c = base_checks[check_id], curr_checks[check_id]
        bs, cs = b.get("status"), c.get("status")
        if bs == cs:
            continue
        entry = {"id": check_id, "name": c.get("name"),
                 "baseline": bs, "current": cs, "detail": c.get("detail")}
        if bs == "SKIP" or cs == "SKIP":
            coverage_changes.append(entry)
        elif _RANK.get(cs, 0) > _RANK.get(bs, 0):
            regressions.append(entry)
        elif _RANK.get(cs, 0) < _RANK.get(bs, 0):
            improvements.append(entry)

    summary_deltas = {}
    base_summary = baseline.get("summary", {})
    curr_summary = current.get("summary", {})
    for key in _SUMMARY_KEYS:
        if key in base_summary or key in curr_summary:
            summary_deltas[key] = _delta(base_summary.get(key), curr_summary.get(key))

    base_agents = _agents_by_type(baseline)
    curr_agents = _agents_by_type(current)
    agent_deltas = {}
    for t in sorted(set(base_agents) & set(curr_agents)):
        agent_deltas[t] = {
            k: _delta(base_agents[t].get(k), curr_agents[t].get(k))
            for k in (*_AGENT_KEYS, "count")
        }

    return {
        "baseline_session_id": baseline.get("session_id"),
        "baseline_timestamp": baseline.get("timestamp"),
        "regressions": regressions,
        "improvements": improvements,
        "coverage_changes": coverage_changes,
        "new_checks": sorted(set(curr_checks) - set(base_checks)),
        "removed_checks": sorted(set(base_checks) - set(curr_checks)),
        "summary_deltas": summary_deltas,
        "agent_deltas": agent_deltas,
        "agents_only_in_baseline": sorted(set(base_agents) - set(curr_agents)),
        "agents_only_in_current": sorted(set(curr_agents) - set(base_agents)),
    }
