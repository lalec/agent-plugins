#!/usr/bin/env python3
"""
agent-eval transcript-parser: parse JSONL transcripts → agent process metrics + checks.

Usage: python3 transcript-parser.py <session-id> <target-name>
           [--output-dir DIR] [--scan] [--compare BASELINE.json]
Output: JSON to stdout

--scan     When the given session has no agents, scan sibling sessions in
           ~/.claude/projects/{project-dir}/ for one containing agent JSONL files.
--compare  Diff this run against a previous run's JSON output — emits a
           `comparison` section with check regressions and metric deltas.

Designed for instruction-based Claude Code agent pipelines (.claude/agents/*.md).
Per-agent expectations (handoff format, artifact paths, pipeline position) are
discovered at runtime from the project's own .claude/agents/*.md files — no
agent-eval.json required. Per-agent cost is computed from each spawn's actual
model recorded in the JSONL records.

The parent (orchestrator) session is analyzed too: W2 orchestrator overhead,
W8 spawn decision latency, O7 top-level source edits after delegation. Only W6
remains omitted — it needs queue-operation records Claude Code doesn't write.
"""

import json
import sys
import os
import re
import glob
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from discovery import (discover_project, artifact_match, build_handoff_regex,
                       build_artifact_header_regex)
from static_checks import run_static_checks
from orchestration_checks import run_orchestration_checks
from parent_session import analyze_parent_session
from comparison import build_comparison


# ── Cost rates ───────────────────────────────────────────────────────────────
# Per-million token rates for current Claude models. Substring-matched against
# each agent's model from the JSONL `message.model`. Cache writes are priced by
# TTL — 5-minute writes cost 1.25× the input rate, 1-hour writes 2× — and the
# JSONL usage block reports each TTL separately. Refresh manually when models
# change. Unknown models fall back to Sonnet rates and emit a top-level note.

MODEL_RATES = {
    "fable":  {"input": 10.00, "output": 50.00, "cache_read": 1.00},
    "opus":   {"input": 5.00,  "output": 25.00, "cache_read": 0.50},
    "sonnet": {"input": 3.00,  "output": 15.00, "cache_read": 0.30},
    "haiku":  {"input": 1.00,  "output": 5.00,  "cache_read": 0.10},
}
CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.00
DEFAULT_RATE_KEY = "sonnet"


def rates_for_model(model_id):
    """Substring-match a model id (e.g. 'claude-fable-5') to MODEL_RATES."""
    if model_id:
        m = model_id.lower()
        for key, rates in MODEL_RATES.items():
            if key in m:
                return key, rates
    return DEFAULT_RATE_KEY, MODEL_RATES[DEFAULT_RATE_KEY]


def compute_cost_usd(model_id, tokens):
    """Cost from a token dict with input/output/cache_read/cache_write_5m/cache_write_1h."""
    _, rates = rates_for_model(model_id)
    return (
        tokens.get("input", 0)          * rates["input"]      / 1_000_000 +
        tokens.get("output", 0)         * rates["output"]     / 1_000_000 +
        tokens.get("cache_read", 0)     * rates["cache_read"] / 1_000_000 +
        tokens.get("cache_write_5m", 0) * rates["input"] * CACHE_WRITE_5M_MULT / 1_000_000 +
        tokens.get("cache_write_1h", 0) * rates["input"] * CACHE_WRITE_1H_MULT / 1_000_000
    )


# ── Behavioral patterns ──────────────────────────────────────────────────────
# H1 flags paths that are suspect in ANY project type — dependency trees and
# other sessions' transcripts. Reading application source is NOT flagged: for
# dev/QA pipelines that is the agents' job. Always-on, no project-type gate.

SUSPECT_PATH_PATTERNS = [
    r"(^|/)node_modules/",
    r"\.claude/projects/",
]


# ── Project type detection (informational only — no checks depend on it) ─────

def detect_project_type(cwd):
    detected = set()
    if os.path.exists(os.path.join(cwd, "package.json")):
        detected.add("web")
    if glob.glob(os.path.join(cwd, "*.js")) or glob.glob(os.path.join(cwd, "src", "*.js")):
        detected.add("web")
    if glob.glob(os.path.join(cwd, "*.ts")) or glob.glob(os.path.join(cwd, "src", "*.ts")):
        detected.add("web")
    if os.path.exists(os.path.join(cwd, "Dockerfile")):
        detected.add("docker")
    if os.path.exists(os.path.join(cwd, "requirements.txt")) or glob.glob(os.path.join(cwd, "*.py")):
        detected.add("python")
    return detected


# ── Session / project helpers ────────────────────────────────────────────────

def resolve_project_dir(cwd):
    # AGENT_EVAL_PROJECTS_DIR overrides the default location — used by fixture
    # tests so transcripts never need to live under ~/.claude/projects.
    base = os.environ.get("AGENT_EVAL_PROJECTS_DIR")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    slug = cwd.replace("/", "-")
    return os.path.join(base, slug)


