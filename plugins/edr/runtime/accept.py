"""`edr accept` — fold anomalies the user confirmed benign into the baseline.

Baseline grows only here (and on bootstrap). Accepting an `added`/`modified`
anomaly stores its current non-volatile attrs, so a later change to the same
artifact re-alerts; accepting a `removed` one drops the stale key. Entries
whose collector version no longer matches are pruned on every save.

CLI: `edr accept <sig> [<sig>...] [--snapshot <ts>]` · `edr accept --all`
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import baseline as baseline_mod  # noqa: E402
import paths  # noqa: E402
from collectors._base import Evidence, read_json  # noqa: E402


def latest_snapshot_ts() -> str | None:
    root = paths.STATE_DIR / "snapshots"
    dirs = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []
    return dirs[-1] if dirs else None


def _collector_meta() -> tuple[dict[str, int], dict[str, list[str]], set[str]]:
    """Current class versions, volatile attrs, and the set of stateless (event) collectors."""
    import run_collectors
    manifest = run_collectors.load_manifest()
    versions, volatile, stateless = {}, {}, set()
    for cls in run_collectors.discover_collectors():
        run_collectors.apply_manifest(cls, manifest)
        versions[cls.name] = cls.version
        volatile[cls.name] = list(cls.volatile_attrs)
        if cls.stateless:
            stateless.add(cls.name)
    return versions, volatile, stateless


def accept(sigs: list[str] | None, snapshot_ts: str | None = None, all_: bool = False,
           collector: str | None = None) -> dict[str, Any]:
    """`collector` narrows `--all` to one collector — the re-baseline after a version bump."""
    ts = snapshot_ts or latest_snapshot_ts()
    snap_dir = paths.STATE_DIR / "snapshots" / str(ts)
    diff = read_json(snap_dir / "diff.json", default={}) if ts else {}
    anomalies = diff.get("anomalies") or [] if isinstance(diff, dict) else []
    wanted = set(sigs or [])
    versions, volatile, stateless = _collector_meta()
    baseline = baseline_mod.load(paths.STATE_DIR)
    accepted: list[str] = []

    for a in anomalies:
        ev = a.get("evidence") or {}
        if a.get("suppressed") or not ev or (collector and ev.get("collector") != collector):
            continue
        if ev.get("collector") in stateless:
            continue  # events are reported once, never baselined
        sig = Evidence(ev["collector"], ev["kind"], ev["key"], ev.get("attrs") or {}).signature_hash()
        if not all_ and sig not in wanted:
            continue
        snap = read_json(snap_dir / f"{ev['collector']}.json", default={})
        version = int((snap or {}).get("version") or versions.get(ev["collector"], 1))
        bk = baseline_mod._key(ev["collector"], version, ev["key"])
        if a.get("change") == "removed":
            baseline.pop(bk, None)
        else:
            attrs = baseline_mod._strip_volatile(ev.get("attrs") or {}, volatile.get(ev["collector"], []))
            baseline[bk] = {"kind": ev["kind"], "attrs": attrs}
        accepted.append(sig)

    pruned = [bk for bk in baseline if _stale(bk, versions)]
    for bk in pruned:
        del baseline[bk]
    if accepted or pruned:
        baseline_mod.save(paths.STATE_DIR, baseline)
    return {"snapshot": ts, "accepted": accepted, "pruned": len(pruned),
            "unmatched": sorted(wanted - set(accepted))}


def _stale(bk: str, versions: dict[str, int]) -> bool:
    try:
        collector, rest = bk.split("@", 1)
        version = int(rest.split("::", 1)[0])
    except ValueError:
        return True
    return collector in versions and version != versions[collector]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edr accept")
    ap.add_argument("sigs", nargs="*", help="signature hashes from diff.json")
    ap.add_argument("--all", action="store_true", help="accept every non-suppressed anomaly")
    ap.add_argument("--snapshot", help="snapshot ts (default: latest)")
    ap.add_argument("--collector", help="with --all: only this collector (re-baseline after a version bump)")
    args = ap.parse_args(argv)
    if not args.sigs and not args.all:
        ap.error("give one or more sigs, or --all")
    paths.ensure()
    print(json.dumps(accept(args.sigs, args.snapshot, args.all, args.collector), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
