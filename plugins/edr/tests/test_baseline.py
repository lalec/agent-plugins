"""diff_against: report_removed=False silences the reverse pass for that collector only."""
from __future__ import annotations

import baseline as baseline_mod
from collectors._base import Evidence


def test_report_removed_switch():
    snapshot = {"processes": [Evidence("processes", "process", "/a", {"x": 1})],
                "launchd": [Evidence("launchd", "launchd_item", "/keep.plist", {})]}
    baseline = {
        "processes@2::/a": {"kind": "process", "attrs": {"x": 1}},
        "processes@2::/gone": {"kind": "process", "attrs": {}},
        "launchd@1::/keep.plist": {"kind": "launchd_item", "attrs": {}},
        "launchd@1::/gone.plist": {"kind": "launchd_item", "attrs": {}},
    }
    versions = {"processes": 2, "launchd": 1}
    anomalies = baseline_mod.diff_against(snapshot, baseline, versions, {},
                                          {"processes": False, "launchd": True})
    assert [(a.change, a.evidence.key) for a in anomalies] == [("removed", "/gone.plist")]
    anomalies = baseline_mod.diff_against(snapshot, baseline, versions, {})
    assert sorted(a.evidence.key for a in anomalies) == ["/gone", "/gone.plist"]