def parse_parent_jsonl(parent_jsonl_path):
    """Extract task_id → description mapping from parent session JSONL."""
    task_map = {}
    if not os.path.exists(parent_jsonl_path):
        return task_map
    with open(parent_jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "queue-operation" and rec.get("operation") == "enqueue":
                content_raw = rec.get("content", "")
                if not content_raw:
                    continue
                try:
                    c = json.loads(content_raw)
                    task_id = c.get("task_id", "")
                    description = c.get("description", "")
                    if task_id and description:
                        task_map[task_id] = description
                except (json.JSONDecodeError, AttributeError):
                    continue
    return task_map


def parse_task_type_map(parent_jsonl_path):
    """Build task_id → subagent_type from queue-operation XML and Task tool_use blocks."""
    tool_to_type = {}
    task_to_tool = {}
    if not os.path.exists(parent_jsonl_path):
        return {}
    with open(parent_jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_content = rec.get("message", {}).get("content", [])
            if isinstance(msg_content, list):
                for block in msg_content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_use"
                            and block.get("name") in ("Task", "Agent")):
                        tool_id = block.get("id", "")
                        subagent_type = block.get("input", {}).get("subagent_type", "")
                        if tool_id and subagent_type:
                            tool_to_type[tool_id] = subagent_type
            if rec.get("type") == "queue-operation" and rec.get("operation") == "enqueue":
                content = rec.get("content", "")
                task_m = re.search(r"<task-id>([^<]+)</task-id>", content)
                tool_m = re.search(r"<tool-use-id>([^<]+)</tool-use-id>", content)
                if task_m and tool_m:
                    task_to_tool[task_m.group(1)] = tool_m.group(1)
    return {
        task_id: tool_to_type[tool_id]
        for task_id, tool_id in task_to_tool.items()
        if tool_id in tool_to_type
    }


def extract_description_from_agent_jsonl(jsonl_path):
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user":
                    continue
                content = rec.get("message", {}).get("content", "")
                if isinstance(content, list):
                    content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                first_line = content.strip().split("\n")[0][:120]
                if first_line:
                    return first_line
    except OSError:
        pass
    return None


def scan_for_agent_session(project_dir, target):
    for entry in sorted(os.listdir(project_dir)):
        candidate_subagent_dir = os.path.join(project_dir, entry, "subagents")
        if not os.path.isdir(candidate_subagent_dir):
            continue
        agent_files = glob.glob(os.path.join(candidate_subagent_dir, "agent-*.jsonl"))
        if not agent_files:
            continue
        for af in agent_files:
            desc = extract_description_from_agent_jsonl(af)
            if desc:
                return entry, candidate_subagent_dir
    return None, None


# ── Path checks ──────────────────────────────────────────────────────────────

def is_suspect_path(path_str):
    return any(re.search(pat, path_str) for pat in SUSPECT_PATH_PATTERNS)


# ── Per-agent parsing ────────────────────────────────────────────────────────

def parse_subagent_jsonl(jsonl_path, description, target, agent_type, agent_meta):
    """Parse one subagent JSONL → per-agent metrics + violations.

    Model is read from each assistant record's `message.model` (set by Claude Code at
    spawn time and stable within a session) — meta.json doesn't carry it.
    """
    agent_id = os.path.basename(jsonl_path).replace("agent-", "").replace(".jsonl", "")

    if not os.path.exists(jsonl_path):
        return {
            "agent_id": agent_id,
            "description": description,
            "agent_type": agent_type,
            "error": "file_not_found",
        }

    expected_artifacts = list(agent_meta.get("artifact_paths", []))
    handoff_re = build_handoff_regex(agent_meta)
    h3_pattern = build_artifact_header_regex(agent_meta)
    role = agent_meta.get("role")

    turns = set()
    token_usage = {}
    tool_calls = {}
    # H4: (tool, input) signatures within the current mutation-free span. Any
    # Edit/Write resets the span — the workspace changed, so re-running an
    # identical command afterwards (loop-style iterate/verify) is legitimate.
    span_signatures = defaultdict(int)
    repeated_counts = {}
    tool_signature_samples = {}
    timestamps = []
    user_timestamps = []
    first_tool_ts = None
    tool_uses_per_turn = defaultdict(int)
    read_count_for_path = defaultdict(int)
    h5_flagged = set()
    skills_invoked = set()
    violations = []
    matched_artifacts = set()
    last_text = ""
    first_user_prompt = ""
    model = None

    with open(jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = rec.get("timestamp")
            if ts:
                timestamps.append(ts)

            # Capture the agent's initial prompt (first user record's content). Used
            # by G5 (handoff lineage) to check whether the upstream agent's output
            # actually arrived in this agent's prompt.
            if rec.get("type") == "user":
                if ts:
                    user_timestamps.append(ts)
                if not first_user_prompt:
                    content = rec.get("message", {}).get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            b.get("text", "")
                            for b in content
                            if isinstance(b, dict) and b.get("type") in ("text", None)
                        )
                    if isinstance(content, str):
                        first_user_prompt = content

            if rec.get("type") != "assistant":
                continue

            req_id = rec.get("requestId", "")
            msg = rec.get("message", {})
            usage = msg.get("usage", {})
            if model is None:
                model = msg.get("model") or None

            if req_id:
                turns.add(req_id)
                # Last record per requestId has the final output_tokens (earlier
                # streaming records have output_tokens=1).
                if usage.get("output_tokens", 0) > 0 or req_id not in token_usage:
                    token_usage[req_id] = usage

            for block in msg.get("content", []):
                btype = block.get("type", "")

                if btype == "text":
                    last_text = block.get("text", "")

                elif btype == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1
                    inp = block.get("input", {})

                    if first_tool_ts is None and ts:
                        first_tool_ts = ts
                    if req_id:
                        tool_uses_per_turn[req_id] += 1

                    # H4: identical (tool, input) signatures with no intervening
                    # workspace mutation. Edit/Write clears the span first, so a
                    # re-run after a change never counts as a duplicate.
                    if tool_name in ("Edit", "Write"):
                        span_signatures.clear()
                    try:
                        sig = (tool_name, json.dumps(inp, sort_keys=True, default=str))
                    except (TypeError, ValueError):
                        sig = (tool_name, repr(inp))
                    span_signatures[sig] += 1
                    if span_signatures[sig] > 1:
                        repeated_counts[sig] = max(repeated_counts.get(sig, 1), span_signatures[sig])
                    if sig not in tool_signature_samples:
                        tool_signature_samples[sig] = inp

                    # H5: file re-read. Same path Read ≥3× without an intervening
                    # Edit/Write resets the counter — the agent has the content,
                    # re-Reading is wasted context. Edit/Write to that path
                    # invalidates prior knowledge so subsequent reads are justified.
                    if tool_name == "Read":
                        rp = inp.get("file_path", "")
                        if rp:
                            read_count_for_path[rp] += 1
                            if read_count_for_path[rp] >= 3 and rp not in h5_flagged:
                                h5_flagged.add(rp)
                                violations.append({
                                    "check": "H5",
                                    "detail": f"Read {rp} ≥3× without intervening Edit/Write",
                                })
                    elif tool_name in ("Edit", "Write"):
                        wp = inp.get("file_path", "")
                        if wp:
                            read_count_for_path[wp] = 0
                            h5_flagged.discard(wp)

                    # O3: capture mid-task skill invocations for the
                    # "skill invoked but not preloaded" check.
                    if tool_name == "Skill":
                        skill_ref = inp.get("skill") or inp.get("name") or ""
                        if isinstance(skill_ref, str) and skill_ref:
                            skills_invoked.add(skill_ref)

                    # H1: suspect path access (dependency trees, other sessions'
                    # transcripts). Reading project source is never flagged.
                    if tool_name in ("Read", "Bash"):
                        path_to_check = inp.get("file_path", "") if tool_name == "Read" else inp.get("command", "")
                        if path_to_check and is_suspect_path(path_to_check):
                            violations.append({
                                "check": "H1",
                                "detail": f"{tool_name} on suspect path: {path_to_check[:120]}",
                            })

                    # H2: shell loop usage
                    if tool_name == "Bash":
                        cmd = inp.get("command", "")
                        if re.search(r"\b(for|while|until)\b.*\bdo\b", cmd, re.DOTALL):
                            violations.append({
                                "check": "H2",
                                "detail": f"Shell loop in Bash: {cmd[:80]}",
                            })

                    # G1 / H3: artifact written. Edit and Write both count.
                    if tool_name in ("Write", "Edit") and expected_artifacts:
                        file_path = inp.get("file_path", "")
                        if artifact_match(file_path, expected_artifacts):
                            matched_artifacts.add(file_path)
                            # H3: only enforced on Write (Edit modifies existing file).
                            if tool_name == "Write" and h3_pattern:
                                content = inp.get("content", "")
                                if content and not h3_pattern.search(content):
                                    violations.append({
                                        "check": "H3",
                                        "detail": f"Artifact file missing required header: {file_path}",
                                    })

    result_status = None
    if handoff_re:
        m = handoff_re.search(last_text)
        if m:
            # First non-None capture group across the alternation.
            result_status = next((g for g in m.groups() if g), None)

    # Aggregate tokens. cache_read sums across turns (each turn is billed for the
    # cache it re-reads). Cache writes are tracked per TTL — the `cache_creation`
    # breakdown is authoritative; the legacy `cache_creation_input_tokens` total
    # is only used when the breakdown is absent (it duplicates the breakdown, so
    # adding both would double-count). Peak context includes cache writes — a
    # first turn that writes 100k to cache held those tokens in its window.
    total_tokens = {"input": 0, "output": 0, "cache_read": 0,
                    "cache_write_5m": 0, "cache_write_1h": 0}
    peak_context = 0
    for usage in token_usage.values():
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cr  = usage.get("cache_read_input_tokens", 0)
        cc  = usage.get("cache_creation", {})
        cw5 = cc.get("ephemeral_5m_input_tokens", 0)
        cw1 = cc.get("ephemeral_1h_input_tokens", 0)
        if not cw5 and not cw1:
            cw5 = usage.get("cache_creation_input_tokens", 0)
        total_tokens["input"]         += inp
        total_tokens["output"]        += out
        total_tokens["cache_read"]    += cr
        total_tokens["cache_write_5m"] += cw5
        total_tokens["cache_write_1h"] += cw1
        peak_context = max(peak_context, inp + out + cr + cw5 + cw1)

    cache_write_total = total_tokens["cache_write_5m"] + total_tokens["cache_write_1h"]
    rate_key, _ = rates_for_model(model)
    cost_usd = compute_cost_usd(model, total_tokens)

    duration_s = None
    if len(timestamps) >= 2:
        try:
            def _parse(s):
                s = s.rstrip("Z").split(".")[0]
                return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
            duration_s = (_parse(max(timestamps)) - _parse(min(timestamps))).total_seconds()
        except Exception:
            pass

    turn_count = len(turns)
    output_tokens_total = total_tokens["output"]
    billed_tokens_total = sum(total_tokens.values())

    # H4: collect duplicate tool-call signatures (count > 1 within one
    # mutation-free span — see span_signatures above).
    repeated_calls = []
    for sig, count in repeated_counts.items():
        tool_name, _ = sig
        sample = tool_signature_samples.get(sig, {})
        preview = (sample.get("file_path")
                   or sample.get("command")
                   or sample.get("path")
                   or sample.get("pattern")
                   or "")
        repeated_calls.append({
            "tool": tool_name,
            "count": count,
            "preview": str(preview)[:120],
        })
        violations.append({
            "check": "H4",
            "detail": f"{tool_name} called {count}× with identical input and no intervening edit: {str(preview)[:100]}",
        })

    # F6: cache hit ratio over the turn-aggregated input. cache_read counts the
    # cached portion of each turn's prompt; input counts the uncached portion.
    cache_denom = total_tokens["input"] + total_tokens["cache_read"]
    cache_hit_ratio = (total_tokens["cache_read"] / cache_denom) if cache_denom > 0 else None

    # F8: tool churn ratio (total tool calls / distinct tools). High values on a
    # large call count indicate the agent is stuck in one tool pattern.
    total_tool_calls = sum(tool_calls.values())
    distinct_tools = len(tool_calls)
    tool_churn_ratio = (total_tool_calls / distinct_tools) if distinct_tools > 0 else None

    # F9: time-to-first-tool. Gap between the agent's first user record and its
    # first tool_use. High = excessive thinking before action.
    time_to_first_tool_s = None
    if first_tool_ts and user_timestamps:
        t_user = _parse_ts(min(user_timestamps))
        t_tool = _parse_ts(first_tool_ts)
        if t_user and t_tool:
            time_to_first_tool_s = max(0.0, (t_tool - t_user).total_seconds())

    # F10: empty/no-tool turns. Turns where the agent produced text but invoked
    # no tools. A small number is normal (e.g. the final return), but a high
    # ratio signals a stuck agent talking to itself.
    empty_turns = sum(1 for r in turns if tool_uses_per_turn.get(r, 0) == 0)

    return {
        "agent_id": agent_id,
        "description": description,
        "agent_type": agent_type,
        "role": role,
        "model": model,
        "rate_key": rate_key,
        "output_tokens": output_tokens_total,
        "peak_context_tokens": peak_context,
        "billed_tokens": billed_tokens_total,
        "tokens": {
            "input":          total_tokens["input"],
            "output":         total_tokens["output"],
            "cache_read":     total_tokens["cache_read"],
            "cache_write":    cache_write_total,
            "cache_write_5m": total_tokens["cache_write_5m"],
            "cache_write_1h": total_tokens["cache_write_1h"],
        },
        "cache_hit_ratio": round(cache_hit_ratio, 3) if cache_hit_ratio is not None else None,
        "cost_usd": round(cost_usd, 4),
        "turns": turn_count,
        "tool_calls": tool_calls,
        "tool_churn_ratio": round(tool_churn_ratio, 2) if tool_churn_ratio is not None else None,
        "repeated_tool_calls": sorted(repeated_calls, key=lambda r: -r["count"]),
        "time_to_first_tool_s": round(time_to_first_tool_s, 1) if time_to_first_tool_s is not None else None,
        "empty_turns": empty_turns,
        "duration_s": duration_s,
        "timestamps": {
            "first": min(timestamps) if timestamps else None,
            "last":  max(timestamps) if timestamps else None,
        },
        "first_user_prompt": first_user_prompt[:4000],
        "first_user_prompt_chars": len(first_user_prompt),
        "last_text": last_text[:4000],
        "skills_invoked": sorted(skills_invoked),
        "expected_artifacts": expected_artifacts,
        "wrote_artifact": bool(matched_artifacts),
        "matched_artifact_paths": sorted(matched_artifacts),
        "has_handoff_declared": bool(handoff_re),
        "result_status": result_status,
        "violations": violations,
    }


# ── Check helpers ────────────────────────────────────────────────────────────

def agent_label(a):
    return a.get("description", "")[:30] or a["agent_id"]


# ── Checks ───────────────────────────────────────────────────────────────────

def run_checks(agents, dag_shape, discovered_agents=None):
    """F-, G-, H-, W-group checks across all evaluated agents."""
    checks = []
    eval_agents = [a for a in agents if "error" not in a]
    if not eval_agents:
        return checks
    discovered_agents = discovered_agents or {}

    # ── F: Efficiency ─────────────────────────────────────────────────────────

    # F1: Turn outlier (>2× median). Replaces the old budget-based F1/F2.
    # Only fires with ≥4 agents (median is unstable below).
    turn_values = [a["turns"] for a in eval_agents]
    if len(turn_values) >= 4:
        median_turns = statistics.median(turn_values)
        outliers = [a for a in eval_agents if a["turns"] > 2 * median_turns]
        if outliers and median_turns > 0:
            detail = ", ".join(f"{agent_label(a)} ({a['turns']} turns)" for a in outliers)
            checks.append({
                "id": "F1", "group": "efficiency", "name": "Turn outliers (>2× median)",
                "status": "WARN", "value": len(outliers),
                "detail": f"median={median_turns:.0f} | outliers: {detail}",
            })
        else:
            checks.append({
                "id": "F1", "group": "efficiency", "name": "Turn outliers (>2× median)",
                "status": "PASS", "value": 0,
                "detail": f"median={median_turns:.0f} | no agent exceeded 2× median",
            })
    else:
        checks.append({
            "id": "F1", "group": "efficiency", "name": "Turn outliers (>2× median)",
            "status": "SKIP", "value": None,
            "detail": f"Need ≥4 agents for stable median (have {len(turn_values)})",
        })

    # F3: Cost per artifact (informational)
    with_artifact = [a for a in eval_agents if a.get("wrote_artifact")]
    total_cost = sum(a["cost_usd"] for a in eval_agents)
    if with_artifact:
        cost_per = total_cost / len(with_artifact)
        f3_detail = f"${cost_per:.3f}/artifact ({len(with_artifact)} artifacts, ${total_cost:.3f} total)"
        f3_value = round(cost_per, 4)
    else:
        f3_detail = f"No artifacts written; total cost ${total_cost:.3f}"
        f3_value = None
    checks.append({
        "id": "F3", "group": "efficiency", "name": "Cost per output artifact",
        "status": "INFO", "value": f3_value, "detail": f3_detail,
    })

    # F4: Context-size outlier (>2× median peak_context). Using peak_context — not
    # billed_tokens — so long-running agents with heavy cache_read aren't punished
    # for being efficient. The signal is "this agent loaded a much bigger workspace
    # than its peers", which is what context-size outliers actually mean.
    tok_pairs = [(a, a["peak_context_tokens"]) for a in eval_agents]
    tok_values = [t for _, t in tok_pairs]
    if len(tok_values) >= 2:
        median_tok = statistics.median(tok_values)
        outliers = [(a, t) for a, t in tok_pairs if t > 2 * median_tok]
        if outliers:
            detail = ", ".join(f"{agent_label(a)} ({t:,})" for a, t in outliers)
            checks.append({
                "id": "F4", "group": "efficiency", "name": "Context outliers (>2× median peak)",
                "status": "WARN", "value": len(outliers),
                "detail": f"median={int(median_tok):,} | outliers: {detail}",
            })
        else:
            top = ", ".join(f"{agent_label(a)} ({t:,})" for a, t in sorted(tok_pairs, key=lambda x: -x[1])[:3])
            checks.append({
                "id": "F4", "group": "efficiency", "name": "Context outliers (>2× median peak)",
                "status": "PASS", "value": 0,
                "detail": f"median={int(median_tok):,} | top agents: {top}",
            })
    else:
        checks.append({
            "id": "F4", "group": "efficiency", "name": "Context outliers (>2× median peak)",
            "status": "SKIP", "value": None, "detail": "Need ≥2 agents for comparison",
        })

    # F5: Duration spread
    durations = [a["duration_s"] for a in eval_agents if a.get("duration_s") is not None]
    if len(durations) >= 2:
        d_min, d_max = min(durations), max(durations)
        spread = d_max / d_min if d_min > 0 else None
        f5_status = "WARN" if spread and spread > 5 else "PASS"
        checks.append({
            "id": "F5", "group": "efficiency", "name": "Duration spread (max/min)",
            "status": f5_status,
            "value": round(spread, 1) if spread else None,
            "detail": f"{spread:.1f}× spread (min={d_min:.0f}s, max={d_max:.0f}s)" if spread else "N/A",
        })
    else:
        checks.append({
            "id": "F5", "group": "efficiency", "name": "Duration spread (max/min)",
            "status": "SKIP", "value": None, "detail": "Insufficient duration data",
        })

    # F6: Cache hit ratio. Only meaningful for agents with multiple turns — a
    # 1-turn agent has no opportunity to cache. WARN when an agent doing real
    # work (≥3 turns, ≥50k input+cache_read) reads <30% from cache.
    f6_significant = [
        a for a in eval_agents
        if a.get("cache_hit_ratio") is not None
        and a["turns"] >= 3
        and (a["tokens"]["input"] + a["tokens"]["cache_read"]) >= 50_000
    ]
    if f6_significant:
        low = [a for a in f6_significant if a["cache_hit_ratio"] < 0.30]
        weighted_num = sum(a["tokens"]["cache_read"] for a in f6_significant)
        weighted_den = sum(a["tokens"]["input"] + a["tokens"]["cache_read"] for a in f6_significant)
        weighted = (weighted_num / weighted_den) if weighted_den > 0 else None
        if low:
            detail = ", ".join(f"{agent_label(a)} ({a['cache_hit_ratio']:.0%})" for a in low)
            checks.append({
                "id": "F6", "group": "efficiency", "name": "Cache hit ratio",
                "status": "WARN", "value": round(weighted, 3) if weighted is not None else None,
                "detail": f"weighted avg {weighted:.0%} | low: {detail}" if weighted is not None else detail,
            })
        else:
            checks.append({
                "id": "F6", "group": "efficiency", "name": "Cache hit ratio",
                "status": "PASS", "value": round(weighted, 3) if weighted is not None else None,
                "detail": f"weighted avg {weighted:.0%} across {len(f6_significant)} multi-turn agents" if weighted is not None else "N/A",
            })
    else:
        checks.append({
            "id": "F6", "group": "efficiency", "name": "Cache hit ratio",
            "status": "SKIP", "value": None,
            "detail": "No agents with ≥3 turns and ≥50k input+cache_read",
        })

    # F7: Model right-sizing. Terminal/writer roles (-pm, -log) on Opus or
    # Fable is almost always overkill — these agents do mechanical
    # writes/handoffs and don't need frontier reasoning. Reviewer/producer on
    # a big model is fine. SKIP when discovery couldn't infer roles.
    over_provisioned_roles = {"terminal", "writer"}
    big_model_keys = ("opus", "fable")
    role_aware = [a for a in eval_agents if a.get("role") in {"producer", "reviewer", "terminal", "writer", "free-form", "unknown"}]
    if role_aware:
        flagged = [
            a for a in eval_agents
            if a.get("role") in over_provisioned_roles
            and a.get("model") and any(k in a["model"].lower() for k in big_model_keys)
        ]
        if flagged:
            detail = ", ".join(f"{agent_label(a)} ({a['role']} on {a['model']})" for a in flagged)
            checks.append({
                "id": "F7", "group": "efficiency", "name": "Model right-sizing",
                "status": "WARN", "value": len(flagged),
                "detail": f"Terminal/writer agent on Opus/Fable: {detail}",
            })
        else:
            checks.append({
                "id": "F7", "group": "efficiency", "name": "Model right-sizing",
                "status": "PASS", "value": 0,
                "detail": "No terminal/writer agents on Opus/Fable",
            })
    else:
        checks.append({
            "id": "F7", "group": "efficiency", "name": "Model right-sizing",
            "status": "SKIP", "value": None, "detail": "No discovered roles to compare against",
        })

    # F8: Tool churn ratio (calls / distinct tools). High = agent stuck on one
    # tool — e.g. 30 Bash calls with only 2 distinct tools used. Threshold floor
    # of 10 calls avoids flagging short agents with naturally small tool variety.
    f8_eligible = [a for a in eval_agents if a.get("tool_churn_ratio") is not None
                   and sum(a.get("tool_calls", {}).values()) >= 10]
    if f8_eligible:
        flagged = [a for a in f8_eligible if a["tool_churn_ratio"] > 10.0]
        if flagged:
            detail = ", ".join(f"{agent_label(a)} ({a['tool_churn_ratio']:.1f}× across {len(a['tool_calls'])} tools)" for a in flagged)
            checks.append({
                "id": "F8", "group": "efficiency", "name": "Tool churn ratio",
                "status": "WARN", "value": len(flagged),
                "detail": f"High tool repetition: {detail}",
            })
        else:
            avg = sum(a["tool_churn_ratio"] for a in f8_eligible) / len(f8_eligible)
            checks.append({
                "id": "F8", "group": "efficiency", "name": "Tool churn ratio",
                "status": "PASS", "value": round(avg, 2),
                "detail": f"avg {avg:.1f}× across {len(f8_eligible)} agents (≥10 tool calls)",
            })
    else:
        checks.append({
            "id": "F8", "group": "efficiency", "name": "Tool churn ratio",
            "status": "SKIP", "value": None, "detail": "No agents with ≥10 tool calls",
        })

    # F9: Time-to-first-tool. Long gap between agent start and first tool call =
    # excessive thinking before action. Threshold 60s — adaptive-thinking models
    # legitimately reason for tens of seconds on hard tasks before acting.
    # SKIP if no agent has both timestamps available.
    f9_eligible = [a for a in eval_agents if a.get("time_to_first_tool_s") is not None]
    if f9_eligible:
        slow = [a for a in f9_eligible if a["time_to_first_tool_s"] > 60]
        if slow:
            detail = ", ".join(f"{agent_label(a)} ({a['time_to_first_tool_s']:.0f}s)" for a in slow)
            checks.append({
                "id": "F9", "group": "efficiency", "name": "Time-to-first-tool",
                "status": "WARN", "value": len(slow),
                "detail": f"Slow start: {detail}",
            })
        else:
            avg = sum(a["time_to_first_tool_s"] for a in f9_eligible) / len(f9_eligible)
            checks.append({
                "id": "F9", "group": "efficiency", "name": "Time-to-first-tool",
                "status": "PASS", "value": round(avg, 1),
                "detail": f"avg {avg:.1f}s across {len(f9_eligible)} agents",
            })
    else:
        checks.append({
            "id": "F9", "group": "efficiency", "name": "Time-to-first-tool",
            "status": "SKIP", "value": None, "detail": "No timestamp pairs available",
        })

    # F10: Empty/no-tool turn ratio. >30% empty on a multi-turn agent suggests
    # the model is talking to itself instead of advancing the task. One trailing
    # text-only turn (the final return) is normal, so the floor is 5 turns.
    f10_eligible = [a for a in eval_agents if a["turns"] >= 5]
    if f10_eligible:
        flagged = []
        for a in f10_eligible:
            ratio = a["empty_turns"] / a["turns"]
            if ratio > 0.30 and a["empty_turns"] >= 3:
                flagged.append((a, ratio))
        if flagged:
            detail = ", ".join(f"{agent_label(a)} ({a['empty_turns']}/{a['turns']} = {r:.0%})" for a, r in flagged)
            checks.append({
                "id": "F10", "group": "efficiency", "name": "Empty (no-tool) turns",
                "status": "WARN", "value": len(flagged),
                "detail": f"High text-only turn ratio: {detail}",
            })
        else:
            checks.append({
                "id": "F10", "group": "efficiency", "name": "Empty (no-tool) turns",
                "status": "PASS", "value": 0,
                "detail": f"All {len(f10_eligible)} multi-turn agents stayed under 30% empty",
            })
    else:
        checks.append({
            "id": "F10", "group": "efficiency", "name": "Empty (no-tool) turns",
            "status": "SKIP", "value": None, "detail": "No agents with ≥5 turns",
        })

    # ── G: Reliability ────────────────────────────────────────────────────────

    # G1: Silent failure — agents with discovered artifact_paths that didn't write any.
    artifact_agents = [a for a in eval_agents if a.get("expected_artifacts")]
    if artifact_agents:
        silent = [a for a in artifact_agents if not a.get("wrote_artifact")]
        if silent:
            checks.append({
                "id": "G1", "group": "reliability", "name": "Silent failures",
                "status": "FAIL", "value": len(silent),
                "detail": f"Expected artifact not written: {[agent_label(a) for a in silent]}",
            })
        else:
            checks.append({
                "id": "G1", "group": "reliability", "name": "Silent failures",
                "status": "PASS", "value": 0,
                "detail": f"All {len(artifact_agents)} agents with declared artifacts wrote them",
            })
    else:
        checks.append({
            "id": "G1", "group": "reliability", "name": "Silent failures",
            "status": "SKIP", "value": None,
            "detail": "No agents declare an output artifact in .claude/agents/*.md",
        })

    # G2: Result completeness — agents with a declared handoff format must produce one.
    handoff_agents = [a for a in eval_agents if a.get("has_handoff_declared")]
    if handoff_agents:
        no_result = [a for a in handoff_agents if a.get("result_status") is None]
        if no_result:
            g2_status = "WARN"
            g2_detail = f"No parseable handoff Status: {[agent_label(a) for a in no_result]}"
        else:
            g2_status = "PASS"
            g2_detail = f"All {len(handoff_agents)} agents with declared handoffs returned a Status"
        checks.append({
            "id": "G2", "group": "reliability", "name": "Result completeness",
            "status": g2_status,
            "value": len(handoff_agents) - len(no_result),
            "detail": g2_detail,
        })
    else:
        checks.append({
            "id": "G2", "group": "reliability", "name": "Result completeness",
            "status": "SKIP", "value": None,
            "detail": "No agents declare a handoff Status format in .claude/agents/*.md",
        })

    # G3: Failure-status rate (informational). Statuses are discovered per
    # project, so "failure" is matched by token (blocked/failed/retry/error)
    # rather than a hardcoded vocabulary. Also reports the full distribution.
    failure_re = re.compile(r"(block|fail|retry|error|abort)", re.IGNORECASE)
    failed = [a for a in eval_agents
              if a.get("result_status") and failure_re.search(a["result_status"])]
    dist = {}
    for a in eval_agents:
        s = a.get("result_status") or "unknown"
        dist[s] = dist.get(s, 0) + 1
    dist_str = ", ".join(f"{k}: {v}" for k, v in sorted(dist.items()))
    checks.append({
        "id": "G3", "group": "reliability", "name": "Failure-status rate",
        "status": "INFO", "value": round(len(failed) / len(eval_agents), 2),
        "detail": f"{len(failed)}/{len(eval_agents)} agents ended in a failure-like status | {dist_str}",
    })

    # G4: Unknown outcomes — declared handoff or artifact, but produced neither.
    expected_output = [
        a for a in eval_agents
        if a.get("has_handoff_declared") or a.get("expected_artifacts")
    ]
    unknown = [
        a for a in expected_output
        if a.get("result_status") is None and not a.get("wrote_artifact")
    ]
    if expected_output:
        if unknown:
            checks.append({
                "id": "G4", "group": "reliability", "name": "Unknown outcomes",
                "status": "FAIL", "value": len(unknown),
                "detail": f"No status, no artifact: {[agent_label(a) for a in unknown]}",
            })
        else:
            checks.append({
                "id": "G4", "group": "reliability", "name": "Unknown outcomes",
                "status": "PASS", "value": 0, "detail": "No unknown outcomes",
            })
    else:
        checks.append({
            "id": "G4", "group": "reliability", "name": "Unknown outcomes",
            "status": "SKIP", "value": None,
            "detail": "No agents declare handoff or artifact — all returns are free-form",
        })

    # G5: Handoff content lineage. For each consecutive agent pair sorted by
    # spawn time, check whether the upstream's last_text shows up in the
    # downstream's first user prompt. Looks for any of:
    #   - file paths (e.g. docs/foo.md, src/bar.tsx)
    #   - Status: <value> tokens
    #   - quoted/backticked identifiers
    # If 0 of these tokens cross the boundary, the orchestrator likely passed a
    # fresh task that doesn't reference the upstream's output. INFO-only — this
    # is sometimes legitimate (clean re-prompting) but often means lost context.
    if len(eval_agents) >= 2:
        sorted_agents = sorted(
            eval_agents,
            key=lambda a: a.get("timestamps", {}).get("first") or "",
        )
        path_re = re.compile(r"[\w./-]+\.[a-zA-Z]{1,6}\b")
        backtick_re = re.compile(r"`([^`\n]{3,80})`")
        status_re = re.compile(r"\*\*Status:\*\*\s*([A-Za-z][\w-]*)")
        transitions = 0
        with_lineage = 0
        broken = []
        for i in range(1, len(sorted_agents)):
            up = sorted_agents[i - 1]
            dn = sorted_agents[i]
            up_text = (up.get("last_text") or "").strip()
            dn_prompt = (dn.get("first_user_prompt") or "").strip()
            if not up_text or not dn_prompt:
                continue
            transitions += 1
            tokens = set()
            tokens.update(m.group(0) for m in path_re.finditer(up_text))
            tokens.update(m.group(1) for m in backtick_re.finditer(up_text))
            tokens.update(m.group(0) for m in status_re.finditer(up_text))
            # Strip very common, low-signal tokens (e.g. ".md" alone).
            tokens = {t for t in tokens if len(t) >= 4}
            if any(t in dn_prompt for t in tokens):
                with_lineage += 1
            else:
                broken.append(f"{agent_label(up)} → {agent_label(dn)}")
        if transitions == 0:
            checks.append({
                "id": "G5", "group": "reliability", "name": "Handoff content lineage",
                "status": "SKIP", "value": None,
                "detail": "No consecutive agent pairs had both last_text and first_prompt",
            })
        else:
            ratio = with_lineage / transitions
            checks.append({
                "id": "G5", "group": "reliability", "name": "Handoff content lineage",
                "status": "INFO", "value": round(ratio, 2),
                "detail": (f"{with_lineage}/{transitions} transitions carried lineage tokens "
                           f"({ratio:.0%})" + (f" | breaks: {broken[:3]}" if broken else "")),
            })
    else:
        checks.append({
            "id": "G5", "group": "reliability", "name": "Handoff content lineage",
            "status": "SKIP", "value": None, "detail": "Need ≥2 agents",
        })

    # ── H: Behavioral Compliance ──────────────────────────────────────────────

    # H1: suspect path access — always on (patterns are suspect in any project
    # type). WARN, not FAIL: wasteful/noisy, but not a broken pipeline.
    h1_viols = [v for a in eval_agents for v in a.get("violations", []) if v["check"] == "H1"]
    if h1_viols:
        checks.append({
            "id": "H1", "group": "behavioral", "name": "Suspect path access",
            "status": "WARN", "value": len(h1_viols),
            "detail": f"{len(h1_viols)} access(es) to node_modules / other-session transcripts: {h1_viols[0]['detail'][:100]}",
        })
    else:
        checks.append({
            "id": "H1", "group": "behavioral", "name": "Suspect path access",
            "status": "PASS", "value": 0,
            "detail": "No dependency-tree or transcript-directory access detected",
        })

    # H2: shell loops are legitimate in generic workflows — reported as INFO
    # for visibility, never as a violation.
    h2_viols = [v for a in eval_agents for v in a.get("violations", []) if v["check"] == "H2"]
    if h2_viols:
        checks.append({
            "id": "H2", "group": "behavioral", "name": "Shell loop usage",
            "status": "INFO", "value": len(h2_viols),
            "detail": f"{len(h2_viols)} shell loop(s) used (informational)",
        })
    else:
        checks.append({
            "id": "H2", "group": "behavioral", "name": "Shell loop usage",
            "status": "INFO", "value": 0, "detail": "No shell loops detected",
        })

    # H3: artifact header format — gated on discovery finding a header template
    # in a log skill's SKILL.md. No template discovered → SKIP, not a guess.
    h3_gated = [a for a in eval_agents
                if build_artifact_header_regex(discovered_agents.get(a.get("agent_type"), {}))]
    if h3_gated:
        h3_viols = [v for a in eval_agents for v in a.get("violations", []) if v["check"] == "H3"]
        if h3_viols:
            checks.append({
                "id": "H3", "group": "behavioral", "name": "Output artifact format",
                "status": "WARN", "value": len(h3_viols),
                "detail": f"{len(h3_viols)} artifact(s) missing the header discovered from the log skill",
            })
        else:
            checks.append({
                "id": "H3", "group": "behavioral", "name": "Output artifact format",
                "status": "PASS", "value": 0, "detail": "All artifacts match the discovered header template",
            })
    else:
        checks.append({
            "id": "H3", "group": "behavioral", "name": "Output artifact format",
            "status": "SKIP", "value": None,
            "detail": "No artifact header template discoverable from log skills",
        })

    # H5: File re-read. Same path Read ≥3× without an intervening Edit/Write
    # is wasted context — the agent already has the file. Tracked inline during
    # per-agent parsing (read counter resets on Edit/Write to that path).
    h5_viols = [v for a in eval_agents for v in a.get("violations", []) if v["check"] == "H5"]
    if h5_viols:
        agents_with = sorted({
            agent_label(a) for a in eval_agents
            if any(v["check"] == "H5" for v in a.get("violations", []))
        })
        checks.append({
            "id": "H5", "group": "behavioral", "name": "File re-read without edit",
            "status": "WARN", "value": len(h5_viols),
            "detail": f"{len(h5_viols)} re-read(s) across {len(agents_with)} agent(s) ({agents_with[:3]})",
        })
    else:
        checks.append({
            "id": "H5", "group": "behavioral", "name": "File re-read without edit",
            "status": "PASS", "value": 0, "detail": "No file re-reads detected",
        })

    # H4: Repeated identical tool calls. Two calls with the same (tool, input)
    # in one agent are almost always wasted work — the agent forgot it already
    # made the call. Different inputs to the same tool are not flagged.
    h4_agents = [a for a in eval_agents if a.get("repeated_tool_calls")]
    if h4_agents:
        total_dups = sum(
            sum(r["count"] - 1 for r in a["repeated_tool_calls"])
            for a in h4_agents
        )
        worst = max(
            (r for a in h4_agents for r in a["repeated_tool_calls"]),
            key=lambda r: r["count"],
        )
        labels = ", ".join(agent_label(a) for a in h4_agents)
        checks.append({
            "id": "H4", "group": "behavioral", "name": "Repeated identical tool calls",
            "status": "WARN", "value": total_dups,
            "detail": f"{total_dups} duplicate call(s) across {len(h4_agents)} agent(s) ({labels}); worst: {worst['tool']} ×{worst['count']}",
        })
    else:
        checks.append({
            "id": "H4", "group": "behavioral", "name": "Repeated identical tool calls",
            "status": "PASS", "value": 0, "detail": "No duplicate (tool, input) pairs detected",
        })

    # ── W: Workflow Efficiency ────────────────────────────────────────────────

    checks.extend(_run_workflow_checks(eval_agents, dag_shape, discovered_agents))
    return checks


def _parse_ts(s):
    if not s:
        return None
    try:
        s = s.rstrip("Z").split(".")[0]
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _run_workflow_checks(eval_agents, dag_shape, discovered_agents=None):
    """W1, W3–W5, W7. W3/W4 are downgraded to INFO when the project's DAG is sequential."""
    checks = []
    discovered_agents = discovered_agents or {}

    all_first = [_parse_ts(a["timestamps"]["first"]) for a in eval_agents if a.get("timestamps", {}).get("first")]
    all_last  = [_parse_ts(a["timestamps"]["last"])  for a in eval_agents if a.get("timestamps", {}).get("last")]

    # W1: Total workflow duration
    if all_first and all_last:
        workflow_start = min(t for t in all_first if t)
        workflow_end   = max(t for t in all_last  if t)
        workflow_duration = (workflow_end - workflow_start).total_seconds()
        sum_agent_duration = sum(a["duration_s"] for a in eval_agents if a.get("duration_s") is not None)
        checks.append({
            "id": "W1", "group": "workflow", "name": "Total workflow duration",
            "status": "INFO",
            "value": round(workflow_duration, 1),
            "detail": f"Wall time: {workflow_duration:.0f}s; sum of agent durations: {sum_agent_duration:.0f}s",
        })
    else:
        checks.append({
            "id": "W1", "group": "workflow", "name": "Total workflow duration",
            "status": "SKIP", "value": None, "detail": "Insufficient timestamp data",
        })

    agent_windows = []
    for a in eval_agents:
        t_first = _parse_ts(a.get("timestamps", {}).get("first"))
        t_last  = _parse_ts(a.get("timestamps", {}).get("last"))
        if t_first and t_last:
            agent_windows.append((t_first, t_last))

    sequential_pipeline = (dag_shape == "sequential")

    # W3: Parallel efficiency
    if len(agent_windows) >= 2:
        events = []
        for start, end in agent_windows:
            events.append((start, +1))
            events.append((end, -1))
        events.sort(key=lambda x: x[0])
        current = 0
        max_concurrent = 0
        for _, delta in events:
            current += delta
            max_concurrent = max(max_concurrent, current)
        max_possible = len(agent_windows)
        parallel_ratio = max_concurrent / max_possible
        if sequential_pipeline:
            # Declared sequential → low concurrency is by design; report INFO.
            w3_status = "INFO"
            w3_detail = (f"Max concurrent: {max_concurrent}/{max_possible} ({parallel_ratio:.0%}) "
                         f"— pipeline declared sequential")
        elif parallel_ratio < 0.3:
            w3_status = "WARN"
            w3_detail = f"Max concurrent: {max_concurrent}/{max_possible} agents ({parallel_ratio:.0%})"
        else:
            w3_status = "PASS"
            w3_detail = f"Max concurrent: {max_concurrent}/{max_possible} agents ({parallel_ratio:.0%})"
        checks.append({
            "id": "W3", "group": "workflow", "name": "Parallel efficiency",
            "status": w3_status, "value": round(parallel_ratio, 2), "detail": w3_detail,
        })
    else:
        checks.append({
            "id": "W3", "group": "workflow", "name": "Parallel efficiency",
            "status": "SKIP", "value": None, "detail": "Need ≥2 agents with timestamps",
        })

    # W4: Sequential bottlenecks
    serial_agents = []
    if len(agent_windows) >= 2:
        for i, (s1, e1) in enumerate(agent_windows):
            overlaps = False
            for j, (s2, e2) in enumerate(agent_windows):
                if i == j:
                    continue
                if s1 < e2 and s2 < e1:
                    overlaps = True
                    break
            if not overlaps:
                serial_agents.append(agent_label(eval_agents[i]))

    if len(agent_windows) >= 2:
        if serial_agents:
            ratio = len(serial_agents) / len(eval_agents)
            if sequential_pipeline:
                w4_status = "INFO"
                w4_detail = (f"{len(serial_agents)} agents ran with no overlap — "
                             f"pipeline declared sequential")
            elif ratio > 0.5:
                w4_status = "WARN"
                w4_detail = f"{len(serial_agents)} of {len(eval_agents)} agents had no overlap: {serial_agents[:5]}"
            else:
                w4_status = "INFO"
                w4_detail = f"{len(serial_agents)} agents ran with no overlap: {serial_agents[:5]}"
            checks.append({
                "id": "W4", "group": "workflow", "name": "Sequential bottlenecks",
                "status": w4_status, "value": len(serial_agents), "detail": w4_detail,
            })
        else:
            checks.append({
                "id": "W4", "group": "workflow", "name": "Sequential bottlenecks",
                "status": "PASS", "value": 0, "detail": "No purely serial bottlenecks detected",
            })
    else:
        checks.append({
            "id": "W4", "group": "workflow", "name": "Sequential bottlenecks",
            "status": "SKIP", "value": None, "detail": "Insufficient data",
        })

    # W7: Spawn-order vs declared DAG. Forward edges come from each agent's
    # `upstreams` field ("Invoked after X" in description) — this is the only
    # unambiguous "must run after" signal. `downstreams` is unreliable for
    # ordering because it also captures failure-routing call sites (e.g.
    # qa.md "delegate back to dev" produces a qa→dev edge that isn't a
    # pipeline arrow but a fix-back loop).
    edges = []
    for name, meta in discovered_agents.items():
        for u in meta.get("upstreams", []):
            if u in discovered_agents and u != name:
                edges.append((u, name))
    spawn_first_ts = {}
    for a in eval_agents:
        t = _parse_ts(a.get("timestamps", {}).get("first"))
        atype = a.get("agent_type")
        if t and atype:
            if atype not in spawn_first_ts or t < spawn_first_ts[atype]:
                spawn_first_ts[atype] = t
    if not edges:
        checks.append({
            "id": "W7", "group": "workflow", "name": "Spawn-order vs declared DAG",
            "status": "SKIP", "value": None,
            "detail": "No declared agent-to-agent edges in .claude/agents/",
        })
    else:
        checked = 0
        violations_w7 = []
        for upstream, downstream in edges:
            if upstream not in spawn_first_ts or downstream not in spawn_first_ts:
                continue
            checked += 1
            if spawn_first_ts[upstream] > spawn_first_ts[downstream]:
                violations_w7.append(f"{downstream} spawned before {upstream}")
        if checked == 0:
            checks.append({
                "id": "W7", "group": "workflow", "name": "Spawn-order vs declared DAG",
                "status": "SKIP", "value": None,
                "detail": f"None of the {len(edges)} declared edges had both endpoints spawned",
            })
        elif violations_w7:
            checks.append({
                "id": "W7", "group": "workflow", "name": "Spawn-order vs declared DAG",
                "status": "FAIL", "value": len(violations_w7),
                "detail": f"{len(violations_w7)}/{checked} edge(s) violated: {violations_w7[:3]}",
            })
        else:
            checks.append({
                "id": "W7", "group": "workflow", "name": "Spawn-order vs declared DAG",
                "status": "PASS", "value": 0,
                "detail": f"All {checked} declared edges respected by spawn order",
            })

    # W5: Idle time within the workflow window
    if len(agent_windows) >= 2 and all_first and all_last:
        sorted_windows = sorted(agent_windows, key=lambda x: x[0])
        workflow_start = min(t for t in all_first if t)
        workflow_end   = max(t for t in all_last  if t)
        total_idle = 0.0
        for i in range(1, len(sorted_windows)):
            gap_start = sorted_windows[i - 1][1]
            gap_end   = sorted_windows[i][0]
            if gap_end > gap_start:
                covered = any(s <= gap_start and e >= gap_end for s, e in sorted_windows
                              if (s, e) != sorted_windows[i - 1])
                if not covered:
                    total_idle += (gap_end - gap_start).total_seconds()
        w5_duration = (workflow_end - workflow_start).total_seconds()
        idle_ratio = total_idle / w5_duration if w5_duration > 0 else 0
        w5_status = "WARN" if idle_ratio > 0.2 else "PASS"
        checks.append({
            "id": "W5", "group": "workflow", "name": "Idle time",
            "status": w5_status,
            "value": round(idle_ratio, 2),
            "detail": f"{total_idle:.0f}s idle of {w5_duration:.0f}s total ({idle_ratio:.0%})",
        })
    else:
        checks.append({
            "id": "W5", "group": "workflow", "name": "Idle time",
            "status": "SKIP", "value": None, "detail": "Insufficient timestamp data",
        })

    return checks


# ── Summary ──────────────────────────────────────────────────────────────────

def build_summary(agents, checks):
    eval_agents = [a for a in agents if "error" not in a]

    total_cost          = sum(a["cost_usd"] for a in eval_agents)
    tok_input           = sum(a["tokens"]["input"]       for a in eval_agents)
    tok_output          = sum(a["tokens"]["output"]      for a in eval_agents)
    tok_cache_r         = sum(a["tokens"]["cache_read"]  for a in eval_agents)
    tok_cache_w         = sum(a["tokens"]["cache_write"] for a in eval_agents)
    total_output        = sum(a.get("output_tokens", a["tokens"]["output"]) for a in eval_agents)
    total_billed        = sum(a["billed_tokens"] for a in eval_agents)
    # Headline metric: sum of each agent's peak context — matches what Claude Code
    # reports in agent returns ("35.2k tokens"). Counts each agent's loaded
    # context once rather than re-billing cache_read across turns.
    total_peak_context  = sum(a["peak_context_tokens"] for a in eval_agents)

    cache_denom = tok_input + tok_cache_r
    workflow_cache_hit = round(tok_cache_r / cache_denom, 3) if cache_denom > 0 else None

    status_counts = {}
    for a in eval_agents:
        s = a.get("result_status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1

    check_counts = {}
    for c in checks:
        key = c["status"].lower()
        check_counts[key] = check_counts.get(key, 0) + 1

    return {
        "agents_evaluated":            len(eval_agents),
        "total_peak_context_tokens":   total_peak_context,
        "total_output_tokens":         total_output,
        "total_billed_tokens":         total_billed,
        "total_tokens": {
            "input":       tok_input,
            "output":      tok_output,
            "cache_read":  tok_cache_r,
            "cache_write": tok_cache_w,
        },
        "workflow_cache_hit_ratio": workflow_cache_hit,
        "total_cost_usd":           round(total_cost, 4),
        "result_statuses":          status_counts,
        "checks":                   check_counts,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage: transcript-parser.py <session-id> <target-name> "
              "[--output-dir DIR] [--scan] [--compare BASELINE.json]",
              file=sys.stderr)
        sys.exit(1)

    session_id = sys.argv[1]
    target = sys.argv[2]
    do_scan = "--scan" in sys.argv
    compare_path = None
    if "--compare" in sys.argv:
        idx = sys.argv.index("--compare")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --compare requires a baseline JSON path", file=sys.stderr)
            sys.exit(1)
        compare_path = sys.argv[idx + 1]

    cwd = os.getcwd()
    project_dir = resolve_project_dir(cwd)
    parent_jsonl = os.path.join(project_dir, f"{session_id}.jsonl")
    subagent_dir = os.path.join(project_dir, session_id, "subagents")

    if not os.path.exists(parent_jsonl):
        print(f"ERROR: Parent JSONL not found: {parent_jsonl}", file=sys.stderr)
        sys.exit(1)

    project_types = detect_project_type(cwd)
    if project_types:
        print(f"INFO: Detected project types: {sorted(project_types)}", file=sys.stderr)

    discovery = discover_project(cwd)
    discovered_agents = discovery["agents"]
    dag_shape = discovery["dag_shape"]
    if discovered_agents:
        print(f"INFO: Discovered {len(discovered_agents)} agents in .claude/agents/ "
              f"(DAG: {dag_shape})", file=sys.stderr)
    else:
        print("INFO: No .claude/agents/ found — discovery-gated checks (G1, G2, G4) will SKIP",
              file=sys.stderr)

    task_map = parse_parent_jsonl(parent_jsonl)
    type_map = parse_task_type_map(parent_jsonl)
    if not task_map and not type_map:
        print("INFO: No queue-operation records in parent JSONL "
              "(expected for Claude Code Agent pipelines)", file=sys.stderr)

    notes = []
    undeclared_seen = set()

    def parse_session_agents(subdir, tmap, ttype_map):
        result = []
        for jsonl_path in sorted(glob.glob(os.path.join(subdir, "agent-*.jsonl"))):
            agent_id = os.path.basename(jsonl_path).replace("agent-", "").replace(".jsonl", "")

            # meta.json carries agentType + description (written by the Claude Code
            # runtime at spawn). Model is in the JSONL records, not meta.json.
            meta_path = os.path.join(subdir, f"agent-{agent_id}.meta.json")
            meta_agent_type = None
            meta_description = None
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as mf:
                        meta = json.load(mf)
                    meta_agent_type = meta.get("agentType") or None
                    meta_description = meta.get("description") or None
                except (json.JSONDecodeError, OSError):
                    pass

            agent_type = meta_agent_type or ttype_map.get(agent_id) or "agent"
            description = (meta_description or tmap.get(agent_id, "") or
                           extract_description_from_agent_jsonl(jsonl_path) or
                           f"Unknown agent {agent_id}")

            agent_meta = discovered_agents.get(agent_type, {})
            if discovered_agents and agent_type not in discovered_agents and agent_type != "agent":
                if agent_type not in undeclared_seen:
                    undeclared_seen.add(agent_type)
                    notes.append(f"agent '{agent_type}' spawned but not declared in .claude/agents/")

            result.append(parse_subagent_jsonl(
                jsonl_path, description, target, agent_type, agent_meta,
            ))
        return result

    agents = []
    if os.path.isdir(subagent_dir):
        agents = parse_session_agents(subagent_dir, task_map, type_map)
    else:
        print(f"WARNING: Subagent directory not found: {subagent_dir}", file=sys.stderr)

    if do_scan and not agents:
        print(f"INFO: No agents in session {session_id}, scanning sibling sessions...", file=sys.stderr)
        alt_session, alt_subagent_dir = scan_for_agent_session(project_dir, target)
        if alt_session:
            print(f"INFO: Found agent session {alt_session}, switching to it", file=sys.stderr)
            session_id = alt_session
            parent_jsonl = os.path.join(project_dir, f"{alt_session}.jsonl")
            alt_task_map = parse_parent_jsonl(parent_jsonl)
            alt_type_map = parse_task_type_map(parent_jsonl)
            agents = parse_session_agents(alt_subagent_dir, alt_task_map, alt_type_map)
        else:
            print(f"WARNING: --scan found no agent session for target '{target}'", file=sys.stderr)

    if not agents:
        print("ERROR: No subagent files found", file=sys.stderr)
        sys.exit(1)

    # Note any unknown models that fell back to default rates.
    unknown_models = sorted({
        a["model"] for a in agents
        if "error" not in a and a.get("model")
        and a.get("rate_key") == DEFAULT_RATE_KEY
        and DEFAULT_RATE_KEY not in a["model"].lower()
    })
    if unknown_models:
        notes.append(f"Unknown model(s) {unknown_models} — fell back to {DEFAULT_RATE_KEY} rates")

    checks = run_checks(agents, dag_shape, discovered_agents)

    # Static-conformance group (S). Always-on; uses CWD's .claude/ files.
    # Pass undeclared agent types so S15 can promote the existing `note`
    # to a first-class check.
    static_checks = run_static_checks(cwd, sorted(undeclared_seen))
    checks.extend(static_checks)

    # Orchestration efficiency group (O). Cross-references runtime per-agent
    # behavior with declared frontmatter to catch over-broad tool grants,
    # late skill loads, weak descriptions, bloated handoffs, and destructive
    # skills exposed to model invocation.
    eval_only = [a for a in agents if "error" not in a]
    orch_checks = run_orchestration_checks(cwd, eval_only)
    checks.extend(orch_checks)

    # Parent-session (orchestrator) analysis: W2 orchestrator overhead,
    # W8 spawn decision latency, O7 top-level source edits after delegation.
    parent = analyze_parent_session(parent_jsonl, eval_only, compute_cost_usd)
    checks.extend(parent["checks"])

    summary = build_summary(agents, checks)

    result = {
        "session_id": session_id,
        "target": target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_types": sorted(project_types),
        "dag_shape": dag_shape,
        "discovered_agent_names": sorted(discovered_agents.keys()),
        "notes": notes,
        "checks": checks,
        "orchestrator": parent["orchestrator"],
        "agents": agents,
        "summary": summary,
    }

    # Compare mode: regression deltas against a previous run's JSON output.
    if compare_path:
        try:
            with open(compare_path) as f:
                baseline = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: Cannot read baseline {compare_path}: {e}", file=sys.stderr)
            sys.exit(1)
        result["comparison"] = build_comparison(baseline, result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
