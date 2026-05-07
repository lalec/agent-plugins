#!/usr/bin/env python3
"""Daily threat intel sync: invoke each feed adapter, upsert IOCs into db.sqlite."""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from intel import db as ioc_db  # noqa: E402

FEEDS_DIR = Path(__file__).parent / "feeds"


def discover_feeds() -> list:
    feeds = []
    for path in sorted(FEEDS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        mod = importlib.import_module(f"intel.feeds.{path.stem}")
        if hasattr(mod, "fetch") and hasattr(mod, "FEED_NAME"):
            feeds.append(mod)
    return feeds


def main() -> int:
    now = time.time()
    counts: dict[str, int] = {}
    with ioc_db.connect() as conn:
        for feed in discover_feeds():
            n = 0
            try:
                for ioc in feed.fetch():
                    ioc_db.upsert(
                        conn,
                        ioc_type=ioc["type"],
                        value=ioc["value"],
                        feed=feed.FEED_NAME,
                        severity=ioc.get("severity"),
                        ts=now,
                        metadata=ioc.get("metadata"),
                    )
                    n += 1
            except Exception as e:
                print(f"[sync] feed {feed.FEED_NAME} failed: {e}", file=sys.stderr)
            counts[feed.FEED_NAME] = n
            print(f"[sync] {feed.FEED_NAME}: {n} IOCs")
    print(f"[sync] total feeds: {len(counts)}, total IOCs: {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
