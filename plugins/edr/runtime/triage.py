"""Triage fast-path.

Three responsibilities only:
  1. Auto-suppress: drop anomalies whose signature_hash is in the FP registry.
  2. Auto-promote: assign a *floor* severity for textbook-bad signals.
     The analyst can RAISE the floor but cannot lower it.
  3. Intel match: any attr that names an ip, domain or sha256 is looked up in
     the IOC database; a hit floors the anomaly at critical.

A rule with `auto_accept: true` folds its matches straight into the baseline
(Apple platform binaries coming and going): they are marked suppressed with
`auto_accepted: <rule id>` and never reach the analyst.

A rule with `always: true` is also evaluated against evidence that produced no
anomaly (a baselined shell running a new `curl | sh` command line, for
instance); a match becomes an anomaly with change='flagged'.

Rule condition grammar: `change`, `kind`, any attr name (scalar or list membership),
`path_glob` / `<attr>_glob` (fnmatch, list-valued attrs match if any element does),
`content_pattern` / `<attr>_pattern` (regex search; list-valued attrs are joined).

Rules are loaded from plugin defaults (`paths.DEFAULT_TRIAGE_RULES`) overlaid by
optional host-local overrides (`paths.USER_TRIAGE_RULES`). Rule IDs collide-by-id,
user version wins; non-colliding rules append.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

import yaml

import paths
from collectors._base import Anomaly, Evidence, read_json

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# evidence attr → IOC type in the intel database
INTEL_ATTRS = {"ip": "ip", "remote_ip": "ip", "remote_ips": "ip", "domain": "domain",
               "domains": "domain", "sha256": "hash_sha256", "exe_sha256": "hash_sha256"}


def load_rules() -> list[dict[str, Any]]:
    """Plugin defaults + optional host overrides; user rules win on id collision."""
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for src in (paths.DEFAULT_TRIAGE_RULES, paths.USER_TRIAGE_RULES):
        if not src.exists():
            continue
        try:
            data = yaml.safe_load(src.read_text()) or {}
        except yaml.YAMLError:
            continue
        for rule in (data.get("rules") or []):
            rid = rule.get("id") or ""
            if not rid:
                continue
            if rid not in by_id:
                order.append(rid)
            by_id[rid] = rule
    return [by_id[rid] for rid in order]


def load_fp_registry(state_dir: Path) -> set[str]:
    """Phase A: read from local mirror. Phase B: synced from cloud Firestore at top of run."""
    fp_path = state_dir / "false_positives.json"
    sigs = read_json(fp_path, default=[])
    return set(sigs) if isinstance(sigs, list) else set()


def apply(anomalies: list[Anomaly], rules: list[dict[str, Any]], fp_sigs: set[str]) -> list[Anomaly]:
    for anomaly in anomalies:
        if anomaly.evidence.signature_hash() in fp_sigs:
            anomaly.suppressed = True
            continue
        for rule in rules:
            if rule.get("auto_accept") or not _rule_matches(rule, anomaly):
                continue
            floor = rule.get("floor", "info")
            if floor not in SEVERITY_ORDER:
                continue  # a typo in a user rule must not crash the scan
            if anomaly.floor_severity is None or SEVERITY_ORDER[floor] > SEVERITY_ORDER[anomaly.floor_severity]:
                anomaly.floor_severity = floor
    return anomalies


def auto_accept(anomalies: list[Anomaly], rules: list[dict[str, Any]]) -> list[Anomaly]:
    """Mark anomalies matched by an `auto_accept` rule; the caller folds them into the baseline."""
    accepting = [r for r in rules if r.get("auto_accept")]
    taken: list[Anomaly] = []
    for anomaly in anomalies:
        if anomaly.suppressed or anomaly.change not in ("added", "modified"):
            continue
        rule = next((r for r in accepting if _rule_matches(r, anomaly)), None)
        if rule:
            anomaly.suppressed = True
            anomaly.evidence.attrs["auto_accepted"] = rule.get("id")
            taken.append(anomaly)
    return taken


def apply_always(anomalies: list[Anomaly], snapshot: dict[str, list[Evidence]],
                 rules: list[dict[str, Any]]) -> int:
    """Run `always` rules over evidence that is not already an anomaly; matches are appended as 'flagged'."""
    always = [r for r in rules if r.get("always")]
    if not always:
        return 0
    known = {(a.evidence.collector, a.evidence.key) for a in anomalies}
    added = 0
    for evs in snapshot.values():
        for ev in evs:
            if (ev.collector, ev.key) in known:
                continue
            probe = Anomaly(change="flagged", evidence=ev)
            for rule in always:
                if _rule_matches(rule, probe):
                    floor = rule.get("floor", "info")
                    if floor in SEVERITY_ORDER and (probe.floor_severity is None
                                                    or SEVERITY_ORDER[floor] > SEVERITY_ORDER[probe.floor_severity]):
                        probe.floor_severity = floor
            if probe.floor_severity is not None:
                anomalies.append(probe)
                added += 1
    return added


def apply_intel(anomalies: list[Anomaly], snapshot: dict[str, list[Evidence]] | None = None,
                db_path: Path | None = None) -> int:
    """Floor at critical everything whose ip / domain / sha256 attrs hit the IOC db.

    Checks every evidence in the snapshot, not only anomalies: a known-bad remote
    inside an already-baselined (command, port) pair must still surface. Such a
    hit is appended as an anomaly with change='flagged'.
    """
    db_path = db_path or paths.INTEL_DB
    if not db_path.exists():
        return 0
    from intel import db as ioc_db
    known = {(a.evidence.collector, a.evidence.key) for a in anomalies}
    candidates = list(anomalies) + [
        Anomaly(change="flagged", evidence=ev)
        for evs in (snapshot or {}).values() for ev in evs if (ev.collector, ev.key) not in known
    ]
    hits = 0
    with ioc_db.connect(db_path) as conn:
        for anomaly in candidates:
            if anomaly.suppressed:
                continue
            matches = []
            for attr, ioc_type in INTEL_ATTRS.items():
                raw = anomaly.evidence.attrs.get(attr)
                for value in (raw if isinstance(raw, list) else [raw]):
                    if not value:
                        continue
                    value = str(value)
                    if ioc_type == "ip" and value.count(":") == 1:
                        value = value.split(":")[0]  # ip:port → ip
                    for row in ioc_db.lookup(conn, ioc_type, value):
                        if row["feed"] != "mitre_macos":
                            matches.append({"type": ioc_type, "value": value,
                                            "feed": row["feed"], "severity": row["severity"]})
            if matches:
                anomaly.evidence.attrs["intel"] = matches[:10]
                anomaly.floor_severity = "critical"
                hits += 1
                if anomaly.change == "flagged":
                    anomalies.append(anomaly)
    return hits


def _rule_matches(rule: dict[str, Any], anomaly: Anomaly) -> bool:
    if rule.get("collector") and rule["collector"] != anomaly.evidence.collector:
        return False
    if not _conditions_hold(rule.get("match", {}) or {}, anomaly):
        return False
    exclude = rule.get("exclude") or {}
    if exclude and _conditions_hold(exclude, anomaly):
        return False
    return True


def _conditions_hold(conditions: dict[str, Any], anomaly: Anomaly) -> bool:
    ev = anomaly.evidence
    for field, expected in conditions.items():
        if field == "change":
            actual = anomaly.change
        elif field == "kind":
            actual = ev.kind
        elif field == "path_glob":
            path_val = ev.attrs.get("path", "")
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(fnmatch.fnmatch(str(path_val), _expand_user(p)) for p in patterns):
                return False
            continue
        elif field == "content_pattern":
            content = ev.attrs.get("content_added") or ev.attrs.get("content") or ""
            if not re.search(expected, str(content)):
                return False
            continue
        elif field.endswith("_glob"):
            raw = ev.key if field == "key_glob" else ev.attrs.get(field[:-5])
            values = raw if isinstance(raw, list) else [raw]
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(fnmatch.fnmatch(str(v), _expand_user(p)) for v in values if v for p in patterns):
                return False
            continue
        elif field.endswith("_pattern"):
            raw = ev.attrs.get(field[:-8])
            text = "\n".join(str(v) for v in raw) if isinstance(raw, list) else str(raw or "")
            if not re.search(expected, text, re.IGNORECASE):
                return False
            continue
        else:
            actual = ev.attrs.get(field)
        if not _scalar_match(actual, expected):
            return False
    return True


def _scalar_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return actual in expected
    if isinstance(expected, bool):
        return bool(actual) == expected
    return actual == expected


def _expand_user(p: str) -> str:
    return str(Path(p).expanduser()) if p.startswith("~") else p
