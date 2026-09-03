"""Approval ledger — one file per approved finding at state/pending_actions/<ts>-<n>.json.

An entry is an action the user approved (a numbered reply) or an accept-as-
benign. It is executed at once when it needs no root, queued when it would
raise the admin dialog and nobody is at the Mac. Every outcome is written
back here; a failed step is a ledger row, never a crash.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import accept as accept_mod
import paths
import respond
from collectors._base import read_json, write_json

_PATH_PRIMITIVES = {"remove_path", "quarantine_file", "launchctl_unload"}


def needs_root(primitive: str, args: dict[str, Any]) -> bool:
    """Would running this primitive raise the admin dialog?"""
    if primitive in _PATH_PRIMITIVES:
        raw = args.get("path") or args.get("plist_path") or ""
        return not respond._writable(Path(os.path.expanduser(str(raw))))
    if primitive == "kill_pid":
        rc = subprocess.run(["ps", "-o", "uid=", "-p", str(args.get("pid", ""))],
                            capture_output=True, text=True)
        uid = rc.stdout.strip()
        return not uid.isdigit() or int(uid) != os.getuid()
    return primitive != "ssh_revoke_key"


def path(batch_ts: str, n: int) -> Path:
    return paths.PENDING_ACTIONS_DIR / f"{batch_ts}-{n}.json"


def save(entry: dict[str, Any]) -> None:
    write_json(path(entry["batch"], entry["n"]), entry)


def queued() -> list[dict[str, Any]]:
    if not paths.PENDING_ACTIONS_DIR.exists():
        return []
    rows = [read_json(p) for p in sorted(paths.PENDING_ACTIONS_DIR.glob("*.json"))]
    return [r for r in rows if isinstance(r, dict) and r.get("status") == "queued"]


def build(batch: dict[str, Any], finding: dict[str, Any], verb: str, source: str,
          msg_id: str | None) -> dict[str, Any] | None:
    """Entry for a fix / ok decision; None when a fix is asked but no action is declared."""
    if verb == "ok":
        kind, primitive, args = "accept", None, {}
    else:
        action = finding.get("action") or {}
        if not action.get("primitive"):
            return None
        kind, primitive, args = "action", str(action["primitive"]), dict(action.get("args") or {})
    return {"batch": batch["ts"], "n": int(finding["n"]), "kind": kind, "sig": finding.get("sig"),
            "primitive": primitive, "args": args,
            "needs_root": kind == "action" and needs_root(primitive, args),
            "source": source, "approved_msg": msg_id, "approved_at": now(),
            "status": "queued", "result": None, "done_at": None}


def execute(entry: dict[str, Any]) -> dict[str, Any]:
    """Run one entry now; records status/result on disk."""
    try:
        if entry["kind"] == "accept":
            res = accept_mod.accept([entry["sig"]], snapshot_ts=entry["batch"])
            ok = bool(res["accepted"])
            summary = "accepted as normal" if ok else "signature not in that run's diff"
        else:
            fn = getattr(respond, entry["primitive"], None)
            if fn is None or entry["primitive"].startswith("_"):
                raise ValueError(f"unknown primitive {entry['primitive']}")
            r = fn(**entry["args"])
            ok, summary = r.success, r.summary + (f" ({r.error})" if r.error else "")
    except Exception as e:
        ok, summary = False, f"{type(e).__name__}: {e}"
    status = "done" if ok else ("cancelled" if "cancelled" in summary else "failed")
    entry.update(status=status, result=summary, done_at=now())
    save(entry)
    return entry


def brief(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: entry.get(k) for k in ("batch", "n", "kind", "primitive", "needs_root", "status", "result")}


def icon(entry: dict[str, Any]) -> str:
    if entry["status"] != "done":
        return "❌"
    return "👌" if entry["kind"] == "accept" else "✅"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
