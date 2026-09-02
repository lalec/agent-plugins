#!/usr/bin/env python3
"""Verify hostile strings cannot break out of a privileged command into a root shell.

`privileged` builds an AppleScript string containing a shell command and hands it to
osascript, which runs it as root. Two layers have to hold for that to be safe:

  1. `shlex.join` / `shlex.quote` — so a malicious *argument* (an attacker-chosen
     filename, a plist label) stays an argument and never becomes shell syntax.
  2. `_escape` — so the resulting command survives embedding in an AppleScript
     string literal without terminating it early.

A break in either layer means an anomaly's own attacker-controlled text executes as
root the moment the analyst tries to remove it. That is the worst failure this plugin
could have, so it is checked directly.

Runs with `do shell script` only — no `with administrator privileges`, so no auth
dialog and no root. Needs no baseline.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "runtime"))
import privileged  # noqa: E402

# Each payload is shell syntax that must survive as literal text.
PAYLOADS = [
    "plain",
    'has "double quotes"',
    "single 'quotes'",
    r"back\slash",
    "semi; colon && ampersand",
    "$(whoami)",
    "`id`",
    "$HOME",
    "new\tline-ish",
    "* ? [glob]",
    '"; rm -rf /tmp/edr-should-never-exist; echo "',
    "\\\" with administrator privileges -- ",
]


def check(payload: str) -> tuple[bool, str]:
    """Round-trip one payload through the same quoting path `privileged` uses."""
    command = shlex.join(["printf", "%s", payload])
    script = f'do shell script "{privileged._escape(command)}"'
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return False, f"osascript failed: {result.stderr.strip()[:120]}"
    got = privileged._normalise(result.stdout).rstrip("\n")
    return got == payload, got


def main() -> int:
    if not privileged.is_available():
        print("[SKIP] privileged_injection — needs macOS with osascript")
        return 0

    failures = []
    for payload in PAYLOADS:
        ok, got = check(payload)
        if not ok:
            failures.append((payload, got))

    canary = Path("/tmp/edr-should-never-exist")
    if canary.exists():
        failures.append(("canary", "payload escaped and ran a real command"))
        canary.unlink()

    if failures:
        print("[FAIL] privileged_injection")
        print("       payloads must round-trip as literal text, uninterpreted:")
        for payload, got in failures:
            print(f"         - sent {payload!r}")
            print(f"           got  {got!r}")
        return 1

    print("[PASS] privileged_injection")
    print(f"       {len(PAYLOADS)} shell-metacharacter payloads round-tripped literally")
    print("       quoting holds for both shlex and the AppleScript string literal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
