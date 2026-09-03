"""`edr accept`: baseline grows only here; volatile attrs stripped; stale versions pruned."""
from __future__ import annotations

import accept
import baseline as baseline_mod
import paths
from collectors._base import Evidence, write_json

TS = "20260101T000000Z"
ADDED = {"collector": "launchd", "kind": "launchd_item", "key": "/x.plist", "attrs": {"a": 1, "mtime": 5}}
REMOVED = {"collector": "launchd", "kind": "launchd_item", "key": "/gone.plist", "attrs": {}}


def _snapshot():
    d = paths.STATE_DIR / "snapshots" / TS
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "diff.json", {"anomalies": [
        {"change": "added", "suppressed": False, "evidence": ADDED},
        {"change": "removed", "suppressed": False, "evidence": REMOVED},
        {"change": "added", "suppressed": True, "evidence": {**ADDED, "key": "/suppressed"}},
    ]})
    write_json(d / "launchd.json", {"version": 1, "evidence": []})


def test_accept_by_sig_then_all(monkeypatch):
    monkeypatch.setattr(accept, "_collector_meta", lambda: ({"launchd": 1}, {"launchd": ["mtime"]}))
    _snapshot()
    baseline_mod.save(paths.STATE_DIR, {
        "launchd@1::/gone.plist": {"kind": "launchd_item", "attrs": {}},
        "launchd@0::/stale": {"kind": "launchd_item", "attrs": {}},
    })
    sig = Evidence(**ADDED).signature_hash()

    res = accept.accept([sig, "nope"], snapshot_ts=TS)
    b = baseline_mod.load(paths.STATE_DIR)
    assert b["launchd@1::/x.plist"]["attrs"] == {"a": 1}  # volatile stripped
    assert "launchd@1::/gone.plist" in b                    # not asked for
    assert "launchd@0::/stale" not in b                     # stale version pruned
    assert res["accepted"] == [sig] and res["unmatched"] == ["nope"] and res["pruned"] == 1

    assert accept.accept(None, snapshot_ts=TS, all_=True, collector="processes")["accepted"] == []
    res = accept.accept(None, snapshot_ts=TS, all_=True)
    b = baseline_mod.load(paths.STATE_DIR)
    assert "launchd@1::/gone.plist" not in b                # removed → key dropped
    assert "launchd@1::/suppressed" not in b                # suppressed never accepted
    assert len(res["accepted"]) == 2
