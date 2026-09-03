"""macOS version and capability probes — the one place that knows what this host can give us.

Every collector asks here before touching a version- or permission-gated
source. A source that is not available yields one `unavailable` evidence in
the collector, never an exception. `edr doctor` prints the table for the host.

Floor: macOS 12. Tested: 13. Newer versions are gated per source below.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

FLOOR = (12, 0)

_TCC_DB = Path.home() / "Library" / "Application Support" / "com.apple.TCC" / "TCC.db"
_LOGIN_ITEMS_13 = (Path.home() / "Library" / "Application Support"
                   / "com.apple.backgroundtaskmanagementagent" / "backgrounditems.btm")

# name → gate. min/max are (major, minor). tool = CLI that must exist. path = file that must exist.
SOURCES: dict[str, dict[str, Any]] = {
    "xattr":               {"tool": "xattr", "used_by": "downloads"},
    "lsof":                {"tool": "lsof", "used_by": "network"},
    "scutil":              {"tool": "scutil", "used_by": "network"},
    "codesign":            {"tool": "codesign", "used_by": "processes, launchd, downloads"},
    "dscl":                {"tool": "dscl", "used_by": "host_security"},
    "spctl":               {"tool": "spctl", "used_by": "host_security"},
    "csrutil":             {"tool": "csrutil", "used_by": "host_security"},
    "launchctl":           {"tool": "launchctl", "used_by": "host_security, launchd"},
    "pluginkit":           {"min": (10, 10), "tool": "pluginkit", "used_by": "browser (Safari)"},
    "profiles":            {"min": (10, 13), "tool": "profiles", "used_by": "host_security"},
    "systemextensionsctl": {"min": (10, 15), "tool": "systemextensionsctl", "used_by": "host_security"},
    "login_items_file":    {"max": (13, 99), "path": _LOGIN_ITEMS_13, "used_by": "host_security",
                            "note": "root-only location on macOS 14+"},
    "sfltool":             {"min": (13, 0), "tool": "sfltool", "root": True, "used_by": "-"},
    "eslogger":            {"min": (13, 0), "tool": "eslogger", "root": True, "fda": True,
                            "used_by": "exec_events (phase 3)"},
    "tcc_db":              {"min": (10, 14), "path": _TCC_DB, "fda": True, "used_by": "-"},
}


def version() -> tuple[int, int]:
    raw = platform.mac_ver()[0] or "0.0"
    parts = (raw.split(".") + ["0", "0"])[:2]
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return (0, 0)


def version_str() -> str:
    return platform.mac_ver()[0] or "unknown"


def has_fda() -> bool:
    """Full Disk Access: the only cheap, reliable probe is opening the user TCC database."""
    try:
        with open(_TCC_DB, "rb"):
            return True
    except OSError:
        return False


def check(name: str) -> tuple[bool, str]:
    """(available, reason). reason is '' when available."""
    gate = SOURCES[name]
    v = version()
    if "min" in gate and v < tuple(gate["min"]):
        return False, f"needs macOS {gate['min'][0]}.{gate['min'][1]}+"
    if "max" in gate and v > tuple(gate["max"]):
        return False, gate.get("note", f"not available after macOS {gate['max'][0]}")
    if gate.get("tool") and not shutil.which(gate["tool"]):
        return False, f"{gate['tool']} not found"
    if gate.get("path") and not Path(gate["path"]).exists():
        return False, "file not present"
    if gate.get("root") and os.geteuid() != 0:
        return False, "needs root"
    if gate.get("fda") and not has_fda():
        return False, "needs Full Disk Access"
    return True, ""


def available(name: str) -> bool:
    return check(name)[0]


def doctor() -> dict[str, Any]:
    try:
        import yaml  # noqa: F401
        pyyaml = True
    except ImportError:
        pyyaml = False
    v = version()
    return {
        "macos": version_str(),
        "supported": v >= FLOOR,
        "floor": f"{FLOOR[0]}.{FLOOR[1]}",
        "python": platform.python_version(),
        "pyyaml": pyyaml,
        "full_disk_access": has_fda(),
        "sources": {
            name: {"available": ok, "reason": reason, "used_by": SOURCES[name]["used_by"]}
            for name, (ok, reason) in ((n, check(n)) for n in SOURCES)
        },
    }


def main() -> int:
    report = doctor()
    print(json.dumps(report, indent=2))
    return 0 if report["supported"] and report["pyyaml"] else 1


if __name__ == "__main__":
    sys.exit(main())
