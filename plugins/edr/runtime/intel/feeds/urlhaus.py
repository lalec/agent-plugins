"""abuse.ch URLhaus — hosts serving malware, URLs added in the past 30 days (CSV export, Auth-Key).

Yields the host of every URL still online: `domain`, or `ip` when the host is
an address. Severity high.
"""
from __future__ import annotations

import ipaddress
import json
from typing import Iterator
from urllib.parse import urlsplit

from intel.feeds._http import abusech_key, csv_rows, get_text

FEED_NAME = "urlhaus"
URL = "https://urlhaus-api.abuse.ch/v2/files/exports/{key}/recent.csv"


def fetch() -> Iterator[dict]:
    key = abusech_key()
    seen: set[str] = set()
    for r in csv_rows(get_text(URL.format(key=key), secret=key), must_have="url_status"):
        if r.get("url_status") != "online":
            continue
        host = (urlsplit(r.get("url", "")).hostname or "").lower()
        if not host or host in seen:
            continue
        seen.add(host)
        try:
            ipaddress.ip_address(host)
            ioc_type = "ip"
        except ValueError:
            ioc_type = "domain"
        yield {"type": ioc_type, "value": host, "severity": "high",
               "metadata": json.dumps({"source": "urlhaus recent", "threat": r.get("threat")})}
