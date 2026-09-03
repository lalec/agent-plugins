"""Browser collector — extensions and policies for every browser present.

Browsers and profiles are discovered, never assumed: Chromium family
(Chrome, Chromium, Brave, Edge, Arc, Vivaldi, Opera) from each vendor's
`Local State`, Firefox from `profiles.ini`, Safari through `pluginkit`. An
absent browser yields nothing. `EDR_BROWSER_ROOT` replaces `~/Library` for
fixtures.

Emits `extension` (id, source, permissions — version is volatile, store
updates are not anomalies) and `browser_policy` (only the keys that force
extensions, proxies, homepages or search engines). Never reads history.
"""
from __future__ import annotations

import configparser
import json
import os
import plistlib
import re
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd

CHROMIUM = {"chrome": "Google/Chrome", "chromium": "Chromium", "brave": "BraveSoftware/Brave-Browser",
            "edge": "Microsoft Edge", "arc": "Arc/User Data", "vivaldi": "Vivaldi",
            "opera": "com.operasoftware.Opera"}
CHROMIUM_POLICY_PLISTS = {"chrome": "com.google.Chrome", "chromium": "org.chromium.Chromium",
                          "brave": "com.brave.Browser", "edge": "com.microsoft.Edge"}
# Chromium `location` enum: 4 unpacked, 8 command line, 7/9 policy, 2/3/6 external, 5/10 component
LOCATION = {4: "unpacked", 8: "unpacked", 7: "policy", 9: "policy", 2: "external", 3: "external", 6: "external"}
COMPONENT = {5, 10}
WATCH_KEYS = {"ExtensionInstallForcelist", "ExtensionInstallSources", "ProxySettings", "ProxyMode",
              "ProxyServer", "ProxyPacUrl", "HomepageLocation", "DefaultSearchProviderSearchURL",
              "DefaultSearchProviderEnabled", "RestoreOnStartupURLs", "NewTabPageLocation",
              "DeveloperToolsAvailability", "PasswordManagerEnabled",
              # Firefox policies.json
              "Extensions", "ExtensionSettings", "Proxy", "Homepage", "SearchEngines", "Certificates"}
FIREFOX_POLICY_JSON = Path("/Applications/Firefox.app/Contents/Resources/distribution/policies.json")


