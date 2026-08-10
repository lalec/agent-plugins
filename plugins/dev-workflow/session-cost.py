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
Always dedupe on `message.id` first. See IMPROVEMENTS.md.
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
    """Deduped usage rows — one per message.id, first occurrence wins."""
    seen, rows = set(), []
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message")
        if not isinstance(m, dict):
            continue
        usage, mid = m.get("usage"), m.get("id")
        if not usage or not mid or mid in seen:
            continue
        seen.add(mid)
        cc = usage.get("cache_creation") or {}
        rows.append(
            dict(
                ts=d.get("timestamp"),
                model=m.get("model"),
                inp=usage.get("input_tokens", 0),
                read=usage.get("cache_read_input_tokens", 0),
                w5=cc.get("ephemeral_5m_input_tokens", 0),
                w1h=cc.get("ephemeral_1h_input_tokens", 0),
                out=usage.get("output_tokens", 0),
            )
        )
    return rows


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


def label_for(path):
    meta = path.replace(".jsonl", ".meta.json")
    if os.path.exists(meta):
        try:
            return json.load(open(meta)).get("agentType") or os.path.basename(path)
        except (ValueError, OSError):
            pass
    return os.path.basename(path)


def cadence(rows):
    """Inter-request gaps on the top level — why the 1h cache TTL pays off."""
    stamped = sorted((r for r in rows if r["ts"]), key=lambda r: r["ts"])
    if len(stamped) < 2:
        return
    parse = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))  # noqa: E731
    gaps = [
        (parse(b["ts"]) - parse(a["ts"])).total_seconds()
        for a, b in zip(stamped, stamped[1:])
    ]
    gaps.sort()
    over = sum(1 for g in gaps if g > 300)
    print(
        f"\ntop-level cadence: median {gaps[len(gaps) // 2]:.0f}s  "
        f"p90 {gaps[int(len(gaps) * 0.9)]:.0f}s  max {gaps[-1]:.0f}s  "
        f"| {over}/{len(gaps)} gaps > 5m"
    )


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    session = sys.argv[1]
    top = load(session)
    components = [("top-level", summarize(top))]
    subagents = sorted(
        glob.glob(os.path.splitext(session)[0] + "/subagents/agent-*.jsonl")
    )
    components += [(label_for(f), summarize(load(f))) for f in subagents]

    hdr = f"{'component':<20}{'model':<18}{'reqs':>5}{'out':>9}{'read':>12}{'w1h':>10}{'w5':>10}{'cost':>9}"
    print(hdr)
    print("-" * len(hdr))
    for name, s in components:
        print(
            f"{name:<20}{s['model']:<18}{s['n']:>5}{s['out']:>9,}"
            f"{s['read']:>12,}{s['w1h']:>10,}{s['w5']:>10,}{s['cost']:>8.2f}"
        )
    print("-" * len(hdr))
    print(
        f"{'TOTAL':<20}{'':<18}{'':>5}{'':>9}{'':>12}{'':>10}{'':>10}"
        f"{sum(s['cost'] for _, s in components):>8.2f}"
    )
    cadence(top)


if __name__ == "__main__":
    main()
