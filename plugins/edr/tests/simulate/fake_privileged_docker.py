#!/usr/bin/env python3
"""Run a benign --privileged container and verify docker collector flags it critical.

Asserts:
  - docker collector emits an `added` anomaly with kind=container, attrs.privileged=True
  - floor_severity == 'critical' (triage rule docker_privileged_or_socket_mount)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import find_anomaly, report_fail, report_pass, require_baseline, run_collector  # noqa: E402

CONTAINER_NAME = "edr_sim_priv"
IMAGE = "alpine:latest"


def plant() -> bool:
    cleanup()  # ensure no stale container
    rc = subprocess.run(
        ["docker", "run", "--rm", "-d", "--privileged", "--name", CONTAINER_NAME,
         IMAGE, "sleep", "30"],
        capture_output=True, text=True, timeout=60,
    )
    if rc.returncode != 0:
        print(f"[simulator] failed to start container: {rc.stderr.strip()}", file=sys.stderr)
        return False
    time.sleep(2)  # give docker daemon a beat to register
    return True


def cleanup() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME],
                   capture_output=True, text=True, timeout=15)


def docker_available() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0


def main() -> int:
    require_baseline()
    if not docker_available():
        print("[SKIP] fake_privileged_docker — docker daemon not running")
        return 0
    try:
        if not plant():
            return 1
        diff = run_collector("docker")
        anomaly = find_anomaly(diff, kind="container", key_substr="",
                               change="added", floor="critical")
        if anomaly and anomaly["evidence"]["attrs"].get("privileged"):
            return report_pass("fake_privileged_docker", anomaly)
        return report_fail("fake_privileged_docker",
                           "added container with attrs.privileged=True, floor=critical",
                           diff)
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
