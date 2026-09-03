"""Shared fetch helpers for feed adapters (skipped by discovery — leading underscore)."""
from __future__ import annotations

import json
import urllib.request
from typing import Any

TIMEOUT = 30
UA = "edr-intel (https://github.com/lalec/agent-plugins)"


def get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_json(url: str) -> Any:
    return json.loads(get_text(url))
