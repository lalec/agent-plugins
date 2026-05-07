"""Shared helpers for red-team simulator scenarios.

Each scenario:
  1. Plants a (clearly-benign-but-suspicious-looking) artifact.
  2. Runs the relevant collector via run_collectors.py --collector NAME.
  3. Asserts the expected anomaly fires (kind + key match + optional floor severity).
  4. Cleans up (try/finally so cleanup always runs).

Scenarios MUST be idempotent: re-running cleans residual state from prior failures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Layout: plugins/edr/tests/simulate/_lib.py
PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
RUN_SCRIPT = PLUGIN_DIR / "runtime" / "run_collectors.py"
DATA_DIR = Path(os.environ.get("EDR_HOME", "~/.claude/edr")).expanduser().resolve()


def baseline_exists() -> bool:
    return (DATA_DIR / "state" / "baseline.json").exists()


def require_baseline() -> None:
    if not baseline_exists():
        print(f"[simulator] ERROR: no baseline.json at {DATA_DIR}/state/ — run `edr` once to bootstrap.",
              file=sys.stderr)
        sys.exit(2)


def run_collector(collector: str) -> dict[str, Any]:
    """Run a single collector and return the parsed diff.json."""
    result = subprocess.run(
        ["python3", str(RUN_SCRIPT), "--collector", collector],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"runner failed: {result.stderr}")

    summary = json.loads(result.stdout)
    snap_dir = Path(summary["snapshot_dir"])
    diff_path = snap_dir / "diff.json"
    if not diff_path.exists():
        return {"anomalies": []}
    return json.loads(diff_path.read_text())


def find_anomaly(diff: dict[str, Any], *, kind: str, key_substr: str,
                 change: str = "added", floor: str | None = None) -> dict[str, Any] | None:
    for a in diff.get("anomalies", []):
        ev = a["evidence"]
        if a["change"] != change:
            continue
        if ev["kind"] != kind:
            continue
        if key_substr not in ev["key"]:
            continue
        if floor and a.get("floor_severity") != floor:
            continue
        return a
    return None


def report_pass(scenario: str, anomaly: dict[str, Any]) -> int:
    ev = anomaly["evidence"]
    print(f"[PASS] {scenario}")
    print(f"       collector={ev['collector']} kind={ev['kind']} key={ev['key']}")
    print(f"       change={anomaly['change']} floor={anomaly.get('floor_severity')}")
    return 0


def report_fail(scenario: str, expected: str, diff: dict[str, Any]) -> int:
    print(f"[FAIL] {scenario}")
    print(f"       expected: {expected}")
    print(f"       got {len(diff.get('anomalies', []))} anomalies:")
    for a in diff.get("anomalies", [])[:10]:
        ev = a["evidence"]
        print(f"         - {a['change']:8s} | {ev['collector']:20s} | {ev['kind']:25s} | "
              f"{ev['key']} | floor={a.get('floor_severity')}")
    return 1
