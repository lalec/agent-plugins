"""Reply grammar, ledger, headless queueing, Discord author check, unreviewed surfacing."""
from __future__ import annotations

import os

import pytest

import alerts
import ledger
import notify
import paths
import pending
from collectors._base import read_json, write_json

TS = "20260903T220004Z"


def make_batch(action=None, ts=TS, **fields):
    batch = {"ts": ts, "host": "t", "headless": True, "posted": None, "reviewed": None,
             "findings": [{"n": 1, "sig": "abc", "severity": "medium", "headline": "h",
                           "recommend": "r", "action": action, "narrative": "because"}]}
    batch.update(fields)
    alerts.save(batch)
    return batch


def ledger_files():
    return sorted(paths.PENDING_ACTIONS_DIR.glob("*.json"))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for p in list(paths.ALERTS_DIR.glob("*.json")) + ledger_files():
        p.unlink()
    paths.NOTIFY_STATE.unlink(missing_ok=True)
    paths.SCHEDULE_STATE.unlink(missing_ok=True)
    monkeypatch.delenv("EDR_HEADLESS", raising=False)
    monkeypatch.setattr(notify, "post", lambda text: None)  # never touch the network
    monkeypatch.setattr(notify, "fetch", lambda after: [])


@pytest.mark.parametrize("text,valid,expected", [
    ("1 2", {1, 2}, [("fix", 1)]),
    ("1 0 2 2", {1, 2}, [("ok", 1), ("fix", 2)]),
    ("1 2 1 2", {1}, [("fix", 1)]),
    ("2", {1}, [("fix", 1)]),            # bare choice, single finding
    ("0", {1}, [("ok", 1)]),
    ("3", {1}, [("skip", 1)]),
    ("2", {1, 2}, None),                 # bare choice is ambiguous with two findings
    ("1 5", {1}, None),                  # unknown choice
    ("3 2", {1, 2}, None),               # unknown finding
    ("1", {1, 2}, None),                 # odd length
    ("ok 1", {1}, None),                 # words are not accepted
    ("rm -rf /", {1}, None),
    ("", {1}, None),
    ("1; 2", {1}, None),
])
def test_parse(text, valid, expected):
    assert pending.parse(text, valid) == expected


def test_needs_root(tmp_path):
    f = tmp_path / "x"
    f.write_text("x")
    assert ledger.needs_root("quarantine_file", {"path": str(f)}) is False
    assert ledger.needs_root("remove_path", {"path": "/usr/bin/nonexistent-edr"}) is True
    assert ledger.needs_root("kill_pid", {"pid": os.getpid()}) is False
    assert ledger.needs_root("kill_pid", {"pid": 1}) is True
    assert ledger.needs_root("pfctl_block_host", {"ip": "1.2.3.4"}) is True
    assert ledger.needs_root("ssh_revoke_key", {}) is False


def test_chat_reply_executes_user_scope_action(tmp_path):
    target = tmp_path / "evil.sh"
    target.write_text("x")
    b = make_batch(action={"primitive": "quarantine_file", "args": {"path": str(target)}})
    out = pending.drain(reply="1 2", batch_ts=b["ts"])
    assert not target.exists()
    assert out["executed"][0]["status"] == "done"
    entry = read_json(paths.PENDING_ACTIONS_DIR / f"{TS}-1.json")
    assert entry["source"] == "chat" and entry["status"] == "done" and entry["needs_root"] is False
    assert alerts.load(TS)["answers"] == {"1": "fix"}
    assert alerts.load(TS)["reviewed"]


def test_why_then_skip():
    make_batch()
    out = pending.drain(reply="1 1", batch_ts=TS)
    assert "because" in out["acks"][0] and not ledger_files()
    assert not alerts.load(TS)["reviewed"]
    out = pending.drain(reply="3", batch_ts=TS)
    assert "skipped" in out["acks"][0] and alerts.load(TS)["reviewed"] and not ledger_files()


def test_garbage_is_hint_only():
    make_batch(action={"primitive": "remove_path", "args": {"path": "/tmp/whatever"}})
    out = pending.drain(reply="rm -rf /", batch_ts=TS)
    assert out["acks"] == [pending.HINT] and not ledger_files() and not out["executed"]


def test_fix_without_declared_action_reports_recommendation():
    make_batch(action=None)
    out = pending.drain(reply="1 2", batch_ts=TS)
    assert "no automatic fix" in out["acks"][0] and "r" in out["acks"][0] and not ledger_files()
    assert alerts.load(TS)["reviewed"]  # answered


