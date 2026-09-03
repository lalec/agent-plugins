"""Alert batches — one file per run at state/alerts/<ts>.json.

The analyst writes the file at the end of every run (empty `findings` when
clean). Each finding carries one pre-declared `action`; a reply only approves
it. Code renders the channel message from here, so the format is enforced
rather than requested.

Fields the loop maintains: `posted` (message id once sent), `answers`
({n: verb}), `reviewed` (timestamp once every finding is answered, the batch
is skipped, or it was shown in an interactive session).
"""
from __future__ import annotations

import calendar
import time
from datetime import datetime
from typing import Any

import paths
from collectors._base import read_json, write_json

SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SEV_ICON = {"critical": "🔴", "high": "🔴", "medium": "🟠", "low": "🟡", "info": "🟢"}
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
    findings = [f for f in batch.get("findings") or [] if _n(f) is not None]
    if not findings:
        return None
    top = max(findings, key=lambda f: SEV_RANK.get(str(f.get("severity")), 0))
    icon = SEV_ICON.get(str(top.get("severity")), "🟠")
    lines = [f"{icon} edr · {local_label(batch['ts'])} · {len(findings)} to decide"]
    for f in findings:
        rec = f" → {f['recommend']}" if f.get("recommend") else ""
        lines.append(f"{_n(f)} · {f.get('headline', '')}{rec}")
    ns = [str(_n(f)) for f in findings]
    lines.append(f"Reply: {ns[0]} · {' '.join(ns[:2])} · ok {ns[-1]} · why {ns[0]} · skip")
    return "\n".join(lines)


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
