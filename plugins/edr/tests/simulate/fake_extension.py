#!/usr/bin/env python3
"""An unpacked (sideloaded) Chromium extension must floor at high.

Builds a throwaway browser root with one Chrome profile holding an unpacked
extension and points the collector at it with EDR_BROWSER_ROOT. No real
browser profile is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import find_anomaly, report_fail, report_pass, run_collector  # noqa: E402

EXT_ID = "edrsimulatorunpackedextension000"


def build(root: Path) -> None:
    prof = root / "Application Support" / "Google" / "Chrome"
    (prof / "Default").mkdir(parents=True)
    (prof / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Default": {}}}}))
    settings = {EXT_ID: {"location": 4, "from_webstore": False, "state": 1, "path": "/tmp/evil-ext",
                         "manifest": {"name": "Totally Legit Helper", "version": "0.1",
                                      "permissions": ["tabs", "webRequest"], "host_permissions": ["<all_urls>"]}}}
    (prof / "Default" / "Secure Preferences").write_text(json.dumps({"extensions": {"settings": settings}}))


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="edr-sim-browser-"))
    os.environ["EDR_BROWSER_ROOT"] = str(root)
    try:
        build(root)
        diff = run_collector("browser")
        a = find_anomaly(diff, kind="extension", key_substr=EXT_ID, floor="high")
        if a:
            return report_pass("fake_extension (unpacked Chromium extension)", a)
        return report_fail("fake_extension", f"extension {EXT_ID} source=unpacked at floor high", diff)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        os.environ.pop("EDR_BROWSER_ROOT", None)


if __name__ == "__main__":
    sys.exit(main())