def test_headless_queues_root_action_then_interactive_runs_it(monkeypatch):
    monkeypatch.setenv("EDR_HEADLESS", "1")
    make_batch(action={"primitive": "remove_path", "args": {"path": "/usr/bin/nonexistent-edr"}})
    out = pending.drain(reply="1 2", batch_ts=TS)
    assert out["queued"] and not out["executed"]
    assert read_json(paths.PENDING_ACTIONS_DIR / f"{TS}-1.json")["status"] == "queued"
    assert "needs admin" in out["acks"][0]
    monkeypatch.delenv("EDR_HEADLESS")
    out = pending.drain()  # path is gone → primitive fails before any dialog
    assert out["executed"][0]["status"] == "failed" and not ledger.queued()


def test_discord_reply_author_check(monkeypatch, tmp_path):
    target = tmp_path / "evil.sh"
    target.write_text("x")
    make_batch(action={"primitive": "quarantine_file", "args": {"path": str(target)}})
    notify.save_state(last_seen="100", posts={"200": TS})
    msgs = [{"id": "300", "author_id": "intruder", "content": "1"},
            {"id": "301", "author_id": "u1", "content": "1 1"}]
    posted: list[str] = []
    monkeypatch.setattr(notify, "user_id", lambda: "u1")
    monkeypatch.setattr(notify, "fetch", lambda after: [m for m in msgs if int(m["id"]) > int(after or 0)])
    monkeypatch.setattr(notify, "post", lambda t: posted.append(t) or "999")
    pending.drain()
    assert target.exists() and not ledger_files()  # intruder's approval ignored
    assert any("because" in p for p in posted)
    assert notify.state()["last_seen"] == "301"


def test_first_drain_never_replays_history(monkeypatch, tmp_path):
    target = tmp_path / "evil.sh"
    target.write_text("x")
    make_batch(action={"primitive": "quarantine_file", "args": {"path": str(target)}})
    monkeypatch.setattr(notify, "user_id", lambda: "u1")
    monkeypatch.setattr(notify, "fetch", lambda after: [{"id": "5", "author_id": "u1", "content": "1 2"}])
    pending.drain()
    assert target.exists() and not ledger_files()
    assert notify.state()["last_seen"] == "5"


def test_discord_reply_to_closed_batch_is_hint(monkeypatch):
    make_batch(action={"primitive": "remove_path", "args": {"path": "/tmp/x"}}, reviewed="done")
    notify.save_state(last_seen="100", posts={"200": TS})
    posted: list[str] = []
    monkeypatch.setattr(notify, "user_id", lambda: "u1")
    monkeypatch.setattr(notify, "fetch", lambda after: [{"id": "300", "author_id": "u1", "content": "1 2"}])
    monkeypatch.setattr(notify, "post", lambda t: posted.append(t) or "999")
    pending.drain()
    assert posted and "closed" in posted[0] and not ledger_files()


def test_unreviewed_reported_once_and_never_headless(monkeypatch):
    make_batch()
    monkeypatch.setenv("EDR_HEADLESS", "1")
    assert pending.drain()["unreviewed"] == []
    monkeypatch.delenv("EDR_HEADLESS")
    out = pending.drain()
    assert [b["ts"] for b in out["unreviewed"]] == [TS]
    assert pending.drain()["unreviewed"] == []


def test_unseen_runs_reported_once():
    write_json(paths.SCHEDULE_STATE, {"runs": [{"ts": TS, "ended": "incomplete", "reason": "budget",
                                                "findings": 0, "posted": False, "seen": False}]})
    out = pending.drain()
    assert out["unseen_runs"][0]["reason"] == "budget"
    assert pending.drain()["unseen_runs"] == []


def test_render():
    b = make_batch()
    text = alerts.render(b)
    assert text.splitlines()[0].endswith("1 to decide")
    assert "1 · h → r" in text and text.splitlines()[-1] == "Reply: 1 · 0 ok · 1 why · 2 fix · 3 skip"
    assert alerts.render({"ts": TS, "findings": []}) is None
    assert alerts.since(alerts.parse_ts(TS) + 0.7)["ts"] == TS  # same-second start still counts
    assert alerts.since(alerts.parse_ts(TS) + 1.0) is None
