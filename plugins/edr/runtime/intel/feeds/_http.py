"""Shared fetch helpers for feed adapters (skipped by discovery — leading underscore).

abuse.ch exports need a free Auth-Key (auth.abuse.ch) placed in the URL path.
It lives in `secrets/abusech.key` under EDR_HOME, never in config, and every
error raised from here has it redacted — feed errors reach the log and the
notify channel.
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Iterator

import paths

TIMEOUT = 60
RETRIES = 3
UA = "edr-intel (https://github.com/lalec/agent-plugins)"
ABUSECH_KEY_FILE = paths.SECRETS_DIR / "abusech.key"


class FeedError(Exception):
    """A feed failure whose message is safe to log and post."""


def abusech_key() -> str:
    try:
        key = ABUSECH_KEY_FILE.read_text().strip()
    except OSError:
        key = ""
    if not key:
        raise FeedError(f"no abuse.ch key at {ABUSECH_KEY_FILE} (free at auth.abuse.ch)")
    return key


def get_bytes(url: str, secret: str | None = None) -> bytes:
    """Fetch with retries for transient transport errors; HTTP errors fail at once."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise FeedError(_redact(f"HTTP {e.code} {e.reason}", secret)) from None
        except (urllib.error.URLError, OSError) as e:
            if attempt == RETRIES:
                raise FeedError(_redact(f"{type(e).__name__}: {e}", secret)) from None
            time.sleep(5)
    raise RuntimeError("unreachable")


def get_text(url: str, secret: str | None = None) -> str:
    data = get_bytes(url, secret)
    if data[:2] == b"PK":  # zipped export: one member
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            data = zf.read(zf.namelist()[0])
    return data.decode("utf-8", errors="replace")


def get_json(url: str, secret: str | None = None) -> Any:
    return json.loads(get_text(url, secret))


def csv_rows(text: str, must_have: str) -> Iterator[dict[str, str]]:
    """Rows of an abuse.ch CSV as dicts. The header may be a `#` comment line; it is the
    first line naming `must_have`. Other comment lines are skipped."""
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if header is None:
            if must_have in line:
                header = _fields(line.lstrip("#").strip())
            continue
        if line.startswith("#"):
            continue
        values = _fields(line)
        if len(values) >= len(header):
            yield dict(zip(header, values))
    if header is None:
        raise FeedError(f"CSV header with {must_have!r} not found — export format changed")


def _fields(line: str) -> list[str]:
    return [v.strip() for v in next(csv.reader([line], skipinitialspace=True), [])]


def _redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "<key>") if secret else text
