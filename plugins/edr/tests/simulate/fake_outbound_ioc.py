#!/usr/bin/env python3
"""A connection to a known-bad address must surface even inside a baselined pair.

Inserts a simulator IOC for 1.1.1.1 into the intel database, holds a TCP
connection to it, runs the network collector, and expects an anomaly with an
`intel` hit at floor critical — whether the (command, port) pair was new or
already baselined (`change: flagged`). Skips when offline. Removes the IOC.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "runtime"))
from _lib import report_fail, run_collector  # noqa: E402
from intel import db as ioc_db  # noqa: E402

TARGET = ("1.1.1.1", 443)
FEED = "edr-simulator"


def main() -> int:
    try:
        sock = socket.create_connection(TARGET, timeout=5)
    except OSError as e:
        print(f"[SKIP] fake_outbound_ioc — no network ({e})")
        return 0
    with ioc_db.connect() as conn:
        ioc_db.upsert(conn, "ip", TARGET[0], FEED, "critical", time.time(), '{"note": "simulator"}')
    try:
        diff = run_collector("network")
        hit = next((a for a in diff.get("anomalies", [])
                    if a["evidence"]["kind"] == "outbound" and a["evidence"]["attrs"].get("intel")
                    and TARGET[0] in a["evidence"]["attrs"].get("remote_ips", [])), None)
        if hit and hit.get("floor_severity") == "critical":
            print(f"[PASS] fake_outbound_ioc (change={hit['change']}, feed={hit['evidence']['attrs']['intel'][0]['feed']})")
            return 0
        return report_fail("fake_outbound_ioc", "outbound anomaly with intel hit on 1.1.1.1 at floor critical", diff)
    finally:
        sock.close()
        with ioc_db.connect() as conn:
            conn.execute("DELETE FROM iocs WHERE feed = ?", (FEED,))


if __name__ == "__main__":
    sys.exit(main())
