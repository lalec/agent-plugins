"""MITRE ATT&CK macOS technique catalog — static, pinned to a curated subset.

Phase A: covers the techniques our 6 starter collectors map to. Phase D
replaces this with the upstream MITRE STIX feed for full coverage.

Each yielded IOC is `{type: 'mitre_id', value: 'T1547.011', metadata: '{...}'}`.
"""
from __future__ import annotations

import json
from typing import Iterator

FEED_NAME = "mitre_macos"

# Curated subset relevant to edr Phase A collectors. Source: attack.mitre.org.
TECHNIQUES = [
    ("T1059", "Command and Scripting Interpreter", "Adversaries may abuse command and scripting interpreters to execute commands."),
    ("T1059.004", "Unix Shell", "Adversaries may abuse Unix shell commands and scripts for execution."),
    ("T1098", "Account Manipulation", "Adversaries may manipulate accounts to maintain access."),
    ("T1098.004", "SSH Authorized Keys", "Adversaries may modify the SSH authorized_keys file to maintain persistent access."),
    ("T1106", "Native API", "Adversaries may interact with the native OS API to execute behaviors."),
    ("T1543", "Create or Modify System Process", "Adversaries may create or modify system-level processes for persistence."),
    ("T1543.001", "Launch Agent", "Adversaries may create or modify launchd Launch Agents to execute payloads on user logon."),
    ("T1543.004", "Launch Daemon", "Adversaries may create or modify launchd Launch Daemons to execute payloads as root."),
    ("T1546", "Event Triggered Execution", "Adversaries may establish persistence using event-triggered execution mechanisms."),
    ("T1546.004", "Unix Shell Configuration Modification", "Adversaries may modify shell rc files to execute on shell startup."),
    ("T1547", "Boot or Logon Autostart Execution", "Adversaries may configure system settings to execute programs at boot or logon."),
    ("T1547.011", "Plist Modification", "Adversaries may modify plist files to execute payloads at startup."),
    ("T1053", "Scheduled Task/Job", "Adversaries may abuse scheduled task functionality."),
    ("T1053.003", "Cron", "Adversaries may use cron utility to schedule task execution."),
    ("T1574", "Hijack Execution Flow", "Adversaries may execute their own malicious payloads by hijacking the way the OS or applications run."),
    ("T1571", "Non-Standard Port", "Adversaries may communicate using a protocol on a port not commonly associated with that protocol."),
    ("T1095", "Non-Application Layer Protocol", "Adversaries may use OSI non-application layer protocols for C2."),
    ("T1049", "System Network Connections Discovery", "Adversaries may attempt to get a listing of network connections to or from the system."),
    ("T1610", "Deploy Container", "Adversaries may deploy a container to facilitate execution."),
    ("T1611", "Escape to Host", "Adversaries may break out of a container to gain access to the underlying host."),
    ("T1195", "Supply Chain Compromise", "Adversaries may manipulate products or product delivery mechanisms before final delivery."),
    ("T1195.002", "Compromise Software Supply Chain", "Adversaries may manipulate application software supply chain."),
]


def fetch() -> Iterator[dict]:
    for tid, name, desc in TECHNIQUES:
        yield {
            "type": "mitre_id",
            "value": tid,
            "metadata": json.dumps({
                "name": name,
                "description": desc,
                "url": f"https://attack.mitre.org/techniques/{tid.replace('.', '/')}/",
            }),
        }
