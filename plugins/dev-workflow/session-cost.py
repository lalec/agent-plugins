#!/usr/bin/env python3
"""Cost of one dev-workflow run, from Claude Code transcripts.

Maintainer tool — NOT installed into projects (unlike shared/graph.py).

    python3 session-cost.py ~/.claude/projects/<encoded>/<session-id>.jsonl

Reads the top-level transcript plus every `<session-id>/subagents/agent-*.jsonl`
and prints a per-component breakdown.

THE GOTCHA THIS EXISTS TO PREVENT: Claude Code writes one transcript row per
*content block*, and every row for a message carries the identical, complete
`message.usage` for the whole message. Summing rows therefore multiplies the
bill by blocks-per-message (2.3x on the run that set the original baseline).
Always dedupe on `message.id` first, taking `max()` on `output_tokens` (rows carry
a running partial, so the first row undercounts subagent output ~10x while looking
plausible), and cut the window at the run boundary — session files accumulate
every resume.
"""

import glob
import json
import os
import sys
from datetime import datetime

# $ per 1M tokens (input, output). Sonnet 5 intro pricing runs through 2026-08-31.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DEFAULT_PRICE = (5.0, 25.0)
CACHE_READ, WRITE_5M, WRITE_1H = 0.1, 1.25, 2.0


def load(path):
    """One row per message.id, collapsing the per-content-block rows.

    Input-side fields (input_tokens, cache_read, cache_creation) are constant
    across a message's rows — they are known when the request is issued, so any
    row is authoritative. `output_tokens` is NOT: it is a running partial, and
    only the final row (the one carrying `stop_reason`) holds the true total.
    Taking the first row undercounts output ~10x on subagent transcripts.
    Hence: max() on output, any-row on the rest.
    """
    by_id = {}
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message")
        if not isinstance(m, dict):
            continue
        usage, mid = m.get("usage"), m.get("id")
        if not usage or not mid:
            continue
        cc = usage.get("cache_creation") or {}
        out = usage.get("output_tokens", 0)
        if mid in by_id:
            by_id[mid]["out"] = max(by_id[mid]["out"], out)
            continue
        by_id[mid] = dict(
            ts=d.get("timestamp"),
            model=m.get("model"),
            inp=usage.get("input_tokens", 0),
            read=usage.get("cache_read_input_tokens", 0),
            w5=cc.get("ephemeral_5m_input_tokens", 0),
            w1h=cc.get("ephemeral_1h_input_tokens", 0),
            out=out,
        )
    return list(by_id.values())


def cost(rows):
    total = 0.0
    for r in rows:
        pin, pout = PRICES.get(r["model"], DEFAULT_PRICE)
        total += (
            (
                r["inp"]
                + r["read"] * CACHE_READ
                + r["w5"] * WRITE_5M
                + r["w1h"] * WRITE_1H
            )
            * pin
            / 1e6
        )
        total += r["out"] * pout / 1e6
    return total


def summarize(rows):
    return dict(
        n=len(rows),
        model=rows[0]["model"] if rows else "-",
        read=sum(r["read"] for r in rows),
        w5=sum(r["w5"] for r in rows),
        w1h=sum(r["w1h"] for r in rows),
        out=sum(r["out"] for r in rows),
        cost=cost(rows),
    )


def meta_for(path):
    """(agentType, spawnDepth, description, agentId, parentAgentId) — depth 1 when unknown.

    Depth is what turns a wall of `general-purpose` rows into one fact: a subagent that
    fans out spends at depth 2+, and that spend is invisible in a flat listing.
    """
    agent_id = os.path.basename(path)[len("agent-") : -len(".jsonl")]
    meta = path.replace(".jsonl", ".meta.json")
    if os.path.exists(meta):
        try:
            j = json.load(open(meta))
            return (
                j.get("agentType") or os.path.basename(path),
                j.get("spawnDepth") or 1,
                j.get("description") or "",
                agent_id,
                j.get("parentAgentId"),
            )
        except (ValueError, OSError):
            pass
    return (os.path.basename(path), 1, "", agent_id, None)


RESUME_GAP = 3600  # a gap this long means someone resumed the session later


