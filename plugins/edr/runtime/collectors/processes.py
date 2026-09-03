"""Process inventory + lineage collector.

`process`: one Evidence per executable path with a codesign verdict. Keyed on
the executable alone: pids, parents and command lines churn between ticks, so
they live in volatile attrs. A process exiting is not an anomaly
(`report_removed = False`). Unsigned or ad-hoc binaries also carry a sha256
so the intel step can match them.

`lineage`: one Evidence per (parent exe → child exe) pair for children in the
watch set — shells, interpreters, download and quarantine tools. First-seen
pairs settle through `edr accept`; an Office or browser parent spawning a
shell is the macro / dropper pattern and gets a triage floor.

The executable comes from `ps -o comm=`, which keeps paths with spaces intact.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import codesign_verdict, load_json_cache, run_cmd, save_json_cache, sha256_file

MAX_COMMANDS = 10
WATCH_CHILDREN = {"osascript", "curl", "wget", "sh", "bash", "zsh", "python", "python3", "perl",
                  "ruby", "nc", "ncat", "openssl", "base64", "xattr", "chmod", "launchctl"}
HASH_STATUSES = {"unsigned", "adhoc", "broken"}


class ProcessesCollector(Collector):
    name = "processes"
    tier = "T"
    maturity = "stable"
    version = 3
    mitre = ["T1059", "T1106", "T1204.002"]
    report_removed = False
    # Per-tick churn — kept in snapshot for analyst context, not used in diff identity.
    volatile_attrs = ["instance_count", "sample_pid", "etime", "pcpu_max", "ppid", "commands",
                      "sample_command", "count"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        rc, out, err = run_cmd(
            ["ps", "-axww", "-o", "pid=,ppid=,uid=,user=,pcpu=,pmem=,etime=,command="],
            timeout=10,
        )
        if rc != 0:
            return [self.safe_evidence("error", "ps_failed", error=err.strip()[:500])]

        comm_by_pid = self._comm_by_pid()
        cache_path = ctx.data_dir / "state" / "codesign_cache.json"
        cache: dict[str, Any] = load_json_cache(cache_path, default={})
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            row = self._parse(line)
            if row and (exe := self._exe(comm_by_pid.get(row["pid"]), row["command"])):
                row["exe"] = exe
                rows.append(row)
        exe_by_pid = {r["pid"]: r["exe"] for r in rows}

        evidences = self._processes(rows, cache) + self._lineage(rows, exe_by_pid)
        save_json_cache(cache_path, cache)
        return evidences

    def _processes(self, rows: list[dict[str, Any]], cache: dict[str, Any]) -> list[Evidence]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[r["exe"]].append(r)
        out: list[Evidence] = []
        for exe, grp in groups.items():
            verdict = codesign_verdict(exe, cache) if exe.startswith("/") else {"status": "unresolved"}
            sample = grp[0]
            attrs = {
                "exe": exe,
                "users": sorted({r["user"] for r in grp}),
                "commands": list(dict.fromkeys(r["command"][:200] for r in grp))[:MAX_COMMANDS],
                "ppid": sample["ppid"],
                "instance_count": len(grp),
                "sample_pid": sample["pid"],
                "etime": sample["etime"],
                "pcpu_max": max(r["pcpu"] for r in grp),
                "codesign_status": verdict.get("status"),
                "codesign_team_id": verdict.get("team_id"),
                "codesign_signing_id": verdict.get("signing_id"),
            }
            if verdict.get("status") in HASH_STATUSES:
                attrs["exe_sha256"] = self._sha_cached(exe, cache)
            out.append(Evidence(collector=self.name, kind="process", key=exe, attrs=attrs))
        return out

    def _lineage(self, rows: list[dict[str, Any]], exe_by_pid: dict[int, str]) -> list[Evidence]:
        pairs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            if Path(r["exe"]).name not in WATCH_CHILDREN:
                continue
            parent = exe_by_pid.get(r["ppid"])
            if parent:
                pairs[(parent, r["exe"])].append(r)
        return [
            Evidence(collector=self.name, kind="lineage", key=f"lineage|{parent}|{child}",
                     attrs={"parent_exe": parent, "child_exe": child, "child": Path(child).name,
                            "parent_name": Path(parent).name, "count": len(grp),
                            "sample_command": grp[0]["command"][:200]})
            for (parent, child), grp in pairs.items()
        ]

    @staticmethod
    def _sha_cached(exe: str, cache: dict[str, Any]) -> str | None:
        try:
            st = Path(exe).stat()
        except OSError:
            return None
        key = f"sha256|{exe}|{int(st.st_mtime)}|{st.st_size}"
        if key not in cache:
            cache[key] = sha256_file(exe)
        return cache[key]

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
            return {"pid": int(parts[0]), "ppid": int(parts[1]), "uid": int(parts[2]),
                    "user": parts[3], "pcpu": float(parts[4]), "pmem": float(parts[5]),
                    "etime": parts[6], "command": parts[7]}
        except ValueError:
            return None

    @staticmethod
    def _exe(comm: str | None, command: str) -> str:
        """Executable path: prefer `comm`; fall back to argv[0] of the command line."""
        first = comm or (command.split(None, 1)[0] if command else "")
        if not first:
            return ""
        if first[0] in "(<" and first[-1] in ")>":  # "(launchd)", "<defunct>"
            return first
        if not first.startswith("/") and "/" not in first:
            return shutil.which(first) or first
        return first
