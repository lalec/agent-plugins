"""Auto-changelog: detect manifest graduations + pending_changes additions, record to changelog.md.

Runs at the top of every `/edr:macos` tick (before collectors). lessons.md stays purely
human-curated; this records mechanical structural events.

Why in-runner instead of Claude Code hooks: hook matchers scope by tool name only,
not file path. A PostToolUse hook would fire on every Write/Edit globally and pollute
every session. Natural alignment is "run at the top of every analyst pass" — what
`/edr:macos` does anyway.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

import paths

LAST_SEEN_FILE = "last_seen.json"
PRUNE_DAYS = 30
DATE_HEADER = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b")


def _current_state() -> dict[str, Any]:
    """Snapshot: collector manifest (plugin defaults overlaid by user override) + pending_changes/."""
    manifest: dict[str, dict[str, Any]] = {}
    for src in (paths.DEFAULT_MANIFEST, paths.USER_MANIFEST):
        if not src.exists():
            continue
        try:
            data = yaml.safe_load(src.read_text()) or {}
        except yaml.YAMLError:
            continue
        for name, entry in (data.get("collectors") or {}).items():
            base = manifest.get(name, {})
            base.update(entry or {})
            manifest[name] = base
    manifest = {n: {"maturity": e.get("maturity", "experimental"), "version": e.get("version", 1)}
                for n, e in manifest.items()}

    pending: dict[str, int] = {}
    if paths.PENDING_DIR.is_dir():
        for f in paths.PENDING_DIR.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(paths.PENDING_DIR))
                try:
                    pending[rel] = int(f.stat().st_mtime)
                except OSError:
                    pass

    return {"manifest": manifest, "pending": pending}


def _diff_events(prior: dict[str, Any], current: dict[str, Any]) -> list[str]:
    out: list[str] = []
    prior_m = prior.get("manifest", {})
    cur_m = current["manifest"]

    for name, entry in cur_m.items():
        if name not in prior_m:
            out.append(f"new collector `{name}` registered (maturity={entry['maturity']}, version={entry['version']})")
            continue
        p = prior_m[name]
        if entry["maturity"] != p["maturity"]:
            out.append(f"`{name}` graduated {p['maturity']} → {entry['maturity']}")
        if entry["version"] != p["version"]:
            out.append(f"`{name}` version bumped {p['version']} → {entry['version']} (baseline entries auto-invalidated)")
    for name in prior_m:
        if name not in cur_m:
            out.append(f"`{name}` collector removed from manifest")

    prior_p = prior.get("pending", {})
    for path in current["pending"]:
        if path not in prior_p:
            out.append(f"new pending change `pending_changes/{path}` — analyst proposal awaiting review")
    for path in prior_p:
        if path not in current["pending"]:
            out.append(f"pending change `pending_changes/{path}` resolved (moved or deleted)")
    return out


def cross_pollinate() -> list[str]:
    """Run at top of every tick. Returns the list of newly-recorded events."""
    last_seen_path = paths.STATE_DIR / LAST_SEEN_FILE
    current = _current_state()

    if not last_seen_path.exists():
        paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
        last_seen_path.write_text(json.dumps(current, sort_keys=True, indent=2))
        return []

    try:
        prior = json.loads(last_seen_path.read_text())
    except json.JSONDecodeError:
        prior = {}

    events = _diff_events(prior, current)
    if events:
        _append_to_changelog(paths.CHANGELOG_FILE, events)
    last_seen_path.write_text(json.dumps(current, sort_keys=True, indent=2))
    return events


def _append_to_changelog(changelog_path: Path, events: list[str]) -> None:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    hms = time.strftime("%H:%M:%SZ", time.gmtime())
    bullets = [f"- {hms} — {e}" for e in events]

    body = changelog_path.read_text() if changelog_path.exists() else _starter_changelog()
    head, sections = _split_sections(body)

    if sections and DATE_HEADER.match(sections[0].lstrip()):
        m = DATE_HEADER.match(sections[0].lstrip())
        if m and m.group(1) == today:
            sections[0] = sections[0].rstrip() + "\n" + "\n".join(bullets) + "\n"
        else:
            sections.insert(0, f"## {today}\n\n" + "\n".join(bullets) + "\n")
    else:
        sections.insert(0, f"## {today}\n\n" + "\n".join(bullets) + "\n")

    cutoff_ts = time.time() - PRUNE_DAYS * 86400
    kept: list[str] = []
    for sec in sections:
        m = DATE_HEADER.match(sec.lstrip())
        if not m:
            kept.append(sec)
            continue
        try:
            sec_ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
        except ValueError:
            kept.append(sec)
            continue
        if sec_ts >= cutoff_ts:
            kept.append(sec)

    changelog_path.write_text(head.rstrip() + "\n\n" + "\n".join(s.rstrip() + "\n" for s in kept))


def _split_sections(body: str) -> tuple[str, list[str]]:
    parts = re.split(r"(?m)^(?=## )", body)
    head = parts[0] if parts else ""
    sections = parts[1:] if len(parts) > 1 else []
    return head, sections


def _starter_changelog() -> str:
    return (
        "# edr — automated changelog\n\n"
        "Auto-generated by `run_collectors.py` at the top of every `/edr:macos` tick. "
        "Records collector graduations, manifest version bumps, and `pending_changes/` activity. "
        "Read alongside `lessons.md` at run start.\n\n"
        f"Pruned to last {PRUNE_DAYS} days. Do not edit by hand — your edits will be overwritten.\n\n"
    )
