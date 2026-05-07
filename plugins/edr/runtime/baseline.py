"""Baseline: last-known-good system signature.

Stored as flat dict keyed by (collector, version, evidence_key) → evidence_dict.
Grows ONLY on confirmed FP or version bump — never auto-grows from raw observation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from collectors._base import Anomaly, Evidence, read_json, write_json

BASELINE_FILENAME = "baseline.json"


def _key(collector: str, version: int, evidence_key: str) -> str:
    return f"{collector}@{version}::{evidence_key}"


def load(state_dir: Path) -> dict[str, dict[str, Any]]:
    """Load baseline as {key: evidence_attrs}. Empty dict on first run."""
    return read_json(state_dir / BASELINE_FILENAME, default={})


def save(state_dir: Path, baseline: dict[str, dict[str, Any]]) -> None:
    write_json(state_dir / BASELINE_FILENAME, baseline)


def _strip_volatile(attrs: dict[str, Any], volatile: list[str]) -> dict[str, Any]:
    if not volatile:
        return attrs
    return {k: v for k, v in attrs.items() if k not in volatile}


def from_snapshot(snapshot: dict[str, list[Evidence]],
                  collector_versions: dict[str, int],
                  volatile_map: dict[str, list[str]] | None = None) -> dict[str, dict[str, Any]]:
    """Build a baseline from a snapshot — used for bootstrap and after FP graduation.

    volatile_map: per-collector attr names to strip before storing (so they're not
    used in subsequent diff comparisons).
    """
    volatile_map = volatile_map or {}
    out: dict[str, dict[str, Any]] = {}
    for collector_name, evidences in snapshot.items():
        version = collector_versions.get(collector_name, 1)
        volatile = volatile_map.get(collector_name, [])
        for ev in evidences:
            out[_key(collector_name, version, ev.key)] = {
                "kind": ev.kind,
                "attrs": _strip_volatile(ev.attrs, volatile),
            }
    return out


def diff_against(snapshot: dict[str, list[Evidence]],
                 baseline: dict[str, dict[str, Any]],
                 collector_versions: dict[str, int],
                 volatile_map: dict[str, list[str]] | None = None) -> list[Anomaly]:
    """Compute anomalies between current snapshot and baseline.

    A baseline entry whose collector version doesn't match the current version
    is ignored (treated as absent → all current evidence shows as 'added' for
    that collector). This is how version bumps invalidate stale baseline.
    """
    volatile_map = volatile_map or {}
    anomalies: list[Anomaly] = []
    seen_keys: set[str] = set()

    # Forward pass: added or modified
    for collector_name, evidences in snapshot.items():
        version = collector_versions.get(collector_name, 1)
        volatile = volatile_map.get(collector_name, [])
        for ev in evidences:
            bk = _key(collector_name, version, ev.key)
            seen_keys.add(bk)
            prior_dict = baseline.get(bk)
            if prior_dict is None:
                anomalies.append(Anomaly(change="added", evidence=ev))
            elif _attrs_changed(prior_dict["attrs"], _strip_volatile(ev.attrs, volatile)):
                prior_ev = Evidence(
                    collector=collector_name,
                    kind=prior_dict["kind"],
                    key=ev.key,
                    attrs=prior_dict["attrs"],
                    ts=0.0,
                )
                anomalies.append(Anomaly(change="modified", evidence=ev, prior=prior_ev))

    # Reverse pass: removed (only for collectors that ran this tick)
    ran_collectors = {(c, collector_versions.get(c, 1)) for c in snapshot.keys()}
    for bk, prior_dict in baseline.items():
        if bk in seen_keys:
            continue
        try:
            collector_name, rest = bk.split("@", 1)
            ver_str, ev_key = rest.split("::", 1)
            version = int(ver_str)
        except ValueError:
            continue
        if (collector_name, version) not in ran_collectors:
            continue  # collector didn't run this tick — silent on absence
        prior_ev = Evidence(
            collector=collector_name,
            kind=prior_dict["kind"],
            key=ev_key,
            attrs=prior_dict["attrs"],
            ts=0.0,
        )
        anomalies.append(Anomaly(change="removed", evidence=prior_ev, prior=prior_ev))

    return anomalies


def _attrs_changed(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str)


def add_to_baseline(state_dir: Path, collector: str, version: int, evidence_key: str, evidence: Evidence) -> None:
    """Used by FP confirmation flow (Phase B) to grow baseline."""
    baseline = load(state_dir)
    baseline[_key(collector, version, evidence_key)] = {
        "kind": evidence.kind,
        "attrs": evidence.attrs,
    }
    save(state_dir, baseline)
