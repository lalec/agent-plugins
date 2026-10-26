"""abuse.ch ThreatFox — IOCs with malware attribution, past 6 months (CSV export, Auth-Key).

Maps `ip:port` → ip, `domain` → domain, `sha256_hash` → hash_sha256.
Severity high when ThreatFox confidence ≥ 75, else medium.
"""
from __future__ import annotations

import json
from typing import Iterator

from intel.feeds._http import abusech_key, csv_rows, get_text

FEED_NAME = "threatfox"
URL = "https://threatfox-api.abuse.ch/v2/files/exports/{key}/full.csv.zip"
TYPES = {"ip:port": "ip", "domain": "domain", "sha256_hash": "hash_sha256"}


def fetch() -> Iterator[dict]:
    key = abusech_key()
    for r in csv_rows(get_text(URL.format(key=key), secret=key), must_have="ioc_value"):
        ioc_type = TYPES.get(r.get("ioc_type", ""))
        value = r.get("ioc_value", "").strip().lower()
        if not ioc_type or not value:
            continue
        if ioc_type == "ip":
            value = value.rsplit(":", 1)[0]
        try:
            confidence = int(r.get("confidence_level") or 0)
        except ValueError:
            confidence = 0
        yield {"type": ioc_type, "value": value, "severity": "high" if confidence >= 75 else "medium",
               "metadata": json.dumps({"malware": r.get("malware_printable") or r.get("fk_malware"),
                                       "threat_type": r.get("threat_type"), "confidence": confidence})}
