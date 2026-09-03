"""abuse.ch Feodo Tracker — botnet C2 servers (recommended blocklist).

Yields `ip`, severity critical: a connection to one of these is C2.
"""
from __future__ import annotations

import json
from typing import Iterator

from intel.feeds._http import get_json

FEED_NAME = "feodo"
URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.json"


def fetch() -> Iterator[dict]:
    for r in get_json(URL) or []:
        ip = str(r.get("ip_address") or "").strip()
        if not ip:
            continue
        yield {"type": "ip", "value": ip, "severity": "critical",
               "metadata": json.dumps({"malware": r.get("malware"), "port": r.get("port"),
                                       "status": r.get("status")})}
