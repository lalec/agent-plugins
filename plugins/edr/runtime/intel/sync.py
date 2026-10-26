#!/usr/bin/env python3
"""Daily threat intel sync: invoke each feed adapter, upsert IOCs into db.sqlite.

Writes `intel/health.json` — per feed: ok, this run's fetch count, rows held,
last good sync (newest row), error. A dead feed must be visible, not a silent "0 IOCs".
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import paths  # noqa: E402
from collectors._base import read_json, write_json  # noqa: E402
from intel import db as ioc_db  # noqa: E402
from intel.feeds._http import FeedError  # noqa: E402

FEEDS_DIR = Path(__file__).parent / "feeds"
PRUNE_AFTER_SEC = 30 * 24 * 3600


def discover_feeds() -> list:
    feeds = []
    for path in sorted(FEEDS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        mod = importlib.import_module(f"intel.feeds.{path.stem}")
        if hasattr(mod, "fetch") and hasattr(mod, "FEED_NAME"):
            feeds.append(mod)
    return feeds


def health() -> dict[str, dict[str, Any]]:
    data = read_json(paths.INTEL_HEALTH, default={})
    return data if isinstance(data, dict) else {}


def main() -> int:
    now = time.time()
    report: dict[str, dict[str, Any]] = {}
    with ioc_db.connect() as conn:
        for feed in discover_feeds():
            n, error = 0, None
            try:
                for ioc in feed.fetch():
                    ioc_db.upsert(conn, ioc_type=ioc["type"], value=ioc["value"], feed=feed.FEED_NAME,
                                  severity=ioc.get("severity"), ts=now, metadata=ioc.get("metadata"))
                    n += 1
            except Exception as e:  # feeds raise FeedError with the key already redacted
                error = str(e) if isinstance(e, FeedError) else f"{type(e).__name__}: {e}"
                print(f"[sync] feed {feed.FEED_NAME} failed: {error}", file=sys.stderr)
            report[feed.FEED_NAME] = {"ok": error is None and n > 0, "fetched": n, "rows": 0,
                                      "last_ok": None, "error": error}
            print(f"[sync] {feed.FEED_NAME}: {n} IOCs")
        pruned = conn.execute("DELETE FROM iocs WHERE feed != 'mitre_macos' AND last_seen < ?",
                              (now - PRUNE_AFTER_SEC,)).rowcount
        for name, rows, newest in conn.execute("SELECT feed, COUNT(*), MAX(last_seen) FROM iocs GROUP BY feed"):
            if name in report:
                report[name].update(rows=rows, last_ok=newest)
    write_json(paths.INTEL_HEALTH, report)
    failed = sorted(name for name, r in report.items() if not r["ok"])
    print(f"[sync] feeds: {len(report)}, failed: {', '.join(failed) or 'none'}, pruned stale: {pruned}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
