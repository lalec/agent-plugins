"""The launchd side of the nightly scan: plist, shim, install / uninstall.

A calendar job fires on wake if the time passed while asleep; launchd gives
it a minimal PATH, so the plist sets PATH and HOME explicitly. The job runs a
small shim in EDR_HOME that resolves the *installed* plugin at run time, so a
plugin update never strands the job on a deleted cache path. The scan sits
under `caffeinate -i`: without it the Mac idle-sleeps mid-run.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import paths

LABEL = "com.edr.macos.scan"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LAUNCHD_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

_SHIM = """#!/bin/bash
# edr nightly shim — written by `edr schedule install`. Resolves the installed plugin at run time.
FALLBACK={fallback}
RUNTIME="$({python} - <<'PY'
import json, os
try:
    d = json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json"))).get("plugins", {{}})
    for k, v in d.items():
        if k.startswith("edr@") and v:
            print(os.path.join(v[0]["installPath"], "runtime")); break
except Exception:
    pass
PY
)"
[ -f "$RUNTIME/schedule.py" ] || RUNTIME="$FALLBACK"
exec /usr/bin/caffeinate -i {python} "$RUNTIME/schedule.py" run
"""


def plist_xml(at: str) -> str:
    hour, minute = (int(x) for x in at.split(":"))
    env = {"PATH": LAUNCHD_PATH, "HOME": str(Path.home()), "EDR_HEADLESS": "1"}
    if os.environ.get("EDR_HOME"):
        env["EDR_HOME"] = os.environ["EDR_HOME"]
    env_xml = "".join(f"\n    <key>{k}</key><string>{v}</string>" for k, v in env.items())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>{paths.NIGHTLY_SHIM}</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
  <key>EnvironmentVariables</key>
  <dict>{env_xml}
  </dict>
  <key>StandardOutPath</key><string>{paths.LAUNCHD_LOG}</string>
  <key>StandardErrorPath</key><string>{paths.LAUNCHD_LOG}</string>
</dict>
</plist>
"""


def install(at: str, notify_status: str) -> int:
    """Interactive only: prints the plist and asks before writing anything."""
    if not sys.stdin.isatty():
        print("edr schedule install needs an interactive terminal — it asks before writing the job.")
        return 2
    xml = plist_xml(at)
    print(xml)
    print(f"Writes {PLIST} and {paths.NIGHTLY_SHIM}, then loads the job. Notify: {notify_status}.")
    if input("Install? [y/N] ").strip().lower() != "y":
        print("Not installed.")
        return 1
    paths.ensure()
    paths.NIGHTLY_SHIM.write_text(_SHIM.format(fallback=_q(str(paths.RUNTIME_DIR)), python=sys.executable))
    paths.NIGHTLY_SHIM.chmod(0o755)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    PLIST.write_text(xml)
    rc, err = launchctl("bootstrap", f"gui/{os.getuid()}", str(PLIST))
    print(f"Loaded {LABEL}" if rc == 0 else f"launchctl bootstrap failed: {err}")
    return rc


def uninstall() -> int:
    launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    for p in (PLIST, paths.NIGHTLY_SHIM):
        p.unlink(missing_ok=True)
    print(f"Removed {LABEL}")
    return 0


def loaded() -> bool:
    return launchctl("print", f"gui/{os.getuid()}/{LABEL}")[0] == 0


def launchctl(*args: str) -> tuple[int, str]:
    proc = subprocess.run(["launchctl", *args], capture_output=True, text=True)
    return proc.returncode, (proc.stderr or proc.stdout).strip()


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"
