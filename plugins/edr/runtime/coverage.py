"""Coverage — what a run checked and how fresh the threat lists are, in plain words.

Every post carries `lines(ts)`, so "nothing found" can be told apart from
"not checked". `intel_warning()` speaks only on the night a threat list goes
stale or recovers: a dead feed is never silent and never nags.

CLI: `edr coverage`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import paths  # noqa: E402
from collectors._base import read_json  # noqa: E402

STALE_AFTER = 48 * 3600
TELEMETRY_TAIL = 64 * 1024


def run_row(ts: str | None = None) -> dict[str, Any]:
    """Telemetry row of the run whose snapshot is `ts`, else the newest one."""
    path = paths.STATE_DIR / "telemetry.jsonl"
    try:
        with path.open("rb") as f:
            f.seek(max(path.stat().st_size - TELEMETRY_TAIL, 0))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    rows = []
    for line in tail:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return next((r for r in reversed(rows) if r.get("snapshot") == ts), rows[-1] if rows else {})


def feeds() -> dict[str, dict[str, Any]]:
    """Threat-list health from the last sync; the static MITRE catalog is not a threat list."""
    data = read_json(paths.INTEL_HEALTH, default={})
    return {k: v for k, v in (data if isinstance(data, dict) else {}).items() if k != "mitre_macos"}


def stale(now: float | None = None) -> list[str]:
    now = now or time.time()
    return sorted(k for k, v in feeds().items() if now - float(v.get("last_ok") or 0) > STALE_AFTER)


def lines(ts: str | None = None) -> list[str]:
    row = run_row(ts)
    cols = (row.get("collectors") or {}).items()
    checked = [c.get("label") or name for name, c in cols if not c.get("errors")]
    failed = [c.get("label") or name for name, c in cols if c.get("errors")]
    out = []
    if checked or failed:
        out.append("Checked: " + ", ".join(checked) + (f" · ⚠️ couldn't check: {', '.join(failed)}" if failed else ""))
    return out + [_intel_line(int(row.get("intel_hits") or 0))]


def _intel_line(matches: int) -> str:
    info = feeds()
    if not info:
        return "⚠️ Threat lists: never synced"
    now = time.time()
    rows = sum(int(v.get("rows") or 0) for v in info.values())
    text = f"Threat lists: {rows:,} entries · {matches} match{'es' if matches != 1 else ''}"
    old = stale(now)
    if old:
        oldest = min(float(info[k].get("last_ok") or 0) for k in old)
        since = f"not updated for {_age(now - oldest)}" if oldest else "never updated"
        return f"⚠️ {text} · {', '.join(old)} {since}"
    newest = max(float(v.get("last_ok") or 0) for v in info.values())
    return f"{text} · updated {_age(now - newest)} ago"


def intel_warning() -> str | None:
    """A line to post when the set of stale threat lists changed since the last call."""
    import notify
    now_stale = stale()
    if now_stale == (notify.state().get("intel_stale") or []):
        return None
    notify.save_state(intel_stale=now_stale)
    if not now_stale:
        return "🟢 edr · threat lists updating again"
    reason = next((feeds()[k].get("error") for k in now_stale if feeds()[k].get("error")), None)
    return f"⚠️ edr · threat lists stale: {', '.join(now_stale)}" + (f" · {reason}" if reason else "")


def _age(sec: float) -> str:
    if sec < 3600:
        return f"{max(int(sec // 60), 1)}m"
    if sec < 48 * 3600:
        return f"{int(sec // 3600)}h"
    return f"{int(sec // 86400)}d"


def main() -> int:
    print("\n".join(lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
