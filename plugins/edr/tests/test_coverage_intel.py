"""Threat-list health, key redaction, abuse.ch CSV parsing, coverage lines, uv tool identity."""
from __future__ import annotations

import time
import urllib.error

import pytest

import coverage
import notify
import paths
from collectors._base import write_json
from collectors.processes import ProcessesCollector
from intel.feeds import _http

KEY = "s3cr3t-key"


def test_csv_rows_commented_header_and_comments():
    text = '# ThreatFox export\n# "first_seen_utc", "ioc_value", "ioc_type"\n# more\n' \
           '"2026-10-01", "1.2.3.4:443", "ip:port"\n'
    assert list(_http.csv_rows(text, "ioc_value")) == [
        {"first_seen_utc": "2026-10-01", "ioc_value": "1.2.3.4:443", "ioc_type": "ip:port"}]


def test_csv_rows_plain_header_and_format_change():
    assert list(_http.csv_rows("id,url,url_status\n1,http://x/a,online\n", "url_status"))[0]["url"] == "http://x/a"
    with pytest.raises(_http.FeedError):
        list(_http.csv_rows("<html>gone</html>", "url_status"))


def test_key_never_in_errors(monkeypatch):
    def gone(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, None)

    monkeypatch.setattr(_http.urllib.request, "urlopen", gone)
    with pytest.raises(_http.FeedError) as e:
        _http.get_bytes(f"https://x/{KEY}/full.csv.zip", secret=KEY)
    assert KEY not in str(e.value)

    def down(req, timeout):
        raise urllib.error.URLError(f"failed for https://x/{KEY}/")

    monkeypatch.setattr(_http.urllib.request, "urlopen", down)
    monkeypatch.setattr(_http.time, "sleep", lambda s: None)
    with pytest.raises(_http.FeedError) as e:
        _http.get_bytes(f"https://x/{KEY}/", secret=KEY)
    assert KEY not in str(e.value) and "<key>" in str(e.value)


def test_missing_key_is_a_named_error(monkeypatch, tmp_path):
    monkeypatch.setattr(_http, "ABUSECH_KEY_FILE", tmp_path / "none")
    with pytest.raises(_http.FeedError, match="auth.abuse.ch"):
        _http.abusech_key()


def test_coverage_flags_stale_lists_and_warns_once(monkeypatch):
    now = time.time()
    write_json(paths.INTEL_HEALTH, {
        "threatfox": {"ok": False, "rows": 40000, "last_ok": now - 6 * 86400, "error": "HTTP 410 Gone"},
        "feodo": {"ok": True, "rows": 1, "last_ok": now},
        "mitre_macos": {"ok": True, "rows": 22, "last_ok": now}})
    paths.NOTIFY_STATE.unlink(missing_ok=True)
    line = coverage.lines()[-1]
    assert line.startswith("⚠️ Threat lists: 40,001 entries") and "threatfox not updated for 6d" in line
    assert coverage.intel_warning() == "⚠️ edr · threat lists stale: threatfox · HTTP 410 Gone"
    assert coverage.intel_warning() is None  # same state: no nag
    write_json(paths.INTEL_HEALTH, {"threatfox": {"ok": True, "rows": 40000, "last_ok": now}})
    assert coverage.intel_warning() == "🟢 edr · threat lists updating again"
    assert "updated 1m ago" in coverage.lines()[-1]
    assert notify.state()["intel_stale"] == []


def test_uv_tool_identity():
    env = "/Users/u/.cache/uv/archive-v0/AbC123/bin/"
    ident = ProcessesCollector._identity
    assert ident(env + "python", f"{env}python {env}mcp-tool --x") == "/Users/u/.cache/uv/archive-v0/*/bin/mcp-tool"
    assert ident(env + "python", f"{env}python -c 'x'") == env + "python"  # no script: never merged
    assert ident("/bin/zsh", "-zsh") == "/bin/zsh"


def test_sync_skips_fresh_feeds(monkeypatch):
    from intel import sync

    class Feed:
        FEED_NAME = "fake"
        calls = 0

        @classmethod
        def fetch(cls):
            cls.calls += 1
            yield {"type": "ip", "value": "203.0.113.9", "severity": "high"}

    monkeypatch.setattr(sync, "discover_feeds", lambda: [Feed])
    paths.INTEL_HEALTH.unlink(missing_ok=True)
    assert sync.main([]) == 0 and Feed.calls == 1
    assert sync.main([]) == 0 and Feed.calls == 1          # fresh: no second download
    assert sync.main(["--force"]) == 0 and Feed.calls == 2
