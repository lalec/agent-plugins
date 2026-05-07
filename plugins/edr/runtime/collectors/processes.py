"""Process inventory collector.

Emits one Evidence per unique (exe, cmdline) pair with codesign verdict.
PIDs are unstable across runs — keying on (exe, cmdline) gives stable diffs.
"""
from __future__ import annotations

import hashlib
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import codesign_verdict, load_json_cache, run_cmd, save_json_cache


class ProcessesCollector(Collector):
    name = "processes"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1059", "T1106"]
    # Per-tick churn — kept in snapshot for analyst context, not used in diff identity.
    # ppid is volatile because each bash/shell invocation has a distinct pid.
    volatile_attrs = ["instance_count", "sample_pid", "etime", "pcpu_max", "ppid"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        rc, out, err = run_cmd(
            ["ps", "-axww", "-o", "pid=,ppid=,uid=,user=,pcpu=,pmem=,etime=,command="],
            timeout=10,
        )
        if rc != 0:
            return [self.safe_evidence("error", "ps_failed", error=err.strip()[:500])]

        cache_path = ctx.data_dir / "state" / "codesign_cache.json"
        codesign_cache: dict[str, Any] = load_json_cache(cache_path, default={})
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for line in out.splitlines():
            row = self._parse(line)
            if not row:
                continue
            exe = self._extract_exe(row["command"])
            cmd_hash = hashlib.sha256(row["command"].encode()).hexdigest()[:12]
            key = f"{exe}|{cmd_hash}"
            groups[key].append({**row, "exe": exe, "cmd_hash": cmd_hash})

        evidences: list[Evidence] = []
        for key, rows in groups.items():
            sample = rows[0]
            exe = sample["exe"]
            verdict = codesign_verdict(exe, codesign_cache) if exe.startswith("/") else {"status": "unresolved"}
            attrs = {
                "exe": exe,
                "command": sample["command"][:500],
                "user": sample["user"],
                "ppid": sample["ppid"],
                "instance_count": len(rows),
                "sample_pid": sample["pid"],
                "etime": sample["etime"],
                "pcpu_max": max(r["pcpu"] for r in rows),
                "codesign_status": verdict.get("status"),
                "codesign_team_id": verdict.get("team_id"),
                "codesign_signing_id": verdict.get("signing_id"),
            }
            evidences.append(Evidence(collector=self.name, kind="process", key=key, attrs=attrs))

        save_json_cache(cache_path, codesign_cache)
        return evidences

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
    def _extract_exe(command: str) -> str:
        """argv[0] heuristic — works for the common case where argv[0] is the path."""
        if not command:
            return ""
        first = command.split(None, 1)[0]
        # Handle paren-wrapped kernel/orphan markers like "(launchd)"
        if first.startswith("(") and first.endswith(")"):
            return first
        # Resolve bare names via PATH (e.g. "python3" -> /opt/homebrew/bin/python3)
        if not first.startswith("/") and "/" not in first:
            resolved = shutil.which(first)
            if resolved:
                return resolved
        return first
