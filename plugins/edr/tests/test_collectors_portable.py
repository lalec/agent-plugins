"""Browser discovery on fixture roots, download window + quarantine parsing, macOS gating."""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import time
from pathlib import Path

import pytest

import macos
from collectors._base import CollectorContext, write_json
from collectors.browser import BrowserCollector
from collectors.downloads import DownloadsCollector


def ctx(tmp_path, last_run_ts=None):
    c = CollectorContext.build(tmp_path, tmp_path / "snap")
    if last_run_ts is not None:
        write_json(c.last_run_path, {"ts": last_run_ts})
    return c


# --- browser ------------------------------------------------------------------

def chrome_fixture(root: Path, unpacked=False):
    prof = root / "Application Support" / "Google" / "Chrome"
    (prof / "Profile 1").mkdir(parents=True)
    (prof / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Profile 1": {}}}}))
    settings = {
        "aaaa": {"location": 4 if unpacked else 1, "from_webstore": not unpacked, "state": 1,
                 "manifest": {"name": "Ext A", "version": "1.0", "permissions": ["tabs"],
                              "host_permissions": ["<all_urls>"]}},
        "cccc": {"location": 5, "manifest": {"name": "component", "version": "1"}},
    }
    (prof / "Profile 1" / "Secure Preferences").write_text(json.dumps({"extensions": {"settings": settings}}))


def firefox_fixture(root: Path):
    ff = root / "Application Support" / "Firefox"
    (ff / "Profiles" / "abc.default-release").mkdir(parents=True)
    (ff / "profiles.ini").write_text("[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/abc.default-release\n")
    addons = [{"id": "ublock@raymondhill.net", "type": "extension", "location": "app-profile", "version": "1.5",
               "defaultLocale": {"name": "uBlock Origin"}, "signedState": 2, "active": True,
               "sourceURI": "https://addons.mozilla.org/firefox/downloads/file/1/x.xpi",
               "userPermissions": {"permissions": ["webRequest"], "origins": ["<all_urls>"]}},
              {"id": "builtin@mozilla", "type": "extension", "location": "app-builtin"},
              {"id": "theme@x", "type": "theme", "location": "app-profile"}]
    (ff / "Profiles" / "abc.default-release" / "extensions.json").write_text(json.dumps({"addons": addons}))


def run_browser(monkeypatch, root: Path):
    monkeypatch.setenv("EDR_BROWSER_ROOT", str(root))
    return BrowserCollector().collect(ctx(root))


def test_browser_chrome_only(monkeypatch, tmp_path):
    chrome_fixture(tmp_path)
    evs = run_browser(monkeypatch, tmp_path)
    exts = [e for e in evs if e.kind == "extension"]
    assert [e.key for e in exts] == ["ext|chrome|Profile 1|aaaa"]  # component skipped
    assert exts[0].attrs["source"] == "store" and exts[0].attrs["host_permissions"] == ["<all_urls>"]


def test_browser_unpacked_and_policy(monkeypatch, tmp_path):
    chrome_fixture(tmp_path, unpacked=True)
    (tmp_path / "Preferences").mkdir()
    with open(tmp_path / "Preferences" / "com.google.Chrome.plist", "wb") as f:
        plistlib.dump({"ExtensionInstallForcelist": ["zzzz;https://evil/update.xml"], "Unrelated": 1}, f)
    evs = run_browser(monkeypatch, tmp_path)
    ext = next(e for e in evs if e.kind == "extension")
    pol = next(e for e in evs if e.kind == "browser_policy")
    assert ext.attrs["source"] == "unpacked"
    assert pol.key == "policy|chrome|user" and pol.attrs["keys"] == ["ExtensionInstallForcelist"]


def test_browser_firefox_only(monkeypatch, tmp_path):
    firefox_fixture(tmp_path)
    evs = run_browser(monkeypatch, tmp_path)
    assert [e.key for e in evs] == ["ext|firefox|abc.default-release|ublock@raymondhill.net"]
    assert evs[0].attrs["source"] == "store" and evs[0].attrs["permissions"] == ["webRequest"]


def test_browser_none(monkeypatch, tmp_path):
    assert run_browser(monkeypatch, tmp_path) == []


# --- downloads ---------------------------------------------------------------

def test_downloads_window_and_quarantine(monkeypatch, tmp_path):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    quarantined = dl / "installer.dmg"
    quarantined.write_bytes(b"x" * 10)
    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;64fdeacb;TestBrowser;", str(quarantined)], check=True)
    local = dl / "notes.sh"
    local.write_text("echo hi")  # no quarantine flag → created locally, ignored
    doc = dl / "paper.pdf"
    doc.write_bytes(b"pdf")
    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;64fdeacb;TestBrowser;", str(doc)], check=True)
    monkeypatch.setattr("collectors.downloads.DIRS", [str(dl)])

    evs = DownloadsCollector().collect(ctx(tmp_path, last_run_ts=time.time() - 60))
    risky = [e for e in evs if e.kind == "risky_download"]
    assert len(risky) == 1 and risky[0].attrs["agent"] == "TestBrowser" and risky[0].attrs["ext"] == ".dmg"
    assert risky[0].attrs["sha256"] and risky[0].attrs["downloaded_at"].startswith("20")
    summary = next(e for e in evs if e.kind == "download_summary")
    assert summary.attrs["count"] == 1 and summary.attrs["by_ext"] == {".pdf": 1}

    # everything is older than the last run → nothing
    assert DownloadsCollector().collect(ctx(tmp_path, last_run_ts=time.time() + 60)) == []


# --- macOS gating --------------------------------------------------------------

@pytest.mark.parametrize("ver,login_items_ok,eslogger_reason,supported", [
    ("11.7.10", True, "needs macOS 13.0+", False),
    ("12.7.6", True, "needs macOS 13.0+", True),
    ("13.7.8", True, "needs root", True),
    ("14.6.1", False, "needs root", True),
    ("15.1", False, "needs root", True),
    ("26.0", False, "needs root", True),
])
def test_macos_gating(monkeypatch, ver, login_items_ok, eslogger_reason, supported):
    monkeypatch.setattr("platform.mac_ver", lambda: (ver, ("", "", ""), ""))
    monkeypatch.setattr(macos.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setitem(macos.SOURCES["login_items_file"], "path", Path("/etc/hosts"))  # exists on every Mac
    monkeypatch.setattr(macos.os, "geteuid", lambda: 501)
    assert macos.check("login_items_file")[0] is login_items_ok
    assert macos.check("eslogger")[1] == eslogger_reason
    assert macos.doctor()["supported"] is supported


def test_macos_missing_tool(monkeypatch):
    monkeypatch.setattr(macos.shutil, "which", lambda name: None)
    assert macos.check("lsof") == (False, "lsof not found")
