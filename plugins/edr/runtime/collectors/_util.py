"""Shared helpers for collectors (skipped by auto-discovery — leading underscore)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def run_cmd(args: list[str], timeout: int = 15, input_data: str | None = None) -> tuple[int, str, str]:
    """Run a shell command, return (returncode, stdout, stderr). Never raises."""
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, input=input_data
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return -127, "", f"binary not found: {e}"
    except Exception as e:
        return -1, "", f"unexpected error: {e}"


VERDICT_VERSION = 2  # bump when the status semantics change; old cache entries are then ignored


def codesign_verdict(path: str, cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return {status, signing_id, team_id, authority} for a binary path.

    status: 'signed-apple' (Apple platform binary — leaf authority "Software Signing")
          | 'signed-store' (App Store — leaf "Apple Mac OS Application Signing")
          | 'signed-developer' (Developer ID or other chain)
          | 'adhoc' | 'unsigned' | 'broken' | 'missing'

    Every valid chain ends at Apple Root CA, so only the *leaf* authority may
    decide "Apple-signed"; Firefox is not an Apple binary.

    Optional cache keyed by (version, path, mtime, size) speeds up repeated lookups.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"status": "missing"}
    try:
        st = p.stat()
        cache_key = f"v{VERDICT_VERSION}|{path}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        cache_key = f"v{VERDICT_VERSION}|{path}"

    if cache is not None and cache_key in cache:
        return cache[cache_key]

    rc, out, err = run_cmd(["codesign", "-dv", "--verbose=4", path], timeout=5)
    verdict = parse_codesign(rc, out + err)

    if cache is not None:
        cache[cache_key] = verdict
    return verdict


def parse_codesign(rc: int, text: str) -> dict[str, Any]:
    """Verdict from `codesign -dv --verbose=4` output (stdout+stderr)."""
    combined = text.lower()
    verdict: dict[str, Any] = {"status": "unsigned"}
    if rc == 0 or "signature=" in combined or "authority=" in combined:
        verdict["status"] = "signed-developer"
        for line in text.splitlines():
            line_l = line.lower()
            if line_l.startswith("authority="):
                verdict.setdefault("authority", []).append(line.split("=", 1)[1])
            elif line_l.startswith("teamidentifier="):
                team = line.split("=", 1)[1].strip()
                verdict["team_id"] = None if team == "not set" else team
            elif line_l.startswith("identifier="):
                verdict["signing_id"] = line.split("=", 1)[1]
            elif "adhoc" in line_l or "ad-hoc" in line_l:
                verdict["status"] = "adhoc"
        leaf = (verdict.get("authority") or [""])[0].strip().lower()
        if verdict["status"] != "adhoc":
            if leaf == "software signing":
                verdict["status"] = "signed-apple"
            elif leaf.startswith("apple mac os application signing"):
                verdict["status"] = "signed-store"
    elif "code object is not signed" in combined or "not signed at all" in combined:
        verdict["status"] = "unsigned"
    elif "invalid signature" in combined or "broken" in combined:
        verdict["status"] = "broken"
    return verdict


def sha256_file(path: str | Path, max_bytes: int = 50 * 1024 * 1024) -> str | None:
    """Hash a file (up to max_bytes). Returns None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            read = 0
            while read < max_bytes:
                chunk = f.read(min(65536, max_bytes - read))
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
        return h.hexdigest()
    except OSError:
        return None


def load_json_cache(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def save_json_cache(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True))
