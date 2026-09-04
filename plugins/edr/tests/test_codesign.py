"""Codesign verdicts: only the leaf authority may say 'Apple'; auto-accept covers platform churn only."""
from __future__ import annotations

import triage
from collectors._base import Anomaly, Evidence
from collectors._util import parse_codesign

APPLE = "Authority=Software Signing\nAuthority=Apple Code Signing Certification Authority\nAuthority=Apple Root CA\nTeamIdentifier=not set\n"
DEVID = "Authority=Developer ID Application: Mozilla Corporation (43AQ936H96)\nAuthority=Developer ID Certification Authority\nAuthority=Apple Root CA\nTeamIdentifier=43AQ936H96\n"
STORE = "Authority=Apple Mac OS Application Signing\nAuthority=Apple Worldwide Developer Relations Certification Authority\nAuthority=Apple Root CA\nTeamIdentifier=ABCDE12345\n"
ADHOC = "Signature=adhoc\nTeamIdentifier=not set\n"


def test_parse_codesign_leaf_decides():
    assert parse_codesign(0, APPLE)["status"] == "signed-apple" and parse_codesign(0, APPLE)["team_id"] is None
    assert parse_codesign(0, DEVID)["status"] == "signed-developer" and parse_codesign(0, DEVID)["team_id"] == "43AQ936H96"
    assert parse_codesign(0, STORE)["status"] == "signed-store"
    assert parse_codesign(0, ADHOC)["status"] == "adhoc"
    assert parse_codesign(1, "code object is not signed at all")["status"] == "unsigned"


def _anomaly(exe, status, change="added"):
    return Anomaly(change=change, evidence=Evidence("processes", "process", exe,
                                                     {"exe": exe, "codesign_status": status}))


def test_auto_accept_only_apple_platform_in_apple_dirs():
    rules = triage.load_rules()
    cases = [
        _anomaly("/usr/libexec/configd", "signed-apple"),
        _anomaly("/System/Library/CoreServices/powerd.bundle/powerd", "signed-apple", "modified"),
        _anomaly("/Applications/Firefox.app/Contents/MacOS/firefox", "signed-developer"),
        _anomaly("/Users/me/Downloads/evil", "signed-apple"),          # right label, wrong place
        _anomaly("/usr/local/bin/tool", "signed-developer"),           # right place, wrong label
        _anomaly("/usr/libexec/gone", "signed-apple", "removed"),
    ]
    taken = triage.auto_accept(cases, rules)
    assert [a.evidence.key for a in taken] == ["/usr/libexec/configd", "/System/Library/CoreServices/powerd.bundle/powerd"]
    assert all(a.suppressed and a.evidence.attrs["auto_accepted"] == "auto_accept_apple_platform_binary" for a in taken)
    assert not cases[2].suppressed and not cases[3].suppressed


def test_fold_writes_baseline_without_marker():
    import baseline as baseline_mod
    a = _anomaly("/usr/libexec/configd", "signed-apple")
    a.evidence.attrs.update({"auto_accepted": "x", "sample_pid": 5})
    b: dict = {}
    assert baseline_mod.fold(b, [a], {"processes": 4}, {"processes": ["sample_pid"]}) == 1
    assert b["processes@4::/usr/libexec/configd"]["attrs"] == {"exe": "/usr/libexec/configd", "codesign_status": "signed-apple"}
