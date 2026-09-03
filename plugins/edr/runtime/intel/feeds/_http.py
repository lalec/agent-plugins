"""Shared fetch helpers for feed adapters (skipped by discovery — leading underscore)."""
from __future__ import annotations

import json
import urllib.request
from typing import Any

TIMEOUT = 30
RETRIES = 3
UA = "edr-intel (https://github.com/lalec/agent-plugins)"


def get_text(url: str) -> str:
    """Fetch with retries for transient transport errors; the last error propagates."""
    import time
    import urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError):
            if attempt == RETRIES:
                raise
            time.sleep(5)
    raise RuntimeError("unreachable")


def get_json(url: str) -> Any:
    return json.loads(get_text(url))
