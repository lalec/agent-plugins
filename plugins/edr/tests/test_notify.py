"""Transport: transient errors are retried, permanent ones logged; nothing raises."""
from __future__ import annotations

import io
import json
import urllib.error

import notify


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _configured(monkeypatch):
    monkeypatch.setattr(notify, "_cfg", lambda: {"channel": "discord", "channel_id": "1", "user_id": "2",
                                                "token_file": "/x", "token_key": "K"})
    monkeypatch.setattr(notify, "token", lambda: "tok")
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)


def test_post_retries_transient_then_succeeds(monkeypatch):
    _configured(monkeypatch)
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("certificate verify failed")
        return _Resp(json.dumps({"id": "42"}).encode())

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.post("hi") == "42" and calls["n"] == 3


def test_post_gives_up_and_logs(monkeypatch, tmp_path):
    _configured(monkeypatch)
    monkeypatch.setattr(notify.paths, "LAUNCHD_LOG", tmp_path / "l.log")

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.post("hi") is None
    assert "after 3 attempts" in (tmp_path / "l.log").read_text()


def test_http_error_is_not_retried(monkeypatch, tmp_path):
    _configured(monkeypatch)
    monkeypatch.setattr(notify.paths, "LAUNCHD_LOG", tmp_path / "l.log")
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.post("hi") is None and calls["n"] == 1
