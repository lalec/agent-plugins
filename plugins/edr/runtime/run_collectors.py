#!/usr/bin/env python3
"""edr runner: discover collectors, run eligible tiers, snapshot, diff, triage.

Reads code from this plugin runtime dir; writes all state to DATA_DIR (default
`~/.claude/edr/`, override via `EDR_HOME`). See paths.py.

CLI:
  edr                                       # default — run T-tier (and D-tier if due)
  edr --bootstrap                           # write baseline; emit no anomalies
  edr --tier T                              # force a specific tier
  edr --collector NAME                      # run a single collector
  edr --no-snapshot                         # don't persist snapshot to disk (for tests)
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

import baseline as baseline_mod  # noqa: E402
import changelog as changelog_mod  # noqa: E402
import paths  # noqa: E402
import triage  # noqa: E402
from collectors._base import Anomaly, Collector, CollectorContext, Evidence, write_json  # noqa: E402

DAILY_INTERVAL_SEC = 23 * 3600


def discover_collectors() -> list[type[Collector]]:
    discovered: list[type[Collector]] = []
    collectors_dir = ROOT / "collectors"
    for path in sorted(collectors_dir.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        mod = importlib.import_module(f"collectors.{path.stem}")
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, Collector) and obj is not Collector:
                discovered.append(obj)
    return discovered


def load_manifest() -> dict[str, dict[str, Any]]:
    """Plugin defaults overlaid by host-local user manifest (if present)."""
    out: dict[str, dict[str, Any]] = {}
    for src in (paths.DEFAULT_MANIFEST, paths.USER_MANIFEST):
        if not src.exists():
            continue
        try:
            data = yaml.safe_load(src.read_text()) or {}
        except yaml.YAMLError:
            continue
        for name, entry in (data.get("collectors") or {}).items():
            base = out.get(name, {})
            base.update(entry or {})
            out[name] = base
    return out


def apply_manifest(cls: type[Collector], manifest: dict[str, dict[str, Any]]) -> None:
    entry = manifest.get(cls.name)
    if not entry:
        return
    if "maturity" in entry:
        cls.maturity = entry["maturity"]
    if "version" in entry:
        cls.version = entry["version"]


def daily_due(state_dir: Path, now: float) -> bool:
    last_path = state_dir / "last_daily_run.json"
    if not last_path.exists():
        return True
    try:
        last = json.loads(last_path.read_text()).get("ts", 0)
    except Exception:
        return True
    return (now - last) > DAILY_INTERVAL_SEC


def select_collectors(classes: list[type[Collector]], wanted_tier: str | None,
                      single: str | None, run_daily: bool) -> list[type[Collector]]:
    out: list[type[Collector]] = []
    for cls in classes:
        if single:
            if cls.name == single:
                out.append(cls)
            continue
        if wanted_tier:
            if cls.tier == wanted_tier:
                out.append(cls)
            continue
        if cls.tier == "T" or (cls.tier == "D" and run_daily):
            out.append(cls)
    return out


def run_one(cls: type[Collector], ctx: CollectorContext) -> list[Evidence]:
    try:
        return cls().collect(ctx)
    except Exception as e:
        tb = traceback.format_exc(limit=5)
        return [Evidence(collector=cls.name, kind="error", key="collector_crash",
                         attrs={"error": str(e), "traceback": tb})]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", action="store_true")
    p.add_argument("--tier", choices=["T", "D", "OD"])
    p.add_argument("--collector")
    p.add_argument("--no-snapshot", action="store_true")
    args = p.parse_args()

    paths.ensure()
    state_dir = paths.STATE_DIR

    if not args.no_snapshot and not args.collector:
        changelog_mod.cross_pollinate()

    now = time.time()
    snapshot_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    snapshot_dir = state_dir / "snapshots" / snapshot_ts
    if not args.no_snapshot:
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    ctx = CollectorContext.build(paths.DATA_DIR, snapshot_dir)
    manifest = load_manifest()
    classes = discover_collectors()
    for cls in classes:
        apply_manifest(cls, manifest)

    run_daily = daily_due(state_dir, now)
    selected = select_collectors(classes, args.tier, args.collector, run_daily)

    snapshot: dict[str, list[Evidence]] = {}
    versions: dict[str, int] = {}
    volatile_map: dict[str, list[str]] = {}
    for cls in selected:
        evs = run_one(cls, ctx)
        snapshot[cls.name] = evs
        versions[cls.name] = cls.version
        volatile_map[cls.name] = list(cls.volatile_attrs)
        if not args.no_snapshot:
            write_json(snapshot_dir / f"{cls.name}.json",
                       {"version": cls.version, "evidence": [e.to_dict() for e in evs]})

    baseline = baseline_mod.load(state_dir)
    if args.bootstrap or not baseline:
        new_baseline = baseline_mod.from_snapshot(snapshot, versions, volatile_map)
        if not args.no_snapshot:
            baseline_mod.save(state_dir, new_baseline)
        anomalies: list[Anomaly] = []
        bootstrap = True
    else:
        anomalies = baseline_mod.diff_against(snapshot, baseline, versions, volatile_map)
        bootstrap = False

    rules = triage.load_rules()
    fp_sigs = triage.load_fp_registry(state_dir)
    triage.apply(anomalies, rules, fp_sigs)

    if not args.no_snapshot:
        write_json(snapshot_dir / "diff.json", {"anomalies": [a.to_dict() for a in anomalies]})

    telemetry_row = {
        "ts": now,
        "snapshot": snapshot_ts,
        "bootstrap": bootstrap,
        "ran_daily": run_daily,
        "collectors": {
            cls.name: {
                "tier": cls.tier,
                "maturity": cls.maturity,
                "version": cls.version,
                "evidence_count": len(snapshot.get(cls.name, [])),
            }
            for cls in selected
        },
        "anomalies_total": len(anomalies),
        "anomalies_suppressed": sum(1 for a in anomalies if a.suppressed),
        "anomalies_floored": sum(1 for a in anomalies if a.floor_severity),
    }
    if not args.no_snapshot:
        with (state_dir / "telemetry.jsonl").open("a") as f:
            f.write(json.dumps(telemetry_row) + "\n")

    if not args.no_snapshot:
        write_json(state_dir / "last_run.json", {"ts": now, "snapshot": snapshot_ts})
        if run_daily:
            write_json(state_dir / "last_daily_run.json", {"ts": now})

    summary = {
        "snapshot_dir": str(snapshot_dir),
        "data_dir": str(paths.DATA_DIR),
        "plugin_dir": str(paths.PLUGIN_DIR),
        "bootstrap": bootstrap,
        "ran_daily": run_daily,
        "collectors_run": [cls.name for cls in selected],
        "anomalies_total": len(anomalies),
        "anomalies_active": sum(1 for a in anomalies if not a.suppressed),
        "anomalies_floored": [
            {"sig": a.evidence.signature_hash(), "collector": a.evidence.collector,
             "kind": a.evidence.kind, "key": a.evidence.key, "floor": a.floor_severity}
            for a in anomalies if a.floor_severity and not a.suppressed
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
