"""Privileged execution via the native macOS admin dialog.

`sudo` cannot be used from an agent session: there is no TTY, so it fails with
"sudo: a terminal is required to read the password". Handing the user a command
to paste back fails for the same reason — running it with Claude Code's `!`
prefix executes in that same TTY-less shell.

So every privileged action goes through AppleScript's
`do shell script ... with administrator privileges`, which raises the standard
macOS authentication dialog. The user still authorises each action and sees the
prompt text describing it, but types their password into a native panel instead
of a terminal.

Nothing here caches credentials. Each call raises its own dialog, which is the
point: one authorisation per privileged action, same as the per-step `y/n` rule
that governs `respond.py`.
"""
from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# osascript's error number when the user dismisses the auth dialog.
_USER_CANCELLED = "-128"
_TIMEOUT_SECONDS = 300


@dataclass
class PrivilegedResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False

    @property
    def summary(self) -> str:
        if self.cancelled:
            return "cancelled at the macOS admin dialog"
        return self.stdout.strip() or self.stderr.strip() or ("ok" if self.success else "failed")


def is_available() -> bool:
    """True when the admin dialog can be raised (macOS with osascript present)."""
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def run(argv: Sequence[str], prompt: str) -> PrivilegedResult:
    """Run one command as root. `argv` is shell-quoted, so callers pass a real
    argument list and never build a command string by hand."""
    return _osascript(shlex.join(argv), prompt)


def run_script(body: str, prompt: str) -> PrivilegedResult:
    """Run a multi-line bash script as root.

    The body is written to a 0700 temp file and executed by path, so no
    quoting of the script itself reaches AppleScript. Use this for uninstalls
    and other sequences that must back up, unload and delete as one authorised
    step rather than raising a dialog per command.
    """
    if not body.strip():
        return PrivilegedResult(False, stderr="empty script body")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sh", prefix="edr-privileged-", delete=False
        ) as handle:
            handle.write("#!/bin/bash\nset -u\n" + body)
            tmp = handle.name
        os.chmod(tmp, 0o700)
        return _osascript(f"/bin/bash {shlex.quote(tmp)}", prompt)
    except OSError as exc:
        return PrivilegedResult(False, stderr=f"could not stage script: {exc}")
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


def _osascript(command: str, prompt: str) -> PrivilegedResult:
    if not is_available():
        return PrivilegedResult(
            False, stderr="admin dialog unavailable (needs macOS with osascript)"
        )
    script = (
        f'do shell script "{_escape(command)}"'
        f' with administrator privileges'
        f' with prompt "{_escape(prompt)}"'
    )
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return PrivilegedResult(False, stderr="admin dialog timed out with no response")
    except OSError as exc:
        return PrivilegedResult(False, stderr=f"could not run osascript: {exc}")

    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        cancelled = _USER_CANCELLED in stderr or "User canceled" in stderr
        return PrivilegedResult(False, stderr=stderr, cancelled=cancelled)
    return PrivilegedResult(True, stdout=_normalise(completed.stdout), stderr=stderr)


def _escape(value: str) -> str:
    """Escape a Python string for embedding in an AppleScript string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalise(output: str) -> str:
    """`do shell script` hands back CR-separated lines; restore real newlines."""
    return re.sub(r"\r\n?", "\n", output)
