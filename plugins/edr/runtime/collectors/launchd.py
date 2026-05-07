"""launchd persistence collector.

Enumerates plists in user/system LaunchAgents + LaunchDaemons (excludes /System
which is Apple-managed). Emits one Evidence per plist with the resolved target
program and its codesign verdict — the key signal for triage rules.
"""
from __future__ import annotations

import os
import plistlib
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import codesign_verdict, load_json_cache, save_json_cache

# Excludes /System/Library/Launch* — those are Apple-managed and noisy to diff.
LAUNCH_DIRS = [
    "/Library/LaunchAgents",
    "/Library/LaunchDaemons",
    "~/Library/LaunchAgents",
]


class LaunchdCollector(Collector):
    name = "launchd"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1547.011", "T1543.001", "T1543.004"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        cache_path = ctx.data_dir / "state" / "codesign_cache.json"
        codesign_cache: dict[str, Any] = load_json_cache(cache_path, default={})
        evidences: list[Evidence] = []

        for raw_dir in LAUNCH_DIRS:
            d = Path(os.path.expanduser(raw_dir))
            if not d.is_dir():
                continue
            for plist in sorted(d.glob("*.plist")):
                ev = self._evaluate(plist, codesign_cache)
                if ev:
                    evidences.append(ev)

        save_json_cache(cache_path, codesign_cache)
        return evidences

    def _evaluate(self, plist_path: Path, codesign_cache: dict[str, Any]) -> Evidence | None:
        try:
            data = plistlib.loads(plist_path.read_bytes())
        except (OSError, plistlib.InvalidFileException) as e:
            return Evidence(collector=self.name, kind="launchd_unparseable",
                            key=str(plist_path), attrs={"error": str(e)})

        program: str | None = data.get("Program")
        program_arguments = data.get("ProgramArguments") or []
        if not program and program_arguments:
            program = program_arguments[0]

        verdict = codesign_verdict(program, codesign_cache) if program and program.startswith("/") else {"status": "unresolved"}

        return Evidence(
            collector=self.name,
            kind="launchd_item",
            key=str(plist_path),
            attrs={
                "label": data.get("Label"),
                "program": program,
                "program_arguments": program_arguments,
                "run_at_load": bool(data.get("RunAtLoad", False)),
                "keep_alive": bool(data.get("KeepAlive", False)),
                "start_interval": data.get("StartInterval"),
                "user_name": data.get("UserName"),
                "scope": "user" if "/Users/" in str(plist_path) else "system",
                "target_codesign_status": verdict.get("status"),
                "target_codesign_team_id": verdict.get("team_id"),
            },
        )
