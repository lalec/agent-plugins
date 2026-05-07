"""Response primitives for NIST SP 800-61 Containment / Eradication / Recovery.

Each primitive is a callable that performs a *single* dangerous action.
**None of these run autonomously.** The analyst chooses which to invoke and
the user must confirm `y/n` per step in the active Claude Code session.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paths

QUARANTINE_DIR = paths.STATE_DIR / "quarantine"


@dataclass
class StepResult:
    success: bool
    summary: str
    rollback_hint: str | None = None
    error: str | None = None


def kill_pid(pid: int, signal_num: int = signal.SIGTERM) -> StepResult:
    try:
        os.kill(pid, signal_num)
        return StepResult(True, f"sent signal {signal_num} to pid {pid}",
                          rollback_hint="cannot un-kill; restart the program if it was legitimate")
    except ProcessLookupError:
        return StepResult(False, f"pid {pid} no longer exists", error="ProcessLookupError")
    except PermissionError as e:
        return StepResult(False, f"permission denied killing pid {pid}", error=str(e))


def launchctl_unload(plist_path: str | Path) -> StepResult:
    p = Path(os.path.expanduser(str(plist_path)))
    if not p.exists():
        return StepResult(False, f"plist not found: {p}")
    rc = subprocess.run(["launchctl", "unload", str(p)], capture_output=True, text=True)
    if rc.returncode != 0:
        return StepResult(False, "launchctl unload failed",
                          error=(rc.stderr or rc.stdout).strip()[:300])
    return StepResult(True, f"unloaded {p}",
                      rollback_hint=f"`launchctl load {p}` to re-enable")


def quarantine_file(path: str | Path) -> StepResult:
    src = Path(os.path.expanduser(str(path)))
    if not src.exists():
        return StepResult(False, f"path not found: {src}")
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dst = QUARANTINE_DIR / f"{src.name}.{int(src.stat().st_mtime)}"
    try:
        shutil.move(str(src), str(dst))
        dst.chmod(0o000)
    except (OSError, PermissionError) as e:
        return StepResult(False, f"quarantine failed for {src}", error=str(e))
    return StepResult(True, f"quarantined {src} -> {dst}",
                      rollback_hint=f"chmod 600 {dst} && mv {dst} {src} to restore")


def ssh_revoke_key(authorized_keys_path: str | Path, key_fingerprint: str) -> StepResult:
    import tempfile
    p = Path(os.path.expanduser(str(authorized_keys_path)))
    if not p.exists():
        return StepResult(False, f"authorized_keys not found: {p}")
    backup = p.with_suffix(p.suffix + f".bak-{int(p.stat().st_mtime)}")
    try:
        shutil.copy2(p, backup)
    except OSError as e:
        return StepResult(False, "backup failed; aborting", error=str(e))
    kept: list[str] = []
    removed = 0
    for line in p.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            kept.append(line)
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".pub", delete=False) as tf:
            tf.write(line + "\n")
            tmp = tf.name
        rc = subprocess.run(["ssh-keygen", "-lf", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        if rc.returncode == 0 and key_fingerprint in rc.stdout:
            removed += 1
            continue
        kept.append(line)
    if removed == 0:
        return StepResult(False, f"no key matching '{key_fingerprint}' found in {p}")
    p.write_text("\n".join(kept) + ("\n" if kept else ""))
    return StepResult(True, f"removed {removed} key(s) matching '{key_fingerprint}' from {p}",
                      rollback_hint=f"`mv {backup} {p}` to restore")


def pfctl_block_host(ip: str) -> StepResult:
    rule = f"block out quick to {ip}\n"
    return StepResult(False, "pfctl block stub — requires sudo orchestration; not yet wired",
                      error=f"would have applied rule: {rule.strip()}")


def list_primitives() -> list[dict[str, str]]:
    return [
        {"name": "kill_pid", "args": "pid: int, signal_num: int = SIGTERM",
         "description": "Send signal to process. Default SIGTERM, escalate to SIGKILL if needed."},
        {"name": "launchctl_unload", "args": "plist_path: str",
         "description": "Disable a launchd job (does not delete plist)."},
        {"name": "quarantine_file", "args": "path: str",
         "description": "Move file to quarantine dir + chmod 000. Reversible."},
        {"name": "ssh_revoke_key", "args": "authorized_keys_path: str, key_fingerprint: str",
         "description": "Remove SSH key by fingerprint; saves backup."},
        {"name": "pfctl_block_host", "args": "ip: str",
         "description": "Block outbound traffic to host (Phase C+)."},
    ]
