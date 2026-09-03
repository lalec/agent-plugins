"""abuse.ch ThreatFox — recent IOCs with malware attribution (JSON export).

Maps `ip:port` → ip, `domain` → domain, `sha256_hash` → hash_sha256.
Severity high when ThreatFox confidence ≥ 75, else medium.
"""
from __future__ import annotations

import json
from typing import Iterator

from intel.feeds._http import get_json

FEED_NAME = "threatfox"
URL = "https://threatfox.abuse.ch/export/json/recent/"
TYPES = {"ip:port": "ip", "domain": "domain", "sha256_hash": "hash_sha256"}


def fetch() -> Iterator[dict]:
    data = get_json(URL)
    rows = [r for group in data.values() for r in group] if isinstance(data, dict) else []
    for r in rows:
        ioc_type = TYPES.get(str(r.get("ioc_type")))
        value = str(r.get("ioc_value") or "").strip().lower()
        if not ioc_type or not value:
            continue
        if ioc_type == "ip":
            value = value.rsplit(":", 1)[0]
        try:
            confidence = int(r.get("confidence_level") or 0)
        except ValueError:
            confidence = 0
        yield {"type": ioc_type, "value": value, "severity": "high" if confidence >= 75 else "medium",
               "metadata": json.dumps({"malware": r.get("malware_printable") or r.get("malware"),
                                       "threat_type": r.get("threat_type"), "confidence": confidence})}