def parse_ts(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def cadence(rows):
    """Inter-request gaps on the top level — why the 1h cache TTL pays off."""
    stamped = sorted((r for r in rows if r["ts"]), key=lambda r: r["ts"])
    if len(stamped) < 2:
        return
    gaps = sorted(
        (parse_ts(b["ts"]) - parse_ts(a["ts"])).total_seconds()
        for a, b in zip(stamped, stamped[1:])
    )
    over = sum(1 for g in gaps if g > 300)
    print(
        f"\ntop-level cadence: median {gaps[len(gaps) // 2]:.0f}s  "
        f"p90 {gaps[int(len(gaps) * 0.9)]:.0f}s  max {gaps[-1]:.0f}s  "
        f"| {over}/{len(gaps)} gaps > 5m"
    )


def warn_if_resumed(rows):
    """A session file accumulates every resume. Costing the whole file answers
    'what has this session cost in total', NOT 'what did one run cost' — the
    number that matters for a per-run baseline. Surface the boundaries so the
    caller can re-run with --until."""
    stamped = sorted((r for r in rows if r["ts"]), key=lambda r: r["ts"])
    breaks = [
        (a["ts"], b["ts"], (parse_ts(b["ts"]) - parse_ts(a["ts"])).total_seconds())
        for a, b in zip(stamped, stamped[1:])
        if (parse_ts(b["ts"]) - parse_ts(a["ts"])).total_seconds() > RESUME_GAP
    ]
    if not breaks:
        return
    print(
        f"\n!! {len(breaks)} long idle gap(s) on the top level. A session file accumulates"
        f"\n   every resume, so the total above may span more than one run. Judge each:"
        f"\n   a mid-run pause (waiting on QA, a human) counts; a next-day resume does not."
    )
    for end, restart, gap in breaks:
        print(f"     stops {end}  resumes {restart}  ({gap / 3600:.1f}h)")
    print(f"     cut with:  --until {breaks[-1][0]}")


def main():
    argv = sys.argv[1:]
    until = None
    if "--until" in argv:
        i = argv.index("--until")
        until = argv[i + 1]
        del argv[i : i + 2]
    if len(argv) != 1:
        sys.exit(__doc__)
    session = argv[0]

    def load_win(p):
        rows = load(p)
        return [r for r in rows if not until or (r["ts"] and r["ts"] <= until)]

    top = load_win(session)
    subagents = sorted(
        glob.glob(os.path.splitext(session)[0] + "/subagents/agent-*.jsonl")
    )

    agents = {}
    for f in subagents:
        kind, depth, desc, aid, parent = meta_for(f)
        agents[aid] = dict(
            kind=kind, depth=depth, desc=desc, parent=parent, s=summarize(load_win(f))
        )

    # Print each depth-1 agent followed by its descendants, so a fan-out reads as a
    # tree rather than as unattributed rows scattered through the listing.
    children = {}
    for aid, a in agents.items():
        children.setdefault(a["parent"], []).append(aid)

    rows = [("top-level", 0, "", summarize(top))]

    def walk(aid, indent):
        a = agents[aid]
        rows.append((a["kind"], a["depth"], a["desc"], a["s"]))
        for kid in sorted(children.get(aid, []), key=lambda k: -agents[k]["s"]["cost"]):
            walk(kid, indent + 1)

    roots = [a for a in agents if agents[a]["parent"] not in agents]
    for aid in sorted(roots, key=lambda k: -agents[k]["s"]["cost"]):
        walk(aid, 0)

    hdr = (
        f"{'component':<20}{'d':>2} {'model':<16}{'reqs':>5}{'out':>9}"
        f"{'read':>12}{'w1h':>10}{'w5':>10}{'cost':>9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for kind, depth, desc, st in rows:
        name = ("  " * max(0, depth - 1)) + kind
        print(
            f"{name[:20]:<20}{depth or '':>2} {st['model']:<16}{st['n']:>5}{st['out']:>9,}"
            f"{st['read']:>12,}{st['w1h']:>10,}{st['w5']:>10,}{st['cost']:>8.2f}"
            + (f"  {desc[:44]}" if desc else "")
        )
    print("-" * len(hdr))

    total = sum(st["cost"] for _, _, _, st in rows)
    nested = [(k, d, x, st) for k, d, x, st in rows if d >= 2]
    print(
        f"{'TOTAL':<20}{'':>2} {'':<16}{'':>5}{'':>9}{'':>12}{'':>10}{'':>10}"
        f"{total:>8.2f}"
    )
    if nested:
        n_cost = sum(st["cost"] for _, _, _, st in nested)
        share = n_cost / total * 100 if total else 0
        print(
            f"{'  of which depth>=2':<20}{'':>2} {'':<16}{len(nested):>5}{'':>9}"
            f"{'':>12}{'':>10}{'':>10}{n_cost:>8.2f}   {share:.0f}% — subagents that fanned out"
        )
    cadence(top)
    warn_if_resumed(top)


if __name__ == "__main__":
    main()
