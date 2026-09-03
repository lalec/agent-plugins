"""Process inventory collector.

Emits one Evidence per executable path with a codesign verdict. Keyed on the
executable alone: pids, parents and command lines churn between ticks, so they
live in volatile attrs and never make an anomaly. A process exiting is not an
anomaly either (`report_removed = False`).

The executable comes from `ps -o comm=`, which keeps paths with spaces intact
(`/Applications/Visual Studio Code.app/...`); splitting the command line on
whitespace truncated those and made codesign report `missing`.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import codesign_verdict, load_json_cache, run_cmd, save_json_cache

MAX_COMMANDS = 10


class ProcessesCollector(Collector):
    name = "processes"
    tier = "T"
    maturity = "stable"
    version = 2
    mitre = ["T1059", "T1106"]
    report_removed = False
    # Per-tick churn — kept in snapshot for analyst context, not used in diff identity.
    volatile_attrs = ["instance_count", "sample_pid", "etime", "pcpu_max", "ppid", "commands"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        rc, out, err = run_cmd(
            ["ps", "-axww", "-o", "pid=,ppid=,uid=,user=,pcpu=,pmem=,etime=,command="],
            timeout=10,
        )
        if rc != 0:
            return [self.safe_evidence("error", "ps_failed", error=err.strip()[:500])]

        comm_by_pid = self._comm_by_pid()
        cache_path = ctx.data_dir / "state" / "codesign_cache.json"
        codesign_cache: dict[str, Any] = load_json_cache(cache_path, default={})
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for line in out.splitlines():
            row = self._parse(line)
            if not row:
                continue
            exe = self._exe(comm_by_pid.get(row["pid"]), row["command"])
            if exe:
                groups[exe].append(row)

        evidences: list[Evidence] = []
        for exe, rows in groups.items():
            verdict = codesign_verdict(exe, codesign_cache) if exe.startswith("/") else {"status": "unresolved"}
            sample = rows[0]
            attrs = {
                "exe": exe,
                "users": sorted({r["user"] for r in rows}),
                "commands": list(dict.fromkeys(r["command"][:200] for r in rows))[:MAX_COMMANDS],
                "ppid": sample["ppid"],
                "instance_count": len(rows),
                "sample_pid": sample["pid"],
                "etime": sample["etime"],
                "pcpu_max": max(r["pcpu"] for r in rows),
                "codesign_status": verdict.get("status"),
                "codesign_team_id": verdict.get("team_id"),
                "codesign_signing_id": verdict.get("signing_id"),
            }
            evidences.append(Evidence(collector=self.name, kind="process", key=exe, attrs=attrs))

        save_json_cache(cache_path, codesign_cache)
        return evidences

    @staticmethod
    def _comm_by_pid() -> dict[int, str]:
        """pid -> executable path as the kernel knows it (spaces intact)."""
        rc, out, _ = run_cmd(["ps", "-axww", "-o", "pid=,comm="], timeout=10)
        table: dict[int, str] = {}
        if rc != 0:
            return table
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                table[int(parts[0])] = parts[1]
        return table

    @staticmethod
    def _parse(line: str) -> dict[str, Any] | None:
        parts = line.strip().split(None, 7)
        if len(parts) < 8:
            return None
        try:
            return {
                "pid": int(parts[0]),
                "ppid": int(parts[1]),
                "uid": int(parts[2]),
                "user": parts[3],
                "pcpu": float(parts[4]),
                "pmem": float(parts[5]),
                "etime": parts[6],
                "command": parts[7],
            }
        except ValueError:
            return None

    @staticmethod
    def _exe(comm: str | None, command: str) -> str:
        """Executable path: prefer `comm`; fall back to argv[0] of the command line."""
        first = comm or (command.split(None, 1)[0] if command else "")
        if not first:
            return ""
        # Paren-wrapped kernel/orphan markers like "(launchd)" or "<defunct>"
        if first[0] in "(<" and first[-1] in ")>":
            return first
        # Resolve bare names via PATH (e.g. "python3" -> /opt/homebrew/bin/python3)
        if not first.startswith("/") and "/" not in first:
            return shutil.which(first) or first
        return first
