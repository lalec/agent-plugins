"""Host security posture — daily tier.

Accounts (users ≥ 500, admin group), remote-access services, Gatekeeper and
SIP, configuration profiles, system extensions, and login items where the OS
still exposes them without root (≤ 13). Every source is gated through
`macos.check`; an unavailable one becomes one `unavailable` evidence so the
gap is visible, never an exception.
"""
from __future__ import annotations

import plistlib
import re
from pathlib import Path
from typing import Any

import macos
from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd, sha256_file

SERVICES = {"sshd": "com.openssh.sshd", "screen_sharing": "com.apple.screensharing",
            "remote_management": "com.apple.RemoteDesktop.agent", "smb": "com.apple.smbd"}
BUNDLE_ID = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9_-]+){2,}$")


class HostSecurityCollector(Collector):
    name = "host_security"
    tier = "D"
    maturity = "beta"
    version = 1
    mitre = ["T1136.001", "T1098", "T1021.004", "T1562.001", "T1547.015"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        out: list[Evidence] = []
        out.extend(self._gated("dscl", self._accounts))
        out.extend(self._gated("launchctl", self._remote_access))
        out.extend(self._gated("spctl", self._gatekeeper))
        out.extend(self._gated("csrutil", self._sip))
        out.extend(self._gated("profiles", self._profiles))
        out.extend(self._gated("systemextensionsctl", self._system_extensions))
        out.extend(self._gated("login_items_file", self._login_items))
        return out

    def _gated(self, source: str, fn) -> list[Evidence]:
        ok, reason = macos.check(source)
        if not ok:
            return [Evidence(collector=self.name, kind="unavailable", key=f"unavailable|{source}",
                             attrs={"source": source, "reason": reason})]
        try:
            return fn()
        except Exception as e:  # one broken source must not hide the others
            return [Evidence(collector=self.name, kind="error", key=f"error|{source}",
                             attrs={"source": source, "error": f"{type(e).__name__}: {e}"})]

    # --- accounts ------------------------------------------------------------

    def _accounts(self) -> list[Evidence]:
        out: list[Evidence] = []
        rc, listing, _ = run_cmd(["dscl", ".", "-list", "/Users", "UniqueID"], timeout=10)
        if rc == 0:
            for line in listing.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) >= 500:
                    name, uid = parts[0], int(parts[1])
                    rc2, detail, _ = run_cmd(["dscl", ".", "-read", f"/Users/{name}", "UserShell",
                                              "NFSHomeDirectory", "RealName"], timeout=5)
                    kv = dict(re.findall(r"^(\w+):\s*(.+)$", detail, re.M)) if rc2 == 0 else {}
                    out.append(Evidence(collector=self.name, kind="user", key=f"user|{name}",
                                        attrs={"name": name, "uid": uid, "shell": kv.get("UserShell"),
                                               "home": kv.get("NFSHomeDirectory")}))
        rc, admins, _ = run_cmd(["dscl", ".", "-read", "/Groups/admin", "GroupMembership"], timeout=5)
        if rc == 0:
            members = sorted(admins.split(":", 1)[1].split()) if ":" in admins else []
            out.append(Evidence(collector=self.name, kind="group", key="group|admin",
                                attrs={"group": "admin", "members": members}))
        return out

    # --- services and posture --------------------------------------------------

    def _remote_access(self) -> list[Evidence]:
        rc, out, _ = run_cmd(["launchctl", "print-disabled", "system"], timeout=10)
        if rc != 0:
            raise RuntimeError("launchctl print-disabled failed")
        state = dict(re.findall(r'"([^"]+)"\s*=>\s*(enabled|disabled|true|false)', out))
        attrs = {}
        for short, label in SERVICES.items():
            raw = state.get(label)
            attrs[short] = ("default" if raw is None
                            else "disabled" if raw in ("disabled", "true") else "enabled")
        return [Evidence(collector=self.name, kind="remote_access", key="remote_access|services", attrs=attrs)]

    def _gatekeeper(self) -> list[Evidence]:
        _, out, err = run_cmd(["spctl", "--status"], timeout=5)
        text = (out + err).lower()
        return [Evidence(collector=self.name, kind="security", key="security|gatekeeper",
                         attrs={"enabled": "assessments enabled" in text, "raw": text.strip()[:80]})]

    def _sip(self) -> list[Evidence]:
        _, out, err = run_cmd(["csrutil", "status"], timeout=5)
        text = (out + err).lower()
        return [Evidence(collector=self.name, kind="security", key="security|sip",
                         attrs={"enabled": "enabled" in text and "disabled" not in text.split("enabled")[0],
                                "raw": text.strip()[:80]})]

    def _profiles(self) -> list[Evidence]:
        _, out, err = run_cmd(["profiles", "list"], timeout=10)
        ids = sorted(set(re.findall(r"profileIdentifier:\s*(\S+)", out + err)))
        return [Evidence(collector=self.name, kind="security", key="security|profiles",
                         attrs={"identifiers": ids, "count": len(ids)})]

    def _system_extensions(self) -> list[Evidence]:
        _, out, err = run_cmd(["systemextensionsctl", "list"], timeout=10)
        exts = sorted(set(re.findall(r"\b([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9_-]+){2,})\s*\(", out)))
        return [Evidence(collector=self.name, kind="security", key="security|system_extensions",
                         attrs={"extensions": exts, "count": len(exts)})]

    def _login_items(self) -> list[Evidence]:
        """The file's hash is the signal; the item list is best-effort context.

        Items sit inside nested bookmark blobs of an NSKeyedArchiver plist, so
        app paths and bundle ids are pulled from the raw bytes.
        """
        path = Path(macos.SOURCES["login_items_file"]["path"])
        raw = path.read_bytes()
        items: set[str] = set()
        for m in re.finditer(rb"(/[A-Za-z0-9._ /-]+?\.app)\b", raw):
            items.add(m.group(1).decode("ascii", "ignore"))
        for m in re.finditer(rb"\b([a-z]{2,}\.[a-z0-9-]+(?:\.[A-Za-z0-9_-]+)+)\b", raw):
            cand = m.group(1).decode("ascii", "ignore")
            if BUNDLE_ID.match(cand) and not cand.startswith(("com.apple.", "NS", "com.apple")):
                items.add(cand)
        return [Evidence(collector=self.name, kind="security", key="security|login_items",
                         attrs={"items": sorted(items)[:100], "count": len(items),
                                "sha256": sha256_file(path), "source": str(path)})]
