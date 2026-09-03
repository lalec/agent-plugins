#!/usr/bin/env python3
"""The dropper pattern: a quarantined download that is then executed.

1. Plant a quarantine-flagged `.command` script in ~/Downloads → `downloads`
   must emit `risky_download` at floor medium.
2. Run it → `processes` must flag the interpreter running a script from
   ~/Downloads at floor high (a `flagged` anomaly on the baselined shell, or
   `added` when the shell was not baselined yet).
Cleans up the file and kills the process.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import report_fail, report_pass, require_baseline, run_collector  # noqa: E402

DOWNLOADS = Path.home() / "Downloads"
SCRIPT = DOWNLOADS / "edr_sim_installer.command"
QUARANTINE = "0081;64fdeacb;EDRSimulator;"


def plant() -> subprocess.Popen:
    SCRIPT.write_text("#!/bin/bash\n# edr simulator — benign\nsleep 60\n")
    SCRIPT.chmod(0o755)
    subprocess.run(["xattr", "-w", "com.apple.quarantine", QUARANTINE, str(SCRIPT)], check=True)
    return subprocess.Popen(["/bin/bash", str(SCRIPT)])


def cleanup(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
    try:
        SCRIPT.unlink()
    except FileNotFoundError:
        pass


def _find(diff, kind, needle, floor):
    for a in diff.get("anomalies", []):
        ev = a["evidence"]
        blob = ev["key"] + " " + " ".join(str(c) for c in ev["attrs"].get("commands", []))
        if ev["kind"] == kind and needle in blob and a.get("floor_severity") == floor:
            return a
    return None


def main() -> int:
    require_baseline()
    cleanup(None)
    proc = None
    try:
        proc = plant()
        time.sleep(0.5)
        rc = 0
        diff = run_collector("downloads")
        a = _find(diff, "risky_download", SCRIPT.name, "medium")
        rc |= report_pass("fake_download_exec (quarantined .command)", a) if a else \
            report_fail("fake_download_exec", f"risky_download for {SCRIPT.name} at floor medium", diff)
        diff = run_collector("processes")
        a = _find(diff, "process", SCRIPT.name, "high")
        rc |= report_pass(f"fake_download_exec (script executed from ~/Downloads, change={a['change']})", a) if a else \
            report_fail("fake_download_exec", f"process running {SCRIPT.name} at floor high", diff)
        return rc
    finally:
        cleanup(proc)


if __name__ == "__main__":
    sys.exit(main())
