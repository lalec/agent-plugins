"""Reply drain — turns decisions into ledger entries and runs them.

A decision is a Discord reply in the notify channel, or the same text typed
by the analyst on the user's behalf (`--reply "1 ok 2" --batch <ts>`). Either
way it is parsed here, strictly, against the finding numbers of one batch;
reply text never reaches a shell or the model.

Grammar (case-insensitive):  `1` / `1 2` approve · `ok 1` accept as benign ·
`why 1` narrative · `skip` close batch · anything else → hint, nothing runs.

Root actions are queued while headless (a dialog would hang the job) and run
at the next interactive `edr poll`, which raises the admin dialog.

CLI: `edr poll [--wait 20m] [--reply "<text>" --batch <ts>]`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import alerts  # noqa: E402
import ledger  # noqa: E402
import notify  # noqa: E402
import paths  # noqa: E402
from collectors._base import read_json, write_json  # noqa: E402

HINT = "? reply 1 · ok 1 · why 1 · skip"
POLL_EVERY = 30
_INT = re.compile(r"^\d+$")


def parse(text: str, valid: set[int]) -> list[tuple[str, int | None]] | None:
    """[(verb, n)] for a well-formed reply, else None. Verbs: approve, ok, why, skip."""
    toks = text.strip().lower().split()
    if not toks:
        return None
    if toks == ["skip"]:
        return [("skip", None)]
    verb, nums = ("approve", toks) if _INT.match(toks[0]) else (toks[0], toks[1:])
    if verb not in ("approve", "ok", "why") or not nums:
        return None
    if not all(_INT.match(t) and int(t) in valid for t in nums):
        return None
    return [(verb, int(t)) for t in dict.fromkeys(nums)]


def drain(wait: int = 0, reply: str | None = None, batch_ts: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"executed": [], "queued": [], "acks": [], "unreviewed": [], "unseen_runs": []}
    _run_queued(out)
    if reply is not None:
        batch = alerts.load(batch_ts) if batch_ts else alerts.latest()
        if batch is None:
            _ack(out, f"no such batch {batch_ts or ''}".strip(), "chat")
        else:
            _handle(batch, reply, "chat", None, out)
    else:
        deadline = time.time() + max(wait, 0)
        while True:
            _drain_discord(out)
            latest = alerts.latest()
            settled = latest is None or bool(latest.get("reviewed")) or alerts.answered(latest)
            if wait <= 0 or settled or time.time() >= deadline:
                break
            time.sleep(POLL_EVERY)
    if not paths.headless() and reply is None:  # a targeted --reply never consumes the listings
        out["unreviewed"] = _take_unreviewed()
        out["unseen_runs"] = _take_unseen_runs()
    return out


def _run_queued(out: dict[str, Any]) -> None:
    """Root actions approved earlier run now that someone can answer the dialog."""
    if paths.headless():
        return
    for entry in ledger.queued():
        ledger.execute(entry)
        out["executed"].append(ledger.brief(entry))
        _ack(out, f"{ledger.icon(entry)} {entry['n']} · {entry['result']}", entry.get("source", "chat"))


def _drain_discord(out: dict[str, Any]) -> None:
    st = notify.state()
    msgs = notify.fetch(st.get("last_seen"))
    if not msgs:
        return
    if st.get("last_seen") is None:  # first drain: never replay channel history
        notify.save_state(last_seen=msgs[-1]["id"])
        return
    for m in msgs:
        if m["author_id"] == notify.user_id():
            ts = notify.batch_for(m["id"])
            batch = alerts.load(ts) if ts else None
            if batch is None:
                _ack(out, HINT, "discord")
            elif batch.get("reviewed"):
                _ack(out, f"batch {alerts.local_label(ts)} is closed", "discord")
            else:
                _handle(batch, m["content"], "discord", m["id"], out)
        notify.save_state(last_seen=m["id"])


def _handle(batch: dict[str, Any], text: str, source: str, msg_id: str | None,
            out: dict[str, Any]) -> None:
    ops = parse(text, alerts.numbers(batch))
    if ops is None:
        _ack(out, HINT, source)
        return
    for verb, n in ops:
        if verb == "skip":
            alerts.mark(batch["ts"], reviewed=ledger.now())
            _ack(out, "🤷 closed, nothing changed", source)
            continue
        f = alerts.finding(batch, n)
        if verb == "why":
            _ack(out, f"{n} · {str(f.get('narrative') or f.get('headline') or '')[:1500]}", source)
            continue
        entry = ledger.build(batch, f, verb, source, msg_id)
        if entry is None:
            _ack(out, f"{n} · nothing to run; reply ok {n} to accept or skip", source)
            continue
        _record_answer(batch["ts"], n, verb)
        if entry["needs_root"] and paths.headless():
            ledger.save(entry)
            out["queued"].append(ledger.brief(entry))
            _ack(out, f"⏳ {n} · needs admin · runs at next session at the Mac", source)
            continue
        ledger.execute(entry)
        out["executed"].append(ledger.brief(entry))
        _ack(out, f"{ledger.icon(entry)} {n} · {entry['result']}", source)
    fresh = alerts.load(batch["ts"])
    if fresh and alerts.answered(fresh) and not fresh.get("reviewed"):
        alerts.mark(batch["ts"], reviewed=ledger.now())


def _record_answer(ts: str, n: int, verb: str) -> None:
    batch = alerts.load(ts) or {}
    answers = dict(batch.get("answers") or {})
    answers[str(n)] = verb
    alerts.mark(ts, answers=answers)


def _ack(out: dict[str, Any], text: str, source: str) -> None:
    out["acks"].append(text)
    if source == "discord":
        notify.post(text)


def _take_unreviewed() -> list[dict[str, Any]]:
    batches = alerts.unreviewed()
    for b in batches:
        alerts.mark(b["ts"], reviewed=ledger.now())
    return [{"ts": b["ts"], "findings": b.get("findings") or []} for b in batches]


def _take_unseen_runs() -> list[dict[str, Any]]:
    st = read_json(paths.SCHEDULE_STATE, default={}) or {}
    runs = st.get("runs") or []
    unseen = [r for r in runs if not r.get("seen")]
    if unseen:
        for r in runs:
            r["seen"] = True
        write_json(paths.SCHEDULE_STATE, st)
    return [{k: r.get(k) for k in ("ts", "ended", "reason", "findings", "posted")} for r in unseen]


def secs(spec: str | None) -> int:
    """'20m' → 1200. Bare numbers are seconds."""
    if not spec:
        return 0
    m = re.match(r"^(\d+)([smh]?)$", spec.strip().lower())
    if not m:
        raise SystemExit(f"bad duration {spec!r}; use e.g. 20m")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edr poll")
    ap.add_argument("--wait", help="keep polling the channel for up to e.g. 20m")
    ap.add_argument("--reply", help="a decision typed in chat, same grammar as a Discord reply")
    ap.add_argument("--batch", help="batch ts the --reply refers to (default: latest)")
    args = ap.parse_args(argv)
    paths.ensure()
    print(json.dumps(drain(secs(args.wait), args.reply, args.batch), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
