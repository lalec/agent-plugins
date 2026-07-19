#!/usr/bin/env python3
"""
agent-eval parent-session analysis: orchestrator metrics + checks W2, W8, O7.

The subagent files show what each agent did; the parent JSONL shows what the
orchestrator did between spawns. This module derives:

  - orchestrator token/cost totals and peak context (W2, INFO)
  - spawn decision latency: gap between an agent finishing and the next
    Agent-tool spawn (W8, INFO)
  - top-level Edit/Write on project source after the first delegation —
    the orchestrator absorbing a subagent's role (O7, WARN)

O7 path heuristic: docs/, .claude/, markdown files, and temp/scratch paths are
bookkeeping the orchestrator legitimately owns; anything else counts as source.
"""

import json
import os
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional

SPAWN_TOOL_NAMES = ("Task", "Agent")

# Project-relative paths the orchestrator may legitimately write without
# absorbing an agent's role: docs, config-dir bookkeeping, markdown. Paths
# outside the project (temp files, scratch dirs) are ignored entirely.
O7_EXEMPT_RE = re.compile(
    r"^(docs|\.claude|node_modules)/|\.md$",
    re.IGNORECASE,
)


def _parse_ts(s: Optional[str]):
    if not s:
        return None
    try:
        s = s.rstrip("Z").split(".")[0]
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _check(check_id, group, name, status, detail, value=None):
    return {"id": check_id, "group": group, "name": name,
            "status": status, "value": value, "detail": detail}