class BrowserCollector(Collector):
    name = "browser"
    tier = "T"
    maturity = "beta"
    version = 1
    mitre = ["T1176", "T1185", "T1557", "T1112"]
    volatile_attrs = ["version"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        self.root = Path(os.environ.get("EDR_BROWSER_ROOT") or Path.home() / "Library")
        self.managed = (self.root / "Managed Preferences" if os.environ.get("EDR_BROWSER_ROOT")
                        else Path("/Library/Managed Preferences"))
        out: list[Evidence] = []
        for browser, sub in CHROMIUM.items():
            out.extend(self._chromium(browser, self.root / "Application Support" / sub))
        out.extend(self._firefox(self.root / "Application Support" / "Firefox"))
        out.extend(self._safari())
        out.extend(self._policies())
        return out

    # --- Chromium family ------------------------------------------------------

    def _chromium(self, browser: str, root: Path) -> list[Evidence]:
        if not root.is_dir():
            return []
        out: list[Evidence] = []
        for profile in self._chromium_profiles(root):
            settings = {}
            for fname in ("Secure Preferences", "Preferences"):
                data = _json(root / profile / fname)
                settings = ((data.get("extensions") or {}).get("settings") or {}) if data else {}
                if settings:
                    break
            for ext_id, s in settings.items():
                manifest = s.get("manifest") or {}
                if not manifest or s.get("location") in COMPONENT:
                    continue
                source = LOCATION.get(s.get("location"), "sideload")
                if source in ("sideload", "external") and s.get("from_webstore"):
                    source = "store"  # an installed app registered a store CRX (Adobe, Docs Offline)
                out.append(self._ext(browser, profile, ext_id, manifest.get("name"), manifest.get("version"),
                                     source, manifest.get("permissions") or [],
                                     manifest.get("host_permissions") or [], s.get("state", 1) == 1,
                                     installed_by_default=bool(s.get("was_installed_by_default"))))
        return out

    @staticmethod
    def _chromium_profiles(root: Path) -> list[str]:
        state = _json(root / "Local State")
        cache = ((state or {}).get("profile") or {}).get("info_cache") or {}
        if cache:
            return sorted(cache)
        if (root / "Default").is_dir():
            return ["Default"]
        return ["."] if (root / "Preferences").exists() else []  # Opera: root is the profile

    # --- Firefox -----------------------------------------------------------

    def _firefox(self, root: Path) -> list[Evidence]:
        ini = root / "profiles.ini"
        if not ini.exists():
            return []
        cp = configparser.ConfigParser()
        try:
            cp.read(ini)
        except configparser.Error:
            return []
        out: list[Evidence] = []
        for section in cp.sections():
            path = cp.get(section, "Path", fallback=None)
            if not path:
                continue
            profile = root / path if cp.get(section, "IsRelative", fallback="1") == "1" else Path(path)
            data = _json(profile / "extensions.json") or {}
            for addon in data.get("addons") or []:
                if addon.get("type") != "extension" or addon.get("location") != "app-profile":
                    continue
                perms = addon.get("userPermissions") or {}
                src_host = re.sub(r"^https?://([^/]+).*$", r"\1", str(addon.get("sourceURI") or ""))
                source = "store" if (src_host.endswith("addons.mozilla.org") or addon.get("signedState", 0) >= 2) else "sideload"
                out.append(self._ext("firefox", profile.name, addon.get("id"),
                                     (addon.get("defaultLocale") or {}).get("name"), addon.get("version"),
                                     source, perms.get("permissions") or [], perms.get("origins") or [],
                                     bool(addon.get("active", True))))
        return out

    # --- Safari ------------------------------------------------------------

    def _safari(self) -> list[Evidence]:
        if os.environ.get("EDR_BROWSER_ROOT"):
            return []  # fixtures cannot stand in for pluginkit
        rc, out, _ = run_cmd(["pluginkit", "-mAvvv", "-p", "com.apple.Safari.extension",
                              "-p", "com.apple.Safari.web-extension", "-p", "com.apple.Safari.content-blocker"],
                             timeout=10)
        if rc != 0:
            return []
        evidences: list[Evidence] = []
        for block in re.split(r"\n(?=[+\-!?]\s)", "\n" + out.strip()):
            head = block.strip().splitlines()[0] if block.strip() else ""
            m = re.match(r"^([+\-!?])\s+(\S+)\((.*?)\)", head)
            if not m:
                continue
            kv = dict(re.findall(r"^\s+([A-Za-z ]+?)\s*=\s*(.+?)\s*$", block, re.M))
            evidences.append(self._ext("safari", "default", m.group(2), kv.get("Display Name"), m.group(3),
                                       "app", [], [], m.group(1) == "+",
                                       path=kv.get("Path"), parent_bundle=kv.get("Parent Bundle")))
        return evidences

    # --- policies ----------------------------------------------------------

    def _policies(self) -> list[Evidence]:
        out: list[Evidence] = []
        user = os.environ.get("USER", "")
        for browser, domain in CHROMIUM_POLICY_PLISTS.items():
            for scope, path in (("managed", self.managed / f"{domain}.plist"),
                                ("managed-user", self.managed / user / f"{domain}.plist"),
                                ("user", self.root / "Preferences" / f"{domain}.plist")):
                out.extend(self._policy(browser, scope, _plist(path)))
        out.extend(self._policy("firefox", "distribution", _json(FIREFOX_POLICY_JSON).get("policies")
                                if _json(FIREFOX_POLICY_JSON) else None))
        out.extend(self._policy("firefox", "user", _plist(self.root / "Preferences" / "org.mozilla.firefox.plist")))
        return out

    def _policy(self, browser: str, scope: str, data: dict[str, Any] | None) -> list[Evidence]:
        if not data:
            return []
        watched = {k: str(v)[:300] for k, v in data.items() if k in WATCH_KEYS}
        if not watched:
            return []
        return [Evidence(collector=self.name, kind="browser_policy", key=f"policy|{browser}|{scope}",
                         attrs={"browser": browser, "scope": scope, "keys": sorted(watched), **watched})]

    def _ext(self, browser: str, profile: str, ext_id: str | None, name: str | None, version: str | None,
             source: str, permissions: list, host_permissions: list, enabled: bool, **extra: Any) -> Evidence:
        return Evidence(collector=self.name, kind="extension", key=f"ext|{browser}|{profile}|{ext_id}",
                        attrs={"browser": browser, "profile": profile, "id": ext_id, "name": name,
                               "version": version, "source": source, "enabled": enabled,
                               "permissions": sorted(str(p) for p in permissions),
                               "host_permissions": sorted(str(p) for p in host_permissions), **extra})


def _json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _plist(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
