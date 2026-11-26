#!/usr/bin/env python3
"""Advisory watch: re-read the whole dependency tree against the advisory database on a clock,
and count the security work still open. Advisories are published on their own schedule, not when
code changes, so this runs beside the work — at session start and after a task's scan — and
never makes a task wait on the network.

    watch.py refresh [--if-older HOURS] [--background]   # run the dependency slot on the whole tree
    watch.py open [--line | --json]                      # the one count of open security work

Counted over what the latest check still finds: unjudged (no statement, or one that names no filed
roadmap item, or `fixed` yet still found), filed (an open roadmap item owns it — an upgrade not yet
landed), left (exploitable with no published fix: visible, never a target of zero), and unfiled
(exploitable with no item yet); plus the other slots' backlog above low. An advisory the latest check
no longer finds is closed, whatever its old statement says — an upgrade closes it without anyone
editing vex.yaml.

Writes only the gitignored .claude/scans/watch.json. Sends what the dependency slot sends —
package names and versions, to the advisory database — with no code change behind it.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scan as S  # noqa: E402 — the slots, the runner and the decisions live there

REFRESH_H = 24  # a record older than this is refreshed when the next trigger fires
STALE_H = 72    # older than this, the count says so: a check nobody refreshed is not "clean"
LOCK_S = 900    # a lock older than this belongs to a refresh that died
OUT = S.SCANS / "watch.json"
LOCK = S.SCANS / "watch.lock"


def record() -> dict | None:
    try:
        return json.loads(OUT.read_text())
    except (OSError, ValueError):
        return None


def age_h(rec: dict | None) -> float | None:
    return (time.time() - rec["ts"]) / 3600 if rec and rec.get("ts") else None


def current(rec: dict | None, hours: float) -> bool:
    """Young enough, and no dependency manifest changed since the commit it read — so the count
    drops on the task that lands an upgrade, not a day later."""
    h = age_h(rec)
    if h is None or h >= hours:
        return False
    head, pat = rec.get("head", ""), S.conf("DEPENDENCY_MANIFESTS")
    if not S.ancestor(head, S.git("rev-parse", "HEAD")):
        return False
    return not pat or not any(re.search(pat, f) for f in S.changed(head, deleted=True))


def refresh(a):
    if a.if_older is not None and current(record(), a.if_older):
        return
    S.SCANS.mkdir(parents=True, exist_ok=True)
    if a.background:  # detach: the caller is a task or a session start, and must not wait
        subprocess.Popen([sys.executable, __file__, "refresh"], cwd=S.ROOT, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return
    try:  # one refresh per project at a time
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime < LOCK_S:
            return
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        sel = [e for e in S.entries() if e.get("slot") == "dependencies" and e.get("command")]
        rec = {"ts": time.time(), "head": S.git("rev-parse", "HEAD"), "state": "empty", "findings": []}
        if sel:
            keep, S.SCANS = S.SCANS, S.SCANS / "watch"  # its own folder: never races a task scan's output
            try:
                state = S.run_entries(sel, "every", rec["head"], "", whole=True)
            finally:
                S.SCANS = keep
            states = {r["state"] for r in state.values()}
            rec["state"] = "errored" if "errored" in states else "ran"
            seen = {}
            for r in state.values():
                for f in r.get("findings", []):
                    d = f["dep"] or {}
                    cur = seen.setdefault(f["key"], {"key": f["key"], "id": d.get("id"), "aliases": d.get("aliases", []),
                                                     "package": d.get("package"), "version": d.get("version"),
                                                     "severity": f["severity"], "fixed": d.get("fixed"), "files": []})
                    if S.F.RANK.get(f["severity"], 0) > S.F.RANK.get(cur["severity"], 0):
                        cur["severity"] = f["severity"]
                    cur["files"] = sorted(set(cur["files"]) | {f["file"]})
            rec["findings"] = list(seen.values())
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1))
        tmp.replace(OUT)
    finally:
        LOCK.unlink(missing_ok=True)


def count() -> dict:
    rec, dec = record(), S.decisions()
    out = {"state": (rec or {}).get("state", "never"), "age_h": age_h(rec), "unjudged": 0, "filed": 0,
           "left": 0, "unfiled": 0, "critical": {}, "backlog": 0}
    for f in (rec or {}).get("findings", []):
        keys = [f["key"]] + [f"{i}@{f['package']}" for i in f.get("aliases", [])]
        found = [dec[k] for k in keys if k in dec]
        s = next((c for c in found if c.get("status") != "under_investigation"), found[0] if found else None) or {}
        status, item = s.get("status"), S.filed_item(s.get("addressed", ""))
        if status == "not_affected":
            continue
        if status == "affected" and not f.get("fixed"):
            out["left" if item else "unfiled"] += 1  # exploitable, no upstream fix: a mitigation's, not zero's
            continue
        if status == "affected" and not item:
            out["unfiled"] += 1
        elif item and status != "fixed":
            out["filed"] += 1  # an open item owns it: open until the check stops finding it
        else:
            out["unjudged"] += 1  # no statement, an item nobody filed, or `fixed` yet still found
        if f["severity"] == "critical":
            out["critical"][f["package"]] = f.get("fixed") or "no fix — judge it"
    rows = [ln.split(None, 4) for ln in S.read(S.BASELINE).splitlines() if ln and not ln.startswith("#")]
    out["backlog"] = sum(1 for r in rows if len(r) > 2 and r[0] != "dependencies" and r[1] not in dec and r[2] != "low")
    return out


def line(c: dict) -> str:
    if c["state"] == "never":
        return f"advisories: unknown — never checked · backlog {c['backlog']} · Next: /audit"
    age = f"checked {c['age_h']:.0f}h ago" + (" — stale" if c["age_h"] > STALE_H else "")
    if c["state"] == "errored":
        return f"advisories: unknown — the last check failed ({age}; see .claude/scans/watch/) · backlog {c['backlog']}"
    if c["state"] == "empty":
        return f"advisories: not watched — no dependency slot tool · backlog {c['backlog']}"
    parts = [f"{c[k]} {k}" for k in ("unjudged", "unfiled", "filed") if c[k]] or ["0 open"]
    if c["critical"]:
        parts.append(f"{len(c['critical'])} critical (" + ", ".join(f"{p} → {v}" for p, v in sorted(c["critical"].items())) + ")")
    if c["left"]:
        parts.append(f"{c['left']} left with no upstream fix")
    nxt = " · Next: /audit" if c["unjudged"] or c["unfiled"] or c["backlog"] else ""
    return "advisories: " + " · ".join(parts) + f" · backlog {c['backlog']} · {age}{nxt}"


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh")
    r.add_argument("--if-older", type=float, nargs="?", const=REFRESH_H)
    r.add_argument("--background", action="store_true")
    o = sub.add_parser("open")
    o.add_argument("--json", action="store_true")
    o.add_argument("--line", action="store_true")
    a = p.parse_args()
    if a.cmd == "refresh":
        refresh(a)
    else:
        c = count()
        print(json.dumps(c) if a.json else line(c))


if __name__ == "__main__":
    main()
