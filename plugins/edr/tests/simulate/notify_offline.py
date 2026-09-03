#!/usr/bin/env python3
"""A broken Discord config must never abort a scan.

Points notify at a token file that does not exist and runs `edr notify test`
in an isolated EDR_HOME. Expected: exit 0, `posted: null`, the reason named.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
NOTIFY = PLUGIN_DIR / "runtime" / "notify.py"


def main() -> int:
    home = tempfile.mkdtemp(prefix="edr-notify-offline-")
    try:
        Path(home, "config.yaml").write_text(
            "notify:\n  channel: discord\n  channel_id: '1'\n  user_id: '2'\n"
            "  token_file: /nonexistent/edr/.env\n"
        )
        env = {**os.environ, "EDR_HOME": home}
        r = subprocess.run([sys.executable, str(NOTIFY), "test"],
                           capture_output=True, text=True, env=env, timeout=30)
        ok = r.returncode == 0 and '"posted": null' in r.stdout and "token not readable" in r.stdout
        if ok:
            print("[PASS] notify_offline (token file absent -> clean no-op, exit 0)")
            return 0
        print("[FAIL] notify_offline")
        print(f"       rc={r.returncode} stdout={r.stdout.strip()} stderr={r.stderr.strip()[-300:]}")
        return 1
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