def _scan_parent(parent_jsonl_path: str) -> Dict:
    """One pass over the parent JSONL → usage, spawn events, edit events."""
    token_usage = {}          # requestId -> usage (last record wins on output>0)
    model = None
    turns = set()
    spawns = []               # [{ts, subagent_type}]
    edits = []                # [{ts, file_path}]
    tool_calls = {}

    with open(parent_jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "assistant":
                continue
            ts = rec.get("timestamp")
            msg = rec.get("message", {})
            if model is None:
                model = msg.get("model") or None
            req_id = rec.get("requestId", "")
            usage = msg.get("usage", {})
            if req_id:
                turns.add(req_id)
                if usage.get("output_tokens", 0) > 0 or req_id not in token_usage:
                    token_usage[req_id] = usage
            for block in msg.get("content", []):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                tool_calls[name] = tool_calls.get(name, 0) + 1
                inp = block.get("input", {})
                if name in SPAWN_TOOL_NAMES:
                    spawns.append({"ts": ts,
                                   "subagent_type": inp.get("subagent_type", "")})
                elif name in ("Edit", "Write"):
                    fp = inp.get("file_path", "")
                    if fp:
                        edits.append({"ts": ts, "file_path": fp})

    tokens = {"input": 0, "output": 0, "cache_read": 0,
              "cache_write_5m": 0, "cache_write_1h": 0}
    peak_context = 0
    for usage in token_usage.values():
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        cc = usage.get("cache_creation", {})
        cw5 = cc.get("ephemeral_5m_input_tokens", 0)
        cw1 = cc.get("ephemeral_1h_input_tokens", 0)
        if not cw5 and not cw1:
            cw5 = usage.get("cache_creation_input_tokens", 0)
        tokens["input"] += inp
        tokens["output"] += out
        tokens["cache_read"] += cr
        tokens["cache_write_5m"] += cw5
        tokens["cache_write_1h"] += cw1
        peak_context = max(peak_context, inp + out + cr + cw5 + cw1)

    return {"model": model, "turns": len(turns), "tokens": tokens,
            "peak_context": peak_context, "spawns": spawns, "edits": edits,
            "tool_calls": tool_calls}


def _check_w2(orch: Dict, agents: List[Dict]) -> Dict:
    """W2: Orchestrator overhead — orchestrator billed tokens vs agent total."""
    orch_billed = orch["billed_tokens"]
    agent_billed = sum(a.get("billed_tokens", 0) for a in agents)
    total = orch_billed + agent_billed
    if total == 0:
        return _check("W2", "workflow", "Orchestrator overhead", "SKIP",
                      "No token usage recorded in parent or agent transcripts")
    share = orch_billed / total
    return _check("W2", "workflow", "Orchestrator overhead", "INFO",
                  f"Orchestrator billed {orch_billed:,} tokens = {share:.0%} of workflow total "
                  f"(agents: {agent_billed:,}); orchestrator cost ${orch['cost_usd']:.3f}",
                  value=round(share, 2))


def _check_w8(scan: Dict, agents: List[Dict]) -> Dict:
    """W8: Spawn decision latency — gap between an agent's last record and the
    next spawn event in the parent. Long gaps = the orchestrator deliberating
    (or doing work itself) between handoffs."""
    spawn_ts = sorted(t for t in (_parse_ts(s["ts"]) for s in scan["spawns"]) if t)
    agent_ends = sorted(t for t in (
        _parse_ts(a.get("timestamps", {}).get("last")) for a in agents) if t)
    if not spawn_ts or not agent_ends:
        return _check("W8", "workflow", "Spawn decision latency", "SKIP",
                      "No spawn/agent-completion timestamp pairs available")
    gaps = []
    for end in agent_ends:
        nxt = next((s for s in spawn_ts if s > end), None)
        if nxt is not None:
            gaps.append((nxt - end).total_seconds())
    if not gaps:
        return _check("W8", "workflow", "Spawn decision latency", "SKIP",
                      "No spawn occurred after any agent completion")
    gaps.sort()
    median = gaps[len(gaps) // 2]
    return _check("W8", "workflow", "Spawn decision latency", "INFO",
                  f"{len(gaps)} completion→next-spawn gap(s); median {median:.0f}s, "
                  f"max {max(gaps):.0f}s",
                  value=round(median, 1))


def _project_relative(file_path: str, cwd: str) -> Optional[str]:
    """Path relative to the project root; None when outside the project."""
    if not file_path.startswith("/"):
        return file_path  # already project-relative
    root = cwd.rstrip("/") + "/"
    if file_path.startswith(root):
        return file_path[len(root):]
    return None


def _check_o7(scan: Dict, cwd: str) -> Dict:
    """O7: Top-level source edits after delegation (role absorption)."""
    spawn_ts = sorted(t for t in (_parse_ts(s["ts"]) for s in scan["spawns"]) if t)
    if not spawn_ts:
        return _check("O7", "orchestration", "Top-level source edits after delegation",
                      "SKIP", "No subagent spawns in parent session")
    first_spawn = spawn_ts[0]
    offending = []
    for e in scan["edits"]:
        t = _parse_ts(e["ts"])
        if t is None or t <= first_spawn:
            continue
        rel = _project_relative(e["file_path"], cwd)
        if rel is not None and not O7_EXEMPT_RE.search(rel):
            offending.append(rel)
    if offending:
        sample = sorted(set(offending))[:3]
        return _check("O7", "orchestration", "Top-level source edits after delegation",
                      "WARN",
                      f"Orchestrator edited {len(offending)} project file(s) itself after "
                      f"delegating to agents (role absorption): {sample}",
                      value=len(offending))
    return _check("O7", "orchestration", "Top-level source edits after delegation",
                  "PASS", "Orchestrator made no post-delegation source edits")


def analyze_parent_session(parent_jsonl_path: str, agents: List[Dict],
                           cost_fn: Callable[[Optional[str], Dict], float],
                           cwd: Optional[str] = None) -> Dict:
    """Analyze the orchestrator session. Returns {"orchestrator": {...}, "checks": [...]}.

    `cost_fn(model, tokens)` is transcript-parser's compute_cost_usd — passed in
    so the rate table lives in exactly one place. `cwd` is the project root used
    to classify O7 edits as project vs external; defaults to os.getcwd().
    """
    cwd = cwd or os.getcwd()
    if not os.path.exists(parent_jsonl_path):
        skip = _check("W2", "workflow", "Orchestrator overhead", "SKIP",
                      "Parent JSONL not found")
        return {"orchestrator": None, "checks": [
            skip,
            _check("W8", "workflow", "Spawn decision latency", "SKIP",
                   "Parent JSONL not found"),
            _check("O7", "orchestration", "Top-level source edits after delegation",
                   "SKIP", "Parent JSONL not found"),
        ]}

    scan = _scan_parent(parent_jsonl_path)
    tokens = scan["tokens"]
    cache_write = tokens["cache_write_5m"] + tokens["cache_write_1h"]
    orchestrator = {
        "model": scan["model"],
        "turns": scan["turns"],
        "peak_context_tokens": scan["peak_context"],
        "billed_tokens": sum(tokens.values()),
        "tokens": {**tokens, "cache_write": cache_write},
        "cost_usd": round(cost_fn(scan["model"], tokens), 4),
        "tool_calls": scan["tool_calls"],
        "subagent_spawns": len(scan["spawns"]),
    }
    checks = [
        _check_w2(orchestrator, agents),
        _check_w8(scan, agents),
        _check_o7(scan, cwd),
    ]
    return {"orchestrator": orchestrator, "checks": checks}
