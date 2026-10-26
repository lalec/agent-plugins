"""Alert batches — one file per run at state/alerts/<ts>.json.

The analyst writes the file at the end of every run (empty `findings` when
clean). Each finding carries one pre-declared `action`; a reply only approves
it. Code renders the channel message from here, so the format is enforced
rather than requested.

Fields the loop maintains: `posted` (message id once sent), `answers`
({n: verb}), `reviewed` (timestamp once every finding is answered or the batch
was shown in an interactive session).

Reply grammar is numeric: `<finding> <choice>` pairs, choices 0 ok · 1 why ·
2 fix · 3 skip; a bare choice when the batch has one finding, and a bare `0`
accepts every finding the analyst called benign.

The header carries the analyst's verdict (`verdict: benign` per finding), not
the floor severity: a batch of benign changes is green even when a triage
floor made one of them critical. Findings already posted on earlier nights
are listed under "Still open" with the night they first appeared.
"""
from __future__ import annotations

import calendar
import time
from datetime import datetime
from typing import Any

import paths
from collectors._base import read_json, write_json

CHOICES = {0: "ok", 1: "why", 2: "fix", 3: "skip"}
CHOICE_LINE = " · ".join(f"{c} {v}" for c, v in CHOICES.items())
TS_FORMAT = "%Y%m%dT%H%M%SZ"


def path(ts: str):
    return paths.ALERTS_DIR / f"{ts}.json"


def load(ts: str) -> dict[str, Any] | None:
    data = read_json(path(ts))
    return data if isinstance(data, dict) and data.get("ts") else None


def save(batch: dict[str, Any]) -> None:
    write_json(path(batch["ts"]), batch)


def mark(ts: str, **fields: Any) -> dict[str, Any] | None:
    batch = load(ts)
    if batch is not None:
        batch.update(fields)
        save(batch)
    return batch


def list_ts() -> list[str]:
    if not paths.ALERTS_DIR.exists():
        return []
    return sorted(p.stem for p in paths.ALERTS_DIR.glob("*.json"))


def latest() -> dict[str, Any] | None:
    for ts in reversed(list_ts()):
        batch = load(ts)
        if batch is not None:
            return batch
    return None


def since(epoch: float) -> dict[str, Any] | None:
    """Newest batch written at or after `epoch` (second resolution) — what a run that started then produced."""
    for ts in reversed(list_ts()):
        if parse_ts(ts) >= int(epoch):
            return load(ts)
    return None


def unreviewed() -> list[dict[str, Any]]:
    """Batches with findings nobody has seen: never posted, never reviewed."""
    out = []
    for ts in list_ts():
        batch = load(ts)
        if batch and batch.get("findings") and not batch.get("posted") and not batch.get("reviewed"):
            out.append(batch)
    return out


def finding(batch: dict[str, Any], n: int) -> dict[str, Any] | None:
    return next((f for f in batch.get("findings") or [] if _n(f) == n), None)


def numbers(batch: dict[str, Any]) -> set[int]:
    return {_n(f) for f in batch.get("findings") or [] if _n(f) is not None}


def answered(batch: dict[str, Any]) -> bool:
    answers = batch.get("answers") or {}
    return bool(numbers(batch)) and all(str(n) in answers for n in numbers(batch))


def parse_ts(ts: str) -> float:
    try:
        return calendar.timegm(time.strptime(ts, TS_FORMAT))
    except ValueError:
        return 0.0


def local_label(ts: str) -> str:
    return datetime.fromtimestamp(parse_ts(ts)).strftime("%a %H:%M")


def render(batch: dict[str, Any]) -> str | None:
    """Channel message for a batch; None when there is nothing to decide."""
    import coverage
    findings = [f for f in batch.get("findings") or [] if _n(f) is not None]
    if not findings:
        return None
    ok = benign(batch)
    look = len(findings) - len(ok)
    yours = f"{len(ok)} look{'s' if len(ok) == 1 else ''} like yours"
    head = (f"🔴 edr · {local_label(batch['ts'])} · {look} need{'s' if look == 1 else ''} a look"
            + (f" · {yours}" if ok else "")) if look else \
        f"🟢 edr · {local_label(batch['ts'])} · no sign of compromise · {yours}"
    since = open_since(batch)
    new = [f for f in findings if _n(f) not in since]
    old = [f for f in findings if _n(f) in since]
    lines = [head] + (["New tonight:"] if new and old else []) + [_line(f, ok) for f in new]
    if old:
        lines += ["Still open:"] + [_line(f, ok, since[_n(f)]) for f in old]
    lines += coverage.lines(batch["ts"])
    ns = sorted(_n(f) for f in findings)
    which = str(ns[0]) if len(ns) == 1 else f"{ns[0]}–{ns[-1]}"
    bulk = " · just 0 = ok all that look like yours" if len(ns) > 1 and ok else ""
    lines.append(f"Reply: {which} · {CHOICE_LINE}{bulk}")
    return "\n".join(lines)


def _line(f: dict[str, Any], ok: set[int], first: str | None = None) -> str:
    mark = "" if _n(f) in ok else "⚠️ "
    count = f" ×{len(sigs(f))}" if len(sigs(f)) > 1 else ""
    when = f" · since {datetime.fromtimestamp(parse_ts(first)).strftime('%-d %b')}" if first else ""
    rec = f" → {f['recommend']}" if f.get("recommend") else ""
    return f"{mark}{_n(f)} · {f.get('headline', '')}{count}{when}{rec}"


def benign(batch: dict[str, Any]) -> set[int]:
    """Finding numbers the analyst called benign — what a bare `0` accepts."""
    return {_n(f) for f in batch.get("findings") or [] if f.get("verdict") == "benign" and _n(f) is not None}


def sigs(f: dict[str, Any]) -> list[str]:
    """A finding covers one or more anomalies with the same root cause."""
    return [s for s in (f.get("sigs") or [f.get("sig")]) if s]


def open_since(batch: dict[str, Any]) -> dict[int, str]:
    """{n: ts of the first night} for findings also posted on the nights just before this one."""
    tracking = {_n(f): set(sigs(f)) for f in batch.get("findings") or [] if _n(f) is not None}
    since: dict[int, str] = {}
    for ts in reversed([t for t in list_ts() if t < batch["ts"]]):
        prior = load(ts)
        if not prior or not tracking:
            break
        seen = {s for f in prior.get("findings") or [] for s in sigs(f)}
        for n, ss in list(tracking.items()):
            if ss & seen:
                since[n] = ts
            else:
                del tracking[n]
    return since


def post_batch(batch: dict[str, Any]) -> str | None:
    """Render + post; records the message id on the batch and in notify state."""
    import notify
    text = render(batch)
    if text is None:
        return None
    mid = notify.post(text)
    if mid:
        mark(batch["ts"], posted=mid)
        notify.remember_post(mid, batch["ts"])
    return mid


def _n(f: dict[str, Any]) -> int | None:
    try:
        return int(f.get("n"))
    except (TypeError, ValueError):
        return None
