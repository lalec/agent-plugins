#!/usr/bin/env python3
"""Plant a benign-looking unsigned LaunchAgent and verify launchd collector flags it critical.

Artifact: a tiny bash script in /tmp/, plus a plist in ~/Library/LaunchAgents/ that points
to it. The script is unsigned (bash scripts aren't codesigned), so the launchd collector's
`target_codesign_status` will be 'unsigned' → triage rule `launchd_unsigned_target` → critical.

Asserts:
  - launchd collector emits an `added` anomaly with kind=launchd_item, key=<plist path>
  - floor_severity == 'critical'
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import find_anomaly, report_fail, report_pass, require_baseline, run_collector  # noqa: E402

LABEL = "com.edr.test.fake-launchagent"
PLIST_PATH = Path(os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist"))
SCRIPT_PATH = Path("/tmp/edr_fake_launchagent.sh")
PLIST_BODY = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>Program</key><string>{SCRIPT_PATH}</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
"""
SCRIPT_BODY = "#!/bin/bash\necho 'edr simulator — benign'\n"


def plant() -> None:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT_PATH.write_text(SCRIPT_BODY)
    SCRIPT_PATH.chmod(0o755)
    PLIST_PATH.write_text(PLIST_BODY)


def cleanup() -> None:
    for p in (PLIST_PATH, SCRIPT_PATH):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    require_baseline()
    cleanup()  # in case a prior run crashed
    try:
        plant()
        diff = run_collector("launchd")
        anomaly = find_anomaly(diff, kind="launchd_item", key_substr=LABEL,
                               change="added", floor="critical")
        if anomaly:
            return report_pass("fake_launchagent (unsigned target)", anomaly)
        return report_fail("fake_launchagent",
                           f"added launchd_item with key containing '{LABEL}', floor=critical",
                           diff)
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
