"""Downloads collector — event shape.

Files that arrived since the last run carrying the `com.apple.quarantine`
xattr, which every browser, mail client and AirDrop sets and which names the
downloading agent and the time. Read from the folders, not from
`QuarantineEventsV2`: Chrome no longer writes URLs there.

Only *risky* files become evidence of their own (installers, bundles, scripts,
archives, anything executable); the rest is one aggregate per run. Stateless:
each event is reported once and never baselined.
"""
from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence, read_json
from collectors._util import codesign_verdict, run_cmd, sha256_file

DIRS = ["~/Downloads", "~/Desktop", "/tmp", "$TMPDIR"]
RISKY_EXT = {".dmg", ".pkg", ".mpkg", ".app", ".command", ".tool", ".sh", ".zsh", ".bash", ".py",
             ".pl", ".rb", ".jar", ".scpt", ".applescript", ".workflow", ".terminal", ".zip",
             ".tar", ".gz", ".tgz", ".7z", ".iso", ".xip"}
FIRST_RUN_WINDOW = 24 * 3600
MAX_EVENTS = 100


class DownloadsCollector(Collector):
    name = "downloads"
    tier = "T"
    maturity = "beta"
    version = 1
    mitre = ["T1204.002", "T1105", "T1553.001"]
    stateless = True
    report_removed = False

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        since = self._since(ctx)
        risky: list[Evidence] = []
        other: Counter[str] = Counter()
        agents: Counter[str] = Counter()
        for entry, st in self._new_entries(since):
            quarantine = self._quarantine(entry)
            if quarantine is None:
                continue  # not downloaded — created locally
            agents[quarantine["agent"]] += 1
            ext = Path(entry).suffix.lower()
            executable = os.path.isfile(entry) and bool(st.st_mode & 0o111)
            if ext not in RISKY_EXT and not executable:
                other[ext or "(none)"] += 1
                continue
            if len(risky) < MAX_EVENTS:
                risky.append(self._risky(entry, st, ext, executable, quarantine))
        out = risky
        if other:
            out.append(Evidence(collector=self.name, kind="download_summary",
                                key=f"dl-summary|{int(ctx.now)}",
                                attrs={"count": sum(other.values()), "by_ext": dict(other.most_common(10)),
                                       "by_agent": dict(agents.most_common(5)), "since": int(since)}))
        return out

    def _risky(self, path: str, st: os.stat_result, ext: str, executable: bool,
               quarantine: dict[str, Any]) -> Evidence:
        is_bundle = os.path.isdir(path)
        attrs: dict[str, Any] = {
            "path": path, "name": Path(path).name, "ext": ext, "size": st.st_size,
            "executable": executable, "bundle": is_bundle,
            "agent": quarantine["agent"], "quarantine_flags": quarantine["flags"],
            "downloaded_at": quarantine["ts"], "mtime": int(st.st_mtime),
        }
        if is_bundle and ext == ".app":
            attrs["codesign_status"] = codesign_verdict(path).get("status")
        elif not is_bundle:
            attrs["sha256"] = sha256_file(path)
        return Evidence(collector=self.name, kind="risky_download",
                        key=f"dl|{path}|{int(st.st_mtime)}", attrs=attrs)

    @staticmethod
    def _since(ctx: CollectorContext) -> float:
        last = read_json(ctx.last_run_path, default={}) or {}
        try:
            return float(last["ts"])
        except (KeyError, TypeError, ValueError):
            return ctx.now - FIRST_RUN_WINDOW

    @staticmethod
    def _new_entries(since: float) -> list[tuple[str, os.stat_result]]:
        out: list[tuple[str, os.stat_result]] = []
        for raw in DIRS:
            d = Path(os.path.expandvars(os.path.expanduser(raw)))
            if not raw.strip("$") or not d.is_dir():
                continue
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if e.is_symlink() or e.name.startswith("."):
                    continue
                arrived = max(st.st_mtime, getattr(st, "st_birthtime", 0.0))
                if arrived > since:
                    out.append((e.path, st))
        return out

    @staticmethod
    def _quarantine(path: str) -> dict[str, Any] | None:
        """Parse 'flags;hextime;agent;uuid' from the quarantine xattr, or None when absent."""
        rc, out, _ = run_cmd(["xattr", "-p", "com.apple.quarantine", path], timeout=5)
        if rc != 0 or not out.strip():
            return None
        parts = (out.strip().split(";") + ["", "", "", ""])[:4]
        try:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(int(parts[1], 16)))
        except ValueError:
            ts = None
        return {"flags": parts[0], "ts": ts, "agent": parts[2] or "unknown"}
