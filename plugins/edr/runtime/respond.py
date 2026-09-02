"""Response primitives for NIST SP 800-61 Containment / Eradication / Recovery.

Each primitive is a callable that performs a *single* dangerous action.
**None of these run autonomously.** The analyst chooses which to invoke and
the user must confirm `y/n` per step in the active Claude Code session.

Anything needing root goes through `privileged`, which raises the native macOS
admin dialog. Never fall back to `sudo` or hand the user a command to paste —
neither works from a session without a TTY.
"""
from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paths
import privileged

QUARANTINE_DIR = paths.STATE_DIR / "quarantine"

# Never remove these, or anything above them, even with an authorised dialog.
_PROTECTED = {
    Path("/"), Path("/Applications"), Path("/Library"), Path("/System"),
    Path("/Users"), Path("/bin"), Path("/etc"), Path("/opt"), Path("/private"),
    Path("/sbin"), Path("/tmp"), Path("/usr"), Path("/var"), Path.home(),
}


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
    if rc.returncode == 0:
        return StepResult(True, f"unloaded {p}",
                          rollback_hint=f"`launchctl load {p}` to re-enable")
    # System-domain jobs need root. Escalate through the admin dialog rather
    # than reporting a permission failure the user cannot act on.
    if not _writable(p):
        res = privileged.run(["launchctl", "unload", str(p)],
                             prompt=f"Disable the launchd job {p.name}")
        if res.success:
            return StepResult(True, f"unloaded {p} (authorised via admin dialog)",
                              rollback_hint=f"`launchctl load {p}` as root to re-enable")
        return StepResult(False, f"could not unload {p}: {res.summary}", error=res.stderr[:300])
    return StepResult(False, "launchctl unload failed",
                      error=(rc.stderr or rc.stdout).strip()[:300])


def quarantine_file(path: str | Path) -> StepResult:
    src = Path(os.path.expanduser(str(path)))
    if not src.exists():
        return StepResult(False, f"path not found: {src}")
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dst = QUARANTINE_DIR / f"{src.name}.{int(src.stat().st_mtime)}"
    try:
        shutil.move(str(src), str(dst))
        dst.chmod(0o000)
    except PermissionError:
        res = privileged.run_script(
            f"mv {_q(src)} {_q(dst)} && chmod 000 {_q(dst)}",
            prompt=f"Quarantine {src.name}",
        )
        if not res.success:
            return StepResult(False, f"quarantine failed for {src}: {res.summary}",
                              error=res.stderr[:300])
        return StepResult(True, f"quarantined {src} -> {dst} (authorised via admin dialog)",
                          rollback_hint=f"chmod 600 {dst} && mv {dst} {src} to restore (as root)")
    except OSError as e:
        return StepResult(False, f"quarantine failed for {src}", error=str(e))
    return StepResult(True, f"quarantined {src} -> {dst}",
                      rollback_hint=f"chmod 600 {dst} && mv {dst} {src} to restore")


def remove_path(path: str | Path, backup: bool = True) -> StepResult:
    """Delete a file or directory tree, escalating to the admin dialog when the
    path is root-owned. This is the uninstall primitive: stale LaunchDaemons,
    orphaned privileged helpers, leftover application bundles.

    With `backup` the tree is copied into the quarantine dir first. Skip it for
    large bundles where a copy is not worth the disk.
    """
    target = Path(os.path.expanduser(str(path))).resolve()
    if not target.exists():
        return StepResult(False, f"path not found: {target}")
    if target in _PROTECTED or target.parent == target:
        return StepResult(False, f"refusing to remove protected path: {target}")

    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dst = QUARANTINE_DIR / f"{target.name}.{int(target.stat().st_mtime)}"
    steps = [f"cp -R {_q(target)} {_q(dst)}"] if backup else []
    steps.append(f"rm -rf {_q(target)}")

    if _writable(target):
        try:
            if backup:
                (shutil.copytree if target.is_dir() else shutil.copy2)(str(target), str(dst))
            (shutil.rmtree if target.is_dir() else os.unlink)(str(target))
        except PermissionError:
            pass  # fall through to the dialog
        except OSError as e:
            return StepResult(False, f"remove failed for {target}", error=str(e))
        else:
            return StepResult(True, f"removed {target}",
                              rollback_hint=f"`mv {dst} {target}` to restore" if backup else None)

    res = privileged.run_script(" && ".join(steps), prompt=f"Remove {target.name}")
    if not res.success:
        return StepResult(False, f"could not remove {target}: {res.summary}",
                          error=res.stderr[:300])
    return StepResult(True, f"removed {target} (authorised via admin dialog)",
                      rollback_hint=f"`sudo mv {dst} {target}` to restore" if backup else None)


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
    # Root access is no longer the blocker — `privileged` covers that. What is
    # still missing is anchor wiring: a rule loaded with `pfctl -a` has no
    # effect until the anchor is referenced from /etc/pf.conf, and editing the
    # firewall's main config is not something to do behind one dialog.
    rule = f"block out quick to {ip}\n"
    return StepResult(False, "pfctl block stub — needs a persistent pf anchor in /etc/pf.conf",
                      error=f"would have applied rule: {rule.strip()}")


def _writable(path: Path) -> bool:
    """True when this user can modify the path without root."""
    probe = path if path.exists() else path.parent
    return os.access(probe, os.W_OK)


def _q(path: Path) -> str:
    return shlex.quote(str(path))


def list_primitives() -> list[dict[str, str]]:
    return [
        {"name": "kill_pid", "args": "pid: int, signal_num: int = SIGTERM",
         "description": "Send signal to process. Default SIGTERM, escalate to SIGKILL if needed."},
        {"name": "launchctl_unload", "args": "plist_path: str",
         "description": "Disable a launchd job (does not delete plist). "
                        "Raises the admin dialog for system-domain jobs."},
        {"name": "quarantine_file", "args": "path: str",
         "description": "Move file to quarantine dir + chmod 000. Reversible. "
                        "Raises the admin dialog when the path is root-owned."},
        {"name": "remove_path", "args": "path: str, backup: bool = True",
         "description": "Delete a file or directory tree, backing it up to quarantine first. "
                        "The uninstall primitive; raises the admin dialog for root-owned paths."},
        {"name": "ssh_revoke_key", "args": "authorized_keys_path: str, key_fingerprint: str",
         "description": "Remove SSH key by fingerprint; saves backup."},
        {"name": "pfctl_block_host", "args": "ip: str",
         "description": "Block outbound traffic to host (Phase C+; needs pf anchor wiring)."},
    ]
