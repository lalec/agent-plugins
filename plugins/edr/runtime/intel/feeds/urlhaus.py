"""abuse.ch URLhaus — hosts currently serving malware (hostfile export).

Yields `domain` (or `ip` when the host is an address). Severity high.
"""
from __future__ import annotations

import ipaddress
import json
from typing import Iterator

from intel.feeds._http import get_text

FEED_NAME = "urlhaus"
URL = "https://urlhaus.abuse.ch/downloads/hostfile/"


def fetch() -> Iterator[dict]:
    for line in get_text(URL).splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        host = parts[1].strip().lower()
        try:
            ipaddress.ip_address(host)
            ioc_type = "ip"
        except ValueError:
            ioc_type = "domain"
        yield {"type": ioc_type, "value": host, "severity": "high",
               "metadata": json.dumps({"source": "urlhaus hostfile"})}
