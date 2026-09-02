"""Triage fast-path.

Two responsibilities only:
  1. Auto-suppress: drop anomalies whose signature_hash is in the FP registry.
  2. Auto-promote: assign a *floor* severity for textbook-bad signals.
     The analyst can RAISE the floor but cannot lower it.

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
from collectors._base import Anomaly, read_json

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


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
            if not _rule_matches(rule, anomaly):
                continue
            floor = rule.get("floor", "info")
            if anomaly.floor_severity is None or SEVERITY_ORDER[floor] > SEVERITY_ORDER[anomaly.floor_severity]:
                anomaly.floor_severity = floor
    return anomalies


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
